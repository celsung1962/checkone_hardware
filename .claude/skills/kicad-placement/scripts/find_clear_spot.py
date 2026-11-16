#!/usr/bin/env python3
"""
Finds a clear spot for board artwork - a silkscreen text (title, revision) or an artwork footprint (logo + title
block) - and optionally places it (run with KiCad's Python).

Clear = the artwork's bounding box plus --margin touches no pad on that side (through-hole pads count on both
sides), no courtyard of a part on that side, no hole, no other silkscreen item on that side, and stays
>= --edge from the board edge. On a dense top side there is often no room for a title at a readable size: try
the bottom side (usually empty of parts), a smaller font (JLCPCB minimum height 1.0 mm, stroke 0.15 mm) or
two lines - and ask before shrinking.

Usage:
    <kicad-python> find_clear_spot.py board.kicad_pcb --text "MAIN BOARD V1.0" --size 1.6 [--side top|bottom]
        [--target X,Y] [--margin 0.5] [--edge 1.0] [--replace-text "OLD TITLE"] [--out new.kicad_pcb]
    <kicad-python> find_clear_spot.py board.kicad_pcb --footprint path/to/Lib.pretty:Logo --side bottom
        [--field Board="MAIN BOARD"] [--field Version="V1.0 10/26"] [--ref LOGO1] [--out new.kicad_pcb]
Without --out it only reports the best spot.
"""
import argparse, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew  # noqa: E402
from placement_core import mm, FM, board_outline  # noqa: E402


