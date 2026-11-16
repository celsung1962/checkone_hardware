#!/usr/bin/env python3
"""
Shared library of the kicad-placement scripts. Runs inside KiCad's Python (it imports pcbnew).

  - KiCad 8 / 9 / 10 API differences (board outline, flip, footprint courtyard);
  - board geometry in mm: outline mask with an inset, courtyard rectangles, THT test, pad pitch;
  - a fine occupancy raster (default 0.05 mm) with exact outward rounding, so a part never "costs" more area than
    its courtyard + spacing (a 0.25 mm raster wastes ~40 % of the area on small parts);
  - the placement plan (JSON) and the selection of parts per block.
"""
import fnmatch, json, math, os, re
import pcbnew

mm = pcbnew.ToMM


def FM(v):
    return pcbnew.FromMM(float(v))


# ----------------------------------------------------------------------------- KiCad version compatibility
def board_outline(board):
    """SHAPE_POLY_SET of the board outline (Edge.Cuts), across KiCad versions."""
    poly = pcbnew.SHAPE_POLY_SET()
    try:
        board.GetBoardPolygonOutlines(poly, False)          # KiCad 10: (poly, aInferOutlineIfNecessary)
    except TypeError:
        board.GetBoardPolygonOutlines(poly)                 # KiCad 8 / 9
    return poly


def flip_to_top(fp):
    """Move a bottom-side footprint to the top side (no-op when already on top)."""
    if not fp.IsFlipped():
        return False
    pos = fp.GetPosition()
    try:
        fp.Flip(pos, pcbnew.FLIP_DIRECTION_LEFT_RIGHT)      # KiCad 9+
    except (AttributeError, TypeError):
        fp.Flip(pos, False)                                 # KiCad 8
    return True


def courtyard_rect(fp, layer=None):
    """(left, top, right, bottom) in mm of the front courtyard; the body box when the footprint has none."""
    cy = fp.GetCourtyard(pcbnew.F_CrtYd if layer is None else layer)
    r = cy.BBox() if cy.OutlineCount() else fp.GetBoundingBox(False)
    return (mm(r.GetLeft()), mm(r.GetTop()), mm(r.GetRight()), mm(r.GetBottom()))


def courtyard_area(fp):
    cy = fp.GetCourtyard(pcbnew.F_CrtYd)
    if cy.OutlineCount():
        return cy.Area() / 1e12
    r = courtyard_rect(fp)
    return (r[2] - r[0]) * (r[3] - r[1])


def is_tht(fp):
    """A soldered through-hole pin: a numbered plated hole. Unnumbered plated holes (an LED light hole, a shield
    stake) need no soldering iron and do not make the part THT (1.2.0)."""
    return any(p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH and p.GetNumber() not in ("", "~") for p in fp.Pads())


def min_smd_pitch(fp):
    ps = [(p.GetPosition().x, p.GetPosition().y) for p in fp.Pads() if p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD]
    d = [math.hypot(a[0] - c[0], a[1] - c[1]) for k, a in enumerate(ps) for c in ps[k + 1:]]
    return mm(min(d)) if d else 99.0


def ref_num(ref):
    m = re.search(r"(\d+)$", ref)
    return int(m.group(1)) if m else 0


def sheet_of(fp):
    return fp.GetSheetname().strip("/") if hasattr(fp, "GetSheetname") else ""


