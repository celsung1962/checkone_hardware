"""Re-pack the signal passives (and decoupling capacitors) of analog ICs around their pins (run with KiCad's Python)
- kicad-placement 1.3.0.

place.py fills a block's region and puts supply capacitors at the supply pins; it does not pull feedback resistors,
filter capacitors or peak-detector diodes to the op-amp pins they belong to. Run this after place.py on the analog
blocks: optional IC moves first ("ic_moves"), then the listed parts are lifted and put back one by one at the free
spot with the lowest wiring cost

    cost = sum over the part's signal pads of  w * (distance to the nearest anchor-IC pin on that net)
                                             + 1 * (distance to the nearest other placed pad on that net)

w = 3 at an input / switch pin (default), 1 at a low-impedance output pin, 0 = no pull (config "weight", per
"REF.PIN"). A decoupling capacitor ("decaps": {"C1": "U1.8"}) is pulled to its supply pin with "decap_weight" (12
keeps the swaps from trading it away). A part without a signal net (a rail test point) stays near its old spot.
Supply and ground nets cost nothing ("supply_nets" regex, as in signal_near.py).

Steps: greedy in "order" (decaps first, then the parts at IC inputs, then the rest, test points last), relocation
passes, then pair swaps within "swap_distance". "mode": "improve" skips the greedy and only improves the current
positions (never leaves a part without a spot). "regions" keep each block's parts inside its rectangles - without
them the greedy mixes blocks. Free = the box rules of verify_placement.py: spacing (SMD / THT / mechanical), edge
clearance, footprint rule areas, front-side artwork and the plan keep-outs matching the reference. A fixed
through-hole part mounted on the bottom side blocks the top side with its pads only.

Run signal_near.py and verify_placement.py afterwards; always write to a new board.

Usage: <kicad-python> pack_passives.py plan.json in.kicad_pcb out.kicad_pcb config.json
config (JSON, see references/placement_rules.md "Analog signal passives"):
  {"movable": [...], "order": [...], "anchors": ["U*"], "ic_moves": {"U14": [145, 81.5, 0]},
   "decaps": {"C204": "U14.8"}, "regions": [{"name": "...", "rects": [[x0, y0, x1, y1]], "refs": [...]}],
   "weight": {"U13.7": 1, "U14.3": 0}, "no_other_nets": ["SENSE_FILTERED"], "mode": "scratch",
   "radius": 10, "passes": 6, "swap_passes": 4, "swap_distance": 12, "decap_weight": 12}
Set PACK_DEBUG=1 to print, for a part without a spot, what blocks it.
"""
import json, math, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew
from placement_core import (mm, FM, load_plan, courtyard_rect, is_tht, fixed_refs, footprint_keepouts, matches,
                            artwork_keepouts, is_artwork, board_outline)

SUPPLY = r"(?i)(GND|^[+-]?\d+(\.\d+)?V|^[+-]\d|VCC|VDD|VEE|VSS|VBAT|CHASSIS|EARTH|SHIELD)"


def net(p):
    return p.GetNetname().strip("/")


def obstacles(fp, fixed):
    """Top-side rectangles of a part that does not move: a fixed through-hole part mounted on the bottom side takes
    only its plated pads on the top side; every other part its courtyard box."""
    if fixed and fp.IsFlipped() and is_tht(fp):
        out = []
        for p in fp.Pads():
            if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
                bb = p.GetBoundingBox()
                out.append((mm(bb.GetLeft()), mm(bb.GetTop()), mm(bb.GetRight()), mm(bb.GetBottom())))
        return out
    return [courtyard_rect(fp)]


