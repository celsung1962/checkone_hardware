#!/usr/bin/env python
"""stitch_residual.py - plane-net pads that stitch_planes.py could not reach (boxed-in pads).
Origin: BladeOne routing trial tool (Vladimir Duk, 2026-09-29), brought into kicad-routing 1.18.0 with three
fixes found on ServiceOne (2026-10-04): hole-to-hole now applies to same-net vias too (two GND vias had been placed
0.09 mm apart); the new drill is checked against other-net TRACKS with the hole clearance, not only the copper
clearance (9 hole_clearance warnings); rule areas that forbid tracks or vias (board-level and footprint-internal)
are obstacles. Run with KiCad's Python; gate the result with kicad-cli DRC.

stitch_residual.py <board> REF-PAD [REF-PAD ...] [--apply] - stitching vias for plane-net pads the stitcher could not
place, with a straight or ONE-bend (dogleg) stub on the 45-degree lattice. Checked against the true shapes with
pcbnew: copper clearance to other-net items, hole-to-copper clearance for the new drill and against other-net
drills, hole-to-hole, board-edge clearance, and no F.Cu stub or via inside another part's crystal/inductor courtyard.
The first leg leaves the pad centre and is necked to the pad's smallest dimension; the new copper is locked.
Shortest total stub wins. Dry run unless --apply."""
import pcbnew, sys, math, re, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board_guard, zone_fill_check  # noqa: E401,E402
args = sys.argv[1:]; APPLY = '--apply' in args
if APPLY:
    board_guard.check_board_writable(args[0], script='stitch_residual.py')
B = pcbnew.LoadBoard(args[0]); TAGS = [a for a in args[1:] if not a.startswith('--')]
MM = 1e6
ds = B.GetDesignSettings(); CLR = ds.m_MinClearance; HCLR = ds.m_HoleClearance; H2H = ds.m_HoleToHoleMin
EDGE = ds.m_CopperEdgeClearance
VIAS = [(600000, 300000), (450000, 200000)]
DIRS = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]
tracks = list(B.GetTracks())
pads = [p for f in B.GetFootprints() for p in f.Pads()]
edge_shapes = [d for d in B.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts]
# crystal/inductor courtyards (F.Cu mounted) - rectangles from the courtyard shapes' own end points (no BOX2I.Merge)
ci = []
for f in B.GetFootprints():
    ref = f.GetReference()
    if not re.match(r'^[YXL]\d+$', ref):
        continue
    xs, ys = [], []
    for it in f.GraphicalItems():
        if it.GetClass() == 'PCB_SHAPE' and it.GetLayer() in (pcbnew.F_CrtYd, pcbnew.B_CrtYd):
            for q in (it.GetStart(), it.GetEnd()):
                xs.append(q.x); ys.append(q.y)
    if xs:
        ci.append((ref, f.GetLayer(), min(xs), min(ys), max(xs), max(ys), {p.GetNetCode() for p in f.Pads()}))
