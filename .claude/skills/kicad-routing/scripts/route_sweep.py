#!/usr/bin/env python
"""route_sweep.py - pick the routing clearance by measurement instead of by guess.

MUST be run with KiCad's own Python (the scripts it drives import pcbnew):

    "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" route_sweep.py <board.kicad_pcb> [opts]

Clearance is the single setting that most changes how much of a board an autorouter can
finish, and the relationship is NOT monotonic. Measured on the 4-layer test board (2026-09-18):

    0.10 mm -> 40 unrouted, 21 clearance violations (undercut a footprint-local override)
    0.15 mm -> 36 unrouted,  4 violations      <- best
    0.20 mm -> 59 unrouted,  7 violations      <- more clearance, much worse

Guessing costs a full router run each time. This sweeps the candidates, scores each by the
real ratsnest (route_report.py), and leaves the winning board in place.

The floor is never below the largest footprint-local clearance override, because below that
the router silently undercuts the part - see route_freerouting.py --auto-clearance.

Options:
  --clearances A,B,C   candidate clearances in mm (default: auto floor, +0.05, +0.10)
  --passes N           router optimiser passes per run (default 100)
  --threads N          router threads (default 1; multi-threaded optimisation is buggy)
  --timeout SECONDS    per-run cap (default 3600)
  --outdir DIR         working directory for .dsn/.ses/logs (default: alongside the board)
  --keep-all           keep every candidate board as <board>.sweep_<clearance>.kicad_pcb
  --dry-run            print the plan and the resolved candidate list, run nothing
  --no-rules           do NOT generate/pass a .rules file; inherit the GUI's autorouter costs

Exit codes: 0 ok, 1 every candidate failed, 2 usage.
"""
import io
import os
import re
import sys
import json
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def die(msg, code=1):
    sys.stderr.write(str(msg).rstrip() + '\n')
    sys.exit(code)


args = sys.argv[1:]
if not args or args[0].startswith('--'):
    die(__doc__, 2)
BOARD = os.path.abspath(args[0])
if not os.path.isfile(BOARD):
    die('no such board: ' + BOARD, 2)


def opt(name, default=None):
    if name in args:
        i = args.index(name)
        if i + 1 >= len(args):
            die(name + ' needs a value', 2)
        return args[i + 1]
    return default


PASSES = opt('--passes', '100')
THREADS = opt('--threads', '1')
TIMEOUT = opt('--timeout', '3600')
OUTDIR = os.path.abspath(opt('--outdir', os.path.dirname(BOARD)))
KEEP_ALL = '--keep-all' in args
DRY = '--dry-run' in args
CLEAR_RAW = opt('--clearances')
# Autorouter costs come from the project's router_costs via a generated .rules file, so a sweep
# is reproducible instead of inheriting whatever the last person set in the Freerouting GUI.
NO_RULES = '--no-rules' in args

sys.path.insert(0, HERE)
import kicad_sexp as K  # noqa: E402


floor = K.clearance_floor(BOARD)
if CLEAR_RAW:
    cands = [float(x) for x in CLEAR_RAW.split(',') if x.strip()]
    below = [c for c in cands if c < floor]
    if below:
        print('note: %s below the footprint-local floor %.3f mm; the router would undercut '
              'those footprints' % (', '.join('%.3f' % c for c in below), floor))
else:
    cands = K.sweep_candidates(floor)

print('=' * 72)
print('CLEARANCE SWEEP  -  %s' % os.path.basename(BOARD))
print('=' * 72)
print('  footprint-local clearance floor : %.3f mm' % floor)
print('  candidates                      : %s' % ', '.join('%.3f' % c for c in cands))
print('  passes=%s threads=%s timeout=%ss' % (PASSES, THREADS, TIMEOUT))
print('  NOTE: each candidate is a full router run. A Freerouting window opens each time and')
print('        must not be closed.')
if DRY:
    print('\n[dry-run] nothing executed')
    sys.exit(0)

if not os.path.isdir(OUTDIR):
    os.makedirs(OUTDIR)

PRISTINE = os.path.join(OUTDIR, '_sweep_pristine.kicad_pcb')
PRISTINE_PRO = os.path.splitext(PRISTINE)[0] + '.kicad_pro'
SRC_PRO = os.path.splitext(BOARD)[0] + '.kicad_pro'
shutil.copy2(BOARD, PRISTINE)
if os.path.isfile(SRC_PRO):
    shutil.copy2(SRC_PRO, PRISTINE_PRO)
