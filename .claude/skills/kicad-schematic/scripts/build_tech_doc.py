#!/usr/bin/env python3
"""
Builds the board technical document (DOC/<Product>_Technical_Documentation.docx)
from a Markdown source and a small JSON config: cover page with a metadata table,
table of contents, branded header and footer (logo, title, company, date,
"Page X of Y"), styled headings and tables (header row in the primary colour,
zebra rows). Tables are never retyped: generate them from the netlist
(netlist_tables.py), the BOM (generate_bom_xlsx.py → bom/bom_summary.md) and the
calc/ scripts, and pull them in with {{include <path>}} (path relative to the .md).

Usage:
    python3 build_tech_doc.py --source DOC/source/technical_doc.md --config DOC/source/doc_config.json \
        [--out DOC/<Product>_Technical_Documentation.docx] [--pdf]

Config (JSON):
{
  "product": "Product X", "doc_title": "Board technical documentation",
  "subtitle": "One-line description of the product",
  "cover_lines": ["Main board, revision A · <MCU> + <ADCs>", "Hardware reference for firmware, assembly and test"],
  "metadata": [["Document no.", "TBD"], ["Product", "Product X — main board"], ["Board revision", "A"],
               ["Schematic", "KiCad 10, 40 A3 pages, commit abc1234 (2026-09-26)"], ["Design contract", "CLAUDE.md rev. 4"],
               ["Hardware", "<owner>"], ["Data source", "KiCad netlist and calc/ scripts"], ["Date", "2026-09-26"]],
  "company": "<Company>", "date": "2026-09-26", "logo": "path/to/logo.png or null",
  "primary": "1F4E79", "accent": "2E75B6", "zebra": "F7F9FA", "text": "292929", "muted": "6D6D6D",
  "font": "Calibri", "page": "A4"
}
Requires: pandoc, python-docx. --pdf also needs LibreOffice (soffice): it writes a review PDF with the table of
contents filled in. The .docx asks Word to refresh its fields on open (the TOC fills in on the first open).
"""
import argparse, json, os, re, shutil, subprocess, sys, tempfile, copy

try:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_TAB_ALIGNMENT
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt, Cm, RGBColor, Emu
except ImportError:
    sys.exit("python-docx is required: pip install python-docx")


SETTINGS_ORDER = ["writeProtection", "view", "zoom", "removePersonalInformation", "removeDateAndTime",
    "doNotDisplayPageBoundaries", "displayBackgroundShape", "printPostScriptOverText", "printFractionalCharacterWidth",
    "printFormsData", "embedTrueTypeFonts", "embedSystemFonts", "saveSubsetFonts", "saveFormsData", "mirrorMargins",
    "alignBordersAndEdges", "bordersDoNotSurroundHeader", "bordersDoNotSurroundFooter", "gutterAtTop",
    "hideSpellingErrors", "hideGrammaticalErrors", "activeWritingStyle", "proofState", "formsDesign",
    "attachedTemplate", "linkStyles", "stylePaneFormatFilter", "stylePaneSortMethod", "documentType", "mailMerge",
    "revisionView", "trackRevisions", "doNotTrackMoves", "doNotTrackFormatting", "documentProtection",
    "autoFormatOverride", "styleLockTheme", "styleLockQFSet", "defaultTabStop", "autoHyphenation",
    "consecutiveHyphenLimit", "hyphenationZone", "doNotHyphenateCaps", "showEnvelope", "summaryLength",
    "clickAndTypeStyle", "defaultTableStyle", "evenAndOddHeaders", "bookFoldRevPrinting", "bookFoldPrinting",
    "bookFoldPrintingSheets", "drawingGridHorizontalSpacing", "drawingGridVerticalSpacing",
    "displayHorizontalDrawingGridEvery", "displayVerticalDrawingGridEvery", "doNotUseMarginsForDrawingGridOrigin",
    "drawingGridHorizontalOrigin", "drawingGridVerticalOrigin", "doNotShadeFormData", "noPunctuationKerning",
    "characterSpacingControl", "printTwoOnOne", "strictFirstAndLastChars", "noLineBreaksAfter", "noLineBreaksBefore",
    "savePreviewPicture", "doNotValidateAgainstSchema", "saveInvalidXml", "ignoreMixedContent",
    "alwaysShowPlaceholderText", "doNotDemarcateInvalidXml", "saveXmlDataOnly", "useXSLTWhenSaving",
    "saveThroughXslt", "showXMLTags", "alwaysMergeEmptyNamespace", "updateFields", "hdrShapeDefaults",
    "footnotePr", "endnotePr", "compat", "docVars", "rsids", "mathPr", "attachedSchema", "themeFontLang",
    "clrSchemeMapping", "doNotIncludeSubdocsInStats", "doNotAutoCompressPictures", "forceUpgrade", "captions",
    "readModeInkLockDown", "smartTagType", "schemaLibrary", "shapeDefaults", "doNotEmbedSmartTags",
    "decimalSymbol", "listSeparator"]
