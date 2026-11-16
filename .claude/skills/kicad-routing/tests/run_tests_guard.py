#!/usr/bin/env python
"""run_tests_guard.py - self-test for the board review rev. 0.2 script fixes (2026-10-20).

Runs on the system Python; the parts that need pcbnew are run through KiCad's Python (found like the scripts find
it: KICAD_PYTHON, then the usual install paths) and are skipped when it is absent. node is needed for the
apply_settings.js cases, kicad-cli for the finish_gated layout gate.

  board_guard.py        refuses on a KiCad lock file (board or project) and on a missing .kicad_pro; --force-write,
                        --allow-no-pro; a board-writing script (stitch_planes, route_finish) refuses and leaves the
                        board byte-identical
  zone_fill_check.py    a via moved without refilling is reported STALE (exit 1); --fix refills and saves; the
                        check is clean afterwards; route_finish.py saves a current fill
  stitch_planes.py      economical via tier drops the 0.25 / 0.15 fallback via
  apply_settings.js     keeps an approved deviation (min_hole_clearance 0.2 on JLCPCB 4L), refuses one below the
                        profile minimum (exit 3, nothing written), leaves a recorded fabricator block untouched
                        without --fab, inserts the economical 0.45 / 0.2 via (0.25 / 0.15 only with --fine-vias)
                        and records economical_via_drill_mm / fine_vias_approved
  finish_gated.py       --help exits 0; --no-layout-gate parses; the layout gate reverts a route that breaks a
                        layout check that passed at the start, and --no-layout-gate keeps it

    py -3 tests/run_tests_guard.py
"""
import hashlib
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
import board_guard  # noqa: E402
import kicad_sexp as KS  # noqa: E402

PASS = FAIL = 0
TMP = tempfile.mkdtemp(prefix='kr_guard_')
KP = KS.find_kicad_python()
CLI = KS.find_kicad_cli()
NODE = shutil.which('node')
ENV = {k: v for k, v in os.environ.items() if k not in (board_guard.FORCE_ENV, board_guard.NO_PRO_ENV)}


