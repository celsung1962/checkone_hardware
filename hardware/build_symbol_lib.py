#!/usr/bin/env python3
"""
Build the project symbol library of CheckOne: hardware/CheckOne/CheckOne.kicad_sym (rev 1.1, 2026-11-16).

Same method and helpers as GapOne V2 (GapOne_V2/hardware/build_symbol_lib.py, form reference serviceone-hw). For every
part:
  1. take the source symbol (KiCad 10 standard library, or a box generated from the pin table), flattening `extends`;
  2. rename it to the part number (symbol name = Value);
  3. set the fields: Reference, Value, Footprint, Datasheet (URL from docs/datasheets/manifest.csv), Description, LCSC;
  4. compare its pins with docs/datasheets/<part>_pins.csv (read from the datasheet). Datasheet wins: pin names and
     types that differ are changed to the datasheet values and logged; a pin NUMBER missing or extra is an error.
Generic symbols (R, C, L, bead, PTC, crystal, cell, connectors, test pad, hole) get their part number and fields where
they are placed (hardware/gen_checkone.py). Project power symbols for the rails the KiCad power library lacks.

Output: the library + hardware/symbol_build_log.md. Run: python hardware/build_symbol_lib.py
"""
import copy
import csv
import os
import re
import sys

import sexpdata
from sexpdata import Symbol as S

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
KLIB = r"C:\Program Files\KiCad\10.0\share\kicad\symbols"
SYMSRC = os.path.join(HERE, "symbol_sources")
DS = os.path.join(ROOT, "docs", "datasheets")
LOG = os.path.join(HERE, "symbol_build_log.md")
G = 2.54
BOARD = "CheckOne"
BOTH = (BOARD,)

PARTS = [
    dict(name="ADS1115IDGSR", ref="U", src="kicad:Analog_ADC:ADS1115IDGS", csv="ADS1115IDGSR", lcsc="C37593",
         manifest="ADS1115IDGSR", boards=BOTH,
         desc="16-bit 860 SPS 4-channel delta-sigma ADC, PGA, I2C, VSSOP-10 (TI)"),
    dict(name="INA226AIDGSR", ref="U", src="kicad:Sensor_Energy:INA226", csv="INA226AIDGSR", lcsc="C49851",
         manifest="INA226AIDGSR", boards=BOTH,
         desc="36 V bidirectional current / power monitor, I2C, VSSOP-10 (TI) - sensor bus"),
    dict(name="PCF8563T", ref="U", src="kicad:Timer_RTC:PCF8563T", csv="PCF8563T", lcsc="C7440", manifest="PCF8563T",
         boards=BOTH, desc="Real-time clock / calendar, I2C, 32.768 kHz, SO-8 (NXP)"),
    dict(name="XC6206P332MR", ref="U", src="kicad:Regulator_Linear:XC6206PxxxMR", csv="XC6206P332MR", lcsc="C5446",
         manifest="XC6206P332MR", boards=BOTH, desc="LDO 3.3 V 200 mA, 1 uA quiescent, SOT-23 (Torex)"),
    dict(name="AO4485", ref="Q", src="custom", csv="AO4485", lcsc="C5334068", manifest="AO4485", boards=BOTH,
         desc="P-channel MOSFET -40 V, 13 mOhm, VGS +-20 V, SOP-8 (ElecSuper; alternative UMW C5125949) - soft start",
         left=["4"], right=["5"], top=["1"]),
    dict(name="XL1509-5.0E1", ref="U", src="custom", csv="XL1509-5.0E1", lcsc="C61063", manifest="XL1509-5.0E1",
         boards=BOTH, desc="Buck converter 5 V fixed, 2 A, 150 kHz, 4.5-40 V input, SOP-8 (XLSEMI)",
         left=["1", "4"], right=["2", "3"], bottom=[None, "5"], width=25.4),
    dict(name="BAT54S", ref="D", src="kicad:Diode:BAT54S", csv="BAT54S", lcsc="C7420333", manifest="BAT54S",
         boards=BOTH, desc="Dual Schottky diode in series, 30 V 200 mA, SOT-23 (hongjiacheng) - input clamp to 3.3VA / GND",
         hide_pin_names=True),
    dict(name="BAT54W", ref="D", src="kicad:Device:D_Schottky", csv="BAT54W", lcsc="C7502705", manifest="BAT54W",
         boards=BOTH, desc="Schottky diode 30 V 200 mA, SOD-123 (hongjiacheng) - RTC supply OR"),
    dict(name="SS34", ref="D", src="kicad:Device:D_Schottky", csv="SS34", lcsc="C8678", manifest="SS34", boards=BOTH,
         desc="Schottky diode 40 V 3 A, SMA (MDD)"),
    dict(name="SMBJ24A", ref="D", src="kicad:Device:D_Zener", csv="SMBJ24A", lcsc="C19077578", manifest="SMBJ24A",
         boards=BOTH, desc="TVS unidirectional 24 V standoff, 26.7 V breakdown, 600 W, SMB (hongjiacheng) - 24 V input"),
    dict(name="SMAJ5.0A", ref="D", src="kicad:Device:D_Zener", csv="SMAJ5.0A", lcsc="C2925443", manifest="SMAJ5.0A",
         boards=BOTH, desc="TVS unidirectional 5 V standoff, 6.4 V breakdown, 400 W, SMA (Liown) - loop input Iin"),
    dict(name="KT-0805G", ref="LED", src="kicad:Device:LED", csv="KT-0805G", lcsc="C2297", manifest="KT-0805G",
         boards=BOTH, desc="LED green 0805 (Hubei KENTO)"),
]

