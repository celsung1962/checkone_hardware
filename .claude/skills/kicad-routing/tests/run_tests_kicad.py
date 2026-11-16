#!/usr/bin/env python
"""run_tests_kicad.py - self-test for the tools that need pcbnew (kicad-routing 1.18.0, 1.19.0).

Run with KiCad's own Python. Boards are built through the pcbnew API and saved, so every fixture is a real
KiCad 10 file. Covers what the ServiceOne routing (2026-10-04) found or added:
  init_project.py       writes the 1.16.0 keys itself, with empty decision lists (no template via-in-pad refs)
  pcbnew                saves only the first outline of a zone (why export_keepouts writes one zone per ring)
  export_keepouts.py    edge band one zone per ring; crystal/inductor corridors; refuses without --export-copy
  stitch_residual.py    hole-to-hole against a same-net via
  center_gaps_safe.py   --indices batch option; centre_gated.py keeps a DRC-clean centring
  finish_gated.py       routes an open 2-pad connection and keeps it only when DRC agrees
1.19.0 (ServiceOne datasheet layout fixes, 2026-10-05):
  init_project.py       writes layout_checks with empty lists
  layout_measure.py     kelvin: a sense line tapped on the power track FAILs, a dedicated one PASSes; gap
  route_finish.py       --exclusive dedicated trace, exact pad-centre ends, via layer flags, hole clearance
centre_gated / finish_gated also need node and kicad-cli; those assertions are skipped when absent.

    "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" tests/run_tests_kicad.py
"""
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile

try:
    import pcbnew
except ImportError:
    print('SKIP  pcbnew not importable - run this suite with KiCad\'s Python')
    sys.exit(0)

HERE = os.path.dirname(os.path.abspath(__file__))
SCR = os.path.join(HERE, '..', 'scripts')
sys.path.insert(0, SCR)
import kicad_sexp as KS  # noqa: E402

FM = lambda v: pcbnew.FromMM(float(v))
MM = pcbnew.ToMM
V = lambda x, y: pcbnew.VECTOR2I(FM(x), FM(y))
PASS = FAIL = 0
TMP = tempfile.mkdtemp(prefix='kr_kicad_')
CLI = KS.find_kicad_cli()
NODE = shutil.which('node')


