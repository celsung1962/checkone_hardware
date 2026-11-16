#!/usr/bin/env python3
"""
Placement survey of a KiCad board (run with KiCad's Python). Read-only. Prints a Markdown report and writes
survey.json next to --out:

  1. outline: bounding box, area, cut-outs;
  2. EVERY text and drawing on Fab / User / Comments / Drawings / silkscreen layers - mechanical notes written
     on the board (which side carries the electronics, height limits, keep-outs) override generic instructions
     and must be read before placing anything;
  3. rule areas (keep-outs) and existing tracks / zones (a placement job must not touch them);
  4. footprints: fixed candidates (inside the outline or locked), parts outside the outline (to place), parts on
     the bottom side, largest courtyards;
  5. area budget: courtyard area + spacing halo per schematic sheet vs. free area (outline minus fixed parts,
     edge clearance and hole keep-outs). Above ~65-70 % utilisation a greedy placer starts to fail; above ~75 %
     the job is probably infeasible at the requested spacing -> report the deficit before placing.

Usage:
    <kicad-python> board_survey.py hardware/<p>.kicad_pcb [--plan plan.json] [--out build/placement]
"""
import argparse, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew  # noqa: E402
from placement_core import (mm, board_outline, courtyard_rect, courtyard_area, is_tht, sheet_of, DEFAULTS,  # noqa: E402
                            load_plan, fixed_refs, Raster, mark_fixed, zones)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("board")
    ap.add_argument("--plan", help="plan JSON (fixed patterns, spacing); defaults otherwise")
    ap.add_argument("--out", default=".")
    a = ap.parse_args()
    plan = load_plan(a.plan) if a.plan else dict(DEFAULTS)
    b = pcbnew.LoadBoard(a.board)
    bb = b.GetBoardEdgesBoundingBox()
    outline = board_outline(b)
    rep = {"board": os.path.abspath(a.board)}
    L, T, R, B = mm(bb.GetLeft()), mm(bb.GetTop()), mm(bb.GetRight()), mm(bb.GetBottom())
    rep["outline"] = dict(bbox=[round(v, 2) for v in (L, T, R, B)], area_mm2=round(outline.Area() / 1e12, 1),
                          holes_in_outline=sum(outline.HoleCount(i) for i in range(outline.OutlineCount())))
    print(f"# Placement survey - {os.path.basename(a.board)}\n")
    print(f"Outline: x {L:.2f}..{R:.2f}, y {T:.2f}..{B:.2f} ({R - L:.1f} x {B - T:.1f} mm), "
          f"area {rep['outline']['area_mm2']} mm2, internal cut-outs {rep['outline']['holes_in_outline']}\n")

    print("## Notes and drawings on non-copper layers (read them: they may override generic rules)\n")
    notes = []
    for d in b.GetDrawings():
        ln = d.GetLayerName()
        if d.GetClass() in ("PCB_TEXT", "PCB_TEXTBOX") and ln != "Edge.Cuts":
            p = d.GetPosition()
            notes.append(dict(layer=ln, x=round(mm(p.x), 1), y=round(mm(p.y), 1), text=d.GetText()))
            print(f"- [{ln}] ({mm(p.x):.1f}, {mm(p.y):.1f}) {d.GetText()!r}")
    shapes = {}
    for d in b.GetDrawings():
        if d.GetClass() == "PCB_SHAPE" and d.GetLayerName() not in ("Edge.Cuts",):
            shapes.setdefault(d.GetLayerName(), []).append(d)
    for ln, lst in shapes.items():
        boxes = [s.GetBoundingBox() for s in lst]
        print(f"- [{ln}] {len(lst)} shapes within x {min(mm(q.GetLeft()) for q in boxes):.1f}..{max(mm(q.GetRight()) for q in boxes):.1f}, "
              f"y {min(mm(q.GetTop()) for q in boxes):.1f}..{max(mm(q.GetBottom()) for q in boxes):.1f} "
              f"(outlines of covers, displays, keep-outs? check them)")
    rep["notes"] = notes
    zl = [dict(rule_area=z.GetIsRuleArea(), name=z.GetZoneName(),
                  bbox=[round(mm(v), 1) for v in (z.GetBoundingBox().GetLeft(), z.GetBoundingBox().GetTop(),
                                                    z.GetBoundingBox().GetRight(), z.GetBoundingBox().GetBottom())])
             for z in zones(b)]
    rep["zones"], rep["tracks"] = zl, len(b.GetTracks())
    print(f"\nZones / rule areas: {len(zl)} {zl[:6]}; tracks and vias: {rep['tracks']}\n")

    fixed = fixed_refs(b, plan)
    fps = {f.GetReference(): f for f in b.GetFootprints()}
    inside, outside, bottom = [], [], []
    for r, f in fps.items():
        (inside if bb.Contains(f.GetPosition()) else outside).append(r)
        if f.IsFlipped():
            bottom.append(r)
    movable = [r for r in fps if r not in fixed]
    rep.update(fixed=sorted(fixed), inside=sorted(inside), outside_count=len(outside), bottom=sorted(bottom),
               movable_count=len(movable))
    print("## Footprints\n")
    print(f"- total {len(fps)}; fixed (plan patterns or locked) {len(fixed)}: {', '.join(sorted(fixed))}")
    print(f"- inside the outline but NOT fixed: {sorted(set(inside) - fixed)}  <- decide: anchor or move")
    print(f"- outside the outline (to place): {len(outside)}; on the bottom side: {bottom}")
    big = sorted(((courtyard_area(fps[r]), r) for r in movable), reverse=True)[:12]
    print("- largest movable courtyards: " + ", ".join(f"{r} {fps[r].GetValue()} {a:.0f} mm2" for a, r in big))

    # area budget per sheet
    sp, tht_sp = plan["spacing"], plan["tht_spacing"]
    per = {}
    for r in movable:
        f = fps[r]
        l, t, rr, d = courtyard_rect(f)
        h = tht_sp if is_tht(f) else sp
        per.setdefault(sheet_of(f) or "?", [0, 0.0])
        per[sheet_of(f) or "?"][0] += 1
        per[sheet_of(f) or "?"][1] += (rr - l + h) * (d - t + h)
    ras = Raster(b, plan["grid"], plan["resolution"])
    occ = ras.empty()
    mark_fixed(ras, occ, b, fixed, plan)
    free = ras.inside(plan["edge_clearance"]) & ~occ
    free_area = ras.area(free)
    demand = sum(v[1] for v in per.values())
    rep.update(per_sheet={k: dict(parts=v[0], demand_mm2=round(v[1])) for k, v in per.items()},
               free_area_mm2=round(free_area), demand_mm2=round(demand), utilisation=round(demand / max(free_area, 1), 3))
    print("\n## Area budget (courtyard + spacing halo)\n")
    print("| Sheet | Parts | Demand mm2 |\n|---|---|---|")
    for k, v in sorted(per.items(), key=lambda kv: -kv[1][1]):
        print(f"| {k} | {v[0]} | {v[1]:.0f} |")
    u = demand / max(free_area, 1)
    verdict = ("comfortable" if u < 0.55 else "dense - plan regions carefully" if u < 0.70 else
               "very dense - expect failures; consider the other side or more area" if u < 0.78 else
               "probably infeasible at this spacing - STOP and report the deficit")
    print(f"\nFree area {free_area:.0f} mm2 (edge {plan['edge_clearance']} mm, fixed parts + {plan['mech_spacing']} mm); "
          f"demand {demand:.0f} mm2 -> utilisation {u:.0%}: {verdict}")
    os.makedirs(a.out, exist_ok=True)
    json.dump(rep, open(os.path.join(a.out, "survey.json"), "w"), indent=1)
    print(f"\nWritten {os.path.join(a.out, 'survey.json')}")


if __name__ == "__main__":
    main()
