#!/usr/bin/env python
"""centre_gated.py - automatic centring of the audit's `between-pads` FAILs (playbook E6), in BATCHES with
bisection, every batch gated by KiCad DRC and the audit.

center_gaps_safe.py proposes one move per off-centre segment, but its own clearance model is not the judge
(playbook G4: 22 moves that passed it produced 9 shorts on BladeOne). Gating one move per DRC run is safe and
slow: ~75 s per move (DRC + audit) on a 340-part board, hours per round. Here the candidate moves are applied
as a SET on a work copy and kept if
    - KiCad DRC gains no item of the copper types (short, clearance, crossing, hole clearance, hole-to-hole,
      connection width, dangling track/via, copper-to-edge) and no unconnected item, AND
    - the audit's shared-gap count does not rise, AND
    - the audit FAIL total falls, AND
    - the audit has no NEW FAIL (1.27.0, audit_gate.py: a FAIL identity the work copy did not have before the set -
      a lower total does not excuse a new between-pads, via or acute FAIL elsewhere);
otherwise the set is split in halves and each half is tried (bisection). Rounds repeat (the audit indices change
after every round) until a round keeps nothing. Measured on ServiceOne (2026-10-04): round 1, 195 candidates,
194 kept, FAIL 427 -> 246 in about ten minutes; four rounds to 225.

1.28.0: a set that moves, changes or removes a locked track or via is rejected (L40, locks.py; center_gaps_safe.py
--allow-locked-nets still decides what it may move); --box / --exclude-box x0,y0,x1,y1 keep the candidates to (or
away from) an area, such as a region left for the designer (L37).

The board given is NOT modified unless --apply; the accepted result is <workdir>/<board>.kicad_pcb.

Usage (system Python; node and KiCad must be installed):
    centre_gated.py <board.kicad_pcb> <workdir> [--apply] [--rounds N] [--log FILE]
                    [--box x0,y0,x1,y1] [--exclude-box x0,y0,x1,y1]
                    [--kicad-python PATH] [--kicad-cli PATH] [--force-write]
The board needs its .kicad_pro beside it; with --apply, no KiCad lock either (board_guard.py).
"""
import collections
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kicad_sexp as KS  # noqa: E402
import board_guard  # noqa: E402
import audit_gate  # noqa: E402
import locks  # noqa: E402

a = sys.argv[1:]
if len(a) < 2 or a[0].startswith('--'):
    sys.stderr.write(__doc__)
    sys.exit(2)
opt = lambda n, d=None: a[a.index(n) + 1] if n in a else d
BOARD, WORK = os.path.abspath(a[0]), os.path.abspath(a[1])
APPLY, ROUNDS = '--apply' in a, int(opt('--rounds', '6'))
BOX, XBOX = [tuple(float(v) for v in opt(n).split(',')) if opt(n) else None for n in ('--box', '--exclude-box')]
inbox = lambda b, x, y: b[0] <= x <= b[2] and b[1] <= y <= b[3]
# The work copies are saved by center_gaps_safe.py, which needs the .kicad_pro beside them (copied below from
# the board's folder); --apply also writes the board itself, so then KiCad must not hold a lock on it.
board_guard.check_board_writable(BOARD, check_locks=APPLY, argv=a[2:], script='centre_gated.py')
KP = KS.find_kicad_python(opt('--kicad-python'))
CLI = KS.find_kicad_cli(opt('--kicad-cli'))
if not (KP and CLI):
    sys.exit('need KiCad\'s python (%s) and kicad-cli (%s); pass --kicad-python / --kicad-cli' % (KP, CLI))
CGS = os.path.join(HERE, 'center_gaps_safe.py')
BAD = re.compile(r'^(shorting_items|clearance|tracks_crossing|hole_clearance|hole_to_hole|connection_width|'
                 r'track_dangling|copper_edge_clearance|via_dangling|items_not_allowed)$')
stem = os.path.splitext(os.path.basename(BOARD))[0]
src = os.path.dirname(BOARD)
base = os.path.join(WORK, stem + '.kicad_pcb')
trial = os.path.join(WORK, 'try', stem + '.kicad_pcb')
for d in (WORK, os.path.dirname(trial)):
    os.makedirs(d, exist_ok=True)
    # the project rules travel with the board: without the .kicad_dru, DRC reports the project's accepted
    # exceptions as new errors (2 false copper_edge_clearance on ServiceOne)
    for f in (stem + '.kicad_pro', stem + '.kicad_dru', 'kicad_golden.project.json'):
        if os.path.exists(os.path.join(src, f)):
            shutil.copy2(os.path.join(src, f), os.path.join(d, f))
