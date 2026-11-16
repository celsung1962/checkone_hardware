#!/usr/bin/env python3
"""
Builds the grouped, costed BOM workbook (DOC/<Product>_BOM.xlsx) from the KiCad
netlist and the catalog data the agent collected. Also writes a Markdown summary
(bom/bom_summary.md) that the technical document includes as its BOM annex.

Usage:
    python3 generate_bom_xlsx.py --netlist hardware/<project>.net --parts bom/parts.csv \
        --product "<Product>" --revision A --batch 5 [--company "<Company>"] \
        [--out DOC/<Product>_BOM.xlsx] [--summary-md bom/bom_summary.md] \
        [--primary 1F4E79] [--zebra F7F9FA] [--font Calibri] [--query "2026-09-26 06:19, jlcpcb.com + lcsc.com"] \
        [--consigned C123456,...]

bom/parts.csv — one row per LCSC code, filled ONLY from catalog queries (never from memory):
    lcsc,manufacturer,mpn,description,jlc_class,lcsc_price_tiers,lcsc_moq,lcsc_multiple,lcsc_stock,
    jlc_price_tiers,jlc_stock,notes
    price tiers: "1:0.0150;50:0.0134;500:0.0101"  (quantity:unit price in US$, ascending)
    jlc_class:   Basic | Preferred | Extended

Grouping: identical parts (same LCSC code, or same Value+Footprint+MPN when there is no
code) on one row, references compressed into ranges (C39–C45). DNP parts and parts without
an LCSC code (test points, holes, fiducials) go to the "DNP and no LCSC" sheet.

Every derived number in the workbook is a formula (line cost, purchase cost, totals,
stock criterion, summary counts). --recalc opens the file in LibreOffice (headless, UNO),
recalculates, saves the cached values and fails if any cell evaluates to an error, so
viewers that do not recalculate (previews, pandas) show the numbers.
"""
import argparse, csv, datetime, math, os, re, sys, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from netlist_check import Netlist  # noqa: E402

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
except ImportError:
    sys.exit("openpyxl is required: pip install openpyxl")

NO_LCSC_OK = re.compile(r"^(TP|MH|FID|H|NT|JP|LOGO|G)\d", re.I)


def truthy(v):
    return str(v).strip().lower() not in ("", "0", "no", "false", "n")


def flag(f, name):
    """KiCad 10 netlists write flags such as dnp / exclude_from_bom as a property with no value: presence = set."""
    if name in f:
        v = f.get(name)
        return v is None or str(v).strip() == "" or truthy(v)
    return False


def ref_key(r):
    m = re.match(r"([A-Za-z_]+)(\d+)(.*)", r)
    return (m.group(1), int(m.group(2)), m.group(3)) if m else (r, 0, "")


def compress(refs):
    refs = sorted(set(refs), key=ref_key)
    out, i = [], 0
    while i < len(refs):
        p, n, s = ref_key(refs[i])
        j = i
        while j + 1 < len(refs):
            p2, n2, s2 = ref_key(refs[j + 1])
            if p2 == p and s2 == s == "" and n2 == ref_key(refs[j])[1] + 1:
                j += 1
            else:
                break
        out.append(refs[i] if j - i < 2 else f"{refs[i]}–{refs[j]}")
        if j - i == 1:
            out.append(refs[j])
        i = j + 1
    return ", ".join(out)


def tiers(s):
    t = []
    for part in str(s or "").split(";"):
        if ":" in part:
            q, p = part.split(":", 1)
            try:
                t.append((int(float(q)), float(p)))
            except ValueError:
                pass
    return sorted(t)


def price_at(t, qty):
    if not t:
        return None
    p = t[0][1]
    for q, v in t:
        if qty >= q:
            p = v
    return p


