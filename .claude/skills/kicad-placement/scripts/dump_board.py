#!/usr/bin/env python3
"""
Dumps a board's outline and footprint courtyards to JSON for render_placement.py (run with KiCad's Python).

Usage:
    <kicad-python> dump_board.py placed.kicad_pcb dump.json
"""
import json, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew  # noqa: E402
from placement_core import mm  # noqa: E402


def main():
    b = pcbnew.LoadBoard(sys.argv[1])
    out = dict(edges=[], fps=[])
    for d in b.GetDrawings():
        if d.GetLayerName() != "Edge.Cuts":
            continue
        s = d.GetShapeStr() if hasattr(d, "GetShapeStr") else ""
        if s == "Polygon":
            ps = d.GetPolyShape()
            pts = [(mm(ps.CVertex(i).x), mm(ps.CVertex(i).y)) for i in range(ps.TotalVertices())]
            out["edges"].append(pts + pts[:1])
        elif s == "Circle":
            c, r = d.GetCenter(), mm(d.GetRadius())
            out["edges"].append([(mm(c.x) + r * math.cos(k * math.pi / 36), mm(c.y) + r * math.sin(k * math.pi / 36)) for k in range(73)])
        elif s == "Arc":
            out["edges"].append([(mm(q.x), mm(q.y)) for q in (d.GetStart(), d.GetArcMid(), d.GetEnd())])
        else:
            out["edges"].append([(mm(d.GetStart().x), mm(d.GetStart().y)), (mm(d.GetEnd().x), mm(d.GetEnd().y))])
    for f in b.GetFootprints():
        cy = f.GetCourtyard(pcbnew.F_CrtYd)
        polys = []
        for k in range(cy.OutlineCount()):
            o = cy.Outline(k)
            polys.append([(mm(o.CPoint(i).x), mm(o.CPoint(i).y)) for i in range(o.PointCount())])
        r = f.GetBoundingBox(False)
        out["fps"].append(dict(ref=f.GetReference(), x=mm(f.GetPosition().x), y=mm(f.GetPosition().y),
                               rot=f.GetOrientationDegrees(), crt=polys, locked=f.IsLocked(), bottom=f.IsFlipped(),
                               bb=(mm(r.GetLeft()), mm(r.GetTop()), mm(r.GetRight()), mm(r.GetBottom()))))
    json.dump(out, open(sys.argv[2], "w"))
    print(f"{len(out['fps'])} footprints, {len(out['edges'])} edge shapes -> {sys.argv[2]}")


if __name__ == "__main__":
    main()