def load_footprint(spec):
    lib, name = spec.rsplit(":", 1)
    io = pcbnew.PCB_IO_MGR.FindPlugin(pcbnew.PCB_IO_MGR.KICAD_SEXP)
    fp = io.FootprintLoad(lib, name)
    fp.SetFPID(pcbnew.LIB_ID(os.path.splitext(os.path.basename(lib))[0], name))
    return fp


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("board")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--text"); g.add_argument("--footprint")
    ap.add_argument("--size", type=float, default=1.6, help="text height (mm)")
    ap.add_argument("--side", choices=("top", "bottom"), default="top")
    ap.add_argument("--target", default="0,0", help="preferred position X,Y (mm)")
    ap.add_argument("--margin", type=float, default=0.5); ap.add_argument("--edge", type=float, default=1.0)
    ap.add_argument("--field", action="append", default=[], help='footprint field, e.g. Version="V1.0"')
    ap.add_argument("--ref", default="LOGO1")
    ap.add_argument("--replace-text", help="remove this existing silkscreen text (the old title)")
    ap.add_argument("--out")
    a = ap.parse_args()
    b = pcbnew.LoadBoard(a.board)
    bottom = a.side == "bottom"
    silk = pcbnew.B_SilkS if bottom else pcbnew.F_SilkS
    cu = pcbnew.B_Cu if bottom else pcbnew.F_Cu
    # the artwork item
    if a.text:
        item = pcbnew.PCB_TEXT(b)
        item.SetText(a.text); item.SetLayer(silk)
        item.SetTextSize(pcbnew.VECTOR2I(FM(a.size), FM(a.size))); item.SetTextThickness(FM(max(0.15, a.size * 0.15)))
        if bottom:
            item.SetMirrored(True)
        b.Add(item)
    else:
        item = load_footprint(a.footprint)
        item.SetReference(a.ref)
        for fdef in a.field:
            k, v = fdef.split("=", 1)
            for fl in item.GetFields():
                if fl.GetName() == k:
                    fl.SetText(v.strip('"'))
        b.Add(item)
        item.SetPosition(pcbnew.VECTOR2I(0, 0))
        if bottom:
            try:
                item.Flip(item.GetPosition(), pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
            except (AttributeError, TypeError):
                item.Flip(item.GetPosition(), False)
    item.SetPosition(pcbnew.VECTOR2I(0, 0))

    def ext():
        if a.text:
            r = item.GetBoundingBox()
            return mm(r.GetLeft()), mm(r.GetTop()), mm(r.GetRight()), mm(r.GetBottom())
        xs, ys = [], []
        for it in list(item.GraphicalItems()) + [f for f in item.GetFields() if f.IsVisible()]:
            r = it.GetBoundingBox(); xs += [mm(r.GetLeft()), mm(r.GetRight())]; ys += [mm(r.GetTop()), mm(r.GetBottom())]
        return min(xs), min(ys), max(xs), max(ys)
    e0 = ext()
    obst = []
    old = []
    for f in b.GetFootprints():
        if f is item:
            continue
        for p in f.Pads():
            ls = p.GetLayerSet()
            if ls.Contains(cu) or p.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH):
                r = p.GetBoundingBox(); obst.append((mm(r.GetLeft()), mm(r.GetTop()), mm(r.GetRight()), mm(r.GetBottom())))
        if f.IsFlipped() == bottom:
            cy = f.GetCourtyard(pcbnew.B_CrtYd if bottom else pcbnew.F_CrtYd)
            r = cy.BBox() if cy.OutlineCount() else None
            if r is not None:
                obst.append((mm(r.GetLeft()), mm(r.GetTop()), mm(r.GetRight()), mm(r.GetBottom())))
    for d in b.GetDrawings():
        if d is item:
            continue
        if d.GetLayer() == silk:
            if a.replace_text and d.GetClass() == "PCB_TEXT" and d.GetText() == a.replace_text:
                old.append(d); continue
            r = d.GetBoundingBox(); obst.append((mm(r.GetLeft()), mm(r.GetTop()), mm(r.GetRight()), mm(r.GetBottom())))
    poly = board_outline(b)
    try:
        poly.Inflate(FM(-a.edge), pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, FM(0.05))
    except (AttributeError, TypeError):
        poly.Inflate(FM(-a.edge), 16)
    bb = b.GetBoardEdgesBoundingBox()
    tx, ty = (float(v) for v in a.target.split(","))
    M = a.margin

    def ok(cx, cy):
        x0, y0, x1, y1 = cx + e0[0] - M, cy + e0[1] - M, cx + e0[2] + M, cy + e0[3] + M
        for x in (x0, (x0 + x1) / 2, x1):
            for y in (y0, (y0 + y1) / 2, y1):
                if not poly.Contains(pcbnew.VECTOR2I(FM(x), FM(y))):
                    return False
        return not any(not (x1 <= o[0] or o[2] <= x0 or y1 <= o[1] or o[3] <= y0) for o in obst)
    best = None
    step = 0.25
    for j in range(int(mm(bb.GetTop()) / step), int(mm(bb.GetBottom()) / step) + 1):
        for i in range(int(mm(bb.GetLeft()) / step), int(mm(bb.GetRight()) / step) + 1):
            cx, cy = i * step, j * step
            if ok(cx, cy):
                d = math.hypot(cx - tx, cy - ty)
                if best is None or d < best[0]:
                    best = (d, cx, cy)
    size = (e0[2] - e0[0], e0[3] - e0[1])
    if best is None:
        print(f"NO clear spot for {size[0]:.1f} x {size[1]:.1f} mm on the {a.side} side "
              f"(margin {M} mm). Options: other side, smaller size, two lines - ask the owner.")
        return 1
    print(f"clear spot: origin ({best[1]:.2f}, {best[2]:.2f}) for {size[0]:.1f} x {size[1]:.1f} mm on the {a.side} side")
    if a.out:
        item.SetPosition(pcbnew.VECTOR2I(FM(best[1]), FM(best[2])))
        if not a.text:
            item.SetLocked(True)
        for d in old:
            b.Remove(d)
        pcbnew.SaveBoard(a.out, b)
        print(f"placed{' and removed ' + str(len(old)) + ' old text(s)' if old else ''} -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
