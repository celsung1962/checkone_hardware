#!/usr/bin/env python3
"""
Local reachability of a placement, IC by IC (run with KiCad's Python: pcbnew, shapely, numpy). 1.5.0.

Distances (verify_placement.py, signal_near.py) say how far a part is from its pin; they do not say whether the
tracks can still get there. This check answers that, around each IC, before the board goes to the router:

  links    every connection among the IC and its local small parts (2-4 pads, not test points: a pad on an IC net
           within --local mm of that pin, plus parts on a non-rail net with those, an RC or a divider), as a
           minimum spanning tree per signal net; on a supply rail (POWER class, a name starting with + or -, or a
           net with a zone) only each part's link to the IC pin, since part-to-part rail links go through the plane
           or the supply tree. Ground excluded, routed on the IC's side only, no vias, with each net's own
           clearance (wider nets neck down to the Default width). Two start
           orders (shortest first, longest first), then up to --passes re-orderings with the failed links first.
           A link that does not route even ALONE on an empty grid has no corridor on its layer: BLOCKED, HARD
           (exit 1). One that routes alone but never with the others is a WARN: a greedy grid router lays each
           route on its shortest path, so this is often the router's limit; look at the corridor.
  escapes  every other IC signal pin (not ground, no local part on its net) routed out of the IC's
           neighbourhood (a ring --ring mm outside its courtyard; --escape-to edge for the board edge), vias
           allowed, in the same passes. An escape that fails even alone is UNRESOLVED (try another side, an earlier
           via, a rotation, moving the part in the way), not proof that the board cannot route.
  fronts   IC signal pins without a free fan-out channel (track + 2 clearances wide, straight out or at 45
           degrees, --front mm long) clear of other nets' pads.
  held     IC pins whose nearest local part is farther than --far mm: which parts' courtyards hold the strip in
           front of the pin. Move the part that tolerates distance (bulk cap, series resistor, crystal), not the
           decoupler or filter capacitor.
  crowded  neighbouring IC pins served by two different parts whose widths along the pin row add up to more than
           twice the pin pitch: both cannot sit radially in line with their pins; offset one, push one out by its
           length, or swap which pin gets the nearer spot.
  rotation the four rotations of each IC scored by the distance from each signal pin to the rest of its net (local
           nets weighted x3); reported when another rotation is at least 10 % shorter. Advisory: it does not move
           the passives with the IC.
  pads     a local two-pad part whose ground pad is nearer the IC pin than its signal pad (GROUND PAD FACES PIN);
           ground pads of local parts without a via site within 1.2 mm (boards with more than two copper layers,
           where ground returns through a via); two-pad parts across two IC pins (crystals, flying capacitors) with
           the two gaps and their difference.

Rules: per net, from the project file (.kicad_pro net classes; a composite class takes the largest values of its
constituents) and the pads' own clearance (KiCad's resolved value, overrides included); copper to edge from the
board's design settings. Custom rules in the .kicad_dru are not evaluated: the script lists the ones with a
clearance-type constraint so you can judge whether they matter here. --track / --clear / --via / --edge raise a
value for every net (never lower it unless --rules-override, and then the output says so).

Scope and honesty: a grid router (--grid, default 0.05 mm) on the outer layer of the IC's side, inner layers taken
as planes, zones ignored, existing tracks ignored unless --with-tracks. A pass is feasibility under simple rules,
not a finished route; a failure is a heuristic's failure, not proof the board cannot be routed.

Usage:
    <kicad-python> local_reach.py board.kicad_pcb [--ic U1 U2 ...] [--ground GND AGND ...] [--json out.json]
        [--local 6] [--ring 5] [--escape-to ring|edge] [--front 2.0] [--far 2.6] [--grid 0.05] [--with-tracks]
        [--track MM --clear MM --via MM --edge MM [--rules-override]] [--no-route]

Adapted from KiStack's layout-placement scripts (route_check.py, grid_router.py, placement_audit.py,
local_search.py, rules.py; https://github.com/BackplaneWorks/kistack), MIT licence, Copyright 2026 American
Embedded, LLC; see references/third_party_kistack.md. Rewritten for pcbnew (no IPC server), per-net rules,
a window around each IC, an escape ring instead of the board edge, and the held / crowded / rotation reports.
"""
import argparse, heapq, json, math, os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import pcbnew  # noqa: E402
import shapely  # noqa: E402
from shapely.geometry import LineString, Point, Polygon, box  # noqa: E402
from shapely.ops import unary_union  # noqa: E402

mm = pcbnew.ToMM
VIA_COST = 12.0          # grid cells; a via costs about 0.6 mm of track at 0.05 mm
MARGIN = 0.01            # keeps grid paths off the exact clearance on diagonals; commits are checked exactly


# ----------------------------------------------------------------------------- geometry from pcbnew
def sps_to_shapely(sps):
    polys = []
    for i in range(sps.OutlineCount()):
        o = sps.Outline(i)
        pts = [(mm(o.CPoint(k).x), mm(o.CPoint(k).y)) for k in range(o.PointCount())]
        holes = []
        for h in range(sps.HoleCount(i)):
            hl = sps.Hole(i, h)
            holes.append([(mm(hl.CPoint(k).x), mm(hl.CPoint(k).y)) for k in range(hl.PointCount())])
        if len(pts) >= 3:
            polys.append(Polygon(pts, holes))
    if not polys:
        return None
    return unary_union([p.buffer(0) for p in polys])