def check(label, cond, detail=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print('PASS  %s%s' % (label, ('  - ' + str(detail)[:200]) if detail else ''))
    else:
        FAIL += 1
        print('FAIL  %s  - %s' % (label, str(detail)[:400]))


def run(script, *args):
    return subprocess.run([sys.executable, os.path.join(SCR, script)] + list(args), capture_output=True, text=True)


# ---------------------------------------------------------------- board builders
def board(w=30, h=20, cutout=None, layers=4):
    # NewBoard, not BOARD(): on Linux SaveBoard writes the .kicad_pro only for a board created with a project
    b = pcbnew.NewBoard(os.path.join(TMP, '_new.kicad_pcb'))
    b.SetCopperLayerCount(layers)
    s = pcbnew.PCB_SHAPE(b); s.SetShape(pcbnew.SHAPE_T_POLY); s.SetLayer(pcbnew.Edge_Cuts); s.SetWidth(FM(0.05))
    s.SetPolyPoints([V(0, 0), V(w, 0), V(w, h), V(0, h)]); b.Add(s)
    if cutout:
        c = pcbnew.PCB_SHAPE(b); c.SetShape(pcbnew.SHAPE_T_CIRCLE); c.SetLayer(pcbnew.Edge_Cuts); c.SetWidth(FM(0.05))
        c.SetCenter(V(cutout[0], cutout[1])); c.SetEnd(V(cutout[0] + cutout[2], cutout[1])); b.Add(c)
    return b


def net(b, name):
    n = b.FindNet(name)
    if n is None:
        n = pcbnew.NETINFO_ITEM(b, name); b.Add(n)
    return n


def part(b, ref, x, y, pads, crt=None):
    """pads: [(num, dx, dy, w, h, netname)]; crt: courtyard half-size (hx, hy)."""
    f = pcbnew.FOOTPRINT(b); f.SetReference(ref); f.SetValue(ref); f.SetPosition(V(x, y))
    b.Add(f)
    for num, dx, dy, w, h, nn in pads:
        p = pcbnew.PAD(f); p.SetNumber(num); p.SetShape(pcbnew.PAD_SHAPE_RECT); p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetLayerSet(pcbnew.PAD.SMDMask()); p.SetSize(V(w, h)); p.SetPosition(V(x + dx, y + dy))
        if nn:
            p.SetNet(net(b, nn))
        f.Add(p)
    if crt:
        s = pcbnew.PCB_SHAPE(f); s.SetShape(pcbnew.SHAPE_T_RECT); s.SetLayer(pcbnew.F_CrtYd); s.SetWidth(FM(0.05))
        s.SetStart(V(x - crt[0], y - crt[1])); s.SetEnd(V(x + crt[0], y + crt[1])); f.Add(s)
    return f


def plane(b, nn, layer=pcbnew.In1_Cu, w=30, h=20):
    z = pcbnew.ZONE(b); z.SetLayer(layer); z.SetNet(net(b, nn))
    sp = pcbnew.SHAPE_POLY_SET(); sp.NewOutline()
    for x, y in ((0.5, 0.5), (w - 0.5, 0.5), (w - 0.5, h - 0.5), (0.5, h - 0.5)):
        sp.Append(FM(x), FM(y))
    z.Outline().Append(sp); b.Add(z)


def save(b, name):
    p = os.path.join(TMP, name)
    pcbnew.SaveBoard(p, b)
    return p


def track(b, nn, pts, w=0.2, layer=pcbnew.F_Cu):
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        t = pcbnew.PCB_TRACK(b); t.SetStart(V(x1, y1)); t.SetEnd(V(x2, y2)); t.SetWidth(FM(w)); t.SetLayer(layer)
        t.SetNet(net(b, nn)); b.Add(t)


# ================================================================ init_project.py
b = board()
part(b, 'U1', 10, 10, [('1', -0.5, 0, 0.4, 0.6, 'GND'), ('2', 0.5, 0, 0.4, 0.6, 'SIG')])
p = save(b, 'init.kicad_pcb')
r = run('init_project.py', p, '--fab', 'jlcpcb', '--layers', '4', '--copper', '1oz', '--force')
pj = os.path.join(TMP, 'kicad_golden.project.json')
P = json.load(open(pj, encoding='utf-8')) if os.path.exists(pj) else {}
check('init_project writes via_in_pad with an EMPTY allowed_refs (the template carried another board\'s parts)',
      P.get('via_in_pad', {}).get('allowed_refs') == [], (r.returncode, P.get('via_in_pad')))
check('init_project writes the 1.16.0 keys (shared_pad_gaps, plane_net_exceptions, detour_limits, priority_routing, router_costs)',
      all(k in P for k in ('shared_pad_gaps', 'plane_net_exceptions', 'detour_limits', 'priority_routing', 'router_costs'))
      and P['shared_pad_gaps'].get('allowed') is False and P['plane_net_exceptions'].get('allowed') == []
      and P['priority_routing'].get('critical_nets') == [], sorted(P))

check('1.19.0: init_project writes layout_checks with EMPTY kelvin / decoupling / separation lists',
      P.get('layout_checks', {}).get('kelvin') == [] and P['layout_checks'].get('decoupling') == []
      and P['layout_checks'].get('separation') == [], P.get('layout_checks'))

# ================================================================ pcbnew: a zone keeps only its first outline on save
# Measured 2026-10-04 (KiCad 10.0.6): a ZONE built with two outlines is written with ONE (polygon) block - the
# second outline is lost. This is why export_keepouts.py writes one rule area per ring. (First read on ServiceOne
# as "the DSN export keeps only the first outline"; the loss happens earlier, at save.)
b = board(40, 20)
z = pcbnew.ZONE(b); z.SetIsRuleArea(True); z.SetDoNotAllowTracks(True); z.SetLayer(pcbnew.F_Cu)
two = pcbnew.SHAPE_POLY_SET()
for x0 in (15, 28):
    two.NewOutline()
    for x, y in ((x0, 5), (x0 + 4, 5), (x0 + 4, 15), (x0, 15)):
        two.Append(FM(x), FM(y))
z.Outline().Append(two); b.Add(z)
p = save(b, 'multi.kicad_pcb')
b2 = pcbnew.LoadBoard(p)
check('pcbnew limitation still present: a 2-outline zone reloads with 1 outline (export_keepouts relies on one zone per ring)',
      b2.GetAreaCount() == 1 and b2.GetArea(0).Outline().OutlineCount() == 1, b2.GetArea(0).Outline().OutlineCount())

# ================================================================ export_keepouts.py
b = board(30, 20, cutout=(22, 10, 3))
part(b, 'L1', 8, 10, [('1', -1.5, 0, 1.1, 3.7, 'SW'), ('2', 1.5, 0, 1.1, 3.7, 'OUT')], crt=(2.35, 2.3))
part(b, 'FID1', 26, 3, [('1', 0, 0, 1.0, 1.0, None)])
p = save(b, 'ko.kicad_pcb')
r = run('export_keepouts.py', p, '--edge-band', '0.55')
check('export_keepouts refuses without --export-copy (it must never touch the real board)', r.returncode == 2, r.returncode)
r = run('export_keepouts.py', p, '--export-copy', '--edge-band', '0.55', '--corridors', 'auto', '--fiducials')
b2 = pcbnew.LoadBoard(p)
zs = [b2.GetArea(i) for i in range(b2.GetAreaCount())]
edge = [z for z in zs if z.GetZoneName().startswith('KO_EXPORT_EDGE')]
check('edge band: one rule area per ring (outline + cut-out = 2), each a single outline for the DSN',
      len(edge) == 2 and all(z.Outline().OutlineCount() == 1 for z in edge), [(z.GetZoneName(), z.Outline().OutlineCount()) for z in edge])
lko = [z for z in zs if z.GetZoneName().startswith('KO_EXPORT_L1')]
l1 = b2.FindFootprintByReference('L1')
pads_free = all(not any(z.Outline().Contains(pd.GetPosition()) for z in lko) for pd in l1.Pads())
body_in = any(z.Outline().Contains(V(8, 10)) for z in lko)
check('inductor corridors: the body is kept out, both pads stay reachable', bool(lko) and pads_free and body_in,
      (len(lko), pads_free, body_in, r.stdout[-200:]))
check('fiducial keepout added', any(z.GetZoneName() == 'KO_EXPORT_FID1' for z in zs), [z.GetZoneName() for z in zs])

# ================================================================ stitch_residual.py: same-net hole-to-hole
b = board(30, 20)
plane(b, 'GND')
part(b, 'C1', 10, 10, [('1', 0, 0, 0.6, 0.6, 'GND')])
v = pcbnew.PCB_VIA(b); v.SetPosition(V(10.75, 10)); v.SetWidth(FM(0.45)); v.SetDrill(FM(0.2)); v.SetNet(net(b, 'GND'))
v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); b.Add(v)
p = save(b, 'resid.kicad_pcb')
r = run('stitch_residual.py', p, 'C1-1', '--apply')
b2 = pcbnew.LoadBoard(p)
vias = [t for t in b2.GetTracks() if t.GetClass() == 'PCB_VIA']
gaps = [math.hypot(MM(a.GetPosition().x - c.GetPosition().x), MM(a.GetPosition().y - c.GetPosition().y)) - MM(a.GetDrill() + c.GetDrill()) / 2
        for i, a in enumerate(vias) for c in vias[i + 1:]]
