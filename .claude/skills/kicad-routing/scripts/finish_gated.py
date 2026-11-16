#!/usr/bin/env python
"""finish_gated.py - finish the connections the autorouter left, one at a time, with route_finish.py, every
attempt gated by KiCad DRC.

For each unconnected item of a fresh DRC report, route_finish.py is run between its two end points at the width
given for the net (falling back to narrower widths: 0.6 mm for wider nets, then 0.2 mm). The attempt is KEPT only if
DRC gains no violation of any type and the unconnected count falls; otherwise the board is restored from the copy
taken just before. After a kept route the list is re-read (one route changes what the next can reach); an item
that failed is not retried. Long connections (> 30 mm) use a coarser grid (0.1 mm) so the search stays bounded.

Layout gate (board review rev. 0.2, 2026-10-20): DRC cannot see a route that joins a Kelvin sense trace to the
load copper (same net) - three finish_gated routes on ServiceOne did exactly that at the U13 sense trace. When the
project parameters (kicad_golden.project.json beside the board, or --params) have `layout_checks`, the script runs
`layout_measure.py check` once at the start and records which checks PASS; after every route the DRC gate would
keep it runs the checks again, and a check that passed and now FAILs reverts the route:
"REVERTED (layout check <name> broke)". --no-layout-gate turns this off. Checks that already FAIL at the start are
not gated (fix them first; they are listed).

Audit gate (1.27.0, ServiceOne D133 review): DRC passes a route that runs between two pads, enters a pad off its
axis, drops a via into a pad or turns sharper than 90 degrees. After DRC and the layout gate, the audit runs and the
route is REVERTED if it adds any FAIL the board did not have (audit_gate.py: compared by identity, not by count).
--no-audit-gate turns this off; do not use it for a board that goes to review.

Stop rule (1.28.0, L30): after 10 attempts or 30 min the run stops when fewer than 1 in 5 attempts were kept or the
projected time exceeds --budget (default 60 min); it then lists the connections left for the interactive router
(<board>.finish_open.json). --no-stop-rule for experiments. Locks (L40): an attempt that moves, changes or removes a
locked track or via is reverted (locks.py), even when DRC and the audit pass. Fast gate (L32): the zones are refilled
for the per-attempt DRC only when the routed net has a zone (a plane via connects through the fill); otherwise the
zone-fill violations are ignored per attempt, and the end of the run checks DRC with --refill-zones.
--refill-every-attempt restores the 1.27 gate.

What it cannot do: shove neighbouring copper. A pad boxed in by other nets stays open - finish those in KiCad
with the interactive router (ServiceOne, 2026-10-04: 24 -> 14 open, the rest boxed in).

Usage (system Python; KiCad installed):
    finish_gated.py <board.kicad_pcb> [--width NET=MM ...] [--default-width 0.2] [--no-narrow] [--via-cost N] [--log FILE]
                    [--params kicad_golden.project.json] [--no-layout-gate] [--no-audit-gate]
                    [--budget MIN] [--min-keep-rate R] [--no-stop-rule] [--refill-every-attempt]
                    [--kicad-python PATH] [--kicad-cli PATH] [--force-write]
The board is modified in place; a backup <board>.bak_prefinish is written first. Close KiCad: the board must have
no KiCad lock and its .kicad_pro beside it (board_guard.py; --force-write overrides, and is passed on).
"""
import collections
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kicad_sexp as KS  # noqa: E402
import board_guard  # noqa: E402
import audit_gate  # noqa: E402
import locks  # noqa: E402
import stop_rule  # noqa: E402

a = sys.argv[1:]
if '--help' in a or '-h' in a:
    sys.stdout.write(__doc__)
    sys.exit(0)
if not a or a[0].startswith('--'):
    sys.stderr.write(__doc__)
    sys.exit(2)
opt = lambda n, d=None: a[a.index(n) + 1] if n in a else d
BOARD = os.path.abspath(a[0])
WIDTH = {}
for i, t in enumerate(a):
    if t == '--width' and i + 1 < len(a) and '=' in a[i + 1]:
        n, w = a[i + 1].rsplit('=', 1)
        WIDTH[n] = float(w)