# ----------------------------------------------------------------------------- the plan
DEFAULTS = {
    "grid": 0.25,                     # placement grid of footprint origins (mm)
    "resolution": 0.05,               # occupancy raster (mm)
    "edge_clearance": 1.0,            # courtyard to Edge.Cuts (mm)
    "sensitive_edge_clearance": 2.5,  # fine-pitch ICs, MLCC > 0805, crystals/oscillators
    "spacing": 0.3,                   # courtyard to courtyard, SMD (mm)
    "tht_spacing": 1.0,               # around through-hole parts (hand soldering, iron access)
    "mech_spacing": 1.0,              # around fixed connectors, holes and other mechanical parts
    "fixed": ["H*", "MH*"],           # glob patterns of footprints that never move
    "treat_locked_as_fixed": True,
    "lock_fixed": True,
    "keepouts": [],                   # [{"name", "rect": [x0,y0,x1,y1], "refs": ["PS1"] or ["*"]}]
    "artwork_obstacle": True,         # padless logos / titles on the front layers keep parts off (bounding box)
    "regions": {},                    # name -> [[x0,y0,x1,y1], ...]
    "blocks": [],
    "sensitive": {"fine_pitch_max": 0.66, "mlcc_packages": ["1206", "1210", "1812", "2220"],
                  "prefixes": ["Y", "X"]},
    "decap_max_sch_distance": 100.0,  # schematic distance (mm) for assigning a capacitor to an IC
    "heat": [], "heat_sensitive": [], "heat_min_distance": 5.0,
    # aluminium electrolytic capacitors are heat-sensitive by default (lifetime halves every ~10 K): footprint-name
    # fragments that identify them; [] switches it off (1.2.0)
    "electrolytic_footprints": ["CP_Elec", "CP_Radial", "CP_Axial", "C_Elec", "CP_THT"],
    # test-point access (1.2.0, WARN): probe pitch between test-point pads, pad to any other courtyard, pad to
    # Edge.Cuts, and all on one side for a single-sided fixture or bench probing
    "testpoints": {"prefixes": ["TP"], "min_pitch": 2.54, "min_to_part": 1.0, "min_to_edge": 1.0, "one_side": True},
    # polarity / pin-1 marks (1.2.0, WARN): polarised parts must keep a silkscreen graphic that no other part covers
    "polarity": {"prefixes": ["D", "LED", "U", "Q", "IC"], "footprints": ["CP_", "LED", "Diode", "D_"],
                 "exclude_prefixes": ["DS"]},
    "near": [],                       # [{"a": "Y1.3", "b": "U1.15", "max_mm": 5, "why": "..."}] datasheet proximity
}


def load_plan(path):
    plan = json.load(open(path, encoding="utf-8"))
    base = os.path.dirname(os.path.abspath(path))
    for k, v in DEFAULTS.items():
        plan.setdefault(k, v)
    for k in ("board", "pintypes", "schpos"):
        if plan.get(k) and not os.path.isabs(plan[k]):
            plan[k] = os.path.normpath(os.path.join(base, plan[k]))
    return plan


def matches(ref, patterns):
    return any(fnmatch.fnmatchcase(ref, p) for p in patterns)


def select(sel, refs, fps, sch):
    """Refs matching a block's "select": explicit "refs" (globs), OR all of the other given conditions:
    sheet (name or list), prefix (list), range [lo, hi] on the reference number, regex; minus "exclude"."""
    out = set()
    explicit = sel.get("refs", [])
    conds = {k: v for k, v in sel.items() if k not in ("refs", "exclude")}
    for r in refs:
        if explicit and matches(r, explicit):
            out.add(r)
            continue
        if not conds:
            continue
        ok = True
        if "all" in conds and not conds["all"]:
            ok = False
        if "sheet" in conds:
            sheets = conds["sheet"] if isinstance(conds["sheet"], list) else [conds["sheet"]]
            names = {sheet_of(fps[r])} | ({sch[r][0]} if r in sch else set())   # PCB and schematic names
            names |= {n.rsplit("/", 1)[-1] for n in names if n}                 # nested: last level too
            ok &= any(fnmatch.fnmatchcase(n, x) for n in names if n for x in sheets)
        if "prefix" in conds:
            ok &= re.match(r"^(%s)\d" % "|".join(map(re.escape, conds["prefix"])), r) is not None
        if "range" in conds:
            ok &= conds["range"][0] <= ref_num(r) <= conds["range"][1]
        if "regex" in conds:
            ok &= re.search(conds["regex"], r) is not None
        if ok:
            out.add(r)
    return {r for r in out if not matches(r, sel.get("exclude", []))}


