"""Score a placement and draw it. No pcbnew.

Metrics are computed on the true courtyards (no clearance margin) so the human
placement and the generated ones are judged the same way:

  mst        ratsnest length: minimum spanning tree per signal net, mm
  crossings  pairs of ratsnest edges from different nets that cross
  cong_peak  peak ratsnest density over a 4 mm grid (mm of wire per cell)
  dec_mean   mean distance from a decoupling cap to the IC power pin it serves, mm
  dec_max    worst such distance
  ov_pairs   courtyard pairs that overlap (same side), ov_area their total area
  fb_area    courtyard area outside the outline / inside a footprint keep-out /
             breaking a placement region
  reg_viol   movable footprints breaking a placement region (reg_locked: locked ones)
  clu_spread mean distance from a clustered part to its cluster's centroid, mm
"""
import math

import numpy as np

from place_core import Problem

CONG_CELL = 4.0

SHEET_COLORS = ["#4e79a7", "#f28e2b", "#59a14f", "#e15759", "#b07aa1",
                "#76b7b2", "#edc948", "#9c755f", "#ff9da7", "#8cd17d", "#86bcb6", "#bab0ac"]


def _mst(pts):
    n = len(pts)
    if n < 2:
        return []
    if n == 2:
        return [(0, 1)]
    a = np.array(pts)
    d = np.abs(a[:, None, 0] - a[None, :, 0]) + np.abs(a[:, None, 1] - a[None, :, 1])
    in_tree = np.zeros(n, bool)
    in_tree[0] = True
    best = d[0].copy()
    src = np.zeros(n, int)
    edges = []
    for _ in range(n - 1):
        best_m = np.where(in_tree, np.inf, best)
        j = int(np.argmin(best_m))
        edges.append((int(src[j]), j))
        in_tree[j] = True
        upd = d[j] < best
        src[upd] = j
        best = np.minimum(best, d[j])
    return edges


def _crossings(seg, net):
    if len(seg) < 2:
        return 0
    s = np.array(seg)
    k = np.array(net)
    p1, p2 = s[:, 0:2], s[:, 2:4]

    def cross(o, a, b):
        return (a[..., 0] - o[..., 0]) * (b[..., 1] - o[..., 1]) - (a[..., 1] - o[..., 1]) * (b[..., 0] - o[..., 0])

    d1 = cross(p1[None, :, :], p2[None, :, :], p1[:, None, :])
    d2 = cross(p1[None, :, :], p2[None, :, :], p2[:, None, :])
    d3 = cross(p1[:, None, :], p2[:, None, :], p1[None, :, :])
    d4 = cross(p1[:, None, :], p2[:, None, :], p2[None, :, :])
    hit = (d1 * d2 < 0) & (d3 * d4 < 0) & (k[:, None] != k[None, :])
    return int(np.triu(hit, 1).sum())


VIA_D = 0.5        # via diameter used to judge via room, mm
VIA_CLR = 0.13     # copper clearance kept around that via, mm
VIA_REACH = (0.0, 0.3, 0.6)   # extra distance from the pad tried for the via, mm


