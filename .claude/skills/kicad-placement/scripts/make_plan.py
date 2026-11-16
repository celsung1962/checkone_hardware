#!/usr/bin/env python3
"""
Writes a DRAFT placement plan for a board (run with KiCad's Python). The draft is a starting point, not a
floorplan: it knows areas, not signal flow. Edit it before placing (references/plan_format.md).

  - fixed: hole patterns, locked footprints and footprints already inside the outline (an engineer put them
    there - confirm each one: anchor or move?);
  - regions: the free area (inside the edge clearance, outside fixed parts + spacing) decomposed greedily into
    the largest empty rectangles;
  - blocks: one per schematic sheet (PCB sheet name), largest demand first, each given regions until its
    utilisation is about 60 %; then test points, fiducials and a catch-all block so no part is left out;
  - "near": empty, with "_near_suggestions" next to it: datasheet proximity candidates found in the netlist
    (oscillator / clock pin, shunt / current monitor, USB series parts / MCU, ADC input capacitors, converter
    inductor / switch pin). Copy the ones that apply into "near"; verify_placement.py checks them;
  - "_todo": what the agent must decide by hand (signal flow from the connectors, parts that belong next to a
    connector, heat sources vs. sensitive parts, height keep-outs, anchors).

Usage:
    <kicad-python> make_plan.py hardware/<p>.kicad_pcb --out build/placement/plan.json
        [--pintypes build/placement/pintypes.json] [--schpos build/placement/schpos.json] [--fixed "J*,SW*,BT*"]
"""
import argparse, json, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew  # noqa: E402
import numpy as np  # noqa: E402
from placement_core import (mm, DEFAULTS, Raster, mark_fixed, fixed_refs, courtyard_rect, is_tht, sheet_of,  # noqa: E402
                            suggest_near)