# ----------------------------------------------------------------------------- occupancy raster
class Raster:
    """Boolean rasters over the board bounding box. Origins of candidate positions are on the placement grid;
    occupancy is tested on the fine raster with exact outward rounding (<= one resolution step)."""

    def __init__(self, board, grid=0.25, res=0.05):
        import numpy as np
        self.np = np
        bb = board.GetBoardEdgesBoundingBox()
        self.X0, self.Y0 = math.floor(mm(bb.GetLeft())), math.floor(mm(bb.GetTop()))
        self.X1, self.Y1 = math.ceil(mm(bb.GetRight())), math.ceil(mm(bb.GetBottom()))
        self.grid, self.res = grid, res
        self.NX, self.NY = int((self.X1 - self.X0) / grid) + 1, int((self.Y1 - self.Y0) / grid) + 1
        self.UP = int(round(grid / res))
        self.FX, self.FY = self.NX * self.UP, self.NY * self.UP
        self.XS = self.X0 + np.arange(self.NX) * grid
        self.YS = self.Y0 + np.arange(self.NY) * grid
        self.board = board

    def inside(self, inset):
        """Fine mask of points >= inset (mm) inside the outline. Computed on the coarse grid with an extra margin
        of one grid step (a smaller margin let courtyards reach 0.91 mm from a chamfered edge), then expanded."""
        np = self.np
        poly = board_outline(self.board)
        amount = FM(-(inset + self.grid))
        try:
            poly.Inflate(amount, pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, FM(0.05))   # KiCad 8+
        except (AttributeError, TypeError):
            poly.Inflate(amount, 16)                                                  # older signature
        m = np.zeros((self.NY, self.NX), bool)
        for j in range(self.NY):
            for i in range(self.NX):
                m[j, i] = poly.Contains(pcbnew.VECTOR2I(FM(self.XS[i]), FM(self.YS[j])))
        return np.kron(m, np.ones((self.UP, self.UP), bool))

    def box(self, a, t, c, d):
        return (max(0, math.floor((a - self.X0) / self.res + 1e-6)), max(0, math.floor((t - self.Y0) / self.res + 1e-6)),
                min(self.FX, math.ceil((c - self.X0) / self.res - 1e-6)), min(self.FY, math.ceil((d - self.Y0) / self.res - 1e-6)))

    def empty(self):
        return self.np.zeros((self.FY, self.FX), bool)

    def mark(self, occ, rect, halo):
        i0, j0, i1, j1 = self.box(rect[0] - halo, rect[1] - halo, rect[2] + halo, rect[3] + halo)
        occ[j0:j1, i0:i1] = True

    def rects_mask(self, rects):
        m = self.empty()
        for r in rects:
            i0, j0, i1, j1 = self.box(*r)
            m[j0:j1, i0:i1] = True
        return m

    def area(self, mask):
        return float(mask.sum()) * self.res * self.res

    def sat(self, bad):
        np = self.np
        s = np.zeros((bad.shape[0] + 1, bad.shape[1] + 1), np.int32)
        s[1:, 1:] = bad.astype(np.int32).cumsum(0).cumsum(1)
        return s

    def feasible(self, S, rect_rel):
        """Boolean (NY, NX) of grid origins where the courtyard rectangle (relative to the origin) is all-free."""
        np = self.np
        l, t, r, d = rect_rel
        ii0 = np.floor((self.XS + l - self.X0) / self.res + 1e-6).astype(int)
        ii1 = np.ceil((self.XS + r - self.X0) / self.res - 1e-6).astype(int)
        jj0 = np.floor((self.YS + t - self.Y0) / self.res + 1e-6).astype(int)
        jj1 = np.ceil((self.YS + d - self.Y0) / self.res - 1e-6).astype(int)
        okI = (ii0 >= 0) & (ii1 <= self.FX)
        okJ = (jj0 >= 0) & (jj1 <= self.FY)
        a0, a1 = np.clip(ii0, 0, self.FX), np.clip(ii1, 0, self.FX)
        b0, b1 = np.clip(jj0, 0, self.FY), np.clip(jj1, 0, self.FY)
        tot = S[b1][:, a1] - S[b0][:, a1] - S[b1][:, a0] + S[b0][:, a0]
        return (tot == 0) & okJ[:, None] & okI[None, :]


def heat_sensitive_refs(fps, plan):
    """The plan's heat_sensitive list plus every aluminium electrolytic capacitor found by footprint name (1.2.0).
    Electrolytics dry out with heat; the articles behind this rule ask for distance from heat sources."""
    pats = plan.get("electrolytic_footprints") or []
    auto = {r for r, f in fps.items() if r.startswith("C") and any(p in f.GetFPIDAsString() for p in pats)}
    return sorted(set(plan.get("heat_sensitive", [])) | auto)


def is_polarised(ref, fp, plan):
    """Diodes, LEDs, ICs, transistors and polarised capacitors (by reference prefix or footprint name)."""
    p = plan.get("polarity") or {}
    if ref.startswith(tuple(p.get("exclude_prefixes", []))):
        return False
    if any(ref.startswith(x) and ref[len(x):len(x) + 1].isdigit() for x in p.get("prefixes", [])):
        return True
    return any(x in fp.GetFPIDAsString() for x in p.get("footprints", []))


