#!/usr/bin/env python
"""run_corpus.py - regression-test the audit against REAL boards.

    python tests/run_corpus.py <corpus_dir> [--record] [--tolerance N]

Why this exists: every fixture in the synthetic suites is something the skill's own author wrote,
so it only contains defects that were already thought of. The footprint-internal keepout bug
survived three releases precisely because no synthetic fixture had one - it took a real board,
and a user noticing, to find it. Real boards carry the cases nobody invented.

How to use it:

  1. Put boards in a directory (a copy is fine; they are never modified):
        corpus/my_board_a.kicad_pcb   + its .kicad_pro and kicad_golden.project.json
        corpus/my_board_b.kicad_pcb   + ...
  2. Record today's audit as the expectation, once you believe it:
        python tests/run_corpus.py corpus --record
  3. From then on, run it after any change to the skill:
        python tests/run_corpus.py corpus

Any drift in the tracked numbers is reported. A change is not automatically wrong - if you
improved a check, re-record. The point is that drift is never silent.

Tracked per board: FAIL/WARN counts, FAIL breakdown by check, and the stats that decide whether
a board can be manufactured (segments, vias, arcs, off-lattice, inner-layer tracks, keepouts,
unclassed power rails, rules matching nothing).

Boards are opened read-only; nothing in the corpus is written except *.expected.json.
"""
import io
import os
import sys
import json
import glob
import subprocess
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
AUDIT = os.path.join(SKILL, 'scripts', 'kicad_audit.js')

TRACKED = ['segments', 'arcs', 'vias', 'footprints', 'off_lattice_segments',
           'inner_layer_segments', 'keepout_zones', 'keepout_zones_in_footprints',
           'power_rails', 'power_rails_unclassed', 'rules_matching_nothing', 'copper_zones']

args = sys.argv[1:]
if not args or args[0].startswith('--'):
    sys.stderr.write(__doc__)
    sys.exit(2)
CORPUS = os.path.abspath(args[0])
RECORD = '--record' in args
TOL = 0
if '--tolerance' in args:
    i = args.index('--tolerance')
    TOL = int(args[i + 1]) if i + 1 < len(args) else 0

if not os.path.isdir(CORPUS):
    sys.stderr.write('no such directory: %s\n' % CORPUS)
    sys.exit(2)

boards = sorted(glob.glob(os.path.join(CORPUS, '*.kicad_pcb')))
if not boards:
    print('no *.kicad_pcb in %s' % CORPUS)
    print('Drop real boards there (with their .kicad_pro and kicad_golden.project.json),')
    print('then run with --record once to capture the expectation.')
    sys.exit(0)

drift_total = 0
missing_expect = 0
print('=' * 72)
print('CORPUS %s  (%d board%s)' % (CORPUS, len(boards), '' if len(boards) == 1 else 's'))
print('=' * 72)

for b in boards:
    name = os.path.basename(b)
    tmp = os.path.join(CORPUS, os.path.splitext(name)[0] + '.audit.json')
    p = subprocess.run(['node', AUDIT, b, '--json', tmp, '--no-sch', '--quiet'],
                       capture_output=True, text=True)
    if not os.path.isfile(tmp):
        print('\n%-34s ERROR: audit produced no report' % name)
        print('   ' + (p.stderr or p.stdout).strip()[:200])
        drift_total += 1
        continue
    with io.open(tmp, encoding='utf-8') as f:
        rep = json.load(f)
    got = {
        'summary': {k: rep['summary'].get(k, 0) for k in ('FAIL', 'WARN', 'INFO')},
        'fail_by_check': dict(Counter(x['check'] for x in rep['findings'] if x['level'] == 'FAIL')),
        'stats': {k: rep['stats'].get(k) for k in TRACKED if k in rep['stats']},
    }
    exp_path = os.path.splitext(b)[0] + '.expected.json'

    if RECORD:
        with io.open(exp_path, 'w', encoding='utf-8') as f:
            f.write(json.dumps(got, indent=1, sort_keys=True))
        print('\n%-34s recorded  (FAIL %d, WARN %d)'
              % (name, got['summary']['FAIL'], got['summary']['WARN']))
        continue

    if not os.path.isfile(exp_path):
        missing_expect += 1
        print('\n%-34s no expectation yet - run with --record' % name)
        print('   today: FAIL %d  WARN %d  %s'
              % (got['summary']['FAIL'], got['summary']['WARN'],
                 ' '.join('%s=%s' % (k, v) for k, v in got['stats'].items())))
        continue

    with io.open(exp_path, encoding='utf-8') as f:
        exp = json.load(f)
    drift = []
    for k in ('FAIL', 'WARN'):
        a, e = got['summary'][k], exp.get('summary', {}).get(k)
        if e is not None and abs(a - e) > TOL:
            drift.append('%s %s -> %s' % (k, e, a))
    for k in set(list(got['stats']) + list(exp.get('stats', {}))):
        a, e = got['stats'].get(k), exp.get('stats', {}).get(k)
        if a != e:
            drift.append('%s %s -> %s' % (k, e, a))
    for k in set(list(got['fail_by_check']) + list(exp.get('fail_by_check', {}))):
        a, e = got['fail_by_check'].get(k, 0), exp.get('fail_by_check', {}).get(k, 0)
        if a != e:
            drift.append('FAIL[%s] %s -> %s' % (k, e, a))
    if drift:
        drift_total += len(drift)
        print('\n%-34s DRIFT (%d)' % (name, len(drift)))
        for d in drift:
            print('   %s' % d)
    else:
        print('\n%-34s stable  (FAIL %d, WARN %d)'
              % (name, got['summary']['FAIL'], got['summary']['WARN']))

print('\n' + '=' * 72)
if RECORD:
    print('expectations recorded for %d board(s)' % len(boards))
    sys.exit(0)
if missing_expect:
    print('%d board(s) have no expectation yet (--record to capture)' % missing_expect)
if drift_total:
    print('DRIFT: %d tracked value(s) changed. Re-record only if the change is an improvement.'
          % drift_total)
else:
    print('no drift: every board matches its recorded expectation')
sys.exit(1 if drift_total else 0)