print('  pristine copy                   : %s' % os.path.basename(PRISTINE))

results = []
for c in cands:
    tag = ('%.3f' % c).replace('.', 'p')
    print('\n' + '-' * 72)
    print('RUN clearance %.3f mm' % c)
    print('-' * 72)
    shutil.copy2(PRISTINE, BOARD)
    if os.path.isfile(PRISTINE_PRO):
        shutil.copy2(PRISTINE_PRO, SRC_PRO)
    rc = subprocess.call([
        PY, os.path.join(HERE, 'route_freerouting.py'), BOARD,
        '--clearance', '%.3f' % c, '--passes', PASSES, '--threads', THREADS,
        '--timeout', TIMEOUT, '--outdir', os.path.join(OUTDIR, 'sweep_' + tag),
    ] + ([] if NO_RULES else ['--auto-rules']))
    if rc != 0:
        print('  router returned %d - candidate discarded' % rc)
        results.append({'clearance': c, 'ok': False, 'unrouted': None})
        continue
    rep_json = os.path.join(OUTDIR, 'report_%s.json' % tag)
    subprocess.call([PY, os.path.join(HERE, 'route_report.py'), BOARD,
                     '--json', rep_json, '--quiet'])
    try:
        with io.open(rep_json, encoding='utf-8') as f:
            rep = json.load(f)
    except Exception as e:
        print('  no report (%s) - candidate discarded' % e)
        results.append({'clearance': c, 'ok': False, 'unrouted': None})
        continue
    r = {'clearance': c, 'ok': True,
         'unrouted': rep.get('unrouted'),
         'completion_pct': rep.get('completion_pct'),
         'invalid_padstacks': len(rep.get('invalid_padstacks', [])),
         'unstitched': sum(rep.get('plane_pads_unstitched', {}).values())}
    results.append(r)
    print('  -> unrouted=%s  completion=%s%%  invalid_padstacks=%d'
          % (r['unrouted'], r['completion_pct'], r['invalid_padstacks']))
    if KEEP_ALL:
        keep = BOARD + '.sweep_%s.kicad_pcb' % tag
        shutil.copy2(BOARD, keep)
        print('  kept: %s' % os.path.basename(keep))


def score(r):
    # invalid padstacks disqualify outright; then fewest unrouted; then fewest unstitched
    if not r['ok'] or r['unrouted'] is None:
        return (1, 9e9, 9e9)
    return (1 if r.get('invalid_padstacks') else 0, r['unrouted'], r.get('unstitched', 0))


print('\n' + '=' * 72)
print('SWEEP RESULT')
print('=' * 72)
print('  %-12s %-10s %-12s %-18s %s' % ('clearance', 'unrouted', 'completion', 'invalid padstacks', 'unstitched'))
for r in results:
    print('  %-12.3f %-10s %-12s %-18s %s'
          % (r['clearance'], r.get('unrouted'), r.get('completion_pct'),
             r.get('invalid_padstacks'), r.get('unstitched')))

usable = [r for r in results if r['ok'] and r['unrouted'] is not None]
if not usable:
    shutil.copy2(PRISTINE, BOARD)
    if os.path.isfile(PRISTINE_PRO):
        shutil.copy2(PRISTINE_PRO, SRC_PRO)
    die('every candidate failed; board restored to its pre-sweep state')

best = sorted(usable, key=score)[0]
print('\n  BEST: clearance %.3f mm (%s unrouted, %s%% complete)'
      % (best['clearance'], best['unrouted'], best['completion_pct']))

tag = ('%.3f' % best['clearance']).replace('.', 'p')
keep = BOARD + '.sweep_%s.kicad_pcb' % tag
if KEEP_ALL and os.path.isfile(keep):
    shutil.copy2(keep, BOARD)
    print('  winning board restored in place')
else:
    print('  NOTE: the board currently on disk is the LAST candidate (%.3f mm), not necessarily'
          % results[-1]['clearance'])
    print('        the best. Re-run with --keep-all to have the winner restored automatically,')
    print('        or re-run route_freerouting.py --clearance %.3f once.' % best['clearance'])

print('\nNEXT: stitch_planes.py, then the post-import repair, then kicad_audit.js.')
sys.exit(0)
