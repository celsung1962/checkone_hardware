#!/usr/bin/env python3
"""
Datasheet library manager: keeps docs/datasheets/manifest.csv and the files it lists.

The agent finds the official URL (manufacturer site first, then a major distributor);
this script downloads, verifies, fingerprints and text-extracts the file, and checks
that every part in the KiCad project has its datasheet on disk.

Usage:
    fetch_datasheets.py add     <manifest> --part ADS131M06 --manufacturer "Texas Instruments" \
                                --url https://www.ti.com/lit/gpn/ads131m06 [--doc-type datasheet] [--notes "..."]
    fetch_datasheets.py add     <manifest> --part TPS7A3001 --doc-type eval_board --none "none published (ti.com, 2026-11-13)"
    fetch_datasheets.py fetch   <manifest> [--force] [--part NAME]
    fetch_datasheets.py import  <manifest> <local.pdf> --part NAME [--manufacturer M] [--doc-type T] [--url U]
    fetch_datasheets.py from-kicad <manifest> <kicad_project_dir>
    fetch_datasheets.py check   <manifest> [--kicad <kicad_project_dir>] [--eval-board]
                                [--no-datasheet-footprint REGEX ...]

doc_type: datasheet | errata | app_note | hw_design_guide | user_guide | eval_board | reference_design | other
          (eval_board = the maker's evaluation-board / EVM user guide with its schematic)
status:   todo | ok | failed:<reason> | manual | none
          (manual = placed by hand with `import`; none = the document does not exist, `add --none "<reason>"`:
           allowed for eval_board / reference_design / app_note rows, with the reason in notes)

--eval-board (check): every IC of the schematic (reference U / IC / PS) must have an evaluation-board or reference
design document on disk (eval_board, user_guide, reference_design or hw_design_guide) or an eval_board row with
status none. Without the flag the missing ones are only counted.
--no-datasheet-footprint: footprints that are bare copper (wire pads, probe pads) and need no datasheet, whatever
their reference; default ^Connector_Wire:SolderWirePad_ .

Files are saved next to the manifest as <PART>_<doc_type>.pdf, plus a .txt text
extraction (pdftotext -layout, if installed) so pin tables can be grepped.
`check` exits non-zero if any row is not ok/manual or a KiCad part has no datasheet.
"""
import argparse, csv, datetime, hashlib, os, re, shutil, subprocess, sys, urllib.request, urllib.error
from urllib.parse import urlparse

FIELDS = ["part", "manufacturer", "doc_type", "url", "filename", "revision", "sha256", "retrieved", "status", "notes"]
AGGREGATORS = ("alldatasheet", "datasheetspdf", "datasheet4u", "datasheetarchive", "datasheetcatalog",
               "datasheets360", "pdf1.alldatasheet", "icpdf", "datasheet.octopart")
UA = "Mozilla/5.0 (X11; Linux x86_64) kicad-schematic-skill/1.0 (datasheet fetch for engineering use)"


def load(path):
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return [{k: (r.get(k) or "") for k in FIELDS} for r in csv.DictReader(f)]


def save(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        for r in sorted(rows, key=lambda r: (r["part"].lower(), r["doc_type"])):
            w.writerow(r)


def safe(s):
    return re.sub(r"[^A-Za-z0-9._+-]+", "_", s).strip("_")


def fname(row):
    return row["filename"] or f"{safe(row['part'])}_{safe(row['doc_type'] or 'datasheet')}.pdf"


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 16), b""):
            h.update(b)
    return h.hexdigest()


def extract_text(pdf):
    txt = os.path.splitext(pdf)[0] + ".txt"
    if shutil.which("pdftotext"):
        r = subprocess.run(["pdftotext", "-layout", pdf, txt], capture_output=True)
        if r.returncode == 0:
            return txt
    return ""


def guess_revision(txt):
    if not txt or not os.path.exists(txt):
        return ""
    head = open(txt, encoding="utf-8", errors="ignore").read(20000)
    m = re.search(r"\b(S[A-Z]{3}\d{3,4}[A-Z]?)\b", head)                   # TI literature number (e.g. SBAS949A)
    m = m or re.search(r"\bRev(?:ision)?\.?\s*([0-9A-Z][0-9A-Z.]{0,5})\b", head)
    m = m or re.search(r"\bVersion\s+([0-9][0-9.]{0,5})\b", head)
    return m.group(1) if m else ""


