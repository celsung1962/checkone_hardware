#!/usr/bin/env python3
"""
Hides the reference designators that sit on the silkscreen (run with KiCad's Python). On a dense board the
designators land on neighbouring pads (DRC "silk_over_copper"); hiding them keeps the Reference field in the
footprint (assembly drawings on Fab still show it). Only the field's visibility changes.

Usage:
    <kicad-python> hide_silk_refs.py board.kicad_pcb --out new.kicad_pcb [--only "R*,C*"] [--dry-run]
"""
import argparse, fnmatch, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("board"); ap.add_argument("--out"); ap.add_argument("--only", default="*")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    pats = [p for p in a.only.split(",") if p]
    b = pcbnew.LoadBoard(a.board)
    n = texts = 0
    for f in b.GetFootprints():
        if not any(fnmatch.fnmatchcase(f.GetReference(), p) for p in pats):
            continue
        r = f.Reference()
        if r.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS) and r.IsVisible():
            n += 1
            if not a.dry_run:
                r.SetVisible(False)
        for it in f.GraphicalItems():           # user texts "${REFERENCE}" drawn on the silkscreen
            if it.GetClass() == "PCB_TEXT" and it.GetLayer() in (pcbnew.F_SilkS, pcbnew.B_SilkS) \
                    and ("${REFERENCE}" in it.GetText() or it.GetText() == f.GetReference()) and it.IsVisible():
                texts += 1
                if not a.dry_run:
                    it.SetVisible(False)
    print(f"silkscreen designators {'to hide' if a.dry_run else 'hidden'}: {n} fields, {texts} user texts")
    if not a.dry_run:
        if not a.out:
            sys.exit("--out is required")
        pcbnew.SaveBoard(a.out, b)
        print(f"-> {a.out}")


if __name__ == "__main__":
    main()