DEFAULT_W = float(opt('--default-width', '0.2'))
VIA_COST = opt('--via-cost')        # passed to route_finish.py (default there)
NO_NARROW = '--no-narrow' in a      # keep the given width: no 0.6 / 0.2 fallback (a neckdown on a rail)
NO_LAYOUT_GATE = '--no-layout-gate' in a
NO_AUDIT_GATE = '--no-audit-gate' in a
REFILL_ALL = '--refill-every-attempt' in a
RULE = stop_rule.StopRule.from_argv(a)
PARAMS = os.path.abspath(opt('--params', os.path.join(os.path.dirname(BOARD), 'kicad_golden.project.json')))
board_guard.check_board_writable(BOARD, argv=a[1:], script='finish_gated.py')   # override exported to route_finish
KP = KS.find_kicad_python(opt('--kicad-python'))
CLI = KS.find_kicad_cli(opt('--kicad-cli'))
if not (KP and CLI):
    sys.exit('need KiCad\'s python (%s) and kicad-cli (%s); pass --kicad-python / --kicad-cli' % (KP, CLI))
RF = os.path.join(HERE, 'route_finish.py')
LM = os.path.join(HERE, 'layout_measure.py')
LOG = opt('--log', os.path.splitext(BOARD)[0] + '.finish.log')
log = open(LOG, 'a', encoding='utf-8')
DRCJ = os.path.splitext(BOARD)[0] + '.finish_drc.json'
AUDJ = os.path.splitext(BOARD)[0] + '.finish_audit.json'


def say(*x):
    s = ' '.join(str(v) for v in x)
    print(s, flush=True)
    log.write(s + '\n'); log.flush()


def drc(refill=True):
    subprocess.run([CLI, 'pcb', 'drc', '--severity-all', '--format', 'json', '-o', DRCJ, BOARD]
                   + (['--refill-zones'] if refill else []), capture_output=True)
    d = json.load(open(DRCJ, encoding='utf-8'))
    keep = [v for v in d['violations']                    # without a refill, a violation against the old fill is noise
            if refill or not any(i.get('description', '').startswith('Zone') for i in v['items'])]
    return d, collections.Counter((v['type'], v['severity']) for v in keep), len(d['unconnected_items'])


def zone_nets(path):
    """Nets with a copper zone: a route on one of them may connect through the fill, so its DRC refills (L32).
    KiCad 9 writes (net N) (net_name "X") in a zone, KiCad 10 (net "X"); rule areas (keepout) carry no net."""
    out = set()
    for z in re.findall(r'^\t\(zone\b.*?^\t\)', open(path, encoding='utf-8').read(), re.S | re.M):
        n = re.search(r'\(net_name "([^"]*)"\)|\(net "([^"]*)"\)', z)
        if n and '(keepout' not in z and (n.group(1) or n.group(2)):
            out.add(n.group(1) or n.group(2))
    return out


ZONE_NETS = zone_nets(BOARD)


def layout_names():
    """Names of the project's layout checks, in the order layout_measure.py check reports them."""
    try:
        lc = (json.load(open(PARAMS, encoding='utf-8')) or {}).get('layout_checks') or {}
    except (OSError, ValueError):
        return []
    n = ['kelvin %s/%s/%s' % (k.get('sense'), k.get('shunt'), k.get('load')) for k in lc.get('kelvin', [])]
    n += ['decoupling %s-%s' % (k.get('pin'), k.get('cap')) for k in lc.get('decoupling', [])]
    n += ['separation %s|%s' % (','.join(k.get('a', [])), ','.join(k.get('b', []))) for k in lc.get('separation', [])]
    return n