TBLPR_ORDER = ["tblStyle", "tblpPr", "tblOverlap", "bidiVisual", "tblStyleRowBandSize", "tblStyleColBandSize",
    "tblW", "jc", "tblCellSpacing", "tblInd", "tblBorders", "shd", "tblLayout", "tblCellMar", "tblLook",
    "tblCaption", "tblDescription"]


def reorder(parent, order):
    """Sorts children into the schema order Word validates against (unknown elements keep their place at the end)."""
    rank = {n: i for i, n in enumerate(order)}
    kids = list(parent)
    def key(c):
        local = c.tag.split("}")[-1]
        return rank.get(local, len(order))
    for c in kids:
        parent.remove(c)
    for c in sorted(kids, key=key):
        parent.append(c)


def rgb(h):
    return RGBColor.from_string(h.upper())


def include(md_path, seen=None):
    seen = seen or set()
    base = os.path.dirname(os.path.abspath(md_path))
    out = []
    for line in open(md_path, encoding="utf-8").read().splitlines():
        m = re.match(r"^\s*\{\{\s*include\s+(.+?)\s*\}\}\s*$", line)
        if m:
            p = os.path.normpath(os.path.join(base, m.group(1)))
            if not os.path.exists(p):
                sys.exit(f"include not found: {m.group(1)} (from {md_path})")
            if p in seen:
                sys.exit(f"recursive include: {p}")
            out.append(include(p, seen | {p}))
        else:
            out.append(line)
    return "\n".join(out)


def set_style_font(style, cfg, size=None, bold=None, color=None):
    f = style.font
    f.name = cfg["font"]
    if size:
        f.size = Pt(size)
    if bold is not None:
        f.bold = bold
    f.color.rgb = rgb(color or cfg["text"])
    rpr = style.element.get_or_add_rPr()
    rf = rpr.find(qn("w:rFonts"))
    if rf is None:
        rf = OxmlElement("w:rFonts")
        rpr.insert(0, rf)
    for k in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rf.set(qn(k), cfg["font"])
    for k in ("w:asciiTheme", "w:hAnsiTheme", "w:cstheme", "w:eastAsiaTheme"):
        if rf.get(qn(k)) is not None:
            del rf.attrib[qn(k)]


AFTER_PBDR = ("w:shd", "w:tabs", "w:suppressAutoHyphens", "w:kinsoku", "w:wordWrap", "w:overflowPunct",
              "w:topLinePunct", "w:autoSpaceDE", "w:autoSpaceDN", "w:bidi", "w:adjustRightInd", "w:snapToGrid",
              "w:spacing", "w:ind", "w:contextualSpacing", "w:mirrorIndents", "w:suppressOverlap", "w:jc",
              "w:textDirection", "w:textAlignment", "w:textboxTightWrap", "w:outlineLvl", "w:divId",
              "w:cnfStyle", "w:rPr", "w:sectPr", "w:pPrChange")


def border(el_pr, side, sz, color, tag="w:pBdr"):
    bd = el_pr.find(qn(tag))
    if bd is None:
        bd = OxmlElement(tag)
        later = next((c for c in el_pr if c.tag in {qn(x) for x in AFTER_PBDR}), None)
        if later is not None:
            later.addprevious(bd)
        else:
            el_pr.append(bd)
    b = OxmlElement(f"w:{side}")
    b.set(qn("w:val"), "single")
    b.set(qn("w:sz"), str(sz))
    b.set(qn("w:space"), "4")
    b.set(qn("w:color"), color)
    bd.append(b)


def field(run, instr):
    """Inserts a complex field (begin / instr / separate / placeholder / end) as separate runs after `run`,
    each carrying `run`'s formatting, so the rendered value keeps the font size and colour."""
    rpr = run._r.find(qn("w:rPr"))
    anchor = run._r
    for kind in ("begin", "instr", "separate", "text", "end"):
        r = OxmlElement("w:r")
        if rpr is not None:
            r.append(copy.deepcopy(rpr))
        if kind in ("begin", "separate", "end"):
            fc = OxmlElement("w:fldChar")
            fc.set(qn("w:fldCharType"), kind)
            r.append(fc)
        elif kind == "instr":
            it = OxmlElement("w:instrText")
            it.set(qn("xml:space"), "preserve")
            it.text = f" {instr} "
            r.append(it)
        else:
            tt = OxmlElement("w:t")
            tt.text = "1"
            r.append(tt)
        anchor.addnext(r)
        anchor = r