check('stitch_residual keeps hole-to-hole (>= 0.254 mm drill edge to drill edge) to a SAME-net via',
      len(vias) == 2 and min(gaps) >= 0.254 - 1e-6, (len(vias), [round(g, 3) for g in gaps], r.stdout[-200:]))

# ================================================================ center_gaps_safe.py --indices / centre_gated.py
if NODE and CLI:
    b = board(30, 20)
    part(b, 'R1', 15, 8, [('1', 0, 0, 0.8, 0.8, 'A')])
    part(b, 'R2', 15, 9.7, [('1', 0, 0, 0.8, 0.8, 'B')])                 # 0.9 mm free between R1-1 and R2-1
    # gap centre line y 8.85; the track runs 0.1 mm off it, in three segments joined away from any pad
    track(b, 'S', [(6, 8.75), (10, 8.75), (20, 8.75), (24, 8.75)])
    part(b, 'J1', 6, 8.75, [('1', 0, 0, 0.6, 0.6, 'S')]); part(b, 'J2', 24, 8.75, [('1', 0, 0, 0.6, 0.6, 'S')])
    p = save(b, 'centre.kicad_pcb')
    aj = os.path.join(TMP, 'centre_audit.json')
    subprocess.run(['node', os.path.join(SCR, 'kicad_audit.js'), p, '--json', aj, '--no-sch', '--quiet'], capture_output=True, cwd=os.path.expanduser('~'))
    bp = [f for f in json.load(open(aj, encoding='utf-8'))['findings'] if f['check'] == 'between-pads' and f['level'] == 'FAIL']
    check('fixture: the audit reports the off-centre track between R1-1 and R2-1', len(bp) == 1, [f['msg'][:120] for f in bp])
    work = os.path.join(TMP, 'cg')
    r = subprocess.run([sys.executable, os.path.join(SCR, 'centre_gated.py'), p, work, '--rounds', '2'],
                       capture_output=True, text=True, timeout=1200)
    res = os.path.join(work, 'centre.kicad_pcb')
    aj2 = os.path.join(TMP, 'centre_audit2.json')
    subprocess.run(['node', os.path.join(SCR, 'kicad_audit.js'), res, '--json', aj2, '--no-sch', '--quiet'], capture_output=True, cwd=os.path.expanduser('~'))
    bp2 = [f for f in json.load(open(aj2, encoding='utf-8'))['findings'] if f['check'] == 'between-pads' and f['level'] == 'FAIL']
    check('centre_gated (center_gaps_safe --indices in batches) centres it and keeps the result', len(bp2) == 0,
          (r.stdout[-400:], [f['msg'][:120] for f in bp2]))
    b0 = pcbnew.LoadBoard(p)
    check('centre_gated leaves the input board untouched without --apply',
          any(abs(MM(t.GetStart().y) - 8.75) < 1e-6 and MM(t.GetLength()) > 9 for t in b0.GetTracks()), '')
