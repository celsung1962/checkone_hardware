#!/usr/bin/env python
"""run_tests_padrow.py - self-test for pad_row_keepouts.py (lesson L16, 1.22.0).

Runs on the system Python; drives KiCad's Python (KICAD_PYTHON, then the usual install paths), node and kicad-cli;
skipped when KiCad's Python is absent. The board is built here: three SOIC-8 from KiCad's library (U1 at 0 deg, U2 at
90 deg, U3 flipped to B.Cu at 30 deg) and U9, a 6-pin part with an exposed pad split into three pads all numbered 7
(not a row). Per SOIC: one via between pins 1/2 on the pad centre line (in), one whose copper crosses the band's outer
edge (in), one whose copper stops just beyond it (out), one under the body (out). Positions come from the pads, so the
expected answer does not depend on the script's frame transform.

  --list          6 bands on U1-U3, 2 on U9 (the exposed-pad grid is not a row); the 6 "in" vias and no other
  kicad_audit.js  section 26 agrees: same band count and the same vias
  --write         6+2 KO_ROW_* rule areas, vias forbidden on all copper layers, tracks allowed; a second run edits them
                  in place; kicad-cli DRC reports exactly the "in" vias as items_not_allowed
  export_keepouts.py --pad-row-bands   KO_EXPORT_ROW_* areas; the Specctra DSN carries them as via_keepout
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCR = os.path.normpath(os.path.join(HERE, '..', 'scripts'))
sys.path.insert(0, SCR)
import kicad_sexp as KS  # noqa: E402

PASS = FAIL = 0
TMP = tempfile.mkdtemp(prefix='kr_padrow_')
KP = KS.find_kicad_python()
CLI = next((p for p in (os.environ.get('KICAD_CLI', ''), r'C:\Program Files\KiCad\10.0\bin\kicad-cli.exe',
                        '/usr/bin/kicad-cli', '/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli')
            if p and os.path.isfile(p)), None)

BUILD = r'''
import math, sys, pcbnew
out = sys.argv[1]
lib = None
for base in (r"C:\Program Files\KiCad\10.0\share\kicad\footprints", "/usr/share/kicad/footprints",
             "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"):
    import os
    if os.path.isdir(os.path.join(base, "Package_SO.pretty")):
        lib = os.path.join(base, "Package_SO.pretty")
b = pcbnew.BOARD()
b.SetCopperLayerCount(2)
gnd = pcbnew.NETINFO_ITEM(b, "GND"); b.Add(gnd)
def mm(v): return pcbnew.FromMM(v)
def edge(x0, y0, x1, y1):
    for a, c in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        s = pcbnew.PCB_SHAPE(b); s.SetShape(pcbnew.SHAPE_T_SEGMENT); s.SetLayer(pcbnew.Edge_Cuts)
        s.SetStart(pcbnew.VECTOR2I(mm(a[0]), mm(a[1]))); s.SetEnd(pcbnew.VECTOR2I(mm(c[0]), mm(c[1]))); b.Add(s)
edge(0, 0, 100, 60)
expect = []
def via(x, y, tag, inside):
    v = pcbnew.PCB_VIA(b); b.Add(v)
    v.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y))); v.SetWidth(mm(0.45)); v.SetDrill(mm(0.2))
    v.SetNetCode(gnd.GetNetCode())
    expect.append((tag, round(x, 3), round(y, 3), inside))
for ref, x, y, rot, flip in (("U1", 20, 20, 0, False), ("U2", 50, 20, 90, False), ("U3", 80, 30, 30, True)):
    fp = pcbnew.FootprintLoad(lib, "SOIC-8_3.9x4.9mm_P1.27mm")
    fp.SetReference(ref); b.Add(fp)
    fp.SetPosition(pcbnew.VECTOR2I(mm(x), mm(y)))
    fp.SetOrientationDegrees(rot)
    if flip:
        try:
            fp.Flip(fp.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
        except Exception:
            fp.Flip(fp.GetPosition(), False)
    P = {p.GetNumber(): (pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)) for p in fp.Pads()}
    p1, p2, p8 = P["1"], P["2"], P["8"]
    ux, uy = p1[0] - p8[0], p1[1] - p8[1]; n = math.hypot(ux, uy); ux, uy = ux / n, uy / n   # outward from row 1
    mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
    # pad 1.95 long: band outer edge 0.975 + 0.5 = 1.475 beyond the pad centre line; via radius 0.225
    via(mx, my, ref + " mid", True)
    via(mx + ux * 1.6, my + uy * 1.6, ref + " edge-in", True)          # copper reaches 1.6 - 0.225 = 1.375
    via(mx + ux * 1.75, my + uy * 1.75, ref + " edge-out", False)      # copper from 1.525
    via(mx - ux * 1.3, my - uy * 1.3, ref + " body", False)            # inner end 0.975, copper from 1.075
fp = pcbnew.FOOTPRINT(b); fp.SetReference("U9"); b.Add(fp); fp.SetPosition(pcbnew.VECTOR2I(mm(30), mm(45)))
def pad(num, x, y, w, h):
    p = pcbnew.PAD(fp); p.SetNumber(num); p.SetAttribute(pcbnew.PAD_ATTRIB_SMD); p.SetShape(pcbnew.PAD_SHAPE_RECT)
    p.SetLayerSet(p.SMDMask()); p.SetSize(pcbnew.VECTOR2I(mm(w), mm(h)))
    p.SetFPRelativePosition(pcbnew.VECTOR2I(mm(x), mm(y))); fp.Add(p)
for i, yy in enumerate((-1, 0, 1)):
    pad(str(i + 1), -3, yy, 1.2, 0.5); pad(str(6 - i), 3, yy, 1.2, 0.5)
for yy in (-1, 0, 1):
    pad("7", 0.8, yy, 0.6, 0.8)
b.Save(out)
import json; json.dump(expect, open(out + ".expect.json", "w"))
'''

DSN = 'import pcbnew, sys\nb = pcbnew.LoadBoard(sys.argv[1])\nprint(pcbnew.ExportSpecctraDSN(b, sys.argv[2]))\n'


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
    return r.returncode, '\n'.join(l for l in (r.stdout + r.stderr).splitlines() if 'image handler' not in l)


def main():
    if not KP:
        print('KiCad Python not found - pad_row_keepouts tests skipped')
        return 0
    print('pad_row_keepouts.py')
    d = os.path.join(TMP, 'b')
    os.makedirs(d)
    pcb = os.path.join(d, 'rows.kicad_pcb')
    open(os.path.join(TMP, 'build.py'), 'w').write(BUILD)
    rc, out = run([KP, os.path.join(TMP, 'build.py'), pcb])
    if rc:
        ok(False, 'test board built', out)
        return 1
    open(os.path.join(d, 'rows.kicad_pro'), 'w').write('{}\n')
    exp = json.load(open(pcb + '.expect.json'))
    want_in = sorted((x, y) for _, x, y, i in exp if i)

    js = os.path.join(TMP, 'list.json')
    rc, out = run([KP, os.path.join(SCR, 'pad_row_keepouts.py'), pcb, '--list', '--json', js])
    rep = json.load(open(js)) if os.path.isfile(js) else []
    soic = [r for r in rep if r['ref'] in ('U1', 'U2', 'U3')]
    ok(rc == 0 and len(soic) == 6 and all(len(r['pins']) == 4 for r in soic), '--list: 2 rows of 4 on each SOIC-8', out)
    ok(len([r for r in rep if r['ref'] == 'U9']) == 2, '--list: the exposed pad split into three "7" pads is not a row',
       [r['pins'] for r in rep if r['ref'] == 'U9'])
    got = sorted((h[1], h[2]) for r in rep for h in r['vias_inside'])
    ok(got == want_in, '--list: exactly the vias whose copper reaches a band (0, 90, 30 deg flipped)',
       'got %s want %s' % (got, want_in))

    aj = os.path.join(TMP, 'audit.json')
    run(['node', os.path.join(SCR, 'kicad_audit.js'), pcb, '--no-sch', '--quiet', '--json', aj])
    a = json.load(open(aj)) if os.path.isfile(aj) else {}
    st = a.get('stats', {})
    msgs = [f['msg'] for f in a.get('findings', a.get('results', [])) if 'pad-row band' in f.get('msg', '')] \
        if isinstance(a.get('findings', a.get('results')), list) else []
    ok(st.get('pad_row_bands') == len(rep) and st.get('vias_in_pad_row_band') == len(want_in),
       'audit section 26 agrees: %s bands, %s vias' % (st.get('pad_row_bands'), st.get('vias_in_pad_row_band')),
       json.dumps(st)[:400] + ' | ' + ' / '.join(msgs[:3]))

    rc, out = run([KP, os.path.join(SCR, 'pad_row_keepouts.py'), pcb, '--write'])
    ok(rc == 0 and '%d new' % len(rep) in out, '--write adds one KO_ROW_* rule area per band', out)
    rc, out = run([KP, os.path.join(SCR, 'pad_row_keepouts.py'), pcb, '--write'])
    ok(rc == 0 and '%d edited, 0 new' % len(rep) in out, '--write again edits them in place', out)
    chk = ('import pcbnew, sys\nb = pcbnew.LoadBoard(sys.argv[1])\n'
           'z = [z for z in b.Zones() if z.GetZoneName().startswith("KO_ROW_")]\n'
           'print(len(z), all(q.GetIsRuleArea() and q.GetDoNotAllowVias() and not q.GetDoNotAllowTracks() and '
           'q.GetLayerSet().Contains(pcbnew.F_Cu) and q.GetLayerSet().Contains(pcbnew.B_Cu) for q in z))\n')
    open(os.path.join(TMP, 'chk.py'), 'w').write(chk)
    rc, out = run([KP, os.path.join(TMP, 'chk.py'), pcb])
    ok(out.split()[-2:] == [str(len(rep)), 'True'], 'rule areas: vias forbidden on F.Cu and B.Cu, tracks allowed', out)
    if CLI:
        dj = os.path.join(TMP, 'drc.json')
        run([CLI, 'pcb', 'drc', '--format', 'json', '-o', dj, pcb])
        v = json.load(open(dj))['violations'] if os.path.isfile(dj) else []
        hit = sorted((round(i['pos']['x'], 3), round(i['pos']['y'], 3)) for x in v if x['type'] == 'items_not_allowed'
                     for i in x['items'] if i['description'].startswith('Via'))
        ok(hit == want_in, 'kicad-cli DRC flags exactly the same vias', 'drc %s want %s' % (hit, want_in))
    else:
        print('  skip kicad-cli not found')

    d2 = os.path.join(TMP, 'x')
    os.makedirs(d2)
    cp = os.path.join(d2, 'rows.kicad_pcb')
    shutil.copy(os.path.join(d, 'rows.kicad_pcb'), cp)
    open(os.path.join(d2, 'rows.kicad_pro'), 'w').write('{}\n')
    rc, out = run([KP, os.path.join(SCR, 'export_keepouts.py'), cp, '--export-copy', '--pad-row-bands'])
    ok(rc == 0 and 'pad-row bands: %d' % len(rep) in out, 'export_keepouts.py --pad-row-bands', out)
    open(os.path.join(TMP, 'dsn.py'), 'w').write(DSN)
    dsn = os.path.join(TMP, 'x.dsn')
    run([KP, os.path.join(TMP, 'dsn.py'), cp, dsn])
    txt = open(dsn, encoding='utf-8', errors='replace').read() if os.path.isfile(dsn) else ''
    ok(txt.count('via_keepout') >= 2 * 2 * len(rep), 'the DSN carries them as via_keepout (%d)' % txt.count('via_keepout'))

    print('\n%d passed, %d failed' % (PASS, FAIL))
    if not FAIL:
        shutil.rmtree(TMP, ignore_errors=True)
    else:
        print('kept ' + TMP)
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