def board_outline(b):
    poly = pcbnew.SHAPE_POLY_SET()
    try:
        b.GetBoardPolygonOutlines(poly, False)
    except TypeError:
        b.GetBoardPolygonOutlines(poly)
    return sps_to_shapely(poly)


class Pad:
    __slots__ = ("ref", "num", "name", "net", "kind", "on", "poly", "center", "clear")


class Fp:
    __slots__ = ("ref", "x", "y", "rot", "back", "pads", "courtyard", "value", "fpid")


def load(path, with_tracks):
    b = pcbnew.LoadBoard(path)
    ncop = b.GetCopperLayerCount()
    fps = []
    for f in b.GetFootprints():
        o = Fp()
        o.ref, o.value, o.fpid = f.GetReference(), f.GetValue(), f.GetFPIDAsString()
        pos = f.GetPosition()
        o.x, o.y, o.rot, o.back = mm(pos.x), mm(pos.y), f.GetOrientationDegrees(), f.IsFlipped()
        cy = f.GetCourtyard(pcbnew.B_CrtYd if o.back else pcbnew.F_CrtYd)
        o.courtyard = sps_to_shapely(cy) if cy.OutlineCount() else None
        if o.courtyard is None:
            r = f.GetBoundingBox(False)
            o.courtyard = box(mm(r.GetLeft()), mm(r.GetTop()), mm(r.GetRight()), mm(r.GetBottom()))
        o.pads = []
        for p in f.Pads():
            q = Pad()
            q.ref, q.num, q.net = o.ref, p.GetNumber(), p.GetNetname()
            q.name = f"{o.ref}.{q.num}"
            att = p.GetAttribute()
            q.kind = {pcbnew.PAD_ATTRIB_SMD: "smd", pcbnew.PAD_ATTRIB_PTH: "tht"}.get(att, "other")
            ls = p.GetLayerSet()
            q.on = set()
            if ls.Contains(pcbnew.F_Cu):
                q.on.add(0)
            if ls.Contains(pcbnew.B_Cu):
                q.on.add(1)
            if not q.on:
                continue                       # paste-only apertures, mechanical-only pads
            lay = pcbnew.F_Cu if 0 in q.on else pcbnew.B_Cu
            q.poly = sps_to_shapely(p.GetEffectivePolygon(lay, pcbnew.ERROR_INSIDE))
            if q.poly is None:
                continue
            c = p.GetPosition()
            q.center = (mm(c.x), mm(c.y))
            q.clear = mm(p.GetOwnClearance(lay))
            o.pads.append(q)
            NETCLASS_OF.setdefault(q.net, p.GetNetClassName())
            PAD_CLEAR.setdefault(q.net, 0.0)
            PAD_CLEAR[q.net] = max(PAD_CLEAR[q.net], q.clear)
        fps.append(o)
    fixed = []
    if with_tracks:
        for t in b.GetTracks():
            net = t.GetNetname()
            if t.GetClass() == "PCB_VIA":
                c = t.GetPosition()
                g = Point(mm(c.x), mm(c.y)).buffer(mm(t.GetWidth(pcbnew.F_Cu)) / 2, 12)
                fixed += [(0, net, g), (1, net, g)]
                continue
            lay = t.GetLayer()
            if lay not in (pcbnew.F_Cu, pcbnew.B_Cu):
                continue
            pts = [t.GetStart(), t.GetEnd()]
            if t.GetClass() == "PCB_ARC":
                pts = [t.GetStart(), t.GetMid(), t.GetEnd()]
            g = LineString([(mm(p.x), mm(p.y)) for p in pts]).buffer(mm(t.GetWidth()) / 2, 4)
            fixed.append((0 if lay == pcbnew.F_Cu else 1, net, g))
    ds = b.GetDesignSettings()
    return dict(board=b, footprints=fps, outline=board_outline(b), fixed=fixed, layers=ncop,
                edge=mm(ds.m_CopperEdgeClearance),
                zone_nets={z.GetNetname() for z in b.Zones() if z.GetNetname() and z.IsOnCopperLayer()})


NETCLASS_OF, PAD_CLEAR = {}, {}
_MASKS = {}


