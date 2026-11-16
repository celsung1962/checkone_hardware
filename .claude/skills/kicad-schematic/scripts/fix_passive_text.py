#!/usr/bin/env python3
"""
Sweep every resistor and capacitor of a KiCad schematic and fix reference / value text that overlaps a symbol
(its own body, another part's body or pins), a wire, a label, a no-connect, a junction or another text.

For each visible Reference / Value field of every R* / C* symbol (prefixes configurable), the script:
  1. computes the text box (stroke-font advance of each character from kicad_text.py, height 1.15 x size) and the symbol
     body box (library artwork incl. half the stroke width, after rotation / mirror; a DNP part's cross is wider);
  2. if the text hits anything, tries the conventional positions in order and keeps the first clear one:
       vertical body   : both texts beside the body, right side then left side (reference above value),
                         then shifted up / down by one and two half-grid steps;
       horizontal body : reference above and value below, then both above, then both below,
                         then shifted left / right;
     texts are written centred (no justify) and horizontal, so rotation and mirroring cannot flip them;
  3. reports what it fixed and what it could not fix (those need a manual move or more room on the sheet).

Modes:
  --check  (default) report only; exit 1 if any R/C text overlaps something.
  --apply  rewrite the .kicad_sch files in place (only the (at ...) of the moved fields, their justify and the
           symbol's fields_autoplaced flag change; everything else is byte-identical). Back up / commit first.

If the schematic is produced by a generator script, do NOT use --apply: run --check, fix the placement rule in
the generator, regenerate. --apply is for hand-drawn schematics.

Always confirm with the plotted-PDF drawing check (scripts/check_drawing.py) and a visual review: this script
uses approximate text metrics and boxes, the PDF check sees what KiCad really draws.

Usage:
    python3 fix_passive_text.py hardware/<project>.kicad_sch [more.kicad_sch ...] [--apply]
           [--prefixes R,C] [--verbose]
    (a directory argument means every *.kicad_sch in it, backups excluded)
"""
import argparse, glob, math, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kicad_text import text_width, HEIGHT  # noqa: E402  (proportional stroke-font widths)
GAP = 0.6             # clearance between a text box and the body (mm)
DNP_GROW = 1.4        # extra half-width of the DNP cross beyond the body (mm)
STEP = 1.27           # shift step for alternative positions (mm)


# ----------------------------------------------------------------------------- s-expression with source spans
class Node(list):
    """A parsed list; .start/.end are the character offsets of '(' and ')' + 1 in the source text."""
    start = end = 0


def parse(text):
    tok = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+')
    stack, root = [], Node()
    for m in tok.finditer(text):
        t = m.group(0)
        if t == "(":
            n = Node(); n.start = m.start(); stack.append(n)
        elif t == ")":
            n = stack.pop(); n.end = m.end()
            (stack[-1] if stack else root).append(n)
        else:
            v = t[1:-1].replace('\\"', '"') if t.startswith('"') else t
            (stack[-1] if stack else root).append(v)
    return root


def head(n):
    return n[0] if isinstance(n, list) and n and isinstance(n[0], str) else None


def kids(n, name):
    return [c for c in n if head(c) == name]


def kid(n, name):
    k = kids(n, name)
    return k[0] if k else None


def num(v):
    return float(v)


# ----------------------------------------------------------------------------- geometry
def xform(x, y, rot, mirror):
    """Library point (y up) -> sheet offset (y down): rotate CCW by rot, then mirror, then flip y."""
    a = math.radians(rot)
    px, py = x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)
    if mirror == "y":
        px = -px
    elif mirror == "x":
        py = -py
    return px, -py


def box_of(points, grow=0.0):
    xs = [p[0] for p in points]; ys = [p[1] for p in points]
    return (min(xs) - grow, min(ys) - grow, max(xs) + grow, max(ys) + grow)