def via_room(P, via_d=VIA_D, clr=VIA_CLR):
    """Plane-net SMD pads with no room for their own via.

    Every SMD pad on a plane net needs a through via beside it. A via fits where its
    copper keeps `clr` from every pad of another net (either side: the via goes through),
    does not touch a pad of its own net (via-in-pad), stays on the board and keeps its
    distance from the vias already given to other pads. Pads are served greedily, the
    most enclosed first. Returns (number of plane pads, list of "REF.PAD" left without).
    """
    from place_core import rot_pt, RES
    rects, nets, owner = [], [], []
    want = []
    for i in range(P.n_real):
        c = P.comps[i]
        deg = P.rots[i][P.K[i]]
        for q, p in enumerate(c["pads"]):
            if "bb" not in p:
                continue
            x0, y0, x1, y1 = p["bb"]
            cs = [rot_pt(x, y, deg) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
            r = (P.X[i] + min(a[0] for a in cs), P.Y[i] + min(a[1] for a in cs),
                 P.X[i] + max(a[0] for a in cs), P.Y[i] + max(a[1] for a in cs))
            k = P.PADNET[i][q]
            if k >= 0 and P.is_plane[k] and not p.get("th"):
                want.append(len(rects))
            rects.append(r)
            nets.append(k if k >= 0 else -2 - len(rects))
            owner.append("%s.%s" % (c["ref"], p["num"]))
    if not want:
        return 0, []
    R = np.array(rects)
    N = np.array(nets)
    rad = via_d / 2.0
    S = P.S
    dirs = [(math.cos(math.radians(a)), math.sin(math.radians(a))) for a in range(0, 360, 30)]

    def on_board(x, y):
        for dx, dy in ((0, 0), (rad + 0.3, 0), (-rad - 0.3, 0), (0, rad + 0.3), (0, -rad - 0.3)):
            ix = int((x + dx - P.bx0) / RES)
            iy = int((y + dy - P.by0) / RES)
            if not (0 <= ix < P.nx and 0 <= iy < P.ny):
                return False
            if S[iy + 1][ix + 1] - S[iy][ix + 1] - S[iy + 1][ix] + S[iy][ix]:
                return False
        return True

    def spots(w):
        x0, y0, x1, y1 = R[w]
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        out = []
        for ux, uy in dirs:
            # distance from the pad centre to its edge along this direction
            t = min((x1 - x0) / 2.0 / abs(ux) if abs(ux) > 1e-9 else 1e9,
                    (y1 - y0) / 2.0 / abs(uy) if abs(uy) > 1e-9 else 1e9)
            for extra in VIA_REACH:
                d = t + rad + 0.05 + extra
                x, y = cx + ux * d, cy + uy * d
                if not on_board(x, y):
                    continue
                dx = np.maximum(np.maximum(R[:, 0] - x, x - R[:, 2]), 0.0)
                dy = np.maximum(np.maximum(R[:, 1] - y, y - R[:, 3]), 0.0)
                gap = np.hypot(dx, dy) - rad
                need = np.where(N == N[w], 0.0, clr)
                if (gap < need - 1e-9).any():
                    continue
                out.append((x, y))
        return out

    cand = {w: spots(w) for w in want}
    placed = []
    starved = []
    for w in sorted(want, key=lambda w: len(cand[w])):
        ok = None
        for x, y in cand[w]:
            if all((x - a) ** 2 + (y - b) ** 2 >= (via_d + clr) ** 2 for a, b in placed):
                ok = (x, y)
                break
        if ok:
            placed.append(ok)
        else:
            starved.append(owner[w])
    return len(want), sorted(starved)


def gap_stats(P):
    """Gap from each movable footprint to its nearest same-side neighbour, on the true
    courtyards. Returns (median, lower quartile, parts with a neighbour under 0.3 mm)."""
    n = P.n_real
    cur = np.array(P.CUR[:n])
    side = np.array(P.side[:n])
    dx = np.maximum(cur[:, None, 0] - cur[None, :, 2], cur[None, :, 0] - cur[:, None, 2])
    dy = np.maximum(cur[:, None, 1] - cur[None, :, 3], cur[None, :, 1] - cur[:, None, 3])
    gap = np.hypot(np.maximum(dx, 0.0), np.maximum(dy, 0.0))
    gap[(side[:, None] & side[None, :]) == 0] = 1e9
    np.fill_diagonal(gap, 1e9)
    mv = np.array([not P.fixed[i] for i in range(n)])
    nn = gap.min(1)[mv]
    nn = nn[nn < 1e8]
    if not len(nn):
        return 0.0, 0.0, 0
    return float(np.median(nn)), float(np.percentile(nn, 25)), int((nn < 0.3).sum())


def evaluate(model, placement=None):
    """Return (metrics dict, drawing data)."""
    P = Problem(model, margin=0.0)
    if placement is not None:
        P.load_placement(placement)
    P.assign_decaps()
    X, Y, K, PO = P.X, P.Y, P.K, P.PADOFF

    seg, seg_net = [], []
    mst = 0.0
    hp = 0.0
    for k in range(len(P.net_names)):
        if P.is_plane[k]:
            continue
        pts = [(X[i] + PO[i][K[i]][q][0], Y[i] + PO[i][K[i]][q][1]) for i, q in P.NETP[k]]
        hp += P.hpwl(k)
        for a, b in _mst(pts):
            seg.append((pts[a][0], pts[a][1], pts[b][0], pts[b][1]))
            seg_net.append(k)
            mst += abs(pts[a][0] - pts[b][0]) + abs(pts[a][1] - pts[b][1])

    # congestion: wire length per grid cell, sampling each edge
    gx = int(math.ceil((P.bx1 - P.bx0) / CONG_CELL))
    gy = int(math.ceil((P.by1 - P.by0) / CONG_CELL))
    grid = np.zeros((gy, gx))
    for x1, y1, x2, y2 in seg:
        ln = math.hypot(x2 - x1, y2 - y1)
        m = max(1, int(ln / 0.5))
        t = (np.arange(m) + 0.5) / m
        cx = np.clip(((x1 + (x2 - x1) * t - P.bx0) / CONG_CELL).astype(int), 0, gx - 1)
        cy = np.clip(((y1 + (y2 - y1) * t - P.by0) / CONG_CELL).astype(int), 0, gy - 1)
        np.add.at(grid, (cy, cx), ln / m)

    # true courtyard overlaps
    cur = np.array(P.CUR)
    side = np.array(P.side)
    w = np.minimum(cur[:, None, 2], cur[None, :, 2]) - np.maximum(cur[:, None, 0], cur[None, :, 0])
    h = np.minimum(cur[:, None, 3], cur[None, :, 3]) - np.maximum(cur[:, None, 1], cur[None, :, 1])
    same = (side[:, None] & side[None, :]) > 0
    ov = np.where((w > 1e-6) & (h > 1e-6) & same, w * h, 0.0)
    ov = np.triu(ov, 1)
    pairs = np.argwhere(ov > 1e-4)
    ov_refs = sorted({P.refs[int(i)] for pr in pairs for i in pr})
    # pairs the placer cannot change: both parts locked or frozen
    ov_fixed = sum(1 for i, j in pairs if P.fixed[int(i)] and P.fixed[int(j)])

    caps = [i for i in range(P.n) if P.CAPT[i] is not None]
    dc = [P.DC[i] for i in caps]

    off_grid = [P.refs[i] for i in P.movable
                if abs(model["comps"][i]["rot"] / 90.0 - round(model["comps"][i]["rot"] / 90.0)) > 1e-6]

    reg_mv, reg_lk = P.region_viol()
    via_n, via_bad = via_room(P)
    g_med, g_q25, g_tight = gap_stats(P)

    metrics = {
        "gap_med": round(g_med, 2),
        "gap_q25": round(g_q25, 2),
        "gap_tight": g_tight,
        "via_pads": via_n,
        "via_starved": len(via_bad),
        "via_starved_list": via_bad,
        "pp_viol": len(P.pair_viol()),
        "pp_list": P.pair_viol(),
        "reg_viol": len(reg_mv),
        "reg_refs": reg_mv,
        "reg_locked": reg_lk,
        "clu_spread": round(P.cluster_spread(), 2),
        "mst": round(mst, 1),
        "hpwl": round(hp, 1),
        "crossings": _crossings(seg, seg_net),
        "cong_peak": round(float(grid.max()), 1),
        "cong_p90": round(float(np.percentile(grid[grid > 0], 90)) if (grid > 0).any() else 0.0, 1),
        "dec_n": len(caps),
        "dec_mean": round(float(np.mean(dc)) if dc else 0.0, 2),
        "dec_max": round(float(np.max(dc)) if dc else 0.0, 2),
        "ov_pairs": int(len(pairs)),
        "ov_fixed": int(ov_fixed),
        "ov_area": round(float(ov.sum()), 2),
        "fb_area": round(float(sum(P.FB)), 2),
        "off_grid_rot": off_grid,
    }
    draw = {"P": P, "seg": seg, "ov_refs": set(ov_refs) | set(reg_mv) | set(reg_lk)}
    return metrics, draw


def index(m, base):
    """Composite index, baseline = 100, lower is better."""
    def r(key):
        return m[key] / base[key] if base[key] else 1.0
    # via room is absolute, not relative: one point per percent of the plane pads that
    # have no place for their via beyond what the baseline already lacks
    lack = m.get("via_starved", 0) - base.get("via_starved", 0)
    via = 100.0 * lack / max(1, m.get("via_pads", 0))
    return round(100.0 * (0.40 * r("mst") + 0.25 * r("crossings") + 0.15 * r("cong_peak")
                          + 0.20 * r("dec_mean")) + via, 1)


def sheet_colors(model):
    sheets = sorted({c["sheet"] for c in model["comps"]})
    return {s: SHEET_COLORS[i % len(SHEET_COLORS)] for i, s in enumerate(sheets)}


def svg(model, draw, colors, ratsnest=True):
    P = draw["P"]
    pad = 2.0
    x0, y0 = P.bx0 - pad, P.by0 - pad
    w, h = P.bx1 - P.bx0 + 2 * pad, P.by1 - P.by0 + 2 * pad
    out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="%.2f %.2f %.2f %.2f" class="board">' % (x0, y0, w, h)]
    out.append('<polygon class="outline" points="%s"/>' % " ".join("%.2f,%.2f" % (p[0], p[1]) for p in model["outline"]))
    for ko in model.get("keepouts", []):
        out.append('<polygon class="keepout" points="%s"><title>%s</title></polygon>' % (
            " ".join("%.2f,%.2f" % (p[0], p[1]) for p in ko["pts"]), ko["name"]))
    for r in P.hard_regions:
        for p in r["polys"]:
            if p["onboard"]:
                out.append('<polygon class="region%s" points="%s"><title>%s (%s)</title></polygon>' % (
                    " excl" if r["exclusive"] else "",
                    " ".join("%.2f,%.2f" % (q[0], q[1]) for q in p["pts"]), r["name"], r["source"]))
    order = sorted(range(P.n), key=lambda i: -P.AREA[i])
    for i in order:
        a = P.CUR[i]
        cw, chh = a[2] - a[0], a[3] - a[1]
        if i >= P.n_real:
            out.append('<rect class="pin" x="%.2f" y="%.2f" width="%.2f" height="%.2f"/>' % (a[0], a[1], cw, chh))
            continue
        cls = "fp"
        if P.fixed[i]:
            cls += " fixed"
        if P.refs[i] in draw["ov_refs"]:
            cls += " clash"
        if P.side[i] == 2:
            cls += " back"
        out.append('<rect class="%s" x="%.2f" y="%.2f" width="%.2f" height="%.2f" fill="%s"><title>%s  %s  %s</title></rect>' % (
            cls, a[0], a[1], cw, chh, colors[P.sheet[i]], P.refs[i], model["comps"][i]["value"], P.sheet[i]))
        if min(cw, chh) >= 2.6:
            fs = min(2.2, min(cw, chh) * 0.38, max(cw, chh) / (0.62 * max(2, len(P.refs[i]))))
            out.append('<text x="%.2f" y="%.2f" font-size="%.2f">%s</text>' % (
                (a[0] + a[2]) / 2, (a[1] + a[3]) / 2, fs, P.refs[i]))
    if ratsnest:
        out.append('<g class="rats">')
        for x1, y1, x2, y2 in draw["seg"]:
            out.append('<line x1="%.2f" y1="%.2f" x2="%.2f" y2="%.2f"/>' % (x1, y1, x2, y2))
        out.append("</g>")
    out.append("</svg>")
    return "".join(out)
