"""
schgen - minimal KiCad 10 schematic writer. CheckOne copy (2026-11-16) of GapOne_V2/hardware/schgen.py, itself the
form-reference generator (serviceone-hw/hardware/schgen.py @ 1ad2cb8); changes: title-block rev 1.1, date 2026-11-16.

Connection style: every symbol pin gets a short wire stub ending in a local label,
global label, hierarchical label, power symbol or no-connect flag. No free routing,
so connectivity is exactly what the generator states and is verified afterwards by
`kicad-cli sch erc` and the netlist rules.

Coordinates in mm, schematic frame (Y down), all on the 1.27 mm (50 mil) grid.
UUIDs are deterministic (uuid5 of sheet/ref/item) so regenerating keeps the
schematic-to-PCB links stable.
"""
import copy, math, os, re, uuid
import sexpdata
from sexpdata import Symbol as S

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = None          # set by set_project("GapOne_CON" | "GapOne_AMP")
PLIB = None
COMPANY = "AQTech Power Prognostics"
KPOWER = r"C:\Program Files\KiCad\10.0\share\kicad\symbols\power.kicad_sym"
NS = uuid.UUID("6b1f3c2e-5f0a-4c55-9a3e-2b5e0c1a7d11")
GRID = 1.27
KICAD_POWER = ("GND", "+3.3V", "+5V", "+12V", "-12V", "+15V", "-15V", "+24V")
STUB = 2.54
GROUND_NETS = ("GND", "AGND", "GND_24V", "GND_LOOP", "CHASSIS")   # symbols drawn pointing down in their library


def U(key):
    return str(uuid.uuid5(NS, key))


def hd(x):
    return x[0].value() if isinstance(x, list) and x and isinstance(x[0], S) else None


def walk(x):
    if isinstance(x, list):
        yield x
        for c in x:
            yield from walk(c)


def snap(v):
    return round(round(v / GRID) * GRID, 4)


# Advance of each character of KiCad's stroke font at 1.27 mm (mm), fitted on 1801 plotted texts (max error 0.03 mm).
# The font is proportional: a fixed width per character misplaces the inner end of long labels by over 1 mm.
CHAR_W = {"%": 1.450, "'": 0.605, "(": 0.846, ")": 0.846, "*": 0.966, "+": 1.572, ",": 0.605, "-": 1.572, ".": 0.605,
          "/": 1.330, ":": 0.605, ";": 0.605, "<": 1.572, "=": 1.572, ">": 1.572, "@": 1.632, "A": 1.088, "B": 1.270,
          "C": 1.270, "D": 1.270, "E": 1.148, "F": 1.088, "G": 1.270, "H": 1.330, "I": 0.605, "J": 0.967, "K": 1.270,
          "L": 1.027, "M": 1.450, "N": 1.330, "O": 1.330, "P": 1.270, "Q": 1.330, "R": 1.270, "S": 1.209, "T": 0.967,
          "U": 1.330, "V": 1.088, "W": 1.450, "X": 1.209, "Y": 1.089, "Z": 1.209, "[": 0.846, "]": 0.846, "_": 0.967,
          "a": 1.148, "b": 1.148, "c": 1.088, "d": 1.148, "e": 1.088, "f": 0.725, "g": 1.148, "h": 1.148, "i": 0.605,
          "k": 1.027, "l": 0.664, "m": 1.693, "n": 1.148, "o": 1.148, "p": 1.148, "q": 1.148, "r": 0.786, "s": 1.027,
          "t": 0.725, "u": 1.148, "v": 0.966, "w": 1.330, "x": 1.027, "y": 0.966, "z": 1.027, "~": 0.907}
CHAR_W.update({str(d): 1.209 for d in range(10)})


def text_width(s, size=1.27):
    """Plotted width (mm) of a single-line text in KiCad's stroke font."""
    return sum(CHAR_W.get(c, 1.21) for c in s) * size / 1.27


FINE = 0.635             # project connection grid 25 mil, KiCad's minimum (D100): label wire ends only
LABEL_GAP = 0.635        # text starts this far from the point where the label wire leaves the pin / lane
LABEL_OFFSET = 0.23      # KiCad draws label text this far inside its anchor (0.228-0.235 measured on the plot, D100)


def snap_fine(v):
    return round(round(v / FINE) * FINE, 4)


def label_wire_fine(net):
    """Wire length for inner-edge alignment: gap + text + KiCad's label text offset (not snapped)."""
    return LABEL_GAP + text_width(net) + LABEL_OFFSET


