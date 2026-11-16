#!/usr/bin/env python
"""krt_check.py - KiCad Routing Tools' copper-hygiene checker (check_weird.py) as a second checker beside the audit
(1.29.0; GapOne CON, 2026-11-06).

KiCad Routing Tools (github.com/drandyhaas/KiCadRoutingTools, MIT) is a KiCad plugin with an A* router. Its router
is not used here: on the GapOne CON board it closed all 98 open connections, but added 1688 audit FAILs, ripped
copper it had been told to keep and stepped the vias down to the fabricator's costlier tier. Its read-only
check_weird.py, however, finds copper defects the audit names differently or not at all, among them:
  soft-joint         same-net segments that meet only by overlapping end caps (the "patched" look of a joint)
  redundant-cycle    a loop edge whose removal leaves the net's connectivity identical
  removable-segment  copper that can go without disconnecting anything or leaving a new dangling end
  stacked-copper     exact duplicate segments, coincident same-net vias
  dangling-end, orphan-island, unsupported-via, dangling-via, narrow-pad-joint, kicad-dangling
The advisory off-centre-via-end category is reported by check_weird after its count and is ignored here.

Known false positive, filtered: check_weird does not see inner-layer zone fills, so a via whose net is a pour on a
layer the via spans is reported as `dangling-via`; KiCad's DRC passes it. Those are dropped (counted in 'filtered').

A finding's identity is category + net + layer (coordinates and sizes blanked), counted, as in audit_gate.py: copper
that only moved keeps its identity, a new soft joint on a net that had none is new.

Usage (system Python or KiCad's; check_weird runs under KiCad's Python):
    krt_check.py BOARD [--json OUT] [--tolerance 0.1]            report; exit 0 clean, 1 findings, 2 not available
    krt_check.py BASELINE RESULT [--json OUT] [--tolerance 0.1]  gate; exit 0 no new finding, 1 new findings
Options: --krt DIR (the plugin folder; default: $KRT_DIR, then the KiCad 3rdparty / scripting plugin folders),
         --kicad-python PATH, --max-list N (default 25).
Module API: find_krt(), check(board, ...) -> findings | None, new_findings(base, cur) -> list.
"""
import collections
import glob
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kicad_sexp as KS  # noqa: E402

CATS = ('dangling-end', 'soft-joint', 'redundant-cycle', 'removable-segment', 'stacked-copper', 'unsupported-via',
        'dangling-via', 'orphan-island', 'narrow-pad-joint', 'kicad-dangling')
_HEAD = re.compile(r'^\s{2}([a-z-]+): (\d+)\s*$')
_ITEM = re.compile(r'^\s{4}net (.+?) \(([^)]*)\) at \((-?[\d.]+), (-?[\d.]+)\): (.*)$')
_NUM = re.compile(r'-?\d+(?:\.\d+)?')


def _version(d):
    try:
        return tuple(int(x) for x in open(os.path.join(d, 'VERSION')).read().strip().split('.'))
    except (OSError, ValueError):
        return (0,)


def find_krt(explicit=None):
    """The KiCad Routing Tools folder holding py_router/check_weird.py (newest version wins), or None."""
    if explicit:
        return explicit if os.path.isfile(os.path.join(explicit, 'py_router', 'check_weird.py')) else None
    if os.environ.get('KRT_DIR'):
        return find_krt(os.environ['KRT_DIR'])
    home = os.path.expanduser('~')
    roots = [os.path.join(home, 'Documents', 'KiCad')] + glob.glob(os.path.join(home, 'OneDrive*', 'Documents', 'KiCad')) \
        + [os.path.join(home, '.local', 'share', 'kicad')]
    pats = []
    for r in roots:
        pats += [os.path.join(r, '*', '3rdparty', 'plugins', '*outingtools*'),
                 os.path.join(r, '*', 'scripting', 'plugins', 'KiCadRoutingTools*')]
    # KICADn_3RDPARTY_DIR set in KiCad's own settings (the PCM folder can live anywhere)
    for cfg in glob.glob(os.path.join(os.environ.get('APPDATA', ''), 'kicad', '*', 'kicad_common.json')) + \
            glob.glob(os.path.join(home, '.config', 'kicad', '*', 'kicad_common.json')) + \
            glob.glob(os.path.join(home, 'Library', 'Preferences', 'kicad', '*', 'kicad_common.json')):
        try:
            env = (json.load(open(cfg, encoding='utf-8')).get('environment') or {}).get('vars') or {}
        except (OSError, ValueError):
            continue
        for k, v in env.items():
            if k.endswith('3RDPARTY_DIR') and v:
                pats.append(os.path.join(v, 'plugins', '*outingtools*'))
    found = {d for p in pats for d in glob.glob(p) if os.path.isfile(os.path.join(d, 'py_router', 'check_weird.py'))}
    return max(found, key=_version) if found else None