def silk_marks(fp):
    """Silkscreen graphics of a footprint (not texts), as (left, top, right, bottom) mm boxes."""
    out = []
    for g in fp.GraphicalItems():
        if g.GetLayerName() not in ("F.Silkscreen", "B.Silkscreen", "F.SilkS", "B.SilkS"):
            continue
        if g.GetClass() in ("PCB_TEXT", "PCB_FIELD", "FP_TEXT", "PCB_TEXTBOX"):
            continue
        r = g.GetBoundingBox()
        out.append((mm(r.GetLeft()), mm(r.GetTop()), mm(r.GetRight()), mm(r.GetBottom())))
    return out


def is_artwork(fp):
    """Footprints without pads (logos, titles, graphics): never placed, never part of spacing checks."""
    return len(list(fp.Pads())) == 0


def fixed_refs(board, plan):
    fixed = set()
    for f in board.GetFootprints():
        r = f.GetReference()
        if matches(r, plan["fixed"]) or (plan.get("treat_locked_as_fixed", True) and f.IsLocked()) or is_artwork(f):
            fixed.add(r)
    return fixed


def zones(board):
    """Zones as typed objects: iterating board.Zones() can yield untyped SwigPyObjects in some contexts."""
    return [board.GetArea(i) for i in range(board.GetAreaCount())]


def footprint_keepouts(board):
    """Bounding boxes (mm) of rule areas that forbid footprints on the front side (conservative for non-rectangular
    areas)."""
    out = []
    for z in zones(board):
        if z.GetIsRuleArea() and getattr(z, "GetDoNotAllowFootprints", lambda: False)():
            if z.GetLayerSet().Contains(pcbnew.F_Cu) or z.GetLayerSet().Contains(pcbnew.F_CrtYd):
                r = z.GetBoundingBox()
                out.append((mm(r.GetLeft()), mm(r.GetTop()), mm(r.GetRight()), mm(r.GetBottom())))
    return out


def artwork_keepouts(board, plan):
    """Bounding boxes of padless artwork (logos, titles) drawn on the FRONT layers: parts placed on top of a logo
    ruin it. "artwork_obstacle": false in the plan turns this off (some teams let parts cover a logo)."""
    if not plan.get("artwork_obstacle", True):
        return []
    out = []
    for f in board.GetFootprints():
        if is_artwork(f) and any(g.GetLayerName().startswith("F.") and "Fab" not in g.GetLayerName()
                                 and "Courtyard" not in g.GetLayerName() for g in f.GraphicalItems()):
            r = f.GetBoundingBox(False)
            out.append((f.GetReference(), (mm(r.GetLeft()), mm(r.GetTop()), mm(r.GetRight()), mm(r.GetBottom()))))
    return out


def mark_fixed(raster, occ, board, fixed, plan):
    """Fixed footprints (with spacing; mechanical ones with mech_spacing) and footprint rule areas -> occupied."""
    for f in board.GetFootprints():
        r = f.GetReference()
        if r not in fixed or is_artwork(f):
            continue
        mech = is_tht(f) or r.startswith(("H", "MH", "J", "BT", "SW"))
        raster.mark(occ, courtyard_rect(f), plan["mech_spacing"] if mech else plan["spacing"])
    for rect in footprint_keepouts(board) + [q for _, q in artwork_keepouts(board, plan)]:
        raster.mark(occ, rect, 0.0)


# ----------------------------------------------------------------------------- decoupling assignment
SUPPLY = re.compile(r"^/?([+-]\d|V(CC|DD|EE|SS|BAT|BUS|IN|OUT)|GND|AGND|DGND|PGND|\+|-)", re.I)
PWRNAME = re.compile(r"^(A?VDD|D?VDD|VCC|VIN|VINA|VOUT|V\+|V-|VEE|VS|VBUS|VDDIO|IOVDD|BAT|3V3|CAP|LDO|VREF|PVIN|AVCC)", re.I)
GNDNAME = re.compile(r"^(A?GND|D?GND|VSS|PGND|EPAD|EP)(_\d+)?$", re.I)