GENERIC = [
    ("R", "kicad:Device:R"), ("C", "kicad:Device:C"), ("C_Polarized", "kicad:Device:C_Polarized"),
    ("L", "kicad:Device:L"), ("FerriteBead_Small", "kicad:Device:FerriteBead_Small"),
    ("Polyfuse", "kicad:Device:Polyfuse"), ("Crystal", "kicad:Device:Crystal"),
    ("Battery_Cell", "kicad:Device:Battery_Cell"), ("Barrel_Jack_Switch", "kicad:Connector:Barrel_Jack_Switch"),
    ("Conn_01x02", "kicad:Connector_Generic:Conn_01x02"), ("Conn_01x04", "kicad:Connector_Generic:Conn_01x04"),
    ("TestPoint", "kicad:Connector:TestPoint"), ("MountingHole", "kicad:Mechanical:MountingHole"),
]
# Project power symbols for rails that the KiCad power library does not have.
# sign: "+" copies the +3.3V shape, "-" the -3V3 shape, "g" the GND shape, "e" the GNDPWR shape.
POWER = {BOARD: [("+3.3VA", "+"), ("+24V_SENS", "+"), ("+5V_DISP", "+"), ("V24_F", "+")]}

SOT23 = "Package_TO_SOT_SMD:SOT-23"
FOOTPRINTS = {
    "ADS1115IDGSR": "Package_SO:TSSOP-10_3x3mm_P0.5mm", "INA226AIDGSR": "Package_SO:TSSOP-10_3x3mm_P0.5mm",
    "PCF8563T": "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", "XC6206P332MR": SOT23,
    "AO4485": "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", "XL1509-5.0E1": "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
    "BAT54S": SOT23, "BAT54W": "Diode_SMD:D_SOD-123", "SS34": "Diode_SMD:D_SMA", "SMBJ24A": "Diode_SMD:D_SMB",
    "SMAJ5.0A": "Diode_SMD:D_SMA", "KT-0805G": "LED_SMD:LED_0805_2012Metric",
}


# --------------------------------------------------------------- helpers (form reference, unchanged) ----


def hd(x):
    return x[0].value() if isinstance(x, list) and x and isinstance(x[0], S) else None


def walk(x):
    if isinstance(x, list):
        yield x
        for c in x:
            yield from walk(c)


def legacy_hide(node):
    """KiCad 8 files write a bare `hide` atom; KiCad 10 writes (hide yes). Convert recursively."""
    if isinstance(node, list):
        return [[S("hide"), S("yes")] if (i > 0 and isinstance(c, S) and c.value() == "hide") else legacy_hide(c)
                for i, c in enumerate(node)]
    return node


