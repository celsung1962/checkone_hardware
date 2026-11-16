#!/usr/bin/env python3
"""Hardware checks for a KiCad repository, driven by hw_checks.json at the repository root (same file locally and in CI).

Per board in the config:
  - ERC (kicad-cli sch erc) and DRC (kicad-cli pcb drc, with --schematic-parity unless "parity": false), compared
    with a committed baseline (tools/hw_checks/baseline/<board>.json). A violation is identified by its type and the
    descriptions of its items (references, nets, pins; no coordinates), counted. FAIL only on violations that are not
    in the baseline; violations that disappeared are reported so the baseline can be refreshed.
  - "commands": project scripts (netlist rules, verify gates, datasheet check). Exit code != 0 is a FAIL, unless the
    command has "known_failure": {"problem_line": <regex>, "match": <regex>, "reason": <text>} and every output line
    matching problem_line also matches match - then it is a warning (reason says what closes it); any other problem
    line still fails.
    In "cmd", {python} is this Python and {netlist} the board's netlist exported fresh from its schematic.
Top-level "ignore": [{"type": <violation type>, "check": "erc"|"drc" (optional), "reason": ...}] - types left out of
the comparison because they differ between platforms (e.g. text_thickness on TrueType fonts); counted in the summary.
Top-level "commands" run once (e.g. the datasheet manifest check).

    python tools/hw_checks/hw_checks.py                     run everything
    python tools/hw_checks/hw_checks.py --board GapOne_AMP  one board
    python tools/hw_checks/hw_checks.py --update-baseline   accept the current ERC / DRC as the new baseline

kicad-cli: $KICAD_CLI, else on PATH, else the newest C:\\Program Files\\KiCad\\*\\bin\\kicad-cli.exe.
In GitHub Actions: annotations (::error / ::warning) and a Markdown summary in $GITHUB_STEP_SUMMARY.
"""
import argparse
import collections
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.getcwd()
CI = os.environ.get('GITHUB_ACTIONS') == 'true'


def kicad_cli():
    c = (os.environ.get('KICAD_CLI') or shutil.which('kicad-cli')
         or next(iter(sorted(glob.glob(r'C:\Program Files\KiCad\*\bin\kicad-cli.exe'), reverse=True)), None))
    if not c:
        sys.exit('kicad-cli not found: set KICAD_CLI')
    return c


def signatures(kind, path):
    """Counter of violation signatures from a kicad-cli ERC / DRC json report."""
    d = json.load(open(path, encoding='utf-8'))
    items = []
    if kind == 'erc':
        for s in d['sheets']:
            items += [(s['path'], v) for v in s['violations']]
    else:
        items = [('', v) for v in d['violations'] + d.get('schematic_parity', [])]
        items += [('', dict(v, type='unconnected_items')) for v in d.get('unconnected_items', [])]
    sig = collections.Counter()
    for where, v in items:
        if v['type'] == 'unconnected_items':
            # KiCad pairs the unconnected pads of a net differently from run to run: count per net instead
            nets = sorted({n for i in v.get('items', []) for n in re.findall(r'\[([^\]]+)\]', i.get('description', ''))})
            sig[f"unconnected_items | net {', '.join(nets)}"] += 1
            continue
        desc = ' / '.join(sorted(i.get('description', '') for i in v.get('items', [])))
        sig[f"{v['type']} | {where} {desc}".strip()] += 1
    return sig


def run(cmd, timeout=1800):
    t = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout)
    return r, time.time() - t


