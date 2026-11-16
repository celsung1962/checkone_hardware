#!/usr/bin/env python3
"""
Placement rule check of a board against its plan (run with KiCad's Python). Independent of the placer: it
re-reads the board and measures. Exit 1 on any hard failure.

Spacing: courtyard bounding boxes first, exact courtyard polygons when the boxes are too close (rotated or
L-shaped courtyards). Hard checks: every movable part on the top side; rotations multiple of 90; origins on the placement grid;
courtyard-to-courtyard gap >= spacing (>= tht_spacing next to through-hole parts, >= mech_spacing next to
holes and fixed mechanical parts); courtyard >= edge clearance from Edge.Cuts (sensitive parts: fine-pitch ICs,
MLCC > 0805, crystals: >= sensitive clearance); no part in a keep-out it is excluded from.
Near (plan "near", hard): datasheet proximity rules - pad-to-pad distance between "a" and "b" (REF.PAD or REF)
<= max_mm: oscillator at its clock pin, shunt beside its current monitor, USB series parts at the MCU, ADC input
filter capacitors at the pins, converter inductor at its switch pin. make_plan.py suggests candidates.
Reported (judgement): decoupling distance pad-to-pad for every recognised decoupling capacitor (<= 2 mm is the
target; with 0.3 mm courtyard spacing 2.0-2.6 mm is usually the practical minimum); heat sources vs sensitive
parts (heat / heat_sensitive / heat_min_distance in the plan; aluminium electrolytics are heat-sensitive by default,
1.2.0); parts outside the outline.
Warnings (1.2.0, never fail the board; thresholds in the plan): test-point access ("testpoints": probe pitch between
test-point pads, pad to any other courtyard, pad to Edge.Cuts, all on one side) and polarity marks ("polarity": every
polarised part keeps a silkscreen graphic that no other courtyard covers).

Usage:
    <kicad-python> verify_placement.py plan.json [--board placed.kicad_pcb] [--json out.json]
"""
import argparse, json, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew  # noqa: E402
from placement_core import (mm, load_plan, fixed_refs, courtyard_rect, is_tht, min_smd_pitch, matches,  # noqa: E402
                            assign_decaps, is_artwork, footprint_keepouts, artwork_keepouts, near_distance,
                            heat_sensitive_refs, is_polarised, silk_marks)


def gap(a, c):
    dx = max(c[0] - a[2], a[0] - c[2], 0.0)
    dy = max(c[1] - a[3], a[1] - c[3], 0.0)
    if dx > 0 and dy > 0:
        return math.hypot(dx, dy)
    return max(dx, dy) if (dx or dy) else -1.0


def poly_gap(fa, fb):
    """Exact courtyard distance (mm): -1 if the polygons overlap, else the smallest vertex-to-polygon distance
    both ways. None when a footprint has no courtyard."""
    ca, cb = fa.GetCourtyard(pcbnew.F_CrtYd), fb.GetCourtyard(pcbnew.F_CrtYd)
    if not (ca.OutlineCount() and cb.OutlineCount()):
        return None
    inter = pcbnew.SHAPE_POLY_SET(ca)
    inter.BooleanIntersection(cb)
    if inter.Area() > 0:
        return -1.0
    best = None
    for src, dst in ((ca, cb), (cb, ca)):
        for k in range(src.OutlineCount()):
            o = src.Outline(k)
            for i in range(o.PointCount()):
                d = math.sqrt(dst.SquaredDistance(o.CPoint(i)))
                best = d if best is None or d < best else best
    return mm(best)