def load_lib(path, _cache={}):
    if path not in _cache:
        tree = legacy_hide(sexpdata.loads(open(path, encoding="utf-8").read()))
        _cache[path] = {n[1]: n for n in tree[1:] if hd(n) == "symbol"}
    return _cache[path]


def rename(sym, new):
    old = sym[1]
    sym[1] = new
    for c in sym:
        if hd(c) == "symbol" and isinstance(c[1], str) and c[1].startswith(old + "_"):
            c[1] = new + c[1][len(old):]


def flatten(lib, name):
    sym = copy.deepcopy(lib[name])
    ext = next((c for c in sym if hd(c) == "extends"), None)
    if ext is None:
        return sym
    parent = flatten(lib, ext[1])
    rename(parent, name)
    props = [c for c in sym if hd(c) == "property"]
    body = [c for c in parent if hd(c) != "property"]
    first = next(i for i, c in enumerate(body) if hd(c) == "symbol" or hd(c) == "embedded_fonts") \
        if any(hd(c) in ("symbol", "embedded_fonts") for c in body) else len(body)
    return body[:first] + props + body[first:]


def font(size=1.27):
    return [S("effects"), [S("font"), [S("size"), size, size]]]


def set_prop(sym, key, value, hide=True):
    for c in sym:
        if hd(c) == "property" and c[1] == key:
            c[2] = value
            return
    node = [S("property"), key, value, [S("at"), 0, 0, 0], [S("show_name"), S("no")],
            [S("do_not_autoplace"), S("no")]] + ([[S("hide"), S("yes")]] if hide else []) + [font()]
    idx = max(i for i, c in enumerate(sym) if hd(c) == "property") + 1
    sym.insert(idx, node)


def drop_props(sym, keys):
    sym[:] = [c for c in sym if not (hd(c) == "property" and c[1] in keys)]


def pins_of(sym):
    out = []
    for n in walk(sym):
        if hd(n) == "pin":
            out.append((n, next(c for c in n if hd(c) == "number"), next(c for c in n if hd(c) == "name")))
    return out


def read_csv(name):
    path = os.path.join(DS, f"{name}_pins.csv")
    if not os.path.exists(path):
        return None, path
    with open(path, newline="", encoding="utf-8") as f:
        lines = [ln for ln in f if not ln.lstrip().startswith("#")]
    rows = [r for r in csv.DictReader(lines) if (r.get("number") or "").strip()]
    return rows, path


def csv_source(path):
    """Citation: the `source` column of the first row (form-reference CSV format) + any '# UNRESOLVED' line."""
    rows, _ = read_csv(os.path.splitext(os.path.basename(path))[0][:-len("_pins")])
    src = next((r.get("source", "") for r in rows if (r.get("source") or "").strip()), "")
    with open(path, encoding="utf-8") as f:
        unres = [ln.strip("# \n") for ln in f if ln.lstrip().startswith("# UNRESOLVED")]
    return (src + (" | " + " ".join(unres) if unres else "")).replace("|", "/")


def norm(s):
    return re.sub(r"~\{([^}]*)\}", r"\1", str(s)).replace("~", "").strip().upper()


def pin_node(num, name, ptype, x, y, ang, hidden=False, length=G):
    n = [S("pin"), S(ptype), S("line"), [S("at"), x, y, ang], [S("length"), length]]
    if hidden:
        n.append([S("hide"), S("yes")])
    n += [[S("name"), name, font()], [S("number"), str(num), font()]]
    return n