# ----------------------------------------------------------------------------- rules
class Rules:
    def __init__(self, path, loaded, a):
        pro = os.path.splitext(path)[0] + ".kicad_pro"
        self.notes = []
        self.classes = {}
        if os.path.isfile(pro):
            j = json.load(open(pro, encoding="utf-8"))
            for c in (j.get("net_settings") or {}).get("classes", []):
                self.classes[c["name"]] = c
        else:
            self.notes.append(f"no {os.path.basename(pro)}: net class values unknown, using the flags or the "
                              "board minimums")
        d = self.classes.get("Default", {})
        self.default = dict(track=d.get("track_width") or 0.2, clear=d.get("clearance") or 0.1,
                            via=d.get("via_diameter") or 0.6)
        self.edge = loaded["edge"]
        # neck-down: near an IC every net may narrow to the Default class width to enter a pad (the AQTech rule
        # files allow it inside small R/C and fine-pitch courtyards); --no-neck routes at the class widths
        self.neck = None if a.no_neck else (a.neck if a.neck is not None else self.default["track"])
        self.flags = {k: getattr(a, k) for k in ("track", "clear", "via", "edge")}
        self.override = a.rules_override
        if self.flags["edge"] is not None:
            if self.flags["edge"] < self.edge and not self.override:
                sys.exit(f"--edge {self.flags['edge']} is looser than the board's {self.edge:.3f} mm; "
                         "pass --rules-override only when the user asks for a looser check")
            if self.flags["edge"] < self.edge:
                self.notes.append(f"copper to edge {self.flags['edge']} mm is LOOSER THAN THE BOARD ({self.edge})")
            self.edge = self.flags["edge"]
        self._cache = {}
        dru = os.path.splitext(path)[0] + ".kicad_dru"
        if os.path.isfile(dru):
            text = "\n".join(l.split("#", 1)[0] for l in open(dru, encoding="utf-8").read().splitlines())
            names = []
            for m in re.finditer(r'\(rule\s+"?([^"\s)]+)"?(.*?)(?=\(rule\b|\Z)', text, re.S):
                if re.search(r"\(constraint\s+(clearance|edge_clearance|hole_clearance|physical_clearance)", m.group(2)):
                    names.append(m.group(1))
            if names:
                self.notes.append(f"{os.path.basename(dru)} has clearance rules this check does not evaluate: "
                                  + ", ".join(names) + "; judge whether they apply near these ICs, or pass --clear")
            else:
                self.notes.append(f"{os.path.basename(dru)}: no clearance-type rules (track-width rules only "
                                  "narrow or widen tracks; the check routes at the net class width)")

    def of(self, net):
        if net in self._cache:
            return self._cache[net]
        cls = NETCLASS_OF.get(net) or "Default"
        parts = [c for c in cls.split(",") if c in self.classes] or ["Default"]
        val = {}
        for k, key in (("track", "track_width"), ("clear", "clearance"), ("via", "via_diameter")):
            vs = [self.classes.get(c, {}).get(key) for c in parts]
            vs = [v for v in vs if isinstance(v, (int, float)) and v > 0]
            val[k] = max(vs) if vs else self.default[k]
        val["clear"] = max(val["clear"], PAD_CLEAR.get(net, 0.0))
        if self.neck is not None and val["track"] > self.neck:
            val["track"] = self.neck           # a wide net necks down to reach a small pad
        for k in ("track", "clear", "via"):
            f = self.flags[k]
            if f is None:
                continue
            if f < val[k] and not self.override:
                continue                       # a flag only raises a rule
            val[k] = f
        self._cache[net] = val
        return val

    def lines(self):
        out = [f"rules: per net from {'the net classes' if self.classes else 'the defaults'}; copper to edge "
               f"{self.edge:.3f} mm; "
               + (f"wider nets neck down to {self.neck} mm near the IC" if self.neck is not None
                  else "tracks at the full class width (--no-neck)")]
        if self.classes:
            out.append("  classes: " + "; ".join(
                f"{n} track {c.get('track_width')} clear {c.get('clearance')} via {c.get('via_diameter')}"
                for n, c in self.classes.items()))
        flags = {k: v for k, v in self.flags.items() if v is not None}
        if flags:
            out.append("  flags: " + ", ".join(f"--{k} {v}" for k, v in flags.items())
                       + (" (rules override: may be LOOSER THAN THE BOARD)" if self.override else " (raise only)"))
        out += ["  " + n for n in self.notes]
        return out