def largest_rect(free):
    """Largest all-True axis-aligned rectangle in a boolean grid (histogram method). Returns (area, i0, j0, i1, j1)."""
    H, W = free.shape
    heights = np.zeros(W, int)
    best = (0, 0, 0, 0, 0)
    for j in range(H):
        heights = np.where(free[j], heights + 1, 0)
        stack = []
        for i in range(W + 1):
            h = heights[i] if i < W else 0
            start = i
            while stack and stack[-1][1] >= h:
                s, sh = stack.pop()
                area = sh * (i - s)
                if area > best[0]:
                    best = (area, s, j - sh + 1, i, j + 1)
                start = s
            stack.append((start, h))
    return best


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("board"); ap.add_argument("--out", required=True)
    ap.add_argument("--pintypes"); ap.add_argument("--schpos")
    ap.add_argument("--fixed", default="", help="extra fixed patterns, e.g. J*,SW*,BT*")
    ap.add_argument("--max-regions", type=int, default=24)
    a = ap.parse_args()
    plan = json.loads(json.dumps(DEFAULTS))
    plan["fixed"] = plan["fixed"] + [p for p in a.fixed.split(",") if p]
    b = pcbnew.LoadBoard(a.board)
    bb = b.GetBoardEdgesBoundingBox()
    fps = {f.GetReference(): f for f in b.GetFootprints()}
    inside_unlocked = sorted(r for r, f in fps.items() if bb.Contains(f.GetPosition()) and not f.IsLocked()
                             and r not in fixed_refs(b, plan))
    plan["fixed"] += inside_unlocked
    fixed = fixed_refs(b, plan)
    off = sorted(r for r in fixed if not bb.Contains(fps[r].GetPosition()))
    if off:
        print(f"WARNING: fixed but OUTSIDE the outline (they will not be placed - narrow the patterns?): {off}")
    ras = Raster(b, plan["grid"], plan["resolution"])
    occ = ras.empty()
    mark_fixed(ras, occ, b, fixed, plan)
    free = ras.inside(plan["edge_clearance"]) & ~occ
    # regions on a 0.5 mm grid for speed
    step = 10                                                           # 10 x 0.05 mm
    coarse = free[: free.shape[0] // step * step, : free.shape[1] // step * step]
    coarse = coarse.reshape(coarse.shape[0] // step, step, coarse.shape[1] // step, step).all(axis=(1, 3))
    regions, rem, total = {}, coarse.copy(), coarse.sum()
    while len(regions) < a.max_regions:
        area, i0, j0, i1, j1 = largest_rect(rem)
        if area * 0.25 < 25 or rem.sum() < 0.03 * total:              # < 25 mm2 or < 3 % of the free area left
            break
        rem[j0:j1, i0:i1] = False
        x0, y0 = ras.X0 + i0 * 0.5, ras.Y0 + j0 * 0.5
        regions[f"R{len(regions) + 1}"] = [[round(x0, 2), round(y0, 2), round(x0 + (i1 - i0) * 0.5, 2), round(y0 + (j1 - j0) * 0.5, 2)]]
    plan["regions"] = regions
    cap = {k: (v[0][2] - v[0][0]) * (v[0][3] - v[0][1]) for k, v in regions.items()}
    movable = [r for r in fps if r not in fixed]
    sheets = {}
    for r in movable:
        if r.startswith(("TP", "FID")):
            continue
        f = fps[r]
        l, t, rr, d = courtyard_rect(f)
        h = plan["tht_spacing"] if is_tht(f) else plan["spacing"]
        s = sheet_of(f) or "?"
        sheets.setdefault(s, 0.0)
        sheets[s] += (rr - l + h) * (d - t + h)
    blocks, left = [], dict(cap)
    # target utilisation ~0.6, raised to the real ratio when the regions cannot give every block 0.6 (otherwise
    # the last blocks get crumbs); +3 % so rounding does not starve the last block
    util = max(0.6, min(0.95, sum(sheets.values()) / max(sum(cap.values()), 1) + 0.03))
    ctr = {k: ((v[0][0] + v[0][2]) / 2, (v[0][1] + v[0][3]) / 2) for k, v in regions.items()}
    for s, dem in sorted(sheets.items(), key=lambda kv: -kv[1]):
        got, need = [], dem / util
        while need > 0:
            avail = [k for k in left if left[k] > 1 and k not in got]
            if not avail:
                break
            if not got:                                                 # seed: the largest region left
                k = max(avail, key=lambda k: left[k])
            else:                                                       # then the nearest to the seed (locality)
                sx, sy = ctr[got[0]]
                k = min(avail, key=lambda k: abs(ctr[k][0] - sx) + abs(ctr[k][1] - sy))
            take = min(left[k], need)
            if take < left[k] - 20:                                     # partial: cut a slice off the long side so
                x0, y0, x1, y1 = regions[k][0]                          # the next block gets its own rectangle (a
                w, h = x1 - x0, y1 - y0                                 # shared rectangle is filled by whichever
                if w >= h:                                              # block is placed first)
                    cut = x0 + max(math.ceil(take / h * 2) / 2, 2.0)   # round UP: a 0-wide slice loops
                    piece, rest = [x0, y0, cut, y1], [cut, y0, x1, y1]
                else:
                    cut = y0 + max(math.ceil(take / w * 2) / 2, 2.0)
                    piece, rest = [x0, y0, x1, cut], [x0, cut, x1, y1]
                n = 1
                while f"{k}{chr(96 + n)}" in regions:
                    n += 1
                k2 = f"{k}{chr(96 + n)}"
                regions[k2] = [piece]; regions[k] = [rest]
                cap[k2] = (piece[2] - piece[0]) * (piece[3] - piece[1])
                left[k] = (rest[2] - rest[0]) * (rest[3] - rest[1]); cap[k] = left[k]
                ctr[k] = ((rest[0] + rest[2]) / 2, (rest[1] + rest[3]) / 2)
                ctr[k2] = ((piece[0] + piece[2]) / 2, (piece[1] + piece[3]) / 2)
                got.append(k2); need -= cap[k2]
            else:
                got.append(k); need -= left[k]; left[k] = 0
        if not got:
            got = [max(cap, key=cap.get)]
        rects = [regions[k][0] for k in got]
        box = [min(r[0] for r in rects), min(r[1] for r in rects), max(r[2] for r in rects), max(r[3] for r in rects)]
        blocks.append(dict(name=s, select={"sheet": s, "exclude": ["TP*", "FID*"]}, box=box, regions=got,
                           _demand_mm2=round(dem)))
    blocks.append(dict(name="Test points", select={"prefix": ["TP"]}))
    blocks.append(dict(name="Fiducials", select={"prefix": ["FID"]}))
    blocks.append(dict(name="Everything else", select={"all": True}))
    plan["blocks"] = blocks
    plan["board"] = os.path.relpath(os.path.abspath(a.board), os.path.dirname(os.path.abspath(a.out)))
    for k in ("pintypes", "schpos"):
        if getattr(a, k):
            plan[k] = os.path.relpath(os.path.abspath(getattr(a, k)), os.path.dirname(os.path.abspath(a.out)))
    fpmap = {f.GetReference(): f for f in b.GetFootprints()}
    _pt = json.load(open(a.pintypes, encoding="utf-8")) if a.pintypes and os.path.exists(a.pintypes) else {}
    plan["near"] = []
    plan["_near_suggestions"] = suggest_near(fpmap, _pt)
    plan["_todo"] = [
        "read the layout section of every IC datasheet; copy the _near_suggestions that apply into near (and add "
        "the ones the netlist cannot show), then give those parts anchors so the placer meets them",
        f"confirm fixed parts already inside the outline: {inside_unlocked}",
        "no fixed pattern may catch a part that is still outside the outline (it would never be placed)",
        "order blocks by signal flow from the fixed connectors; split a sheet into several blocks where it holds "
        "several functions (input channels per channel, battery side vs. regulators, ...)",
        "move connector-side parts (TVS, ESD, PPTC, connector rail capacitors) into a small block next to the "
        "connector, placed first",
        "heat sources (regulators, switches, shunts, power transistors) and sensitive parts (ADC, references, "
        "crystals, front-ends) in different regions; fill heat / heat_sensitive (aluminium electrolytics are added "
        "automatically); set testpoints / polarity from whoever tests and reworks the board",
        "tall parts outside height-limited areas (displays, covers): keepouts with refs",
        "check every region is reachable by its block's nets (no block split across the board)",
    ]
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    json.dump(plan, open(a.out, "w", encoding="utf-8"), indent=1)
    free_a = ras.area(free)
    print(f"draft plan -> {a.out}: {len(regions)} regions covering {sum(cap.values()):.0f} of {free_a:.0f} mm2 free, "
          f"{len(blocks)} blocks, {len(fixed)} fixed ({len(inside_unlocked)} unlocked parts inside the outline)")
    print(f"target utilisation per block {util:.2f}")
    if util > 0.65:
        print("WARNING: above 0.65 the placer starts to spill parts out of their blocks - add area (other side, "
              "smaller parts), merge small regions by hand or accept spills; say so in the report")
    for blk in blocks[:-3]:
        print(f"  {blk['name']:24s} demand {blk['_demand_mm2']:6d} mm2 -> regions {blk['regions']}")


if __name__ == "__main__":
    main()
