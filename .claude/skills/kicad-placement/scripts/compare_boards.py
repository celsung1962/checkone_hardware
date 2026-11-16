#!/usr/bin/env python3
"""
Proves that a placement job changed ONLY placement (run with KiCad's Python). Compares two boards:

  - per footprint: library link, UUID, side, graphic items (UUID, layer, kind), pads (number, net, UUID, layers),
    fields (name, text, layer) - any difference is reported as a non-placement change;
  - board drawings, tracks / vias, zones - must be identical (a placement job never routes or draws);
  - fixed footprints (plan patterns or --fixed) must keep position, rotation and side;
  - placement changes are counted (moved, rotated, flipped, lock state).

A line-based diff of .kicad_pcb files is useless for this: KiCad reorders items inside a footprint when it is
rotated, so thousands of lines change while nothing but positions did.

Usage:
    <kicad-python> compare_boards.py before.kicad_pcb after.kicad_pcb [--plan plan.json] [--fixed "J*,H*"]
Field position / visibility changes (e.g. designators hidden on the silkscreen) are counted, not failed.
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew  # noqa: E402
from placement_core import mm, load_plan, matches  # noqa: E402


def sig(path):
    b = pcbnew.LoadBoard(path)
    fps = {}
    for f in b.GetFootprints():
        g = sorted((str(i.m_Uuid.AsString()), i.GetLayerName(), i.GetClass()) for i in f.GraphicalItems())
        p = sorted((q.GetNumber(), q.GetNetname(), str(q.m_Uuid.AsString()), q.GetLayerSet().FmtHex()) for q in f.Pads())
        flds = sorted((fl.GetName(), fl.GetText(), fl.GetLayerName()) for fl in f.GetFields())
        fps[f.GetReference()] = dict(
            content=(f.GetFPIDAsString(), str(f.m_Uuid.AsString()), g, p, flds),
            place=(round(mm(f.GetPosition().x), 4), round(mm(f.GetPosition().y), 4), round(f.GetOrientationDegrees(), 3),
                   f.IsFlipped()), locked=f.IsLocked(), fpos={fl.GetName(): (fl.IsVisible(), fl.GetPosition().x, fl.GetPosition().y)
                                                              for fl in f.GetFields()})
    drawings = sorted((str(d.m_Uuid.AsString()), d.GetClass(), d.GetLayerName()) for d in b.GetDrawings())
    tracks = sorted((str(t.m_Uuid.AsString()), t.GetClass()) for t in b.GetTracks())
    zones = sorted(str(b.GetArea(i).m_Uuid.AsString()) for i in range(b.GetAreaCount()))
    return fps, drawings, tracks, zones


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("before"); ap.add_argument("after")
    ap.add_argument("--plan"); ap.add_argument("--fixed", default="")
    a = ap.parse_args()
    fixed_pats = [p for p in a.fixed.split(",") if p]
    if a.plan:
        fixed_pats += load_plan(a.plan)["fixed"]
    A, Ad, At, Az = sig(a.before)
    B, Bd, Bt, Bz = sig(a.after)
    problems = []
    for r in sorted(set(A) | set(B)):
        if r not in A or r not in B:
            problems.append(f"{r}: footprint {'added' if r in B else 'removed'}")
            continue
        if A[r]["content"] != B[r]["content"]:
            what = [n for n, x, y in zip(("library", "uuid", "graphics", "pads/nets", "fields"), A[r]["content"], B[r]["content"]) if x != y]
            problems.append(f"{r}: non-placement change in {', '.join(what)}")
        if matches(r, fixed_pats) and A[r]["place"] != B[r]["place"]:
            problems.append(f"{r}: FIXED footprint moved {A[r]['place']} -> {B[r]['place']}")
    for name, x, y in (("board drawings", Ad, Bd), ("tracks/vias", At, Bt), ("zones", Az, Bz)):
        if x != y:
            problems.append(f"{name} changed ({len(x)} -> {len(y)} items)")
    moved = sum(1 for r in A if r in B and A[r]["place"][:2] != B[r]["place"][:2])
    rotated = sum(1 for r in A if r in B and A[r]["place"][2] != B[r]["place"][2])
    flipped = sum(1 for r in A if r in B and A[r]["place"][3] != B[r]["place"][3])
    locked = sum(1 for r in A if r in B and A[r]["locked"] != B[r]["locked"])
    fields = sum(1 for r in A if r in B and A[r]["fpos"] != B[r]["fpos"])
    print(f"footprints {len(B)}: moved {moved}, rotated {rotated}, flipped {flipped}, lock changed {locked}, "
          f"field position/visibility changed {fields}")
    for p in problems:
        print("  -", p)
    print(f"\nPlacement-only change: {'PASS' if not problems else 'FAIL'}")
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main())
