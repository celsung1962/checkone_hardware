#!/usr/bin/env python
"""run_tests_rules.py - self-test for rules_writer.py (rev M).

The assertion that matters most is the quoting one. Freerouting's rules reader stops at the first
space in an unquoted design name: a board called "My Board v2" is read as 'My', the designName
check fails, and THE ENTIRE RULES FILE IS SILENTLY IGNORED. The run completes normally, the log
says nothing useful, and none of the costs applied. Verified against Freerouting 2.4.1, where an
unquoted name produced `designName not matching ... got 'BladeOne'` and a quoted one produced no
warning at all.

    python tests/run_tests_rules.py
"""
import io
import os
import re
import sys
import json
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
W = os.path.join(SKILL, 'scripts', 'rules_writer.py')
OUT = os.path.join(HERE, 'fixtures_rules')

PASS = FAIL = 0


def check(label, cond, detail=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print('PASS  %s%s' % (label, ('  - ' + str(detail)) if detail else ''))
    else:
        FAIL += 1
        print('FAIL  %s  - %s' % (label, detail))


DSN = '''(pcb "C:\\somewhere\\My Board v2.dsn"
  (parser
    (string_quote ")
    (space_in_quoted_tokens on)
  )
  (structure
    (layer F.Cu
      (type signal)
    )
    (layer GND
      (type power)
    )
    (layer POWER
      (type power)
    )
    (layer B.Cu
      (type signal)
    )
  )
  (network
  )
)
'''

if os.path.isdir(OUT):
    shutil.rmtree(OUT)
os.makedirs(OUT)
# the filename carries the design name, spaces included - that is what Freerouting compares against
src = os.path.join(OUT, 'My Board v2.dsn')
io.open(src, 'w', encoding='utf-8', newline='').write(DSN)


def run(*a):
    p = subprocess.run([sys.executable, W] + list(a), capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


dst = os.path.join(OUT, 'a.rules')
rc, so = run(src, dst, '--via-cost', '150', '--quiet')
check('writer exits 0', rc == 0, so.strip()[:140])
txt = io.open(dst, encoding='utf-8').read() if os.path.isfile(dst) else ''

# ---------------------------------------------------------------- the silent-failure guard
check('design name is QUOTED (unquoted = rules silently ignored)',
      '(rules PCB "My Board v2"' in txt, txt.split('\n')[0] if txt else 'no file')
check('design name comes from the DSN basename, spaces intact',
      'My Board v2' in txt.split('\n')[0])

# ---------------------------------------------------------------- layers
check('signal layers are routable', '(layer_rule F.Cu' in txt and '(layer_rule B.Cu' in txt)
fcu = txt[txt.index('(layer_rule F.Cu'):txt.index('(layer_rule GND')]
check('a signal layer is active with a preferred direction',
      '(active on)' in fcu and 'preferred_direction' in fcu, fcu.replace('\n', ' ')[:70])
gnd = txt[txt.index('(layer_rule GND'):txt.index('(layer_rule POWER')]
check('a power plane is NOT activated for routing', '(active off)' in gnd,
      gnd.replace('\n', ' ')[:60])
check('preferred directions alternate between the two signal layers',
      'vertical' in fcu and 'horizontal' in txt[txt.index('(layer_rule B.Cu'):])

# ---------------------------------------------------------------- costs
check('via cost reaches the file', '(via_costs 150)' in txt)
check('plane via cost is separate from via cost', '(plane_via_costs 5)' in txt)
check('autoroute settings block present',
      '(autoroute_settings' in txt and '(autoroute on)' in txt and '(vias on)' in txt)

# ---------------------------------------------------------------- params file
par = os.path.join(OUT, 'kicad_golden.project.json')
io.open(par, 'w', encoding='utf-8').write(json.dumps(
    {'router_costs': {'via_cost': 222, 'plane_via_cost': 7,
                      'preferred_direction': {'F.Cu': 'horizontal'}}}))
dst2 = os.path.join(OUT, 'b.rules')
rc, so = run(src, dst2, '--params', par, '--quiet')
t2 = io.open(dst2, encoding='utf-8').read() if os.path.isfile(dst2) else ''
check('costs are read from the params file', '(via_costs 222)' in t2 and '(plane_via_costs 7)' in t2,
      so.strip()[:100])
f2 = t2[t2.index('(layer_rule F.Cu'):t2.index('(layer_rule GND')] if t2 else ''
check('a per-layer preferred direction override is honoured', 'horizontal' in f2, f2.replace('\n', ' ')[:70])

# an explicit flag must beat the params file
dst3 = os.path.join(OUT, 'c.rules')
rc, so = run(src, dst3, '--params', par, '--via-cost', '333', '--quiet')
t3 = io.open(dst3, encoding='utf-8').read() if os.path.isfile(dst3) else ''
check('an explicit --via-cost overrides the params file', '(via_costs 333)' in t3)

# ---------------------------------------------------------------- wiring into the router
# This guards a bug that SHIPPED: the '-dr' append was written against a variable that did not
# exist (`FR_CMD` instead of `cmd`) and at the wrong indentation, which also pulled the whole
# routing block inside `if RULES:`. It is valid Python, so no syntax check catches it, and
# --export-only returns before reaching that line, so the obvious smoke test misses it too.
# Every sweep candidate died with NameError.
import ast

RF = os.path.join(SKILL, 'scripts', 'route_freerouting.py')
tree = ast.parse(io.open(RF, encoding='utf-8').read())


def literals(node):
    return {n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)}


def find_in_bodies(tree):
    """-> (name assigned the router argv, name augmented with -dr, same_block)"""
    argv_name = dr_name = None
    same = False
    for parent in ast.walk(tree):
        body = getattr(parent, 'body', None)
        if not isinstance(body, list):
            continue
        a = d = None
        for st in body:
            if isinstance(st, ast.Assign) and '-de' in literals(st) and '-do' in literals(st):
                if isinstance(st.targets[0], ast.Name):
                    a = st.targets[0].id
            # the -dr append may sit inside a nested `if RULES:` within the same body
            for sub in ast.walk(st):
                if isinstance(sub, ast.AugAssign) and '-dr' in literals(sub):
                    if isinstance(sub.target, ast.Name):
                        d = sub.target.id
        if a and d:
            argv_name, dr_name, same = a, d, True
            break
        argv_name = argv_name or a
        dr_name = dr_name or d
    return argv_name, dr_name, same


argv_name, dr_name, same_block = find_in_bodies(tree)
check('the router argv variable is found', argv_name is not None, argv_name)
check('the -dr append targets the SAME variable as -de/-do',
      argv_name is not None and argv_name == dr_name, '%s vs %s' % (argv_name, dr_name))
check('the -dr append lives in the same block as the argv construction', same_block,
      'a stray top-level `if RULES:` swallows the routing block')

print('\n%d/%d assertions passed' % (PASS, PASS + FAIL))
sys.exit(1 if FAIL else 0)