def edge_segments(b):
    segs = []
    for d in b.GetDrawings():
        if d.GetLayerName() != "Edge.Cuts":
            continue
        s = d.GetShapeStr() if hasattr(d, "GetShapeStr") else ""
        if s == "Polygon":
            ps = d.GetPolyShape()
            pts = [(mm(ps.CVertex(i).x), mm(ps.CVertex(i).y)) for i in range(ps.TotalVertices())]
            segs += list(zip(pts, pts[1:] + pts[:1]))
        elif s in ("Circle",):
            c, r = d.GetCenter(), mm(d.GetRadius())
            pts = [(mm(c.x) + r * math.cos(k * math.pi / 36), mm(c.y) + r * math.sin(k * math.pi / 36)) for k in range(72)]
            segs += list(zip(pts, pts[1:] + pts[:1]))
        elif s in ("Arc",):
            pts = [(mm(q.x), mm(q.y)) for q in (d.GetStart(), d.GetArcMid(), d.GetEnd())]
            segs += list(zip(pts, pts[1:]))
        else:
            segs.append(((mm(d.GetStart().x), mm(d.GetStart().y)), (mm(d.GetEnd().x), mm(d.GetEnd().y))))
    return segs


def pseg(p, a, c):
    vx, vy = c[0] - a[0], c[1] - a[1]
    L = vx * vx + vy * vy or 1e-12
    t = max(0.0, min(1.0, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / L))
    return math.hypot(p[0] - a[0] - t * vx, p[1] - a[1] - t * vy)


