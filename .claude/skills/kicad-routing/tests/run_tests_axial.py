#!/usr/bin/env python
"""run_tests_axial.py - self-test for the axial pad entries of route_finish.py (lessons L10 / L11, 1.23.0).

Runs on the system Python; drives KiCad's Python (KICAD_PYTHON, then the usual install paths) and node; skipped when
KiCad's Python is absent. Each case builds a 2-layer board from KiCad's library footprints, routes one connection
pad centre to pad centre with route_finish.py and audits it (kicad_audit.js section 7, pad-entry).

  offset 0603 pair     R1.2 -> R2.1, 4 mm right / 3 mm down: no non-axial entry, no bend closer than 0.5 mm to a pad
                       edge, both ends exactly on the pad centres; --no-axial on the same board enters diagonally
                       or ends off-centre (the 1.19 behaviour)
  90 deg 1206          R4 rotated 90 deg, elongated pads: the stub runs along the rotated long axis
  SOIC-8 pin           U1.1 -> R5.1: the pin is entered from its outer end, along the pin axis
  wide track, 0402     --width 0.8 into 0402 pads: each stub is no wider than the pad's smallest dimension, the rest of
                       the route keeps 0.8 mm
  off-lattice pad      R7 at 30 deg: exit 1, "no clear axial entry", nothing written
  shared stub          a pad with an axial entry and a 45 deg one: --refinish joins the second to the existing stub
  no acute turn        U2.1 -> R15.1 with the target behind the pin's outward stub: no acute joint (1.27.0); with
                       --allow-acute the 1.26 search turns back at 135 deg and the audit FAILs it
  refinish_gated.py    takes the pad-entry FAIL pads from the audit, re-routes each, keeps only DRC- and audit-better results
  --refinish           realigns the --no-axial pair (pad-to-pad chain re-routed whole) and the end of a longer route
                       (cut back to a vertex >= --refinish-length from the pad): pad-entry clean afterwards
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCR = os.path.normpath(os.path.join(HERE, '..', 'scripts'))
sys.path.insert(0, SCR)
import kicad_sexp as KS  # noqa: E402

PASS = FAIL = 0
TMP = tempfile.mkdtemp(prefix='kr_axial_')
KP = KS.find_kicad_python()

BUILD = r'''
import json, os, sys, pcbnew
out, spec = sys.argv[1], json.loads(sys.argv[2])
base = None
for b_ in (r"C:\Program Files\KiCad\10.0\share\kicad\footprints", "/usr/share/kicad/footprints",
           "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"):
    if os.path.isdir(os.path.join(b_, "Resistor_SMD.pretty")):
        base = b_
b = pcbnew.BOARD()
b.SetCopperLayerCount(2)
def mm(v): return pcbnew.FromMM(v)
for a, c in (((0, 0), (40, 0)), ((40, 0), (40, 30)), ((40, 30), (0, 30)), ((0, 30), (0, 0))):
    s = pcbnew.PCB_SHAPE(b); s.SetShape(pcbnew.SHAPE_T_SEGMENT); s.SetLayer(pcbnew.Edge_Cuts)
    s.SetStart(pcbnew.VECTOR2I(mm(a[0]), mm(a[1]))); s.SetEnd(pcbnew.VECTOR2I(mm(c[0]), mm(c[1]))); b.Add(s)
nets = {}
for ref, lib, name, x, y, rot, padnets in spec:
    fp = pcbnew.FootprintLoad(os.path.join(base, lib + ".pretty"), name)
    fp.SetReference(ref); b.Add(fp)
    fp.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y))); fp.SetOrientationDegrees(rot)
    for p in fp.Pads():
        n = padnets.get(p.GetNumber())
        if n:
            if n not in nets:
                nets[n] = pcbnew.NETINFO_ITEM(b, n); b.Add(nets[n])
            p.SetNet(nets[n])
b.Save(out)
'''


def ok(cond, name, extra=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print('  ok   ' + name)
    else:
        FAIL += 1
        print('  FAIL ' + name + (('\n       ' + str(extra)[-1800:]) if extra else ''))


def run(args):
    r = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', errors='replace',
                       env=dict(os.environ, MSYS_NO_PATHCONV='1'))
    return r.returncode, '\n'.join(l for l in (r.stdout + r.stderr).splitlines() if 'image handler' not in l)


def board(name, spec):
    d = os.path.join(TMP, name)
    os.makedirs(d)
    pcb = os.path.join(d, 'a.kicad_pcb')
    rc, out = run([KP, os.path.join(TMP, 'build.py'), pcb, json.dumps(spec)])
    if rc:
        raise SystemExit('board build failed: ' + out)
    open(os.path.join(d, 'a.kicad_pro'), 'w').write('{}\n')
    return pcb


def route(pcb, net, a, b, *extra):
    return run([KP, os.path.join(SCR, 'route_finish.py'), pcb, '--net', net, '--from-pad', a, '--to-pad', b,
                '--grid', '0.05', '--safety', '0.05'] + list(extra))


def entry_findings(pcb, refs):
    j = pcb + '.audit.json'
    run(['node', os.path.join(SCR, 'kicad_audit.js'), pcb, '--no-sch', '--quiet', '--json', j])
    a = json.load(open(j)) if os.path.isfile(j) else {'findings': []}
    return [f['msg'] for f in a['findings'] if f['check'] == 'pad-entry' and f['level'] == 'FAIL'
            and any(r + '-' in f['msg'] for r in refs)]


def acute_findings(pcb):
    j = pcb + '.audit.json'
    run(['node', os.path.join(SCR, 'kicad_audit.js'), pcb, '--no-sch', '--quiet', '--json', j])
    a = json.load(open(j, encoding='utf-8')) if os.path.isfile(j) else {'findings': []}
    return [f['msg'] for f in a['findings'] if f['check'] == 'acute']


def add_tracks(pcb, net, segs, w=0.2):
    code = ('import pcbnew, sys, json\nb = pcbnew.LoadBoard(sys.argv[1])\nn = b.FindNet(sys.argv[2])\n'
            'for x1, y1, x2, y2 in json.loads(sys.argv[3]):\n'
            '    t = pcbnew.PCB_TRACK(b); b.Add(t)\n'
            '    t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x1), pcbnew.FromMM(y1)))\n'
            '    t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x2), pcbnew.FromMM(y2)))\n'
            '    t.SetWidth(pcbnew.FromMM(%s)); t.SetLayer(pcbnew.F_Cu); t.SetNetCode(n.GetNetCode())\n'
            'b.Save(sys.argv[1])\n' % w)
    open(os.path.join(TMP, 'at.py'), 'w').write(code)
    rc, out = run([KP, os.path.join(TMP, 'at.py'), pcb, net, json.dumps(segs)])
    if rc:
        raise SystemExit(out)


def tracks(pcb):
    code = ('import pcbnew, sys\nb = pcbnew.LoadBoard(sys.argv[1])\n'
            'for t in b.GetTracks():\n'
            '    if t.Type() == pcbnew.PCB_TRACE_T:\n'
            '        print(round(pcbnew.ToMM(t.GetStart().x), 4), round(pcbnew.ToMM(t.GetStart().y), 4), '
            'round(pcbnew.ToMM(t.GetEnd().x), 4), round(pcbnew.ToMM(t.GetEnd().y), 4), round(pcbnew.ToMM(t.GetWidth()), 4))\n')
    open(os.path.join(TMP, 'tr.py'), 'w').write(code)
    rc, out = run([KP, os.path.join(TMP, 'tr.py'), pcb])
    return [tuple(float(v) for v in l.split()) for l in out.splitlines() if l and l[0] in '-0123456789']


R0603 = ('Resistor_SMD', 'R_0603_1608Metric')
R0402 = ('Resistor_SMD', 'R_0402_1005Metric')
R1206 = ('Resistor_SMD', 'R_1206_3216Metric')
SOIC = ('Package_SO', 'SOIC-8_3.9x4.9mm_P1.27mm')


def main():
    if not KP:
        print('KiCad Python not found - axial entry tests skipped')
        return 0
    open(os.path.join(TMP, 'build.py'), 'w').write(BUILD)
    print('route_finish.py axial entries')

    spec = [['R1', *R0603, 10, 10, 0, {'2': 'A'}], ['R2', *R0603, 14, 13, 0, {'1': 'A'}]]
    pcb = board('pair', spec)
    rc, out = route(pcb, 'A', 'R1.2', 'R2.1')
    f = entry_findings(pcb, ['R1', 'R2'])
    ok(rc == 0 and 'axial stub into R1.2' in out and 'axial stub into R2.1' in out, 'offset 0603 pair routed with two axial stubs', out)
    ok(not f, 'offset 0603 pair: no pad-entry FAIL (axis, bend >= 0.5 mm, exact centres)', f)
    pcb2 = board('pair_noaxial', spec)
    rc, out = route(pcb2, 'A', 'R1.2', 'R2.1', '--no-axial')
    f2 = entry_findings(pcb2, ['R1', 'R2'])
    ok(rc == 0 and f2, '--no-axial on the same board leaves pad-entry FAILs (the 1.19 behaviour)', f2 or out)
    rc, out = run([KP, os.path.join(SCR, 'route_finish.py'), pcb2, '--refinish', 'R2.1', '--grid', '0.05', '--safety', '0.05'])
    f3 = entry_findings(pcb2, ['R1', 'R2'])
    ok(rc == 0 and 're-routed pad to pad' in out and not f3, '--refinish R2.1 realigns that diagonal pad-to-pad route: audit clean',
       (f3, out))
    pcb3 = board('refin_mid', [['R10', *R0603, 10, 10, 0, {'2': 'F'}], ['R11', *R0603, 20, 16, 0, {'1': 'F'}]])
    add_tracks(pcb3, 'F', [(10.825, 10, 13.175, 10), (13.175, 10, 19.175, 16)])      # 45 deg into R11.1: non-axial
    f_pre = entry_findings(pcb3, ['R11'])
    rc, out = run([KP, os.path.join(SCR, 'route_finish.py'), pcb3, '--refinish', 'R11.1', '--grid', '0.05', '--safety', '0.05'])
    f4 = entry_findings(pcb3, ['R11'])
    ok(any('non-axial' in m for m in f_pre) and rc == 0 and 'taken out; re-route from (13.1750, 10.0000)' in out and not f4,
       '--refinish R11.1: a 45 deg entry is cut back to its vertex and re-enters the pad axially', (f_pre, f4, out))
    rc, out = run([KP, os.path.join(SCR, 'route_finish.py'), pcb3, '--refinish', 'R11.1'])
    ok(rc == 0 and 'already axial - nothing to do' in out, '--refinish on an axial entry does nothing', out)
    pcb4 = board('shared', [['R12', *R0603, 20, 10, 0, {'1': 'G'}]])
    add_tracks(pcb4, 'G', [(19.175, 10, 17.175, 10), (17.175, 10, 12, 10),          # axial stub + its route
                           (19.175, 10, 16.175, 13), (16.175, 13, 12, 13)])         # second entry at 45 deg
    rc, out = run([KP, os.path.join(SCR, 'route_finish.py'), pcb4, '--refinish', 'R12.1', '--grid', '0.05', '--safety', '0.05'])
    f5 = entry_findings(pcb4, ['R12'])
    ok(rc == 0 and '2 tracks end in the pad, 1 non-axial' in out and 'shares the existing stub ending at (17.1750, 10.0000)' in out
       and not f5, 'two entries: the 45 deg one is re-routed onto the existing axial stub (shared, not doubled)', (f5, out))

    pcb5 = board('gated', [['R20', *R0603, 8, 8, 0, {'2': 'H'}], ['R21', *R0603, 18, 14, 0, {'1': 'H'}],
                           ['R22', *R0603, 8, 22, 0, {'2': 'K'}], ['R23', *R0603, 18, 26, 0, {'1': 'K'}]])
    add_tracks(pcb5, 'H', [(8.825, 8, 11.175, 8), (11.175, 8, 17.175, 14)])
    add_tracks(pcb5, 'K', [(8.825, 22, 10.175, 22), (10.175, 22, 14.175, 26), (14.175, 26, 17.175, 26)])
    pre = entry_findings(pcb5, ['R21', 'R23'])
    rc, out = run([sys.executable, os.path.join(SCR, 'refinish_gated.py'), pcb5])
    post = entry_findings(pcb5, ['R21', 'R23'])
    ok(rc == 0 and pre and not post and re.search(r'end: [1-9]\d* kept', out) and os.path.isfile(pcb5 + '.bak_prerefinish'),
       'refinish_gated.py: pads taken from the audit, each kept only when DRC holds and the audit FAIL count falls', (pre, post, out))

    pcb = board('rot90', [['R3', *R1206, 10, 10, 0, {'2': 'B'}], ['R4', *R1206, 18, 17, 90, {'1': 'B'}]])
    rc, out = route(pcb, 'B', 'R3.2', 'R4.1')
    f = entry_findings(pcb, ['R3', 'R4'])
    ok(rc == 0 and 'axial stub into R4.1' in out and not f,
       '1206 rotated 90 deg (elongated pads): stubs along the rotated long axis, audit clean', f or out)

    pcb = board('soic', [['U1', *SOIC, 12, 12, 0, {'1': 'C'}], ['R5', *R0603, 24, 20, 0, {'1': 'C'}]])
    rc, out = route(pcb, 'C', 'U1.1', 'R5.1')
    f = entry_findings(pcb, ['U1', 'R5'])
    ok(rc == 0 and 'axial stub into U1.1 on F.Cu: dir (-1, 0)' in out and not f,
       'SOIC-8 pin 1 entered from its outer end along the pin axis', f or out)

    # 1.27.0: the target lies behind the pin's outward stub (pin 1 exits to the left, R15 is up and to the right).
    # The shortest path turns back at 135 deg (interior 45) at the stub end; the search must turn at 90 deg at most.
    spec = [['U2', *SOIC, 12, 15, 0, {'1': 'J'}], ['R15', *R0603, 22, 10, 0, {'1': 'J'}]]
    pcb = board('acute', spec)
    rc, out = route(pcb, 'J', 'U2.1', 'R15.1')
    ac = acute_findings(pcb)
    ok(rc == 0 and not ac, 'pin stub pointing away from the target: routed with no acute joint (1.27.0)', (ac, out))
    pcb = board('acute_allowed', spec)
    rc, out = route(pcb, 'J', 'U2.1', 'R15.1', '--allow-acute')
    ac = acute_findings(pcb)
    ok(rc == 0 and ac, '--allow-acute on the same board turns back at the stub end (the 1.26 search), the audit FAILs it',
       (ac, out))

    pcb = board('wide', [['R6', *R0402, 10, 10, 0, {'2': 'D'}], ['R8', *R0402, 16, 14, 0, {'1': 'D'}]])
    rc, out = route(pcb, 'D', 'R6.2', 'R8.1', '--width', '0.8')
    tr = tracks(pcb)
    f = entry_findings(pcb, ['R6', 'R8'])
    widths = sorted({t[4] for t in tr})
    ok(rc == 0 and len(widths) == 2 and widths[0] < 0.8 and widths[1] == 0.8 and not any('wider than' in m for m in f),
       'wide track into 0402: stubs %s mm, route 0.8 mm, no wide-entry FAIL' % widths[0] if widths else '', (tr, f, out))

    pcb = board('offlat', [['R7', *R0603, 10, 10, 30, {'2': 'E'}], ['R9', *R0603, 16, 14, 0, {'1': 'E'}]])
    before = open(pcb, 'rb').read()
    rc, out = route(pcb, 'E', 'R7.2', 'R9.1')
    ok(rc == 1 and 'no clear axial entry into R7.2' in out and open(pcb, 'rb').read() == before,
       'pad at 30 deg: exit 1, no clear axial entry, nothing written', out)

    print('\n%d passed, %d failed' % (PASS, FAIL))
    if not FAIL:
        shutil.rmtree(TMP, ignore_errors=True)
    else:
        print('kept ' + TMP)
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