def hit(a, b):
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def seg_hits_box(p, q, b):
    """Liang-Barsky: segment p-q against box b=(x0,y0,x1,y1)."""
    x0, y0, dx, dy = p[0], p[1], q[0] - p[0], q[1] - p[1]
    t0, t1 = 0.0, 1.0
    for pp, qq in ((-dx, x0 - b[0]), (dx, b[2] - x0), (-dy, y0 - b[1]), (dy, b[3] - y0)):
        if pp == 0:
            if qq < 0:
                return False
        else:
            t = qq / pp
            if pp < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
            if t0 > t1:
                return False
    return True


def text_box(cx, cy, text, size, vertical=False, just=("center", "center")):
    w, h = max(text_width(text, size), 0.6), HEIGHT * size
    if vertical:
        w, h = h, w
    hx, vy = just
    x0 = cx - w / 2 if hx == "center" else (cx if hx == "left" else cx - w)
    y0 = cy - h / 2 if vy == "center" else (cy if vy == "top" else cy - h)
    if vertical:          # justification of rotated text is not modelled: assume centred
        x0, y0 = cx - w / 2, cy - h / 2
    return (x0, y0, x0 + w, y0 + h)


# ----------------------------------------------------------------------------- library symbols
class LibSym:
    def __init__(self, node):
        self.pts, self.pins = [], []
        self._walk(node)

    def _walk(self, n):
        for c in n:
            if not isinstance(c, list):
                continue
            h = head(c)
            if h in ("rectangle", "polyline", "circle", "arc", "bezier"):
                sw = 0.254
                st = kid(c, "stroke")
                if st is not None and kid(st, "width") is not None:
                    sw = max(num(kid(st, "width")[1]), 0.1524)
                pts = []
                for k in c:
                    if head(k) in ("start", "end", "mid", "center"):
                        pts.append((num(k[1]), num(k[2])))
                    elif head(k) == "pts":
                        pts += [(num(q[1]), num(q[2])) for q in k if head(q) == "xy"]
                r = num(kid(c, "radius")[1]) if kid(c, "radius") is not None else 0.0
                if h == "circle" and pts:
                    cx, cy = pts[0]; pts = [(cx - r, cy - r), (cx + r, cy + r)]
                for x, y in pts:
                    for dx in (-sw / 2, sw / 2):
                        for dy in (-sw / 2, sw / 2):
                            self.pts.append((x + dx, y + dy))
            elif h == "pin":
                at = kid(c, "at"); ln = kid(c, "length")
                L = num(ln[1]) if ln is not None else 2.54
                x, y, a = num(at[1]), num(at[2]), num(at[3]) if len(at) > 3 else 0.0
                e = (x + L * math.cos(math.radians(a)), y + L * math.sin(math.radians(a)))
                self.pins.append(((x, y), e))
            elif h == "symbol":
                self._walk(c)


