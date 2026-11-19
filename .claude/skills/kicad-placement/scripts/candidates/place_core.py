"""Placement optimiser core: simulated annealing over a board model.

No pcbnew here. Input is the JSON written by extract_model.py, output is a JSON with
one position/rotation per footprint. Any Python with numpy works (scipy is used when
present, for the decoupling-capacitor assignment).

    python place_core.py model.json cand.json --seed 3 --profile balanced --moves 1500000

Cost (all lengths in mm), minimised:

    wl      weighted half-perimeter wirelength of signal nets (plane nets excluded)
    dec     distance from each decoupling capacitor to the IC power pin it serves
    ov      courtyard overlap area between footprints sharing a board side
    fb      courtyard area outside the outline or inside a footprint keep-out
    sheet   spread of each schematic sheet around its own centroid
    dom     spread of each minority ground domain around its own centroid
    clu     spread of each schematic cluster (a hub and the small parts wired to it)
    reg     spread of each off-board placement region (a grouping directive)

Locked footprints never move; they act as obstacles and as anchors: a cluster or an
off-board region that contains locked parts is pulled to them instead of to its own
centroid.

Placement regions drawn on the board are hard: their members pay the fb cost outside
the region, and an exclusive region (ISO_ name) charges every other footprint inside it.
"""
import argparse
import json
import math
import random
import re
import time

GROUND_RE = re.compile(r"GND|VSS|CHASSIS|EARTH", re.I)
POWER_RE = re.compile(r"^[+-]\d|^\+|^V(CC|DD|BUS|BAT|IN)\b|^\d+V\d*", re.I)
IC_PREFIX = ("U", "PS", "Q", "IC")

PROFILES = {
    # name: weights
    # clu was calibrated on GapOne_CON: at these values the groups get ~13% tighter for
    # about the same routing index; 3x these values tightens ~19% but costs ~6% of index.
    "balanced":   {"wl": 1.0, "dec": 2.0, "sheet": 0.010, "dom": 0.020, "clu": 0.018, "reg": 0.10},
    "wirelength": {"wl": 1.0, "dec": 1.0, "sheet": 0.000, "dom": 0.010, "clu": 0.006, "reg": 0.05},
    "blocks":     {"wl": 1.0, "dec": 2.0, "sheet": 0.040, "dom": 0.040, "clu": 0.036, "reg": 0.20},
    "decoupling": {"wl": 1.0, "dec": 5.0, "sheet": 0.010, "dom": 0.020, "clu": 0.018, "reg": 0.10},
}
KIND_W = {"sheet": "sheet", "dom": "dom", "cluster": "clu", "region": "reg"}
CLUSTER_NET_PINS = 6   # a net with more pins than this is a bus/rail, not a "wire"
HUB_PADS = 4           # a part with at least this many connected pads can own a cluster
W_OV = 60.0      # per mm2 of overlap at the end of the anneal
W_FB = 120.0     # per mm2 outside the board / inside a keep-out
W_PP = 12.0      # per mm a constrained pin pair is beyond its limit
PAIR_COST = 0.05  # mm2-equivalent added per overlapping pair (kills zero-gradient nesting)
CELL = 3.0       # spatial hash cell, mm
RES = 0.2        # forbidden-area raster, mm


def rot_pt(lx, ly, deg):
    d = deg % 360.0
    if d == 0.0:
        return lx, ly
    if d == 90.0:
        return ly, -lx
    if d == 180.0:
        return -lx, -ly
    if d == 270.0:
        return -ly, lx
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return lx * c + ly * s, -lx * s + ly * c


def ref_prefix(ref):
    return "".join(ch for ch in ref if ch.isalpha())


def raster_inside(poly, gx, gy):
    import numpy as np
    xs, ys = np.meshgrid(gx, gy)
    inside = np.zeros(xs.shape, dtype=bool)
    n = len(poly)
    for a in range(n):
        x1, y1 = poly[a]
        x2, y2 = poly[(a + 1) % n]
        if y1 == y2:
            continue
        cond = (y1 > ys) != (y2 > ys)
        xi = (x2 - x1) * (ys - y1) / (y2 - y1) + x1
        inside ^= cond & (xs < xi)
    return inside


