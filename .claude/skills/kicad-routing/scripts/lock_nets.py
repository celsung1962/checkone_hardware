#!/usr/bin/env python
"""lock_nets.py - lock a phase's copper and prove a later phase did not disturb it.

MUST be run with KiCad's own Python (it imports pcbnew):

    "<kicad>/bin/python" lock_nets.py <board.kicad_pcb> [--nets A,B] [--verify] [--unlock]

Phased routing is only safe if "locked" actually holds. KiCad writes a locked track into the
Specctra DSN as `(type fix)`, and Freerouting honours it - but that is a property of a toolchain,
not a guarantee, and a silent failure here would corrupt the phase it was meant to protect. So
this records a fingerprint of the exact geometry it locks, and `--verify` re-checks every item
afterwards. A moved track is reported, never assumed away.

Net selection, first match wins:
  --nets A,B,C                          explicit list
  kicad_golden.project.json             priority_routing.critical_nets
  (nothing)                             refuses to guess

Modes:
  (default)   lock the selected nets' tracks and vias, write <board>.lockfp.json
  --verify    compare the board against that fingerprint; exit 1 if anything moved
  --unlock    clear the locked flag on the selected nets (fingerprint untouched)

Options:
  --fingerprint PATH   override the fingerprint location
  --quiet              one summary line

Exit codes: 0 ok, 1 fingerprint mismatch / nothing selected, 2 usage.
"""
import io
import os
import sys
import json


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


VERIFY = '--verify' in args
UNLOCK = '--unlock' in args
QUIET = '--quiet' in args
FP = opt('--fingerprint', os.path.splitext(BOARD)[0] + '.lockfp.json')
NETS_RAW = opt('--nets')

try:
    import pcbnew
except ImportError as e:
    die("cannot import pcbnew (%s). Run this with KiCad's own Python." % e)


def critical_from_params(board):
    for name in (os.path.splitext(board)[0] + '.golden.json',
                 os.path.join(os.path.dirname(board), 'kicad_golden.project.json')):
        if os.path.isfile(name):
            try:
                with io.open(name, encoding='utf-8') as f:
                    p = json.load(f)
            except Exception:
                continue
            nets = (p.get('priority_routing') or {}).get('critical_nets') or []
            if nets:
                return [n for n in nets if not str(n).startswith('_')], os.path.basename(name)
    return [], None


if NETS_RAW:
    crit, src = [n.strip() for n in NETS_RAW.split(',') if n.strip()], '--nets'
else:
    crit, src = critical_from_params(BOARD)
if not crit:
    die('no critical nets given. Pass --nets, or set priority_routing.critical_nets in '
        'kicad_golden.project.json. This script will not guess which nets are critical.')

if not VERIFY:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import board_guard  # noqa: E402
    board_guard.check_board_writable(BOARD, script='lock_nets.py')   # KiCad lock / .kicad_pro beside it
b = pcbnew.LoadBoard(BOARD)
present = set()
for fp_ in b.GetFootprints():
    for p in fp_.Pads():
        if p.GetNetname():
            present.add(p.GetNetname())
missing = [n for n in crit if n not in present]


def key(t):
    """Geometry identity. Endpoint order is normalised so a re-serialised segment is not
    mistaken for a moved one."""
    if t.GetClass() == 'PCB_VIA':
        c = t.GetStart()
        # KiCad 10 vias can carry a per-layer width; the arg-less GetWidth() asserts and can
        # hang a headless run, so always use the layer-aware accessor.
        w = t.GetFrontWidth() if hasattr(t, 'GetFrontWidth') else t.GetWidth(pcbnew.F_Cu)
        return 'V|%s|%d,%d|%d/%d' % (t.GetNetname(), c.x, c.y, w, t.GetDrill())
    s, e = t.GetStart(), t.GetEnd()
    a, z = sorted([(s.x, s.y), (e.x, e.y)])
    return 'T|%s|%s|%d,%d|%d,%d|%d' % (t.GetNetname(), b.GetLayerName(t.GetLayer()),
                                       a[0], a[1], z[0], z[1], t.GetWidth())


items = [t for t in b.GetTracks() if t.GetNetname() in set(crit)]
out = []
out.append('critical nets: %d (from %s)' % (len(crit), src))
if missing:
    out.append('  NOT on this board: %s' % ', '.join(missing))

if VERIFY:
    if not os.path.isfile(FP):
        die('no fingerprint at %s - run without --verify first' % FP)
    with io.open(FP, encoding='utf-8') as f:
        rec = json.load(f)
    before = set(rec['items'])
    now = set(key(t) for t in items)
    lost, added = before - now, now - before
    out.append('  fingerprinted : %d' % len(before))
    out.append('  identical     : %d' % len(before & now))
    out.append('  MOVED/MISSING : %d' % len(lost))
    out.append('  new on those nets: %d' % len(added))
    for k in sorted(lost)[:8]:
        out.append('     lost: %s' % k)
    out.append('  still flagged locked: %d' % sum(1 for t in items if t.IsLocked()))
    ok = not lost
    out.append('  VERDICT: %s' % ('lock held - phase geometry untouched' if ok
                                  else 'LOCK BROKEN - phase geometry was altered, do not proceed'))
    print(('lock_verify ok=%s moved=%d' % (ok, len(lost))) if QUIET else '\n'.join(out))
    sys.exit(0 if ok else 1)

if UNLOCK:
    n = 0
    for t in items:
        if t.IsLocked():
            t.SetLocked(False)
            n += 1
    pcbnew.SaveBoard(BOARD, b)
    out.append('  unlocked %d item(s)' % n)
    print(('unlocked=%d' % n) if QUIET else '\n'.join(out))
    sys.exit(0)

n = 0
for t in items:
    t.SetLocked(True)
    n += 1
pcbnew.SaveBoard(BOARD, b)
b2 = pcbnew.LoadBoard(BOARD)
it2 = [t for t in b2.GetTracks() if t.GetNetname() in set(crit)]
rec = {'board': os.path.basename(BOARD), 'nets': crit,
       'items': sorted(key(t) for t in it2)}
with io.open(FP, 'w', encoding='utf-8') as f:
    f.write(json.dumps(rec, indent=1))
out.append('  locked %d item(s); fingerprint of %d written to %s'
           % (n, len(rec['items']), os.path.basename(FP)))
out.append('  locked flag survives reload: %d' % sum(1 for t in it2 if t.IsLocked()))
out.append('  NEXT: export the DSN (locked tracks become "(type fix)"), route the next phase,')
out.append('        import, then re-run with --verify BEFORE trusting the result.')
print(('locked=%d fingerprint=%d' % (n, len(rec['items']))) if QUIET else '\n'.join(out))
sys.exit(0)