# ----------------------------------------------------------------------------- one sheet
class Sheet:
    def __init__(self, path):
        self.path = path
        self.text = open(path, encoding="utf-8").read()
        self.root = parse(self.text)[0]
        libs = kid(self.root, "lib_symbols")
        self.lib = {c[1]: LibSym(c) for c in (libs or []) if head(c) == "symbol"}
        self.syms, self.obst_segs, self.obst_boxes, self.texts = [], [], [], []
        paper = kid(self.root, "paper")
        dims = {"A4": (297, 210), "A3": (420, 297), "A2": (594, 420), "A1": (841, 594), "A0": (1189, 841),
                "A": (279.4, 215.9), "B": (431.8, 279.4), "C": (558.8, 431.8), "D": (863.6, 558.8)}
        w, h = dims.get(paper[1] if paper else "A4", (297, 210))
        if paper is not None and len(paper) > 2 and paper[2] == "portrait":
            w, h = h, w
        self.frame = (12.0, 12.0, w - 12.0, h - 12.0)
        self.title_block = (w - 12.0 - 110.0, h - 12.0 - 36.0, w - 12.0, h - 12.0)   # KiCad default block ~110 mm wide
        self._collect()

    def _fields(self, s):
        out = []
        for p in kids(s, "property"):
            eff = kid(p, "effects")
            hidden = kid(p, "hide") is not None and (len(kid(p, "hide")) < 2 or kid(p, "hide")[1] == "yes")
            if eff is not None and ("hide" in eff or (kid(eff, "hide") is not None and kid(eff, "hide")[-1] != "no")):
                hidden = True
            if hidden or not p[2]:
                continue
            at = kid(p, "at")
            size = 1.27
            just = ("center", "center")
            if eff is not None:
                fnt = kid(eff, "font")
                if fnt is not None and kid(fnt, "size") is not None:
                    size = num(kid(fnt, "size")[1])
                j = kid(eff, "justify")
                if j is not None:
                    hx = "left" if "left" in j else ("right" if "right" in j else "center")
                    vy = "top" if "top" in j else ("bottom" if "bottom" in j else "center")
                    just = (hx, vy)
            out.append(dict(node=p, name=p[1], text=p[2], x=num(at[1]), y=num(at[2]),
                            ang=num(at[3]) if len(at) > 3 else 0.0, size=size, just=just))
        return out

    def _collect(self):
        for s in kids(self.root, "symbol"):
            lib_id = kid(s, "lib_id")[1]
            at = kid(s, "at")
            x, y, rot = num(at[1]), num(at[2]), num(at[3]) if len(at) > 3 else 0.0
            mir = kid(s, "mirror")[1] if kid(s, "mirror") is not None else None
            dnp = kid(s, "dnp") is not None and kid(s, "dnp")[1] == "yes"
            L = self.lib.get(lib_id)
            fields = self._fields(s)
            ref = next((f["text"] for f in fields if f["name"] == "Reference"),
                       next((p[2] for p in kids(s, "property") if p[1] == "Reference"), "?"))
            body = pins = None
            if L and L.pts:
                body = box_of([(x + dx, y + dy) for dx, dy in (xform(px, py, rot, mir) for px, py in L.pts)])
                pins = [tuple((x + dx, y + dy) for dx, dy in (xform(a[0], a[1], rot, mir), xform(b[0], b[1], rot, mir)))
                        for a, b in L.pins]
            sym = dict(node=s, ref=ref, x=x, y=y, rot=rot, mir=mir, dnp=dnp, body=body, pins=pins or [], fields=fields)
            self.syms.append(sym)
            for p in sym["pins"]:
                self.obst_segs.append((p[0], p[1], ref))
            for f in fields:
                vert = (round(f["ang"]) % 180 == 90) != (round(rot) % 180 == 90)
                self.texts.append(dict(box=text_box(f["x"], f["y"], f["text"], f["size"], vert, f["just"]),
                                       owner=ref, field=f, sym=sym))
        for w in kids(self.root, "wire") + kids(self.root, "bus"):
            pts = [(num(q[1]), num(q[2])) for q in kid(w, "pts") if head(q) == "xy"]
            for a, b in zip(pts, pts[1:]):
                self.obst_segs.append((a, b, "wire"))
        for j in kids(self.root, "junction"):
            at = kid(j, "at"); self.obst_boxes.append(((num(at[1]) - 0.5, num(at[2]) - 0.5, num(at[1]) + 0.5, num(at[2]) + 0.5), "junction"))
        for nc in kids(self.root, "no_connect"):
            at = kid(nc, "at"); self.obst_boxes.append(((num(at[1]) - 0.7, num(at[2]) - 0.7, num(at[1]) + 0.7, num(at[2]) + 0.7), "no-connect"))
        for kind in ("label", "global_label", "hierarchical_label", "text"):
            for l in kids(self.root, kind):
                at = kid(l, "at"); eff = kid(l, "effects"); size = 1.27
                if eff is not None and kid(eff, "font") is not None and kid(kid(eff, "font"), "size") is not None:
                    size = num(kid(kid(eff, "font"), "size")[1])
                ang = num(at[3]) if len(at) > 3 else 0.0
                w, h = text_width(l[1].split("\n")[0], size), HEIGHT * size * (l[1].count("\n") + 1)
                x, y = num(at[1]), num(at[2])
                # labels grow from the anchor in the direction of their angle
                if round(ang) % 360 == 0:
                    b = (x, y - h, x + w, y)
                elif round(ang) % 360 == 180:
                    b = (x - w, y - h, x, y)
                elif round(ang) % 360 == 90:
                    b = (x - h, y - w, x, y)
                else:
                    b = (x - h, y, x, y + w)
                if kind == "text":
                    b = (x, y, x + w, y + h)
                self.obst_boxes.append((b, kind))
        for tb in kids(self.root, "text_box"):
            at, sz = kid(tb, "at"), kid(tb, "size")
            x, y = num(at[1]), num(at[2])
            self.obst_boxes.append(((x, y, x + num(sz[1]), y + num(sz[2])), "text box"))

    # ------------------------------------------------------------------- collision test for one text box
    def clashes(self, box, sym, ignore=()):
        own = sym["ref"]
        out = []
        f = self.frame
        if box[0] < f[0] or box[1] < f[1] or box[2] > f[2] or box[3] > f[3]:
            out.append("frame")
        if hit(box, self.title_block):
            out.append("title block")
        for s in self.syms:
            if s["body"] is None:
                continue
            b = s["body"]
            if s is sym and s["dnp"]:
                b = (b[0] - DNP_GROW, b[1] - DNP_GROW, b[2] + DNP_GROW, b[3] + DNP_GROW)
            if hit(box, b):
                out.append("own body" if s is sym else f"body of {s['ref']}")
        for a, b, who in self.obst_segs:
            if who == own:
                continue
            if seg_hits_box(a, b, box):
                out.append("wire" if who == "wire" else f"pin of {who}")
        for b, kind in self.obst_boxes:
            if hit(box, b):
                out.append(kind)
        for t in self.texts:
            if t["field"] in ignore:
                continue
            if hit(box, t["box"]):
                out.append(f"text '{t['field']['text']}' of {t['owner']}")
        return out