def is_aggregator(url):
    host = urlparse(url).netloc.lower()
    return any(a in host for a in AGGREGATORS)


def cmd_add(a):
    rows = load(a.manifest)
    dt = a.doc_type or "datasheet"
    if a.none is not None:
        if dt not in NONE_OK:
            sys.exit(f"--none is only for {', '.join(sorted(NONE_OK))} rows (a datasheet always exists)")
        if not a.none.strip():
            sys.exit('--none needs the reason, e.g. --none "none published (ti.com, 2026-11-13)"')
    for r in rows:
        if r["part"].lower() == a.part.lower() and r["doc_type"] == dt:
            if a.url:
                r["url"] = a.url
                r["status"] = "todo"
            r["manufacturer"] = a.manufacturer or r["manufacturer"]
            r["notes"] = a.notes or r["notes"]
            if a.none is not None:
                r.update(status="none", notes=a.none.strip(), url="", filename="", sha256="",
                         retrieved=datetime.date.today().isoformat())
            print(f"updated {a.part} ({dt})")
            break
    else:
        rows.append({**{k: "" for k in FIELDS}, "part": a.part, "manufacturer": a.manufacturer or "",
                     "doc_type": dt, "url": a.url or "", "status": "todo", "notes": a.notes or ""})
        if a.none is not None:
            rows[-1].update(status="none", notes=a.none.strip(), retrieved=datetime.date.today().isoformat())
        print(f"added {a.part} ({dt})" + (" - none: " + a.none.strip() if a.none is not None else ""))
    if a.url and is_aggregator(a.url):
        print("  WARNING: aggregator site — find the manufacturer's official URL instead.")
    save(a.manifest, rows)


