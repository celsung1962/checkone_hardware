"""Extract a placement model (JSON) from a KiCad board.

Run with KiCad's own Python (it needs ``pcbnew``):

    "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" extract_model.py BOARD.kicad_pcb model.json

The model is everything the placer needs and nothing else, so the optimiser itself
never imports pcbnew and can run in plain worker processes:

  * board outline polygon and footprint keep-out polygons (mm)
  * per footprint: reference, sheet, side, locked flag, current position/rotation,
    courtyard rectangle and pad centres expressed in the footprint's own frame
    (i.e. as they would be at rotation 0)
  * which nets are carried by copper zones (planes)

Local frame convention (matches KiCad's RotatePoint, y pointing down):

    board = pos + ( lx*cos(a) + ly*sin(a),  -lx*sin(a) + ly*cos(a) )
"""
import json
import math
import sys

import pcbnew

MM = 1e6


def to_local(dx, dy, deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return dx * c - dy * s, dx * s + dy * c


def poly_points(poly):
    pts = []
    for i in range(poly.OutlineCount()):
        o = poly.Outline(i)
        for k in range(o.PointCount()):
            p = o.CPoint(k)
            pts.append((p.x, p.y))
    return pts


def bbox_corners(bb):
    x0, y0 = bb.GetX(), bb.GetY()
    x1, y1 = x0 + bb.GetWidth(), y0 + bb.GetHeight()
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def pt_in_poly(x, y, poly):
    inside = False
    n = len(poly)
    for a in range(n):
        x1, y1 = poly[a]
        x2, y2 = poly[(a + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def polys_touch(a, b):
    """True when two polygons overlap (vertex-in-polygon test, enough for drawn rooms)."""
    return any(pt_in_poly(x, y, b) for x, y in a) or any(pt_in_poly(x, y, a) for x, y in b)


def norm_sheet(s):
    return (s or "").strip().strip("/").lower()


def region_members(b, kind, source):
    """References of the footprints a placement rule area refers to."""
    refs = []
    if kind == "sheet":
        want = norm_sheet(source.rstrip("*"))
        prefix = source.endswith("*")
        for f in b.GetFootprints():
            got = norm_sheet(f.GetSheetname())
            if got == want or (prefix and got.startswith(want)):
                refs.append(f.GetReference())
    elif kind == "class":
        for f in b.GetFootprints():
            names = [s.strip() for s in (f.GetComponentClassAsString() or "").split(",")]
            if source in names:
                refs.append(f.GetReference())
    elif kind == "group":
        ids = set()
        for g in b.Groups():
            if g.GetName() == source:
                for it in g.GetItems():
                    ids.add(it.m_Uuid.AsString())
        for f in b.GetFootprints():
            if f.m_Uuid.AsString() in ids:
                refs.append(f.GetReference())
    return sorted(refs)


def extract_regions(b, outline):
    """Placement rule areas ("rooms"). Rule areas that share the same source are one
    region made of several polygons (their union). A polygon touching the board is a
    hard area; a region drawn entirely off the board is only a grouping directive.
    A rule area whose name starts with ISO_ also keeps every other footprint out."""
    kinds = {pcbnew.PLACEMENT_SOURCE_T_SHEETNAME: "sheet",
             pcbnew.PLACEMENT_SOURCE_T_COMPONENT_CLASS: "class",
             pcbnew.PLACEMENT_SOURCE_T_GROUP_PLACEMENT: "group"}
    regions = {}
    for z in b.Zones():
        if not z.GetIsRuleArea() or not z.GetPlacementAreaEnabled():
            continue
        kind = kinds.get(z.GetPlacementAreaSourceType())
        source = z.GetPlacementAreaSource()
        if kind is None or not source:
            continue
        r = regions.setdefault((kind, source), {"names": [], "kind": kind, "source": source,
                                                "exclusive": False, "polys": []})
        name = z.GetZoneName() or source
        if name not in r["names"]:
            r["names"].append(name)
        if name.upper().startswith("ISO_"):
            r["exclusive"] = True
        ls = z.GetLayerSet()
        top, bottom = ls.Contains(pcbnew.F_Cu), ls.Contains(pcbnew.B_Cu)
        if not top and not bottom:
            top = bottom = True
        zo = z.Outline()
        for i in range(zo.OutlineCount()):
            c = zo.Outline(i)
            pts = [[c.CPoint(k).x / MM, c.CPoint(k).y / MM] for k in range(c.PointCount())]
            r["polys"].append({"pts": pts, "top": top, "bottom": bottom,
                               "onboard": polys_touch(pts, outline)})
    out = []
    for (kind, source), r in sorted(regions.items()):
        r["name"] = "+".join(r.pop("names"))
        r["onboard"] = any(p["onboard"] for p in r["polys"])
        r["members"] = region_members(b, kind, source)
        out.append(r)
    return out


def extract(path):
    b = pcbnew.LoadBoard(path)

    outline_set = pcbnew.SHAPE_POLY_SET()
    if not b.GetBoardPolygonOutlines(outline_set, False) or outline_set.OutlineCount() == 0:
        raise SystemExit("board has no closed Edge.Cuts outline")
    # largest outline is the board
    best = max(range(outline_set.OutlineCount()), key=lambda i: outline_set.Outline(i).Area())
    o = outline_set.Outline(best)
    outline = [[o.CPoint(k).x / MM, o.CPoint(k).y / MM] for k in range(o.PointCount())]

    keepouts = []
    plane_nets = set()
    for z in b.Zones():
        if z.GetIsRuleArea():
            if z.GetDoNotAllowFootprints():
                zo = z.Outline()
                for i in range(zo.OutlineCount()):
                    c = zo.Outline(i)
                    keepouts.append({
                        "name": z.GetZoneName(),
                        "pts": [[c.CPoint(k).x / MM, c.CPoint(k).y / MM] for k in range(c.PointCount())],
                    })
        elif z.GetNetname():
            plane_nets.add(z.GetNetname())

    comps = []
    seen = {}
    skipped = []
    for f in b.GetFootprints():
        ref = f.GetReference()
        back = f.GetLayer() == pcbnew.B_Cu
        pos = f.GetPosition()
        deg = f.GetOrientationDegrees()

        pts = poly_points(f.GetCourtyard(pcbnew.B_CrtYd if back else pcbnew.F_CrtYd))
        cy_src = "courtyard"
        if not pts:
            pts = poly_points(f.GetCourtyard(pcbnew.F_CrtYd if back else pcbnew.B_CrtYd))
        if not pts:
            cy_src = "pads"
            for p in f.Pads():
                pts.extend(bbox_corners(p.GetBoundingBox()))
        if not pts:
            # no courtyard and no pads (logo, fiducial art): not a placement object
            skipped.append(ref)
            continue

        loc = [to_local(x - pos.x, y - pos.y, deg) for x, y in pts]
        rect = [min(p[0] for p in loc) / MM, min(p[1] for p in loc) / MM,
                max(p[0] for p in loc) / MM, max(p[1] for p in loc) / MM]

        pads = []
        through = False
        for p in f.Pads():
            th = p.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH)
            through = through or th
            pp = p.GetPosition()
            lx, ly = to_local(pp.x - pos.x, pp.y - pos.y, deg)
            bl = [to_local(x - pos.x, y - pos.y, deg) for x, y in bbox_corners(p.GetBoundingBox())]
            pads.append({"num": p.GetNumber(), "net": p.GetNetname(),
                         "x": lx / MM, "y": ly / MM, "th": th,
                         "bb": [min(q[0] for q in bl) / MM, min(q[1] for q in bl) / MM,
                                max(q[0] for q in bl) / MM, max(q[1] for q in bl) / MM]})

        if ref in seen:
            raise SystemExit("duplicate reference %r: annotate the board first" % ref)
        seen[ref] = True
        comps.append({
            "ref": ref,
            "value": f.GetValue(),
            "fp": f.GetFPID().GetUniStringLibItemName(),
            "sheet": f.GetSheetname() or "/",
            "back": back,
            "through": through,
            "locked": bool(f.IsLocked()),
            "x": pos.x / MM, "y": pos.y / MM, "rot": deg,
            "rect": rect,
            "rect_src": cy_src,
            "pads": pads,
        })

    comps.sort(key=lambda c: c["ref"])
    return {
        "board": path,
        "kicad": pcbnew.Version(),
        "copper_layers": b.GetCopperLayerCount(),
        "edge_clearance": b.GetDesignSettings().m_CopperEdgeClearance / MM,
        "outline": outline,
        "keepouts": keepouts,
        "regions": extract_regions(b, outline),
        "plane_nets": sorted(plane_nets),
        "skipped": skipped,
        "comps": comps,
    }


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: extract_model.py BOARD.kicad_pcb model.json")
    model = extract(sys.argv[1])
    with open(sys.argv[2], "w", encoding="utf-8") as fh:
        json.dump(model, fh)
    n = len(model["comps"])
    lk = sum(1 for c in model["comps"] if c["locked"])
    print("model: %d footprints (%d locked, %d free), %d keepouts, planes %s, skipped %s" % (
        n, lk, n - lk, len(model["keepouts"]), model["plane_nets"], model["skipped"]))
    for r in model["regions"]:
        print("region %s: %s=%s, %d members, %s%s" % (
            r["name"], r["kind"], r["source"], len(r["members"]),
            "on board (hard)" if r["onboard"] else "off board (group only)",
            ", exclusive" if r["exclusive"] else ""))
