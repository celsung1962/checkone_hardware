#!/usr/bin/env python3
"""
Drawing-clearance check of a plotted KiCad schematic (references/schematic_drawing.md, section 9).
Exports the schematic to PDF with kicad-cli (or reads an existing PDF) and reports, per page:
  1. text/text  - text spans whose boxes intersect (fields, labels, pin names/numbers, notes, power names);
  2. text/wire  - text crossed by a wire (wire colour);
  3. text/DNP   - text under the cross of a DNP part;
  4. text/body  - text crossed by a symbol outline (stroke width included: thick capacitor plates reach further
                  than their centre line);
  5. text/NC    - field or label text under a no-connect cross (pin numbers exempt);
  6. frame      - text or wires crossing the inner drawing frame or lying in the border band (zone letters and
                  numbers excepted); title-block text that does not fit the title block.
Each hit is printed with the sheet name and the position in mm; exit 1 on any hit.

Text boxes are shrunk slightly so touching boxes do not count. That margin can hide a value whose last letter
just touches a neighbouring part: run scripts/fix_passive_text.py --check as well (it measures the full advance).

Colours are KiCad's default schematic plot colours; pass --wire/--body/--dnp/--nc "r,g,b" (0-1) for a project
with another colour theme.

Allow-list (--allow file.csv, columns sheet,text,reason): text that a LIBRARY symbol draws inside its own
artwork (e.g. switch contact names). Never add an entry for an overlap you caused: fix the placement.

Usage:
    python3 check_drawing.py hardware/<project>.kicad_sch [--allow docs/drawing_allow.csv] [--pdf existing.pdf]
                             [--kicad-cli PATH] [--max 8]
Requires: PyMuPDF (pip install pymupdf), kicad-cli (KiCad 8+).
"""
import argparse, csv, os, re, shutil, subprocess, sys, tempfile

try:
    import fitz
except ImportError:
    sys.exit("PyMuPDF is required: pip install pymupdf")

SHRINK = 0.12          # ignore touching boxes: shrink each box by this fraction of its height
MM = 72 / 25.4
FRAME = 12.0 * MM      # KiCad default page layout: outer border 10 mm, inner frame 12 mm from the page edge


def colour(s):
    return tuple(round(float(x), 2) for x in s.split(","))


def find_kicad_cli(given):
    if given:
        return given
    for c in (shutil.which("kicad-cli"),
              *sorted(__import__("glob").glob(r"C:\Program Files\KiCad\*\bin\kicad-cli.exe"), reverse=True),
              "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli", "/usr/bin/kicad-cli"):
        if c and os.path.exists(c):
            return c
    sys.exit("kicad-cli not found: pass --kicad-cli PATH")


def title_block(page, r):
    # KiCad default title block: fixed size (~112 x 42 mm incl. comments) at the bottom-right of the 10 mm border,
    # so a page fraction is wrong on A4 (it only fit A3)
    return r.x0 > page.rect.width - 122 * MM and r.y0 > page.rect.height - 52 * MM


def spans(page):
    out = []
    for b in page.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            for sp in ln["spans"]:
                t = sp["text"].strip()
                if not t:
                    continue
                r = fitz.Rect(sp["bbox"])
                h = min(r.height, r.width) * SHRINK
                v = r.height * 0.25 if r.height < r.width * 3 else h    # font boxes of stacked lines touch
                out.append((fitz.Rect(r.x0 + h, r.y0 + v, r.x1 - h, r.y1 - v), t, r, title_block(page, r)))
    return out


def segments(page, col, widths=False):
    segs = []
    for d in page.get_drawings():
        c = tuple(round(x, 2) for x in (d.get("color") or ()))
        if c != col:
            continue
        w = d.get("width") or 0
        for it in d["items"]:
            if it[0] == "l":
                found = [(it[1], it[2])]
            elif it[0] == "re":
                q = it[1]
                found = [(q.tl, q.tr), (q.tr, q.br), (q.br, q.bl), (q.bl, q.tl)]
            else:
                continue
            segs += [(a, b, w) for a, b in found] if widths else found
    return segs


