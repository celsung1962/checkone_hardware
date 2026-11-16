#!/usr/bin/env python3
"""
Extracts the conventions of a reference KiCad project and prints a Markdown report.

Usage:
    python3 analyze_kicad_project.py <project_folder> [--include-orphans]

Requires: sexpdata (pip install sexpdata --break-system-packages)

The report is raw material: turning it into rules (majority form,
discarded forms, defects not to copy) is done by whoever writes the brief.
"""
import sys, os, re, glob, json, sqlite3, collections, argparse

try:
    import sexpdata
    from sexpdata import Symbol
except ImportError:
    sys.exit("Install sexpdata: pip install sexpdata --break-system-packages")

STD_FIELDS = {"Reference", "Value", "Footprint", "Datasheet", "Description"}
IGNORE_PATTERNS = [r"/\.history/", r"-backups/", r"_old$", r"-bak$", r"\.bak$"]


def name(x):
    return x[0].value() if isinstance(x, list) and x and isinstance(x[0], Symbol) else None


def find(x, n):
    return [c for c in x if name(c) == n]


def get(x, n):
    r = find(x, n)
    return r[0] if r else None


def load_sch(path):
    with open(path, encoding="utf-8") as f:
        return sexpdata.loads(f.read())


def props_of(sym):
    return {p[1]: p[2] for p in find(sym, "property") if len(p) > 2}


def is_virtual(props, lib):
    return props.get("Reference", "").startswith("#") or lib.startswith("power:")