def label_len(net):
    """Wire length (grid multiple) that runs under the whole text of a 1.27 mm label (+0.6 mm margin)."""
    return round(-(-(text_width(net) + 0.6) // GRID) * GRID, 4)


def font(size=1.27, justify=None, hide=False):
    e = [S("effects"), [S("font"), [S("size"), size, size]]]
    if justify:
        e.append([S("justify")] + [S(j) for j in justify.split()])
    if hide:
        e.append([S("hide"), S("yes")])
    return e


_libs = {}


def set_project(name):
    """Select the board: project name and its symbol library hardware/<name>/<name>.kicad_sym."""
    global PROJECT, PLIB
    PROJECT = name
    PLIB = os.path.join(HERE, name, f"{name}.kicad_sym")
    _libs.clear()


def lib_symbol(lib_id):
    """Return the (flattened) library symbol for lib_id 'Lib:Name'."""
    lib, name = lib_id.split(":", 1)
    path = PLIB if lib == PROJECT else KPOWER if lib == "power" else None
    if path is None:
        raise ValueError(f"library {lib} not allowed (use the project library or power)")
    if path not in _libs:
        tree = sexpdata.loads(open(path, encoding="utf-8").read())
        _libs[path] = {n[1]: n for n in tree[1:] if hd(n) == "symbol"}
    syms = _libs[path]
    sym = copy.deepcopy(syms[name])
    ext = next((c for c in sym if hd(c) == "extends"), None)
    if ext is not None:   # power lib symbols are not derived; project lib is already flattened
        raise ValueError(f"{lib_id}: derived symbol not supported")
    return sym


def sym_pins(sym):
    """{number: dict(name, x, y, ang, len, unit)} in library coordinates (Y up)."""
    pins = {}
    for sub in sym:
        if hd(sub) != "symbol":
            continue
        parts = sub[1].rsplit("_", 2)
        unit = int(parts[-2]) if len(parts) == 3 and parts[-2].isdigit() else 0
        for p in sub:
            if hd(p) != "pin":
                continue
            at = next(c for c in p if hd(c) == "at")
            ln = next((c[1] for c in p if hd(c) == "length"), 0)
            num = str(next(c for c in p if hd(c) == "number")[1])
            nm = str(next(c for c in p if hd(c) == "name")[1])
            pins.setdefault(num, []).append(dict(name=nm, x=at[1], y=at[2], ang=at[3] if len(at) > 3 else 0,
                                                 len=ln, unit=unit, type=p[1].value()))
    return pins


def rot(x, y, deg):
    a = math.radians(deg)
    return x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)


class Part:
    def __init__(self, sheet, lib_id, ref, at, rotation=0, unit=1, value=None, fields=None, dnp=False, mirror=None):
        self.sheet, self.lib_id, self.ref, self.unit, self.dnp = sheet, lib_id, ref, unit, dnp
        if mirror and rotation:
            raise ValueError(f"{ref}: mirror is supported with rotation 0 only")
        self.mirror = mirror     # 'x' = flipped top/bottom, 'y' = flipped left/right (KiCad "mirror x" / "mirror y")
        self.text_left = False   # vertical 2-pin parts: put reference/value on the left side
        self.field_pos = {}      # {"Reference": (dx, dy)} explicit centred field positions (schematic mm, y down)
        self.x, self.y, self.rot = snap(at[0]), snap(at[1]), rotation
        self.sym = lib_symbol(lib_id)
        self.pins = sym_pins(self.sym)
        props = {c[1]: c[2] for c in self.sym if hd(c) == "property"}
        self.fields = {k: props.get(k, "") for k in ("Reference", "Value", "Footprint", "Datasheet", "Description")}
        self.fields["LCSC"] = props.get("LCSC", "")
        self.fields["Reference"] = ref
        if value is not None:
            self.fields["Value"] = value
        self.fields.update(fields or {})
        self.used = set()

    def pin(self, num):
        """Schematic position and outward direction (unit vector) of pin `num` of this unit."""
        cands = [p for p in self.pins[str(num)] if p["unit"] in (0, self.unit)]
        if not cands:
            raise KeyError(f"{self.ref}: pin {num} not in unit {self.unit}")
        p = cands[0]
        sy = -1 if self.mirror == "x" else 1
        sx = -1 if self.mirror == "y" else 1
        rx, ry = rot(sx * p["x"], sy * p["y"], self.rot)
        dx, dy = rot(sx * math.cos(math.radians(p["ang"] + 180)), sy * math.sin(math.radians(p["ang"] + 180)), self.rot)
        return (snap(self.x + rx), snap(self.y - ry)), (round(dx), round(-dy))

    def two_pin_axis(self):
        """'v' or 'h' for parts with exactly two pins (passives, diodes, fuses), else None."""
        nums = [n for n, lst in self.pins.items() if any(q["unit"] in (0, self.unit) for q in lst)]
        if len(nums) != 2 or self.ref.startswith("#"):
            return None
        (ax, ay), _ = self.pin(nums[0])
        (bx, by), _ = self.pin(nums[1])
        return "v" if ax == bx else "h" if ay == by else None

    def text_side(self):
        """Transistors: 'left' or 'right' = side opposite the gate/base pin; None for other parts."""
        if not re.match(r"^Q\d", self.ref):
            return None
        g = next((n for n, lst in self.pins.items() if lst[0]["name"] in ("G", "B")), None)
        if g is None:
            return None
        (gx, _), _ = self.pin(g)
        return "right" if gx < self.x else "left"

    def body_halfwidth(self):
        """Half-width (mm, schematic x) of the symbol artwork incl. half the stroke, after rotation. Capacitor
        plates reach 2.03 mm + stroke, a resistor body 1.02 mm: a fixed value put C texts on the plates (D92)."""
        best = 0.0

        def walk(n):
            nonlocal best
            if not isinstance(n, list) or not n:
                return
            kind = hd(n)
            if kind in ("rectangle", "polyline", "circle", "arc"):
                pts = []
                for c in n:
                    if hd(c) in ("start", "end", "mid", "center"):
                        pts.append((c[1], c[2]))
                    elif hd(c) == "pts":
                        pts += [(q[1], q[2]) for q in c[1:] if hd(q) == "xy"]
                r = next((c[1] for c in n if hd(c) == "radius"), 0)
                sw = next((w[1] for c in n if hd(c) == "stroke" for w in c[1:] if hd(w) == "width"), 0) or 0.254
                for x, y in pts:
                    best = max(best, abs(rot(x, y, self.rot)[0]) + r + sw / 2)
                return
            for c in n[1:]:
                walk(c)
        walk(self.sym)
        return best or 0.8

    def body_halfheight(self):
        """Half-height (mm, schematic y) of the symbol artwork after rotation, pins excluded (rotated 90 deg: the
        half-width of the part turned on its side)."""
        saved, self.rot = self.rot, (self.rot + 90) % 360
        try:
            return self.body_halfwidth()
        finally:
            self.rot = saved

    def side_edge(self, sgn):
        """Signed x offset of the outermost pin on that side (texts start just beyond it)."""
        xs = [self.pin(n)[0][0] - self.x for n, lst in self.pins.items() if any(q["unit"] in (0, self.unit) for q in lst)]
        if self.two_pin_axis() == "v":
            return sgn * self.body_halfwidth()
        return max(xs) if sgn > 0 else min(xs)

    def small_body(self):
        return self.lib_id.split(":")[-1] in ("R", "C", "C_Polarized", "L", "FerriteBead_Small")

    def sexp(self, paths):
        """paths: list of (sheet instance path, reference offset) - one entry per sheet instance."""
        mech = self.lib_id.split(":")[-1] in ("TestPoint", "MountingHole", "Fiducial")   # parts policy 9: no BOM/CPL
        node = [S("symbol"), [S("lib_id"), self.lib_id], [S("at"), self.x, self.y, self.rot]] +             ([[S("mirror"), S(self.mirror)]] if self.mirror else []) + [[S("unit"), self.unit],
                [S("body_style"), 1], [S("exclude_from_sim"), S("no")], [S("in_bom"), S("no" if mech else "yes")],
                [S("on_board"), S("yes")], [S("in_pos_files"), S("no" if mech else "yes")],
                [S("dnp"), S("yes" if self.dnp else "no")],
                [S("uuid"), U(f"{self.sheet.name}/{self.ref}/{self.unit}")]]
        libprops = {c[1]: c for c in self.sym if hd(c) == "property"}
        for k, v in self.fields.items():
            lp = libprops.get(k)
            if lp is not None:
                at = next(c for c in lp if hd(c) == "at")
                ox, oy = at[1], at[2]
                hidden = any(hd(c) == "hide" and c[1] == S("yes") for c in lp) or \
                    any(hd(c) == "effects" and any(hd(e) == "hide" for e in c) for c in lp)
            else:
                ox, oy, hidden = 0, 0, True
            if k in ("Footprint", "Datasheet", "Description", "LCSC"):
                hidden = True
            just = None
            fang = None
            two = self.two_pin_axis()
            side = self.text_side()
            cw = 1.22                 # stroke-font character pitch at 1.27 mm (measured in the plotted PDF, D92)
            if k in self.field_pos and self.field_pos[k] is None:
                px, py, hidden = 0, 0, True          # field hidden on purpose (e.g. the "TP" value of a test pad)
            elif k in self.field_pos:    # explicit placement (centred text), offsets in mm from the symbol origin
                px, py = self.field_pos[k][0], -self.field_pos[k][1]
            elif (two or side) and k in ("Reference", "Value") and not self.ref.startswith("#"):
                other = self.fields["Value"] if k == "Reference" else self.fields["Reference"]
                w = cw * len(str(v))
                if two == "h":           # horizontal body: reference above, value below, centred
                    # clear the artwork's own height (capacitor plates reach 2.16 mm): body + 0.5 gap + half the text,
                    # rounded up to the 1.27 grid; at least 2.54 (small bodies), 3.175 for the others (Phase D)
                    need = math.ceil((self.body_halfheight() + 0.5 + 0.64 + (1.9 if self.dnp else 0)) / 1.27) * 1.27
                    half = max(2.54 if self.small_body() else 3.175, need)
                    px, py = 0, (half if k == "Reference" else -half)
                else:                    # vertical body / transistor: both texts on one side, left-aligned look
                    sgn = -1 if (side == "left" or self.text_left) else 1
                    edge = self.side_edge(sgn)
                    gapx = 2.3 if side else (3.4 if self.dnp else 0.6)   # transistor circle / DNP cross width
                    if getattr(self, "text_vertical", False) and two == "v":
                        # baseline style (Phase D): both texts written vertically beside the body, two thin columns,
                        # so shunts can sit 7.62 mm apart
                        px = edge + sgn * (gapx + 0.64 + (0 if k == "Reference" else 2.03))
                        py = -getattr(self, "text_dy", 0)      # shift along the body (series pairs, long values)
                        fang = 90 if self.rot in (0, 180) else 0
                    else:
                        px = edge + sgn * (gapx + w / 2)
                        py = 1.27 if k == "Reference" else -1.27
            elif self.rot in (90, 270) and not self.ref.startswith("#"):
                px, py = {"Reference": (0, 3.81), "Value": (0, -3.81)}.get(k, (0, 0))
            else:
                px, py = rot(ox, oy, self.rot)
                if self.mirror == "y":
                    px = -px
                elif self.mirror == "x":
                    py = -py
                if lp is not None and self.rot == 0:   # keep the library's justification (KiCad mirrors it itself)
                    eff = next((c for c in lp if hd(c) == "effects"), [])
                    j = next((c for c in eff if hd(c) == "justify"), None)
                    just = " ".join(x.value() for x in j[1:]) if j else None
            node.append([S("property"), k, v, [S("at"), self.x + px, self.y - py,
                                                 fang if fang is not None else (90 if self.rot in (90, 270) else 0)]]
                        + ([[S("hide"), S("yes")]] if hidden else []) + [font(justify=just)])
        for num in self.pins:
            if any(p["unit"] in (0, self.unit) for p in self.pins[num]):
                node.append([S("pin"), num, [S("uuid"), U(f"{self.sheet.name}/{self.ref}/{self.unit}/pin{num}")]])
        proj = [S("project"), PROJECT]
        for path, off in paths:
            proj.append([S("path"), path, [S("reference"), shift_ref(self.ref, off)], [S("unit"), self.unit]])
        node.append([S("instances"), proj])
        return node


def shift_ref(ref, off):
    """R101 + 100 -> R201 (CH2 = CH1 + 100, section 13.3)."""
    if not off:
        return ref
    m = re.match(r"^(\D+)(\d+)$", ref)
    return f"{m.group(1)}{int(m.group(2)) + off}" if m else ref


# Title-block revision of every sheet: CheckOne rev 1.1 from the first change (CLAUDE.md O8, principle 8)
REV, REV_DATE = "1.1", "2026-11-16"


class Sheet:
    def __init__(self, name, filename, title, paper="A3", rev=REV, date=REV_DATE, comments=(),
                 instances=None):
        """instances: None for a single-instance sheet, or a list of (instance name, reference offset,
        {hierarchical label -> root global net}) for a multi-instance sheet (D15)."""
        self.name, self.filename, self.title, self.paper = name, filename, title, paper
        self.rev, self.date, self.comments = rev, date, comments
        self.parts, self.items, self.lib_ids = [], [], set()
        self.segs, self.anchors, self.taps = [], [], set()
        self.pending = []        # labels placed at sexp() time, column-aligned (_emit_labels)
        self.npwr = 0
        self.tag = "".join(w[:3] for w in name.split("_")).upper()   # unique per sheet (Power_Battery -> POWBAT)
        self.uuid = U(f"sheet/{name}")
        self.instances = instances or [(name, 0, {})]
        self.hier = {}           # hierarchical label name -> shape
        self.ports_at = None     # top-left of the SHEET PORTS block (mm); set by the sheet module

    def merge(self, other, dx, dy):
        """Append everything drawn on `other` to this sheet, translated by (dx, dy) mm (grid multiples).
        Used to put two drawings on one page (Phase 8c: battery + rails, HMI + connectors)."""
        dx, dy = snap(dx), snap(dy)
        mv = lambda p: (snap(p[0] + dx), snap(p[1] + dy))
        for p in other.parts:
            p.x, p.y = snap(p.x + dx), snap(p.y + dy)
            self.parts.append(p)
        self.segs += [(mv(a), mv(b), k) for a, b, k in other.segs]
        self.anchors += [mv(a) for a in other.anchors]
        self.pending += [(mv(pt), net, ang, key) for pt, net, ang, key in other.pending]
        self.taps |= {mv(t) for t in other.taps}

        def shift(node):
            if isinstance(node, list) and node:
                if hd(node) in ("at", "xy") and len(node) >= 3:
                    node[1], node[2] = snap(node[1] + dx), snap(node[2] + dy)
                    return
                for c in node:
                    shift(c)
        for it in other.items:
            shift(it)
            self.items.append(it)
        self.lib_ids |= other.lib_ids
        for k, v in other.hier.items():
            self.hier.setdefault(k, v)

    def rename(self, name, filename, title, comments=None, paper=None):
        self.name, self.filename, self.title = name, filename, title
        self.uuid = U(f"sheet/{name}")
        self.instances = [(name, 0, {})]
        if comments is not None:
            self.comments = comments
        if paper:
            self.paper = paper

    def inst_uuid(self, inst):
        return self.uuid if len(self.instances) == 1 and inst == self.name else U(f"sheet/{self.name}/{inst}")

    # ---------- placement ----------
    def place(self, lib_id, ref, at, **kw):
        p = Part(self, lib_id, ref, at, **kw)
        self.parts.append(p)
        self.lib_ids.add(lib_id)
        return p

    def _wire(self, a, b, key, fine=False):
        sn = snap_fine if fine else snap        # fine: label wire ends on the 25 mil connection grid (D100)
        a, b = (sn(a[0]), sn(a[1])), (sn(b[0]), sn(b[1]))
        if a == b:
            return
        if a[0] != b[0] and a[1] != b[1]:
            raise ValueError(f"{self.name}: diagonal wire {a} -> {b} ({key})")
        self.segs.append((a, b, key))

    # ---------- free wiring (Phase 8c: passives wired to their ICs, no labels) ----------
    def place_at(self, lib_id, ref, pin, point, rotation=0, **kw):
        """Place a part so that its pin `pin` lands exactly on `point`."""
        p = Part(self, lib_id, ref, (0, 0), rotation=rotation, **kw)
        (px, py), _ = p.pin(pin)
        p.x, p.y = snap(point[0] - px), snap(point[1] - py)
        p.used.add(str(pin))
        self.parts.append(p)
        self.lib_ids.add(lib_id)
        return p

    def two_pin(self, lib_id, ref, start, direction, pin1="1", **kw):
        """Place a 2-pin part with pin `pin1` on `start`, body extending in direction
        'right' | 'left' | 'down' | 'up'. Returns (part, far pin point)."""
        want = {"right": (1, 0), "left": (-1, 0), "down": (0, 1), "up": (0, -1)}[direction]
        for r in (0, 90, 180, 270):
            t = Part(self, lib_id, ref, (0, 0), rotation=r, **kw)
            other = next(n for n, lst in t.pins.items() if n != pin1 and any(q["unit"] in (0, t.unit) for q in lst))
            (ax, ay), _ = t.pin(pin1)
            (bx, by), _ = t.pin(other)
            d = (bx - ax, by - ay)
            if (d[0] == 0 or (d[0] > 0) == (want[0] > 0)) and (d[1] == 0 or (d[1] > 0) == (want[1] > 0)) and \
                    (abs(d[0]) > 0) == (want[0] != 0) and (abs(d[1]) > 0) == (want[1] != 0):
                p = self.place_at(lib_id, ref, pin1, start, rotation=r, **kw)
                return p, p.pin(other)[0]
        raise ValueError(f"{ref}: no rotation gives direction {direction}")

    def pt(self, part, num):
        part.used.add(str(num))
        return part.pin(num)[0]

    def wire(self, *pts, key=None):
        """Polyline wire through the points (orthogonal segments only)."""
        k = key or f"{self.name}/w/{pts}"
        for i, (a, b) in enumerate(zip(pts, pts[1:])):
            self._wire(a, b, f"{k}/{i}")

    def route(self, a, b, via="hv", key=None):
        """Orthogonal route a -> b: 'hv' (horizontal first), 'vh', or ('x', x) / ('y', y) dog-leg."""
        if a[0] == b[0] or a[1] == b[1]:
            self.wire(a, b, key=key)
        elif via == "hv":
            self.wire(a, (b[0], a[1]), b, key=key)
        elif via == "vh":
            self.wire(a, (a[0], b[1]), b, key=key)
        elif via[0] == "x":
            self.wire(a, (via[1], a[1]), (via[1], b[1]), b, key=key)
        elif via[0] == "y":
            self.wire(a, (a[0], via[1]), (b[0], via[1]), b, key=key)

    def conn(self, pa, na, pb, nb, via="hv"):
        """Wire pin na of part pa to pin nb of part pb."""
        self.route(self.pt(pa, na), self.pt(pb, nb), via, key=f"{self.name}/c/{pa.ref}.{na}-{pb.ref}.{nb}")

    def lab(self, point, net, direction="right", kind="local", shape="bidirectional"):
        """Label anchored on a wire end at `point`; direction = side the text extends to."""
        point = (snap(point[0]), snap(point[1]))
        ang = {"right": 0, "left": 180, "up": 90, "down": 270}[direction]
        just = {0: "left", 180: "right", 90: "left", 270: "right"}[ang]
        key = f"{self.name}/lab/{net}/{point}"
        if kind != "local":                  # inter-sheet net: local label here + hierarchical port (SHEET PORTS)
            self.hier.setdefault(net, shape)
        self._label_on_wire(point, net, ang, key)

    def _label_on_wire(self, point, net, ang, key):
        """Local label whose text sits on a wire (EA01 style): the wire is extended from `point` under the whole
        text, and the label is anchored at the far end with its text running back toward `point`. The label is
        emitted at sexp() time so that a column of labels can share one far end (_emit_labels)."""
        self.pending.append(((snap(point[0]), snap(point[1])), net, ang, key))
        d = {0: (1, 0), 180: (-1, 0), 90: (0, -1), 270: (0, 1)}[ang]
        return (snap(point[0] + d[0] * label_len(net)), snap(point[1] + d[1] * label_len(net)))

    def _emit_labels(self):
        """Inner-edge alignment: every label of a column starts its text at the same distance (LABEL_GAP) from the
        point where it leaves the pin / lane, whatever its length. The wire runs from that point under the whole
        text and the label is anchored at the far end (EA01 style); with a proportional font the far end is off the
        1.27 mm grid, so it is snapped to the project's 25 mil connection grid (D100): alignment error <= 0.32 mm."""
        d = {0: (1, 0), 180: (-1, 0), 90: (0, -1), 270: (0, 1)}
        for point, net, ang, key in self.pending:
            L = label_wire_fine(net)
            end = (snap_fine(point[0] + d[ang][0] * L), snap_fine(point[1] + d[ang][1] * L))
            self._wire(point, end, key + "/under", fine=True)
            self.anchors.append(end)
            back = (ang + 180) % 360
            just = {0: "left", 180: "right", 90: "left", 270: "right"}[back]
            self.items.append([S("label"), net, [S("at"), end[0], end[1], back], [S("fields_autoplaced"), S("yes")],
                               font(justify=f"{just} bottom"), [S("uuid"), U(key)]])
        self.pending = []

    def pwr(self, point, net, flip=None):
        """Power symbol whose pin sits on `point`. Negative rails are drawn pointing down (flip)."""
        lib_id = f"power:{net}" if net in KICAD_POWER else f"{PROJECT}:{net}"
        point = (snap(point[0]), snap(point[1]))
        self.taps.add(point)                 # a rail symbol on a lane is placed on the wire on purpose (split + junction)
        if flip is None:
            flip = net.startswith("-") and lib_id.startswith(PROJECT)
        self.npwr += 1
        p = Part(self, lib_id, f"#PWR{self.tag}{self.npwr:03d}", point, rotation=180 if flip else 0, value=net)
        self.parts.append(p)
        self.lib_ids.add(lib_id)

    def nc_at(self, part, num):
        self.nc(part, num)

    D = {"right": (1, 0), "left": (-1, 0), "down": (0, 1), "up": (0, -1)}

    def go(self, point, direction, dist):
        dx, dy = self.D[direction]
        return (snap(point[0] + dx * dist), snap(point[1] + dy * dist))

    def drop(self, point, lib_id, ref, direction="down", gap=2.54, end=None, pin1="1", **kw):
        """Branch from a wire node: short wire `gap` long, then a 2-pin part body in `direction`.
        end = power net name (symbol at the far pin) or None. Returns (part, far pin point)."""
        a = self.go(point, direction, gap)
        if gap:
            self.wire(point, a, key=f"{self.name}/drop/{ref}")
        else:
            self.taps.add((snap(point[0]), snap(point[1])))       # part pin placed on a wire on purpose
        p, far = self.two_pin(lib_id, ref, a, direction, pin1=pin1, **kw)
        p.used.update(n for n, lst in p.pins.items() if any(q["unit"] in (0, p.unit) for q in lst))
        if end:
            self.pwr(far, end)
        return p, far

    def span(self, a, b, lib_id, ref, pin1="1", **kw):
        """2-pin part centred between collinear points a and b (pin1 toward a), wired to both."""
        if a[0] == b[0]:
            direction = "down" if b[1] > a[1] else "up"
            length = abs(b[1] - a[1])
        elif a[1] == b[1]:
            direction = "right" if b[0] > a[0] else "left"
            length = abs(b[0] - a[0])
        else:
            raise ValueError(f"{ref}: span points not aligned {a} {b}")
        t = Part(self, lib_id, ref, (0, 0), **kw)
        nums = [n for n, lst in t.pins.items() if any(q["unit"] in (0, t.unit) for q in lst)]   # this unit only
        (ax, ay), _ = t.pin(nums[0])
        (bx, by), _ = t.pin(nums[1])
        body = abs(ax - bx) + abs(ay - by)
        gap = snap((length - body) / 2)
        if gap < 0:
            raise ValueError(f"{ref}: span {length} shorter than the part ({body})")
        p, far = self.drop(a, lib_id, ref, direction, gap=gap, pin1=pin1, **kw)
        self.wire(far, b, key=f"{self.name}/span/{ref}")
        return p

    def chain(self, point, direction, items, gap=2.54):
        """Series string from `point`: items = [(lib_id, ref, kwargs)] each placed after a `gap` wire.
        Returns (parts, end point)."""
        parts, cur = [], point
        for lib_id, ref, kw in items:
            p, cur = self.drop(cur, lib_id, ref, direction, gap=gap, **kw)
            parts.append(p)
        return parts, cur

    def _ports_block(self):
        """SHEET PORTS block (Celso's VibraOne EA01 style): one hierarchical label per inter-sheet net, wired to
        the local label of the same name used inside the sheet."""
        if not self.hier:
            return []
        if self.ports_at is None:
            raise ValueError(f"{self.name}: sheet has ports but no ports_at position")
        x0, y0 = snap(self.ports_at[0]), snap(self.ports_at[1])
        names = sorted(self.hier)
        hw, wl = self._ports_dims()
        out = [[S("text_box"), "SHEET PORTS", [S("exclude_from_sim"), S("no")], [S("at"), x0, y0, 0],
                [S("size"), hw + wl, 5.08], [S("margins"), 0.9525, 0.9525, 0.9525, 0.9525],
                [S("stroke"), [S("width"), 0], [S("type"), S("dash")], [S("color"), 204, 102, 0, 1]],
                [S("fill"), [S("type"), S("none")]],
                [S("effects"), [S("font"), [S("size"), 1.27, 1.27], [S("color"), 204, 102, 0, 1]],
                 [S("justify"), S("left"), S("top")]], [S("uuid"), U(f"{self.name}/ports/title")]]]
        for i, n in enumerate(names):
            y = snap(y0 + 7.62 + i * 2.54)
            a, b = (snap(x0 + hw), y), (snap(x0 + hw + wl), y)        # hierarchical label text lies left of a
            self._wire(a, b, f"{self.name}/ports/w/{n}")
            self.anchors += [a, b]
            out.append([S("hierarchical_label"), n, [S("shape"), S(self.hier[n])], [S("at"), a[0], a[1], 180],
                        [S("fields_autoplaced"), S("yes")], font(justify="right"), [S("uuid"), U(f"{self.name}/ports/h/{n}")]])
            out.append([S("label"), n, [S("at"), b[0], b[1], 180], [S("fields_autoplaced"), S("yes")],
                        font(justify="right bottom"), [S("uuid"), U(f"{self.name}/ports/l/{n}")]])
        return out

    def _ports_dims(self):
        """(hierarchical-label column width, wire length) of the SHEET PORTS block, from the longest name."""
        n = max(len(n) for n in self.hier)
        return snap(n * 1.1 + 5.08), snap(n * 1.1 + 6.0)

    def ports_size(self):
        """(width, height) of the SHEET PORTS block in mm, for layout."""
        if not self.hier:
            return 0, 0
        hw, wl = self._ports_dims()
        return hw + wl, 7.62 + len(self.hier) * 2.54

    def _finish_wires(self):
        """Split segments at T points, add junctions where 3+ connections meet, and refuse pins or
        label anchors lying inside a wire (they would connect silently)."""
        segs = list(self.segs)
        pins = []
        for p in self.parts:
            for num, lst in p.pins.items():
                if any(q["unit"] in (0, p.unit) for q in lst):
                    pins.append((p.pin(num)[0], f"{p.ref}.{num}"))
        ends = {e for a, b, _ in segs for e in (a, b)}

        def inside(pt, a, b):
            if a[0] == b[0] == pt[0]:
                return min(a[1], b[1]) < pt[1] < max(a[1], b[1])
            if a[1] == b[1] == pt[1]:
                return min(a[0], b[0]) < pt[0] < max(a[0], b[0])
            return False
        for (pt, name) in pins:
            for a, b, k in segs:
                if inside(pt, a, b) and pt not in ends and pt not in self.taps:
                    raise ValueError(f"{self.name}: pin {name} at {pt} lies inside wire {a}-{b} ({k})")
        for p in self.parts:                 # no wire may run along the body of a 2-pin part (it would short it)
            if p.ref.startswith("#") or not p.two_pin_axis():
                continue
            nums = [n for n, lst in p.pins.items() if any(q["unit"] in (0, p.unit) for q in lst)]
            (ax, ay), _ = p.pin(nums[0])
            (bx, by), _ = p.pin(nums[1])
            mid = (snap((ax + bx) / 2), snap((ay + by) / 2))
            for a, b, k in segs:
                if inside(mid, a, b):
                    raise ValueError(f"{self.name}: wire {a}-{b} runs through the body of {p.ref} ({k})")
        for pt in self.anchors:
            for a, b, k in segs:
                if inside(pt, a, b) and pt not in ends:
                    raise ValueError(f"{self.name}: label anchor {pt} lies inside wire {a}-{b} ({k})")
        # split at T points (another segment's end on this segment's interior)
        changed = True
        while changed:
            changed = False
            ends = {e for a, b, _ in segs for e in (a, b)} | self.taps
            for i, (a, b, k) in enumerate(segs):
                hit = next((e for e in ends if inside(e, a, b)), None)
                if hit:
                    segs[i:i + 1] = [(a, hit, k + "/s1"), (hit, b, k + "/s2")]
                    changed = True
                    break
        # overlapping collinear segments are a drawing error
        seen = set()
        out = []
        for a, b, k in segs:
            key = tuple(sorted((a, b)))
            if key in seen:
                continue
            seen.add(key)
            out.append((a, b, k))
        deg = {}
        for a, b, _ in out:
            for e in (a, b):
                deg[e] = deg.get(e, 0) + 1
        pin_at = {}
        for pt, _ in pins:
            pin_at[pt] = pin_at.get(pt, 0) + 1
        items = []
        for a, b, k in out:
            items.append([S("wire"), [S("pts"), [S("xy"), a[0], a[1]], [S("xy"), b[0], b[1]]],
                          [S("stroke"), [S("width"), 0], [S("type"), S("default")]], [S("uuid"), U(k)]])
        for e, n in deg.items():
            if n + min(pin_at.get(e, 0), 1) >= 3:
                items.append([S("junction"), [S("at"), e[0], e[1]], [S("diameter"), 0], [S("color"), 0, 0, 0, 0],
                              [S("uuid"), U(f"{self.name}/junction/{e}")]])
        return items

    def _end(self, part, num, stub):
        (x, y), (dx, dy) = part.pin(num)
        part.used.add(str(num))
        return (x, y), (snap(x + dx * stub), snap(y + dy * stub)), (dx, dy)

    def label(self, part, num, net, kind="local", shape="bidirectional", stub=STUB):
        """kind: local | global | hier."""
        start, end, (dx, dy) = self._end(part, num, stub)
        key = f"{self.name}/{part.ref}/{part.unit}/{num}/{kind}"
        self._wire(start, end, key + "/w")
        ang = {(1, 0): 0, (-1, 0): 180, (0, -1): 90, (0, 1): 270}[(dx, dy)]
        just = {0: "left", 180: "right", 90: "left", 270: "right"}[ang]
        if kind in ("local", "global"):
            if kind == "global":
                self.hier.setdefault(net, shape)
            return self._label_on_wire(end, net, ang, key)
        self.anchors.append(end)
        if kind == "hier":
            self.hier[net] = shape
            self.items.append([S("hierarchical_label"), net, [S("shape"), S(shape)], [S("at"), end[0], end[1], ang],
                               [S("fields_autoplaced"), S("yes")], font(justify=just), [S("uuid"), U(key)]])
        return end

    def power(self, part, num, net, stub=0.0):
        """Power symbol (project or KiCad power lib) at the pin end (optionally after a stub)."""
        start, end, (dx, dy) = self._end(part, num, stub)
        self._wire(start, end, f"{self.name}/{part.ref}/{part.unit}/{num}/pw")
        lib_id = f"power:{net}" if net in KICAD_POWER else f"{PROJECT}:{net}"
        # orient the symbol body away from the part (Phase D): rail symbols point up and ground symbols down in the
        # library; a rail on a downward pin is turned over, and so is a ground on an upward pin (inverted ground)
        ground = net in GROUND_NETS
        turn = (dy > 0 and not ground) or (dy < 0 and ground)
        self.npwr += 1
        ref = f"#PWR{self.tag}{self.npwr:03d}"
        p = Part(self, lib_id, ref, end, rotation=180 if turn else 0, value=net)
        self.parts.append(p)
        self.lib_ids.add(lib_id)
        return end

    def power_bus(self, part, nums, net, stub=5.08):
        """Several pins on the same side to one rail: stubs, a bar joining the stub ends (with
        junctions) and a single power symbol at the last end."""
        raw = [self._end(part, n, stub) for n in nums]
        (dx, dy) = raw[0][2]
        # put every stub end on one common line (pins can sit a few 0.01 mm off-grid): no tiny bar
        # segments, so no four-way junctions where the bar meets a stub
        if dy:
            line = snap((max if dy > 0 else min)(e[1] for _, e, _ in raw))
            ends = [(s_[0], line) for s_, _, _ in raw]
        else:
            line = snap((max if dx > 0 else min)(e[0] for _, e, _ in raw))
            ends = [(line, s_[1]) for s_, _, _ in raw]
        drawn = set()
        for n, (start, _, _), end in zip(nums, raw, ends):
            if (start, end) not in drawn:        # stacked pins share one stub (no overlapping wires)
                self._wire(start, end, f"{self.name}/{part.ref}/{part.unit}/{n}/pb")
                drawn.add((start, end))
            part.used.add(str(n))
        ends = sorted(set(ends), key=lambda e: (e[1], e[0]))
        for a, b in zip(ends, ends[1:]):
            self._wire(a, b, f"{self.name}/{part.ref}/bus/{a}/{b}")
        tip = ends[-1] if (net == "GND" or net.startswith("-")) else ends[0]
        lib_id = f"power:{net}" if net in KICAD_POWER else f"{PROJECT}:{net}"
        self.npwr += 1
        p = Part(self, lib_id, f"#PWR{self.tag}{self.npwr:03d}", tip, rotation=0, value=net)
        self.parts.append(p)
        self.lib_ids.add(lib_id)

    def nc(self, part, num):
        (x, y), _ = part.pin(num)
        part.used.add(str(num))
        self.items.append([S("no_connect"), [S("at"), x, y], [S("uuid"), U(f"{self.name}/{part.ref}/{part.unit}/{num}/nc")]])

    def text(self, txt, at, size=1.27, key=None, bold=False, color=None):
        f = [S("font"), [S("size"), size, size]] + ([[S("bold"), S("yes")]] if bold else []) + \
            ([[S("color")] + list(color) + [1]] if color else [])
        self.items.append([S("text"), txt, [S("exclude_from_sim"), S("no")], [S("at"), at[0], at[1], 0],
                           [S("effects"), f, [S("justify"), S("left"), S("top")]], [S("uuid"), U(key or f"{self.name}/t/{txt[:40]}/{at}")]])

    def note(self, txt, at, size=(80, 20), style="note", key=None):
        """Text box. style: note (black border), calc (orange border, black text), warn (red bold 1.778)."""
        stroke_col = {"note": (0, 0, 0), "calc": (204, 102, 0), "warn": (255, 0, 0)}[style]
        fsize = 1.778 if style == "warn" else 1.27
        f = [S("font"), [S("size"), fsize, fsize]] + ([[S("bold"), S("yes")], [S("color"), 255, 0, 0, 1]] if style == "warn" else [])
        self.items.append([S("text_box"), txt, [S("exclude_from_sim"), S("no")], [S("at"), at[0], at[1], 0],
                           [S("size"), size[0], size[1]], [S("margins"), 0.9525, 0.9525, 0.9525, 0.9525],
                           [S("stroke"), [S("width"), 0], [S("type"), S("solid")], [S("color")] + list(stroke_col) + [1]],
                           [S("fill"), [S("type"), S("none")]], [S("effects"), f, [S("justify"), S("left"), S("top")]],
                           [S("uuid"), U(key or f"{self.name}/note/{txt[:40]}")]])

    # ---------- output ----------
    def check_all_pins_used(self):
        missing = []
        for p in self.parts:
            if p.ref.startswith("#"):
                continue
            for num, lst in p.pins.items():
                if any(q["unit"] in (0, p.unit) for q in lst) and num not in p.used:
                    missing.append(f"{p.ref}.{num}")
        return missing

    def lib_symbols(self):
        out = [S("lib_symbols")]
        for lib_id in sorted(self.lib_ids):
            sym = lib_symbol(lib_id)
            sym[1] = lib_id
            out.append(sym)
        return out

    def sexp(self, root_uuid):
        tb = [S("title_block"), [S("title"), self.title], [S("date"), self.date], [S("rev"), self.rev],
              [S("company"), COMPANY]] + [[S("comment"), i + 1, c] for i, c in enumerate(self.comments)]
        tree = [S("kicad_sch"), [S("version"), 20260306], [S("generator"), "eeschema"],
                [S("generator_version"), "10.0"], [S("uuid"), self.uuid], [S("paper"), self.paper], tb,
                self.lib_symbols()]
        self._emit_labels()
        tree += self.items + self._ports_block() + self._finish_wires()
        paths = [(f"/{root_uuid}/{self.inst_uuid(inst)}", off) for inst, off, _ in self.instances]
        for p in self.parts:
            tree.append(p.sexp(paths))
        tree.append([S("embedded_fonts"), S("no")])
        return tree


def write(tree, path):
    txt = sexpdata.dumps(tree)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(txt + "\n")


def root_sheet(sheets, title, comments=(), notes=(), lines=(), texts=(), paper="A3", ymax=220, gap=10.16):
    """Root schematic with one sheet symbol per sub-sheet; every sheet port is a sheet pin wired to a local label
    of the same name (VibraOne EA01 style), so inter-sheet nets are visible on the root."""
    ru = U("root")
    tree = [S("kicad_sch"), [S("version"), 20260306], [S("generator"), "eeschema"], [S("generator_version"), "10.0"],
            [S("uuid"), ru], [S("paper"), paper],
            [S("title_block"), [S("title"), title], [S("date"), REV_DATE], [S("rev"), REV], [S("company"), COMPANY]]
            + [[S("comment"), i + 1, c] for i, c in enumerate(comments)], [S("lib_symbols")]]
    boxes = [(sh, inst, nets) for sh in sheets for inst, _, nets in sh.instances]
    x, y, page, col = 63.5, 30.48, 2, 0
    limits = ymax if isinstance(ymax, (list, tuple)) else [ymax] * 8    # per-column limit (A4: title block)
    for sh, inst, nets in boxes:
        pins = sorted(sh.hier)
        h = max(15.24, (len(pins) + 1) * 2.54)
        if y + h > limits[col]:
            x, y, col = x + 101.6, 30.48, col + 1
        su = sh.inst_uuid(inst)
        node = [S("sheet"), [S("at"), x, y], [S("size"), 50.8, h], [S("exclude_from_sim"), S("no")],
                [S("in_bom"), S("yes")], [S("on_board"), S("yes")], [S("dnp"), S("no")],
                [S("fields_autoplaced"), S("yes")], [S("stroke"), [S("width"), 0.1524], [S("type"), S("solid")]],
                [S("fill"), [S("color"), 0, 0, 0, 0.0]], [S("uuid"), su],
                [S("property"), "Sheetname", inst, [S("at"), x, y - 0.7, 0], font(justify="left bottom")],
                [S("property"), "Sheetfile", sh.filename, [S("at"), x, y + h + 0.6, 0], font(justify="left top", hide=True)]]
        for k, name in enumerate(pins):
            py_ = snap(y + (k + 1) * 2.54)
            node.append([S("pin"), name, S(sh.hier[name]), [S("at"), x, py_, 180], font(justify="left"),
                         [S("uuid"), U(f"root/{inst}/pin/{name}")]])
            gnet = nets.get(name, name)
            end = (snap_fine(x - 2.54 - label_wire_fine(gnet)), py_)   # text ends 2.54 + gap before the pin (D100)
            tree.append([S("wire"), [S("pts"), [S("xy"), x, py_], [S("xy"), end[0], end[1]]],
                         [S("stroke"), [S("width"), 0], [S("type"), S("default")]], [S("uuid"), U(f"root/{inst}/w/{name}")]])
            tree.append([S("label"), gnet, [S("at"), end[0], end[1], 0], [S("fields_autoplaced"), S("yes")],
                         font(justify="left bottom"), [S("uuid"), U(f"root/{inst}/gl/{name}")]])
        node.append([S("instances"), [S("project"), PROJECT, [S("path"), f"/{ru}", [S("page"), str(page)]]]])
        tree.append(node)
        page += 1
        y = snap(y + h + gap)
    for n_, (txt, at, size) in enumerate(notes):
        tree.append([S("text_box"), txt, [S("exclude_from_sim"), S("no")], [S("at"), at[0], at[1], 0],
                     [S("size"), size[0], size[1]], [S("margins"), 0.9525, 0.9525, 0.9525, 0.9525],
                     [S("stroke"), [S("width"), 0], [S("type"), S("solid")], [S("color"), 0, 0, 0, 1]],
                     [S("fill"), [S("type"), S("none")]], [S("effects"), [S("font"), [S("size"), 1.27, 1.27]],
                                                         [S("justify"), S("left"), S("top")]],
                     [S("uuid"), U(f"root/note/{n_}")]])
    for i, pts in enumerate(lines):
        tree.append([S("polyline"), [S("pts")] + [[S("xy"), x_, y_] for x_, y_ in pts],
                     [S("stroke"), [S("width"), 0.254], [S("type"), S("default")]], [S("fill"), [S("type"), S("none")]],
                     [S("uuid"), U(f"root/line/{i}")]])
    for i, (txt, at, size) in enumerate(texts):
        tree.append([S("text"), txt, [S("exclude_from_sim"), S("no")], [S("at"), at[0], at[1], 0],
                     [S("effects"), [S("font"), [S("size"), size, size]], [S("justify"), S("left"), S("bottom")]],
                     [S("uuid"), U(f"root/text/{i}")]])
    tree.append([S("sheet_instances"), [S("path"), "/", [S("page"), "1"]]])
    tree.append([S("embedded_fonts"), S("no")])
    return ru, tree
