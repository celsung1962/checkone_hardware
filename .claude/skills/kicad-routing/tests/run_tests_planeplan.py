#!/usr/bin/env python
"""run_tests_planeplan.py - self-test for plane_plan.py (lesson L23, 1.21.0).

Runs on the system Python and drives plane_plan.py through KiCad's Python (KICAD_PYTHON, then the usual install
paths); skipped when it is absent. Fixture: tests/fixtures/planeplan.kicad_pcb (4 layers, In1 GND, In2 +3.3V), reduced
to the two main planes and copied with an empty .kicad_pro so board_guard accepts it.

  map     refuses a never_split layer (In1 GND); on In2 proposes PP_P24V_1 serving R60.1 / R60.2, gap 0.5 mm for
          24 V, and writes .json / .md / .png
  apply   writes the zone named after the island on In2, net +24V, priority above the main plane, clearance 0.5;
          a second run replaces it (one zone, not two)
  check   FAIL when no via of +24V reaches the island (empty or isolated fill); 0 FAIL once a +24V via is inside;
          FAIL when a strip island across the board splits the main plane in two
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
TMP = tempfile.mkdtemp(prefix='kr_planeplan_')
KP = KS.find_kicad_python()
PP = os.path.join(SCR, 'plane_plan.py')


def ok(cond, name, extra=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print('  ok   ' + name)
    else:
        FAIL += 1
        print('  FAIL ' + name + (('\n       ' + extra[-1500:]) if extra else ''))


def run(*a):
    r = subprocess.run([KP, PP] + list(a), capture_output=True, text=True, encoding='utf-8', errors='replace')
    out = '\n'.join(l for l in (r.stdout + r.stderr).splitlines() if 'image handler' not in l)
    return r.returncode, out


def kpy(code):
    r = subprocess.run([KP, '-c', code], capture_output=True, text=True, encoding='utf-8', errors='replace')
    if r.returncode:
        raise SystemExit(r.stdout + r.stderr)
    return r.stdout


def board(name):
    d = os.path.join(TMP, name)
    os.makedirs(d)
    pcb = os.path.join(d, 'pp.kicad_pcb')
    shutil.copy(os.path.join(HERE, 'fixtures', 'planeplan.kicad_pcb'), pcb)
    open(os.path.join(d, 'pp.kicad_pro'), 'w').write('{}\n')
    kpy('import pcbnew\nb = pcbnew.LoadBoard(%r)\n'
        'for z in [z for z in b.Zones() if z.GetNetname() not in ("GND", "+3.3V")]: b.Remove(z)\n'
        'b.Save(%r)\n' % (pcb, pcb))
    return d, pcb


def params(d, islands):
    json.dump({'plane_plan': {'main_planes': {'In1.Cu': 'GND', 'In2.Cu': '+3.3V'}, 'never_split': ['GND'],
                              'min_neck_mm': 1.0, 'islands': islands}},
              open(os.path.join(d, 'kicad_golden.project.json'), 'w'), indent=1)


def add_via(pcb, x, y, net='+24V'):
    kpy('import pcbnew\nb = pcbnew.LoadBoard(%r)\nv = pcbnew.PCB_VIA(b)\n'
        'v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(%s), pcbnew.FromMM(%s)))\nv.SetWidth(pcbnew.FromMM(0.45))\n'
        'v.SetDrill(pcbnew.FromMM(0.2))\nb.Add(v)\nv.SetNetCode(b.FindNet(%r).GetNetCode())\n'
        'assert v.GetNetname() == %r, v.GetNetname()\nb.Save(%r)\n' % (pcb, x, y, net, net, pcb))


def main():
    if not KP:
        print('KiCad Python not found - plane_plan tests skipped')
        return 0
    print('plane_plan.py')
    d, pcb = board('map')
    params(d, [])
    rc, out = run('map', pcb, '--layer', 'In1.Cu')
    ok(rc != 0 and 'never_split' in out, 'map refuses the never_split GND layer', out)
    rc, out = run('map', pcb, '--layer', 'In2.Cu', '--rails', '+24V', '--min-pads', '2', '--out', os.path.join(d, 'o'))
    ok(rc == 0, 'map In2 runs', out)
    j = json.load(open(os.path.join(d, 'o', 'plane_plan_In2_Cu.json')))
    c = (j['islands'] or [{}])[0]
    ok(j['main_plane'] == '+3.3V' and c.get('name') == 'PP_P24V_1' and
       sorted(c.get('pads_served', [])) == ['R60.1', 'R60.2'], 'map proposes PP_P24V_1 serving R60.1/R60.2',
       json.dumps(j)[:600])
    ok(c.get('gap_mm') == 0.5 and c.get('voltage_v') == 24.0, 'map: 24 V -> gap 0.5 mm', str(c.get('gap_mm')))
    ok(c.get('pads_without_own_via') == ['R60.1', 'R60.2'], 'map: both pads still need their own via')
    ok(all(os.path.isfile(os.path.join(d, 'o', 'plane_plan_In2_Cu.' + e)) for e in ('md', 'png')),
       'map writes the .md table and the .png')

    d, pcb = board('apply')
    isl = {'name': 'PP_TEST', 'rail': '+24V', 'layer': 'In2.Cu', 'voltage_v': 24,
           'outline': [[40, 5], [55, 5], [55, 20], [40, 20]]}
    params(d, [isl])
    rc, out = run('apply', pcb)
    ok(rc == 0 and 'zone PP_TEST' in out, 'apply writes the island zone', out)
    rc, out = run('apply', pcb)
    info = kpy('import pcbnew\nb = pcbnew.LoadBoard(%r)\n'
               'z = [z for z in b.Zones() if z.GetZoneName() == "PP_TEST"]\n'
               'm = [z for z in b.Zones() if z.GetNetname() == "+3.3V"][0]\n'
               'print(len(z), z[0].GetNetname(), b.GetLayerName(z[0].GetLayer()), '
               'z[0].GetAssignedPriority() > m.GetAssignedPriority(), pcbnew.ToMM(z[0].GetLocalClearance()))\n' % pcb)
    ok(rc == 0 and info.split() == ['1', '+24V', 'In2.Cu', 'True', '0.5'],
       'apply is idempotent: one zone, +24V, In2, above the main plane, clearance 0.5', info + out)
    rc, out = run('check', pcb)
    ok(rc == 1 and ('fills to nothing' in out or 'isolated island copper' in out), 'check FAILs an island no via reaches', out)
    add_via(pcb, 47.5, 12.5)
    run('apply', pcb)
    rc, out = run('check', pcb)
    ok(rc == 0 and '0 FAIL' in out, 'check passes once a +24V via is inside the island', out)

    d, pcb = board('split')
    add_via(pcb, 50, 30)
    params(d, [{'name': 'PP_STRIP', 'rail': '+24V', 'layer': 'In2.Cu', 'voltage_v': 24,
                'outline': [[-1, 28], [101, 28], [101, 32], [-1, 32]]}])
    run('apply', pcb)
    rc, out = run('check', pcb)
    ok(rc == 1 and 'splits it' in out, 'check FAILs an island that splits the main plane', out)

    print('\n%d passed, %d failed' % (PASS, FAIL))
    if not FAIL:
        shutil.rmtree(TMP, ignore_errors=True)
    else:
        print("kept " + TMP)
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