def assign_decaps(fps, caps, pintypes, schpos, max_sch_distance=100.0):
    """{cap: (ic, pin)}: a capacitor between a ground of an IC and a rail that reaches a power pin of that IC
    (pin type power_in/power_out from the netlist, or a supply-like pin function), assigned to the schematically
    nearest such IC on the same sheet. Without schpos every candidate counts as 50 mm away."""
    ics = [r for r in fps if r.startswith(("U", "PS", "IC"))]
    gnds = {}
    for u in ics:
        g = {"GND"}
        for p in fps[u].Pads():
            func = pintypes.get(f"{u}.{p.GetNumber()}", ["", "", ""])[1]
            if GNDNAME.match(func or "") and p.GetNetname():
                g.add(p.GetNetname())
        gnds[u] = g
    out = {}
    for c in caps:
        if not c.startswith("C"):
            continue
        nets = [p.GetNetname() for p in fps[c].Pads()]
        if len(nets) != 2:
            continue
        best = None
        for u in ics:
            for rail, other in ((nets[0], nets[1]), (nets[1], nets[0])):
                if other not in gnds[u] or rail in gnds[u]:
                    continue
                for p in fps[u].Pads():
                    if p.GetNetname() != rail:
                        continue
                    typ, func, _ = pintypes.get(f"{u}.{p.GetNumber()}", ["", "", ""])
                    # functions like "+VOUT_6" / "-VIN": the sign is not part of the name (a module's output pin is
                    # often typed "output", so the name is the only clue)
                    if not (typ.startswith(("power_in", "power_out")) or PWRNAME.match((func or "").lstrip("+-~"))):
                        continue
                    if u in schpos and c in schpos:
                        d = math.hypot(schpos[u][1] - schpos[c][1], schpos[u][2] - schpos[c][2])
                        d += 0 if schpos[u][0] == schpos[c][0] else 1e4
                    else:
                        d = 50.0
                    if best is None or d < best[0]:
                        best = (d, u, p.GetNumber())
        if best and best[0] < max_sch_distance:
            out[c] = (best[1], best[2])
    return out


# ---------------------------------------------------------------- datasheet proximity ("near")
# Found on the ServiceOne main board (2026-10-05): after placement and routing, six of ten datasheet layout findings
# were PLACEMENT problems no router could fix - the ADC clock oscillator 23 mm from its pin (its trace ended up in
# one corridor with the analog inputs), an ADC input filter capacitor 14 mm from the pins, the second current
# monitor 44 mm from its shunt, the USB series resistors 31-40 mm from the MCU. None broke a spacing or edge rule,
# so the placement check passed. "near" turns such datasheet rules into checked pad-to-pad distances.
SW_FUNC = re.compile(r"^(SW\d*|LX\d*|L\d|PH\d*|PHASE)$", re.I)
AIN_FUNC = re.compile(r"^(AIN\d*[PN]?|ADC\d*[PN]?|CH\d+[PN]?)$", re.I)   # not IN+/IN-: monitors and op-amps
USB_NET = re.compile(r"(USB|^/?D[PMN]$|D\+|D-|_DP$|_DN$|_DM$)", re.I)
FLY_FUNC = re.compile(r"^(C\d*[+-]|CP|CN|CFLY\d*[+-]?|BOOT|BST|CB|CAP\d*[+-])$", re.I)
POWERISH = re.compile(r"^/?([+-]?\d|GND|VCC|VDD|VBAT|VBUS|VIN|VOUT|AGND|DGND|PGND)", re.I)


def parse_ohms(value):
    """'0R02' -> 0.02, 'R010' -> 0.01, '20m' -> 0.02, '4K7' / '4.7K' -> 4700, '100' -> 100; None if not a value."""
    v = (value or "").strip()
    for u in ("\u03a9", "ohm", "Ohm", "OHM"):
        v = v.replace(u, "")
    v = v.strip()
    m = re.match(r"^(\d+(?:\.\d+)?)\s*([mkKMRr]?)$", v)
    if m:
        return float(m.group(1)) * {"m": 1e-3, "k": 1e3, "K": 1e3, "M": 1e6, "R": 1.0, "r": 1.0, "": 1.0}[m.group(2)]
    m = re.match(r"^(\d*)([RrKkM])(\d*)$", v)
    if m and (m.group(1) or m.group(3)):
        return float((m.group(1) or "0") + "." + (m.group(3) or "0")) * {"R": 1.0, "r": 1.0, "K": 1e3, "k": 1e3, "M": 1e6}[m.group(2)]
    return None