def custom_symbol(p, rows):
    """Rectangle box (form reference algorithm): left/right/top/bottom lists of pin numbers; pins not placed go left
    (inputs/passive) or right (outputs) in CSV order; pads with the same name as a placed pin are stacked hidden."""
    byn = {r["number"].strip(): r for r in rows}
    sides = {k: list(p.get(k) or []) for k in ("left", "right", "top", "bottom")}
    bad = [x for v in sides.values() for x in v if x and x not in byn]
    if bad:
        raise ValueError(f"{p['name']}: layout pins {bad} not in the pin table")
    placed = {x for v in sides.values() for x in v if x}
    first_by_name = {}
    for k in ("left", "right", "top", "bottom"):
        for x in sides[k]:
            if x:
                first_by_name.setdefault(norm(byn[x]["name"]), x)
    stacked = {}
    for r in rows:
        num = r["number"].strip()
        if num in placed:
            continue
        key = norm(r["name"])
        if key in first_by_name and r.get("type", "").strip() != "no_connect":   # NC pads are never stacked
            stacked[num] = first_by_name[key]
        else:
            side = "right" if r.get("type", "").strip() in ("output", "power_out", "tri_state", "open_collector") \
                else "left"
            sides[side].append(num)
            first_by_name[key] = num
    nlr = max(len(sides["left"]), len(sides["right"]), 1)
    ntb = max(len(sides["top"]), len(sides["bottom"]), 0)

    def maxlen(k):
        return max((len(norm(byn[x]["name"])) for x in sides[k] if x), default=0)
    w = max((ntb + 1) * 2 * G, (maxlen("left") + maxlen("right")) * 1.0 + 3 * G, 4 * G, p.get("width", 0))
    GV = G * p.get("pitch", 1)
    h = (nlr + 1) * GV
    w = -(-w // (2 * G)) * 2 * G
    w = p.get("box_width", w)                 # explicit width (connectors drawn alike)
    h = round(h / G) * G
    x0, y0 = -w / 2, h / 2
    pins, pos = [], {}
    for i, num in enumerate(sides["left"]):
        if num:
            pos[num] = (x0 - G, y0 - (i + 1) * GV, 0)
    for i, num in enumerate(sides["right"]):
        if num:
            pos[num] = (-x0 + G, y0 - (i + 1) * GV, 180)
    for i, num in enumerate(sides["top"]):
        if num:
            pos[num] = (x0 + (i + 1) * G * 2, y0 + G, 270)
    for i, num in enumerate(sides["bottom"]):
        if num:
            pos[num] = (x0 + (i + 1) * G * 2, -y0 - G, 90)

    def plen(num):
        return 2 * G if len(num) > 2 and not p.get("pitch") else G

    def ext(num, x, y, a):
        d = plen(num) - G
        return (x - d if a == 0 else x + d if a == 180 else x, y + d if a == 270 else y - d if a == 90 else y)
    for num, (x, y, a) in pos.items():
        r = byn[num]
        x, y = ext(num, x, y, a)
        pins.append(pin_node(num, r["name"].strip(), r["type"].strip() or "passive", round(x, 2), round(y, 2), a,
                             length=plen(num)))
    for num, onto in stacked.items():
        r = byn[num]
        x, y, a = pos[onto]
        x, y = ext(onto, x, y, a)
        # stacked duplicates are passive (KiCad library convention): a hidden power_in pin would create an implicit
        # global net named after the pin (e.g. GND) and short it to the rail drawn on the visible pin
        pins.append(pin_node(num, r["name"].strip(), "passive", round(x, 2), round(y, 2), a,
                             hidden=True, length=plen(onto)))
    nm = p["name"]
    rect = [S("rectangle"), [S("start"), round(x0, 2), round(y0, 2)], [S("end"), round(-x0, 2), round(-y0, 2)],
            [S("stroke"), [S("width"), 0.254], [S("type"), S("default")]], [S("fill"), [S("type"), S("background")]]]
    sym = [S("symbol"), nm, [S("pin_names"), [S("offset"), 1.016]], [S("exclude_from_sim"), S("no")],
           [S("in_bom"), S("yes")], [S("on_board"), S("yes")]]
    for k, v, at in (("Reference", p["ref"], (x0, y0 + 1.27)), ("Value", nm, (x0, -y0 - 1.27))):
        sym.append([S("property"), k, v, [S("at"), round(at[0], 2), round(at[1], 2), 0],
                    [S("effects"), [S("font"), [S("size"), 1.27, 1.27]], [S("justify"), S("left")]]])
    for k in ("Footprint", "Datasheet", "Description"):
        sym.append([S("property"), k, "", [S("at"), 0, 0, 0], [S("hide"), S("yes")], font()])
    sym.append([S("symbol"), f"{nm}_0_1", rect])
    sym.append([S("symbol"), f"{nm}_1_1"] + pins)
    sym.append([S("embedded_fonts"), S("no")])
    return sym


def rotate_sym(sym, deg):
    """Turn the artwork and pins of a symbol by `deg` (multiple of 90, counter-clockwise, symbol y up). Fields keep
    their positions (the sheets place them)."""
    k = (deg // 90) % 4

    def r(x, y):
        for _ in range(k):
            x, y = -y, x
        return x, y
    for n in walk(sym):
        if hd(n) == "pin":
            at = next(c for c in n if hd(c) == "at")
            at[1], at[2] = r(at[1], at[2])
            at[3] = (at[3] + 90 * k) % 360
        elif hd(n) in ("start", "end", "mid", "center", "xy") and len(n) == 3:
            n[1], n[2] = r(n[1], n[2])


def manifest_urls():
    with open(os.path.join(DS, "manifest.csv"), newline="", encoding="utf-8") as f:
        return {r["part"]: r["url"] for r in csv.DictReader(f) if r["doc_type"] == "datasheet"}


# ------------------------------------------------------------------ main ----


def build_part(p, board, urls):
    """Return (symbol, log row) or raise ValueError."""
    rows, csvpath = read_csv(p["csv"])
    if rows is None:
        raise FileNotFoundError(os.path.basename(csvpath))
    src = p["src"]
    if src == "custom":
        sym, origin = custom_symbol(p, rows), "custom (generated from the pin table)"
    elif src.startswith("file:"):
        _, fname, name = src.split(":")
        sym = flatten(load_lib(os.path.join(SYMSRC, fname)), name)
        origin = f"form reference hardware/symbol_sources/{fname}"
    else:
        _, lib, name = src.split(":")
        sym = flatten(load_lib(os.path.join(KLIB, lib + ".kicad_sym")), name)
        origin = f"KiCad {lib}:{name}"
    rename(sym, p["name"])
    if p.get("renumber"):                    # source symbol of the same function with another pinout
        for _, num, _ in pins_of(sym):
            num[1] = p["renumber"][str(num[1])]
        origin += f", renumbered {p['renumber']}"
    if p.get("rotate"):
        rotate_sym(sym, p["rotate"])
        origin += f", turned {p['rotate']} deg"
    set_prop(sym, "Reference", p["ref"], hide=False)
    set_prop(sym, "Value", p["name"], hide=False)
    set_prop(sym, "Footprint", FOOTPRINTS.get(p["name"], "").format(lib=board))
    set_prop(sym, "Datasheet", urls.get(p["manifest"], ""))
    set_prop(sym, "Description", p["desc"])
    set_prop(sym, "LCSC", p["lcsc"])
    if p["name"] in FOOTPRINTS:
        drop_props(sym, {"ki_fp_filters"})
    byn = {}
    for r in rows:
        byn.setdefault(r["number"].strip(), []).append(r)
    changes, sympins = [], pins_of(sym)
    nums_sym = {str(num[1]) for _, num, _ in sympins}
    missing, extra = sorted(set(byn) - nums_sym), sorted(nums_sym - set(byn))
    if missing or extra:
        raise ValueError(f"{p['name']} ({origin}): pin numbers differ from the datasheet - missing in symbol "
                         f"{missing}, not in datasheet {extra}")
    for node, num, nm in sympins:
        r = byn[str(num[1])][0]
        dname, dtype = r["name"].strip(), (r.get("type") or "").strip()
        if norm(nm[1]) != norm(dname):
            changes.append(f"pin {num[1]}: name '{nm[1]}' -> '{dname}'")
            nm[1] = dname
        # hidden pins (stacked duplicates, custom or KiCad-sourced) stay passive: a hidden power_in pin creates an
        # implicit global net named after the pin (e.g. VIN, GND) and shorts it to the rail on the visible pin
        stacked_hidden = any(hd(c) == "hide" for c in node)
        if stacked_hidden and node[1].value() != "passive":
            changes.append(f"pin {num[1]}: hidden {node[1].value()} -> passive")
            node[1] = S("passive")
        elif dtype and node[1].value() != dtype and not stacked_hidden:
            changes.append(f"pin {num[1]}: type {node[1].value()} -> {dtype}")
            node[1] = S(dtype)
    if p.get("hide_pin_names"):
        pn = next((c for c in sym if hd(c) == "pin_names"), None)
        if pn is None:
            pn = [S("pin_names")]
            sym.insert(2, pn)
        pn[:] = [c for c in pn if hd(c) != "hide"] + [[S("hide"), S("yes")]]
    notes = []
    if not urls.get(p["manifest"]):
        notes.append("no datasheet URL in manifest.csv")
    if not p["lcsc"]:
        notes.append("no LCSC code yet")
    return sym, (p["name"], p["lcsc"] or "-", origin, os.path.basename(csvpath), csv_source(csvpath),
                 changes, notes)


def build():
    urls = manifest_urls()
    status = 0
    with open(LOG, "w", encoding="utf-8", newline="\n") as logf:
        logf.write("# Symbol build log (generated by hardware/build_symbol_lib.py - do not edit)\n")
        for board in BOTH:
            out, log, errors, skipped = [], [], [], []
            for p in PARTS:
                if board not in p["boards"]:
                    continue
                try:
                    sym, row = build_part(p, board, urls)
                except FileNotFoundError as e:
                    skipped.append(f"{p['name']}: no pin table ({e})")
                    continue
                except ValueError as e:
                    errors.append(str(e))
                    continue
                out.append(sym)
                log.append(row)
            for name, src in GENERIC:
                _, lib, sname = src.split(":")
                sym = flatten(load_lib(os.path.join(KLIB, lib + ".kicad_sym")), sname)
                rename(sym, name)
                set_prop(sym, "LCSC", "")
                if name in ("Conn_01x01", "Conn_01x01_Pin"):   # wire / coax pads use project footprints too (AMP probe pads)
                    drop_props(sym, {"ki_fp_filters"})
                if name == "Conn_01x01_Pin":      # solder points: pin number hidden, as the baseline symbol
                    sym[:] = [c for c in sym if hd(c) != "pin_numbers"]
                    sym.insert(2, [S("pin_numbers"), [S("hide"), S("yes")]])
                out.append(sym)
            power_lib = load_lib(os.path.join(KLIB, "power.kicad_sym"))
            for net, sign in POWER[board]:
                sym = flatten(power_lib, {"+": "+3.3V", "-": "-3V3", "g": "GND", "e": "GNDPWR"}[sign])
                rename(sym, net)
                set_prop(sym, "Value", net, hide=False)
                set_prop(sym, "Description", f'Power symbol creates a global label with name "{net}"')
                for _, _, nm in pins_of(sym):
                    nm[1] = net
                out.append(sym)
            tree = [S("kicad_symbol_lib"), [S("version"), 20251024], [S("generator"), "kicad_symbol_editor"],
                    [S("generator_version"), "10.0"]] + out
            path = os.path.join(HERE, board, f"{board}.kicad_sym")
            open(path, "w", encoding="utf-8", newline="\n").write(sexpdata.dumps(tree) + "\n")
            logf.write(f"\n## {board}\n\n| Symbol | LCSC | Source symbol | Pin table | Datasheet reference "
                       "| Changes to match the datasheet | Notes |\n|---|---|---|---|---|---|---|\n")
            for nm, lc, origin, csvf, srow, ch, notes in log:
                logf.write(f"| {nm} | {lc} | {origin} | {csvf} | {srow} | {'; '.join(ch) if ch else 'none'} | "
                           f"{'; '.join(notes) if notes else ''} |\n")
            if skipped:
                logf.write("\n### Skipped (pin table missing)\n\n" + "".join(f"- {s}\n" for s in skipped))
            if errors:
                logf.write("\n### Errors\n\n" + "".join(f"- {e}\n" for e in errors))
            print(f"{board}: {len(out)} symbols ({len(log)} parts) -> {os.path.relpath(path, ROOT)}; "
                  f"{len(skipped)} skipped; {len(errors)} errors")
            for e in errors:
                print("  ERROR:", e)
            for s in skipped:
                print("  skipped:", s)
            status |= 1 if errors else 0
    return status


if __name__ == "__main__":
    sys.exit(build())