# ----------------------------------------------------------------------------- the sweep
def candidates(sym, fields):
    """Alternative (cx, cy) for Reference and Value, conventional order first."""
    b = sym["body"]
    cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    hw, hh = (b[2] - b[0]) / 2, (b[3] - b[1]) / 2
    if sym["dnp"]:
        hw, hh = hw + DNP_GROW, hh + DNP_GROW
    pins = sym["pins"]
    vertical = bool(pins) and abs(pins[0][0][0] - pins[-1][0][0]) < 0.01
    ref = next((f for f in fields if f["name"] == "Reference"), None)
    val = next((f for f in fields if f["name"] == "Value"), None)
    wr = text_width(ref["text"], ref["size"]) if ref else 0
    wv = text_width(val["text"], val["size"]) if val else 0
    lh = HEIGHT * max(f["size"] for f in fields)
    out = []
    if vertical:
        for dy in (0, -STEP, STEP, -2 * STEP, 2 * STEP):
            for sgn in (1, -1):
                x_edge = cx + sgn * (hw + GAP)
                out.append(((x_edge + sgn * wr / 2, cy - lh * 0.55 + dy), (x_edge + sgn * wv / 2, cy + lh * 0.55 + dy)))
    else:
        for dx in (0, -STEP, STEP, -2 * STEP, 2 * STEP):
            up, dn = cy - hh - GAP - lh / 2, cy + hh + GAP + lh / 2
            out.append(((cx + dx, up), (cx + dx, dn)))
            out.append(((cx + dx, up - lh * 1.05), (cx + dx, up)))
            out.append(((cx + dx, dn), (cx + dx, dn + lh * 1.05)))
    return out