def pad_points(fps, tag):
    """REF.PAD -> [(x, y)] of that pad; REF -> every pad of the footprint. Empty when not found."""
    ref, _, num = tag.partition(".")
    f = fps.get(ref)
    if f is None:
        return []
    return [(mm(p.GetPosition().x), mm(p.GetPosition().y)) for p in f.Pads() if not num or p.GetNumber() == num]


def near_distance(fps, a, b):
    pa, pb = pad_points(fps, a), pad_points(fps, b)
    if not pa or not pb:
        return None
    return min(math.hypot(x1 - x2, y1 - y2) for x1, y1 in pa for x2, y2 in pb)


def suggest_near(fps, pintypes):
    """Candidate datasheet proximity rules found in the netlist. Suggestions only: each one is a design decision."""
    ics = {r: f for r, f in fps.items() if r.startswith(("U", "IC"))}

    def func(u, pin):
        # the netlist function carries the pin number as a suffix ("AIN1P_4", "SW_1"); drop it
        return re.sub(r"_[A-Za-z]?\d+$", "", pintypes.get(f"{u}.{pin}", ["", "", ""])[1] or "")
    net_ic_pins = {}
    for u, f in ics.items():
        for p in f.Pads():
            if p.GetNetname():
                net_ic_pins.setdefault(p.GetNetname(), []).append((u, p.GetNumber()))
    out, seen = [], set()

    def add(a, b, mx, why):
        key = (a.split(".")[0], b.split(".")[0], why)
        if key not in seen:
            seen.add(key)
            out.append({"a": a, "b": b, "max_mm": mx, "why": why})
    for r, f in sorted(fps.items()):
        pads = [p for p in f.Pads() if p.GetNetname()]
        if r.startswith(("Y", "X")):                          # clock source at the clock pin
            for p in pads:
                n = p.GetNetname()
                if POWERISH.match(n) or "GND" in n.upper():
                    continue
                hops = [n]                                    # directly, or through one series resistor / capacitor
                for q, g in fps.items():
                    if q.startswith(("R", "C")) and q != r:
                        qn = [x.GetNetname() for x in g.Pads()]
                        if len(qn) == 2 and n in qn:
                            other = qn[1] if qn[0] == n else qn[0]
                            if other and not POWERISH.match(other) and "GND" not in other.upper():
                                hops.append(other)
                for h in hops:
                    for u, pin in net_ic_pins.get(h, []):
                        add(f"{r}.{p.GetNumber()}", f"{u}.{pin}", 5.0,
                            "clock source at its clock pin, on the digital side (keeps the clock out of analog corridors)")
        elif r.startswith("R"):
            ohm = parse_ohms(f.GetValue())
            nets = {p.GetNetname() for p in pads}
            if ohm is not None and 0 < ohm < 1.0 and len(nets) == 2:   # shunt -> current monitor with both nets
                for u in ics:
                    un = {p.GetNetname() for p in ics[u].Pads()}
                    if nets <= un:
                        add(r, u, 6.0, "current monitor beside its shunt: short dedicated Kelvin sense lines")
            if any(USB_NET.search(n) for n in nets):               # USB series parts at the MCU
                for n in nets:
                    if USB_NET.search(n):
                        continue
                    for u, pin in net_ic_pins.get(n, []):
                        add(f"{r}", f"{u}.{pin}", 3.0, "USB series resistor at the chip pin")
        elif r.startswith("C"):
            for p in pads:                                         # ADC input filter capacitors at the pins
                for u, pin in net_ic_pins.get(p.GetNetname(), []):
                    if AIN_FUNC.match(func(u, pin)):
                        add(f"{r}.{p.GetNumber()}", f"{u}.{pin}", 3.0, "ADC input filter capacitor at the input pin")
                    elif FLY_FUNC.match(func(u, pin)):
                        add(f"{r}.{p.GetNumber()}", f"{u}.{pin}", 3.0, "flying / bootstrap capacitor at its pins")
        elif r.startswith("L"):
            for p in pads:                                         # converter inductor at its switch pin
                for u, pin in net_ic_pins.get(p.GetNetname(), []):
                    if SW_FUNC.match(func(u, pin)):
                        add(f"{r}.{p.GetNumber()}", f"{u}.{pin}", 5.0, "converter inductor at its switch pin (small hot loop)")
    return out
