#!/usr/bin/env python3
"""
Renders a placement for review (any Python with matplotlib): outline, courtyards coloured by block, fixed parts
greyed, plan regions and keep-outs dashed, references as labels. Look at it before trusting any number: clumps,
parts far from their block, a block split in two and decoupling capacitors away from their IC show at a glance.

Usage:
    python3 render_placement.py dump.json placed.png [--report placed_report.json] [--plan plan.json] [--dpi 110]
"""
import argparse, json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Polygon, Rectangle  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dump"); ap.add_argument("png")
    ap.add_argument("--report"); ap.add_argument("--plan"); ap.add_argument("--dpi", type=int, default=110)
    a = ap.parse_args()
    d = json.load(open(a.dump))
    rep = json.load(open(a.report)) if a.report else {"placed": {}}
    plan = json.load(open(a.plan, encoding="utf-8")) if a.plan else {}
    xs = [p[0] for e in d["edges"] for p in e]; ys = [p[1] for e in d["edges"] for p in e]
    X0, X1, Y0, Y1 = min(xs), max(xs), min(ys), max(ys)
    w = X1 - X0; h = Y1 - Y0
    fig, ax = plt.subplots(figsize=(max(8, 18 * w / max(w, h)), max(6, 18 * h / max(w, h)) + 1))
    for e in d["edges"]:
        ax.plot([p[0] for p in e], [p[1] for p in e], "k-", lw=1)
    for name, rects in plan.get("regions", {}).items():
        for r in rects:
            ax.add_patch(Rectangle((r[0], r[1]), r[2] - r[0], r[3] - r[1], fill=False, ec="b", ls=":", lw=0.6))
            ax.text(r[0] + 0.5, r[1] + 1.5, name, color="b", fontsize=6)
    for k in plan.get("keepouts", []):
        r = k["rect"]
        ax.add_patch(Rectangle((r[0], r[1]), r[2] - r[0], r[3] - r[1], fill=False, ec="r", ls="--", lw=0.8))
    cols, pal = {}, plt.cm.tab20.colors
    inside = lambda f: X0 - 2 < f["x"] < X1 + 2 and Y0 - 2 < f["y"] < Y1 + 2
    for f in d["fps"]:
        if not inside(f):
            continue
        blk = rep["placed"].get(f["ref"], {}).get("block", "fixed / not placed")
        c = (0.6, 0.6, 0.6) if blk == "fixed / not placed" else cols.setdefault(blk, pal[len(cols) % 20])
        for poly in f["crt"]:
            ax.add_patch(Polygon(poly, closed=True, fc=c, ec="k", lw=0.3, alpha=0.3 if blk.startswith("fixed") else 0.65))
        if not f["crt"]:
            b = f["bb"]; ax.add_patch(Rectangle((b[0], b[1]), b[2] - b[0], b[3] - b[1], fc=c, alpha=0.4))
        ax.text(f["x"], f["y"], f["ref"], fontsize=3.5 if not blk.startswith("fixed") else 6, ha="center", va="center")
    ax.set_xlim(X0 - 2, X1 + 2); ax.set_ylim(Y1 + 2, Y0 - 2); ax.set_aspect("equal")
    ax.legend(handles=[Rectangle((0, 0), 1, 1, fc=c) for c in cols.values()], labels=list(cols), fontsize=6,
              loc="upper left", bbox_to_anchor=(1.0, 1.0))
    plt.tight_layout(); plt.savefig(a.png, dpi=a.dpi)
    print(f"rendered -> {a.png}")


if __name__ == "__main__":
    main()
