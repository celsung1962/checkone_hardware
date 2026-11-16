#!/usr/bin/env python
"""dedupe_copper.py - remove duplicate same-net copper: a segment that lies entirely inside another same-net segment
(lesson L19, audit `loop`; ServiceOne rev. 0.2 clean-up, 2026-10-22).

MUST be run with KiCad's own Python (pcbnew).

A segment S is removed when another segment T of the same net, layer and width >= S's lies along the same line (both
end points of S within --tol mm of T's centreline and between T's ends). Exact duplicates keep one copy. S's ends stay
covered by T, so connectivity is unchanged. Kept: a segment that carries the exact pad-centre end T does not (KiCad's
Cleanup "Delete tracks fully inside pads" removes those and the track then ends off-centre, L44), and locked
segments (L40). KiCad's own Cleanup merges co-linear pieces only and leaves these.

Usage: dedupe_copper.py BOARD [--apply] [--box x0,y0,x1,y1] [--exclude-box x0,y0,x1,y1] [--tol 0.02] [--indices K]
--box keeps the pass inside a rectangle, --exclude-box skips one. --indices K removes only candidate K (for
gate_each.py: one candidate per gated run). board_guard on --apply; saved in place.
"""
import math, os, sys
import pcbnew

a = sys.argv[1:]
if not a or a[0].startswith('-'):
    sys.stdout.write(__doc__)
    sys.exit(2)
BOARD = a[0]
APPLY = '--apply' in a
BOX = tuple(map(float, a[a.index('--box') + 1].split(','))) if '--box' in a else None
XBOX = tuple(map(float, a[a.index('--exclude-box') + 1].split(','))) if '--exclude-box' in a else None
TOL = float(a[a.index('--tol') + 1]) if '--tol' in a else 0.02
ONLY = int(a[a.index('--indices') + 1]) if '--indices' in a else None
mm = pcbnew.ToMM
b = pcbnew.LoadBoard(BOARD)
segs = [t for t in b.GetTracks() if t.GetClass() == 'PCB_TRACK']
PADS = [p for fp in b.GetFootprints() for p in fp.Pads()]


def at_pad_centre(pt, net):
    return any(p.GetNetname() == net and (p.GetPosition() - pt).EuclideanNorm() <= 1000 for p in PADS)


def on(p, t):
    ax, ay, bx, by = mm(t.GetStart().x), mm(t.GetStart().y), mm(t.GetEnd().x), mm(t.GetEnd().y)
    px, py = mm(p.x), mm(p.y)
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return False
    u = ((px - ax) * dx + (py - ay) * dy) / L2
    if u < -1e-6 or u > 1 + 1e-6:
        return False
    return math.hypot(px - ax - u * dx, py - ay - u * dy) <= TOL


gone = set()
out = []
by = {}
for t in segs:
    by.setdefault((t.GetNetname(), t.GetLayer()), []).append(t)
for (net, L), ts in by.items():
    for s in ts:
        if s.m_Uuid.AsString() in gone or s.GetLength() == 0 or s.IsLocked():
            continue
        x, y = mm(s.GetStart().x), mm(s.GetStart().y)
        if (BOX and not (BOX[0] <= x <= BOX[2] and BOX[1] <= y <= BOX[3])) or \
           (XBOX and XBOX[0] <= x <= XBOX[2] and XBOX[1] <= y <= XBOX[3]):
            continue
        for t in ts:
            if t is s or t.m_Uuid.AsString() == s.m_Uuid.AsString() or t.m_Uuid.AsString() in gone:
                continue
            if t.GetWidth() < s.GetWidth():
                continue
            if on(s.GetStart(), t) and on(s.GetEnd(), t):
                tends = (t.GetStart(), t.GetEnd())
                if any(at_pad_centre(e, net) and not any((e - q).EuclideanNorm() <= 1000 for q in tends)
                       for e in (s.GetStart(), s.GetEnd())):
                    continue                       # S carries the exact pad-centre end; T does not
                if t.GetLength() == s.GetLength() and s.m_Uuid.AsString() < t.m_Uuid.AsString():
                    continue                       # exact pair: drop only one of the two
                if ONLY is not None and len(out) != ONLY:
                    out.append('(not this run)'); break
                gone.add(s.m_Uuid.AsString())
                out.append('%-18s %s (%.3f,%.3f)-(%.3f,%.3f) w%.2f inside a %.2f mm segment' % (
                    net[:18], b.GetLayerName(L), x, y, mm(s.GetEnd().x), mm(s.GetEnd().y), mm(s.GetWidth()),
                    mm(t.GetLength())))
                break
for i, o in enumerate(out):
    print('  dup [%d]' % i, o)
print('duplicates', len(out))
if APPLY and out:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import board_guard
    board_guard.check_board_writable(BOARD, argv=[], script='dedupe_copper.py')
    for t in list(b.GetTracks()):
        if t.m_Uuid.AsString() in gone:
            b.Remove(t)
    pcbnew.SaveBoard(BOARD, b)
    print('saved')
