"""Write a candidate placement into a COPY of the board. Needs KiCad's Python.

    kicad-python apply_placement.py BOARD.kicad_pcb cand.json OUT_DIR

The original board is never modified. In the copy:
  * every unlocked footprint is moved/rotated to the candidate position
  * all tracks and vias are removed (they belong to the old placement)
  * zone fills are cleared (outlines stay; refill after routing)
The project file, design rules and library tables are copied next to it so the
copy opens with the same netclasses and rules.

After saving, the copy is reloaded and every pad position is compared with what the
placer predicted, which proves the rotation convention end to end.
"""
import json
import math
import os
import shutil
import sys

import pcbnew

MM = 1e6


def rot_pt(lx, ly, deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return lx * c + ly * s, -lx * s + ly * c


def apply(board_path, placement, out_dir, model=None):
    os.makedirs(out_dir, exist_ok=True)
    src_dir = os.path.dirname(os.path.abspath(board_path))
    stem = os.path.splitext(os.path.basename(board_path))[0]
    out_board = os.path.join(out_dir, stem + ".kicad_pcb")
    if os.path.abspath(out_board) == os.path.abspath(board_path):
        raise SystemExit("refusing to overwrite the source board")

    b = pcbnew.LoadBoard(board_path)
    # take typed references before touching the board: after items are deleted the
    # SWIG wrapper can hand back untyped zone objects
    zones = [z for z in b.Zones() if not z.GetIsRuleArea()]
    moved = 0
    for f in b.GetFootprints():
        ref = f.GetReference()
        if f.IsLocked() or ref not in placement:
            continue
        x, y, rot = placement[ref]
        f.SetOrientationDegrees(rot)
        f.SetPosition(pcbnew.VECTOR2I(int(round(x * MM)), int(round(y * MM))))
        moved += 1
    for z in zones:
        z.UnFill()
    # Delete (not Remove): Remove hands ownership to Python, which cannot free the item
    tracks = list(b.GetTracks())
    removed = len(tracks)
    for t in tracks:
        b.Delete(t)
    pcbnew.SaveBoard(out_board, b)

    for ext in (".kicad_pro", ".kicad_dru", ".kicad_sch"):
        src = os.path.join(src_dir, stem + ext)
        if os.path.exists(src) and ext != ".kicad_sch":
            shutil.copy2(src, os.path.join(out_dir, stem + ext))
    for name in ("fp-lib-table", "sym-lib-table"):
        src = os.path.join(src_dir, name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(out_dir, name))

    worst = None
    if model is not None:
        chk = pcbnew.LoadBoard(out_board)
        by_ref = {c["ref"]: c for c in model["comps"]}
        worst = 0.0
        for f in chk.GetFootprints():
            c = by_ref.get(f.GetReference())
            if c is None or f.GetReference() not in placement:
                continue
            x, y, rot = placement[c["ref"]] if not c["locked"] else (c["x"], c["y"], c["rot"])
            for p, mp in zip(f.Pads(), c["pads"]):
                dx, dy = rot_pt(mp["x"], mp["y"], rot)
                pp = p.GetPosition()
                worst = max(worst, abs(pp.x / MM - (x + dx)), abs(pp.y / MM - (y + dy)))
    return {"board": out_board, "moved": moved, "tracks_removed": removed, "pad_error_mm": worst}


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("usage: apply_placement.py BOARD.kicad_pcb cand.json OUT_DIR")
    with open(sys.argv[2], encoding="utf-8") as fh:
        cand = json.load(fh)
    model = None
    cdir = os.path.dirname(os.path.abspath(sys.argv[2]))
    for mp in (os.path.join(cdir, "model.json"), os.path.join(os.path.dirname(cdir), "model.json")):
        if os.path.exists(mp):
            with open(mp, encoding="utf-8") as fh:
                model = json.load(fh)
            break
    print(json.dumps(apply(sys.argv[1], cand["placement"], sys.argv[3], model), indent=1))