holes = [(t.GetPosition(), t.GetDrill() // 2, t.GetNetCode()) for t in tracks if t.GetClass() == 'PCB_VIA']
# rule areas that forbid tracks or vias - top-level and footprint-internal (the stitchers did not read them)
kos = [B.GetArea(i) for i in range(B.GetAreaCount()) if B.GetArea(i).GetIsRuleArea()]
kos += [z for f in B.GetFootprints() for z in f.Zones() if z.GetIsRuleArea()]
kos = [z for z in kos if z.GetDoNotAllowTracks() or z.GetDoNotAllowVias()]
holes += [(p.GetPosition(), max(p.GetDrillSize().x, p.GetDrillSize().y) // 2, p.GetNetCode()) for p in pads if p.GetDrillSize().x > 0]


def disc(c, r):
    # a circle as a zero-length segment of width 2r: SWIG's SHAPE_CIRCLE.Collide accepts only a bare SEG
    return pcbnew.SHAPE_SEGMENT(c, c, int(2 * r))


def near(pos, item, r=2 * MM):
    # by bounding box, NOT GetPosition(): a track's position is its start point, so a long track passing right
    # beside the probe was skipped (measured: 3 shorts on the first copy run)
    bb = item.GetBoundingBox()
    return bb.GetLeft() - r <= pos.x <= bb.GetRight() + r and bb.GetTop() - r <= pos.y <= bb.GetBottom() + r


def shape_ok(shape, layer, net, pos, drill_r=0):
    for o in tracks:
        if o.GetNetCode() == net or not o.IsOnLayer(layer) or not near(pos, o):
            continue
        if shape.Collide(o.GetEffectiveShape(layer), CLR - 1):
            return False
        # the new drill against other-net tracks: hole clearance, not only copper clearance (ServiceOne
        # 2026-10-04: 9 hole_clearance warnings at 0.225-0.253 mm)
        if drill_r and disc(pos, drill_r).Collide(o.GetEffectiveShape(layer), HCLR - 1):
            return False
    for p in pads:
        if p.GetNetCode() == net or not p.IsOnLayer(layer) or not near(pos, p):
            continue
        ps = p.GetEffectiveShape(layer)
        if shape.Collide(ps, CLR - 1):
            return False
        if drill_r and disc(pos, drill_r).Collide(ps, HCLR - 1):
            return False
    for c, r, n in holes:
        if r <= 0 or (c - pos).EuclideanNorm() > 8 * MM:
            continue
        if n != net and shape.Collide(disc(c, r), HCLR - 1):
            return False
        # hole-to-hole is a fabrication limit for ANY two drills, same net included (ServiceOne 2026-10-04:
        # two GND vias placed 0.09 mm apart when same-net holes were skipped)
        if drill_r and (c - pos).EuclideanNorm() - r - drill_r < H2H - 1:
            return False
    for z in kos:
        if (layer is None or z.IsOnLayer(layer)) and z.Outline().Collide(shape, 0):
            return False
    for e in edge_shapes:
        if shape.Collide(e.GetEffectiveShape(), EDGE - 1):
            return False
    return True


def in_ci(x, y, layer, net):
    for ref, lay, x0, y0, x1, y1, own in ci:
        if lay == layer and net not in own and x0 <= x <= x1 and y0 <= y <= y1:
            return ref
    return None


def seg_ci(a, b, layer, net, n=20):
    return any(in_ci(a.x + (b.x - a.x) * k / n, a.y + (b.y - a.y) * k / n, layer, net) for k in range(n + 1))


def find(p):
    c = p.GetPosition(); net = p.GetNetCode(); layer = pcbnew.F_Cu if p.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu
    wn = min(p.GetSizeX(), p.GetSizeY(), 400000)
    best = None
    for vd, vdr in VIAS:
        for d1 in DIRS:
            n1 = math.hypot(*d1)
            for L1 in range(300000, 3000001, 100000):
                a = pcbnew.VECTOR2I(int(c.x + d1[0] / n1 * L1), int(c.y + d1[1] / n1 * L1))
                if abs(abs(a.x - c.x) - abs(a.y - c.y)) > 2 and a.x != c.x and a.y != c.y:
                    continue
                s1 = pcbnew.SHAPE_SEGMENT(c, a, wn)
                if seg_ci(c, a, layer, net) or not shape_ok(s1, layer, net, a):
                    break                                   # a longer first leg in this direction is no better
                # entry rule 8: inside the pad's clearance area the track is ONE straight segment through the
                # centre, so a bend is allowed only once the first leg has fully left pad + clearance
                bend_ok = not disc(a, wn // 2).Collide(p.GetEffectiveShape(layer), CLR)
                # 45-degree bends only (no 90-degree corners: the standard mitres corners, and a square joint
                # beside a pad produced a 0.079 mm connection_width neck)
                turn45 = [d for d in DIRS if abs(d[0] * d1[0] + d[1] * d1[1]) > 0 and d != d1 and d != (-d1[0], -d1[1])
                          and (d[0] * d1[0] + d[1] * d1[1]) > 0]
                for d2 in [None] + (turn45 if bend_ok else []):
                    for L2 in ([0] if d2 is None else range(200000, 2000001, 100000)):
                        if d2 is None:
                            v = a
                        else:
                            n2 = math.hypot(*d2)
                            v = pcbnew.VECTOR2I(int(a.x + d2[0] / n2 * L2), int(a.y + d2[1] / n2 * L2))
                        total = L1 + L2
                        if best and total >= best[0]:
                            continue
                        if d2 is not None:
                            s2 = pcbnew.SHAPE_SEGMENT(a, v, wn)
                            if seg_ci(a, v, layer, net) or not shape_ok(s2, layer, net, v):
                                break
                        if in_ci(v.x, v.y, pcbnew.F_Cu, net):
                            continue
                        vs = disc(v, vd // 2)
                        # no via-in-pad: the via's copper must stay fully outside EVERY pad of its own net too
                        # (shape_ok skips same-net items, which let a 0.6 via sit inside its 0.9 mm pad)
                        if any(q.GetNetCode() == net and q.IsOnLayer(pcbnew.F_Cu) and near(v, q, 4 * MM)
                               and vs.Collide(q.GetEffectiveShape(pcbnew.F_Cu), 0) for q in pads):
                            continue
                        if not (shape_ok(vs, pcbnew.F_Cu, net, v, vdr // 2) and shape_ok(vs, pcbnew.B_Cu, net, v, vdr // 2)):
                            continue
                        best = (total, vd, vdr, a, v, d2 is not None, wn)
        if best:
            break                                           # prefer the larger via when any position fits
    return layer, best


def pad_of(tag):
    ref, num = tag.rsplit('-', 1)
    return [q for q in B.FindFootprintByReference(ref).Pads() if q.GetNumber() == num][0]


placed = 0
for tag in TAGS:
    p = pad_of(tag); layer, best = find(p)
    if not best:
        print('  %-8s %-6s no position found' % (tag, p.GetNetname())); continue
    total, vd, vdr, a, v, dog, wn = best
    c = p.GetPosition()
    print('  %-8s %-6s via %.2f/%.2f at (%.4f, %.4f)  stub %.3f mm %s  width %.3f' % (tag, p.GetNetname(), vd / MM, vdr / MM, v.x / MM, v.y / MM,
          total / MM, '(dogleg via %.4f,%.4f)' % (a.x / MM, a.y / MM) if dog else '(straight)', wn / MM))
    if APPLY:
        pts = [c, a, v] if dog else [c, v]
        for s_, e_ in zip(pts, pts[1:]):
            t = pcbnew.PCB_TRACK(B); t.SetStart(s_); t.SetEnd(e_); t.SetWidth(wn); t.SetLayer(layer); t.SetNetCode(p.GetNetCode()); t.SetLocked(True); B.Add(t); tracks.append(t)
        vv = pcbnew.PCB_VIA(B); vv.SetPosition(v); vv.SetWidth(vd); vv.SetDrill(vdr); vv.SetViaType(pcbnew.VIATYPE_THROUGH)
        vv.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); vv.SetNetCode(p.GetNetCode()); vv.SetRemoveUnconnected(True); vv.SetKeepStartEnd(True); vv.SetLocked(True)
        B.Add(vv); tracks.append(vv); holes.append((v, vdr // 2, p.GetNetCode()))
    placed += 1
print('placed %d of %d' % (placed, len(TAGS)))
if APPLY and placed:
    print('fill:', zone_fill_check.refill(B)); B.Save(args[0]); print('saved')
elif not APPLY:
    print('dry run - not saved')