shutil.copy2(BOARD, base)
LOG = opt('--log', os.path.join(WORK, 'centre_gated.log'))
log = open(LOG, 'a', encoding='utf-8')


def say(*x):
    s = ' '.join(str(v) for v in x)
    print(s, flush=True)
    log.write(s + '\n'); log.flush()


def drc(pcb):
    j = os.path.join(WORK, 'drc.json')
    subprocess.run([CLI, 'pcb', 'drc', '--severity-all', '--refill-zones', '--format', 'json', '-o', j, pcb], capture_output=True)
    d = json.load(open(j, encoding='utf-8'))
    c = collections.Counter(v['type'] for v in d['violations'] if BAD.match(v['type']))
    c['unconnected_items'] = len(d['unconnected_items'])
    return c


def audit(pcb, out):
    allf = audit_gate.audit(pcb, out)
    f = [x for x in allf if x['level'] == 'FAIL']
    return sum(1 for x in f if x['check'] == 'shared-gap'), len(f), allf


state = {}


def accept(S, audit_json):
    shutil.copy2(base, trial)
    o = subprocess.run([KP, CGS, trial, audit_json, '--apply', '--indices', ','.join(map(str, S))],
                       capture_output=True, text=True).stdout
    done = len(re.findall(r'centred \[', o))
    if not done:
        return False
    d = drc(trial)
    worse = {k: d[k] - state['drc'].get(k, 0) for k in d if d[k] > state['drc'].get(k, 0)}
    if worse:
        say('  set of %3d: DRC worse %s' % (len(S), worse)); return False
    g, f, allf = audit(trial, os.path.join(WORK, 'audit_try.json'))
    if g > state['gap'] or f >= state['fail']:
        say('  set of %3d: audit shared-gap %d vs %d, FAIL %d vs %d' % (len(S), g, state['gap'], f, state['fail'])); return False
    new = audit_gate.new_fails(state['ids'], allf)
    if new:
        say('  set of %3d: %d NEW audit FAIL(s), first: [%s] %s' % (len(S), len(new), new[0]['check'], new[0]['msg'][:120])); return False
    moved = locks.changed(state['locks'], locks.fingerprint(trial))
    if moved:
        say('  set of %3d: %s' % (len(S), moved[0])); return False
    shutil.copy2(trial, base)
    state.update(gap=g, fail=f, drc=d, ids=audit_gate.fail_ids(allf))
    say('  set of %3d: KEPT (%d moves) -> FAIL %d' % (len(S), done, f)); return True


def bisect(S, audit_json):
    if not S or accept(S, audit_json):
        return
    if len(S) == 1:
        say('  [%d] rejected' % S[0]); return
    h = len(S) // 2
    bisect(S[:h], audit_json); bisect(S[h:], audit_json)


for rnd in range(1, ROUNDS + 1):
    aj = os.path.join(WORK, 'audit_round%d.json' % rnd)
    g, f, allf = audit(base, aj)
    state.update(gap=g, fail=f, drc=drc(base), ids=audit_gate.fail_ids(allf), locks=locks.fingerprint(base))
    r = subprocess.run([KP, CGS, base, aj], capture_output=True, text=True)
    cands = []
    for m in re.finditer(r'centred \[(\d+)\] .*?@(-?[\d.]+),(-?[\d.]+)', r.stdout):
        x, y = float(m.group(2)), float(m.group(3))
        if (BOX and not inbox(BOX, x, y)) or (XBOX and inbox(XBOX, x, y)):
            continue
        cands.append(int(m.group(1)))
    say('round %d: audit FAIL %d, shared-gap %d, DRC %s; candidates %d' % (rnd, f, g, dict(state['drc']), len(cands)))
    before = state['fail']
    bisect(cands, aj)
    if state['fail'] >= before:
        break
say('end: audit FAIL %d, shared-gap %d; result %s' % (state['fail'], state['gap'], base))
if APPLY:
    shutil.copy2(BOARD, BOARD + '.bak_precentre')
    shutil.copy2(base, BOARD)
    say('applied to %s (backup .bak_precentre)' % BOARD)