def shade(cell, color):
    tcpr = cell._tc.get_or_add_tcPr()
    sh = OxmlElement("w:shd")
    sh.set(qn("w:val"), "clear")
    sh.set(qn("w:color"), "auto")
    sh.set(qn("w:fill"), color)
    tcpr.append(sh)


def style_table(tbl, cfg, header=True):
    tblpr = tbl._tbl.tblPr
    for old in tblpr.findall(qn("w:tblBorders")):
        tblpr.remove(old)
    bds = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        b = OxmlElement(f"w:{side}")
        b.set(qn("w:val"), "single")
        b.set(qn("w:sz"), "4")
        b.set(qn("w:color"), "BFBFBF")
        bds.append(b)
    tblpr.append(bds)
    tw = tblpr.find(qn("w:tblW"))
    if tw is None:
        tw = OxmlElement("w:tblW")
        tblpr.append(tw)
    tw.set(qn("w:type"), "pct")
    tw.set(qn("w:w"), "5000")
    reorder(tblpr, TBLPR_ORDER)
    for i, row in enumerate(tbl.rows):
        is_head = header and i == 0
        if is_head:
            trpr = row._tr.get_or_add_trPr()
            th = OxmlElement("w:tblHeader")
            trpr.append(th)
        for cell in row.cells:
            if is_head:
                shade(cell, cfg["primary"])
            elif i % 2 == 0:
                shade(cell, cfg["zebra"])
            for p in cell.paragraphs:
                p.paragraph_format.space_before = Pt(1)
                p.paragraph_format.space_after = Pt(1)
                for r in p.runs:
                    r.font.size = Pt(9)
                    r.font.name = cfg["font"]
                    if is_head:
                        r.font.bold = True
                        r.font.color.rgb = rgb("FFFFFF")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--out")
    ap.add_argument("--pdf", action="store_true")
    a = ap.parse_args()
    cfg = {"doc_title": "Board technical documentation", "subtitle": "", "cover_lines": [], "metadata": [],
           "company": "", "date": "", "logo": None, "primary": "1F4E79", "accent": "2E75B6", "zebra": "F7F9FA",
           "text": "292929", "muted": "6D6D6D", "font": "Calibri", "page": "A4"}
    cfg.update(json.load(open(a.config, encoding="utf-8")))
    if "product" not in cfg:
        sys.exit("config needs 'product'")
    cfg_dir = os.path.dirname(os.path.abspath(a.config))
    if cfg.get("logo") and not os.path.isabs(cfg["logo"]):
        cfg["logo"] = os.path.normpath(os.path.join(cfg_dir, cfg["logo"]))
    slug = re.sub(r"[^A-Za-z0-9]+", "_", cfg["product"]).strip("_")
    out = a.out or os.path.join("DOC", f"{slug}_Technical_Documentation.docx")
    if not shutil.which("pandoc"):
        sys.exit("pandoc not found")

    tmp = tempfile.mkdtemp()
    md = os.path.join(tmp, "doc.md")
    open(md, "w", encoding="utf-8").write(include(a.source))
    body = os.path.join(tmp, "body.docx")
    r = subprocess.run(["pandoc", md, "-f", "markdown+pipe_tables+grid_tables-implicit_figures", "-o", body],
                       capture_output=True, text=True, cwd=os.path.dirname(os.path.abspath(a.source)))
    if r.returncode:
        sys.exit("pandoc failed: " + r.stderr)

    d = Document(body)
    sec = d.sections[0]
    if cfg["page"].upper() == "A4":
        sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    else:
        sec.page_width, sec.page_height = Cm(21.59), Cm(27.94)
    for m in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(sec, m, Cm(2.54))
    text_w = sec.page_width - sec.left_margin - sec.right_margin

    st = d.styles

    def find_style(name):
        for s in st:
            if s.name and (s.name.lower() == name.lower() or (s.style_id or "").lower() == name.replace(" ", "").lower()):
                return s
        return None
    for name, size in (("Normal", 10.5), ("Body Text", 10.5), ("First Paragraph", 10.5), ("Compact", 10.5)):
        s = find_style(name)
        if s is not None:
            set_style_font(s, cfg, size=size)
    for name, size, color in (("Heading 1", 16, cfg["primary"]), ("Heading 2", 13, cfg["accent"]),
                              ("Heading 3", 11, cfg["primary"]), ("Heading 4", 10.5, cfg["accent"])):
        s = find_style(name)
        if s is not None:
            set_style_font(s, cfg, size=size, bold=True, color=color)
            s.font.italic = False
            s.paragraph_format.space_before = Pt(14 if name == "Heading 1" else 10)
            s.paragraph_format.space_after = Pt(6)
            s.paragraph_format.keep_with_next = True
            if name == "Heading 1":
                s.paragraph_format.page_break_before = True
    for s in st:
        if s.name in ("Source Code", "Verbatim Char"):
            s.font.size = Pt(8.5)

    for t in d.tables:
        style_table(t, cfg)

    # ---------- cover, metadata table, TOC (inserted before the first body element) ----------
    first = d.element.body[0]

    def para_before(text="", size=None, bold=False, color=None, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=6):
        p = d.add_paragraph()
        first.addprevious(p._p)
        p.alignment = align
        p.paragraph_format.space_after = Pt(space_after)
        if text:
            run = p.add_run(text)
            run.font.name = cfg["font"]
            run.font.bold = bold
            if size:
                run.font.size = Pt(size)
            run.font.color.rgb = rgb(color or cfg["text"])
        return p

    for _ in range(6):
        para_before()
    para_before(cfg["doc_title"].upper(), 22, True, cfg["primary"], space_after=10)
    para_before(cfg["product"], 16, True, cfg["primary"], space_after=10)
    if cfg["subtitle"]:
        para_before(cfg["subtitle"], 11.5, False, cfg["text"])
    for i, line in enumerate(cfg["cover_lines"]):
        para_before(line, 10, False, cfg["muted"] if i == 0 else cfg["text"])
    para_before()
    if cfg["metadata"]:
        mt = d.add_table(rows=len(cfg["metadata"]), cols=2)
        first.addprevious(mt._tbl)
        for i, (k, v) in enumerate(cfg["metadata"]):
            c0, c1 = mt.rows[i].cells
            c0.text, c1.text = str(k), str(v)
            c0.width, c1.width = Emu(int(text_w * 0.3)), Emu(int(text_w * 0.7))
            for p in c0.paragraphs:
                for rr in p.runs:
                    rr.font.bold = True
        style_table(mt, cfg, header=False)
        mt.autofit = False
        for col, frac in zip(mt.columns, (0.3, 0.7)):
            col.width = Emu(int(text_w * frac))
        grid = mt._tbl.tblGrid
        for gc, frac in zip(grid.findall(qn("w:gridCol")), (0.3, 0.7)):
            gc.set(qn("w:w"), str(int(text_w * frac / 635)))
    pb = para_before()
    pb.add_run().add_break(WD_BREAK.PAGE)
    para_before("Contents", 14, True, cfg["primary"], align=WD_ALIGN_PARAGRAPH.LEFT)
    tp = para_before(align=WD_ALIGN_PARAGRAPH.LEFT)
    field(tp.add_run(), 'TOC \\o "1-2" \\h \\z \\u')
    # Heading 1 already breaks the page before the first section.

    # ---------- header and footer ----------
    sec.header_distance = Cm(1.25)
    sec.footer_distance = Cm(1.25)
    hp = sec.header.paragraphs[0]
    hp.text = ""
    hp.paragraph_format.tab_stops.add_tab_stop(text_w, WD_TAB_ALIGNMENT.RIGHT)
    if cfg.get("logo") and os.path.exists(cfg["logo"]):
        hp.add_run().add_picture(cfg["logo"], height=Cm(0.9))
    hr = hp.add_run(f"\t{cfg['product']} — {cfg['doc_title']}")
    hr.font.size = Pt(8)
    hr.font.name = cfg["font"]
    hr.font.color.rgb = rgb(cfg["muted"])
    border(hp._p.get_or_add_pPr(), "bottom", 8, cfg["primary"])

    fp = sec.footer.paragraphs[0]
    fp.text = ""
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    border(fp._p.get_or_add_pPr(), "top", 6, cfg["accent"])

    def frun(text, bold=False, color=None):
        rr = fp.add_run(text)
        rr.font.size = Pt(8)
        rr.font.name = cfg["font"]
        rr.font.bold = bold
        rr.font.color.rgb = rgb(color or cfg["muted"])
        return rr
    if cfg["company"]:
        frun(cfg["company"], True, cfg["primary"])
        frun("   ·   ")
    frun(f"{cfg['doc_title']} — {cfg['product']}")
    if cfg["date"]:
        frun(f"   ·   {cfg['date']}")
    frun("   ·   Page ")
    field(frun(""), "PAGE")
    frun(" of ")
    field(frun(""), "NUMPAGES")

    # ask Word to refresh the TOC and page fields on open
    settings = d.settings.element
    uf = OxmlElement("w:updateFields")
    uf.set(qn("w:val"), "true")
    nxt = next((c for c in settings if c.tag in {qn(x) for x in ("w:hdrShapeDefaults", "w:footnotePr", "w:endnotePr",
                "w:compat", "w:docVars", "w:rsids", "w:themeFontLang", "w:clrSchemeMapping", "w:decimalSymbol",
                "w:listSeparator")}), None)
    if nxt is not None:
        nxt.addprevious(uf)
    else:
        settings.append(uf)
    d.core_properties.title = f"{cfg['product']} — {cfg['doc_title']}"
    d.core_properties.author = cfg["company"] or ""

    reorder(settings, SETTINGS_ORDER)
    for pm in d.element.body.iter(qn("w:pgMar")):
        if pm.get(qn("w:gutter")) is None:
            pm.set(qn("w:gutter"), "0")
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    d.save(out)
    print(f"Wrote {out}")

    if a.pdf:
        refreshed = refresh_and_pdf(out)
        print(refreshed)
    shutil.rmtree(tmp, ignore_errors=True)


