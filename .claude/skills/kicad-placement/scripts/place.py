#!/usr/bin/env python3
"""
Block-based component placer for KiCad boards, driven by a placement plan (run with KiCad's Python).

Input : the board named in the plan (never modified), the plan JSON (references/plan_format.md), optionally
        pintypes.json and schpos.json from extract_schematic.py.
Output: a NEW .kicad_pcb (--out) with the movable footprints on the top side, rotations 0/90/180/270, origins on
        the placement grid, courtyards >= spacing apart (THT and mechanical parts more), >= edge clearance from
        Edge.Cuts (sensitive parts more), outside keep-outs; and a JSON report (placed, out-of-zone, failed,
        decoupling distances, improvements).

Method (each step exists because the simpler version failed on a real board):
  1. occupancy raster at fine resolution (0.05 mm) with exact rounding - a coarse raster wasted ~40 % of the
     area on small parts and made a feasible board look full;
  2. decoupling capacitors of fixed ICs first (their IC is already in place); then blocks in plan order, each
     with a target box and allowed regions; inside a block each IC with its decoupling capacitors (smallest
     value first, target = the served power pin), then the rest;
  3. target of a part = its schematic position mapped into the block box (signal-flow order), blended with the
     centroid of already-placed neighbours on signal nets; anchors in the plan override;
  4. each part takes the free origin of lowest cost = distance to target + net length to placed pads, trying
     its rotations; if its block has no room, it spills to the whole board and is reported; an IC with
     decoupling capacitors is placed together with them: its k best origins per rotation are tried with the
     capacitors placed at each, and the shortest total capacitor distance wins;
  5. improvement passes: a decoupling capacitor far from its pin may evict up to 4 small parts near the pin
     (they are re-placed in their own block, otherwise everything is restored); an IC whose capacitors ended far
     away is re-placed together with them and the small parts around it, trying 4 rotations within
     +/-4 mm of its position, then +/-8 mm inside its block;
  6. final zone check (courtyard centre inside the block's regions).
Heat sources (plan "heat") and sensitive parts ("heat_sensitive" plus every aluminium electrolytic, 1.2.0) keep
heat_min_distance from each other while
placing, not only in the check.

Usage:
    <kicad-python> place.py plan.json --out build/placement/placed.kicad_pcb [--report build/placement/report.json]
    <kicad-python> place.py plan.json --budget       # area demand vs free area per block, no placement
"""
import argparse, json, math, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew  # noqa: E402
import numpy as np  # noqa: E402
from placement_core import (mm, FM, load_plan, matches, select, Raster, fixed_refs, mark_fixed, courtyard_rect,  # noqa: E402
                            is_tht, min_smd_pitch, flip_to_top, ref_num, assign_decaps, SUPPLY, GNDNAME,
                            heat_sensitive_refs)

MULTI_ROT = ("U", "Q", "D", "Y", "J", "PS", "SW", "LED", "X")


def cap_value(v):
    m = re.match(r"([\d.]+)\s*([pnuµ])F", v or "")
    return float(m.group(1)) * {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6}[m.group(2)] if m else 1e9


