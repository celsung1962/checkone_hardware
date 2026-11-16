#!/usr/bin/env python
"""run_tests_fanout.py - self-test for the fan-out pattern and the pin-array channel centreline (lessons L21 / L22,
1.24.0).

Runs on the system Python; drives KiCad's Python, node and kicad-cli; skipped when KiCad's Python is absent.

  fan-out     SOIC-8 U1, pins 1-4 leave axially and bend 45 deg at 0.8 / 1.3 / 0.9 / 1.6 mm from the pad centres, then
              run parallel to the exit: audit section 31 WARNs the group (spread 0.8 mm) and section 7 FAILs the bends
              closer than 0.5 mm to the pad edge. fanout_regularise.py --list reports the group; --apply moves every
              first bend to 1.6 mm (pad edge + 0.5 is 1.475): the WARN and those pad-entry FAILs go, DRC does not rise,
              every segment keeps its direction and the far ends do not move
  centreline  2 x 3 THT grid at a 4 mm pitch (channel 2.5 mm, wider than the between-pads limit): a track along the
              channel 0.3 mm off its centreline -> audit section 29 FAIL pin-array "off-centre"; on the centreline no
              finding; center_gaps_safe.py --apply centres it from the audit JSON and the FAIL goes
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
TMP = tempfile.mkdtemp(prefix='kr_fanout_')
KP = KS.find_kicad_python()

BUILD = r'''
import json, math, os, sys, pcbnew
out, kind = sys.argv[1], sys.argv[2]
b = pcbnew.BOARD(); b.SetCopperLayerCount(2)
def mm(v): return pcbnew.FromMM(v)
def V(x, y): return pcbnew.VECTOR2I(mm(x), mm(y))
for a, c in (((0, 0), (40, 0)), ((40, 0), (40, 30)), ((40, 30), (0, 30)), ((0, 30), (0, 0))):
    s = pcbnew.PCB_SHAPE(b); s.SetShape(pcbnew.SHAPE_T_SEGMENT); s.SetLayer(pcbnew.Edge_Cuts)
    s.SetStart(V(*a)); s.SetEnd(V(*c)); b.Add(s)
nets = {}
def net(n):
    if n not in nets:
        nets[n] = pcbnew.NETINFO_ITEM(b, n); b.Add(nets[n])
    return nets[n]
def track(pts, n, w=0.2):
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        t = pcbnew.PCB_TRACK(b); b.Add(t); t.SetStart(V(x1, y1)); t.SetEnd(V(x2, y2)); t.SetWidth(mm(w))
        t.SetLayer(pcbnew.F_Cu); t.SetNetCode(net(n).GetNetCode())
if kind == 'fanout':
    base = None
    for b_ in (r"C:\Program Files\KiCad\10.0\share\kicad\footprints", "/usr/share/kicad/footprints",
               "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"):
        if os.path.isdir(os.path.join(b_, "Package_SO.pretty")):
            base = b_
    fp = pcbnew.FootprintLoad(os.path.join(base, "Package_SO.pretty"), "SOIC-8_3.9x4.9mm_P1.27mm")
    fp.SetReference("U1"); b.Add(fp); fp.SetPosition(V(25, 15))
    k = 0.75 / math.sqrt(2) * math.sqrt(2)     # 45-degree run of 0.75 mm in x and y
    for num, D in (("1", 0.8), ("2", 1.3), ("3", 0.9), ("4", 1.6)):
        p = [q for q in fp.Pads() if q.GetNumber() == num][0]
        p.SetNet(net("N" + num))
        cx, cy = pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)
        v1 = (cx - D, cy); v2 = (v1[0] - 0.75, cy - 0.75); v3 = (10, v2[1])
        track([(cx, cy), v1, v2, v3], "N" + num)
else:
    fp = pcbnew.FOOTPRINT(b); fp.SetReference("J1"); b.Add(fp); fp.SetPosition(V(10, 10))
    i = 0
    for yy in (0, 4):
        for xx in (0, 4, 8):
            i += 1
            p = pcbnew.PAD(fp); p.SetNumber(str(i)); p.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
            p.SetShape(pcbnew.PAD_SHAPE_CIRCLE); p.SetSize(V(1.5, 1.5)); p.SetDrillSize(V(0.9, 0.9))
            p.SetLayerSet(p.PTHMask()); p.SetFPRelativePosition(V(xx, yy)); fp.Add(p)
    y = 12.0 + float(kind)
    track([(7, 6), (7, y), (21, y), (21, 18)], "S")
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
    r = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', errors='replace')
    return r.returncode, '\n'.join(l for l in (r.stdout + r.stderr).splitlines()
                                   if 'image handler' not in l and 'memory leak' not in l)


def board(name, kind):
    d = os.path.join(TMP, name)
    os.makedirs(d)
    pcb = os.path.join(d, 'f.kicad_pcb')
    rc, out = run([KP, os.path.join(TMP, 'build.py'), pcb, kind])
    if rc:
        raise SystemExit('board build failed: ' + out)
    open(os.path.join(d, 'f.kicad_pro'), 'w').write('{}\n')
    return pcb


def audit(pcb):
    j = pcb + '.audit.json'
    run(['node', os.path.join(SCR, 'kicad_audit.js'), pcb, '--no-sch', '--quiet', '--json', j])
    return json.load(open(j))


def tracks(pcb):
    code = ('import pcbnew, sys\nb = pcbnew.LoadBoard(sys.argv[1])\n'
            'for t in b.GetTracks():\n'
            '    print(t.GetNetname(), round(pcbnew.ToMM(t.GetStart().x), 4), round(pcbnew.ToMM(t.GetStart().y), 4), '
            'round(pcbnew.ToMM(t.GetEnd().x), 4), round(pcbnew.ToMM(t.GetEnd().y), 4))\n')
    open(os.path.join(TMP, 'tr.py'), 'w').write(code)
    rc, out = run([KP, os.path.join(TMP, 'tr.py'), pcb])
    return [l.split() for l in out.splitlines() if l[:1] in 'NS']


def main():
    if not KP:
        print('KiCad Python not found - fan-out tests skipped')
        return 0
    open(os.path.join(TMP, 'build.py'), 'w').write(BUILD)
    print('fan-out pattern (L22)')
    pcb = board('fan', 'fanout')
    a = audit(pcb)
    fo = [f['msg'] for f in a['findings'] if f['check'] == 'fan-out']
    pe = [f['msg'] for f in a['findings'] if f['check'] == 'pad-entry' and 'last bend' in f['msg']]
    ok(len(fo) == 1 and 'pins 1, 2, 3, 4' in fo[0] and '0.8 to 1.6 mm' in fo[0], 'audit 31: one WARN for the U1 group (0.8 to 1.6 mm)', fo)
    ok(len(pe) == 3, 'audit 7: three bends closer than 0.5 mm to the pad edge', pe)
    rc, out = run([KP, os.path.join(SCR, 'fanout_regularise.py'), pcb, '--list'])
    ok(rc == 0 and 'U1     row 1 F.Cu: pins 1,2,3,4, bends 0.800..1.600 mm (spread 0.800)' in out, '--list reports the group', out)
    before = tracks(pcb)
    rc, out = run([KP, os.path.join(SCR, 'fanout_regularise.py'), pcb, '--apply'])
    a2 = audit(pcb)
    fo2 = [f for f in a2['findings'] if f['check'] == 'fan-out']
    pe2 = [f for f in a2['findings'] if f['check'] == 'pad-entry' and 'last bend' in f['msg']]
    ok(rc == 0 and 'D 1.600: kept' in out and not fo2 and not pe2, '--apply aligns the bends at 1.6 mm: fan-out WARN and pad-entry FAILs gone', (out, fo2, pe2))
    after = tracks(pcb)
    import math

    def dirs(rows):
        return sorted((r[0], round(math.degrees(math.atan2(float(r[4]) - float(r[2]), float(r[3]) - float(r[1]))) % 180, 1)) for r in rows)
    far_b = sorted((r[0], r[3], r[4]) for r in before if float(r[3]) == 10.0)
    far_a = sorted((r[0], r[3], r[4]) for r in after if float(r[3]) == 10.0)
    ok(dirs(before) == dirs(after) and far_b == far_a and len(far_a) == 4,
       'every segment keeps its direction; the far ends do not move', (before, after))
    bends = sorted({round(float(r[3]), 4) for r in after if r[0] in ('N1', 'N2', 'N3', 'N4') and r[1] == '22.525'})
    ok(len(bends) == 1, 'all four first bends on one line (x = %s)' % bends, after)

    print('pin-array channel centreline (L21)')
    pcb = board('cl_on', '0')
    a = audit(pcb)
    oc = [f for f in a['findings'] if f['check'] == 'pin-array']
    ok(not oc and a['stats'].get('pin_arrays') == 1, 'track on the channel centreline: no pin-array finding', oc)
    pcb = board('cl_off', '0.3')
    a = audit(pcb)
    oc = [f['msg'] for f in a['findings'] if f['check'] == 'pin-array' and 'off-centre' in f['msg']]
    ok(len(oc) == 1 and 'runs between pads J1-' in oc[0] and '@ 7,12.3 (F.Cu)' in oc[0], 'track 0.3 mm off the centreline -> FAIL pin-array off-centre', oc or a['findings'][:5])
    j = pcb + '.audit.json'
    rc, out = run([KP, os.path.join(SCR, 'center_gaps_safe.py'), pcb, j, '--apply'])
    a2 = audit(pcb)
    oc2 = [f for f in a2['findings'] if f['check'] == 'pin-array']
    ok(rc == 0 and 'centred' in out and not oc2, 'center_gaps_safe.py --apply centres it from the audit JSON', (out, oc2))

    print('\n%d passed, %d failed' % (PASS, FAIL))
    if not FAIL:
        shutil.rmtree(TMP, ignore_errors=True)
    else:
        print('kept ' + TMP)
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