def download(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/pdf,*/*"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
        ctype = resp.headers.get("Content-Type", "")
    if not data.startswith(b"%PDF"):
        kind = "HTML page" if b"<html" in data[:2000].lower() else f"'{ctype or 'unknown'}' content"
        raise ValueError(f"not a PDF ({kind}; probably a landing/login/captcha page — find the direct PDF link)")
    if len(data) < 20_000:
        print(f"  note: small file ({len(data)} bytes) — confirm it is the full datasheet")
    tmp = dest + ".part"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, dest)
    return len(data)


def cmd_fetch(a):
    rows = load(a.manifest)
    base = os.path.dirname(os.path.abspath(a.manifest))
    ok = fail = skip = 0
    for r in rows:
        if a.part and r["part"].lower() != a.part.lower():
            continue
        if r["status"] in ("ok", "manual", "none") and not a.force:
            skip += 1
            continue
        if not r["url"]:
            r["status"] = "failed:no_url"
            fail += 1
            print(f"FAIL {r['part']}: no URL — search the manufacturer site and `add --url`")
            continue
        dest = os.path.join(base, fname(r))
        try:
            n = download(r["url"], dest)
            txt = extract_text(dest)
            r.update(filename=os.path.basename(dest), sha256=sha(dest),
                     retrieved=datetime.date.today().isoformat(), status="ok",
                     revision=guess_revision(txt) or r["revision"])
            ok += 1
            warn = "  (aggregator site — replace with manufacturer URL)" if is_aggregator(r["url"]) else ""
            print(f"OK   {r['part']} ({r['doc_type']}): {os.path.basename(dest)}, {n/1024:.0f} kB"
                  f"{', text extracted' if txt else ''}{warn}")
        except (urllib.error.HTTPError, urllib.error.URLError, ValueError, TimeoutError, OSError) as e:
            reason = getattr(e, "code", None) or type(e).__name__
            r["status"] = f"failed:{reason}"
            fail += 1
            print(f"FAIL {r['part']} ({r['doc_type']}): {e}")
    save(a.manifest, rows)
    print(f"\n{ok} downloaded, {skip} already present, {fail} failed")
    if fail:
        print("Failed items: find a direct PDF link and `add --url` again, or download by hand and `import`.")
        sys.exit(1)


def cmd_import(a):
    rows = load(a.manifest)
    base = os.path.dirname(os.path.abspath(a.manifest))
    with open(a.file, "rb") as f:
        if not f.read(4).startswith(b"%PDF"):
            sys.exit("Not a PDF file.")
    dt = a.doc_type or "datasheet"
    row = next((r for r in rows if r["part"].lower() == a.part.lower() and r["doc_type"] == dt), None)
    if row is None:
        row = {**{k: "" for k in FIELDS}, "part": a.part, "doc_type": dt}
        rows.append(row)
    row["manufacturer"] = a.manufacturer or row["manufacturer"]
    row["url"] = a.url or row["url"]
    dest = os.path.join(base, fname(row))
    if os.path.abspath(a.file) != os.path.abspath(dest):
        shutil.copyfile(a.file, dest)
    txt = extract_text(dest)
    row.update(filename=os.path.basename(dest), sha256=sha(dest), retrieved=datetime.date.today().isoformat(),
               status="manual", revision=row["revision"] or guess_revision(txt))
    save(a.manifest, rows)
    print(f"imported {a.part} ({dt}) → {os.path.basename(dest)}")


PASSIVE_REF = re.compile(r"^(R|RR|C|L|FB|RV|TP|TC|MH|FID|H|JP|NT)\d", re.I)
# copper pads with no part number (solder-wire pads, probe pads) need no datasheet, whatever their reference prefix;
# more patterns with --no-datasheet-footprint
PAD_FOOTPRINT_DEFAULT = [r"^Connector_Wire:SolderWirePad_"]
IC_REF = re.compile(r"^(U|IC|PS)\d", re.I)
EVAL_TYPES = ("eval_board", "user_guide", "reference_design", "hw_design_guide")
NONE_OK = ("eval_board", "reference_design", "app_note")


def kicad_parts(folder, pad_footprints=None):
    pad = re.compile("|".join(f"(?:{p})" for p in (pad_footprints or PAD_FOOTPRINT_DEFAULT)))
    try:
        import sexpdata
        from sexpdata import Symbol
    except ImportError:
        sys.exit("Install sexpdata: pip install sexpdata --break-system-packages")

    def n(x):
        return x[0].value() if isinstance(x, list) and x and isinstance(x[0], Symbol) else None
    parts = {}
    for root, _, files in os.walk(folder):
        if any(s in root for s in (".history", "-backups")):
            continue
        for f in files:
            if not f.endswith(".kicad_sch"):
                continue
            tree = sexpdata.loads(open(os.path.join(root, f), encoding="utf-8").read())
            for s in tree:
                if n(s) != "symbol":
                    continue
                props = {p[1]: p[2] for p in s if n(p) == "property" and len(p) > 2}
                ref = props.get("Reference", "")
                lib = next((c[1] for c in s if n(c) == "lib_id"), "")
                if not ref or ref.startswith("#") or PASSIVE_REF.match(ref) or str(lib).startswith("power:"):
                    continue
                if pad.search(str(props.get("Footprint", ""))):
                    continue
                val = props.get("Value", "").strip()
                if val:
                    parts.setdefault(val, {"refs": [], "url": props.get("Datasheet", "").strip()})["refs"].append(ref)
    return parts


def cmd_from_kicad(a):
    rows = load(a.manifest)
    have = {r["part"].lower() for r in rows}
    added = 0
    for val, info in sorted(kicad_parts(a.kicad).items()):
        if val.lower() in have:
            continue
        url = info["url"] if info["url"].startswith("http") else ""
        rows.append({**{k: "" for k in FIELDS}, "part": val, "doc_type": "datasheet", "url": url, "status": "todo",
                     "notes": "from KiCad: " + ",".join(sorted(info["refs"])[:6])})
        added += 1
        print(f"added {val} ({', '.join(sorted(info['refs'])[:4])}){' url from Datasheet field' if url else ' — needs URL'}")
    save(a.manifest, rows)
    print(f"\n{added} part(s) added from {a.kicad}")


def cmd_check(a):
    rows = load(a.manifest)
    base = os.path.dirname(os.path.abspath(a.manifest))
    bad = []
    notes = []
    for r in rows:
        path = os.path.join(base, r["filename"]) if r["filename"] else ""
        if r["status"] == "none":
            if r["doc_type"] not in NONE_OK:
                bad.append(f"{r['part']} ({r['doc_type']}): status none is only for {', '.join(NONE_OK)} rows")
            elif not r["notes"].strip():
                bad.append(f"{r['part']} ({r['doc_type']}): status none without the reason in notes")
            continue
        if r["status"] not in ("ok", "manual"):
            bad.append(f"{r['part']} ({r['doc_type']}): status {r['status'] or 'empty'}")
        elif not path or not os.path.exists(path):
            bad.append(f"{r['part']} ({r['doc_type']}): file missing on disk")
        elif r["sha256"] and sha(path) != r["sha256"]:
            bad.append(f"{r['part']} ({r['doc_type']}): file changed since it was recorded (sha256 mismatch)")
        if r["url"] and is_aggregator(r["url"]):
            bad.append(f"{r['part']} ({r['doc_type']}): aggregator URL — replace with the manufacturer's")
    if a.kicad:
        have = {r["part"].lower() for r in rows if r["doc_type"] == "datasheet"}
        evald = {r["part"].lower() for r in rows if (r["doc_type"] in EVAL_TYPES and r["status"] in ("ok", "manual"))
                 or (r["doc_type"] == "eval_board" and r["status"] == "none")}
        no_eval = []
        for val, info in sorted(kicad_parts(a.kicad, a.no_datasheet_footprint).items()):
            refs = ", ".join(sorted(info["refs"])[:4])
            if val.lower() not in have:
                bad.append(f"{val} ({refs}): in the schematic but no datasheet in the manifest")
            if any(IC_REF.match(r) for r in info["refs"]) and val.lower() not in evald:
                no_eval.append(f"{val} ({refs}): IC without an evaluation-board / reference-design document "
                               f"or an eval_board row 'none' (add --doc-type eval_board, or --none \"<reason>\")")
        if a.eval_board:
            bad += no_eval
        elif no_eval:
            notes.append(f"{len(no_eval)} IC(s) without an evaluation-board document - not enforced "
                         f"(check --eval-board): {', '.join(x.split(' (')[0] for x in no_eval)[:300]}")
    print(f"{len(rows)} documents in the manifest")
    for n_ in notes:
        print("NOTE", n_)
    if bad:
        print(f"FAIL — {len(bad)} problem(s):")
        for b in bad:
            print("  -", b)
        sys.exit(1)
    print("PASS — every document is on disk and every schematic part has its datasheet.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("add"); p.add_argument("manifest"); p.add_argument("--part", required=True)
    p.add_argument("--manufacturer"); p.add_argument("--url"); p.add_argument("--doc-type"); p.add_argument("--notes")
    p.add_argument("--none", metavar="REASON", help="the document does not exist (eval_board / reference_design / "
                                                    "app_note rows): status none, reason in notes")
    p = sp.add_parser("fetch"); p.add_argument("manifest"); p.add_argument("--force", action="store_true"); p.add_argument("--part")
    p = sp.add_parser("import"); p.add_argument("manifest"); p.add_argument("file"); p.add_argument("--part", required=True)
    p.add_argument("--manufacturer"); p.add_argument("--doc-type"); p.add_argument("--url")
    p = sp.add_parser("from-kicad"); p.add_argument("manifest"); p.add_argument("kicad")
    p = sp.add_parser("check"); p.add_argument("manifest"); p.add_argument("--kicad")
    p.add_argument("--eval-board", action="store_true", help="FAIL for an IC without an evaluation-board document")
    p.add_argument("--no-datasheet-footprint", action="append", metavar="REGEX",
                   help="footprint pattern of bare copper pads that need no datasheet (repeatable; replaces the default)")
    a = ap.parse_args()
    {"add": cmd_add, "fetch": cmd_fetch, "import": cmd_import, "from-kicad": cmd_from_kicad, "check": cmd_check}[a.cmd](a)


if __name__ == "__main__":
    main()
