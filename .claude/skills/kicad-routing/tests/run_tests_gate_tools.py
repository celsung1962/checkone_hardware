#!/usr/bin/env python
"""run_tests_gate_tools.py - self-test for the 1.28.0 finishing tools (ServiceOne rev. 0.2 lessons L30-L44).

Run with KiCad's own Python (the pcbnew parts are skipped under another interpreter). Boards are built through the
pcbnew API and saved, so every fixture is a real KiCad 10 file. Covers:
  stop_rule.py          keep rate, projected time, budget, argv options (L30)
  locks.py              locked tracks and vias read from the file; moved / unlocked items reported (L39, L40)
  edit_tracks.py        exact delete / add; refuses to delete a locked item without --allow-locked
  dedupe_copper.py      a segment inside another is removed; a locked one is kept
  via_relocate.py       web: a via slides along its stub to the mask web; axis: a plane via goes onto the pad axis;
                        locked vias are skipped (L15, L38, L40)
  open_ends.py          copper ends of an open connection (needs kicad-cli) (L31)
  dangling_classify.py  lead-in kept, unused stub removed (needs kicad-cli) (L33)
  gate_each.py / stage_gate.py   usage errors (their gating is exercised on real boards: reference 11, section 9)

    "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" tests/run_tests_gate_tools.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCR = os.path.join(HERE, '..', 'scripts')
sys.path.insert(0, SCR)
import kicad_sexp as KS  # noqa: E402
import locks  # noqa: E402
import stop_rule  # noqa: E402

PASS = FAIL = 0
TMP = tempfile.mkdtemp(prefix='kr_gate_')


def check(label, cond, detail=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print('PASS  %s%s' % (label, ('  - ' + str(detail)[:200]) if detail else ''))
    else:
        FAIL += 1
        print('FAIL  %s  - %s' % (label, str(detail)[:400]))


def run(script, *args):
    return subprocess.run([sys.executable, os.path.join(SCR, script)] + list(args), capture_output=True, text=True,
                          env=dict(os.environ, MSYS_NO_PATHCONV='1'))


# ---------------------------------------------------------------- stop rule (pure python)
now = [0.0]
clock = lambda: now[0] * 60.0
r = stop_rule.StopRule(budget_min=60, clock=clock)
for _ in range(9):
    r.attempt(False)
check('stop rule: no verdict before 10 attempts or 30 min', r.should_stop(50) is None)
r.attempt(False)
check('stop rule: 0 of 10 kept -> stop on the keep rate', 'keep rate' in (r.should_stop(50) or ''), r.should_stop(50))
r = stop_rule.StopRule(budget_min=60, clock=clock)
for i in range(10):
    r.attempt(i % 2 == 0)
now[0] = 10.0
check('stop rule: 5 of 10 kept, 20 min projected -> go on', r.should_stop(10) is None)
check('stop rule: 110 min projected -> stop', 'projected' in (r.should_stop(100) or ''))
now[0] = 61.0
check('stop rule: budget spent -> stop', 'budget' in (r.should_stop(0) or ''))
check('stop rule: --no-stop-rule disables it, --budget / --min-keep-rate are read',
      stop_rule.StopRule.from_argv(['b', '--no-stop-rule']) is None and
      stop_rule.StopRule.from_argv(['b', '--budget', '15', '--min-keep-rate', '0.5']).budget == 15)
check('stop rule: the estimate warns when over budget', 'over budget' in stop_rule.StopRule(budget_min=10).estimate(40, 1, 0.5))

r = run('gate_each.py', 'x.kicad_pcb', '--count', '3')
check('gate_each.py: no tool after "--" -> usage, exit 2', r.returncode == 2 and 'Usage' in r.stdout, r.returncode)
r = run('stage_gate.py', 'snap')
check('stage_gate.py: too few arguments -> usage, exit 2', r.returncode == 2, r.returncode)

try:
    import pcbnew
except ImportError:
    print('SKIP  pcbnew parts: run this suite with KiCad\'s Python')
    print('\n%d/%d assertions passed' % (PASS, PASS + FAIL))
    sys.exit(1 if FAIL else 0)

FM = lambda v: pcbnew.FromMM(float(v))
MM = pcbnew.ToMM
V = lambda x, y: pcbnew.VECTOR2I(FM(x), FM(y))
CLI = KS.find_kicad_cli()


def board(w=30, h=20):
    b = pcbnew.BOARD()
    b.SetCopperLayerCount(4)
    s = pcbnew.PCB_SHAPE(b); s.SetShape(pcbnew.SHAPE_T_POLY); s.SetLayer(pcbnew.Edge_Cuts); s.SetWidth(FM(0.05))
    s.SetPolyPoints([V(0, 0), V(w, 0), V(w, h), V(0, h)]); b.Add(s)
    return b


def net(b, name):
    n = b.FindNet(name)
    if n is None:
        n = pcbnew.NETINFO_ITEM(b, name); b.Add(n)
    return n


def part(b, ref, x, y, pads):
    f = pcbnew.FOOTPRINT(b); f.SetReference(ref); f.SetValue(ref); f.SetPosition(V(x, y))
    b.Add(f)
    for num, dx, dy, w, h, nn in pads:
        p = pcbnew.PAD(f); p.SetNumber(num); p.SetShape(pcbnew.PAD_SHAPE_RECT); p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetLayerSet(pcbnew.PAD.SMDMask()); p.SetSize(V(w, h)); p.SetPosition(V(x + dx, y + dy))
        p.SetNet(net(b, nn)); f.Add(p)
    return f


def plane(b, nn, w=30, h=20):
    z = pcbnew.ZONE(b); z.SetLayer(pcbnew.In1_Cu); z.SetNet(net(b, nn))
    sp = pcbnew.SHAPE_POLY_SET(); sp.NewOutline()
    for x, y in ((0.5, 0.5), (w - 0.5, 0.5), (w - 0.5, h - 0.5), (0.5, h - 0.5)):
        sp.Append(FM(x), FM(y))
    z.Outline().Append(sp); b.Add(z)


def track(b, nn, pts, w=0.2, locked=False):
    out = []
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        t = pcbnew.PCB_TRACK(b); t.SetStart(V(x1, y1)); t.SetEnd(V(x2, y2)); t.SetWidth(FM(w))
        t.SetLayer(pcbnew.F_Cu); t.SetNet(net(b, nn)); t.SetLocked(locked); b.Add(t); out.append(t)
    return out


def via(b, nn, x, y, locked=False):
    v = pcbnew.PCB_VIA(b); v.SetPosition(V(x, y)); v.SetWidth(pcbnew.F_Cu, FM(0.45)); v.SetDrill(FM(0.2))
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); v.SetNet(net(b, nn)); v.SetLocked(locked); b.Add(v)
    return v


def save(b, name):
    d = os.path.join(TMP, os.path.splitext(name)[0])
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, name)
    pcbnew.SaveBoard(p, b)
    with open(os.path.splitext(p)[0] + '.kicad_pro', 'w') as f:      # board_guard: the project travels with the board
        f.write('{}')
    return p


def tracks_of(path, nn):
    return [t for t in pcbnew.LoadBoard(path).GetTracks() if t.GetNetname() == nn]


# ---------------------------------------------------------------- locks.py on a real KiCad 10 file
b = board()
track(b, 'GND', [(2, 2), (8, 2)], locked=True)
via(b, 'GND', 8, 2, locked=True)
track(b, 'SIG', [(2, 6), (8, 6)])
p = save(b, 'locks.kicad_pcb')
fp0 = locks.fingerprint(p)
check('locks: the locked segment and via are read, the unlocked one is not', len(fp0) == 2 and
      sorted(k for k, _, _ in fp0.values()) == ['segment', 'via'], fp0)
b2 = pcbnew.LoadBoard(p)
for t in b2.GetTracks():
    if t.IsLocked() and t.GetClass() == 'PCB_VIA':
        t.SetPosition(V(8.5, 2))
p2 = os.path.join(os.path.dirname(p), 'moved.kicad_pcb'); pcbnew.SaveBoard(p2, b2)
msgs = locks.changed(fp0, locks.fingerprint(p2))
check('locks: a moved locked via is reported', len(msgs) == 1 and 'via' in msgs[0] and 'moved' in msgs[0], msgs)
b3 = pcbnew.LoadBoard(p)
for t in b3.GetTracks():
    t.SetLocked(False)
p3 = os.path.join(os.path.dirname(p), 'unlocked.kicad_pcb'); pcbnew.SaveBoard(p3, b3)
check('locks: unlocking is reported as well', len(locks.changed(fp0, locks.fingerprint(p3))) == 2)
check('locks: an unchanged board reports nothing', locks.changed(fp0, locks.fingerprint(p)) == [])
rr = run('locks.py', p, '--compare', p2)
check('locks.py --compare: exit 1 on a moved item', rr.returncode == 1 and 'moved' in rr.stdout, rr.stdout)

# ---------------------------------------------------------------- edit_tracks.py
spec = os.path.join(TMP, 'spec.json')
json.dump([{'net': 'SIG', 'layer': 'F.Cu', 'width': 0.2, 'delete': [[8, 6, 2, 6]], 'add': [[2, 6, 5, 6], [5, 6, 8, 6, 0.3]]}],
          open(spec, 'w'))
pe = save(b, 'edit.kicad_pcb')
rr = run('edit_tracks.py', pe, spec)
ts = sorted((round(MM(t.GetStart().x), 3), round(MM(t.GetWidth()), 3)) for t in tracks_of(pe, 'SIG'))
check('edit_tracks: the segment matched in reverse order is deleted, two added (one with its own width)',
      rr.returncode == 0 and ts == [(2.0, 0.2), (5.0, 0.3)], (rr.stdout + rr.stderr)[-200:] + str(ts))
json.dump({'net': 'GND', 'layer': 'F.Cu', 'delete': [[2, 2, 8, 2]]}, open(spec, 'w'))
rr = run('edit_tracks.py', pe, spec)
check('edit_tracks: deleting a locked segment is refused', rr.returncode != 0 and 'locked' in (rr.stdout + rr.stderr)
      and len(tracks_of(pe, 'GND')) == 2, (rr.stdout + rr.stderr)[-200:])
rr = run('edit_tracks.py', pe, spec, '--allow-locked')
check('edit_tracks: --allow-locked deletes it', rr.returncode == 0 and len(tracks_of(pe, 'GND')) == 1, rr.stdout[-120:])
json.dump({'net': 'SIG', 'layer': 'F.Cu', 'delete': [[0, 0, 1, 1]]}, open(spec, 'w'))
rr = run('edit_tracks.py', pe, spec)
check('edit_tracks: a missing match aborts', rr.returncode != 0 and 'ABORT: 0 matches' in (rr.stdout + rr.stderr))

# ---------------------------------------------------------------- dedupe_copper.py
b = board()
track(b, 'A', [(2, 2), (12, 2)])
track(b, 'A', [(4, 2), (7, 2)])
track(b, 'B', [(2, 5), (12, 5)])
track(b, 'B', [(4, 5), (7, 5)], locked=True)
pd = save(b, 'dedupe.kicad_pcb')
rr = run('dedupe_copper.py', pd)
check('dedupe_copper: one duplicate found (the locked one is kept)', 'duplicates 1' in rr.stdout and ' A ' in rr.stdout.replace('  ', ' '), rr.stdout)
rr = run('dedupe_copper.py', pd, '--apply')
check('dedupe_copper --apply: the inner segment is removed, the long one stays', len(tracks_of(pd, 'A')) == 1 and
      round(MM(tracks_of(pd, 'A')[0].GetLength()), 3) == 10.0 and len(tracks_of(pd, 'B')) == 2, rr.stdout[-200:])

# ---------------------------------------------------------------- via_relocate.py
b = board()
plane(b, 'GND')
part(b, 'R1', 10, 10, [('1', 0, 0, 1.0, 1.0, 'GND')])
track(b, 'GND', [(10, 10), (10.75, 10)])
via(b, 'GND', 10.75, 10)
part(b, 'R2', 20, 10, [('1', 0, 0, 1.0, 0.6, 'GND')])
track(b, 'GND', [(20, 10), (20.6, 10.6)])
via(b, 'GND', 20.6, 10.6)
part(b, 'R3', 10, 15, [('1', 0, 0, 1.0, 1.0, 'GND')])
track(b, 'GND', [(10, 15), (10.75, 15)])
via(b, 'GND', 10.75, 15, locked=True)
pv = save(b, 'via.kicad_pcb')
aud = os.path.join(TMP, 'via_audit.json')
json.dump({'findings': [
    {'level': 'FAIL', 'check': 'via', 'msg': 'via GND 0.45/0.2 @ 10.75,10: ring 0.025 mm from SMD pad R1-1 (needs 0.15 mm)'},
    {'level': 'FAIL', 'check': 'via', 'msg': 'via GND 0.45/0.2 @ 10.75,15: ring 0.025 mm from SMD pad R3-1 (needs 0.15 mm)'},
    {'level': 'FAIL', 'check': 'pad-entry', 'msg': 'GND enters pad R2-1 off its axis @ 20,10 (F.Cu)'}]}, open(aud, 'w'))
rr = run('via_relocate.py', pv, aud, '--mode', 'web', '--apply')
vs = {(round(MM(v.GetPosition().x), 3), round(MM(v.GetPosition().y), 3)) for v in pcbnew.LoadBoard(pv).GetTracks()
      if v.GetClass() == 'PCB_VIA'}
moved = [x for x, y in vs if y == 10 and x < 15]
check('via_relocate web: the via slides along its stub to >= 0.16 mm mask web (x >= 10.885)',
      moved and moved[0] >= 10.885 - 1e-6 and moved[0] <= 11.0, (rr.stdout[-300:], vs))
check('via_relocate web: the locked via is skipped', (10.75, 15.0) in vs and 'locked' in rr.stdout, rr.stdout[-300:])
rr = run('via_relocate.py', pv, aud, '--mode', 'axis', '--apply')
bb = pcbnew.LoadBoard(pv)
v2 = [(round(MM(v.GetPosition().x), 3), round(MM(v.GetPosition().y), 3)) for v in bb.GetTracks()
      if v.GetClass() == 'PCB_VIA' and MM(v.GetPosition().x) > 15]
st = [t for t in bb.GetTracks() if t.GetClass() == 'PCB_TRACK' and MM(t.GetStart().x) > 15]
check('via_relocate axis: the via goes onto the long pad axis past the stub zone (y 10, |dx| >= 0.5 + 0.55 + 0.225)',
      len(v2) == 1 and v2[0][1] == 10.0 and abs(v2[0][0] - 20) >= 1.275 - 1e-6, (rr.stdout[-300:], v2))
check('via_relocate axis: the new stub runs straight from the pad centre, no wider than the pad',
      len(st) == 1 and round(MM(st[0].GetStart().y), 3) == 10.0 and round(MM(st[0].GetEnd().y), 3) == 10.0
      and MM(st[0].GetWidth()) <= 0.6 + 1e-6, [(MM(t.GetStart().x), MM(t.GetStart().y), MM(t.GetEnd().x), MM(t.GetEnd().y)) for t in st])

# ---------------------------------------------------------------- open_ends.py + dangling_classify.py (kicad-cli)
if not CLI:
    print('SKIP  open_ends / dangling_classify: kicad-cli not found')
else:
    b = board()
    part(b, 'R5', 5, 5, [('1', 0, 0, 1.0, 1.0, 'SIG'), ('2', 15, 0, 1.0, 1.0, 'SIG')])
    track(b, 'SIG', [(5, 5), (9, 5)])                         # lead-in: its free end continues the open connection
    part(b, 'R6', 5, 12, [('1', 0, 0, 1.0, 1.0, 'OTHER'), ('2', 10, 0, 1.0, 1.0, 'OTHER')])
    track(b, 'OTHER', [(5, 12), (15, 12)])                    # complete
    track(b, 'OTHER', [(10, 12), (10, 15)])                   # unused stub off the complete run
    po = save(b, 'ends.kicad_pcb')
    drcj, endj, stj = (os.path.join(TMP, n) for n in ('drc.json', 'ends.json', 'stubs.json'))
    subprocess.run([CLI, 'pcb', 'drc', '--severity-all', '--format', 'json', '-o', drcj, po], capture_output=True)
    rr = run('open_ends.py', po, drcj, endj)
    ends = json.load(open(endj)) if os.path.exists(endj) else []
    sig = [e for e in ends if e['net'] == 'SIG' and e['pairs']]
    check('open_ends: the SIG connection is routed from the free track end (9,5) to pad R5.2',
          sig and {sig[0]['pairs'][0]['a']['kind'], sig[0]['pairs'][0]['b']['kind']} == {'free', 'pad'}
          and [9.0, 5.0] in (sig[0]['pairs'][0]['a']['xy'], sig[0]['pairs'][0]['b']['xy']), (rr.stdout + rr.stderr)[-300:])
    rr = run('dangling_classify.py', po, endj, drcj, stj, '--apply')
    st = json.load(open(stj)) if os.path.exists(stj) else {}
    check('dangling_classify: the lead-in is kept, the unused stub is removed',
          len(st.get('kept', [])) == 1 and st['kept'][0]['net'] == 'SIG' and len(st.get('removed', [])) == 1
          and st['removed'][0]['net'] == 'OTHER' and len(tracks_of(po, 'OTHER')) == 1 and len(tracks_of(po, 'SIG')) == 1,
          (rr.stdout + rr.stderr)[-300:])

shutil.rmtree(TMP, ignore_errors=True)
print('\n%d/%d assertions passed' % (PASS, PASS + FAIL))
sys.exit(1 if FAIL else 0)