PLANES = r'''
import sys, json, pcbnew
b = pcbnew.LoadBoard(sys.argv[1]); out = {}
for z in b.Zones():
    if z.GetIsRuleArea() or not z.GetNetname(): continue
    out.setdefault(z.GetNetname(), set()).update(b.GetLayerName(l) for l in z.GetLayerSet().Seq())
print(json.dumps({k: sorted(v) for k, v in out.items()}))
'''


def check(board, krt=None, kp=None, tolerance=0.1, raw_out=None):
    """Run check_weird on BOARD; return the findings (dicts) or None when the checker is not available."""
    krt = krt or find_krt()
    kp = KS.find_kicad_python(kp)
    if not (krt and kp):
        return None
    r = subprocess.run([kp, os.path.join(krt, 'py_router', 'check_weird.py'), os.path.abspath(board),
                        '--tolerance', str(tolerance), '--max-print', '0'], capture_output=True, text=True,
                       encoding='utf-8', errors='replace', cwd=krt)
    if raw_out:
        open(raw_out, 'w', encoding='utf-8').write(r.stdout + r.stderr)
    if 'Checking' not in r.stdout:
        raise RuntimeError('check_weird.py failed on %s: %s' % (board, (r.stderr or r.stdout).strip()[-400:]))
    p = subprocess.run([kp, '-c', PLANES, os.path.abspath(board)], capture_output=True, text=True)
    try:
        planes = json.loads(p.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        planes = {}
    found, cat = [], None
    for line in r.stdout.splitlines():
        h = _HEAD.match(line)
        if h:
            cat = h.group(1) if h.group(1) in CATS else None
            continue
        m = _ITEM.match(line)
        if not (m and cat):
            continue
        net, layer, x, y, msg = m.group(1), m.group(2), float(m.group(3)), float(m.group(4)), m.group(5)
        f = {'check': cat, 'net': net, 'layer': layer, 'x': x, 'y': y, 'msg': msg, 'filtered': False}
        if cat == 'dangling-via' and any(L.startswith('In') for L in planes.get(net, [])):
            f['filtered'] = True          # inner-layer pour of the via's own net: check_weird does not see it
        found.append(f)
    return found


def identity(f):
    return (f['check'], f['net'], f['layer'], _NUM.sub('#', f['msg']))


def counts(findings):
    return collections.Counter(identity(f) for f in findings if not f['filtered'])


def new_findings(base, cur):
    b = base if isinstance(base, collections.Counter) else counts(base)
    seen, out = collections.Counter(), []
    for f in cur:
        if f['filtered']:
            continue
        i = identity(f)
        seen[i] += 1
        if seen[i] > b.get(i, 0):
            out.append(f)
    return out


def _summary(fs):
    c = collections.Counter(f['check'] for f in fs if not f['filtered'])
    return ', '.join('%s %d' % (k, c[k]) for k in CATS if c[k]) or 'none'


def main(a):
    pos = [x for i, x in enumerate(a) if not x.startswith('--') and (i == 0 or not a[i - 1].startswith('--'))]
    if not pos:
        sys.stdout.write(__doc__)
        return 2
    opt = lambda n, d=None: a[a.index(n) + 1] if n in a else d
    krt = find_krt(opt('--krt'))
    if not krt:
        print('KiCad Routing Tools not found (install it from the KiCad PCM, or pass --krt DIR / set KRT_DIR)')
        return 2
    tol, top = float(opt('--tolerance', 0.1)), int(opt('--max-list', 25))
    print('KiCad Routing Tools %s at %s' % ('.'.join(map(str, _version(krt))), krt))
    runs = [check(p, krt, opt('--kicad-python'), tol) for p in pos[:2]]
    if any(r is None for r in runs):
        print("KiCad's Python not found; pass --kicad-python")
        return 2
    cur = runs[-1]
    nf = sum(f['filtered'] for f in cur)
    rep = {'board': pos[-1], 'krt': krt, 'findings': cur}
    if len(runs) == 1:
        live = [f for f in cur if not f['filtered']]
        print('%d finding(s): %s; %d plane-via false positive(s) filtered' % (len(live), _summary(cur), nf))
        for f in live[:top]:
            print('  [%s] %s (%s) @ %.3f,%.3f: %s' % (f['check'], f['net'], f['layer'], f['x'], f['y'], f['msg'][:120]))
        res = 1 if live else 0
    else:
        new = new_findings(runs[0], cur)
        rep['baseline'], rep['new'] = pos[0], new
        print('baseline: %s\nresult:   %s' % (_summary(runs[0]), _summary(cur)))
        for f in new[:top]:
            print('  NEW [%s] %s (%s) @ %.3f,%.3f: %s' % (f['check'], f['net'], f['layer'], f['x'], f['y'], f['msg'][:120]))
        print('result: %s' % ('BLOCKED - %d new finding(s)' % len(new) if new else 'PASS - no new finding'))
        res = 1 if new else 0
    if opt('--json'):
        json.dump(rep, open(opt('--json'), 'w', encoding='utf-8'), indent=1)
    return res


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
