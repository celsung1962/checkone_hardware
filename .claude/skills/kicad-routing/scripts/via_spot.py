#!/usr/bin/env python
"""via_spot.py - scan the legal via spots along a line before a fix is attempted (lesson L34; ServiceOne issues 3 and 7,
2026-10-22).

MUST be run with KiCad's own Python (pcbnew, shapely).

A fix that needs a neighbour moved is not forced: it is recorded for the interactive router. Before a scripted fix
places a via (a plane pin's own via on its pad axis, a relocated stub via), scan the spots: for each point on the
line from (x0,y0) to (x1,y1) in STEP mm the tool prints the minimum copper clearance of a via of the given size to all
other-net copper (F.Cu / B.Cu pads, tracks, other vias) and the minimum hole-to-hole distance (drill edges, any net),
with the nearest offender. No spot that meets the project's clearance (e.g. 0.1 mm copper, 0.25 mm hole-to-hole) =
a list item for the interactive router, not a forced move. ServiceOne examples: U8 pin 10 (axis blocked by a track
and two vias), U202 pin 6 (no legal spot: pin 7's track runs under the body).

Usage: via_spot.py BOARD NET x0,y0 x1,y1 STEP [--d 0.45] [--drill 0.2]
Read-only.
"""
import sys, math
import pcbnew
from shapely.geometry import Point, Polygon, LineString

a = sys.argv[1:]
if len(a) < 5 or a[0].startswith('-'):
    sys.stdout.write(__doc__)
    sys.exit(2)
BOARD, NET = a[0], a[1]
p0, p1 = [tuple(map(float, s.split(','))) for s in a[2:4]]
STEP = float(a[4])
D = float(a[a.index('--d') + 1]) if '--d' in a else 0.45
DR = float(a[a.index('--drill') + 1]) if '--drill' in a else 0.2
mm = pcbnew.ToMM
b = pcbnew.LoadBoard(BOARD)
lo = (min(p0[0], p1[0]) - 3, min(p0[1], p1[1]) - 3, max(p0[0], p1[0]) + 3, max(p0[1], p1[1]) + 3)
inb = lambda x, y: lo[0] <= x <= lo[2] and lo[1] <= y <= lo[3]
obs, holes = [], []
for fp in b.GetFootprints():
    for p in fp.Pads():
        c = p.GetPosition()
        if not inb(mm(c.x), mm(c.y)):
            continue
        if p.GetDrillSizeX() > 0:
            holes.append((mm(c.x), mm(c.y), mm(p.GetDrillSizeX()) / 2, fp.GetReference() + '.' + p.GetNumber()))
        if p.GetNetname() == NET:
            continue
        for L in (pcbnew.F_Cu, pcbnew.B_Cu):
            if not p.IsOnLayer(L):
                continue
            o = p.GetEffectivePolygon(L).Outline(0)
            obs.append((Polygon([(mm(o.CPoint(i).x), mm(o.CPoint(i).y)) for i in range(o.PointCount())]),
                        '%s.%s %s' % (fp.GetReference(), p.GetNumber(), p.GetNetname())))
for t in b.GetTracks():
    if t.GetClass() == 'PCB_VIA':
        c = t.GetPosition()
        if inb(mm(c.x), mm(c.y)):
            holes.append((mm(c.x), mm(c.y), mm(t.GetDrillValue()) / 2, 'via ' + t.GetNetname()))
            if t.GetNetname() != NET:
                obs.append((Point(mm(c.x), mm(c.y)).buffer(mm(t.GetWidth(pcbnew.F_Cu)) / 2), 'via ' + t.GetNetname()))
        continue
    if t.GetNetname() == NET or t.GetLayer() not in (pcbnew.F_Cu, pcbnew.B_Cu):
        continue
    s, e = t.GetStart(), t.GetEnd()
    if not (inb(mm(s.x), mm(s.y)) or inb(mm(e.x), mm(e.y))):
        continue
    obs.append((LineString([(mm(s.x), mm(s.y)), (mm(e.x), mm(e.y))]).buffer(mm(t.GetWidth()) / 2),
                'track %s %s' % (t.GetNetname(), b.GetLayerName(t.GetLayer()))))
n = max(1, int(round(math.hypot(p1[0] - p0[0], p1[1] - p0[1]) / STEP)))
for i in range(n + 1):
    x = p0[0] + (p1[0] - p0[0]) * i / n
    y = p0[1] + (p1[1] - p0[1]) * i / n
    v = Point(x, y).buffer(D / 2)
    cl = min(((g.distance(v), nme) for g, nme in obs), default=(9, '-'))
    hh = min(((math.hypot(x - hx, y - hy) - hr - DR / 2, nme) for hx, hy, hr, nme in holes
              if math.hypot(x - hx, y - hy) > 1e-3), default=(9, '-'))
    print('(%.3f, %.3f)  copper %.3f [%s]  hole-hole %.3f [%s]' % (x, y, cl[0], cl[1], hh[0], hh[1]))