# ----------------------------------------------------------------------------- grid router (routability witness)
class Grid:
    """Two outer layers (0 = F.Cu, 1 = B.Cu) over a window; inner layers taken as planes. Routed copper becomes an
    obstacle for later routes."""

    def __init__(self, L, rules, window, step):
        self.rules, self.step = rules, step
        x0, y0, x1, y1 = window.bounds
        self.x0, self.y0 = x0, y0
        self.nx = int(math.ceil((x1 - x0) / step)) + 1
        self.ny = int(math.ceil((y1 - y0) / step)) + 1
        xs, ys = x0 + np.arange(self.nx) * step, y0 + np.arange(self.ny) * step
        self.X, self.Y = np.meshgrid(xs, ys)
        self.outline = L["outline"]
        self.copper = {0: [], 1: []}
        # obstacle masks of the board's own copper are cached across Grid instances of one window (one IC, several
        # passes): key = (window, step, id of the geometry, buffer distance)
        wkey = (round(x0, 4), round(y0, 4), self.nx, self.ny, step)
        self.items = {0: [], 1: []}
        for fp in L["footprints"]:
            for p in fp.pads:
                if p.poly.intersects(window):
                    for l in p.on:
                        self.copper[l].append((p.net, p.poly))
                        self.items[l].append((p.net, p.poly, _MASKS.setdefault((wkey, id(p.poly)), {})))
        for l, n, g in L["fixed"]:
            if g.intersects(window):
                self.copper[l].append((n, g))
                self.items[l].append((n, g, _MASKS.setdefault((wkey, id(g)), {})))
        self.window = window
        self._inside = _MASKS.setdefault((wkey, "inside"), {})

    def _sub(self, g, r, cache):
        """(i0, i1, j0, j1, submask) of g buffered by r, cached."""
        k = round(r, 4)
        if k not in cache:
            gb = g.buffer(r, 8)
            minx, miny, maxx, maxy = gb.bounds
            i0 = max(0, int((miny - self.y0) / self.step) - 1)
            i1 = min(self.ny, int((maxy - self.y0) / self.step) + 2)
            j0 = max(0, int((minx - self.x0) / self.step) - 1)
            j1 = min(self.nx, int((maxx - self.x0) / self.step) + 2)
            if i0 < i1 and j0 < j1:
                cache[k] = (i0, i1, j0, j1, shapely.contains_xy(gb, self.X[i0:i1, j0:j1], self.Y[i0:i1, j0:j1]))
            else:
                cache[k] = None
        return cache[k]

    def mask(self, g):
        m = np.zeros(self.X.shape, bool)
        if g is None or g.is_empty:
            return m
        minx, miny, maxx, maxy = g.bounds
        i0 = max(0, int((miny - self.y0) / self.step) - 1)
        i1 = min(self.ny, int((maxy - self.y0) / self.step) + 2)
        j0 = max(0, int((minx - self.x0) / self.step) - 1)
        j1 = min(self.nx, int((maxx - self.x0) / self.step) + 2)
        if i0 < i1 and j0 < j1:
            m[i0:i1, j0:j1] = shapely.contains_xy(g, self.X[i0:i1, j0:j1], self.Y[i0:i1, j0:j1])
        return m

    def inside(self, half):
        k = round(half, 4)
        if k not in self._inside:
            self._inside[k] = self.mask(self.outline.buffer(-(self.rules.edge + half)).intersection(self.window))
        return self._inside[k]

    def blocked(self, net, layer, half):
        """Cells where a centre line of half-width `half` on `net` would break the clearance to other copper; the
        clearance between two nets is the larger of their two."""
        c_own = self.rules.of(net)["clear"]
        m = np.zeros(self.X.shape, bool)
        for n, g, cache in self.items[layer]:
            if n == net and n:
                continue
            c = max(c_own, self.rules.of(n)["clear"]) if n else c_own
            s = self._sub(g, c + half + MARGIN, cache)
            if s is not None:
                i0, i1, j0, j1, sub = s
                m[i0:i1, j0:j1] |= sub
        return m

    def route(self, net, start_polys, goal, layers=(0,), allow_via=False, max_len=None):
        """goal: list of (layer, polygon), or a list of two masks. Returns the length in mm, or None."""
        r = self.rules.of(net)
        ht, hv = r["track"] / 2, r["via"] / 2
        free = [self.inside(ht) & ~self.blocked(net, l, ht) for l in (0, 1)]
        vfree = (self.inside(hv) & ~self.blocked(net, 0, hv) & ~self.blocked(net, 1, hv)) if allow_via else None
        sm = np.zeros(self.X.shape, bool)
        for sp in start_polys:
            sm |= self.mask(sp)
        start = [(l, i, j) for l in layers for i, j in zip(*np.nonzero(sm))]
        if isinstance(goal, list) and goal and isinstance(goal[0], np.ndarray):
            gmask = [goal[0] & free[0], goal[1] & free[1]]
        else:
            gmask = [np.zeros(self.X.shape, bool), np.zeros(self.X.shape, bool)]
            for l, gp in goal:
                gmask[l] |= self.mask(gp)
        if not allow_via:
            for l in (0, 1):
                if l not in layers:
                    gmask[l][:] = False
        if not start or not (gmask[0].any() or gmask[1].any()):
            return None
        g_all = np.vstack([np.argwhere(gmask[l]) for l in (0, 1) if gmask[l].any()])
        gi0, gj0 = g_all.min(0)
        gi1, gj1 = g_all.max(0)

        def hb(i, j):
            di = max(gi0 - i, 0, i - gi1)
            dj = max(gj0 - j, 0, j - gj1)
            return max(di, dj) + 0.414 * min(di, dj)
        dist, prev, pq = {}, {}, []
        for s in start:
            dist[s] = 0.0
            heapq.heappush(pq, (hb(s[1], s[2]), 0.0, s))
        steps = [(-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
                 (-1, -1, 1.4142), (-1, 1, 1.4142), (1, -1, 1.4142), (1, 1, 1.4142)]
        limit = None if max_len is None else max_len / self.step
        found = None
        while pq:
            _, g, node = heapq.heappop(pq)
            if g > dist.get(node, 1e18):
                continue
            l, i, j = node
            if gmask[l][i, j]:
                found = node
                break
            if limit is not None and g > limit:
                continue
            fl = free[l]
            for di, dj, c in steps:
                ii, jj = i + di, j + dj
                if not (0 <= ii < self.ny and 0 <= jj < self.nx):
                    continue
                if not (fl[ii, jj] or gmask[l][ii, jj] or sm[ii, jj]):
                    continue
                if di and dj and not (fl[i + di, j] or fl[i, j + dj]):
                    continue
                nn, ng = (l, ii, jj), g + c
                if ng < dist.get(nn, 1e18):
                    dist[nn], prev[nn] = ng, node
                    heapq.heappush(pq, (ng + hb(ii, jj), ng, nn))
            if allow_via and vfree[i, j] and free[1 - l][i, j]:
                nn, ng = (1 - l, i, j), g + VIA_COST
                if ng < dist.get(nn, 1e18):
                    dist[nn], prev[nn] = ng, node
                    heapq.heappush(pq, (ng + hb(i, j), ng, nn))
        if found is None:
            return None
        path = [found]
        while path[-1] in prev:
            path.append(prev[path[-1]])
        path.reverse()
        if not self._commit(net, path, ht, hv):
            return None
        return dist[found] * self.step

    def _commit(self, net, path, ht, hv):
        def xy(n):
            return (self.x0 + n[2] * self.step, self.y0 + n[1] * self.step)

        def seg(pts):
            return LineString(pts).buffer(ht, 4) if len(pts) > 1 else Point(pts[0]).buffer(ht, 4)
        pieces, cur, pts = [], path[0][0], []
        for n in path:
            if n[0] != cur:
                if pts:
                    pieces.append((cur, seg(pts)))
                v = Point(xy(n)).buffer(hv, 12)
                pieces += [(0, v), (1, v)]
                cur, pts = n[0], [xy(n)]
            else:
                pts.append(xy(n))
        if pts:
            pieces.append((cur, seg(pts)))
        edge = self.outline.buffer(-self.rules.edge + 0.0005)
        c_own = self.rules.of(net)["clear"]
        for layer, g in pieces:
            gx0, gy0, gx1, gy1 = g.bounds
            for n2, p in self.copper[layer]:
                if n2 == net and n2:
                    continue
                need = max(c_own, self.rules.of(n2)["clear"]) if n2 else c_own
                px0, py0, px1, py1 = p.bounds
                if px0 > gx1 + need or px1 < gx0 - need or py0 > gy1 + need or py1 < gy0 - need:
                    continue
                if p.distance(g) < need - 0.0005:
                    return False
            if not edge.contains(g):
                return False
        for layer, g in pieces:
            self.copper[layer].append((net, g))
            self.items[layer].append((net, g, {}))
        return True


# ----------------------------------------------------------------------------- the checks around one IC
def is_ground(net, pats):
    return bool(net) and any(re.fullmatch(p, net) for p in pats)


def is_rail(net, L):
    """A supply rail: a POWER net class, a name starting with + or -, or a net with a copper zone. Its parts are
    joined through planes or a supply tree, so only each local part's link to the IC pin is checked."""
    return bool(net) and (net[0] in "+-" or "POWER" in (NETCLASS_OF.get(net) or "") or net in L["zone_nets"])


def local_set(L, ic, radius, gnd):
    """The IC's local parts (2-4 pads, not test points, same side): a pad on an IC net within `radius` of that IC
    pin (first ring), and parts sharing a non-rail net with a first-ring part within `radius` of it (an RC filter,
    a divider). Ground does not make a part local."""
    cand = [fp for fp in L["footprints"] if fp.ref != ic.ref and 2 <= len(fp.pads) <= 4 and fp.back == ic.back
            and not re.match(r"(TP|FID|H|MH)\d", fp.ref)]
    pins = {}
    for p in ic.pads:
        if p.net and not is_ground(p.net, gnd):
            pins.setdefault(p.net, []).append(p)
    first = [fp for fp in cand if any(q.net in pins and min(q.poly.distance(p.poly) for p in pins[q.net]) <= radius
                                      for q in fp.pads)]
    names = {fp.ref for fp in first}
    second = []
    for fp in cand:
        if fp.ref in names:
            continue
        for q in fp.pads:
            if not q.net or is_ground(q.net, gnd) or is_rail(q.net, L) or q.net in pins:
                continue
            if any(x.net == q.net and x.poly.distance(q.poly) <= radius for f in first for x in f.pads):
                second.append(fp)
                break
    return first + second


def plan_links(ic, small, gnd, L):
    """Signal nets: minimum spanning tree over the pads of the IC and its local parts (two or more footprints on
    the net). Rails: each local part's pad to the nearest IC pin on that rail (no part-to-part links; those go
    through the plane or the supply tree). Ground excluded; links inside one footprint skipped."""
    pads = [p for p in ic.pads if p.kind == "smd"] + [p for fp in small for p in fp.pads]
    bynet = {}
    for p in pads:
        if p.net and not is_ground(p.net, gnd):
            bynet.setdefault(p.net, []).append(p)
    links = []
    for net, ps in bynet.items():
        if len({p.ref for p in ps}) < 2:
            continue
        if is_rail(net, L):
            icp = [p for p in ps if p.ref == ic.ref]
            if not icp:
                continue
            for q in ps:
                if q.ref == ic.ref:
                    continue
                d, p = min(((q.poly.distance(x.poly), x) for x in icp), key=lambda t: t[0])
                links.append(dict(d=d, name=f"{p.name} -> {q.name} ({net})", net=net, a=p, b=q))
            continue
        used, rest = [ps[0]], ps[1:]
        while rest:
            d, a, c = min(((x.poly.distance(y.poly), x, y) for x in used for y in rest), key=lambda t: t[0])
            if a.ref != c.ref:
                links.append(dict(d=d, name=f"{a.name} -> {c.name} ({net})", net=net, a=a, b=c))
            used.append(c)
            rest.remove(c)
    links.sort(key=lambda t: t["d"])
    return links


def check_ic(L, rules, ic, a, gnd):
    small = local_set(L, ic, a.local, gnd)
    side = 1 if ic.back else 0
    links = plan_links(ic, small, gnd, L)
    local_nets = {p.net for fp in small for p in fp.pads if p.net}
    sig = [p for p in ic.pads if p.net and not is_ground(p.net, gnd) and p.kind == "smd"
           and not p.net.startswith("unconnected-")]
    esc = []
    for p in sorted(sig, key=lambda p: (int(p.num) if p.num.isdigit() else 999, p.num)):
        if p.net not in local_nets and p.net not in esc:
            esc.append(p.net)
    out = dict(ic=ic.ref, value=ic.value, local_parts=sorted(fp.ref for fp in small), links=len(links),
               escapes=len(esc))
    reach = max(a.local, a.ring) + 3.0
    window = ic.courtyard.buffer(reach).envelope.intersection(L["outline"].envelope)

    # --- links and escapes
    # A greedy grid router lays each route on its shortest path, so an early route can take the corridor a later
    # one needs although a router (or a person) would have gone round. So: two starting orders (shortest first,
    # longest first), then up to --passes re-orderings with the failed routes first. Anything that still fails is
    # routed ALONE on an empty grid: a local link that cannot route even alone has no corridor on its layer, which
    # is a placement defect (HARD); one that routes alone but never together is a WARN for a human look.
    if not a.no_route:
        if a.escape_to == "edge":
            band = L["outline"].buffer(-(rules.edge)).difference(L["outline"].buffer(-(rules.edge + 3 * a.grid)))
        else:
            band = ic.courtyard.buffer(a.ring).difference(ic.courtyard.buffer(a.ring - 3 * a.grid))
        vias_ok = L["layers"] >= 2

        def route_link(G, i):
            k = links[i]
            return G.route(k["net"], [k["a"].poly], [(side, k["b"].poly)], layers=(side,), allow_via=False,
                           max_len=max(12.0, 2.5 * k["d"] + 3.0)) is not None

        def route_escape(G, net, gm):
            sp = [p.poly for p in ic.pads if p.net == net]
            return G.route(net, sp, [gm, gm], layers=(side,), allow_via=vias_ok, max_len=a.ring + 12.0) is not None

        def one_pass(li, en):
            G = Grid(L, rules, window, a.grid)
            gm = G.mask(band.intersection(window))
            lf = [i for i in li if not route_link(G, i)]
            ef = [n for n in en if not route_escape(G, n, gm)]
            return lf, ef

        best, npass = None, 0
        for li, en in ((list(range(len(links))), list(esc)), (list(range(len(links)))[::-1], esc[::-1])):
            for _ in range(1 + a.passes):
                lf, ef = one_pass(li, en)
                npass += 1
                if best is None or (len(lf), len(ef)) < (len(best[0]), len(best[1])):
                    best = (lf, ef)
                if not lf and not ef:
                    break
                li = lf + [i for i in li if i not in lf]
                en = ef + [n for n in en if n not in ef]
            if not best[0] and not best[1]:
                break
        lf, ef = best
        alone_l, alone_e = [], []
        for i in lf:
            G = Grid(L, rules, window, a.grid)
            if not route_link(G, i):
                alone_l.append(i)
        for n in ef:
            G = Grid(L, rules, window, a.grid)
            if not route_escape(G, n, G.mask(band.intersection(window))):
                alone_e.append(n)
        out["passes"] = npass
        out["links_together"] = not lf
        out["links_failed"] = [dict(link=links[i]["name"], alone=i not in alone_l) for i in lf]
        out["links_blocked"] = [links[i]["name"] for i in alone_l]
        out["escapes_failed"] = [dict(net=n, alone=n not in alone_e) for n in ef]
        out["escapes_unresolved"] = list(alone_e)

    # --- fronts
    fronts = []
    for p in sig:
        if p.net in local_nets:
            continue
        r = rules.of(p.net)
        w = r["track"] + 2 * r["clear"]
        dx, dy = p.center[0] - ic.x, p.center[1] - ic.y
        ux, uy = ((1 if dx > 0 else -1), 0) if abs(dx) >= abs(dy) else (0, (1 if dy > 0 else -1))
        x0, y0, x1, y1 = p.poly.bounds
        sx = (x1 if ux > 0 else x0) if ux else p.center[0]
        sy = (y1 if uy > 0 else y0) if uy else p.center[1]
        hits, ok = set(), False
        for ang in (0, 45, -45):
            t = math.radians(ang)
            vx, vy = ux * math.cos(t) - uy * math.sin(t), ux * math.sin(t) + uy * math.cos(t)
            ch = LineString([(sx, sy), (sx + a.front * vx, sy + a.front * vy)]).buffer(w / 2, cap_style=2)
            h = set()
            for fp in L["footprints"]:
                if fp.ref == ic.ref or fp.back != ic.back:
                    continue
                for q in fp.pads:
                    if q.net != p.net and q.poly.intersects(ch):
                        h.add(q.name)
            if not h:
                ok = True
                break
            hits |= h
        if not ok:
            fronts.append(dict(pin=p.num, net=p.net, blocked_by=sorted(hits)))
    out["fronts"] = fronts

    # --- nearest local part per pin, held strips, ground pad facing
    held, facing = [], []
    nearest = {}
    for p in sig:
        cands = [(p.poly.distance(q.poly), fp, q) for fp in small for q in fp.pads if q.net == p.net]
        if not cands:
            continue
        d, fp, q = min(cands, key=lambda t: t[0])
        nearest[p.num] = (d, fp, q)
        g = [x for x in fp.pads if is_ground(x.net, gnd)]
        if g and len(fp.pads) == 2 and math.dist(g[0].center, p.center) < math.dist(q.center, p.center):
            facing.append(dict(pin=p.num, net=p.net, part=fp.ref, gap=round(d, 3)))
        if d > a.far:
            dx, dy = p.center[0] - ic.x, p.center[1] - ic.y
            ux, uy = ((1 if dx > 0 else -1), 0) if abs(dx) >= abs(dy) else (0, (1 if dy > 0 else -1))
            width = 1.0
            strip = LineString([p.center, (p.center[0] + ux * a.far, p.center[1] + uy * a.far)]).buffer(
                width / 2, cap_style=2).difference(ic.courtyard)
            who = sorted(o.ref for o in L["footprints"] if o.ref not in (ic.ref, fp.ref) and o.back == ic.back
                         and o.courtyard.intersection(strip).area > 1e-4
                         and not any(x.net == p.net for x in o.pads))
            held.append(dict(pin=p.num, net=p.net, part=fp.ref, gap=round(d, 3), held_by=who))
    out["held"] = sorted(held, key=lambda h: -h["gap"])
    out["ground_facing_pin"] = facing

    # --- crowded neighbouring pins
    pitch = None
    smd = [p for p in ic.pads if p.kind == "smd"]
    ds = [math.dist(x.center, y.center) for i, x in enumerate(smd) for y in smd[i + 1:]]
    if ds:
        pitch = min(ds)
    crowded = []
    if pitch:
        pins = [p for p in sig if p.num in nearest]
        for i, x in enumerate(pins):
            for y in pins[i + 1:]:
                if math.dist(x.center, y.center) > 1.2 * pitch:
                    continue
                fx, fy = nearest[x.num][1], nearest[y.num][1]
                gx, gy = nearest[x.num][0], nearest[y.num][0]
                if fx.ref == fy.ref or not ((gx > a.far) ^ (gy > a.far)):
                    continue                   # only when one part got the spot and the other was pushed out

                def radial_width(fp):          # a radial part lies with its narrow side along the pin row
                    x0, y0, x1, y1 = fp.courtyard.bounds
                    return min(x1 - x0, y1 - y0)
                need = radial_width(fx) + radial_width(fy)
                if need > 2 * pitch + 1e-6:
                    crowded.append(dict(pins=[x.num, y.num], parts=[fx.ref, fy.ref], widths=round(need, 2),
                                        two_pitch=round(2 * pitch, 2),
                                        gaps=[round(nearest[x.num][0], 2), round(nearest[y.num][0], 2)]))
    out["crowded"] = crowded

    # --- two-pad parts across two IC pins
    pairs = []
    for fp in small:
        s = [q for q in fp.pads if q.net and not is_ground(q.net, gnd)]
        if len(fp.pads) != 2 or len(s) != 2 or s[0].net == s[1].net:
            continue
        if any(q.net.startswith("+") or "POWER" in (NETCLASS_OF.get(q.net) or "") for q in s):
            continue                           # a pull-up or a feed resistor, not a part across two signal pins
        gaps = []
        for q in s:
            pins = [p for p in sig if p.net == q.net]
            if not pins:
                break
            gaps.append(min(q.poly.distance(p.poly) for p in pins))
        if len(gaps) == 2:
            pairs.append(dict(part=fp.ref, gaps=[round(g, 3) for g in gaps], difference=round(abs(gaps[0] - gaps[1]), 3)))
    out["pairs"] = pairs

    # --- ground via sites (boards with planes)
    vias = []
    if L["layers"] > 2:
        allp = [q for fp in L["footprints"] for q in fp.pads if q.poly.intersects(window)]
        for fp in small:
            for q in fp.pads:
                if not is_ground(q.net, gnd):
                    continue
                rv = rules.of(q.net)
                hv, c = rv["via"] / 2, rv["clear"]
                allowed = L["outline"].buffer(-(rules.edge + hv)).intersection(q.poly.buffer(1.2 + hv))
                obst = [x.poly.buffer(max(c, rules.of(x.net)["clear"]) + hv, 8) for x in allp if x.net != q.net]
                obst += [x.poly.buffer(hv, 8) for x in allp if x.net == q.net and x.kind == "smd" and x is not q]
                if obst:
                    allowed = allowed.difference(unary_union(obst))
                if allowed.is_empty:
                    vias.append(dict(pad=q.name, site=None))
    out["no_via_site"] = vias

    # --- rotation score
    netpads = {}
    for fp in L["footprints"]:
        for q in fp.pads:
            if q.net:
                netpads.setdefault(q.net, []).append(q)
    sc = {}
    for rot in (0, 90, 180, 270):
        t = math.radians(rot)
        s = 0.0
        for p in sig:
            far = [q.center for q in netpads.get(p.net, []) if q.ref != ic.ref]
            if not far:
                continue
            cx = sum(c[0] for c in far) / len(far)
            cy = sum(c[1] for c in far) / len(far)
            dx, dy = p.center[0] - ic.x, p.center[1] - ic.y
            px = ic.x + dx * math.cos(t) - dy * math.sin(t)
            py = ic.y + dx * math.sin(t) + dy * math.cos(t)
            s += (3.0 if p.net in local_nets else 1.0) * math.hypot(px - cx, py - cy)
        sc[rot] = round(s, 1)
    best = min(sc, key=sc.get)
    out["rotation"] = dict(scores={f"+{k}": v for k, v in sc.items()},
                           suggest=(f"+{best} deg" if best and sc[best] < 0.9 * sc[0] else None))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("board")
    ap.add_argument("--ic", nargs="*", help="ICs to check (default: every U* / IC* / Q* footprint with more than 4 pads)")
    ap.add_argument("--ground", nargs="*", default=[r".*GND.*", r"VSS.*", r"0V"],
                    help="ground net regexes (full match); default .*GND.*, VSS.*, 0V")
    ap.add_argument("--local", type=float, default=6.0, help="local parts: a pad within this of the IC pin on its "
                    "net, or of a local part on a signal net (mm)")
    ap.add_argument("--ring", type=float, default=5.0, help="escape ring outside the IC courtyard (mm)")
    ap.add_argument("--escape-to", choices=("ring", "edge"), default="ring")
    ap.add_argument("--front", type=float, default=2.0, help="fan-out channel length (mm)")
    ap.add_argument("--far", type=float, default=2.6, help="pin-to-part gap above which the strip is examined (mm)")
    ap.add_argument("--grid", type=float, default=0.05)
    ap.add_argument("--passes", type=int, default=4, help="re-orderings (failed routes first) after each start order")
    ap.add_argument("--neck", type=float, help="neck-down width for wider nets near the IC (default: the Default "
                    "class track width)")
    ap.add_argument("--no-neck", action="store_true", help="route every net at its full class width")
    ap.add_argument("--with-tracks", action="store_true", help="existing tracks and vias are obstacles")
    ap.add_argument("--no-route", action="store_true", help="skip the router (links and escapes)")
    for k in ("track", "clear", "via", "edge"):
        ap.add_argument(f"--{k}", type=float)
    ap.add_argument("--rules-override", action="store_true")
    ap.add_argument("--json")
    a = ap.parse_args()
    t0 = time.time()
    L = load(a.board, a.with_tracks)
    if L["outline"] is None:
        sys.exit("no board outline (Edge.Cuts)")
    rules = Rules(a.board, L, a)
    fps = {fp.ref: fp for fp in L["footprints"]}
    if a.ic:
        miss = [r for r in a.ic if r not in fps]
        if miss:
            sys.exit(f"not on the board: {', '.join(miss)}")
        ics = [fps[r] for r in a.ic]
    else:
        ics = [fp for fp in L["footprints"] if re.match(r"(U|IC|Q)\d", fp.ref) and len(fp.pads) > 4
               and L["outline"].contains(Point(fp.x, fp.y))]
        ics.sort(key=lambda f: (re.sub(r"\d+", "", f.ref), int(re.sub(r"\D", "", f.ref) or 0)))
    for line in rules.lines():
        print(line)
    print(f"{len(ics)} ICs; local parts within {a.local} mm; escapes to the "
          + (f"ring {a.ring} mm outside each IC" if a.escape_to == "ring" else "board edge")
          + f"; grid {a.grid} mm; tracks {'kept as obstacles' if a.with_tracks else 'ignored'}; zones ignored\n")
    results, hard, warn = [], [], []
    for ic in ics:
        r = check_ic(L, rules, ic, a, a.ground)
        results.append(r)
        head = f"{r['ic']} ({r['value']}): {len(r['local_parts'])} local parts, {r['links']} local links, {r['escapes']} escapes"
        print(head)
        if not a.no_route:
            if r["links_blocked"]:
                hard.append(r["ic"])
                print(f"  local links BLOCKED (no corridor on the IC's side even alone): open a corridor or move a part")
                for n in r["links_blocked"]:
                    print(f"    BLOCKED {n}")
            if r["links_together"]:
                print(f"  local links together: yes ({r['passes']} pass{'es' if r['passes'] > 1 else ''})")
            else:
                warn.append(r["ic"])
                soft = [f["link"] for f in r["links_failed"] if f["alone"]]
                if soft:
                    print(f"  local links together: not found in {r['passes']} passes; each of these routes alone, "
                          "so look at the corridor (WARN):")
                    for n in soft:
                        print(f"    {n}")
            for n in r["escapes_unresolved"]:
                print(f"  escape UNRESOLVED {n}: no way out of the ring even alone (another side, an earlier via, a "
                      "rotation, or move the part in the way)")
            soft_e = [e["net"] for e in r["escapes_failed"] if e["alone"]]
            if soft_e:
                print(f"  escapes that route alone but not with the rest: {', '.join(soft_e)} (WARN)")
        for f in r["fronts"]:
            print(f"  front blocked: pin {f['pin']} {f['net']} by {', '.join(f['blocked_by'])}")
        for h in r["held"]:
            print(f"  far: pin {h['pin']} {h['net']} -> {h['part']} {h['gap']} mm; strip held by "
                  f"{', '.join(h['held_by']) or 'nothing (free: move the part in)'}")
        for c in r["crowded"]:
            print(f"  crowded: pins {c['pins'][0]}/{c['pins'][1]} parts {c['parts'][0]}/{c['parts'][1]} need "
                  f"{c['widths']} mm along the row, 2 x pitch = {c['two_pitch']} mm (gaps {c['gaps'][0]} / {c['gaps'][1]} mm)")
        for g in r["ground_facing_pin"]:
            print(f"  GROUND PAD FACES PIN: {g['part']} at pin {g['pin']} {g['net']}")
        for p in r["pairs"]:
            if p["difference"] > 0.3:
                print(f"  pair {p['part']}: gaps {p['gaps'][0]} / {p['gaps'][1]} mm, difference {p['difference']} mm")
        for v in r["no_via_site"]:
            print(f"  no via site within 1.2 mm: {v['pad']}")
        if r["rotation"]["suggest"]:
            print(f"  rotation: {r['rotation']['suggest']} scores better {r['rotation']['scores']} (advisory)")
    print(f"\nLocal reachability: {'PASS' if not hard else 'FAIL'}"
          + (f" - blocked local links around {', '.join(hard)}" if hard else "")
          + (f"; no common solution found around {', '.join(warn)} (WARN)" if warn else "")
          + f" ({time.time() - t0:.0f} s)")
    if a.json:
        json.dump(dict(board=a.board, rules=rules.lines(), results=results, fail=hard, warn=warn),
                  open(a.json, "w", encoding="utf-8"), indent=1, default=str)
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