def edge_dist(r, segs):
    for a, c in segs:
        for p in (a, c):
            if r[0] <= p[0] <= r[2] and r[1] <= p[1] <= r[3]:
                return 0.0
    pts = [(r[0], r[1]), (r[2], r[1]), (r[2], r[3]), (r[0], r[3])]
    samples = []
    for a, c in zip(pts, pts[1:] + pts[:1]):
        n = max(1, int(math.hypot(c[0] - a[0], c[1] - a[1]) / 0.1))
        samples += [(a[0] + (c[0] - a[0]) * k / n, a[1] + (c[1] - a[1]) * k / n) for k in range(n)]
    return min(pseg(p, a, c) for p in samples for a, c in segs)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plan")
    ap.add_argument("--board", help="board to check (default: the plan's board)")
    ap.add_argument("--json")
    a = ap.parse_args()
    plan = load_plan(a.plan)
    b = pcbnew.LoadBoard(a.board or plan["board"])
    fps = {f.GetReference(): f for f in b.GetFootprints()}
    fixed = fixed_refs(b, plan)
    movable = [r for r in fps if r not in fixed]
    bb = b.GetBoardEdgesBoundingBox()
    segs = edge_segments(b)
    s = plan["sensitive"]
    sens = {r for r in movable if (r.startswith("U") and min_smd_pitch(fps[r]) <= s["fine_pitch_max"])
            or r.startswith(tuple(s["prefixes"]))
            or (r.startswith("C") and any(p in fps[r].GetFPIDAsString() for p in s["mlcc_packages"]))}
    R = {r: courtyard_rect(f) for r, f in fps.items()}
    res = {k: [] for k in ("bottom", "rotation", "grid", "outside", "spacing", "edge", "sensitive_edge", "keepout", "near")}
    g = plan["grid"]
    art = artwork_keepouts(b, plan)
    for r in movable:
        f = fps[r]
        if not bb.Contains(f.GetPosition()):
            res["outside"].append(r)
            continue
        if f.IsFlipped():
            res["bottom"].append(r)
        if round(f.GetOrientationDegrees()) % 90:
            res["rotation"].append(r)
        x, y = mm(f.GetPosition().x), mm(f.GetPosition().y)
        if g and (abs(x / g - round(x / g)) > 1e-3 or abs(y / g - round(y / g)) > 1e-3):
            res["grid"].append(r)                      # "grid": null in the plan skips it (hand-placed boards)
        e = edge_dist(R[r], segs)
        if e < plan["edge_clearance"] - 1e-3:
            res["edge"].append([r, round(e, 2)])
        if r in sens and e < plan["sensitive_edge_clearance"] - 1e-3:
            res["sensitive_edge"].append([r, round(e, 2)])
        for k in (plan["keepouts"] + [{"name": "rule area", "rect": q} for q in footprint_keepouts(b)]
                  + [{"name": f"artwork {a}", "rect": q} for a, q in art]):
            q = k["rect"]
            if matches(r, k.get("refs", ["*"])) and gap(R[r], q) < 0:
                res["keepout"].append([r, k.get("name", "")])
    on = [r for r in fps if bb.Contains(fps[r].GetPosition()) and not is_artwork(fps[r])]
    min_gap = 99.0
    for i, p in enumerate(on):
        for q in on[i + 1:]:
            if p in fixed and q in fixed:
                continue
            bg = gap(R[p], R[q])
            if bg > 3:
                continue
            gg = bg                      # bounding boxes first (fast, conservative) ...
            mech0 = any((x in fixed and (is_tht(fps[x]) or x.startswith(("H", "MH")))) for x in (p, q))
            need0 = plan["mech_spacing"] if mech0 else (plan["tht_spacing"] if (is_tht(fps[p]) or is_tht(fps[q])) else plan["spacing"])
            if bg < need0:               # ... then the exact polygons (rotated / L-shaped courtyards)
                pg = poly_gap(fps[p], fps[q])
                gg = bg if pg is None else pg
            mech = any((x in fixed and (is_tht(fps[x]) or x.startswith(("H", "MH")))) for x in (p, q))
            need = plan["mech_spacing"] if mech else (plan["tht_spacing"] if (is_tht(fps[p]) or is_tht(fps[q])) else plan["spacing"])
            if gg < need - 0.02:
                res["spacing"].append([p, q, round(gg, 2), need])
            if not mech:
                min_gap = min(min_gap, gg)
    pt = json.load(open(plan["pintypes"])) if plan.get("pintypes") and os.path.exists(plan["pintypes"]) else {}
    sp = json.load(open(plan["schpos"])) if plan.get("schpos") and os.path.exists(plan["schpos"]) else {}
    dec = assign_decaps(fps, movable, pt, sp, plan["decap_max_sch_distance"])
    decap = []
    for c, (u, pin) in sorted(dec.items()):
        pad = next(pp for pp in fps[u].Pads() if pp.GetNumber() == pin)
        rail = pad.GetNetname()
        pos = [q.GetPosition() for q in fps[c].Pads() if q.GetNetname() == rail]
        d = min(math.hypot(mm(q.x - pad.GetPosition().x), mm(q.y - pad.GetPosition().y)) for q in pos)
        decap.append(dict(ic=u, cap=c, pin=pin, function=pt.get(f"{u}.{pin}", ["", "", ""])[1], dist=round(d, 2)))
    thermal = []
    hs = [c for c in heat_sensitive_refs(fps, plan) if c in fps]
    for h in plan["heat"]:
        if h in fps and hs:
            d, c = min((gap(R[h], R[c]), c) for c in hs)
            thermal.append(dict(heat=h, value=fps[h].GetValue(), nearest=c, gap=round(d, 1),
                                ok=d >= plan["heat_min_distance"]))
    near = []
    for n in plan.get("near", []):
        d = near_distance(fps, n["a"], n["b"])
        near.append(dict(n, dist=None if d is None else round(d, 2)))
        if d is None or d > n["max_mm"] + 1e-6:
            res["near"].append([n["a"], n["b"], None if d is None else round(d, 2), n["max_mm"]])
    # ---- warnings (1.2.0): test-point access and polarity marks
    warn = {"tp_pitch": [], "tp_to_part": [], "tp_to_edge": [], "tp_sides": [], "polarity_no_mark": [],
            "polarity_covered": []}
    tpp = plan["testpoints"]
    tps = [r for r in on if any(r.startswith(x) and r[len(x):len(x) + 1].isdigit() for x in tpp["prefixes"])]

    def pad_box(f):
        r = None
        for p in f.Pads():
            q = p.GetBoundingBox()
            box = (mm(q.GetLeft()), mm(q.GetTop()), mm(q.GetRight()), mm(q.GetBottom()))
            r = box if r is None else (min(r[0], box[0]), min(r[1], box[1]), max(r[2], box[2]), max(r[3], box[3]))
        return r
    P = {t: pad_box(fps[t]) for t in tps}
    for i, t in enumerate(tps):
        for u in tps[i + 1:]:
            c1 = ((P[t][0] + P[t][2]) / 2, (P[t][1] + P[t][3]) / 2)
            c2 = ((P[u][0] + P[u][2]) / 2, (P[u][1] + P[u][3]) / 2)
            dd = math.hypot(c1[0] - c2[0], c1[1] - c2[1])
            if dd < tpp["min_pitch"] - 1e-3:
                warn["tp_pitch"].append([t, u, round(dd, 2)])
        others = [r for r in on if r != t and r not in tps]
        dmin, who = min(((gap(P[t], R[r]), r) for r in others), default=(99.0, ""))
        if dmin < tpp["min_to_part"] - 1e-3:
            warn["tp_to_part"].append([t, who, round(dmin, 2)])
        e = edge_dist(P[t], segs)
        if e < tpp["min_to_edge"] - 1e-3:
            warn["tp_to_edge"].append([t, round(e, 2)])
    sides = {("bottom" if fps[t].IsFlipped() else "top") for t in tps}
    if tpp.get("one_side", True) and len(sides) > 1:
        warn["tp_sides"] = sorted(t for t in tps if fps[t].IsFlipped())
    for r in on:
        if r in fixed and r.startswith(("H", "MH")):
            continue
        if not is_polarised(r, fps[r], plan):
            continue
        marks = silk_marks(fps[r])
        if not marks:
            warn["polarity_no_mark"].append(r)
            continue
        others = [q for q in on if q != r]
        if all(any(gap(m, R[q]) < 0 and R[q][0] <= m[0] and R[q][1] <= m[1] and R[q][2] >= m[2] and R[q][3] >= m[3]
                   for q in others) for m in marks):
            warn["polarity_covered"].append(r)
    out = dict(hard=res, warn=warn, min_courtyard_gap=round(min_gap, 3), decoupling=decap, thermal=thermal, near=near,
               movable=len(movable), fixed=sorted(fixed))
    hard = sum(len(v) for v in res.values())
    for k, v in res.items():
        print(f"{k:15s} {len(v):4d} {v[:6]}")
    print(f"min courtyard gap (SMD/THT pairs): {min_gap:.3f} mm")
    if decap:
        ds = [x["dist"] for x in decap]
        print(f"decoupling: {len(ds)} caps; <= 2.0 mm {sum(d <= 2.0 for d in ds)}, <= 2.6 mm {sum(d <= 2.6 for d in ds)}, "
              f"<= 4 mm {sum(d <= 4 for d in ds)}; worst: "
              + ", ".join(f"{x['cap']}->{x['ic']}.{x['pin']} {x['dist']}" for x in sorted(decap, key=lambda x: -x["dist"])[:6]))
    else:
        print("decoupling: none recognised" + ("" if pt else " (give the plan a pintypes.json)"))
    bad_t = [t for t in thermal if not t["ok"]]
    if thermal:
        print(f"thermal: {len(thermal)} heat sources, min gap {min(t['gap'] for t in thermal)} mm; below "
              f"{plan['heat_min_distance']} mm: {[(t['heat'], t['nearest'], t['gap']) for t in bad_t]}")
    print(f"warnings (test points: pitch >= {tpp['min_pitch']}, to part >= {tpp['min_to_part']}, to edge >= "
          f"{tpp['min_to_edge']} mm; polarity marks):")
    for k, v in warn.items():
        print(f"  {k:17s} {len(v):4d} {v[:6]}")
    if a.json:
        json.dump(out, open(a.json, "w"), indent=1)
    print(f"\nPlacement rules: {'PASS' if hard == 0 else 'FAIL'} - {hard} hard violations")
    return 0 if hard == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