def layout():
    """{check name: pass} from layout_measure.py check on the board as it is on disk."""
    j = os.path.splitext(BOARD)[0] + '.finish_layout.json'
    if os.path.exists(j):
        os.remove(j)
    r = subprocess.run([KP, LM, 'check', BOARD, '--params', PARAMS, '--json', j], capture_output=True, text=True,
                       timeout=1800)
    try:
        rows = json.load(open(j, encoding='utf-8'))
    except (OSError, ValueError):
        say('  layout check did not run (exit %d): %s' % (r.returncode, (r.stderr or r.stdout).strip()[-200:]))
        return None
    names = layout_names()
    if len(names) != len(rows):
        names = ['%s #%d' % (x.get('check', '?'), i) for i, x in enumerate(rows)]
    return {nm: bool(x.get('pass')) for nm, x in zip(names, rows) if 'pass' in x}


def _pad_tag(desc):
    """'Pad 2 [GND] of C24 on F.Cu' -> 'C24.2'; None for a track or a via end."""
    m = re.match(r'^(?:SMD |PTH )?[Pp]ad (\S+) \[.*\] of (\S+)', desc or '')
    return '%s.%s' % (m.group(2), m.group(1)) if m else None


def items(d):
    out = []
    for u in d['unconnected_items']:
        p, q = u['items'][0], u['items'][1]
        m = re.search(r'\[([^\]]+)\]', p['description'])
        out.append((m.group(1) if m else '?', (p['pos']['x'], p['pos']['y']), (q['pos']['x'], q['pos']['y']),
                    _pad_tag(p['description']), _pad_tag(q['description'])))
    return out


shutil.copy2(BOARD, BOARD + '.bak_prefinish')
d, viol0, n0 = drc()
say('start: unconnected %d, DRC %s' % (n0, dict(viol0)))
_, viol0_fast, _ = drc(refill=False)                # per-attempt baseline without a refill
LOCKS = locks.fingerprint(BOARD)
if LOCKS:
    say('locks: %d locked track(s) / via(s); an attempt that moves one is reverted' % len(LOCKS))
if RULE:
    say(RULE.estimate(n0, 1.5, 1.0 if REFILL_ALL else 0.5))
STOPPED = None
GATE = set()                         # layout checks that PASS at the start: a route may not break them
if NO_LAYOUT_GATE:
    say('layout gate: off (--no-layout-gate)')
elif not layout_names():
    say('layout gate: off (no layout_checks in %s)' % PARAMS)
else:
    base = layout()
    if base is None:
        sys.exit('layout gate: layout_measure.py check failed on the start board; fix it or pass --no-layout-gate')
    GATE = {k for k, v in base.items() if v}
    say('layout gate: %d check(s) PASS at the start and are gated%s' % (
        len(GATE), ''.join('\n  not gated (FAILs already): %s' % k for k, v in sorted(base.items()) if not v)))
IDS = None                           # audit FAIL identities of the board as it stands: a route may add none
if NO_AUDIT_GATE:
    say('audit gate: off (--no-audit-gate)')
else:
    IDS = audit_gate.fail_ids(audit_gate.audit(BOARD, AUDJ, PARAMS if os.path.exists(PARAMS) else None))
    say('audit gate: %d FAIL(s) on the start board; a route that adds one is reverted' % sum(IDS.values()))