def main():
    plan_path, inp, out, cfg_path = sys.argv[1:5]
    plan = load_plan(plan_path)
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    sup = re.compile(cfg.get("supply_nets", SUPPLY))
    b = pcbnew.LoadBoard(inp)
    edge = board_outline(b)
    bb = edge.BBox()
    inside = lambda f: bb.Contains(f.GetPosition())                       # staging-area parts are ignored
    fps = {f.GetReference(): f for f in b.GetFootprints() if inside(f)}
    for r, (x, y, rot) in cfg.get("ic_moves", {}).items():               # ICs first, by the engineer's floorplan
        fps[r].SetOrientationDegrees(rot); fps[r].SetPosition(pcbnew.VECTOR2I(FM(x), FM(y)))
    fixed = fixed_refs(b, plan)
    mov = [r for r in cfg["movable"] if r in fps]
    rule_areas = footprint_keepouts(b)
    g = plan["grid"]
    W = cfg.get("weight", {})
    anchors = cfg.get("anchors", ["U*", "IC*"])
    is_ic = lambda r: matches(r, anchors)

    geo = {}                                                               # per part and rotation, origin-relative
    for r in mov:
        f = fps[r]
        pos0, rot0 = f.GetPosition(), f.GetOrientationDegrees()
        geo[r] = {}
        for rot in (0, 90, 180, 270):
            f.SetOrientationDegrees(rot); f.SetPosition(pcbnew.VECTOR2I(0, 0))
            geo[r][rot] = (courtyard_rect(f), [(mm(p.GetPosition().x), mm(p.GetPosition().y), net(p)) for p in f.Pads()])
        f.SetOrientationDegrees(rot0); f.SetPosition(pos0)
    tht = {r: is_tht(fps[r]) for r in fps}

    static = [(r, q, False) for r, q in artwork_keepouts(b, plan)]
    for r, f in fps.items():
        if r in mov or is_artwork(f):
            continue
        mech = r in fixed and (tht[r] or r.startswith(("H", "MH", "J")))
        for q in obstacles(f, r in fixed):
            static.append((r, q, mech))
    spads = {}
    for r, f in fps.items():
        if r in mov:
            continue
        for p in f.Pads():
            n = net(p)
            if n and not sup.search(n):
                spads.setdefault(n, []).append((mm(p.GetPosition().x), mm(p.GetPosition().y), r, p.GetNumber()))

    state = {r: None for r in mov}
    home = {r: (mm(fps[r].GetPosition().x), mm(fps[r].GetPosition().y)) for r in mov}
    decaps = cfg.get("decaps", {})
    region = {r: blk["rects"] for blk in cfg.get("regions", []) for r in blk["refs"]}
    kos = {r: rule_areas + [k["rect"] for k in plan["keepouts"] if matches(r, k.get("refs", ["*"]))] for r in mov}
    local = {"static": []}

    def placed_rects(skip):
        for r, s in state.items():
            if s is not None and r != skip:
                q = geo[r][s[2]][0]
                yield r, (q[0] + s[0], q[1] + s[1], q[2] + s[0], q[3] + s[1])

    def placed_pads(n, skip):
        for r, s in state.items():
            if s is not None and r != skip:
                for px, py, pn in geo[r][s[2]][1]:
                    if pn == n:
                        yield px + s[0], py + s[1]

    def set_local(ref, cx, cy, m):
        local["static"] = [(o, q, plan["mech_spacing"] if mech else plan["tht_spacing"] if tht[o] or tht[ref] else plan["spacing"])
                           for o, q, mech in static if q[0] < cx + m and q[2] > cx - m and q[1] < cy + m and q[3] > cy - m]

    def blocker(ref, rect):
        if ref in region and not any(q[0] <= rect[0] and rect[2] <= q[2] and q[1] <= rect[1] and rect[3] <= q[3] for q in region[ref]):
            return "region"
        for o, q, s in local["static"]:
            if rect[0] - s < q[2] and q[0] < rect[2] + s and rect[1] - s < q[3] and q[1] < rect[3] + s:
                return o
        for o, q in placed_rects(ref):
            s = plan["tht_spacing"] if tht[o] or tht[ref] else plan["spacing"]
            if rect[0] - s < q[2] and q[0] < rect[2] + s and rect[1] - s < q[3] and q[1] < rect[3] + s:
                return o
        for q in kos[ref]:
            if rect[0] < q[2] and q[0] < rect[2] and rect[1] < q[3] and q[1] < rect[3]:
                return "keepout"
        c = plan["edge_clearance"]
        for x, y in ((rect[0] - c, rect[1] - c), (rect[2] + c, rect[1] - c), (rect[0] - c, rect[3] + c), (rect[2] + c, rect[3] + c)):
            if not edge.Contains(pcbnew.VECTOR2I(FM(x), FM(y))):
                return "edge"
        return None

    def free(ref, rect):
        return blocker(ref, rect) is None

    def targets(ref):
        t = {}
        for px, py, n in geo[ref][0][1]:
            if not n or sup.search(n) or n in t:
                continue
            ic = [(x, y, W.get(f"{r}.{pn}", 3.0)) for x, y, r, pn in spads.get(n, []) if is_ic(r) and W.get(f"{r}.{pn}", 3.0) > 0]
            oth = [] if n in cfg.get("no_other_nets", []) else \
                [(x, y) for x, y, r, pn in spads.get(n, []) if not is_ic(r)] + list(placed_pads(n, ref))
            t[n] = (ic, oth)
        if ref in decaps:
            u, pn = decaps[ref].split(".")
            for p in fps[u].Pads():
                if p.GetNumber() == pn:
                    t[net(p)] = ([(mm(p.GetPosition().x), mm(p.GetPosition().y), cfg.get("decap_weight", 12.0))], [])
        return t

    def cost_at(ref, rot, x, y, t):
        if not t:
            return math.hypot(x - home[ref][0], y - home[ref][1])
        c = 0.0
        for px, py, n in geo[ref][rot][1]:
            if n in t:
                ic, oth = t[n]
                X, Y = px + x, py + y
                if ic:
                    c += min(w * math.hypot(X - u, Y - v) for u, v, w in ic)
                if oth:
                    c += min(math.hypot(X - u, Y - v) for u, v in oth)
        return c

    def best_spot(ref, R):
        t = targets(ref)
        pts = [(u, v) for ic, oth in t.values() for u, v, *_ in ic] or [(u, v) for ic, oth in t.values() for u, v in oth] \
            or [home[ref]]
        cx, cy = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
        n = int(R / g)
        set_local(ref, cx, cy, R + 6)
        cand = sorted((cost_at(ref, rot, x, y, t), x, y, rot) for rot in (0, 90, 180, 270)
                      for x in (round((cx + i * g) / g) * g for i in range(-n, n + 1))
                      for y in (round((cy + j * g) / g) * g for j in range(-n, n + 1)))
        for c, x, y, rot in cand:
            q = geo[ref][rot][0]
            if free(ref, (q[0] + x, q[1] + y, q[2] + x, q[3] + y)):
                return c, x, y, rot
        if os.environ.get("PACK_DEBUG"):
            why = {}
            for c, x, y, rot in cand[::7]:
                q = geo[ref][rot][0]
                k = blocker(ref, (q[0] + x, q[1] + y, q[2] + x, q[3] + y))
                why[k] = why.get(k, 0) + 1
            print("   debug", ref, sorted(why.items(), key=lambda t: -t[1])[:12])
        return None

    def total():
        return sum(cost_at(r, s[2], s[0], s[1], targets(r)) for r, s in state.items() if s)

    for r in mov:
        f = fps[r]
        state[r] = (mm(f.GetPosition().x), mm(f.GetPosition().y), round(f.GetOrientationDegrees()) % 360)
    print(f"cost before: {total():.1f}", flush=True)
    start = dict(state)
    order = [r for r in (cfg.get("order") or mov) if r in state]
    if cfg.get("mode") != "improve":
        for r in mov:
            state[r] = None
        for r in order:
            s = best_spot(r, cfg.get("radius", 10))
            if s is None:
                x, y, rot = start[r]; q = geo[r][rot][0]
                set_local(r, x, y, 10)
                if free(r, (q[0] + x, q[1] + y, q[2] + x, q[3] + y)):
                    print(f"  {r}: no free spot within the radius, kept where it was", flush=True)
                    s = (0, x, y, rot)
            if s is None:
                print(f"  {r}: no free spot within the radius, searching 40 mm", flush=True)
                s = best_spot(r, 40)
            if s is None:
                print(f"STOP: {r} has no free spot - partial board saved, unplaced parts moved off the board")
                for u in mov:
                    if state[u] is not None:
                        x, y, rot = state[u]; fps[u].SetOrientationDegrees(rot); fps[u].SetPosition(pcbnew.VECTOR2I(FM(x), FM(y)))
                    else:
                        fps[u].SetPosition(pcbnew.VECTOR2I(bb.GetRight() + FM(20), bb.GetTop()))
                b.Save(out)
                sys.exit(1)
            state[r] = s[1:]
        print(f"cost after greedy: {total():.1f}", flush=True)
    for k in range(cfg.get("passes", 4)):
        moved = 0
        for r in order:
            old = state[r]
            c_old = cost_at(r, old[2], old[0], old[1], targets(r))
            state[r] = None
            s = best_spot(r, cfg.get("radius", 10))
            if s is not None and s[0] < c_old - 0.05:
                state[r] = s[1:]; moved += 1
            else:
                state[r] = old
        print(f"pass {k + 1}: moved {moved}, cost {total():.1f}", flush=True)
        if not moved:
            break
    for k in range(cfg.get("swap_passes", 3)):
        swaps, base = 0, total()
        for i, a in enumerate(order):
            for bq in order[i + 1:]:
                sa, sb = state[a], state[bq]
                if math.hypot(sa[0] - sb[0], sa[1] - sb[1]) > cfg.get("swap_distance", 12):
                    continue
                best = (base, sa, sb)
                for ra in (0, 90, 180, 270):
                    for rb in (0, 90, 180, 270):
                        state[a] = (sb[0], sb[1], ra); state[bq] = (sa[0], sa[1], rb)
                        qa, qb = geo[a][ra][0], geo[bq][rb][0]
                        set_local(a, sb[0], sb[1], 8)
                        ok = free(a, (qa[0] + sb[0], qa[1] + sb[1], qa[2] + sb[0], qa[3] + sb[1]))
                        if ok:
                            set_local(bq, sa[0], sa[1], 8)
                            ok = free(bq, (qb[0] + sa[0], qb[1] + sa[1], qb[2] + sa[0], qb[3] + sa[1]))
                        if ok:
                            c = total()
                            if c < best[0] - 0.05:
                                best = (c, state[a], state[bq])
                state[a], state[bq] = best[1], best[2]
                if best[0] < base - 0.05:
                    swaps += 1; base = best[0]
        print(f"swap pass {k + 1}: {swaps} swaps, cost {total():.1f}", flush=True)
        if not swaps:
            break
    for r in mov:
        x, y, rot = state[r]
        fps[r].SetOrientationDegrees(rot); fps[r].SetPosition(pcbnew.VECTOR2I(FM(x), FM(y)))
    b.Save(out)


if __name__ == "__main__":
    main()