class Placer:
    def __init__(self, plan):
        self.plan = plan
        self.b = pcbnew.LoadBoard(plan["board"])
        self.fp = {f.GetReference(): f for f in self.b.GetFootprints()}
        self.pt = json.load(open(plan["pintypes"])) if plan.get("pintypes") and os.path.exists(plan["pintypes"]) else {}
        self.sch = json.load(open(plan["schpos"])) if plan.get("schpos") and os.path.exists(plan["schpos"]) else {}
        self.fixed = fixed_refs(self.b, plan)
        self.r = Raster(self.b, plan["grid"], plan["resolution"])
        self.occ = self.r.empty()
        mark_fixed(self.r, self.occ, self.b, self.fixed, plan)
        self.IN = self.r.inside(plan["edge_clearance"])
        self.INS = self.r.inside(plan["sensitive_edge_clearance"])
        self.movable = [r for r in self.fp if r not in self.fixed]
        self.flipped = [r for r in self.movable if flip_to_top(self.fp[r])]
        self.geom = {r: self._geom(self.fp[r]) for r in self.movable}
        self.netpads = {}
        for r, f in self.fp.items():
            for p in f.Pads():
                n = p.GetNetname()
                if n and not n.startswith("unconnected"):
                    self.netpads.setdefault(n, []).append(r)
        self.padpos = {r: [(p.GetNetname(), mm(p.GetPosition().x), mm(p.GetPosition().y)) for p in self.fp[r].Pads()]
                       for r in self.fixed}
        self.placed = {r: (mm(self.fp[r].GetPosition().x), mm(self.fp[r].GetPosition().y)) for r in self.fixed}
        self.rect = {}
        self.block_of = {}
        self.spill = set()
        self.report = dict(placed={}, out_of_zone=[], spilled=[], failed=[], decap={}, improved=[],
                           flipped_to_top=self.flipped, unassigned=[])
        s = plan["sensitive"]
        self.sensitive = {r for r in self.movable if (r.startswith("U") and min_smd_pitch(self.fp[r]) <= s["fine_pitch_max"])
                          or r.startswith(tuple(s["prefixes"]))
                          or (r.startswith("C") and any(p in self.fp[r].GetFPIDAsString() for p in s["mlcc_packages"]))}
        self.heat_sensitive = heat_sensitive_refs(self.fp, plan)    # plan list + aluminium electrolytics (1.2.0)
        self.keep = []                                              # (patterns, rect)
        for k in plan["keepouts"]:
            self.keep.append((k.get("refs", ["*"]), k["rect"]))
        self._blocks()
        self._decaps()

    # ------------------------------------------------------------------ geometry and nets
    def _geom(self, f):
        g = {}
        for rot in (0, 90, 180, 270):
            f.SetOrientationDegrees(rot)
            p = f.GetPosition(); px, py = mm(p.x), mm(p.y)
            l, t, r, d = courtyard_rect(f)
            g[rot] = dict(rect=(l - px, t - py, r - px, d - py),
                          pads=[(q.GetNetname(), mm(q.GetPosition().x) - px, mm(q.GetPosition().y) - py) for q in f.Pads()])
        return g

    def netw(self, n):
        if not n or n.startswith("unconnected") or GNDNAME.match(n.lstrip("/")) or n.lstrip("/").upper() == "GND":
            return 0.0
        return 0.15 if (len(self.netpads.get(n, [])) > 12 or SUPPLY.match(n)) else 1.0

    def pad_xy(self, ref, pin):
        for p in self.fp[ref].Pads():
            if p.GetNumber() == pin:
                return mm(p.GetPosition().x), mm(p.GetPosition().y)

    # ------------------------------------------------------------------ blocks
    def _blocks(self):
        plan = self.plan
        left = set(self.movable)
        self.blocks = []
        for blk in plan["blocks"]:
            refs = select(blk.get("select", {}), sorted(left, key=ref_num), self.fp, self.sch)
            rects = []
            for rn in blk.get("regions", []):
                rects += plan["regions"][rn]
            rects += blk.get("rects", [])
            box = blk.get("box") or (rects[0] if rects else None)
            allowed = rects or ([box] if box else None)                # None = the whole board
            b = dict(name=blk["name"], refs=sorted(refs, key=ref_num), box=box, allowed=allowed,
                     mirror_x=blk.get("mirror_x", False), mirror_y=blk.get("mirror_y", False),
                     anchors=blk.get("anchors", {}))
            self.blocks.append(b)
            for r in refs:
                self.block_of[r] = b
            left -= refs
        self.report["unassigned"] = sorted(left)

    def _decaps(self):
        self.decap = assign_decaps(self.fp, self.movable, self.pt, self.sch, self.plan["decap_max_sch_distance"])

    # ------------------------------------------------------------------ targets
    def sch_target(self, ref, blk):
        rs = [r for r in blk["refs"] if r in self.sch]
        if ref not in self.sch or len(rs) < 2 or not blk["box"]:
            return None
        xs = [self.sch[r][1] for r in rs]; ys = [self.sch[r][2] for r in rs]
        u = (self.sch[ref][1] - min(xs)) / ((max(xs) - min(xs)) or 1)
        v = (self.sch[ref][2] - min(ys)) / ((max(ys) - min(ys)) or 1)
        if blk["mirror_x"]:
            u = 1 - u
        if blk["mirror_y"]:
            v = 1 - v
        x0, y0, x1, y1 = blk["box"]
        return x0 + 1.5 + u * (x1 - x0 - 3), y0 + 1.5 + v * (y1 - y0 - 3)

    def neighbours(self, ref, signal_only=True):
        out = []
        for net, _, _ in self.geom[ref][0]["pads"]:
            if (self.netw(net) == 1.0) if signal_only else self.netw(net) > 0:
                out += [(x, y) for rr, pl in self.padpos.items() if rr != ref for (n2, x, y) in pl if n2 == net]
        return out

    def target(self, ref):
        blk = self.block_of[ref]
        if ref in blk["anchors"]:
            return tuple(blk["anchors"][ref])
        if ref in self.decap and self.decap[ref][0] in self.placed:
            u, pin = self.decap[ref]
            px, py = self.pad_xy(u, pin); cx, cy = self.placed[u]
            vx, vy = px - cx, py - cy; n = math.hypot(vx, vy) or 1
            return px + 1.8 * vx / n, py + 1.8 * vy / n
        st = self.sch_target(ref, blk)
        nb = self.neighbours(ref) or self.neighbours(ref, False)
        if st and nb:
            return 0.5 * st[0] + 0.5 * np.mean([p[0] for p in nb]), 0.5 * st[1] + 0.5 * np.mean([p[1] for p in nb])
        if st:
            return st
        if nb:
            return float(np.mean([p[0] for p in nb])), float(np.mean([p[1] for p in nb]))
        if blk["box"]:
            x0, y0, x1, y1 = blk["box"]
            return (x0 + x1) / 2, (y0 + y1) / 2
        return (self.r.X0 + self.r.X1) / 2, (self.r.Y0 + self.r.Y1) / 2

    # ------------------------------------------------------------------ one part
    def allowed_mask(self, ref, rects):
        m = (self.INS if ref in self.sensitive else self.IN).copy()
        if rects is not None:
            m &= self.r.rects_mask(rects)
        for pats, rect in self.keep:
            if matches(ref, pats):
                m &= ~self.r.rects_mask([rect])
        # thermal separation, enforced while placing: a heat source keeps heat_min_distance from every placed
        # sensitive part, and a sensitive part from every placed heat source
        d = self.plan["heat_min_distance"]
        sens = self.heat_sensitive
        other = sens if ref in self.plan["heat"] else self.plan["heat"] if ref in sens else []
        near = [self.rect[o][0] for o in other if o in self.rect] +                [courtyard_rect(self.fp[o]) for o in other if o in self.fixed]
        if near:
            m &= ~self.r.rects_mask([(q[0] - d, q[1] - d, q[2] + d, q[3] + d) for q in near])
        return m

    def candidates(self, ref, tgt, only=None, rots=None, k=1, sep=1.5):
        """Lowest-cost free origins: up to k per rotation, at least `sep` mm apart. Returns (list, spilled)
        with list = [(cost, x, y, rot), ...] sorted by cost. Falls back to the whole board (spill) when the
        block's regions have no room."""
        blk = self.block_of[ref]
        rots = rots or ((0, 90, 180, 270) if ref.startswith(MULTI_ROT) else (0, 90))
        attempts = [self.allowed_mask(ref, only or blk["allowed"])]
        if not only and blk["allowed"] is not None:
            attempts.append(self.allowed_mask(ref, None))           # spill: anywhere on the board
        gx, gy = np.meshgrid(self.r.XS, self.r.YS)
        # the occupancy already holds each placed part's own halo; a part whose halo is larger (through-hole)
        # must also keep ITS distance from them: test it inflated by the difference (gap >= max of the two)
        ext = max(0.0, (self.plan["tht_spacing"] if is_tht(self.fp[ref]) else self.plan["spacing"]) - self.plan["spacing"])
        for att, allowed in enumerate(attempts):
            S = self.r.sat(self.occ | ~allowed)
            out = []
            for rot in rots:
                g = self.geom[ref][rot]
                rr0 = g["rect"]
                feas = self.r.feasible(S, (rr0[0] - ext, rr0[1] - ext, rr0[2] + ext, rr0[3] + ext))
                if not feas.any():
                    continue
                cost = np.hypot(gx - tgt[0], gy - tgt[1]) * (0.6 if att == 0 else 3.0)
                for net, px, py in g["pads"]:
                    w = self.netw(net)
                    if not w:
                        continue
                    others = [(x, y) for rr, pl in self.padpos.items() if rr != ref for (n2, x, y) in pl if n2 == net]
                    if not others:
                        continue
                    dmin = None
                    for x, y in others:
                        dd = np.abs(gx + px - x) + np.abs(gy + py - y)
                        dmin = dd if dmin is None else np.minimum(dmin, dd)
                    cost = cost + w * dmin
                cost = np.where(feas, cost, np.inf)
                flat = np.argsort(cost, axis=None)[: max(200, k * 50)]
                picked = []
                for idx in flat:
                    c = cost.flat[idx]
                    if not np.isfinite(c):
                        break
                    x, y = float(self.r.XS[idx % self.r.NX]), float(self.r.YS[idx // self.r.NX])
                    if all(math.hypot(x - q[1], y - q[2]) >= sep for q in picked):
                        picked.append((float(c), x, y, rot))
                    if len(picked) >= k:
                        break
                out += picked
            if out:
                return sorted(out), bool(att)
        return [], False

    def put(self, ref, x, y, rot, spilled=False):
        blk = self.block_of[ref]
        if spilled:
            self.spill.add(ref)
        f = self.fp[ref]
        f.SetOrientationDegrees(rot)
        f.SetPosition(pcbnew.VECTOR2I(FM(x), FM(y)))
        g = self.geom[ref][rot]
        rc = (x + g["rect"][0], y + g["rect"][1], x + g["rect"][2], y + g["rect"][3])
        halo = self.plan["tht_spacing"] if is_tht(f) else self.plan["spacing"]
        self.r.mark(self.occ, rc, halo)
        self.rect[ref] = (rc, halo)
        self.padpos[ref] = [(n, x + px, y + py) for n, px, py in g["pads"]]
        self.placed[ref] = (x, y)
        self.report["placed"][ref] = dict(x=round(x, 3), y=round(y, 3), rot=rot, block=blk["name"])

    def place(self, ref, tgt, only=None, rots=None):
        cands, spilled = self.candidates(ref, tgt, only, rots, k=1)
        if not cands:
            return False
        _, x, y, rot = cands[0]
        self.put(ref, x, y, rot, spilled)
        return True

    def place_decap(self, c):
        u, pin = self.decap[c]
        px, py = self.pad_xy(u, pin); cx, cy = self.placed[u]
        vx, vy = px - cx, py - cy; n = math.hypot(vx, vy) or 1
        tgt = (px + 1.8 * vx / n, py + 1.8 * vy / n)
        for w in (4, 8):                                                # near the pin first, then a wider window,
            if self.place(c, tgt, only=[(px - w, py - w, px + w, py + w)]):   # only then the block's regions
                return True
        return self.place(c, (px, py))

    def place_with_decaps(self, u, caps, k=4):
        """An IC is only as good as the room around its power pins: try the k best origins per rotation, place its
        decoupling capacitors at each, keep the combination with the shortest total capacitor distance
        (plus a small share of the IC's own cost). Without this, an IC placed late lands in a tight hole and its
        capacitors end up 10-17 mm away."""
        cands, spilled = self.candidates(u, self.target(u), k=k)
        if not cands:
            return False
        best = None
        group = [u] + caps
        for cost, x, y, rot in cands[: 4 * k]:
            snap = self.snapshot(group)
            self.put(u, x, y, rot, spilled)
            ok = all(self.place_decap(c) for c in caps)
            score = sum(self.decap_dist(c)[0] for c in caps) + 0.2 * cost if ok else float("inf")
            if best is None or score < best[0]:
                best = (score, x, y, rot)
            self.restore(snap)
        _, x, y, rot = best
        self.put(u, x, y, rot, spilled)
        for c in caps:
            if c not in self.placed and not self.place_decap(c):
                self.report["failed"].append(c)
        return True

    # ------------------------------------------------------------------ undo support for the improvement passes
    def unplace(self, ref):
        for d in (self.placed, self.padpos, self.rect, self.report["placed"]):
            d.pop(ref, None)
        self.spill.discard(ref)

    def rebuild(self):
        self.occ[:] = False
        mark_fixed(self.r, self.occ, self.b, self.fixed, self.plan)
        for rc, h in self.rect.values():
            self.r.mark(self.occ, rc, h)

    def snapshot(self, refs):
        return {r: (self.fp[r].GetPosition(), self.fp[r].GetOrientationDegrees(), self.placed.get(r), self.padpos.get(r),
                    self.rect.get(r), self.report["placed"].get(r), r in self.spill) for r in refs}

    def restore(self, snap):
        for r, (pos, rot, pl, pp, rc, rp, sp) in snap.items():
            self.fp[r].SetOrientationDegrees(rot); self.fp[r].SetPosition(pos)
            for d, v in ((self.placed, pl), (self.padpos, pp), (self.rect, rc), (self.report["placed"], rp)):
                if v is None:
                    d.pop(r, None)
                else:
                    d[r] = v
            (self.spill.add if sp else self.spill.discard)(r)
        self.rebuild()

    def decap_dist(self, c):
        """Pad-to-pad distance from the served power pin to the capacitor pad on the same rail."""
        u, pin = self.decap[c]
        px, py = self.pad_xy(u, pin)
        rail = next(p.GetNetname() for p in self.fp[u].Pads() if p.GetNumber() == pin)
        pads = [(x, y) for n, x, y in self.padpos[c] if n == rail] or [(x, y) for _, x, y in self.padpos[c]]
        return min(math.hypot(x - px, y - py) for x, y in pads), (px, py)

    # ------------------------------------------------------------------ the run
    def run(self):
        # decoupling capacitors of FIXED ICs first, before any block: their IC's position is known from the start
        # and later blocks would otherwise take the room next to its power pins
        for c in sorted([c for c in self.decap if self.decap[c][0] in self.fixed and c in self.block_of],
                        key=lambda c: cap_value(self.fp[c].GetValue())):
            if not self.place_decap(c):
                self.report["failed"].append(c)
        for blk in self.blocks:
            refs = blk["refs"]
            ics = sorted([r for r in refs if r.startswith(("U", "Q", "L", "Y", "PS", "SW", "IC", "X"))],
                         key=lambda r: -(lambda g: (g[2] - g[0]) * (g[3] - g[1]))(self.geom[r][0]["rect"]))
            order = sorted([c for c in refs if self.decap.get(c, ("",))[0] in self.fixed],
                           key=lambda c: cap_value(self.fp[c].GetValue()))
            for u in ics:
                order.append(u)
                order += sorted([c for c in refs if self.decap.get(c, ("",))[0] == u],
                                key=lambda c: cap_value(self.fp[c].GetValue()))
            order += [r for r in refs if r not in order]
            for ref in order:
                if ref in self.placed:
                    continue
                caps = sorted([c for c in refs if self.decap.get(c, ("",))[0] == ref and c not in self.placed],
                              key=lambda c: cap_value(self.fp[c].GetValue()))
                ok = self.place_with_decaps(ref, caps) if caps else self.place(ref, self.target(ref))
                if not ok:
                    self.report["failed"].append(ref)
        self.improve_decaps()
        self.improve_clusters()
        self.finish()

    def small(self, r):
        return r not in self.fixed and r not in self.decap and (r[0] in "RCDF" or r.startswith("TP")) and r in self.rect

    def improve_decaps(self, limit=2.6):
        for c in sorted([c for c in self.decap if c in self.placed], key=lambda c: -self.decap_dist(c)[0]):
            d0, (px, py) = self.decap_dist(c)
            if d0 <= limit:
                continue
            near = sorted([r for r in self.placed if r != c and self.small(r)
                           and math.hypot((self.rect[r][0][0] + self.rect[r][0][2]) / 2 - px, (self.rect[r][0][1] + self.rect[r][0][3]) / 2 - py) < 5],
                          key=lambda r: math.hypot((self.rect[r][0][0] + self.rect[r][0][2]) / 2 - px, (self.rect[r][0][1] + self.rect[r][0][3]) / 2 - py))
            for k in range(0, min(4, len(near)) + 1):
                group = [c] + near[:k]
                snap = self.snapshot(group)
                for r in group:
                    self.unplace(r)
                self.rebuild()
                u = self.decap[c][0]; cx, cy = self.placed[u]
                vx, vy = px - cx, py - cy; n = math.hypot(vx, vy) or 1
                ok = self.place(c, (px + 1.8 * vx / n, py + 1.8 * vy / n), only=[(px - 3.2, py - 3.2, px + 3.2, py + 3.2)])
                if ok and self.decap_dist(c)[0] < d0 - 0.3 and all(self.place(r, self.target(r)) for r in near[:k]) \
                        and not (self.spill & set(near[:k])):
                    self.report["improved"].append([c, round(d0, 2), round(self.decap_dist(c)[0], 2), near[:k]])
                    break
                self.restore(snap)

    def improve_clusters(self, limit=2.6):
        def cost(u):
            cs = [c for c in self.decap if self.decap[c][0] == u and c in self.placed]
            return sum(self.decap_dist(c)[0] for c in cs), cs
        for u in sorted({self.decap[c][0] for c in self.decap if c in self.placed and self.decap[c][0] not in self.fixed},
                        key=lambda u: -cost(u)[0]):
            c0, caps = cost(u)
            if not caps or max(self.decap_dist(c)[0] for c in caps) <= limit or u not in self.placed:
                continue
            ux, uy = self.placed[u]
            near = [r for r in self.placed if r != u and r not in caps and self.small(r)
                    and math.hypot((self.rect[r][0][0] + self.rect[r][0][2]) / 2 - ux, (self.rect[r][0][1] + self.rect[r][0][3]) / 2 - uy) < 7]
            group = [u] + caps + near
            base = self.snapshot(group)
            best = (c0, None)
            blk_rects = self.block_of[u]["allowed"]
            for win, rot in [(w, r) for w in (4, 8) for r in (0, 90, 180, 270)]:
                if win == 8 and best[1] is not None:
                    break                                  # the small window already improved it
                for r in group:
                    self.unplace(r)
                self.rebuild()
                window = (ux - win, uy - win, ux + win, uy + win)
                only = [window] if blk_rects is None else [
                    (max(a[0], window[0]), max(a[1], window[1]), min(a[2], window[2]), min(a[3], window[3]))
                    for a in blk_rects if a[0] < window[2] and window[0] < a[2] and a[1] < window[3] and window[1] < a[3]] or [window]
                ok = self.place(u, (ux, uy), only=only, rots=(rot,))
                for c in sorted(caps, key=lambda c: cap_value(self.fp[c].GetValue())):
                    if not ok:
                        break
                    px, py = self.pad_xy(u, self.decap[c][1]); vx, vy = px - self.placed[u][0], py - self.placed[u][1]
                    n = math.hypot(vx, vy) or 1
                    ok = self.place(c, (px + 1.8 * vx / n, py + 1.8 * vy / n), only=[(px - 4, py - 4, px + 4, py + 4)]) \
                        or self.place(c, (px, py))
                ok = ok and all(self.place(r, self.target(r)) for r in near)
                if ok and not (self.spill & set(group)) and cost(u)[0] < best[0] - 0.5:
                    best = (cost(u)[0], self.snapshot(group))
                self.restore(base)
            if best[1]:
                self.restore(best[1])
                self.report["improved"].append([u, "cluster", round(c0, 1), round(best[0], 1)])

    def finish(self):
        for r, (rc, _) in self.rect.items():
            cx, cy = (rc[0] + rc[2]) / 2, (rc[1] + rc[3]) / 2
            al = self.block_of[r]["allowed"]
            if al is not None and not any(a <= cx <= c and t <= cy <= d for a, t, c, d in al):
                self.report["out_of_zone"].append(f"{r} ({self.block_of[r]['name']})")
        self.report["spilled"] = sorted(self.spill)
        for c, (u, pin) in self.decap.items():
            if c in self.placed:
                self.report["decap"][c] = dict(ic=u, pin=pin, function=self.pt.get(f"{u}.{pin}", ["", "", ""])[1],
                                               dist=round(self.decap_dist(c)[0], 2))
        if self.plan.get("lock_fixed", True):
            bb = self.b.GetBoardEdgesBoundingBox()
            for r in self.fixed:
                if bb.Contains(self.fp[r].GetPosition()):
                    self.fp[r].SetLocked(True)

    def budget(self):
        print(f"{'block':30s} {'parts':>5s} {'demand':>8s} {'free':>8s} {'ratio':>6s}")
        tot = 0
        for blk in self.blocks:
            dem = 0
            for r in blk["refs"]:
                l, t, rr, d = self.geom[r][0]["rect"]
                h = self.plan["tht_spacing"] if is_tht(self.fp[r]) else self.plan["spacing"]
                dem += (rr - l + h) * (d - t + h)
            tot += dem
            av = self.r.area(~self.occ & self.IN & (self.r.rects_mask(blk["allowed"]) if blk["allowed"] else True))
            print(f"{blk['name'][:30]:30s} {len(blk['refs']):5d} {dem:8.0f} {av:8.0f} {dem / max(av, 1):6.2f}")
        free = self.r.area(~self.occ & self.IN)
        print(f"{'TOTAL':30s} {sum(len(b['refs']) for b in self.blocks):5d} {tot:8.0f} {free:8.0f} {tot / max(free, 1):6.2f}")
        if self.report["unassigned"]:
            print("UNASSIGNED (add them to a block):", " ".join(self.report["unassigned"]))
        print(f"decoupling capacitors recognised: {len(self.decap)}"
              + ("" if self.pt else "  (no pintypes.json: only supply-like pin names are used)"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plan")
    ap.add_argument("--out", help="output .kicad_pcb (required unless --budget)")
    ap.add_argument("--report", help="report JSON (default: next to --out)")
    ap.add_argument("--budget", action="store_true", help="print demand vs free area per block and exit")
    a = ap.parse_args()
    pl = Placer(load_plan(a.plan))
    if a.budget:
        pl.budget()
        return 0
    if not a.out:
        sys.exit("--out is required (the input board is never overwritten)")
    if os.path.abspath(a.out) == os.path.abspath(pl.plan["board"]):
        sys.exit("--out must differ from the input board")
    bb = pl.b.GetBoardEdgesBoundingBox()
    off = sorted(r for r in pl.fixed if not bb.Contains(pl.fp[r].GetPosition()))
    if off:
        print(f"WARNING: fixed but OUTSIDE the outline - they will not be placed: {off}")
    if pl.report["unassigned"]:
        sys.exit("unassigned parts (add them to a block or a catch-all block {\"select\": {\"all\": true}}): "
                 + " ".join(pl.report["unassigned"]))
    pl.run()
    pcbnew.SaveBoard(a.out, pl.b)
    rp = a.report or os.path.splitext(a.out)[0] + "_report.json"
    json.dump(pl.report, open(rp, "w"), indent=1)
    d = pl.report["decap"]
    print(f"placed {len(pl.report['placed'])} / {len(pl.movable)}; failed {pl.report['failed']}; "
          f"spilled {pl.report['spilled']}; out of zone {pl.report['out_of_zone']}")
    if d:
        ds = sorted(v["dist"] for v in d.values())
        print(f"decoupling: {len(d)} caps, <= 2.6 mm: {sum(x <= 2.6 for x in ds)}, <= 4 mm: {sum(x <= 4 for x in ds)}, "
              f"worst {ds[-1]} mm")
    print(f"improvements: {len(pl.report['improved'])}; board -> {a.out}; report -> {rp}")
    return 1 if pl.report["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