def to_int(v, default=None):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return default


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--netlist", required=True)
    ap.add_argument("--parts", required=True)
    ap.add_argument("--product", required=True)
    ap.add_argument("--revision", default="A")
    ap.add_argument("--batch", type=int, default=5)
    ap.add_argument("--company", default="")
    ap.add_argument("--out")
    ap.add_argument("--summary-md", default="bom/bom_summary.md")
    ap.add_argument("--primary", default="1F4E79")
    ap.add_argument("--zebra", default="F7F9FA")
    ap.add_argument("--font", default="Calibri")
    ap.add_argument("--query", default="", help="when/where prices and stock were queried")
    ap.add_argument("--consigned", default="", help="LCSC codes supplied by the customer (cost shown for reference)")
    ap.add_argument("--price-source", choices=("lcsc", "jlc"), default="lcsc",
                    help="price the BOM with the LCSC store tiers (default) or the JLCPCB assembly-library tiers "
                         "(when only JLCPCB was queried; no MOQ/multiple applied)")
    ap.add_argument("--recalc", action="store_true", help="recalculate with LibreOffice and check for formula errors")
    a = ap.parse_args()
    out = a.out or os.path.join("DOC", re.sub(r"[^A-Za-z0-9]+", "_", a.product).strip("_") + "_BOM.xlsx")
    B = a.batch
    consigned = {c.strip() for c in a.consigned.split(",") if c.strip()}
    JLC = a.price_source == "jlc"

    nl = Netlist(a.netlist)
    parts = {}
    with open(a.parts, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("lcsc", "").strip():
                parts[r["lcsc"].strip()] = r

    groups = collections.OrderedDict()
    side = collections.OrderedDict()
    n_virtual = 0
    for ref, f in nl.comps.items():
        if ref.startswith("#"):
            n_virtual += 1
            continue
        excluded = flag(f, "exclude_from_bom")      # test pads, holes, fiducials: listed, never bought
        lcsc = str(f.get("LCSC", "")).strip()
        dnp = flag(f, "dnp") or truthy(f.get("DNP", ""))
        mpn = str(f.get("MPN", f.get("Manufacturer_Part_Number", ""))).strip()
        key = (lcsc or f"{f.get('Value')}|{f.get('Footprint')}|{mpn}", dnp)
        target = side if (dnp or not lcsc or excluded) else groups
        g = target.setdefault(key, {"refs": [], "value": f.get("Value", ""), "fp": f.get("Footprint", ""),
                                    "desc": f.get("Description", ""), "lcsc": lcsc, "dnp": dnp, "mpn": mpn})
        g["refs"].append(ref)

    def sort_key(item):
        g = item[1]
        return (ref_key(sorted(g["refs"], key=ref_key)[0])[0], g["value"])
    groups = collections.OrderedDict(sorted(groups.items(), key=sort_key))

    wb = Workbook()
    F = lambda **k: Font(name=a.font, size=k.pop("size", 10), **k)  # noqa: E731
    thin = Side(style="thin", color="BFBFBF")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    hdr_fill = PatternFill("solid", fgColor=a.primary)
    zebra = PatternFill("solid", fgColor=a.zebra)
    text_col = "292929"

    def header(ws, row, names, widths):
        for i, (nme, w) in enumerate(zip(names, widths), 1):
            c = ws.cell(row=row, column=i, value=nme)
            c.font = F(bold=True, color="FFFFFF")
            c.fill = hdr_fill
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            c.border = border
            ws.column_dimensions[get_column_letter(i)].width = w
        ws.row_dimensions[row].height = 42

    # ---------------- BOM sheet ----------------
    ws = wb.active
    ws.title = "BOM"
    ws["A1"] = f"{a.product} — Bill of materials (BOM), board revision {a.revision}"
    ws["A1"].font = F(size=14, bold=True, color=a.primary)
    sub = " · ".join(x for x in [a.company, "identical parts grouped on one row",
                                  f"query: {a.query}" if a.query else "",
                                  f"costs in US$; batch of {B} boards; no setup fees, PCB, assembly or freight"] if x)
    ws["A2"] = sub
    ws["A2"].font = F(size=9, color="6D6D6D")
    src = "JLCPCB" if JLC else "LCSC"
    cols = ["Item", "Qty/board", f"Qty batch ({B})", "References", "Value", "Description", "Footprint",
            "Manufacturer / PN", "LCSC", "JLCPCB class", f"{src} unit cost (US$)", "Line cost per board (US$)",
            f"{src} purchase (qty)", f"{src} purchase cost (US$)", "LCSC stock", "JLCPCB unit cost (US$)",
            "JLCPCB stock", f"JLCPCB stock ≥ 10 × batch", "Notes"]
    widths = [6, 8, 9, 34, 16, 44, 30, 26, 11, 11, 11, 13, 11, 12, 11, 11, 13, 12, 50]
    header(ws, 4, cols, widths)
    first = 5
    missing, low_stock = [], []
    r = first
    for i, (key, g) in enumerate(groups.items(), 1):
        q = len(g["refs"])
        p = parts.get(g["lcsc"])
        notes = []
        if p is None:
            missing.append(g["lcsc"])
            notes.append("NO CATALOG DATA in bom/parts.csv — query the catalog")
            p = {}
        moq = to_int(p.get("lcsc_moq"), 1) or 1
        mult = to_int(p.get("lcsc_multiple"), 1) or 1
        buy = max(moq, math.ceil(q * B / mult) * mult) if p else None
        lt, jt = tiers(p.get("lcsc_price_tiers")), tiers(p.get("jlc_price_tiers"))
        if JLC:                                   # JLCPCB pricing: batch quantity, JLCPCB tiers
            lt, moq, mult = jt, 1, 1
            buy = q * B if p else None
        lunit = price_at(lt, buy or q * B)
        junit = price_at(jt, q * B)
        jstock = to_int(p.get("jlc_stock"))
        if p and not JLC and (moq > 1 or mult > 1):
            notes.append(f"LCSC MOQ/multiple: {moq}/{mult}")
        if g["lcsc"] in consigned:
            notes.append("consigned by the customer (cost for reference only)")
        if p.get("notes"):
            notes.append(p["notes"])
        if jstock is not None and jstock < 10 * q * B:
            low_stock.append((g["value"], g["lcsc"], q, jstock))
        mfr_pn = " / ".join(x for x in [p.get("manufacturer", ""), p.get("mpn", "") or g["mpn"]] if x)
        row = [i, q, f"=B{r}*{B}", compress(g["refs"]), g["value"], p.get("description") or g["desc"],
               g["fp"], mfr_pn, g["lcsc"], p.get("jlc_class", ""), lunit, f"=B{r}*K{r}" if lunit is not None else None,
               buy, f"=M{r}*K{r}" if (lunit is not None and buy) else None, to_int(p.get("lcsc_stock")),
               junit, jstock, f'=IF(Q{r}="","",IF(Q{r}>=10*C{r},"yes","NO"))', "; ".join(notes)]
        for c_i, v in enumerate(row, 1):
            c = ws.cell(row=r, column=c_i, value=v)
            c.font = F(color=text_col)
            c.border = border
            if i % 2 == 0:
                c.fill = zebra
            if c_i in (4, 6, 19):
                c.alignment = Alignment(wrap_text=True, vertical="top")
            if c_i in (11, 12, 14, 16):
                c.number_format = "0.0000"
            if c_i in (15, 17):
                c.number_format = "#,##0"
        r += 1
    last = r - 1
    tot = r
    for col, v in (("B", f"=SUM(B{first}:B{last})"), ("C", f"=SUM(C{first}:C{last})"), ("K", "Total per board"),
                   ("L", f"=SUM(L{first}:L{last})"), ("M", "Batch purchase total →"), ("N", f"=SUM(N{first}:N{last})")):
        c = ws[f"{col}{tot}"]
        c.value = v
        c.font = F(bold=True, color=text_col)
        if col in ("L", "N"):
            c.number_format = "0.00"
    ws.freeze_panes = "E5"
    ws.auto_filter.ref = f"A4:{get_column_letter(len(cols))}{last}"

    # ---------------- DNP / no LCSC sheet ----------------
    ds = wb.create_sheet("DNP and no LCSC")
    ds["A1"] = "Parts not assembled (DNP) and parts without an LCSC code (test points, holes, fiducials)"
    ds["A1"].font = F(size=12, bold=True, color=a.primary)
    header(ds, 3, ["Type", "Qty", "References", "Value", "Footprint", "LCSC", "Description"], [14, 6, 60, 22, 36, 12, 48])
    rr = 4
    unexpected_no_lcsc = []
    for key, g in sorted(side.items(), key=sort_key):
        kind = "DNP" if g["dnp"] else "No LCSC"
        if not g["dnp"] and not g["lcsc"] and not all(NO_LCSC_OK.match(x) for x in g["refs"]):
            unexpected_no_lcsc.extend(g["refs"])
        vals = [kind, len(g["refs"]), compress(g["refs"]), g["value"], g["fp"], g["lcsc"],
                (parts.get(g["lcsc"], {}) or {}).get("description") or g["desc"]]
        for c_i, v in enumerate(vals, 1):
            c = ds.cell(row=rr, column=c_i, value=v)
            c.font = F(color=text_col)
            c.border = border
            if c_i in (3, 7):
                c.alignment = Alignment(wrap_text=True, vertical="top")
        rr += 1

    # ---------------- Summary sheet (first) ----------------
    sm = wb.create_sheet("Summary", 0)
    sm.column_dimensions["A"].width = 52
    sm.column_dimensions["B"].width = 72
    sm["A1"] = f"{a.product} — BOM summary"
    sm["A1"].font = F(size=14, bold=True, color=a.primary)
    rng = lambda c: f"BOM!{c}{first}:{c}{last}"  # noqa: E731
    n_comp = len([x for x in nl.comps if not x.startswith("#")])
    lines = [
        ("Board", f"{a.product}, revision {a.revision}"),
        ("Components in the schematic", n_comp),
        ("Assembled BOM lines (with LCSC)", f"=COUNTA({rng('I')})"),
        ("Assembled parts per board", f"=BOM!B{tot}"),
        (f"Component cost per board, {src} prices (US$)", f"=BOM!L{tot}"),
        (f"{src} purchase cost for a batch of {B}" + ("" if JLC else ", with MOQ and multiple") + " (US$)",
         f"=BOM!N{tot}"),
        ("Query", a.query or "—"),
        ("Pricing rule", (f"JLCPCB assembly-library prices at the tier of the batch quantity (batch of {B}); LCSC store "
                          "not queried. " if JLC else
                          f"LCSC: price tier of the purchased quantity (batch of {B}, MOQ and multiple respected); "
                          "JLCPCB: price tier of the batch quantity. ")
                         + "Excludes Extended setup fees, PCB, assembly and freight"
                         + ("; consigned parts included for reference" if consigned else "")),
        (f"JLCPCB stock below 10 × batch", ", ".join(x[1] for x in low_stock) or "none"),
        ("Basic references (JLCPCB) — distinct", f'=COUNTIF({rng("J")},"Basic")'),
        ("Basic parts per board", f'=SUMIF({rng("J")},"Basic",{rng("B")})'),
        ("Preferred references (JLCPCB) — distinct", f'=COUNTIF({rng("J")},"Preferred")'),
        ("Preferred parts per board", f'=SUMIF({rng("J")},"Preferred",{rng("B")})'),
        ("Extended references (JLCPCB) — distinct", f'=COUNTIF({rng("J")},"Extended")'),
        ("Extended parts per board", f'=SUMIF({rng("J")},"Extended",{rng("B")})'),
        ("Lines without catalog data", ", ".join(missing) or "none"),
    ]
    for i, (k, v) in enumerate(lines, 3):
        sm.cell(row=i, column=1, value=k).font = F(bold=True, color=text_col)
        c = sm.cell(row=i, column=2, value=v)
        c.font = F(color=text_col)
        c.alignment = Alignment(wrap_text=True, horizontal="left")
        if "US$" in k:
            c.number_format = "0.00"
    sm.cell(row=len(lines) + 4, column=1,
            value="All counts, costs and totals are formulas over the BOM sheet; catalog data from bom/parts.csv.").font = F(size=9, italic=True, color="6D6D6D")
    for s in (ws, ds, sm):
        s.sheet_view.showGridLines = False
        s.page_setup.orientation = "landscape"
        s.page_setup.fitToWidth = 1
        s.sheet_properties.pageSetUpPr.fitToPage = True
        s.page_setup.fitToHeight = 0

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    wb.save(out)

    # ---------------- Markdown summary for the technical document ----------------
    tkey = "jlc_price_tiers" if JLC else "lcsc_price_tiers"
    per_board = sum(price_at(tiers(parts.get(g["lcsc"], {}).get(tkey)),
                             max(to_int(parts.get(g["lcsc"], {}).get("lcsc_moq"), 1) or 1,
                                 math.ceil(len(g["refs"]) * B / (to_int(parts.get(g["lcsc"], {}).get("lcsc_multiple"), 1) or 1))
                                 * (to_int(parts.get(g["lcsc"], {}).get("lcsc_multiple"), 1) or 1))) * len(g["refs"])
                    for g in groups.values() if parts.get(g["lcsc"]) and tiers(parts[g["lcsc"]].get(tkey)))
    pieces = sum(len(g["refs"]) for g in groups.values())
    cls = collections.Counter()
    for g in groups.values():
        cls[(parts.get(g["lcsc"], {}) or {}).get("jlc_class", "unknown")] += 1
    md = [f"| Item | Value |", "| --- | --- |",
          f"| BOM lines (identical parts grouped) | {len(groups)} |",
          f"| Assembled parts per board | {pieces} |",
          f"| Component cost per board ({src} prices) | US$ {per_board:.2f}{' (incomplete: lines without catalog data)' if missing else ''} |",
          f"| JLCPCB classes (distinct lines) | " + ", ".join(f"{k} {v}" for k, v in sorted(cls.items())) + " |",
          f"| Price and stock query | {a.query or '—'} |", ""]
    if low_stock:
        md.append(f"JLCPCB stock below the criterion (≥ 10 × batch of {B}):\n")
        md += [f"- {v} ({l}): {q} per board, JLCPCB stock {s:,}" for v, l, q, s in low_stock]
        md.append("")
    md.append(f"Full detail in `{out}`.")
    os.makedirs(os.path.dirname(os.path.abspath(a.summary_md)), exist_ok=True)
    open(a.summary_md, "w", encoding="utf-8").write("\n".join(md) + "\n")

    print(f"Wrote {out}: {len(groups)} BOM lines, {pieces} parts/board, {len(side)} DNP/no-LCSC lines")
    print(f"Wrote {a.summary_md}")
    if missing:
        print(f"WARNING: {len(missing)} line(s) without catalog data: {', '.join(missing)}")
    if unexpected_no_lcsc:
        print(f"WARNING: parts without LCSC that are not test points/holes/fiducials: {', '.join(unexpected_no_lcsc)}")
    if low_stock:
        print(f"NOTE: {len(low_stock)} line(s) with JLCPCB stock below 10 × batch")
    if a.recalc:
        msg, ok = recalc(out)
        print(msg)
        if not ok:
            sys.exit(1)
    else:
        print("Formulas have no cached values yet: run again with --recalc (LibreOffice) or open and save in Excel.")


UNO_RECALC = r'''
import sys, uno
from com.sun.star.beans import PropertyValue
def prop(n, v):
    p = PropertyValue(); p.Name = n; p.Value = v; return p
src, port = sys.argv[1], sys.argv[2]
local = uno.getComponentContext()
resolver = local.ServiceManager.createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver", local)
ctx = resolver.resolve(f"uno:socket,host=localhost,port={port};urp;StarOffice.ComponentContext")
desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
url = uno.systemPathToFileUrl(src)
doc = desktop.loadComponentFromURL(url, "_blank", 0, (prop("Hidden", True),))
doc.calculateAll()
doc.storeToURL(url, (prop("FilterName", "Calc MS Excel 2007 XML"),))
doc.close(True)
'''


def recalc(path):
    """Recalculates the workbook in LibreOffice and reports formula errors. Returns (message, ok)."""
    import shutil, subprocess, tempfile, time
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return "Recalc skipped: LibreOffice not found. Open and save the file in Excel to store values.", True
    path = os.path.abspath(path)
    prof = tempfile.mkdtemp()
    port = "2084"
    proc = subprocess.Popen([soffice, f"-env:UserInstallation=file://{prof}", "--headless", "--invisible",
                             "--norestore", f"--accept=socket,host=localhost,port={port};urp;"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    script = os.path.join(prof, "recalc.py")
    open(script, "w").write(UNO_RECALC)
    done = False
    for _ in range(30):
        time.sleep(1)
        r = subprocess.run([shutil.which("python3") or sys.executable, script, path, port], capture_output=True, text=True)
        if r.returncode == 0:
            done = True
            break
    proc.terminate()
    if not done:
        return "Recalc failed (LibreOffice/UNO not reachable): " + r.stderr[-300:], False
    from openpyxl import load_workbook
    wb = load_workbook(path, data_only=True)
    bad = {"#REF!", "#VALUE!", "#NAME?", "#DIV/0!", "#N/A", "#NUM!", "#NULL!"}
    errs = [f"{ws.title}!{c.coordinate}={c.value}" for ws in wb for row in ws.iter_rows() for c in row
            if isinstance(c.value, str) and c.value in bad]
    if errs:
        return f"Recalculated, but {len(errs)} formula error(s): {', '.join(errs[:10])}", False
    return "Recalculated with LibreOffice: values cached, no formula errors.", True


if __name__ == "__main__":
    main()