else:
    print('SKIP  centre_gated: node or kicad-cli not found')

# ================================================================ finish_gated.py
if CLI:
    b = board(30, 20, layers=2)
    part(b, 'R1', 8, 10, [('1', 0, 0, 0.8, 0.9, 'SIG')])
    part(b, 'R2', 20, 10, [('1', 0, 0, 0.8, 0.9, 'SIG')])
    p = save(b, 'finish.kicad_pcb')
    r = subprocess.run([sys.executable, os.path.join(SCR, 'finish_gated.py'), p], capture_output=True, text=True, timeout=1800)
    m = re.search(r'end: unconnected (\d+)', r.stdout)
    check('finish_gated routes an open 2-pad connection and keeps it (DRC-gated)', bool(m) and m.group(1) == '0', r.stdout[-400:])
    check('finish_gated writes a backup before touching the board', os.path.exists(p + '.bak_prefinish'), '')
else:
    print('SKIP  finish_gated: kicad-cli not found')


# ================================================================ 1.19.0: layout_measure.py kelvin / gap, route_finish.py --exclusive
# ServiceOne (2026-10-05): both INA226 sense inputs had been routed by tapping the power track 8 mm and 58 mm away
# from the shunt pads - DRC-clean (same net), +20 % and +47 % current error. The fixture reproduces a tapped sense
# line; layout_measure must FAIL it, and a route_finish --exclusive trace from the shunt pad must PASS.