tried, progress = set(), True
while progress and not STOPPED:
    progress = False
    for net, p, q, pa, qa in items(d):
        if RULE:
            STOPPED = RULE.should_stop(len(d['unconnected_items']))
            if STOPPED:
                say('STOP RULE: %s' % STOPPED)
                break
        key = (net, round(p[0], 2), round(p[1], 2), round(q[0], 2), round(q[1], 2))
        if key in tried:
            continue
        tried.add(key)
        w = WIDTH.get(net, DEFAULT_W)
        far = ((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2) ** 0.5
        grid = '0.1' if far > 30 else '0.05'
        for wa in [w] + ([] if NO_NARROW else ([0.6] if w > 0.6 else []) + ([0.2] if w > 0.2 else [])):
            shutil.copy2(BOARD, BOARD + '.try')
            # 1.26.4: a pad end is routed pad-to-pad (route_finish.py axial stub, 1.23.0); coordinates as fall-back
            ends = (['--from-pad', pa] if pa else ['--from', '%.4f,%.4f' % p]) +                    (['--to-pad', qa] if qa else ['--to', '%.4f,%.4f' % q])
            base_cmd = [KP, RF, BOARD, '--net', net, '--width', str(wa), '--grid', grid, '--safety', grid,
                        '--clearance', '0.105'] + (['--via-cost', VIA_COST] if VIA_COST else [])
            r = subprocess.run(base_cmd + ends, capture_output=True, text=True, timeout=1800)
            if r.returncode != 0 and (pa or qa):
                shutil.copy2(BOARD + '.try', BOARD)
                r = subprocess.run(base_cmd + ['--from', '%.4f,%.4f' % p, '--to', '%.4f,%.4f' % q],
                                   capture_output=True, text=True, timeout=1800)
            if r.returncode != 0:
                tail = (r.stdout + r.stderr).strip().splitlines()[-1:] if (r.stdout + r.stderr).strip() else ''
                say('  %-28s w%.2f  route_finish exit %d %s' % (net[:28], wa, r.returncode, tail))
                shutil.copy2(BOARD + '.try', BOARD)
                continue
            refill = REFILL_ALL or net in ZONE_NETS
            d2, viol, n = drc(refill)
            ref = viol0 if refill else viol0_fast
            worse = {k: viol[k] - ref.get(k, 0) for k in viol if viol[k] > ref.get(k, 0)}
            if worse or n >= n0:
                say('  %-28s w%.2f  REVERTED (unconnected %d -> %d, new %s)' % (net[:28], wa, n0, n, worse))
                shutil.copy2(BOARD + '.try', BOARD)
                if RULE:
                    RULE.attempt(False)
                continue
            moved = locks.changed(LOCKS, locks.fingerprint(BOARD))
            if moved:
                say('  %-28s w%.2f  REVERTED (%s)' % (net[:28], wa, moved[0]))
                shutil.copy2(BOARD + '.try', BOARD)
                if RULE:
                    RULE.attempt(False)
                continue
            if GATE:
                now = layout()
                broke = sorted(k for k in GATE if now is None or not now.get(k, False))
                if broke:
                    say('  %-28s w%.2f  REVERTED (layout check %s broke)' % (net[:28], wa, ', '.join(broke)))
                    shutil.copy2(BOARD + '.try', BOARD)
                    if RULE:
                        RULE.attempt(False)
                    continue
            if IDS is not None:
                allf = audit_gate.audit(BOARD, AUDJ, PARAMS if os.path.exists(PARAMS) else None)
                new = audit_gate.new_fails(IDS, allf)
                if new:
                    say('  %-28s w%.2f  REVERTED (%d new audit FAIL, first [%s] %s)' % (
                        net[:28], wa, len(new), new[0]['check'], new[0]['msg'][:110]))
                    shutil.copy2(BOARD + '.try', BOARD)
                    if RULE:
                        RULE.attempt(False)
                    continue
                IDS = audit_gate.fail_ids(allf)
            say('  %-28s w%.2f  KEPT (unconnected %d -> %d)' % (net[:28], wa, n0, n))
            if RULE:
                RULE.attempt(True)
            if refill:
                d, viol0, n0 = d2, viol, n
                _, viol0_fast, _ = drc(refill=False)
            else:
                d, viol0_fast, n0 = d2, viol, n
            progress = True
            break
        if progress:
            break
d, viol0, n0 = drc()                                # stage end: DRC with the zones refilled
if n0:
    OPEN = os.path.splitext(BOARD)[0] + '.finish_open.json'
    json.dump([{'net': net, 'a': p, 'b': q, 'a_pad': pa, 'b_pad': qa} for net, p, q, pa, qa in items(d)],
              open(OPEN, 'w', encoding='utf-8'), indent=1)
    say('%d connection(s) left for the interactive router: %s' % (n0, OPEN))
for f in (BOARD + '.try', os.path.splitext(BOARD)[0] + '.finish_layout.json', AUDJ):
    if os.path.exists(f):
        os.remove(f)
if RULE:
    say(RULE.summary())
say('end: unconnected %d, DRC %s%s' % (n0, dict(viol0), ' (stopped: %s)' % STOPPED if STOPPED else ''))
