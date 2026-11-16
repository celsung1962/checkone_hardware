#!/usr/bin/env python
"""run_tests_models.py - self-test for model_builder.py (L26) and mounting_hole_fp.py (L24), 1.25.0.

model_builder.py runs on any Python; the rest drives KiCad's Python, node and kicad-cli and is skipped without them.

  model_builder spec        2 boxes -> STEP with 2 solids and a VRML with 2 shapes, named *_approx; a zero-extent box
                            is refused
  model_builder footprint   SOIC-8 from KiCad's library: body over F.Fab to 1.75 mm + 8 leads = 9 solids; --assign
                            adds one (model ...) block, a second run replaces it (still one)
  approx model on a board   the footprint with the ${KIPRJMOD} model on a board: audit section 28 lists it as *_approx
                            (INFO), no missing-model FAIL; kicad-cli pcb render writes a PNG
  mounting_hole_fp          M2 hole 2.3 mm, contacts 4.2 / 5.0 mm -> MountingHole_2.3mm_KO3.0: NPTH, rule area
                            KO_MECH (tracks, vias, pours not allowed) on F.Cu and B.Cu, r >= 3.0 mm; --plated gives a
                            PTH pad
  keep-out enforced         on a board: a foreign track 2 mm from the hole -> KiCad DRC items_not_allowed; at 3.5 mm
                            none; audit section 27 counts the hole as covered (no "no mechanical_keepouts entry" INFO);
                            the Specctra DSN carries the keep-out
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
TMP = tempfile.mkdtemp(prefix='kr_models_')
KP = KS.find_kicad_python()
CLI = KS.find_kicad_cli()
FPLIB = next((p for p in (r'C:\Program Files\KiCad\10.0\share\kicad\footprints', '/usr/share/kicad/footprints',
                          '/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints') if os.path.isdir(p)), None)


def ok(cond, name, extra=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print('  ok   ' + name)
    else:
        FAIL += 1
        print('  FAIL ' + name + (('\n       ' + str(extra)[-1500:]) if extra else ''))


def run(args):
    r = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', errors='replace')
    return r.returncode, '\n'.join(l for l in (r.stdout + r.stderr).splitlines()
                                   if 'image handler' not in l and 'memory leak' not in l)


BOARD = r'''
import os, sys, pcbnew
out, lib, name, mode = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
b = pcbnew.BOARD(); b.SetCopperLayerCount(2)
def mm(v): return pcbnew.FromMM(v)
def V(x, y): return pcbnew.VECTOR2I(mm(x), mm(y))
for a, c in (((0, 0), (40, 0)), ((40, 0), (40, 30)), ((40, 30), (0, 30)), ((0, 30), (0, 0))):
    s = pcbnew.PCB_SHAPE(b); s.SetShape(pcbnew.SHAPE_T_SEGMENT); s.SetLayer(pcbnew.Edge_Cuts)
    s.SetStart(V(*a)); s.SetEnd(V(*c)); b.Add(s)
fp = pcbnew.FootprintLoad(lib, name); b.Add(fp); fp.SetPosition(V(20, 15))
fp.SetReference("H1" if mode != "model" else "U1")
if mode != "model":
    n = pcbnew.NETINFO_ITEM(b, "SIG"); b.Add(n)
    y = 15 + float(mode)
    t = pcbnew.PCB_TRACK(b); b.Add(t); t.SetStart(V(5, y)); t.SetEnd(V(35, y)); t.SetWidth(mm(0.2))
    t.SetLayer(pcbnew.F_Cu); t.SetNetCode(n.GetNetCode())
b.Save(out)
'''


def main():
    print('model_builder.py')
    mb = os.path.join(SCR, 'model_builder.py')
    spec = os.path.join(TMP, 'spec.json')
    json.dump({'name': 'SW_TEST', 'note': 'datasheet fig. 2', 'boxes': [
        {'name': 'housing', 'color': [0.1, 0.1, 0.1], 'x': [-4.7, 4.7], 'y': [-14.7, -1.7], 'z': [0, 17]},
        {'name': 'pin1', 'x': [-0.38, 0.38], 'y': [-0.2, 0.2], 'z': [-3.2, 2]}]}, open(spec, 'w'))
    out = os.path.join(TMP, 'm.3dshapes')
    rc, o = run([sys.executable, mb, 'spec', spec, '--out', out])
    st = os.path.join(out, 'SW_TEST_approx.step')
    txt = open(st).read() if os.path.isfile(st) else ''
    wrl = open(os.path.join(out, 'SW_TEST_approx.wrl')).read() if os.path.isfile(os.path.join(out, 'SW_TEST_approx.wrl')) else ''
    ok(rc == 0 and txt.count('MANIFOLD_SOLID_BREP') == 2 and txt.startswith('ISO-10303-21;') and wrl.count('Shape {') == 2,
       'spec: 2 boxes -> SW_TEST_approx.step (2 solids) and .wrl (2 shapes)', o)
    json.dump({'name': 'BAD', 'boxes': [{'x': [0, 1], 'y': [0, 0], 'z': [0, 1]}]}, open(spec, 'w'))
    rc, o = run([sys.executable, mb, 'spec', spec, '--out', out])
    ok(rc != 0 and 'zero y extent' in o, 'spec: a zero-extent box is refused', o)
    if not FPLIB:
        print('  skip KiCad footprint library not found')
    else:
        lib = os.path.join(TMP, 'P.pretty')
        os.makedirs(lib)
        src = open(os.path.join(FPLIB, 'Package_SO.pretty', 'SOIC-8_3.9x4.9mm_P1.27mm.kicad_mod'), encoding='utf-8').read()
        src = re.sub(r'\n\s*\(model .*?\n\t\)', '', src, flags=re.S)          # no model: the part needs one
        fpf = os.path.join(lib, 'SOIC-8_3.9x4.9mm_P1.27mm.kicad_mod')
        open(fpf, 'w', encoding='utf-8', newline='\n').write(src)
        rc, o = run([sys.executable, mb, 'footprint', fpf, '--height', '1.75', '--out', out, '--assign'])
        st = os.path.join(out, 'SOIC-8_3.9x4.9mm_P1.27mm_approx.step')
        txt = open(st).read() if os.path.isfile(st) else ''
        f1 = open(fpf, encoding='utf-8').read()
        ok(rc == 0 and txt.count('MANIFOLD_SOLID_BREP') == 9 and 'z 0.00 .. 1.75 mm' in o, 'footprint: SOIC-8 body + 8 leads = 9 solids, 0 to 1.75 mm', o)
        ok(f1.count('(model ') == 1 and '${KIPRJMOD}/m.3dshapes/SOIC-8_3.9x4.9mm_P1.27mm_approx.step' in f1, '--assign adds one model block (project-relative path)', o)
        rc, o = run([sys.executable, mb, 'footprint', fpf, '--height', '1.75', '--out', out, '--assign'])
        ok(rc == 0 and 'replaced' in o and open(fpf, encoding='utf-8').read().count('(model ') == 1, 'a second --assign replaces it (still one block)', o)
        if KP:
            open(os.path.join(TMP, 'board.py'), 'w').write(BOARD)
            pcb = os.path.join(TMP, 'model.kicad_pcb')
            rc, o = run([KP, os.path.join(TMP, 'board.py'), pcb, lib, 'SOIC-8_3.9x4.9mm_P1.27mm', 'model'])
            j = pcb + '.audit.json'
            run(['node', os.path.join(SCR, 'kicad_audit.js'), pcb, '--no-sch', '--quiet', '--json', j])
            a = json.load(open(j)) if os.path.isfile(j) else {'findings': []}
            mf = [f for f in a['findings'] if f['check'] == 'model']
            ok(any(f['level'] == 'INFO' and '_approx' in f['msg'] for f in mf) and not any(f['level'] == 'FAIL' for f in mf),
               'on a board: audit 28 lists the *_approx model (INFO), no missing-model FAIL', mf)
            if CLI:
                png = os.path.join(TMP, 'r.png')
                rc, o = run([CLI, 'pcb', 'render', '--output', png, '--width', '400', '--height', '300', pcb])
                ok(rc == 0 and os.path.isfile(png) and os.path.getsize(png) > 1000, 'kicad-cli pcb render draws the board with the model', o)

    print('mounting_hole_fp.py')
    if not KP:
        print('  skip KiCad Python not found')
    else:
        lib = os.path.join(TMP, 'H.pretty')
        rc, o = run([KP, os.path.join(SCR, 'mounting_hole_fp.py'), '--lib', lib, '--hole', '2.3', '--contact-top', '4.2',
                     '--contact-bottom', '5.0', '--note', 'AK-H-79 post d 5.00'])
        fpf = os.path.join(lib, 'MountingHole_2.3mm_KO3.0.kicad_mod')
        t = open(fpf, encoding='utf-8').read() if os.path.isfile(fpf) else ''
        ok(rc == 0 and 'np_thru_hole' in t and '(name "KO_MECH")' in t and '(tracks not_allowed)' in t and
           '(vias not_allowed)' in t and '(copperpour not_allowed)' in t and '"F.Cu" "B.Cu"' in t and 'exclude_from_bom' in t,
           'M2 2.3 mm, contacts 4.2 / 5.0 -> KO3.0: NPTH + KO_MECH (tracks, vias, pours) on F.Cu and B.Cu', o + t[:300])
        pts = [tuple(map(float, m)) for m in re.findall(r'\(xy ([-\d.]+) ([-\d.]+)\)', t)]
        ok(pts and min((x * x + y * y) ** 0.5 for x, y in pts) >= 3.0 - 1e-3, 'the keep-out polygon is never inside r 3.0 mm', pts[:4])
        rc, o = run([KP, os.path.join(SCR, 'mounting_hole_fp.py'), '--lib', lib, '--hole', '3.2', '--contact-top', '7',
                     '--plated', '0.6', '--name', 'MH_M3_PTH'])
        t2 = open(os.path.join(lib, 'MH_M3_PTH.kicad_mod'), encoding='utf-8').read() if rc == 0 else ''
        ok('(pad "1" thru_hole circle' in t2 and 'keep-out r 4 mm' in o, '--plated: PTH pad, keep-out r 4.0 (washer d 7)', o)
        open(os.path.join(TMP, 'board.py'), 'w').write(BOARD)
        res = {}
        for off in ('2', '3.5'):
            pcb = os.path.join(TMP, 'h%s.kicad_pcb' % off)
            run([KP, os.path.join(TMP, 'board.py'), pcb, lib, 'MountingHole_2.3mm_KO3.0', off])
            if CLI:
                dj = pcb + '.drc.json'
                run([CLI, 'pcb', 'drc', '--format', 'json', '-o', dj, pcb])
                v = json.load(open(dj))['violations'] if os.path.isfile(dj) else []
                res[off] = sum(1 for x in v if x['type'] == 'items_not_allowed')
        if CLI:
            ok(res.get('2', 0) >= 1 and res.get('3.5', 1) == 0, 'KiCad DRC: a track 2 mm from the hole violates the keep-out, at 3.5 mm none', res)
        pcb = os.path.join(TMP, 'h2.kicad_pcb')
        j = pcb + '.audit.json'
        run(['node', os.path.join(SCR, 'kicad_audit.js'), pcb, '--no-sch', '--quiet', '--json', j])
        a = json.load(open(j)) if os.path.isfile(j) else {'findings': [], 'stats': {}}
        mk = [f['msg'] for f in a['findings'] if f['check'] == 'mech-keepout']
        ok(any('carry their own keep-out' in m for m in mk) and not any('no mechanical_keepouts entry' in m for m in mk),
           'audit 27 counts the hole as covered by its own keep-out', mk)
        dsn = os.path.join(TMP, 'h.dsn')
        open(os.path.join(TMP, 'dsn.py'), 'w').write('import pcbnew, sys\nprint(pcbnew.ExportSpecctraDSN(pcbnew.LoadBoard(sys.argv[1]), sys.argv[2]))\n')
        run([KP, os.path.join(TMP, 'dsn.py'), pcb, dsn])
        d = open(dsn, encoding='utf-8', errors='replace').read() if os.path.isfile(dsn) else ''
        ok('keepout' in d, 'the Specctra DSN carries the footprint keep-out', d[:200])

    print('\n%d passed, %d failed' % (PASS, FAIL))
    if not FAIL:
        shutil.rmtree(TMP, ignore_errors=True)
    else:
        print('kept ' + TMP)
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