def kelvin_board(tapped, hole=False):
    b = board(40, 22)
    part(b, 'J1', 4, 10, [('1', 0, 0, 1.2, 1.2, 'PWR')])
    part(b, 'J2', 34, 10, [('1', 0, 0, 1.2, 1.2, 'LOAD')])
    part(b, 'R1', 15.5, 10, [('1', -1.5, 0, 1.0, 1.6, 'PWR'), ('2', 1.5, 0, 1.0, 1.6, 'LOAD')], crt=(2.3, 1.1))
    part(b, 'U1', 15.5, 17, [('1', -1.0, 0, 0.4, 0.8, 'PWR'), ('2', 1.0, 0, 0.4, 0.8, 'LOAD')], crt=(1.6, 0.8))
    track(b, 'PWR', [(4, 10), (14, 10)], w=0.6)
    track(b, 'LOAD', [(17, 10), (34, 10)], w=0.6)
    if tapped:
        track(b, 'PWR', [(14.5, 17), (14.5, 13), (11.5, 10)])
        track(b, 'LOAD', [(16.5, 17), (16.5, 13.5), (20, 10)])
    if hole:
        f = pcbnew.FOOTPRINT(b); f.SetReference('H1'); f.SetPosition(V(14.5, 13.5)); b.Add(f)
        h = pcbnew.PAD(f); h.SetAttribute(pcbnew.PAD_ATTRIB_NPTH); h.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        h.SetLayerSet(pcbnew.PAD.UnplatedHoleMask()); h.SetSize(V(1.0, 1.0)); h.SetDrillSize(V(1.0, 1.0))
        h.SetPosition(V(14.5, 13.5)); f.Add(h)
    return b


def lm(*a):
    r = subprocess.run([sys.executable, os.path.join(SCR, 'layout_measure.py')] + list(a), capture_output=True, text=True)
    rows = [json.loads(l.split('  ', 1)[1] if l.startswith(('PASS', 'FAIL')) else l) for l in r.stdout.splitlines() if '{' in l]
    return r.returncode, rows


p = save(kelvin_board(True), 'kelvin_tapped.kicad_pcb')
rc, rows = lm('kelvin', p, 'U1.1', 'R1.1', 'J1.1')
check('layout_measure kelvin FAILs a sense line tapped on the power track (shared copper > 0, exit 1)',
      rc == 1 and rows and rows[0]['shared_mm'] > 1.0 and rows[0]['pass'] is False, rows)
rc, rows = lm('kelvin', p, 'U1.2', 'R1.2', 'J2.1')
check('... on the load side too (the tap is on the far side of the shunt)', rc == 1 and rows and rows[0]['pass'] is False, rows)

p = save(kelvin_board(False, hole=True), 'kelvin_route.kicad_pcb')
r1 = run('route_finish.py', p, '--net', 'PWR', '--from-pad', 'R1.1', '--to-pad', 'U1.1', '--exclusive', '--width', '0.2',
         '--grid', '0.05', '--safety', '0.05', '--via-cost', '500')
r2 = run('route_finish.py', p, '--net', 'LOAD', '--from-pad', 'R1.2', '--to-pad', 'U1.2', '--exclusive', '--width', '0.2',
         '--grid', '0.05', '--safety', '0.05', '--via-cost', '40', '--layer', 'B.Cu')
