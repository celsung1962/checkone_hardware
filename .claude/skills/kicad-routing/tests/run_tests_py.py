#!/usr/bin/env python
"""run_tests_py.py - self-test for the skill's python helpers (rev J).

Dependency-free and pcbnew-free: covers the pure logic that decides how the router is driven,
which is exactly the logic that silently got the 4-layer test board wrong before rev J. The parts that need
pcbnew (route_report's ratsnest, route_freerouting's export) are exercised against real boards,
not here.

    python tests/run_tests_py.py        (exit 0 = all assertions passed)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'scripts'))
import kicad_sexp as K  # noqa: E402

PASS = FAIL = 0


def check(label, cond, detail=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print('PASS  %s%s' % (label, ('  - ' + str(detail)) if detail else ''))
    else:
        FAIL += 1
        print('FAIL  %s  - %s' % (label, detail))


# ---------------------------------------------------------------- fixtures
def fp(ref, clearance=None, extra=''):
    c = '\n\t\t(clearance %s)' % clearance if clearance is not None else ''
    return ('\t(footprint "Lib:Part" (layer "F.Cu") (uuid "u-%s") (at 10 10)\n'
            '\t\t(property "Reference" "%s" (at 0 0 0) (layer "F.SilkS"))\n'
            '\t\t(property "Value" "X" (at 0 0 0) (layer "F.Fab"))%s%s\n'
            '\t\t(pad "1" smd roundrect (at 0 0) (size 0.8 0.95) (layers "F.Cu") (net 1 "N1"))\n'
            '\t)\n' % (ref, ref, c, extra))


HEADER = '(kicad_pcb\n\t(version 20260206)\n\t(generator "pcbnew")\n'
FOOTER = ')\n'

# a pad-level clearance must NOT be mistaken for a footprint-level override
PAD_LEVEL = ('\t(footprint "Lib:Part" (layer "F.Cu") (uuid "u-PZ") (at 5 5)\n'
             '\t\t(property "Reference" "PZ" (at 0 0 0) (layer "F.SilkS"))\n'
             '\t\t(pad "1" smd roundrect (at 0 0) (size 0.8 0.95) (layers "F.Cu")\n'
             '\t\t\t(clearance 0.9)\n'
             '\t\t\t(net 1 "N1"))\n'
             '\t)\n')

none_board = HEADER + fp('R1') + fp('R2') + FOOTER
one_board = HEADER + fp('R1') + fp('U6', '0.15') + fp('R2') + FOOTER
many_board = HEADER + fp('U6', '0.15') + fp('U9', '0.25') + fp('R1', '0.05') + FOOTER
pad_board = HEADER + fp('R1') + PAD_LEVEL + FOOTER

# ---------------------------------------------------------------- footprint_local_clearances
got = K.footprint_local_clearances(none_board)
check('no override -> empty list', got == [], got)

got = K.footprint_local_clearances(one_board)
check('single override found with its reference', got == [('U6', 0.15)], got)

got = sorted(K.footprint_local_clearances(many_board))
check('all overrides found', got == [('R1', 0.05), ('U6', 0.15), ('U9', 0.25)], got)

# This is the one that matters: a (clearance ...) inside a PAD is not a footprint override.
# Treating it as one would raise the export clearance to 0.9 mm and cripple routing.
got = K.footprint_local_clearances(pad_board)
check('pad-level clearance is NOT read as a footprint override', got == [], got)

# ---------------------------------------------------------------- clearance_floor
check('floor of a board with no overrides is 0', K.clearance_floor(none_board) == 0.0)
check('floor is the LARGEST override', K.clearance_floor(many_board) == 0.25,
      K.clearance_floor(many_board))
check('floor ignores pad-level clearance', K.clearance_floor(pad_board) == 0.0,
      K.clearance_floor(pad_board))

# ---------------------------------------------------------------- sweep_candidates
c = K.sweep_candidates(0.15)
check('candidates start AT the floor, never below', c[0] == 0.15 and min(c) == 0.15, c)
check('candidates step upward', c == [0.15, 0.20, 0.25], c)
c0 = K.sweep_candidates(0.0)
check('no floor -> conventional 0.10 start', c0 == [0.10, 0.15, 0.20], c0)
check('floor is respected for an unusual override', K.sweep_candidates(0.3)[0] == 0.3,
      K.sweep_candidates(0.3))

# ---------------------------------------------------------------- padstack validity rule
# A via whose drill is at least its own diameter is the signature of a corrupted SES import
# (observed on the 4-layer test board: 0.25 mm diameter against a 0.30 mm drill).
def padstack_ok(diameter_mm, drill_mm):
    return drill_mm < diameter_mm


check('valid padstack accepted', padstack_ok(0.25, 0.15))
check('drill equal to diameter rejected', not padstack_ok(0.25, 0.25))
check('drill larger than diameter rejected (the 4-layer test board corruption)', not padstack_ok(0.25, 0.30))

# ---------------------------------------------------------------- file round-trip
import tempfile  # noqa: E402
tmp = tempfile.mkdtemp(prefix='kr_py_')   # outside tests/: the suite leaves a checkout unchanged
path = os.path.join(tmp, 'local_clearance.kicad_pcb')
with open(path, 'w') as f:
    f.write(many_board)
check('helper accepts a PATH as well as board text',
      K.clearance_floor(path) == 0.25, K.clearance_floor(path))

# ---------------------------------------------------------------- auto-clearance must OUTLIVE the save
# pcbnew caches the project settings it read at LoadBoard time. SaveBoard rewrites the .kicad_pro
# from that cache, so restoring the netclass clearance BEFORE the save is undone by the save while
# still logging "restored". Measured: a 3-candidate sweep left the board netclasses at the last
# candidate export clearance (0.100 -> 0.250 mm), which silently inflates every later DRC and
# feeds the next run clearance floor. The restore must be re-asserted AFTER SaveBoard.
import ast
import io as _io

_src = _io.open(os.path.join(HERE, '..', 'scripts', 'route_freerouting.py'), encoding='utf-8').read()
_tree = ast.parse(_src)

_saves, _restores = [], []
for _n in ast.walk(_tree):
    if isinstance(_n, ast.Call):
        _f = _n.func
        if isinstance(_f, ast.Attribute) and _f.attr == 'SaveBoard':
            _saves.append(_n.lineno)
        if isinstance(_f, ast.Name) and _f.id == 'restore_clearance':
            _restores.append(_n.lineno)

check('the board save is found', bool(_saves), _saves)
check('a clearance restore runs AFTER the board save',
      bool(_saves) and any(r > max(_saves) for r in _restores),
      'saves at %s, restores at %s - a restore before the save is undone by it' % (_saves, _restores))
check('the pre-export restore is still there too (the DSN must not see the raised value)',
      bool(_saves) and any(r < min(_saves) for r in _restores), _restores)

# ---------------------------------------------------------------- route_finish lattice gate
# route_finish.py must refuse to write off-lattice geometry. The check exists because two real bugs
# produced skewed segments during development (endpoint snapping, and a zero-length step at a via
# that made the collinearity test swallow a whole run). A check that runs AFTER the board is
# modified would be decorative, so assert it comes first.
_rf = os.path.join(HERE, '..', 'scripts', 'route_finish.py')
check('route_finish.py is shipped', os.path.isfile(_rf), _rf)
if os.path.isfile(_rf):
    _t2 = ast.parse(_io.open(_rf, encoding='utf-8').read())
    _die3, _adds, _saves2 = [], [], []
    for _n in ast.walk(_t2):
        if isinstance(_n, ast.Call) and isinstance(_n.func, ast.Name) and _n.func.id == 'die':
            for _a in _n.args:
                if isinstance(_a, ast.Constant) and _a.value == 3:
                    _die3.append(_n.lineno)
        if isinstance(_n, ast.Call) and isinstance(_n.func, ast.Attribute):
            if _n.func.attr == 'Add':
                _adds.append(_n.lineno)
            if _n.func.attr == 'Save':
                _saves2.append(_n.lineno)
    check('an off-lattice result exits 3', bool(_die3), _die3)
    check('the lattice check runs BEFORE anything is added to the board',
          bool(_die3) and bool(_adds) and min(_die3) < min(_adds),
          'die(3) at %s, first board mutation at %s' % (_die3, _adds))
    check('the lattice check runs BEFORE the board is saved',
          bool(_die3) and bool(_saves2) and min(_die3) < min(_saves2),
          'die(3) at %s, Save at %s' % (_die3, _saves2))

# ---------------------------------------------------------------- 1.18.0: collect() geometry + stitch_planes obstacles
# Found routing the ServiceOne board (2026-10-04): an outline drawn as gr_poly + gr_circle cut-outs gave the stitcher
# NO board edge; footprint rule areas were not read (a via landed in a push-button keepout); pads were modelled by
# half their larger side, so a rectangle's corners stuck out (a stub shorted a side-LED pad); custom pads used
# their small anchor size.
import io, shutil, subprocess, tempfile  # noqa: E402


def fp10(ref, x, y, pads, extra=''):
    return ('\t(footprint "Lib:%s"\n\t\t(layer "F.Cu")\n\t\t(uuid "u-%s")\n\t\t(at %s %s)\n'
            '\t\t(property "Reference" "%s"\n\t\t\t(at 0 0 0)\n\t\t\t(layer "F.SilkS")\n\t\t)\n%s%s\t)\n'
            % (ref, ref, x, y, ref, pads, extra))


def pad10(num, x, y, w, h, net, shape='roundrect', extra=''):
    return ('\t\t(pad "%s" smd %s\n\t\t\t(at %s %s)\n\t\t\t(size %s %s)\n\t\t\t(layers "F.Cu" "F.Paste" "F.Mask")\n'
            '\t\t\t(net "%s")%s\n\t\t)\n' % (num, shape, x, y, w, h, net, extra))


KEEPOUT_FP = ('\t\t(zone\n\t\t\t(net "")\n\t\t\t(layer "F.Cu")\n\t\t\t(uuid "z-ko")\n\t\t\t(name "KO_SW")\n'
              '\t\t\t(hatch edge 0.5)\n\t\t\t(keepout\n\t\t\t\t(tracks not_allowed)\n\t\t\t\t(vias not_allowed)\n'
              '\t\t\t\t(pads allowed)\n\t\t\t\t(copperpour allowed)\n\t\t\t\t(footprints allowed)\n\t\t\t)\n'
              '\t\t\t(polygon\n\t\t\t\t(pts\n\t\t\t\t\t(xy 10.35 5) (xy 16 5) (xy 16 15) (xy 10.35 15)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n')
CUSTOM_PAD = ('\t\t(pad "3" smd custom\n\t\t\t(at 0 0)\n\t\t\t(size 0.4 0.4)\n\t\t\t(layers "F.Cu")\n\t\t\t(net "SIG")\n'
              '\t\t\t(primitives\n\t\t\t\t(gr_poly\n\t\t\t\t\t(pts (xy -0.2 -0.3) (xy 1.2 -0.3) (xy 1.2 0.3) (xy -0.2 0.3))\n'
              '\t\t\t\t\t(width 0)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n')
PLANE = ('\t(zone\n\t\t(net "GND")\n\t\t(layer "In1.Cu")\n\t\t(uuid "z-gnd")\n\t\t(hatch edge 0.5)\n'
         '\t\t(polygon\n\t\t\t(pts\n\t\t\t\t(xy 0.5 0.5) (xy 19.5 0.5) (xy 19.5 19.5) (xy 0.5 19.5)\n\t\t\t)\n\t\t)\n\t)\n')
EDGE_POLY = ('\t(gr_poly\n\t\t(pts\n\t\t\t(xy 0 0) (xy 20 0) (xy 20 20) (xy 0 20)\n\t\t)\n\t\t(stroke\n\t\t\t(width 0.05)\n'
             '\t\t\t(type solid)\n\t\t)\n\t\t(fill no)\n\t\t(layer "Edge.Cuts")\n\t\t(uuid "e-1")\n\t)\n')
EDGE_CIRCLE = ('\t(gr_circle\n\t\t(center 16 16)\n\t\t(end 17.5 16)\n\t\t(stroke\n\t\t\t(width 0.05)\n\t\t\t(type solid)\n'
               '\t\t)\n\t\t(fill no)\n\t\t(layer "Edge.Cuts")\n\t\t(uuid "e-2")\n\t)\n')
STITCH_BOARD = (HEADER + '\t(layers\n\t\t(0 "F.Cu" signal)\n\t\t(4 "In1.Cu" power)\n\t\t(2 "B.Cu" signal)\n\t)\n'
                + fp10('SW1', 10, 10, pad10('1', 0, 0, 0.6, 0.6, 'GND'), KEEPOUT_FP)
                + fp10('C1', 19.0, 1.0, pad10('2', 0, 0, 0.6, 0.6, 'GND'))
                + fp10('D1', 4, 16, pad10('1', 0, 0, 2.0, 1.0, 'SIG') + CUSTOM_PAD)
                + EDGE_POLY + EDGE_CIRCLE + PLANE + FOOTER)
_td = tempfile.mkdtemp(prefix='kr_stitch_')
_sb = os.path.join(_td, 'stitch.kicad_pcb')
io.open(_sb, 'w', encoding='utf-8', newline='\n').write(STITCH_BOARD)
_B = K.collect(_sb)
check('collect reads an Edge.Cuts gr_poly outline and a gr_circle cut-out (were invisible)',
      len(_B['edges']) >= 4 + 40 and any(abs(e[0] - 17.5) < 1e-6 for e in _B['edges']), len(_B['edges']))
_ra = _B.get('rule_areas', [])
check('collect reads a footprint-internal rule area with its flags, layer and polygon',
      len(_ra) == 1 and _ra[0]['tracks'] and _ra[0]['vias'] and _ra[0]['layers'] == ['F.Cu'] and len(_ra[0]['poly']) == 4, _ra)
_d1 = {p['pad']: p['r'] for p in _B['pads'] if p['ref'] == 'D1'}
check('a rectangular pad is modelled by half its diagonal (2 x 1 -> 1.118), not half its larger side',
      abs(_d1.get('1', 0) - 1.1180) < 1e-3, _d1)
check('a custom pad is modelled by its primitives, not its 0.4 mm anchor', _d1.get('3', 0) >= 1.2, _d1)
# board review rev. 0.2: board_guard refuses a board without its .kicad_pro beside it; an empty project keeps the
# rules_from_project defaults. --no-fill: this is the text-writer path, no KiCad Python needed.
io.open(os.path.join(_td, 'stitch.kicad_pro'), 'w', encoding='utf-8').write('{}\n')
_r = subprocess.run([sys.executable, os.path.join(HERE, '..', 'scripts', 'stitch_planes.py'), _sb, '--nets', 'GND', '--no-fill'],
                    capture_output=True, text=True)
_A = K.collect(_sb)
_new = [v for v in _A['vias'] if v['net'] == 'GND']
_sw = [v for v in _new if abs(v['y'] - 10) < 2.5 and abs(v['x'] - 10) < 2.5]
check('stitch_planes keeps the via of SW1-1 out of the footprint keepout beside it (via left of x 10.35)',
      len(_sw) == 1 and _sw[0]['x'] + _sw[0]['r'] <= 10.35 + 1e-6, (_sw, _r.stdout[-300:]))
_c1 = [v for v in _new if v['x'] > 15 and v['y'] < 5]
check('stitch_planes keeps the via of C1-2 0.5 mm inside a gr_poly outline corner (no edge was seen before)',
      len(_c1) == 1 and _c1[0]['x'] + _c1[0]['r'] <= 19.5 + 1e-6 and _c1[0]['y'] - _c1[0]['r'] >= 0.5 - 1e-6, _c1)
shutil.rmtree(_td, ignore_errors=True)

# ---------------------------------------------------------------- 1.27.0: audit_gate.py (new-FAIL gate)
import audit_gate as G  # noqa: E402
import json  # noqa: E402
import tempfile  # noqa: E402

_f = lambda chk, msg, lvl='FAIL': {'level': lvl, 'check': chk, 'msg': msg}
_bp = 'GND runs between pads R111-2 / U203-6 off-centre: 0.575 mm vs 0.4 mm clearance @ -27.45,-18.905 (F.Cu)'
_bp_moved = 'GND runs between pads R111-2 / U203-6 off-centre: 0.3 mm vs 0.2 mm clearance @ -27.1,-18.0 (F.Cu)'
check('audit_gate: a FAIL whose copper only moved keeps its identity (numbers blanked)',
      G.identity(_f('between-pads', _bp)) == G.identity(_f('between-pads', _bp_moved)), G.identity(_f('between-pads', _bp)))
check('audit_gate: references, net names and layers keep their digits (R111-2, +3.3VA, -3.3VA, In1.Cu)',
      G.identity(_f('via', 'via +3.3VA @ 1,2 near R111-2 on In1.Cu'))[1] == 'via +3.3VA @ #,# near R111-2 on In1.Cu' and
      G.identity(_f('via', 'via -3.3VA @ 1,2'))[1] != G.identity(_f('via', 'via +3.3VA @ 1,2'))[1] and
      G.identity(_f('via', 'via +24V_SW @ 1,2'))[1] != G.identity(_f('via', 'via +3.3V @ 1,2'))[1],
      [G.identity(_f('via', m))[1] for m in ('via +3.3VA @ 1,2 near R111-2 on In1.Cu', 'via -3.3VA @ 1,2', 'via +24V_SW @ 1,2')])
_base = [_f('between-pads', _bp), _f('via', 'via inside SMD pad C23-2 (/ADC_AIN3N) @ -32.7,-6.25'), _f('width', 'w', 'WARN')]
_cur = [_f('between-pads', _bp_moved), _f('via', 'via inside SMD pad C23-2 (/ADC_AIN3N) @ -32.7,-6.25'),
        _f('via', 'via inside SMD pad C105-1 (-3.3VA) @ -11.85,-15.9'), _f('acute', 'acute joint on GND @ 1,2 (F.Cu): 45° between two branches')]
_new = G.new_fails(_base, _cur)
check('audit_gate: a new via-in-pad and a new acute joint are new; the moved between-pads FAIL is not',
      sorted(x['check'] for x in _new) == ['acute', 'via'] and 'C105-1' in [x for x in _new if x['check'] == 'via'][0]['msg'], _new)
check('audit_gate: a lower total does not excuse a new FAIL (3 old removed, 1 new added -> blocked)',
      len(G.new_fails([_f('pad-entry', 'p %d' % i) for i in range(3)] + [_f('loop', 'x')], [_f('loop', 'x'), _f('via', 'via inside SMD pad C1-1 @ 0,0')])) == 1)
check('audit_gate: identities are counted (two vias-in-pad of one identity where the baseline had one -> one new)',
      len(G.new_fails([_f('via', 'via inside SMD pad C1-1 @ 0,0')], [_f('via', 'via inside SMD pad C1-1 @ 0,0'), _f('via', 'via inside SMD pad C1-1 @ 0.1,0')])) == 1)
_td = tempfile.mkdtemp()
_jb, _jc = os.path.join(_td, 'b.json'), os.path.join(_td, 'c.json')
json.dump({'findings': _base}, io.open(_jb, 'w', encoding='utf-8'))
json.dump({'findings': _cur}, io.open(_jc, 'w', encoding='utf-8'))
_gs = os.path.join(HERE, '..', 'scripts', 'audit_gate.py')
_r1 = subprocess.run([sys.executable, _gs, _jb, _jc, '--quiet'], capture_output=True, text=True)
_r0 = subprocess.run([sys.executable, _gs, _jb, _jb], capture_output=True, text=True)
check('audit_gate CLI: exit 1 and BLOCKED on new FAILs, exit 0 and PASS on none',
      _r1.returncode == 1 and 'BLOCKED' in _r1.stdout and '2 new' in _r1.stdout and _r0.returncode == 0 and 'PASS' in _r0.stdout,
      (_r1.returncode, _r1.stdout[-200:], _r0.returncode))
shutil.rmtree(_td, ignore_errors=True)

print('\n%d/%d assertions passed' % (PASS, PASS + FAIL))
sys.exit(1 if FAIL else 0)
