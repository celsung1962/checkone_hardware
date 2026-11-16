#!/usr/bin/env python
"""stage_gate.py - gate one change to a routed board against a snapshot taken just before it (lessons L27, L32, L40,
L42; ServiceOne rev. 0.2 work, Claude, 2026-10-22/23).

A change passes when, against the snapshot:
  - KiCad DRC gains no violation of any type and the unconnected count does not rise;
  - the audit has no NEW FAIL by identity (audit_gate.py; a lower total does not excuse a new FAIL);
  - every layout check (layout_measure.py check: Kelvin, decoupling, separation) that passed still passes;
  - every locked track and via is unchanged (locks.py);
  - KiCad Routing Tools' copper-hygiene checker has no NEW finding (krt_check.py: soft joints, redundant loops,
    removable or stacked copper, dangling ends, orphan islands), when the plugin is installed (1.29.0). --no-krt
    skips it; a snapshot taken without it is compared without it.
Without --refill the DRC skips the zone refill and ignores violations against a zone fill (a refill clears them):
about 30 s per gate instead of minutes (L32). Run the last gate of a stage with --refill.

The snapshot normalises the baseline (L42): with --normalise the board is loaded and saved once through pcbnew before
the snapshot, so a later pcbnew save does not "add" FAILs that only depend on the order of items in the file (the
shared-gap message did before 1.28.0). The snapshot copies the .kicad_pro, .kicad_dru, the project parameters and the
3D-model folder beside the board: without them the audit reports false 'model' FAILs and pcbnew writes default rules.

Usage (system Python; node and KiCad installed):
    stage_gate.py SNAPSHOT_DIR BOARD --snap [--normalise] [--no-krt]   record the baseline; exit 0
    stage_gate.py SNAPSHOT_DIR BOARD [--refill]             compare; exit 0 PASS, 1 BLOCKED
Options: --params FILE (default kicad_golden.project.json beside the board), --kicad-python PATH, --kicad-cli PATH.
Module API: snapshot(snap_dir, board, ...), compare(snap_dir, board, ...) -> (ok, report_lines).
"""
import collections
import glob
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kicad_sexp as KS  # noqa: E402
import audit_gate  # noqa: E402
import locks  # noqa: E402
import krt_check  # noqa: E402


def _params(board, params=None):
    p = params or os.path.join(os.path.dirname(os.path.abspath(board)), 'kicad_golden.project.json')
    return p if os.path.isfile(p) else None


def drc(cli, pcb, out, refill=False):
    subprocess.run([cli, 'pcb', 'drc', '--severity-all', '--format', 'json', '-o', out, pcb]
                   + (['--refill-zones'] if refill else []), capture_output=True)
    d = json.load(open(out, encoding='utf-8'))
    keep = [v for v in d['violations'] if refill or not any(
        i.get('description', '').startswith('Zone') for i in v['items'])]
    return {'viol': dict(collections.Counter('%s|%s' % (v['type'], v['severity']) for v in keep)),
            'unconnected': len(d['unconnected_items'])}


def layout(kp, pcb, out, params):
    if not params or not (json.load(open(params, encoding='utf-8')) or {}).get('layout_checks'):
        return []
    if os.path.exists(out):
        os.remove(out)
    subprocess.run([kp, os.path.join(HERE, 'layout_measure.py'), 'check', pcb, '--params', params, '--json', out],
                   capture_output=True, env=dict(os.environ, MSYS_NO_PATHCONV='1'))
    try:
        rows = json.load(open(out, encoding='utf-8'))
    except (OSError, ValueError):
        return None
    rows = rows if isinstance(rows, list) else rows.get('results', [])
    return [bool(x.get('pass')) for x in rows]


NORMALISE = r'''
import sys, pcbnew
b = pcbnew.LoadBoard(sys.argv[1]); pcbnew.SaveBoard(sys.argv[1], b)
'''