def check(label, cond, detail=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print('PASS  %s' % label)
    else:
        FAIL += 1
        print('FAIL  %s  - %s' % (label, str(detail)[:600]))


def sha(p):
    return hashlib.sha1(open(p, 'rb').read()).hexdigest()


def run(argv, **kw):
    kw.setdefault('timeout', 1800)
    return subprocess.run(argv, capture_output=True, text=True, env=ENV, **kw)


def write(p, text):
    with open(p, 'w', encoding='utf-8', newline='') as f:
        f.write(text)
    return p


# ================================================================ board_guard.py (dependency-free)
d = os.path.join(TMP, 'guard')
os.makedirs(d)
brd = write(os.path.join(d, 'x.kicad_pcb'), '(kicad_pcb (version 20240108) (generator "test"))\n')
pro = write(os.path.join(d, 'x.kicad_pro'), '{}\n')
check('guard: a board with its .kicad_pro and no lock is writable', board_guard.problems(brd) == [], board_guard.problems(brd))
lck = write(os.path.join(d, '~x.kicad_pcb.lck'), '{"hostname": "PC", "username": "celso"}')
p = board_guard.problems(brd)
check('guard: the KiCad 9/10 board lock ~x.kicad_pcb.lck is found (and its owner shown)', len(p) == 1 and 'celso' in p[0], p)
try:
    board_guard.check_board_writable(brd, argv=[])
    ok = False
except SystemExit as e:
    ok = e.code == board_guard.REFUSED
check('guard: check_board_writable raises SystemExit(3) on a lock file', ok)
r = run([sys.executable, os.path.join(SCR, 'board_guard.py'), brd])
check('guard CLI: exit 3 and a clear message on a lock file', r.returncode == 3 and 'lock file' in r.stderr, (r.returncode, r.stderr))
r = run([sys.executable, os.path.join(SCR, 'board_guard.py'), brd, '--force-write'])
check('guard CLI: --force-write overrides', r.returncode == 0, (r.returncode, r.stderr))
os.remove(lck)
write(os.path.join(d, '~x.kicad_pro.lck'), 'x')
check('guard: a project lock ~x.kicad_pro.lck also refuses', len(board_guard.problems(brd)) == 1, board_guard.problems(brd))
check('guard: check_locks=False ignores it (centre_gated without --apply)', board_guard.problems(brd, check_locks=False) == [])
os.remove(os.path.join(d, '~x.kicad_pro.lck'))
write(os.path.join(d, 'x.kicad_pcb.lck'), 'x')
check('guard: the variant without "~" is found too', len(board_guard.problems(brd)) == 1, board_guard.problems(brd))
os.remove(os.path.join(d, 'x.kicad_pcb.lck'))
os.remove(pro)
p = board_guard.problems(brd)
check('guard: a missing .kicad_pro refuses (pcbnew would write default rules)', len(p) == 1 and '.kicad_pro' in p[0], p)
r = run([sys.executable, os.path.join(SCR, 'board_guard.py'), brd])
check('guard CLI: exit 3 on a missing .kicad_pro', r.returncode == 3, (r.returncode, r.stderr))
r = run([sys.executable, os.path.join(SCR, 'board_guard.py'), brd, '--allow-no-pro'])
check('guard CLI: --allow-no-pro skips only the project check', r.returncode == 0, (r.returncode, r.stderr))
write(lck, 'x')
r = run([sys.executable, os.path.join(SCR, 'board_guard.py'), brd, '--allow-no-pro'])
check('guard CLI: --allow-no-pro still refuses a lock', r.returncode == 3, (r.returncode, r.stderr))
os.remove(lck)

# a text-writing script on the system Python refuses before touching the board
sp = os.path.join(TMP, 'stitch')
os.makedirs(sp)
for f in ('two_layer.kicad_pcb', 'two_layer.kicad_pro'):
    shutil.copy2(os.path.join(HERE, 'fixtures_boards', f), os.path.join(sp, f))
sb = os.path.join(sp, 'two_layer.kicad_pcb')
h0 = sha(sb)
write(os.path.join(sp, '~two_layer.kicad_pcb.lck'), 'x')
r = run([sys.executable, os.path.join(SCR, 'stitch_planes.py'), sb])
check('stitch_planes.py refuses (exit 3) while KiCad holds the lock; board byte-identical',
      r.returncode == 3 and sha(sb) == h0 and 'REFUSED' in r.stderr, (r.returncode, r.stderr[-300:]))
os.remove(os.path.join(sp, '~two_layer.kicad_pcb.lck'))

# economical via tier in stitch_planes
import importlib.util  # noqa: E402
spec = importlib.util.spec_from_file_location('stitch_planes_mod', os.path.join(SCR, 'stitch_planes.py'))
SPM = importlib.util.module_from_spec(spec)
spec.loader.exec_module(SPM)
write(os.path.join(sp, 'kicad_golden.project.json'), json.dumps({'fabricator': {'economical_via_drill_mm': 0.2}}))
sizes = SPM.economical_sizes(sb, SPM.VIA_SIZES)
check('stitch_planes: economical tier 0.2 mm drops the 0.25 / 0.15 fallback via', (0.25, 0.15) not in sizes and (0.45, 0.2) in sizes, sizes)
write(os.path.join(sp, 'kicad_golden.project.json'), json.dumps({'fabricator': {'economical_via_drill_mm': 0.2, 'fine_vias_approved': True}}))
check('stitch_planes: fine_vias_approved keeps it', SPM.economical_sizes(sb, SPM.VIA_SIZES) == list(SPM.VIA_SIZES))
os.remove(os.path.join(sp, 'kicad_golden.project.json'))
check('stitch_planes: no parameters = unchanged sizes', SPM.economical_sizes(sb, SPM.VIA_SIZES) == list(SPM.VIA_SIZES))

# ================================================================ apply_settings.js
if NODE:
    AP = os.path.join(SCR, 'apply_settings.js')
    ad = os.path.join(TMP, 'apply')
    os.makedirs(ad)
    mini = {'board': {'design_settings': {'rules': {'min_hole_clearance': 0.2},
                                          'via_dimensions': [{'diameter': 0, 'drill': 0}]}},
            'erc': {}, 'net_settings': {'classes': []}, 'schematic': {}, 'meta': {'filename': 'p.kicad_pro', 'version': 3}}
    pp = os.path.join(ad, 'p.kicad_pro')
    pj = os.path.join(ad, 'kicad_golden.project.json')

    def setup(dev, fab=None):
        write(pp, json.dumps(mini, indent=2))
        par = {'project': 'p', 'approved_rule_deviations': dev}
        if fab:
            par['fabricator'] = fab
        write(pj, json.dumps(par, indent=2))

    def node(*a):
        return run([NODE, AP, pp] + list(a), cwd=os.path.expanduser('~'))

    setup({'_doc': 'x', 'min_hole_clearance': {'value': 0.2, 'reason': 'D110 test'}})
    r = node('--fab', 'jlcpcb', '--layers', '4', '--copper', '1oz', '--no-bom', '--no-erc', '--no-schematic')
    P = json.load(open(pp, encoding='utf-8'))
    R = json.load(open(pj, encoding='utf-8'))
    rules = P['board']['design_settings']['rules']
    vd = ['%g/%g' % (v['diameter'], v['drill']) for v in P['board']['design_settings']['via_dimensions']]
    check('apply_settings keeps the approved deviation min_hole_clearance 0.2 after the JLCPCB 4L profile (0.254)',
          r.returncode == 0 and rules['min_hole_clearance'] == 0.2 and 'kept approved deviation: min_hole_clearance = 0.2' in r.stdout,
          (r.returncode, rules.get('min_hole_clearance'), r.stdout[-400:], r.stderr[-300:]))
    check('apply_settings --fab 4L inserts the economical small via 0.45/0.2, not 0.25/0.15', '0.45/0.2' in vd and '0.25/0.15' not in vd, vd)
    check('apply_settings records fabricator.economical_via_drill_mm 0.2 and fine_vias_approved false',
          R['fabricator'].get('economical_via_drill_mm') == 0.2 and R['fabricator'].get('fine_vias_approved') is False, R.get('fabricator'))
    check('apply_settings keeps the project deviation block', R['approved_rule_deviations']['min_hole_clearance']['value'] == 0.2, R.get('approved_rule_deviations'))

    setup({})
    r = node('--fab', 'jlcpcb', '--layers', '4', '--copper', '1oz', '--no-bom', '--no-erc', '--no-schematic', '--fine-vias')
    P = json.load(open(pp, encoding='utf-8'))
    R = json.load(open(pj, encoding='utf-8'))
    vd = ['%g/%g' % (v['diameter'], v['drill']) for v in P['board']['design_settings']['via_dimensions']]
    check('apply_settings --fine-vias keeps the 0.25/0.15 minimum via and records fine_vias_approved',
          '0.25/0.15' in vd and R['fabricator'].get('fine_vias_approved') is True, (vd, R.get('fabricator', {}).get('fine_vias_approved')))
    check('apply_settings without a deviation: min_hole_clearance follows the profile (0.254)',
          P['board']['design_settings']['rules']['min_hole_clearance'] == 0.254, P['board']['design_settings']['rules'].get('min_hole_clearance'))

    setup({'min_clearance': {'value': 0.05, 'reason': 'too fine'}, 'min_hole_clearance': {'value': 0.2, 'reason': 'ok'}})
    h0 = sha(pp)
    r = node('--fab', 'jlcpcb', '--layers', '4', '--copper', '1oz')
    check('apply_settings refuses a deviation below the profile minimum (min_clearance 0.05 < 0.09): exit 3, nothing written',
          r.returncode == 3 and 'min_clearance = 0.05 < 0.09' in r.stderr and 'min_hole_clearance' not in r.stderr and sha(pp) == h0,
          (r.returncode, r.stderr[-300:]))
    setup({'min_hole_clearance': {'value': 0.2, 'reason': 'D110'}})
    r = node('--fab', 'jlcpcb', '--layers', '2', '--copper', '1oz', '--dry-run')
    check('apply_settings: on 2L (no absolute_min) 0.2 is below the profile 0.254 and is refused', r.returncode == 3, (r.returncode, r.stderr[-300:]))

    fab = {'name': 'JLCPCB 4-layer 1oz', 'profile': '4L-1oz', 'layers': 4, 'copper': '1oz',
           'kicad_rules': {'min_hole_clearance': 0.254, 'min_clearance': 0.09}}
    setup({'min_hole_clearance': {'value': 0.2, 'reason': 'D110'}}, fab=fab)
    h0 = sha(pj)
    r = node('--no-bom', '--no-erc', '--no-schematic')
    P = json.load(open(pp, encoding='utf-8'))
    check('apply_settings without --fab: the recorded fabricator block is left untouched (params byte-identical)',
          r.returncode == 0 and sha(pj) == h0 and 'left untouched' in r.stdout, (r.returncode, r.stdout[-300:], r.stderr[-300:]))
    check('... and the deviation is put back over the template value', P['board']['design_settings']['rules']['min_hole_clearance'] == 0.2,
          P['board']['design_settings']['rules'].get('min_hole_clearance'))
    setup({'min_hole_clearance': {'value': 0.1, 'reason': 'too fine'}}, fab=fab)
    r = node('--dry-run')
    check('... and a deviation below the recorded profile absolute minimum (0.1 < 0.2) is refused', r.returncode == 3, (r.returncode, r.stderr[-300:]))
    shutil.rmtree(ad, ignore_errors=True)

    tpl = json.load(open(os.path.join(HERE, '..', 'templates', 'kicad_golden.project.json'), encoding='utf-8'))
    check('template carries approved_rule_deviations with only a _doc',
          set(tpl.get('approved_rule_deviations', {'x': 1})) == {'_doc'}, tpl.get('approved_rule_deviations'))
    fj = json.load(open(os.path.join(HERE, '..', 'fabricators', 'jlcpcb.json'), encoding='utf-8'))
    check('jlcpcb.json: economical_via_drill_mm 0.2 on every 4L/6L profile, omitted on 2L',
          all(fj['profiles'][k].get('economical_via_drill_mm') == 0.2 for k in fj['profiles'] if k[0] in '46')
          and all('economical_via_drill_mm' not in fj['profiles'][k] for k in fj['profiles'] if k[0] == '2'))
else:
    print('SKIP  apply_settings: node not found')

# ================================================================ finish_gated.py argument parsing
r = run([sys.executable, os.path.join(SCR, 'finish_gated.py'), '--help'])
check('finish_gated --help exits 0 and documents --no-layout-gate', r.returncode == 0 and '--no-layout-gate' in r.stdout, (r.returncode, r.stderr[-200:]))
fd = os.path.join(TMP, 'fg_parse')
os.makedirs(fd)
fb = write(os.path.join(fd, 'f.kicad_pcb'), '(kicad_pcb)\n')
write(os.path.join(fd, 'f.kicad_pro'), '{}\n')
write(os.path.join(fd, '~f.kicad_pcb.lck'), 'x')
if KP and CLI:
    r = run([sys.executable, os.path.join(SCR, 'finish_gated.py'), fb, '--no-layout-gate', '--default-width', '0.2'], timeout=120)
    check('finish_gated parses --no-layout-gate and refuses a locked board before any work (exit 3)',
          r.returncode == 3 and 'REFUSED' in r.stderr and not os.path.exists(fb + '.bak_prefinish'), (r.returncode, r.stderr[-300:]))
else:
    print('SKIP  finish_gated lock refusal: KiCad python / kicad-cli not found')

# ================================================================ pcbnew parts (KiCad's Python)
BUILD = r'''
import sys, pcbnew
FM = lambda v: pcbnew.FromMM(float(v)); V = lambda x, y: pcbnew.VECTOR2I(FM(x), FM(y))
def board(w=30, h=20, layers=4):
    # NewBoard, not BOARD(): on Linux SaveBoard writes the .kicad_pro only for a board created with a project
    b = pcbnew.NewBoard(sys.argv[1]); b.SetCopperLayerCount(layers)
    s = pcbnew.PCB_SHAPE(b); s.SetShape(pcbnew.SHAPE_T_POLY); s.SetLayer(pcbnew.Edge_Cuts); s.SetWidth(FM(0.05))
    s.SetPolyPoints([V(0, 0), V(w, 0), V(w, h), V(0, h)]); b.Add(s); return b
def net(b, name):
    n = b.FindNet(name)
    if n is None:
        n = pcbnew.NETINFO_ITEM(b, name); b.Add(n)
    return n
def part(b, ref, x, y, pads):
    f = pcbnew.FOOTPRINT(b); f.SetReference(ref); f.SetValue(ref); f.SetPosition(V(x, y)); b.Add(f)
    for num, dx, dy, w, h, nn in pads:
        p = pcbnew.PAD(f); p.SetNumber(num); p.SetShape(pcbnew.PAD_SHAPE_RECT); p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetLayerSet(pcbnew.PAD.SMDMask()); p.SetSize(V(w, h)); p.SetPosition(V(x + dx, y + dy))
        if nn: p.SetNet(net(b, nn))
        f.Add(p)
def plane(b, nn, layer, w=30, h=20):
    z = pcbnew.ZONE(b); z.SetLayer(layer); z.SetNet(net(b, nn))
    sp = pcbnew.SHAPE_POLY_SET(); sp.NewOutline()
    for x, y in ((0.5, 0.5), (w - 0.5, 0.5), (w - 0.5, h - 0.5), (0.5, h - 0.5)): sp.Append(FM(x), FM(y))
    z.Outline().Append(sp); b.Add(z)
def track(b, nn, pts, w=0.2, layer=pcbnew.F_Cu):
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        t = pcbnew.PCB_TRACK(b); t.SetStart(V(x1, y1)); t.SetEnd(V(x2, y2)); t.SetWidth(FM(w)); t.SetLayer(layer)
        t.SetNet(net(b, nn)); b.Add(t)
def via(b, nn, x, y):
    v = pcbnew.PCB_VIA(b); v.SetPosition(V(x, y)); v.SetWidth(FM(0.45)); v.SetDrill(FM(0.2)); v.SetNet(net(b, nn))
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); b.Add(v)
def fill(b):
    zs = pcbnew.ZONES()
    for i in range(b.GetAreaCount()): zs.append(b.GetArea(i))
    pcbnew.ZONE_FILLER(b).Fill(zs)
'''


def kicad(code, *argv):
    f = os.path.join(TMP, 'kc_%d.py' % (abs(hash(code)) % 10 ** 8))
    write(f, BUILD + code)
    return run([KP, f] + list(argv))


if KP:
    zd = os.path.join(TMP, 'zone')
    os.makedirs(zd)
    zb = os.path.join(zd, 'z.kicad_pcb')
    r = kicad(r'''
b = board(); plane(b, 'GND', pcbnew.In1_Cu)
part(b, 'J1', 5, 10, [('1', 0, 0, 1, 1, 'SIG')]); part(b, 'J2', 25, 10, [('1', 0, 0, 1, 1, 'SIG')])
part(b, 'K1', 5, 15, [('1', 0, 0, 1, 1, 'R')]); part(b, 'K2', 25, 15, [('1', 0, 0, 1, 1, 'R')])
via(b, 'SIG', 15, 10); track(b, 'SIG', [(5, 10), (15, 10)]); track(b, 'SIG', [(15, 10), (25, 10)], layer=pcbnew.B_Cu)
pcbnew.SaveBoard(sys.argv[1], b)
''', zb)
    check('fixture: synthetic 4-layer board with a GND plane saved with its .kicad_pro',
          r.returncode == 0 and os.path.exists(os.path.join(zd, 'z.kicad_pro')), r.stderr[-300:])
    ZF = os.path.join(SCR, 'zone_fill_check.py')
    r = run([KP, ZF, zb])
    check('zone_fill_check: a board saved with an unfilled zone is STALE (exit 1)', r.returncode == 1, (r.returncode, r.stdout[-300:]))
    run([KP, ZF, zb, '--fix'])
    r = run([KP, ZF, zb])
    check('zone_fill_check: a freshly filled board is current (exit 0)', r.returncode == 0 and '0 stale' in r.stdout, (r.returncode, r.stdout[-300:]))
    r = kicad(r'''
b = pcbnew.LoadBoard(sys.argv[1])
v = [t for t in b.GetTracks() if t.GetClass() == 'PCB_VIA'][0]
old = v.GetPosition(); new = old + V(0, 1)
for t in [t for t in b.GetTracks() if t.GetClass() == 'PCB_TRACK']:      # the via and its track ends move together
    if t.GetStart() == old: t.SetStart(new)
    if t.GetEnd() == old: t.SetEnd(new)
v.SetPosition(new); b.Save(sys.argv[1])
''', zb)
    r = run([KP, ZF, zb, '--json', os.path.join(zd, 'zf.json')])
    rows = json.load(open(os.path.join(zd, 'zf.json'), encoding='utf-8'))['zones'] if os.path.exists(os.path.join(zd, 'zf.json')) else []
    check('zone_fill_check: a via moved without refilling is a STALE fill (exit 1), same area, XOR > 0',
          r.returncode == 1 and 'STALE' in r.stdout and rows and rows[0]['stale'] and abs(rows[0]['saved_mm2'] - rows[0]['fresh_mm2']) < 0.01,
          (r.returncode, r.stdout[-300:], rows))
    write(os.path.join(zd, '~z.kicad_pcb.lck'), 'x')
    h0 = sha(zb)
    r = run([KP, ZF, zb, '--fix'])
    check('zone_fill_check --fix goes through board_guard (refuses on a lock, board untouched)', r.returncode == 3 and sha(zb) == h0, (r.returncode, r.stderr[-200:]))
    os.remove(os.path.join(zd, '~z.kicad_pcb.lck'))
    r = run([KP, ZF, zb, '--fix'])
    r2 = run([KP, ZF, zb])
    check('zone_fill_check --fix refills and saves; the check is clean afterwards',
          r.returncode == 0 and 'refilled and saved' in r.stdout and r2.returncode == 0, (r.stdout[-200:], r2.stdout[-200:]))

    # stitch_planes.py (system Python, text writer): --dry-run runs under a lock; a real write refills the zones
    sd = os.path.join(TMP, 'stitchz')
    os.makedirs(sd)
    sz = os.path.join(sd, 's.kicad_pcb')
    kicad(r'''
b = board(); plane(b, 'GND', pcbnew.In1_Cu)
part(b, 'C1', 15, 10, [('1', -0.8, 0, 0.9, 1.0, 'GND'), ('2', 0.8, 0, 0.9, 1.0, 'SIG')])
pcbnew.SaveBoard(sys.argv[1], b)
''', sz)
    run([KP, ZF, sz, '--fix'])
    write(os.path.join(sd, '~s.kicad_pcb.lck'), 'x')
    r = run([sys.executable, os.path.join(SCR, 'stitch_planes.py'), sz, '--dry-run'])
    check('stitch_planes.py --dry-run still runs under a lock (it writes nothing)', r.returncode == 0 and 'placed' in r.stdout,
          (r.returncode, r.stdout[-200:], r.stderr[-300:]))
    os.remove(os.path.join(sd, '~s.kicad_pcb.lck'))
    r = run([sys.executable, os.path.join(SCR, 'stitch_planes.py'), sz])
    r2 = run([KP, ZF, sz])
    check('stitch_planes.py places a plane via and refills the zones in the saved board (zone_fill_check exit 0)',
          r.returncode == 0 and 'zone refill:' in r.stdout and r2.returncode == 0, (r.stdout[-400:], r.stderr[-200:], r2.stdout[-200:]))

    # route_finish.py saves a current fill (it refills before saving)
    r = run([KP, os.path.join(SCR, 'route_finish.py'), zb, '--net', 'R', '--from-pad', 'K1.1', '--to-pad', 'K2.1',
             '--grid', '0.1', '--safety', '0.1', '--via-cost', '5'])
    r2 = run([KP, ZF, zb])
    check('route_finish.py: the saved fill is current after the route (zone_fill_check exit 0)',
          r.returncode == 0 and r2.returncode == 0, (r.returncode, r.stdout[-200:], r.stderr[-200:], r2.stdout[-200:]))
    # route_finish.py refuses without the .kicad_pro beside the board
    nb = os.path.join(TMP, 'nopro')
    os.makedirs(nb)
    shutil.copy2(zb, os.path.join(nb, 'z.kicad_pcb'))
    h0 = sha(os.path.join(nb, 'z.kicad_pcb'))
    r = run([KP, os.path.join(SCR, 'route_finish.py'), os.path.join(nb, 'z.kicad_pcb'), '--net', 'R', '--from-pad', 'K1.1',
             '--to-pad', 'K2.1'])
    check('route_finish.py refuses a board copied without its .kicad_pro (exit 3, no .kicad_pro created, board untouched)',
          r.returncode == 3 and not os.path.exists(os.path.join(nb, 'z.kicad_pro')) and sha(os.path.join(nb, 'z.kicad_pcb')) == h0,
          (r.returncode, r.stderr[-300:], os.listdir(nb)))
    r = run([KP, os.path.join(SCR, 'export_keepouts.py'), os.path.join(nb, 'z.kicad_pcb'), '--export-copy', '--edge-band', '0.55'])
    check('export_keepouts.py refuses an export copy without its .kicad_pro', r.returncode == 3, (r.returncode, r.stderr[-200:]))
    r = run([KP, os.path.join(SCR, 'export_keepouts.py'), os.path.join(nb, 'z.kicad_pcb'), '--export-copy', '--edge-band', '0.55',
             '--allow-no-pro'])
    check('export_keepouts.py --allow-no-pro skips only that check', r.returncode == 0, (r.returncode, r.stderr[-200:]))

    # ------------------------------------------------------------ finish_gated layout gate
    if CLI:
        def gate_board(tag):
            gd = os.path.join(TMP, 'gate_' + tag)
            os.makedirs(gd)
            gb = os.path.join(gd, 'g.kicad_pcb')
            kicad(r'''
b = board(30, 20, layers=2)
part(b, 'A1', 5, 10, [('1', 0, 0, 0.8, 0.9, 'A')]); part(b, 'A2', 25, 10, [('1', 0, 0, 0.8, 0.9, 'A')])
part(b, 'B1', 8, 10.7, [('1', 0, 0, 0.4, 0.4, 'B')]); part(b, 'B2', 22, 10.7, [('1', 0, 0, 0.4, 0.4, 'B')])
track(b, 'B', [(8, 10.7), (22, 10.7)])
pcbnew.SaveBoard(sys.argv[1], b)
''', gb)
            # A is not routed yet: the separation check PASSes at the start (no A copper), so it is gated
            write(os.path.join(gd, 'kicad_golden.project.json'), json.dumps(
                {'layout_checks': {'kelvin': [], 'decoupling': [], 'separation': [{'a': ['A'], 'b': ['B'], 'min_mm': 1.0}]}}))
            return gb

        gb = gate_board('on')
        r = run([sys.executable, os.path.join(SCR, 'finish_gated.py'), gb])
        m = re.search(r'end: unconnected (\d+)', r.stdout)
        check('finish_gated layout gate: a DRC-clean route that breaks a passing layout check is REVERTED',
              'REVERTED (layout check separation A|B broke)' in r.stdout and m and m.group(1) == '1', r.stdout[-700:] + r.stderr[-300:])
        gb = gate_board('off')
        r = run([sys.executable, os.path.join(SCR, 'finish_gated.py'), gb, '--no-layout-gate'])
        m = re.search(r'end: unconnected (\d+)', r.stdout)
        check('finish_gated --no-layout-gate keeps the same route', 'layout gate: off' in r.stdout and m and m.group(1) == '0',
              r.stdout[-500:] + r.stderr[-300:])
    else:
        print('SKIP  finish_gated layout gate: kicad-cli not found')
else:
    print('SKIP  pcbnew parts: KiCad python not found')

shutil.rmtree(TMP, ignore_errors=True)
print('\n%d/%d assertions passed' % (PASS, PASS + FAIL))
sys.exit(1 if FAIL else 0)