def seg_hits_rect(a, b, r):
    x0, y0, dx, dy = a.x, a.y, b.x - a.x, b.y - a.y
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x0 - r.x0), (dx, r.x1 - x0), (-dy, y0 - r.y0), (dy, r.y1 - y0)):
        if p == 0:
            if q < 0:
                return False
        else:
            t = q / p
            if p < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
            if t0 > t1:
                return False
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("schematic", help="root .kicad_sch")
    ap.add_argument("--pdf", help="use this plotted PDF instead of exporting one")
    ap.add_argument("--allow", help="CSV allow-list: sheet,text,reason")
    ap.add_argument("--kicad-cli")
    ap.add_argument("--max", type=int, default=8, help="hits printed per page")
    ap.add_argument("--wire", default="0,0.59,0"); ap.add_argument("--body", default="0.52,0,0")
    ap.add_argument("--dnp", default="0.88,0.18,0.19"); ap.add_argument("--nc", default="0,0,0.52")
    a = ap.parse_args()
    WIRE, BODY, DNP, NOCONN = colour(a.wire), colour(a.body), colour(a.dnp), colour(a.nc)
    allow = {}
    if a.allow:
        for row in csv.DictReader(open(a.allow, encoding="utf-8")):
            allow[(row["sheet"].strip("/"), row["text"])] = row.get("reason", "")
    pdf = a.pdf
    if not pdf:
        pdf = os.path.join(tempfile.mkdtemp(prefix="drawing_check_"), "schematic.pdf")
        r = subprocess.run([find_kicad_cli(a.kicad_cli), "sch", "export", "pdf", "-o", pdf, a.schematic],
                           capture_output=True, text=True)
        if not os.path.exists(pdf):
            sys.exit(f"kicad-cli export failed: {r.stderr or r.stdout}")
    doc = fitz.open(pdf)
    total = 0
    for i, page in enumerate(doc):
        title = next((l for l in page.get_text().splitlines() if l.startswith("Sheet: /")), f"page {i + 1}")
        sheet = title.replace("Sheet: /", "").strip("/")
        inner = fitz.Rect(FRAME, FRAME, page.rect.width - FRAME, page.rect.height - FRAME)
        sp = spans(page)
        hits = []
        for _, t, full, _ in [x for x in sp if x[3]]:          # title block: only the frame check applies
            if (full.x1 > inner.x1 or full.y1 > inner.y1) and full.intersects(inner):
                hits.append(f"'{t}'/frame (title block)")
        sp = [x for x in sp if not x[3]]
        for p in range(len(sp)):
            for q in range(p + 1, len(sp)):
                ra, rb = sp[p][0], sp[q][0]
                if not ra.intersects(rb):
                    continue
                inter = ra & rb
                if sp[p][1] == sp[q][1] and inter.get_area() > 0.6 * min(ra.get_area(), rb.get_area()):
                    continue        # KiCad plots each text twice (stroke + searchable layer)
                hits.append(f"'{sp[p][1]}'/'{sp[q][1]}'@({ra.x0 / MM:.0f},{ra.y0 / MM:.0f})")
        wires, dnp, noconn = segments(page, WIRE), segments(page, DNP), segments(page, NOCONN)
        body = [s for s in segments(page, BODY, widths=True) if inner.contains(s[0]) and inner.contains(s[1])]
        seen = set()
        for r, t, full, _ in sp:
            key = (t, round(full.x0), round(full.y0))
            if key in seen:
                continue
            seen.add(key)
            at = f"@({full.x0 / MM:.0f},{full.y0 / MM:.0f})"
            if not inner.contains(full):
                if not (not full.intersects(inner) and len(t) <= 2):     # zone letters/numbers in the band
                    hits.append(f"'{t}'/frame{at}")
                continue
            if any(seg_hits_rect(p, q, r) for p, q in wires):
                hits.append(f"'{t}'/wire{at}")
            if any(seg_hits_rect(p, q, r) for p, q in dnp):
                hits.append(f"'{t}'/DNP{at}")
            if not re.fullmatch(r"[A-Z]{0,2}\d{1,3}", t) and any(seg_hits_rect(p, q, r) for p, q in noconn):
                hits.append(f"'{t}'/NC{at}")
            core = fitz.Rect(r.x0 + r.width * 0.1, r.y0 + r.height * 0.15, r.x1 - r.width * 0.1, r.y1 - r.height * 0.15)
            if (sheet, t) not in allow and any(
                    seg_hits_rect(p, q, fitz.Rect(core.x0 - w / 2, core.y0 - w / 2, core.x1 + w / 2, core.y1 + w / 2))
                    and not (core.contains(p) and core.contains(q)) for p, q, w in body):
                hits.append(f"'{t}'/body{at}")
        for p, q in wires:
            if not (inner.contains(p) and inner.contains(q)):
                hits.append(f"wire at ({p.x / MM:.0f},{p.y / MM:.0f}) mm/frame")
        total += len(hits)
        print(f"{title:40} {len(hits):4d} hits" + ("" if not hits else ": " + "; ".join(hits[:a.max])))
    print(f"\nDrawing check: {'PASS' if total == 0 else 'FAIL'} - {total} hits")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