def sweep(sheet, prefixes, apply, verbose):
    edits, fixed, unfixed, ok = [], [], [], 0
    rx = re.compile(r"^(%s)\d" % "|".join(map(re.escape, prefixes)))
    for sym in sheet.syms:
        if not rx.match(sym["ref"]) or sym["body"] is None:
            continue
        fields = [f for f in sym["fields"] if f["name"] in ("Reference", "Value")]
        if not fields:
            continue
        mine = [t for t in sheet.texts if t["sym"] is sym and t["field"] in fields]
        problems = {t["field"]["name"]: sheet.clashes(t["box"], sym, ignore=fields) for t in mine}
        if not any(problems.values()):
            ok += 1
            continue
        if verbose:
            print(f"  {sym['ref']}: " + "; ".join(f"{k} -> {', '.join(sorted(set(v)))}" for k, v in problems.items() if v))
        done = False
        for cand in candidates(sym, fields):
            pos = {"Reference": cand[0], "Value": cand[1]}
            boxes = {f["name"]: text_box(*pos[f["name"]], f["text"], f["size"]) for f in fields}
            if hit(boxes.get("Reference", (0, 0, 0, 0)), boxes.get("Value", (9e9, 9e9, 9e9, 9e9))):
                continue
            if all(not sheet.clashes(boxes[f["name"]], sym, ignore=fields) for f in fields):
                ang = 90 if round(sym["rot"]) % 180 == 90 else 0      # field angle + symbol angle = horizontal
                for f in fields:
                    x, y = pos[f["name"]]
                    edits.append((f["node"], round(x, 3), round(y, 3), ang))
                    f["x"], f["y"] = x, y
                    for t in sheet.texts:                                # later parts see the new position
                        if t["field"] is f:
                            t["box"] = boxes[f["name"]]
                if kid(sym["node"], "fields_autoplaced") is not None:
                    edits.append((kid(sym["node"], "fields_autoplaced"), None, None, None))
                fixed.append(sym["ref"])
                done = True
                break
        if not done:
            unfixed.append((sym["ref"], {k: sorted(set(v)) for k, v in problems.items() if v}))
    if apply and edits:
        text = sheet.text
        for node, x, y, ang in sorted(edits, key=lambda e: -e[0].start):
            if x is None:                                    # drop (fields_autoplaced yes)
                text = text[:node.start] + text[node.end:]
                continue
            at = kid(node, "at")
            eff = kid(node, "effects")
            j = kid(eff, "justify") if eff is not None else None
            seg = text[node.start:node.end]
            new_at = f"(at {x:g} {y:g} {ang:g})"
            if j is not None:                                # centred text: remove the justify node
                seg = seg[:j.start - node.start] + seg[j.end - node.start:]
            a0, a1 = at.start - node.start, at.end - node.start
            seg = seg[:a0] + new_at + seg[a1:]
            text = text[:node.start] + seg + text[node.end:]
        open(sheet.path, "w", encoding="utf-8", newline="").write(text)
    return ok, fixed, unfixed


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", help=".kicad_sch files or directories")
    ap.add_argument("--apply", action="store_true", help="rewrite the files (default: check only)")
    ap.add_argument("--prefixes", default="R,C", help="reference prefixes to sweep (default R,C)")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    files = []
    for p in a.paths:
        if os.path.isdir(p):
            files += [f for f in sorted(glob.glob(os.path.join(p, "*.kicad_sch")))
                      if not re.search(r"(-bak|_old|backups)", f)]
        else:
            files.append(p)
    prefixes = [x.strip() for x in a.prefixes.split(",") if x.strip()]
    tot_fixed = tot_unfixed = tot_ok = 0
    for f in files:
        sh = Sheet(f)
        ok, fixed, unfixed = sweep(sh, prefixes, a.apply, a.verbose)
        tot_ok += ok; tot_fixed += len(fixed); tot_unfixed += len(unfixed)
        verb = "moved" if a.apply else "would move"
        print(f"{os.path.basename(f):32s} clear {ok:4d}  {verb} {len(fixed):3d}  unresolved {len(unfixed):3d}"
              + (f"  [{', '.join(fixed[:12])}{' ...' if len(fixed) > 12 else ''}]" if fixed else ""))
        for ref, prob in unfixed:
            print(f"    UNRESOLVED {ref}: " + "; ".join(f"{k} -> {', '.join(v)}" for k, v in prob.items()))
    print(f"\nR/C text sweep: {tot_ok} clear, {tot_fixed} {'moved' if a.apply else 'to move'}, {tot_unfixed} unresolved")
    if a.apply and tot_fixed:
        print("Re-run ERC, the plotted-PDF drawing check (check_drawing.py) and the connectivity check.")
    return 0 if (tot_unfixed == 0 and (a.apply or tot_fixed == 0)) else 1


if __name__ == "__main__":
    sys.exit(main())
