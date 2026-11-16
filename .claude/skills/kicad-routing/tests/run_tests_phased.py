#!/usr/bin/env python
"""run_tests_phased.py - self-test for the phased-routing tooling (rev L).

Covers dsn_filter.py, which is pure text surgery and needs no pcbnew. The lock_nets.py side
needs a real board and KiCad's python, so it is exercised against the corpus, not here.

Two of these assertions encode bugs that actually shipped during development and would have
corrupted a DSN silently:

  * a class member list contains QUOTED net names with spaces  ("/Solar MPPT - Power/REGN")
  * net names contain PARENTHESES                              (Net-(U7-EN))

and one encodes why the obvious validity check is wrong:

  * a Specctra DSN is not KiCad s-expression - backslashes are literal and (string_quote ")
    uses a bare quote as a value, so an absolute paren-balance check reports a good file as bad

    python tests/run_tests_phased.py
"""
import io
import os
import sys
import json
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
FILT = os.path.join(SKILL, 'scripts', 'dsn_filter.py')
OUT = os.path.join(HERE, 'fixtures_phased')

PASS = FAIL = 0


def check(label, cond, detail=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print('PASS  %s%s' % (label, ('  - ' + str(detail)) if detail else ''))
    else:
        FAIL += 1
        print('FAIL  %s  - %s' % (label, detail))


# A DSN with every hazard the real exporter produces.
DSN = '''(pcb "C:\\Users\\someone\\board.dsn"
  (parser
    (string_quote ")
    (space_in_quoted_tokens on)
    (host_cad "KiCad's Pcbnew")
  )
  (structure
    (layer F.Cu (type signal))
    (layer B.Cu (type signal))
  )
  (network
    (net "Net-(U7-EN)"
      (pins R37-1 U7-6)
    )
    (net +VSYS
      (pins R37-2 C24-1)
    )
    (net "/Solar MPPT  - Power/REGN"
      (pins U6-9 C7-1)
    )
    (net GND
      (pins U6-1 C7-2)
    )
    (class kicad_default "/Solar MPPT  - Power/REGN" "Net-(U7-EN)" GND
      (circuit (use_via Via_450))
      (rule (width 200) (clearance 150))
    )
    (class POWER_DC +VSYS
      (circuit (use_via Via_600))
      (rule (width 600) (clearance 150))
    )
  )
  (wiring
  )
)
'''

if os.path.isdir(OUT):
    shutil.rmtree(OUT)
os.makedirs(OUT)
src = os.path.join(OUT, 'in.dsn')
io.open(src, 'w', encoding='utf-8', newline='').write(DSN)


def run(*a):
    p = subprocess.run([sys.executable, FILT] + list(a), capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def nets_in(path):
    t = io.open(path, encoding='utf-8', newline='').read()
    blk = t[t.index('(network'):]
    out = []
    for line in blk.split('\n'):
        ls = line.strip()
        if ls.startswith('(net '):
            v = ls[5:].strip()
            out.append(v[1:v.index('"', 1)] if v.startswith('"') else v.split()[0])
    return out


# ---------------------------------------------------------------- basic subsetting
dst = os.path.join(OUT, 'a.dsn')
rc, so = run(src, dst, '--nets', '+VSYS,GND', '--quiet')
check('filter exits 0', rc == 0, so.strip()[:120])
got = sorted(nets_in(dst)) if os.path.isfile(dst) else []
check('only the selected nets survive', got == ['+VSYS', 'GND'], got)

# ---------------------------------------------------------------- the two shipped bugs
dst2 = os.path.join(OUT, 'b.dsn')
rc, so = run(src, dst2, '--nets', '+VSYS', '--invert', '--quiet')
check('--invert exits 0', rc == 0, so.strip()[:120])
if os.path.isfile(dst2):
    txt = io.open(dst2, encoding='utf-8', newline='').read()
    # a naive find('(') splits the class header inside "Net-(U7-EN)" and wrecks the file
    check('net name containing parentheses survives', 'Net-(U7-EN)' in txt)
    # a naive .split() shreds a quoted name containing spaces into fragments
    check('quoted net name with spaces survives intact',
          '"/Solar MPPT  - Power/REGN"' in txt)
    # (string_quote ") legitimately contributes ONE unpaired quote, so the raw count is odd on a
    # healthy DSN. Discount that line before checking the rest pairs up.
    body = '\n'.join(l for l in txt.split('\n') if 'string_quote' not in l)
    check('quotes pair up once (string_quote ") is discounted', body.count('"') % 2 == 0,
          'quotes=%d' % body.count('"'))
    kept = sorted(nets_in(dst2))
    check('--invert keeps everything else', kept == sorted(['Net-(U7-EN)', '/Solar MPPT  - Power/REGN', 'GND']), kept)

# ---------------------------------------------------------------- class pruning
if os.path.isfile(dst):
    txt = io.open(dst, encoding='utf-8', newline='').read()
    i = txt.index('(class POWER_DC')
    check('a class keeps its selected member', '+VSYS' in txt[i:i + 60])
    j = txt.index('(class kicad_default')
    head = txt[j:txt.index('(circuit', j)]
    check('a class drops its unselected members', 'Net-(U7-EN)' not in head and 'GND' in head,
          head.strip()[:80])

# ---------------------------------------------------------------- refuses to guess
rc, so = run(src, os.path.join(OUT, 'c.dsn'), '--quiet')
check('refuses to run without a net selection', rc != 0 and 'will not guess' in so, 'rc=%d' % rc)

# ---------------------------------------------------------------- params file
par = os.path.join(OUT, 'kicad_golden.project.json')
io.open(par, 'w', encoding='utf-8').write(json.dumps({'priority_routing': {'critical_nets': ['GND']}}))
dst3 = os.path.join(OUT, 'd.dsn')
rc, so = run(src, dst3, '--params', par, '--quiet')
check('reads critical_nets from the params file', rc == 0 and nets_in(dst3) == ['GND'],
      nets_in(dst3) if os.path.isfile(dst3) else so.strip()[:80])

print('\n%d/%d assertions passed' % (PASS, PASS + FAIL))
sys.exit(1 if FAIL else 0)