def snapshot(snap, board, params=None, kp=None, cli=None, normalise=False, krt=True):
    board = os.path.abspath(board)
    os.makedirs(snap, exist_ok=True)
    stem = os.path.splitext(board)[0]
    params = _params(board, params)
    if normalise:
        import board_guard
        board_guard.check_board_writable(board, argv=[], script='stage_gate.py')
        subprocess.run([kp, '-c', NORMALISE, board], capture_output=True)
    for f in [board, stem + '.kicad_pro', stem + '.kicad_dru'] + ([params] if params else []):
        if os.path.isfile(f):
            shutil.copy2(f, snap)
    for m3d in glob.glob(os.path.join(os.path.dirname(board), '*.3dshapes')):
        dst = os.path.join(snap, os.path.basename(m3d))
        if not os.path.isdir(dst):
            shutil.copytree(m3d, dst)
    sb = os.path.join(snap, os.path.basename(board))
    sp = os.path.join(snap, os.path.basename(params)) if params else None
    res = {'drc': drc(cli, sb, os.path.join(snap, 'drc.json')),
           'drc_refill': drc(cli, sb, os.path.join(snap, 'drc_refill.json'), refill=True),
           'layout': layout(kp, sb, os.path.join(snap, 'layout.json'), sp),
           'locks': {u: list(v) for u, v in locks.fingerprint(sb).items()},
           'krt': krt_check.check(sb, kp=kp) if krt else None}
    audit_gate.audit(sb, os.path.join(snap, 'audit.json'), sp)
    json.dump(res, open(os.path.join(snap, 'gate_base.json'), 'w', encoding='utf-8'), indent=1)
    return res


def compare(snap, board, params=None, kp=None, cli=None, refill=False):
    board = os.path.abspath(board)
    params = _params(board, params)
    base = json.load(open(os.path.join(snap, 'gate_base.json'), encoding='utf-8'))
    work = os.path.splitext(board)[0] + '.gate'
    b0 = base['drc_refill' if refill else 'drc']
    d = drc(cli, board, work + '_drc.json', refill)
    lay = layout(kp, board, work + '_layout.json', params)
    cur = audit_gate.audit(board, work + '_audit.json', params)
    bf = json.load(open(os.path.join(snap, 'audit.json'), encoding='utf-8'))['findings']
    new = audit_gate.new_fails(bf, cur)
    gone = sum(audit_gate.fail_ids(bf).values()) - sum(audit_gate.fail_ids(cur).values()) + len(new)
    worse = {k: v - b0['viol'].get(k, 0) for k, v in d['viol'].items() if v > b0['viol'].get(k, 0)}
    broke = ['layout check did not run'] if lay is None else [
        i for i, (p0, p1) in enumerate(zip(base['layout'], lay)) if p0 and not p1]
    kf = krt_check.check(board, kp=kp) if base.get('krt') is not None else None
    knew = krt_check.new_findings(base['krt'], kf) if kf is not None else []
    moved = locks.changed({u: tuple(v) for u, v in base.get('locks', {}).items()}, locks.fingerprint(board))
    ok = not worse and d['unconnected'] <= b0['unconnected'] and not new and not broke and not moved and not knew
    lines = ['DRC new %s | unconnected %d -> %d | audit FAIL new %d, removed %d | layout broken %s | locks %s | krt new %s | %s' % (
        worse or '{}', b0['unconnected'], d['unconnected'], len(new), gone, broke or '[]',
        moved[0] if moved else 'unchanged', len(knew) if kf is not None else 'off', 'PASS' if ok else 'BLOCKED')]
    lines += ['  NEW [%s] %s' % (f['check'], f['msg'][:170]) for f in new[:15]]
    lines += ['  NEW krt [%s] %s (%s) @ %.3f,%.3f' % (f['check'], f['net'], f['layer'], f['x'], f['y']) for f in knew[:15]]
    for f in (work + '_drc.json', work + '_layout.json', work + '_audit.json'):
        if os.path.exists(f):
            os.remove(f)
    return ok, lines


def main(a):
    if len(a) < 2 or a[0].startswith('-'):
        sys.stdout.write(__doc__)
        return 2
    opt = lambda n: a[a.index(n) + 1] if n in a else None
    kp, cli = KS.find_kicad_python(opt('--kicad-python')), KS.find_kicad_cli(opt('--kicad-cli'))
    if not (kp and cli):
        sys.exit("need KiCad's python (%s) and kicad-cli (%s); pass --kicad-python / --kicad-cli" % (kp, cli))
    snap, board = os.path.abspath(a[0]), os.path.abspath(a[1])
    if '--snap' in a:
        res = snapshot(snap, board, opt('--params'), kp, cli, normalise='--normalise' in a, krt='--no-krt' not in a)
        print('snapshot %s: unconnected %d, DRC %s, %d locked item(s), krt %s' % (
            snap, res['drc']['unconnected'], res['drc']['viol'], len(res['locks']),
            'not installed' if res['krt'] is None else '%d finding(s)' % sum(not f['filtered'] for f in res['krt'])))
        return 0
    ok, lines = compare(snap, board, opt('--params'), kp, cli, refill='--refill' in a)
    print('\n'.join(lines))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