class Problem:
    def __init__(self, model, margin=0.15, big_net=40):
        import numpy as np
        comps = list(model["comps"])
        self.n_real = len(comps)
        # A locked through-hole part only occupies the opposite side where its pins come
        # through, so parts may sit over its body there (e.g. SMD over a bottom-side
        # terminal block). Model that as: body on its own side + one fixed obstacle per
        # through pad on the other side. Unlocked through-hole parts stay two-sided.
        split = set()
        for c in model["comps"]:
            if c["locked"] and c["through"] and all("bb" in p for p in c["pads"]):
                split.add(c["ref"])
                for p in c["pads"]:
                    if p.get("th"):
                        comps.append({"ref": "%s#%s" % (c["ref"], p["num"]), "value": "", "sheet": c["sheet"],
                                      "back": not c["back"], "through": False, "locked": True,
                                      "x": c["x"], "y": c["y"], "rot": c["rot"], "rect": p["bb"],
                                      "pads": [], "synthetic": True})
        self.comps = comps
        self.model = model
        self.margin = margin
        self.n = n = len(comps)
        self.refs = [c["ref"] for c in comps]
        self.sheet = [c["sheet"] for c in comps]
        self.fixed = [bool(c["locked"]) for c in comps]
        self.movable = [i for i in range(n) if not self.fixed[i]]
        self.side = [(2 if c["back"] else 1) if (c["ref"] in split or not c["through"]) else 3
                     for c in comps]

        # rotations available to each footprint
        self.rots = []
        self.K = []
        for c in comps:
            if c["locked"]:
                self.rots.append([c["rot"]])
                self.K.append(0)
            else:
                self.rots.append([0.0, 90.0, 180.0, 270.0])
                self.K.append(int(round(c["rot"] / 90.0)) % 4)
        self.X = [c["x"] for c in comps]
        self.Y = [c["y"] for c in comps]

        # geometry per rotation: inflated courtyard rect, true rect, pad offsets
        h = margin / 2.0
        self.RECT, self.RECT0, self.PADOFF, self.AREA = [], [], [], []
        for c, rl in zip(comps, self.rots):
            x0, y0, x1, y1 = c["rect"]
            per_r, per_r0, per_p = [], [], []
            for deg in rl:
                cs = [rot_pt(x, y, deg) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
                ax0, ay0 = min(p[0] for p in cs), min(p[1] for p in cs)
                ax1, ay1 = max(p[0] for p in cs), max(p[1] for p in cs)
                per_r0.append((ax0, ay0, ax1, ay1))
                per_r.append((ax0 - h, ay0 - h, ax1 + h, ay1 + h))
                per_p.append([rot_pt(p["x"], p["y"], deg) for p in c["pads"]])
            self.RECT.append(per_r)
            self.RECT0.append(per_r0)
            self.PADOFF.append(per_p)
            self.AREA.append((x1 - x0) * (y1 - y0))

        # nets
        count = {}
        for c in comps:
            for p in c["pads"]:
                if p["net"]:
                    count[p["net"]] = count.get(p["net"], 0) + 1
        plane = set(model.get("plane_nets", []))
        self.net_names = sorted(nm for nm, k in count.items() if k >= 2)
        nid = {nm: i for i, nm in enumerate(self.net_names)}
        self.is_ground = [bool(GROUND_RE.search(nm)) for nm in self.net_names]
        self.is_plane = [nm in plane or self.is_ground[i] or count[nm] > big_net
                         for i, nm in enumerate(self.net_names)]
        self.is_power = [(not self.is_ground[i]) and (bool(POWER_RE.search(nm)) or count[nm] >= 10)
                         for i, nm in enumerate(self.net_names)]
        self.NW = []
        for i, nm in enumerate(self.net_names):
            if self.is_plane[i]:
                self.NW.append(0.0)
            elif self.is_power[i]:
                self.NW.append(0.3)
            else:
                self.NW.append(1.0)
        self.NETP = [[] for _ in self.net_names]
        self.PADNET = []
        for i, c in enumerate(comps):
            pn = []
            for q, p in enumerate(c["pads"]):
                k = nid.get(p["net"], -1)
                pn.append(k)
                if k >= 0:
                    self.NETP[k].append((i, q))
            self.PADNET.append(pn)
        self.CN = [sorted({k for k in pn if k >= 0 and self.NW[k] > 0.0}) for pn in self.PADNET]

        # pin pairs with a distance limit: datasheet decoupling entries (this cap pad at
        # that IC pin) and pairs the source placement already keeps tight
        self.PP = []
        self.PPC = [[] for _ in range(n)]
        by_ref = {c["ref"]: i for i, c in enumerate(comps[:self.n_real])}
        pinned_caps = set()
        for pp in model.get("pin_pairs", []):
            i, j = by_ref.get(pp["a"][0]), by_ref.get(pp["b"][0])
            if i is None or j is None:
                continue
            qi = next((q for q, p in enumerate(comps[i]["pads"]) if p["num"] == pp["a"][1]), None)
            qj = next((q for q, p in enumerate(comps[j]["pads"]) if p["num"] == pp["b"][1]), None)
            if qi is None or qj is None:
                continue
            k = len(self.PP)
            self.PP.append((i, qi, j, qj, float(pp["max"])))
            self.PPC[i].append(k)
            self.PPC[j].append(k)
            if pp.get("kind") == "decoupling":
                pinned_caps.add(j)
        self.PV = [0.0] * len(self.PP)

        # decoupling capacitors: 2-pad C with one pad on a rail and the other on ground/rail
        self.dec_groups = []
        groups = {}
        for i, c in enumerate(comps):
            if ref_prefix(c["ref"]) != "C" or i in pinned_caps:
                continue
            netted = [(q, k) for q, k in enumerate(self.PADNET[i]) if k >= 0]
            if len(netted) != 2:
                continue
            (qa, ka), (qb, kb) = netted
            pa, pb = self.is_power[ka], self.is_power[kb]
            ga, gb = self.is_plane[ka] and not pa, self.is_plane[kb] and not pb
            if pa and (gb or pb):
                groups.setdefault(ka, []).append((i, qa))
            elif pb and ga:
                groups.setdefault(kb, []).append((i, qb))
        for k, caps in groups.items():
            targets = [(j, q) for (j, q) in self.NETP[k]
                       if ref_prefix(self.refs[j]) in IC_PREFIX and len(comps[j]["pads"]) >= 3]
            if not targets:
                continue
            by_sheet = {}
            for cap in caps:
                by_sheet.setdefault(self.sheet[cap[0]], []).append(cap)
            for sh, cl in by_sheet.items():
                local = [t for t in targets if self.sheet[t[0]] == sh]
                self.dec_groups.append((cl, local or targets))
        self.CAPT = [None] * n          # cap -> (own pad, target comp, target pad)
        self.DEPS = [[] for _ in range(n)]
        self.DC = [0.0] * n

        # spread groups: sheets, and minority ground domains
        self.GRP = [[] for _ in range(n)]
        self.ANC = [[] for _ in range(n)]   # anchored groups: (group, target x, target y)
        self.g_kind, self.g_n, self.g_sx, self.g_sy = [], [], [], []
        self.GW = []
        by = {}
        for i in range(self.n_real):
            by.setdefault(self.sheet[i], []).append(i)
        for sh, mem in sorted(by.items()):
            if len(mem) >= 3:
                self._add_group("sheet", mem)
        dom = {}
        for i in range(n):
            gs = {k for k in self.PADNET[i] if k >= 0 and self.is_ground[k]}
            if len(gs) == 1:
                dom.setdefault(next(iter(gs)), []).append(i)
        if len(dom) >= 2:
            biggest = max(dom, key=lambda k: len(dom[k]))
            for k, mem in sorted(dom.items()):
                if k != biggest and len(mem) >= 4:
                    self._add_group("dom", mem)
        self.domains = {self.net_names[k]: [self.refs[i] for i in mem] for k, mem in dom.items()}

        # schematic clusters and off-board regions (grouping directives)
        idx = {self.refs[i]: i for i in range(self.n_real)}
        regions = model.get("regions", [])
        self.clusters = self._build_clusters()
        for mem in self.clusters:
            self._add_cluster("cluster", mem)
        self.soft_regions = []
        for r in regions:
            mem = [idx[ref] for ref in r["members"] if ref in idx]
            if not r["onboard"] and len(mem) >= 2:
                self.soft_regions.append((r["name"], mem))
                self._add_cluster("region", mem)

        # forbidden raster (outside outline, inside footprint keep-outs) as an integral image
        ol = model["outline"]
        self.bx0, self.by0 = min(p[0] for p in ol), min(p[1] for p in ol)
        self.bx1, self.by1 = max(p[0] for p in ol), max(p[1] for p in ol)
        self.nx = int(math.ceil((self.bx1 - self.bx0) / RES))
        self.ny = int(math.ceil((self.by1 - self.by0) / RES))
        gx = self.bx0 + (np.arange(self.nx) + 0.5) * RES
        gy = self.by0 + (np.arange(self.ny) + 0.5) * RES
        def dilate(mask, k):
            out = mask.copy()
            h, w = mask.shape
            for dy in range(-k, k + 1):
                for dx in range(-k, k + 1):
                    if dx or dy:
                        out[max(0, dy):h + min(0, dy), max(0, dx):w + min(0, dx)] |= \
                            mask[max(0, -dy):h + min(0, -dy), max(0, -dx):w + min(0, -dx)]
            return out

        # When optimising (margin > 0) the forbidden ground is grown: the board edge by
        # the copper-to-edge rule, keep-outs by one raster cell, because an overlap
        # smaller than half a cell is invisible to the raster but not to KiCad's DRC.
        # Scoring (margin 0) uses the true shapes, so an existing placement is not
        # penalised for the guard band.
        guard = margin > 0
        forb = ~raster_inside(ol, gx, gy)
        if guard:
            ke = int(math.ceil(model.get("edge_clearance", 0.0) / RES))
            pad = np.ones((self.ny + 2 * ke, self.nx + 2 * ke), dtype=bool)
            pad[ke:ke + self.ny, ke:ke + self.nx] = forb
            forb = dilate(pad, ke)[ke:ke + self.ny, ke:ke + self.nx] if ke else forb
        for ko in model.get("keepouts", []):
            m = raster_inside(ko["pts"], gx, gy)
            forb |= dilate(m, 1) if guard else m

        def integral(mask):
            integ = np.zeros((self.ny + 1, self.nx + 1), dtype=np.int64)
            integ[1:, 1:] = mask.astype(np.int64).cumsum(0).cumsum(1)
            return integ.tolist()

        def cells(mask):
            return [(int(ix), int(iy)) for iy, ix in zip(*np.nonzero(~mask))][::7]

        self.S = integral(forb)
        self.free_cells = cells(forb)

        # hard regions: one forbidden raster per distinct (regions, side) combination.
        # SI[i] selects the raster footprint i is judged against; 0 is the plain board.
        self.SS = [self.S]
        self.FREE = [self.free_cells]
        self.SI = [0] * n
        hard = [r for r in regions if r["onboard"]]
        self.hard_regions = hard
        memb = [[] for _ in range(n)]
        for h, r in enumerate(hard):
            for ref in r["members"]:
                if ref in idx:
                    memb[idx[ref]].append(h)
        excl = [h for h, r in enumerate(hard) if r["exclusive"]]
        rmask = {}

        def inside(h, side):
            key = (h, side)
            if key not in rmask:
                polys = [p for p in hard[h]["polys"] if p["onboard"]
                         and ((p["top"] and side & 1) or (p["bottom"] and side & 2))]
                m = np.zeros(forb.shape, dtype=bool)
                for p in polys:
                    m |= raster_inside(p["pts"], gx, gy)
                rmask[key] = (m, bool(polys))
            return rmask[key]

        self.region_notes = []
        cache = {}
        for i in range(self.n_real):
            if not memb[i] and not excl:
                continue
            key = (tuple(memb[i]), self.side[i])
            if key not in cache:
                f = forb.copy()
                for h in memb[i]:
                    m, ok = inside(h, self.side[i])
                    if not ok:      # region has no polygon on this footprint's side
                        m = inside(h, 3)[0]
                    f |= ~m
                for h in excl:
                    if h not in memb[i]:
                        f |= inside(h, self.side[i])[0]
                cache[key] = len(self.SS)
                self.SS.append(integral(f))
                self.FREE.append(cells(f) or self.free_cells)
            self.SI[i] = cache[key]
            for h in memb[i]:
                if not inside(h, self.side[i])[1]:
                    self.region_notes.append("%s: região %s não tem polígono no lado deste componente" % (
                        self.refs[i], hard[h]["name"]))
        self.region_info = []
        for h, r in enumerate(hard):
            mem = [idx[ref] for ref in r["members"] if ref in idx]
            area = float((inside(h, 3)[0] & ~forb).sum()) * RES * RES
            self.region_info.append({
                "name": r["name"], "exclusive": r["exclusive"], "members": len(mem),
                "area": round(area, 1), "need": round(sum(self.AREA[i] for i in mem), 1)})

        self.W = dict(PROFILES["balanced"])
        self.w_ov = W_OV
        self.w_fb = W_FB
        self.CUR = [None] * n
        self.H = {}
        self.HP = [0.0] * len(self.net_names)
        self.FB = [0.0] * n
        self.refresh()

    # ---------------------------------------------------------------- setup helpers
    def _add_group(self, kind, mem):
        g = len(self.g_kind)
        self.g_kind.append(kind)
        self.g_n.append(len(mem))
        self.g_sx.append(0.0)
        self.g_sy.append(0.0)
        self.GW.append(0.0)
        for i in mem:
            self.GRP[i].append(g)

    def _build_clusters(self):
        """Schematic-based clustering: every small part joins the hub (IC, connector...)
        it is wired to through a small signal net, directly or through other small parts.
        Small parts wired only to each other form a hub-less cluster."""
        nr = self.n_real
        npad = [sum(1 for k in self.PADNET[i] if k >= 0) for i in range(nr)]
        adj = [{} for _ in range(nr)]
        for k, pl in enumerate(self.NETP):
            if self.NW[k] != 1.0 or len(pl) > CLUSTER_NET_PINS:
                continue
            cs = sorted({i for i, _ in pl if i < nr})
            if len(cs) < 2:
                continue
            w = 1.0 / (len(cs) - 1)
            for a in cs:
                for b in cs:
                    if a != b:
                        adj[a][b] = adj[a].get(b, 0.0) + w
        owner = [i if npad[i] >= HUB_PADS else -1 for i in range(nr)]
        while True:
            new = {}
            for s in range(nr):
                if owner[s] >= 0 or not adj[s]:
                    continue
                score = {}
                for j, w in adj[s].items():
                    o = owner[j]
                    if o >= 0:
                        score[o] = score.get(o, 0.0) + w * (2.0 if self.sheet[o] == self.sheet[s] else 1.0)
                if score:
                    new[s] = max(sorted(score), key=lambda o: score[o])
            if not new:
                break
            for s, o in new.items():
                owner[s] = o
        # leftovers wired to each other
        for s in range(nr):
            if owner[s] >= 0 or not adj[s]:
                continue
            stack, comp = [s], []
            owner[s] = s
            while stack:
                a = stack.pop()
                comp.append(a)
                for j in adj[a]:
                    if owner[j] < 0:
                        owner[j] = s
                        stack.append(j)
        by = {}
        for i in range(nr):
            if owner[i] >= 0:
                by.setdefault(owner[i], []).append(i)
        return [mem for _, mem in sorted(by.items()) if len(mem) >= 2]

    def _add_cluster(self, kind, mem):
        """A group that sticks to its locked members when it has any (anchoring),
        otherwise a free group held together around its own centroid."""
        anchors = [i for i in mem if self.fixed[i]]
        free = [i for i in mem if not self.fixed[i]]
        if not free:
            return
        if not anchors:
            self._add_group(kind, mem)
            return
        g = len(self.g_kind)
        self.g_kind.append(kind)
        self.g_n.append(len(free))
        self.g_sx.append(0.0)
        self.g_sy.append(0.0)
        self.GW.append(0.0)
        # each free member aims at the anchor pads it is wired to, else at the anchors
        apads = {}
        for a in anchors:
            for q, k in enumerate(self.PADNET[a]):
                if k >= 0:
                    o = self.PADOFF[a][0][q]
                    apads.setdefault(k, []).append((self.X[a] + o[0], self.Y[a] + o[1]))
        target = {}
        for i in free:
            for want in (1.0, 0.3):
                pts = [p for k in set(self.PADNET[i]) if k >= 0 and self.NW[k] == want
                       for p in apads.get(k, ())]
                if pts:
                    target[i] = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
                    break
        if target:
            fx = sum(t[0] for t in target.values()) / len(target)
            fy = sum(t[1] for t in target.values()) / len(target)
        else:
            fx = sum(self.X[a] for a in anchors) / len(anchors)
            fy = sum(self.Y[a] for a in anchors) / len(anchors)
        for i in free:
            tx, ty = target.get(i, (fx, fy))
            self.ANC[i].append((g, tx, ty))

    def set_profile(self, name, cluster=1.0):
        """cluster scales the schematic-clustering weight: 0 turns it off, 1 is the
        profile's own value. Regions drawn by the user are never scaled."""
        self.W = dict(PROFILES[name])
        self.W["clu"] *= cluster
        for g, kind in enumerate(self.g_kind):
            self.GW[g] = self.W.get(KIND_W[kind], 0.0)

    def refresh(self):
        """Rebuild every cache from X/Y/K."""
        n = self.n
        self.H = {}
        for i in range(n):
            r = self.RECT[i][self.K[i]]
            x, y = self.X[i], self.Y[i]
            self.CUR[i] = (x + r[0], y + r[1], x + r[2], y + r[3])
            self._hash_add(i)
        for g in range(len(self.g_kind)):
            self.g_sx[g] = 0.0
            self.g_sy[g] = 0.0
        for i in range(n):
            for g in self.GRP[i]:
                self.g_sx[g] += self.X[i]
                self.g_sy[g] += self.Y[i]
        for k in range(len(self.net_names)):
            self.HP[k] = self.hpwl(k) if self.NW[k] > 0.0 else 0.0
        for i in range(n):
            self.FB[i] = 0.0 if self.fixed[i] else self.forb(i)
        for i in range(n):
            self.DC[i] = self.capdist(i) if self.CAPT[i] is not None else 0.0
        for k in range(len(self.PP)):
            self.PV[k] = self.pairpen(k)

    def pairdist(self, k):
        i, qi, j, qj, _ = self.PP[k]
        a = self.PADOFF[i][self.K[i]][qi]
        b = self.PADOFF[j][self.K[j]][qj]
        return math.hypot(self.X[i] + a[0] - self.X[j] - b[0], self.Y[i] + a[1] - self.Y[j] - b[1])

    def pairpen(self, k):
        d = self.pairdist(k) - self.PP[k][4]
        return d if d > 0.0 else 0.0

    def pair_viol(self, tol=0.01):
        """Pin pairs beyond their limit: [(ref.pad, ref.pad, distance, limit)]."""
        out = []
        for k, (i, qi, j, qj, lim) in enumerate(self.PP):
            d = self.pairdist(k)
            if d > lim + tol:
                out.append(("%s.%s" % (self.refs[i], self.comps[i]["pads"][qi]["num"]),
                            "%s.%s" % (self.refs[j], self.comps[j]["pads"][qj]["num"]), round(d, 2), lim))
        return out

    def _cells(self, cur):
        inv = 1.0 / CELL
        return [cx * 8192 + cy
                for cx in range(int(cur[0] * inv), int(cur[2] * inv) + 1)
                for cy in range(int(cur[1] * inv), int(cur[3] * inv) + 1)]

    def _hash_add(self, i):
        H = self.H
        for key in self._cells(self.CUR[i]):
            cell = H.get(key)
            if cell is None:
                H[key] = {i}
            else:
                cell.add(i)

    def _hash_del(self, i, cur):
        H = self.H
        for key in self._cells(cur):
            H[key].discard(i)

    # ---------------------------------------------------------------- cost terms
    def hpwl(self, k):
        X, Y, K, PO = self.X, self.Y, self.K, self.PADOFF
        pl = self.NETP[k]
        i, q = pl[0]
        o = PO[i][K[i]][q]
        x0 = x1 = X[i] + o[0]
        y0 = y1 = Y[i] + o[1]
        for i, q in pl[1:]:
            o = PO[i][K[i]][q]
            x = X[i] + o[0]
            y = Y[i] + o[1]
            if x < x0:
                x0 = x
            elif x > x1:
                x1 = x
            if y < y0:
                y0 = y
            elif y > y1:
                y1 = y
        return (x1 - x0) + (y1 - y0)

    def forb(self, i, S=None):
        """Courtyard area of footprint i on forbidden ground. S overrides the raster
        (pass self.S to ignore placement regions)."""
        if S is None:
            S = self.SS[self.SI[i]]
        a = self.CUR[i]
        inv = 1.0 / RES
        ux0 = int(round((a[0] - self.bx0) * inv))
        ux1 = int(round((a[2] - self.bx0) * inv))
        uy0 = int(round((a[1] - self.by0) * inv))
        uy1 = int(round((a[3] - self.by0) * inv))
        ix0 = 0 if ux0 < 0 else (self.nx if ux0 > self.nx else ux0)
        ix1 = 0 if ux1 < 0 else (self.nx if ux1 > self.nx else ux1)
        iy0 = 0 if uy0 < 0 else (self.ny if uy0 > self.ny else uy0)
        iy1 = 0 if uy1 < 0 else (self.ny if uy1 > self.ny else uy1)
        cnt =S[iy1][ix1] - S[iy0][ix1] - S[iy1][ix0] + S[iy0][ix0]
        outside = (ux1 - ux0) * (uy1 - uy0) - (ix1 - ix0) * (iy1 - iy0)
        return (cnt + outside) * RES * RES

    def ov_others(self, i, skip):
        """Overlap of footprint i (at CUR[i]) with every footprint not in skip."""
        a = self.CUR[i]
        ax0, ay0, ax1, ay1 = a
        si = self.side[i]
        side, CUR, H = self.side, self.CUR, self.H
        inv = 1.0 / CELL
        tot = 0.0
        seen = None
        cx0, cx1 = int(ax0 * inv), int(ax1 * inv)
        cy0, cy1 = int(ay0 * inv), int(ay1 * inv)
        multi = cx0 != cx1 or cy0 != cy1
        if multi:
            seen = set()
        for cx in range(cx0, cx1 + 1):
            base = cx * 8192
            for cy in range(cy0, cy1 + 1):
                cell = H.get(base + cy)
                if not cell:
                    continue
                for j in cell:
                    if j == i or j in skip:
                        continue
                    if multi:
                        if j in seen:
                            continue
                        seen.add(j)
                    if not (si & side[j]):
                        continue
                    b = CUR[j]
                    w = (ax1 if ax1 < b[2] else b[2]) - (ax0 if ax0 > b[0] else b[0])
                    if w <= 0.0:
                        continue
                    hh = (ay1 if ay1 < b[3] else b[3]) - (ay0 if ay0 > b[1] else b[1])
                    if hh <= 0.0:
                        continue
                    tot += w * hh + PAIR_COST
        return tot

    def pair_ov(self, i, j):
        if not (self.side[i] & self.side[j]):
            return 0.0
        a, b = self.CUR[i], self.CUR[j]
        w = min(a[2], b[2]) - max(a[0], b[0])
        hh = min(a[3], b[3]) - max(a[1], b[1])
        if w <= 0.0 or hh <= 0.0:
            return 0.0
        return w * hh + PAIR_COST

    def capdist(self, c):
        q, t, tq = self.CAPT[c]
        o = self.PADOFF[c][self.K[c]][q]
        p = self.PADOFF[t][self.K[t]][tq]
        return abs(self.X[c] + o[0] - self.X[t] - p[0]) + abs(self.Y[c] + o[1] - self.Y[t] - p[1])

    def spread_move(self, i, ox, oy, nx, ny):
        """Apply a move to the group sums and return the weighted cost change."""
        d = 0.0
        dx, dy = nx - ox, ny - oy
        dq = nx * nx + ny * ny - ox * ox - oy * oy
        gsx, gsy, gn, GW = self.g_sx, self.g_sy, self.g_n, self.GW
        for g in self.GRP[i]:
            sx, sy = gsx[g], gsy[g]
            nsx, nsy = sx + dx, sy + dy
            if GW[g]:
                d += GW[g] * (dq - (nsx * nsx + nsy * nsy - sx * sx - sy * sy) / gn[g])
            gsx[g], gsy[g] = nsx, nsy
        for g, tx, ty in self.ANC[i]:
            if GW[g]:
                d += GW[g] * (dq - 2.0 * (tx * dx + ty * dy))
        return d

    def region_viol(self, eps=1e-6):
        """Footprints breaking a placement region: (movable refs, locked refs)."""
        mv, lk = [], []
        for i in range(self.n_real):
            if self.SI[i] and self.forb(i) - self.forb(i, self.S) > eps:
                (lk if self.fixed[i] else mv).append(self.refs[i])
        return mv, lk

    def cluster_spread(self):
        """Mean distance (mm) from a cluster member to its cluster's centroid."""
        tot, m = 0.0, 0
        for mem in self.clusters + [r[1] for r in self.soft_regions]:
            cx = sum(self.X[i] for i in mem) / len(mem)
            cy = sum(self.Y[i] for i in mem) / len(mem)
            tot += sum(math.hypot(self.X[i] - cx, self.Y[i] - cy) for i in mem)
            m += len(mem)
        return tot / m if m else 0.0

    def assign_decaps(self):
        """(Re)assign each decoupling cap to an IC power pin, balanced, by current distance."""
        try:
            import numpy as np
            from scipy.optimize import linear_sum_assignment
        except Exception:  # pragma: no cover - greedy fallback
            np = None
        X, Y, K, PO = self.X, self.Y, self.K, self.PADOFF
        self.DEPS = [[] for _ in range(self.n)]
        for caps, targets in self.dec_groups:
            rep = int(math.ceil(len(caps) / float(len(targets))))
            slots = targets * rep
            cp = [(X[c] + PO[c][K[c]][q][0], Y[c] + PO[c][K[c]][q][1]) for c, q in caps]
            tp = [(X[t] + PO[t][K[t]][q][0], Y[t] + PO[t][K[t]][q][1]) for t, q in slots]
            if np is not None:
                a = np.array(cp)
                b = np.array(tp)
                cost = np.abs(a[:, None, 0] - b[None, :, 0]) + np.abs(a[:, None, 1] - b[None, :, 1])
                rows, cols = linear_sum_assignment(cost)
                pairs = zip(rows.tolist(), cols.tolist())
            else:
                used, pairs = set(), []
                for r, (x, y) in enumerate(cp):
                    best = min((s for s in range(len(slots)) if s not in used),
                               key=lambda s: abs(x - tp[s][0]) + abs(y - tp[s][1]))
                    used.add(best)
                    pairs.append((r, best))
            for r, s in pairs:
                c, q = caps[r]
                t, tq = slots[s]
                self.CAPT[c] = (q, t, tq)
                self.DEPS[t].append(c)
        for i in range(self.n):
            self.DC[i] = self.capdist(i) if self.CAPT[i] is not None else 0.0

    # ---------------------------------------------------------------- moves
    def step(self, ch, T, rnd, probe=False):
        """Try a move. ch = [(i, x, y, k), ...] with one or two footprints.

        Returns (accepted, delta).
        """
        X, Y, K, CUR, RECT = self.X, self.Y, self.K, self.CUR, self.RECT
        HP, NW, FB, DC = self.HP, self.NW, self.FB, self.DC
        if len(ch) == 1:
            ids = (ch[0][0],)
            nets = self.CN[ids[0]]
        else:
            ids = (ch[0][0], ch[1][0])
            nets = list(set(self.CN[ids[0]]) | set(self.CN[ids[1]]))

        caps = []
        for i in ids:
            if self.CAPT[i] is not None:
                caps.append(i)
            if self.DEPS[i]:
                caps.extend(self.DEPS[i])
        if len(ids) == 2 and caps:
            caps = list(set(caps))
        PPC, PV = self.PPC, self.PV
        if len(ids) == 1:
            pps = PPC[ids[0]]
        else:
            pps = list(set(PPC[ids[0]]) | set(PPC[ids[1]])) if (PPC[ids[0]] or PPC[ids[1]]) else ()
        pp_old = 0.0
        for k in pps:
            pp_old += PV[k]

        old = 0.0
        for k in nets:
            old += HP[k] * NW[k]
        ov_old = 0.0
        fb_old = 0.0
        for i in ids:
            ov_old += self.ov_others(i, ids)
            fb_old += FB[i]
        if len(ids) == 2:
            ov_old += self.pair_ov(ids[0], ids[1])
        dc_old = 0.0
        for c in caps:
            dc_old += DC[c]

        saved = [(i, X[i], Y[i], K[i], CUR[i]) for i in ids]
        sp = 0.0
        for i, nx, ny, nk in ch:
            sp += self.spread_move(i, X[i], Y[i], nx, ny)
            X[i], Y[i], K[i] = nx, ny, nk
            r = RECT[i][nk]
            CUR[i] = (nx + r[0], ny + r[1], nx + r[2], ny + r[3])

        new_hp = [self.hpwl(k) for k in nets]
        new = 0.0
        for k, v in zip(nets, new_hp):
            new += v * NW[k]
        ov_new = 0.0
        fb_new = []
        for i in ids:
            ov_new += self.ov_others(i, ids)
            fb_new.append(self.forb(i))
        if len(ids) == 2:
            ov_new += self.pair_ov(ids[0], ids[1])
        dc_new = [self.capdist(c) for c in caps]
        pp_new = [self.pairpen(k) for k in pps]

        W = self.W
        delta = (W["wl"] * (new - old) + self.w_ov * (ov_new - ov_old)
                 + self.w_fb * (sum(fb_new) - fb_old) + W["dec"] * (sum(dc_new) - dc_old) + sp
                 + W_PP * (sum(pp_new) - pp_old))

        if not probe and (delta <= 0.0 or rnd() < math.exp(-delta / T)):
            for k, v in zip(pps, pp_new):
                PV[k] = v
            for k, v in zip(nets, new_hp):
                HP[k] = v
            for i, v in zip(ids, fb_new):
                FB[i] = v
            for c, v in zip(caps, dc_new):
                DC[c] = v
            for i, _, _, _, cur in saved:
                self._hash_del(i, cur)
            for i in ids:
                self._hash_add(i)
            return True, delta

        for i, ox, oy, ok, cur in saved:
            self.spread_move(i, X[i], Y[i], ox, oy)
            X[i], Y[i], K[i], CUR[i] = ox, oy, ok, cur
        return False, delta

    def net_centroid(self, i):
        X, Y, K, PO = self.X, self.Y, self.K, self.PADOFF
        sx = sy = 0.0
        m = 0
        for k in self.CN[i]:
            for j, q in self.NETP[k]:
                if j != i:
                    o = PO[j][K[j]][q]
                    sx += X[j] + o[0]
                    sy += Y[j] + o[1]
                    m += 1
        if not m:
            return None
        return sx / m, sy / m

    def propose(self, rng, reach):
        mov = self.movable
        i = mov[int(rng.random() * len(mov))]
        u = rng.random()
        X, Y, K = self.X, self.Y, self.K
        if u < 0.50:
            nx = X[i] + rng.gauss(0.0, reach)
            ny = Y[i] + rng.gauss(0.0, reach)
            nk = K[i]
        elif u < 0.64:
            nx, ny = X[i], Y[i]
            nk = (K[i] + 1 + int(rng.random() * 3)) % 4
        elif u < 0.84:
            j = mov[int(rng.random() * len(mov))]
            if j == i:
                return None
            return [(i, X[j], Y[j], K[i]), (j, X[i], Y[i], K[j])]
        else:
            c = self.net_centroid(i)
            if c is None:
                return None
            nx = c[0] + rng.gauss(0.0, reach * 0.3)
            ny = c[1] + rng.gauss(0.0, reach * 0.3)
            nk = K[i] if rng.random() < 0.7 else int(rng.random() * 4)
        nx = self.bx0 if nx < self.bx0 else (self.bx1 if nx > self.bx1 else nx)
        ny = self.by0 if ny < self.by0 else (self.by1 if ny > self.by1 else ny)
        return [(i, nx, ny, nk)]

    # ---------------------------------------------------------------- drivers
    def randomize(self, rng):
        for i in self.movable:
            free = self.FREE[self.SI[i]]
            ix, iy = free[int(rng.random() * len(free))]
            self.X[i] = self.bx0 + (ix + 0.5) * RES
            self.Y[i] = self.by0 + (iy + 0.5) * RES
            self.K[i] = int(rng.random() * 4)
        self.refresh()

    def anneal(self, rng, moves, refine=False, stages=250, log=None):
        size = max(self.bx1 - self.bx0, self.by1 - self.by0)
        r_hi = size * (0.04 if refine else 0.30)
        r_lo = 0.15
        ov_lo = 0.3 if refine else 0.02
        self.w_ov = W_OV * ov_lo
        self.assign_decaps()

        # temperature from the typical uphill move at the starting conditions
        ups = []
        for _ in range(600):
            ch = self.propose(rng, r_hi)
            if ch:
                d = self.step(ch, 1.0, rng.random, probe=True)[1]
                if d > 0:
                    ups.append(d)
        ups.sort()
        t_hi = (ups[len(ups) // 2] if ups else 1.0) * (0.03 if refine else 0.6)
        t_lo = t_hi * (5e-3 if refine else 2e-4)

        per = max(1, moves // stages)
        rnd = rng.random
        for st in range(stages):
            f = st / float(stages - 1)
            T = t_hi * (t_lo / t_hi) ** f
            reach = r_hi * (r_lo / r_hi) ** f
            self.w_ov = W_OV * ov_lo ** (1.0 - min(1.0, f / 0.8))
            if st % 10 == 0 and st:
                self.assign_decaps()
            acc = 0
            for _ in range(per):
                ch = self.propose(rng, reach)
                if ch and self.step(ch, T, rnd)[0]:
                    acc += 1
            if log and st % 25 == 0:
                log("stage %3d T %.4f reach %.2f acc %.2f  %s" % (
                    st, T, reach, acc / float(per), self.summary()))
        self.w_ov = W_OV

    def place(self, i, x, y, k):
        old = self.CUR[i]
        self.spread_move(i, self.X[i], self.Y[i], x, y)
        self.X[i], self.Y[i], self.K[i] = x, y, k
        r = self.RECT[i][k]
        self.CUR[i] = (x + r[0], y + r[1], x + r[2], y + r[3])
        self._hash_del(i, old)
        self._hash_add(i)

    def snap(self, grid=0.05):
        for i in self.movable:
            self.X[i] = round(self.X[i] / grid) * grid
            self.Y[i] = round(self.Y[i] / grid) * grid
        self.refresh()

    def legalize(self, step=0.25, rmax=45.0, passes=4, grid=0.05):
        """Move every footprint that still overlaps or leaves the board to the nearest
        legal spot, cheapest in wirelength among the nearest ring. Returns how many are
        still illegal."""
        eps = 1e-9
        empty = ()
        bad = []
        for _ in range(passes):
            bad = [i for i in self.movable if self.ov_others(i, empty) > eps or self.forb(i) > eps]
            if not bad:
                break
            bad.sort(key=lambda i: self.AREA[i])
            for i in bad:
                if not (self.ov_others(i, empty) > eps or self.forb(i) > eps):
                    continue
                ox, oy, ok = self.X[i], self.Y[i], self.K[i]
                rect = self.RECT[i][ok]
                best = None
                r = step
                while r <= rmax and best is None:
                    m = max(8, int(2.0 * math.pi * r / step))
                    for a in range(m):
                        th = 2.0 * math.pi * a / m
                        x = round((ox + r * math.cos(th)) / grid) * grid
                        y = round((oy + r * math.sin(th)) / grid) * grid
                        self.CUR[i] = (x + rect[0], y + rect[1], x + rect[2], y + rect[3])
                        if self.forb(i) > eps or self.ov_others(i, empty) > eps:
                            continue
                        self.X[i], self.Y[i] = x, y
                        wl = sum(self.hpwl(k) * self.NW[k] for k in self.CN[i])
                        if best is None or wl < best[0]:
                            best = (wl, x, y)
                    r += step
                self.X[i], self.Y[i] = ox, oy
                self.CUR[i] = (ox + rect[0], oy + rect[1], ox + rect[2], oy + rect[3])
                if best is not None:
                    self.place(i, best[1], best[2], ok)
        self.refresh()
        return len([i for i in self.movable
                    if self.ov_others(i, empty) > eps or self.forb(i) > eps])

    def _legal(self, i, skip=()):
        return self.forb(i) <= 1e-9 and self.ov_others(i, skip) <= 1e-9

    def _pen(self, i):
        return sum(self.pairpen(k) for k in self.PPC[i])

    def _try_at(self, i, x, y, k):
        """Put footprint i at (x, y, rotation k) without touching the caches."""
        r = self.RECT[i][k]
        self.X[i], self.Y[i], self.K[i] = x, y, k
        self.CUR[i] = (x + r[0], y + r[1], x + r[2], y + r[3])

    def fix_pairs(self, passes=3, step=0.25, grid=0.05):
        """Greedy repair of the pin pairs still beyond their limit after legalisation.
        For each one, the smaller movable part is moved to the legal spot nearest the
        other pin, or swapped with an unconstrained neighbour of similar size. A move is
        kept only when it is legal and lowers that part's own pair penalty."""
        fixed_n = 0
        for _ in range(passes):
            bad = sorted((k for k in range(len(self.PP)) if self.pairpen(k) > 0.01),
                         key=lambda k: -self.pairpen(k))
            if not bad:
                break
            for k in bad:
                if self.pairpen(k) <= 0.01:
                    continue
                i, qi, j, qj, lim = self.PP[k]
                movers = [m for m in (j, i) if not self.fixed[m]]
                movers.sort(key=lambda m: self.AREA[m])
                done = False
                for m in movers:
                    o, qo, qm = (i, qi, qj) if m == j else (j, qj, qi)
                    po = self.PADOFF[o][self.K[o]][qo]
                    tx, ty = self.X[o] + po[0], self.Y[o] + po[1]
                    ox, oy, ok, ocur = self.X[m], self.Y[m], self.K[m], self.CUR[m]
                    before = self._pen(m)
                    best = None
                    r = 0.0
                    while r <= lim - 0.05:
                        cnt = 1 if r == 0.0 else max(8, int(2.0 * math.pi * r / step))
                        for a in range(cnt):
                            th = 2.0 * math.pi * a / cnt
                            for kk in range(len(self.rots[m])):
                                pm = self.PADOFF[m][kk][qm]
                                x = round((tx + r * math.cos(th) - pm[0]) / grid) * grid
                                y = round((ty + r * math.sin(th) - pm[1]) / grid) * grid
                                self._try_at(m, x, y, kk)
                                if not self._legal(m):
                                    continue
                                pen = self._pen(m)
                                if pen < before - 0.01:
                                    wl = sum(self.hpwl(n) * self.NW[n] for n in self.CN[m])
                                    if best is None or (pen, wl) < best[0]:
                                        best = ((pen, wl), x, y, kk)
                        if best is not None and best[0][0] <= 0.01:
                            break
                        r += step
                    self.X[m], self.Y[m], self.K[m], self.CUR[m] = ox, oy, ok, ocur
                    if best is not None:
                        self.place(m, best[1], best[2], best[3])
                        fixed_n += 1
                        done = True
                        break
                    # swap with an unconstrained neighbour of similar size near the pin
                    cands = [s for s in self.movable if s != m and s != o
                             and self.side[s] == self.side[m]
                             and 0.4 * self.AREA[m] <= self.AREA[s] <= 2.5 * self.AREA[m]
                             and math.hypot(self.X[s] - tx, self.Y[s] - ty) <= lim + 2.5]
                    cands.sort(key=lambda s: math.hypot(self.X[s] - tx, self.Y[s] - ty))
                    for s in cands:
                        sx, sy, sk, scur = self.X[s], self.Y[s], self.K[s], self.CUR[s]
                        both = before + self._pen(s)
                        ok_swap = None
                        for kk in range(len(self.rots[m])):
                            self._try_at(m, sx, sy, kk)
                            for ks in range(len(self.rots[s])):
                                self._try_at(s, ox, oy, ks)
                                if (self._legal(m, (s,)) and self._legal(s, (m,))
                                        and self.pair_ov(m, s) <= 1e-9
                                        and self._pen(m) + self._pen(s) < both - 0.01):
                                    ok_swap = (kk, ks)
                                    break
                            if ok_swap:
                                break
                        self.X[m], self.Y[m], self.K[m], self.CUR[m] = ox, oy, ok, ocur
                        self.X[s], self.Y[s], self.K[s], self.CUR[s] = sx, sy, sk, scur
                        if ok_swap:
                            self.place(m, sx, sy, ok_swap[0])
                            self.place(s, ox, oy, ok_swap[1])
                            fixed_n += 1
                            done = True
                            break
                    if done:
                        break
        self.refresh()
        return fixed_n

    def terms(self):
        empty = ()
        wl = sum(self.HP[k] * self.NW[k] for k in range(len(self.HP)))
        ov = sum(self.ov_others(i, empty) for i in range(self.n)) / 2.0
        fb = sum(self.FB)
        dec = sum(self.DC)
        return {"wl": wl, "ov": ov, "fb": fb, "dec": dec, "pp": sum(self.PV)}

    def summary(self):
        t = self.terms()
        return "wl %.0f dec %.0f ov %.1f fb %.1f pp %.1f" % (t["wl"], t["dec"], t["ov"], t["fb"], t["pp"])

    def placement(self):
        return {self.refs[i]: [round(self.X[i], 4), round(self.Y[i], 4), self.rots[i][self.K[i]]]
                for i in range(self.n_real)}

    def load_placement(self, pl):
        for i, ref in enumerate(self.refs):
            if ref in pl and not self.fixed[i]:
                x, y, rot = pl[ref]
                self.X[i], self.Y[i] = x, y
                self.K[i] = int(round(rot / 90.0)) % 4
        self.refresh()


def run(model_path, out_path, seed, profile, moves, init, margin, verbose, cluster=1.0, init_file=None):
    with open(model_path, encoding="utf-8") as fh:
        model = json.load(fh)
    t0 = time.time()
    P = Problem(model, margin=margin)
    P.set_profile(profile, cluster)
    rng = random.Random(seed)
    if init == "random":
        P.randomize(rng)
    elif init == "file":
        with open(init_file, encoding="utf-8") as fh:
            P.load_placement(json.load(fh)["placement"])
    log = (lambda s: print(s, flush=True)) if verbose else None
    P.anneal(rng, moves, refine=(init != "random"), log=log)
    P.snap()
    left = P.legalize()
    for _ in range(3):
        if not P.fix_pairs():
            break
    left = len([i for i in P.movable if not P._legal(i)])
    P.assign_decaps()
    result = {
        "seed": seed, "profile": profile, "init": init, "moves": moves, "margin": margin,
        "cluster": cluster, "init_file": init_file, "pin_pairs_bad": P.pair_viol(),
        "seconds": round(time.time() - t0, 1), "illegal_left": left,
        "terms": P.terms(), "placement": P.placement(),
    }
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh)
    print("seed %d %-10s %s  illegal %d  %.0fs" % (seed, profile, P.summary(), left, result["seconds"]),
          flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("out")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--profile", default="balanced", choices=sorted(PROFILES))
    ap.add_argument("--moves", type=int, default=1500000)
    ap.add_argument("--init", default="random", choices=("random", "current", "file"))
    ap.add_argument("--init-file", default=None, help="candidate JSON to start from (--init file)")
    ap.add_argument("--margin", type=float, default=0.15)
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--cluster", type=float, default=1.0)
    a = ap.parse_args()
    run(a.model, a.out, a.seed, a.profile, a.moves, a.init, a.margin, a.verbose, a.cluster, a.init_file)