def is_power(props, lib, libsym_power):
    return props.get("Reference", "").startswith("#PWR") or lib.startswith("power:") or lib in libsym_power


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--include-orphans", action="store_true")
    a = ap.parse_args()
    root = os.path.abspath(a.folder)

    pros = [p for p in glob.glob(os.path.join(root, "*.kicad_pro"))]
    if not pros:
        sys.exit("No .kicad_pro in the folder.")
    pro_path = pros[0]
    base = os.path.splitext(os.path.basename(pro_path))[0]
    top_file = base + ".kicad_sch"

    files = sorted(os.path.basename(p) for p in glob.glob(os.path.join(root, "*.kicad_sch"))
                   if not any(re.search(pt, p) for pt in IGNORE_PATTERNS))
    D = {}
    for f in files:
        try:
            D[f] = load_sch(os.path.join(root, f))
        except Exception as e:
            print(f"> Warning: failed to read {f}: {e}", file=sys.stderr)

    out = []
    P = out.append
    P(f"# Guidelines extracted from `{base}`\n")

    # ---------- hierarchy ----------
    referenced = {top_file}
    sheet_rows = []
    for f, d in D.items():
        for s in find(d, "sheet"):
            pr = props_of(s)
            sf = pr.get("Sheetfile", "")
            referenced.add(sf)
            sheet_rows.append((f, pr.get("Sheetname", ""), sf, len(find(s, "pin"))))
    orphans = [f for f in D if f not in referenced]
    if not a.include_orphans:
        for f in orphans:
            D.pop(f, None)
    file_uses = collections.Counter(r[2] for r in sheet_rows)
    depth_ok = all(r[0] == top_file for r in sheet_rows)

    P("## 1. Project and hierarchy\n")
    gv = collections.Counter(str(get(d, "generator_version")[1]) if get(d, "generator_version") else "?" for d in D.values())
    P(f"- KiCad version (generator_version): {dict(gv)}")
    P(f"- Root sheet: `{top_file}`; {'single-level' if depth_ok else 'multi-level'} hierarchy")
    P(f"- Orphan sheets (not referenced, ignored): {orphans or 'none'}")
    multi = {k: v for k, v in file_uses.items() if v > 1}
    P(f"- Files instantiated more than once (multi-instance): {multi or 'none'}")
    dup = collections.defaultdict(list)
    for r in sheet_rows:
        m = re.match(r"(.+?)_?(\d+)\.kicad_sch$", r[2])
        if m:
            dup[m.group(1)].append(r[2])
    dup = {k: v for k, v in dup.items() if len(v) > 1}
    P(f"- Sheets duplicated by file copy (numeric suffix): {dup or 'none'}\n")
    P("| Sheet | File | Page | Sheet pins | Title block filled |")
    P("|---|---|---|---|---|")
    for f, d in D.items():
        pap = get(d, "paper")
        tb = get(d, "title_block")
        sn = next((r[1] for r in sheet_rows if r[2] == f), "(root)" if f == top_file else "?")
        pins = next((r[3] for r in sheet_rows if r[2] == f), "")
        P(f"| {sn} | `{f}` | {pap[1] if pap else '?'} | {pins} | {'yes' if tb and len(tb) > 1 else 'no'} |")
    P("")

    # ---------- symbols ----------
    libsym_power = set()
    for d in D.values():
        ls = get(d, "lib_symbols")
        if ls:
            for s in find(ls, "symbol"):
                if get(s, "power") is not None:
                    libsym_power.add(s[1])

    comps = []
    power = collections.Counter()
    for f, d in D.items():
        for s in find(d, "symbol"):
            lib = get(s, "lib_id")[1] if get(s, "lib_id") else "?"
            pr = props_of(s)
            if is_power(pr, lib, libsym_power):
                power[(lib, pr.get("Value", ""))] += 1
                continue
            if is_virtual(pr, lib):
                continue
            dn = get(s, "dnp")
            comps.append(dict(file=f, lib=lib, props=pr, dnp=bool(dn and str(dn[1]) == "yes")))

    n = len(comps)
    P(f"## 2. Components ({n})\n")
    fields = collections.Counter()
    fvals = collections.defaultdict(collections.Counter)
    fprefix = collections.defaultdict(set)
    for c in comps:
        pref = re.match(r"[A-Za-z_]+", c["props"].get("Reference", "?") + "?").group(0)
        for k, v in c["props"].items():
            fields[k] += 1
            fvals[k][v] += 1
            fprefix[k].add(pref)
    P("### Fields (presence)\n")
    P("| Field | Presence | Examples |")
    P("|---|---|---|")
    junk = []
    for k, cnt in fields.most_common():
        ex = [v for v, _ in fvals[k].most_common(3) if v][:3]
        pct = 100 * cnt / max(n, 1)
        if pct >= 1 or k in STD_FIELDS:
            P(f"| `{k}` | {cnt} ({pct:.0f} %) | {', '.join('`'+e[:40]+'`' for e in ex)} |")
        top_v, top_c = fvals[k].most_common(1)[0]
        if k not in STD_FIELDS and cnt > 0.3 * n and top_c > 0.9 * cnt and len(fprefix[k]) >= 3:
            junk.append((k, cnt, top_v))
    P("")
    P("### Fields suspected of copy inheritance (same value in ≥ 90 % of occurrences, on ≥ 3 component types)\n")
    if junk:
        P(f"**Do not copy** ({len(junk)} fields): " + ", ".join(
            f"`{k}` ({cnt}×, {'empty' if not v else '`'+v[:20]+'`'})" for k, cnt, v in junk))
    else:
        P("- none")
    P("")

    # libraries
    libs = collections.Counter(c["lib"].split(":")[0] for c in comps)
    P("### Symbol libraries\n")
    P(", ".join(f"`{k}` ({v})" for k, v in libs.most_common()))
    P("")
    fplibs = collections.Counter(c["props"].get("Footprint", "").split(":")[0] for c in comps)
    P("### Footprint libraries\n")
    P(", ".join(f"`{k or '(empty)'}` ({v})" for k, v in fplibs.most_common()))
    P("")

    # prefixes
    pref = collections.defaultdict(collections.Counter)
    for c in comps:
        r = c["props"].get("Reference", "")
        p = re.match(r"[A-Za-z_]+", r + "?").group(0)
        pref[p][c["lib"].split(":")[-1][:24]] += 1
    P("### Reference prefixes\n")
    P("| Prefix | Count | Most common symbols |")
    P("|---|---|---|")
    for p, cn in sorted(pref.items(), key=lambda x: -sum(x[1].values())):
        P(f"| `{p}` | {sum(cn.values())} | {', '.join(k for k, _ in cn.most_common(3))} |")
    P("")

    # passives
    sizes = collections.Counter()
    for c in comps:
        r = c["props"].get("Reference", "")
        m = re.search(r"_(\d{4})_\d{4}Metric", c["props"].get("Footprint", ""))
        if m and r[:1] in "RCL" and re.match(r"^[RCL]\d", r):
            sizes[(r[0], m.group(1))] += 1
    P("### Passive sizes\n")
    P(", ".join(f"{k[0]} {k[1]}: {v}" for k, v in sizes.most_common()) or "none")
    P("")

    # internal part number: non-standard fields present mostly on passives
    P("### Possible internal part-number fields (sample on passives)\n")
    for k, cnt in fields.most_common():
        if k in STD_FIELDS or k == "LCSC":
            continue
        passive_share = sum(1 for c in comps if k in c["props"] and re.match(r"^[RCL]\d", c["props"].get("Reference", "")))
        if cnt >= 0.2 * n and passive_share >= 0.7 * cnt and (k, cnt) not in [(j[0], j[1]) for j in junk]:
            vals = [v for v, _ in fvals[k].most_common(25) if v]
            P(f"- `{k}`: {', '.join('`'+v+'`' for v in vals)}")
    P("")

    lcsc_missing = [c["props"].get("Reference") for c in comps if not c["props"].get("LCSC", "").strip()]
    P(f"- Components with DNP: {sum(c['dnp'] for c in comps)}")
    P(f"- Components without `LCSC`: {len(lcsc_missing)} — {', '.join(lcsc_missing[:20])}{' …' if len(lcsc_missing) > 20 else ''}\n")

    # ---------- power ----------
    P("## 3. Power symbols (lib_id → Value = net name)\n")
    P("| lib_id | Value | Count | Note |")
    P("|---|---|---|---|")
    for (lib, val), cnt in power.most_common():
        base_name = lib.split(":")[-1]
        obs = []
        if lib.startswith("power:") and base_name not in (val, "PWR_FLAG") and val != "PWR_FLAG":
            obs.append("name ≠ value")
        if not lib.startswith("power:"):
            obs.append("non-standard library")
        P(f"| `{lib}` | `{val}` | {cnt} | {', '.join(obs)} |")
    P("")

    # ---------- labels ----------
    lab = collections.Counter(); hl = collections.Counter(); gl = collections.Counter()
    shapes = collections.Counter(); lsize = collections.Counter()
    for d in D.values():
        for l in find(d, "label"):
            lab[l[1]] += 1
            e = get(l, "effects"); fnt = get(e, "font") if e else None
            if fnt and get(fnt, "size"):
                lsize[tuple(get(fnt, "size")[1:])] += 1
        for l in find(d, "hierarchical_label"):
            hl[l[1]] += 1; shapes[str(get(l, "shape")[1]) if get(l, "shape") else "?"] += 1
        for l in find(d, "global_label"):
            gl[l[1]] += 1
    names = set(lab) | set(hl) | set(gl)
    P("## 4. Labels and net names\n")
    P(f"- Local: {len(lab)} names; hierarchical: {len(hl)}; global: {len(gl)}")
    P(f"- Hierarchical label shapes: {dict(shapes)}")
    P(f"- Label font size: {dict(lsize.most_common(3))}")
    prefixes = collections.Counter(x.split("_")[0] for x in names if "_" in x)
    P(f"- Most common prefixes: {', '.join(f'`{k}_` ({v})' for k, v in prefixes.most_common(12))}")
    n_pre = sorted(x for x in names if re.search(r"(^|_)n[A-Z]", x))
    n_suf = sorted(x for x in names if re.search(r"_N$", x))
    b_suf = sorted(x for x in names if re.search(r"(_B|#|~)$", x))
    diff_n = [x for x in n_suf if re.sub(r"_N$", "_P", x) in names]
    P(f"- Active-low with `n` prefix: {len(n_pre)} (e.g. {', '.join(n_pre[:6])})")
    P(f"- `_N` suffix: {len(n_suf)}, of which {len(diff_n)} have a `_P` pair (differential) and {len(n_suf) - len(diff_n)} look like active-low (e.g. {', '.join([x for x in n_suf if x not in diff_n][:6])})")
    P(f"- Other active-low suffixes (`_B`, `#`, `~`): {len(b_suf)}")
    P(f"- Name sample: {', '.join('`'+x+'`' for x in sorted(names)[::max(1, len(names)//40)][:40])}\n")

    # ---------- text ----------
    styles = collections.defaultdict(list)
    for f, d in D.items():
        for t in find(d, "text_box") + find(d, "text"):
            e = get(t, "effects"); fn = get(e, "font") if e else None
            sz = get(fn, "size")[1] if fn and get(fn, "size") else "?"
            bold = bool(fn and get(fn, "bold") and str(get(fn, "bold")[1]) != "no")
            col = get(fn, "color") if fn else None
            stk = get(t, "stroke")
            st = str(get(stk, "type")[1]) if stk and get(stk, "type") else "-"
            scol = get(stk, "color") if stk else None
            key = (name(t), sz, "bold" if bold else "normal",
                   str(tuple(col[1:4])) if col else "default", st, str(tuple(scol[1:4])) if scol else "default")
            if len(styles[key]) < 3:
                styles[key].append(str(t[1])[:50].replace("\n", " / "))
            else:
                styles[key].append(None)
    P("## 5. Text styles\n")
    P("| Type | Font (mm) | Weight | Text color | Border | Border color | Count | Examples |")
    P("|---|---|---|---|---|---|---|---|")
    for k, v in sorted(styles.items(), key=lambda x: -len(x[1])):
        ex = [x for x in v if x][:3]
        P(f"| {k[0]} | {k[1]} | {k[2]} | {k[3]} | {k[4]} | {k[5]} | {len(v)} | {' · '.join('`'+x+'`' for x in ex)} |")
    P("")

    # ---------- .kicad_pro ----------
    pro = json.load(open(pro_path, encoding="utf-8"))
    sch = pro.get("schematic", {})
    P("## 6. Project configuration (`.kicad_pro`)\n")
    dr = sch.get("drawing", {})
    P(f"- Connection grid: {sch.get('connection_grid_size')} mil; default text: {dr.get('default_text_size')} mil; line thickness: {dr.get('default_line_thickness')} mil")
    P(f"- Annotation: {sch.get('annotation')}; start: {sch.get('annotate_start_num')}; reuse_designators: {sch.get('reuse_designators')}")
    P(f"- Defined variants: {sch.get('variants') or 'none'}")
    P(f"- Page template: `{sch.get('page_layout_descr_file') or '(default)'}`")
    bom = sch.get("bom_settings", {}).get("fields_ordered", [])
    P(f"- Fields shown in the BOM: {', '.join(f['label'] for f in bom if f.get('show'))}")
    sev = pro.get("erc", {}).get("rule_severities", {})
    P(f"- ERC rules set to `ignore`: {', '.join(k for k, v in sev.items() if v == 'ignore') or 'none'}")
    P(f"- ERC rules set to `warning`: {', '.join(k for k, v in sev.items() if v == 'warning')}")
    ncs = pro.get("net_settings", {}).get("classes", [])
    P(f"- Net classes: {', '.join(c.get('name') for c in ncs)}; net class patterns: {pro.get('net_settings', {}).get('netclass_patterns') or 'none'}")
    rules = pro.get("board", {}).get("design_settings", {}).get("rules", {})
    if rules:
        P(f"- Board rules: clearance {rules.get('min_clearance')} mm, min track {rules.get('min_track_width')} mm, via {rules.get('min_via_diameter')}/{rules.get('min_through_hole_diameter')} mm")
    P("")

    # ---------- libraries and fabrication ----------
    P("## 7. Project libraries and fabrication\n")
    for t in ("sym-lib-table", "fp-lib-table"):
        p = os.path.join(root, t)
        if os.path.exists(p):
            txt = open(p, encoding="utf-8").read()
            P(f"- `{t}`: " + ", ".join(f"`{m}`" for m in re.findall(r'\(name "([^"]+)"\)', txt)))
    table_libs = set()
    for t in ("sym-lib-table",):
        p = os.path.join(root, t)
        if os.path.exists(p):
            table_libs |= set(re.findall(r'\(name "([^"]+)"\)', open(p, encoding="utf-8").read()))
    std_like = {"Device", "power", "Connector_Generic", "Mechanical", "LED", "Diode", "Switch", "Transistor_FET",
                "Transistor_BJT", "Amplifier_Operational", "Analog_ADC", "Analog_DAC", "Oscillator",
                "Regulator_Linear", "Regulator_Switching", "Converter_DCDC", "74xx", "Logic_LevelTranslator",
                "Connector", "Memory_EEPROM", "Interface", "MCU_Espressif", "Sensor"}
    glob_libs = sorted(set(libs) - table_libs - std_like)
    P(f"- Symbol libraries used that are neither in the project table nor look standard (probably global on the original machine): {', '.join('`'+g+'`' for g in glob_libs) or 'none'}")
    fp_table = set()
    p = os.path.join(root, "fp-lib-table")
    if os.path.exists(p):
        fp_table = set(re.findall(r'\(name "([^"]+)"\)', open(p, encoding="utf-8").read()))
    std_fp_prefix = ("Resistor_", "Capacitor_", "Inductor_", "Package_", "LED_", "Diode_", "Connector",
                     "MountingHole", "Fiducial", "Crystal", "Oscillator", "Varistor", "Converter_",
                     "Button_Switch", "TestPoint", "Fuse", "Relay_", "Transformer_", "Jumper", "Module", "RF_")
    glob_fp = sorted(k for k in fplibs if k and k not in fp_table and not k.startswith(std_fp_prefix))
    P(f"- Footprint libraries outside the project table and non-standard: {', '.join('`'+g+'`' for g in glob_fp) or 'none'}")
    db = os.path.join(root, "jlcpcb", "project.db")
    if os.path.exists(db):
        try:
            c = sqlite3.connect(db)
            cnt = c.execute("select count(*) from part_info").fetchone()[0]
            P(f"- `kicad-jlcpcb-tools` plugin present: `jlcpcb/project.db` with {cnt} references")
        except Exception as e:
            P(f"- `jlcpcb/project.db` present but unreadable: {e}")
    else:
        P("- JLCPCB plugin: `jlcpcb/project.db` not found")
    P("")

    # ---------- ICs ----------
    P("## 8. Active parts and connectors (reuse candidates)\n")
    P("| Sheet | Ref | Value | LCSC | Footprint |")
    P("|---|---|---|---|---|")
    seen = set()
    for c in comps:
        r = c["props"].get("Reference", "")
        if re.match(r"^[RCL]\d", r):
            continue
        v = c["props"].get("Value", "")
        if v in seen:
            continue
        seen.add(v)
        P(f"| {c['file'].replace('.kicad_sch','')} | {r} | `{v[:32]}` | {c['props'].get('LCSC','')} | {c['props'].get('Footprint','').split(':')[-1][:40]} |")
    P("")
    print("\n".join(out))


if __name__ == "__main__":
    main()