rc, rows = lm('kelvin', p, 'U1.1', 'R1.1', 'J1.1')
rc2, rows2 = lm('kelvin', p, 'U1.2', 'R1.2', 'J2.1')
check('route_finish --exclusive draws a dedicated sense trace: layout_measure kelvin PASSes on both sides',
      r1.returncode == 0 and r2.returncode == 0 and rc == 0 and rc2 == 0 and rows[0]['shared_mm'] == 0 and rows2[0]['shared_mm'] == 0,
      (r1.stdout[-200:], r2.stdout[-200:], rows, rows2))
b2 = pcbnew.LoadBoard(p)
ends = set()
for t in b2.GetTracks():
    if t.GetClass() != 'PCB_VIA' and t.GetNetname() == 'PWR' and MM(t.GetWidth()) < 0.3:
        ends |= {(round(MM(t.GetStart().x), 4), round(MM(t.GetStart().y), 4)), (round(MM(t.GetEnd().x), 4), round(MM(t.GetEnd().y), 4))}
check('--from-pad / --to-pad: the trace starts and ends exactly on the pad centres (audit pad-entry rule)',
      (14.0, 10.0) in ends and (14.5, 17.0) in ends, sorted(ends)[:6])
hc = b2.GetDesignSettings().m_HoleClearance
dmin = min((MM(t.GetEffectiveShape().GetClearance(pcbnew.SHAPE_CIRCLE(V(14.5, 13.5), FM(0.5))))
            for t in b2.GetTracks() if t.GetClass() != 'PCB_VIA' and MM(t.GetWidth()) < 0.3), default=99)
check('route_finish keeps the board hole clearance to an NPTH hole in the way (was copper clearance only)',
      dmin >= MM(hc) - 1e-3, (round(dmin, 3), MM(hc)))
b = board(20, 20)
part(b, 'A1', 5, 10, [('1', 0, 0, 0.8, 0.8, 'S')])
part(b, 'A2', 15, 10, [('1', 0, 0, 0.8, 0.8, 'S')])
track(b, 'WALL', [(10, 0.6), (10, 19.4)])                 # F.Cu wall from edge to edge: the route needs a via
p = save(b, 'viaflags.kicad_pcb')
r3 = run('route_finish.py', p, '--net', 'S', '--from-pad', 'A1.1', '--to-pad', 'A2.1', '--grid', '0.05', '--safety', '0.05',
         '--via-cost', '5', '--edge', '0.3')
vias = [t for t in pcbnew.LoadBoard(p).GetTracks() if t.GetClass() == 'PCB_VIA']
check('route_finish vias carry remove_unused_layers / keep_end_layers (audit Q-06)',
      bool(vias) and all(v.Cast().GetRemoveUnconnected() and v.Cast().GetKeepStartEnd() for v in vias), (len(vias), r3.stdout[-200:]))

b = board(30, 12)
track(b, 'CLK', [(2, 5), (28, 5)])
track(b, 'AIN', [(2, 5.5), (12, 5.5)])           # 0.3 mm gap edge to edge over 10 mm
track(b, 'AIN', [(12, 5.5), (12, 9)])
p = save(b, 'gap.kicad_pcb')
rc, rows = lm('gap', p, '--a', 'AIN', '--b', 'CLK', '--max', '1.0')
check('layout_measure gap: same-layer edge gap and parallel length', rows and abs(rows[0]['min_gap_mm'] - 0.3) < 0.02
      and 9.0 <= rows[0]['within_max'][0]['parallel_mm'] <= 11.0, rows)
rc, rows = lm('gap', p, '--a', 'AIN', '--b', 'CLK', '--max', '1.0', '--exempt', '4,5.25,3')
check('layout_measure gap --exempt ignores the area around the IC pins (10 mm run -> about 5 mm counted)',
      rows and rows[0]['within_max'] and 4.0 <= rows[0]['within_max'][0]['parallel_mm'] <= 6.5, rows)

shutil.rmtree(TMP, ignore_errors=True)
print('\n%d/%d assertions passed' % (PASS, PASS + FAIL))
sys.exit(1 if FAIL else 0)