UNO_SCRIPT = r'''
import sys, uno
from com.sun.star.beans import PropertyValue
def prop(n, v):
    p = PropertyValue(); p.Name = n; p.Value = v; return p
src, docx_out, pdf_out = sys.argv[1:4]
local = uno.getComponentContext()
resolver = local.ServiceManager.createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver", local)
ctx = resolver.resolve("uno:socket,host=localhost,port=2083;urp;StarOffice.ComponentContext")
desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
doc = desktop.loadComponentFromURL(uno.systemPathToFileUrl(src), "_blank", 0, (prop("Hidden", True),))
idx = doc.getDocumentIndexes()
for i in range(idx.getCount()):
    idx.getByIndex(i).update()
doc.getTextFields().refresh()
doc.storeToURL(uno.systemPathToFileUrl(docx_out), (prop("FilterName", "MS Word 2007 XML"),))
doc.storeToURL(uno.systemPathToFileUrl(pdf_out), (prop("FilterName", "writer_pdf_Export"),))
doc.close(True)
'''


def refresh_and_pdf(docx_path):
    """Writes a review PDF next to the .docx with the TOC and page fields updated (LibreOffice via UNO).
    The .docx itself is not round-tripped through LibreOffice, so its styling stays exactly as built."""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return "PDF skipped: LibreOffice not found (the TOC updates when the file is opened in Word)."
    import time
    docx_path = os.path.abspath(docx_path)
    pdf = os.path.splitext(docx_path)[0] + ".pdf"
    prof = tempfile.mkdtemp()
    proc = subprocess.Popen([soffice, f"-env:UserInstallation=file://{prof}", "--headless", "--invisible",
                             "--norestore", '--accept=socket,host=localhost,port=2083;urp;'],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    script = os.path.join(prof, "refresh.py")
    open(script, "w").write(UNO_SCRIPT)
    tmp_docx = docx_path + ".refreshed.docx"
    ok = False
    py = shutil.which("python3")
    for _ in range(30):
        time.sleep(1)
        r = subprocess.run([py, script, docx_path, tmp_docx, pdf], capture_output=True, text=True)
        if r.returncode == 0:
            ok = True
            break
    proc.terminate()
    if os.path.exists(tmp_docx):
        os.remove(tmp_docx)  # the delivered .docx stays as built; Word refreshes its TOC on open (updateFields)
    if ok:
        return f"Wrote {pdf} (TOC updated in the PDF)"
    r = subprocess.run([soffice, f"-env:UserInstallation=file://{prof}", "--headless", "--convert-to", "pdf",
                        "--outdir", os.path.dirname(docx_path), docx_path], capture_output=True, text=True)
    return (f"Wrote {pdf} (plain conversion; TOC updates when opened in Word)" if os.path.exists(pdf)
            else "PDF conversion failed: " + r.stderr[-300:])


if __name__ == "__main__":
    main()