def note(level, msg):
    if CI:
        print(f'::{level}::{msg}')
    else:
        print(f'  {level.upper()}: {msg}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', default='hw_checks.json')
    ap.add_argument('--board', action='append')
    ap.add_argument('--update-baseline', action='store_true')
    a = ap.parse_args()
    cfg = json.load(open(os.path.join(ROOT, a.config), encoding='utf-8-sig'))
    cli = kicad_cli()
    base_dir = os.path.join(ROOT, cfg.get('baseline_dir', 'tools/hw_checks/baseline'))
    tmp = tempfile.mkdtemp()
    summary, failed = ['## Hardware checks', '', '| Board | Check | Result |', '|---|---|---|'], False

    def command(board, c, stem=None):
        nonlocal failed
        cmd = [sys.executable if x == '{python}' else x for x in c['cmd']]
        if '{netlist}' in cmd:                      # the board's netlist, exported fresh from the schematic
            net = os.path.join(tmp, f'{board}.net')
            if not os.path.exists(net):
                run([cli, 'sch', 'export', 'netlist', '--format', 'kicadsexpr', '-o', net, stem + '.kicad_sch'])
            cmd = [net if x == '{netlist}' else x for x in cmd]
        r, dt = run(cmd)
        out = (r.stdout + r.stderr).strip()
        print(f"\n--- {board} / {c['name']} (exit {r.returncode}, {dt:.0f} s)\n{out[-4000:]}")
        kf = c.get('known_failure')
        problems = [ln.strip() for ln in out.splitlines() if kf and re.search(kf['problem_line'], ln)]
        if r.returncode == 0:
            res = 'PASS'
        elif kf and problems and all(re.search(kf['match'], p) for p in problems):
            res = f"KNOWN FAIL - {kf['reason']}"
            note('warning', f"{board} {c['name']}: known failure - {kf['reason']}")
        else:
            unknown = [p for p in problems if not re.search(kf['match'], p)]
            for p in unknown or [(out.splitlines() or [''])[-1].strip()]:
                note('error', f"{board} {c['name']}: {p}")
            res, failed = 'FAIL', True
        summary.append(f"| {board} | {c['name']} | {res} |")

    for b in cfg['boards']:
        name = b['name']
        if a.board and name not in a.board:
            continue
        stem = os.path.splitext(os.path.join(ROOT, b['project']))[0]
        bl_path = os.path.join(base_dir, f'{name}.json')
        baseline = json.load(open(bl_path, encoding='utf-8-sig')) if os.path.exists(bl_path) else {}
        current = {}
        for kind in ('erc', 'drc'):
            if not b.get(kind, True):
                continue
            out = os.path.join(tmp, f'{name}_{kind}.json')
            if kind == 'erc':
                cmd = [cli, 'sch', 'erc', '--format', 'json', '--severity-all', '-o', out, stem + '.kicad_sch']
            else:
                cmd = [cli, 'pcb', 'drc', '--format', 'json', '--severity-all', '-o', out, stem + '.kicad_pcb']
                if b.get('parity', True):
                    cmd.insert(3, '--schematic-parity')
            r, dt = run(cmd)
            if not os.path.exists(out):
                failed = True
                note('error', f'{name} {kind.upper()}: kicad-cli produced no report: {(r.stderr or r.stdout).strip()[-500:]}')
                summary.append(f'| {name} | {kind.upper()} | FAIL (no report) |')
                continue
            sig = signatures(kind, out)
            ign = {i['type'] for i in cfg.get('ignore', []) if i.get('check', kind) == kind}
            vtype = lambda s: s.split('|')[0].strip()   # 'text_thickness |' (no description) has no ' | '
            n_ign = sum(n for s, n in sig.items() if vtype(s) in ign)
            sig = collections.Counter({s: n for s, n in sig.items() if vtype(s) not in ign})
            current[kind] = dict(sorted(sig.items()))
            old = collections.Counter({s: n for s, n in baseline.get(kind, {}).items() if vtype(s) not in ign})
            new, gone = sig - old, old - sig
            print(f'\n--- {name} / {kind.upper()} ({dt:.0f} s): {sum(sig.values())} item(s), baseline '
                  f'{sum(old.values())}, new {sum(new.values())}, fixed {sum(gone.values())}')
            for s, n in sorted(new.items()):
                print(f'  NEW x{n}: {s}')
            for s, n in sorted(gone.items())[:20]:
                print(f'  fixed x{n}: {s}')
            if not baseline and not a.update_baseline:
                res = f'NO BASELINE ({sum(sig.values())} items) - run with --update-baseline'
                note('warning', f'{name} {kind.upper()}: no baseline')
            elif new and not a.update_baseline:
                failed, res = True, f'FAIL - {sum(new.values())} new item(s)'
                for s, n in sorted(new.items())[:30]:
                    note('error', f'{name} {kind.upper()} new: {s}' + (f' (x{n})' if n > 1 else ''))
            else:
                res = f'PASS ({sum(sig.values())} items, all in the baseline)'
                if gone:
                    res += f'; {sum(gone.values())} fixed - refresh the baseline'
            if n_ign:
                res += f'; {n_ign} ignored ({", ".join(sorted(ign))})'
            summary.append(f'| {name} | {kind.upper()} | {res} |')
        if a.update_baseline and current:
            os.makedirs(base_dir, exist_ok=True)
            json.dump(current, open(bl_path, 'w', encoding='utf-8', newline='\n'), indent=1, ensure_ascii=False)
            print(f'baseline written: {os.path.relpath(bl_path, ROOT)}')
        for c in b.get('commands', []):
            command(name, c, stem)
    if not a.board:
        for c in cfg.get('commands', []):
            command('(repository)', c)

    text = '\n'.join(summary) + '\n'
    print('\n' + text)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8').write(text)
    print('HW CHECKS: ' + ('FAIL' if failed else 'PASS'))
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
