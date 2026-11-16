#!/usr/bin/env python3
"""
Generates Markdown tables for the board technical document straight from the
KiCad netlist, so pin maps, connector pinouts and test-point lists are never
retyped by hand. Write each table to DOC/source/generated/ and include it in the
document source with {{include generated/<file>.md}}.

Usage:
    netlist_tables.py <project.net> pins       --ref U1 [--pin-regex '^GPIO'] [--notes notes.csv]
    netlist_tables.py <project.net> connectors [--prefix CONN,J]
    netlist_tables.py <project.net> testpoints [--prefix TP,TC]
    netlist_tables.py <project.net> parts      [--prefix U,Y,Q,D] [--group]
    netlist_tables.py <project.net> nets       --regex '^P4_I2C'

pins:       one row per pin of a part — pin function, pin number, net, note
            (--notes: CSV pin_function,note to add a human column, e.g. "CS of ADC #1")
connectors: one row per connector — value, then "pin = net" for every pin
testpoints: one row per test point — net and sheet
parts:      ICs/actives with value, sheet and description (or grouped by value)
nets:       every node on the matching nets
"""
import argparse, csv, os, re, sys, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from netlist_check import Netlist  # noqa: E402


def natural(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(s))]


def clean_net(n):
    if not n or n.startswith("unconnected-") or n.startswith("Net-("):
        return "—" if (not n or n.startswith("unconnected-")) else n
    return n.lstrip("/").split("/")[-1]


def table(head, rows):
    out = ["| " + " | ".join(head) + " |", "| " + " | ".join("---" for _ in head) + " |"]
    for r in rows:
        out.append("| " + " | ".join(str(c).replace("|", "\\|") for c in r) + " |")
    return "\n".join(out)


def pins_of(nl, ref):
    res = []
    for (r, pin), net in nl.pin_net.items():
        if r != ref:
            continue
        node = next((n for n in nl.nets[net] if n[0] == r and n[1] == pin), None)
        res.append((node[2] if node else "", pin, net))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("netlist")
    ap.add_argument("kind", choices=["pins", "connectors", "testpoints", "parts", "nets"])
    ap.add_argument("--ref")
    ap.add_argument("--pin-regex", default="")
    ap.add_argument("--notes")
    ap.add_argument("--prefix", default="")
    ap.add_argument("--regex", default="")
    ap.add_argument("--group", action="store_true")
    a = ap.parse_args()
    nl = Netlist(a.netlist)
    prefixes = [p.strip() for p in a.prefix.split(",") if p.strip()]

    def has_prefix(ref, default):
        pf = prefixes or default
        return any(re.match(rf"^{re.escape(p)}\d", ref) for p in pf)

    if a.kind == "pins":
        if not a.ref or a.ref not in nl.comps:
            sys.exit(f"--ref must name a part in the netlist (got {a.ref})")
        notes = {}
        if a.notes:
            with open(a.notes, newline="", encoding="utf-8") as f:
                notes = {r["pin_function"]: r["note"] for r in csv.DictReader(f)}
        rx = re.compile(a.pin_regex) if a.pin_regex else None
        rows = [(fn or "—", pin, clean_net(net), notes.get(fn, ""))
                for fn, pin, net in pins_of(nl, a.ref) if not rx or rx.search(fn or "")]
        rows.sort(key=lambda r: natural(r[0]))
        head = ["Pin function", "Pin", "Net"] + (["Function"] if notes else [])
        print(table(head, [r if notes else r[:3] for r in rows]))
        print(f"\nSource: netlist `{os.path.basename(a.netlist)}`, part {a.ref} ({nl.comps[a.ref].get('Value','')}).")
    elif a.kind == "connectors":
        rows = []
        for ref in sorted((r for r in nl.comps if has_prefix(r, ["CONN", "J", "CN", "P"])), key=natural):
            ps = sorted(pins_of(nl, ref), key=lambda x: natural(x[1]))
            rows.append((ref, nl.comps[ref].get("Value", ""), "; ".join(f"{p} = {clean_net(n)}" for _, p, n in ps)))
        print(table(["Ref.", "Part", "Pinout (pin = net)"], rows))
        print(f"\nSource: netlist `{os.path.basename(a.netlist)}`.")
    elif a.kind == "testpoints":
        rows = []
        for ref in sorted((r for r in nl.comps if has_prefix(r, ["TP", "TC"])), key=natural):
            nets = sorted({clean_net(n) for _, _, n in pins_of(nl, ref) if not str(n).startswith("unconnected-")})
            rows.append((ref, ", ".join(nets) or "—", nl.comps[ref].get("_sheet", "")))
        print(table(["Ref.", "Net", "Sheet"], rows))
        print(f"\nSource: netlist `{os.path.basename(a.netlist)}`.")
    elif a.kind == "parts":
        sel = [r for r in nl.comps if has_prefix(r, ["U", "Y", "Q", "D", "PS", "K"])]
        if a.group:
            g = collections.OrderedDict()
            for r in sorted(sel, key=natural):
                c = nl.comps[r]
                k = c.get("Value", "")
                g.setdefault(k, {"refs": [], "sheets": set(), "desc": c.get("Description", "")})
                g[k]["refs"].append(r)
                g[k]["sheets"].add(c.get("_sheet", ""))
            rows = [(k, len(v["refs"]), ", ".join(v["refs"][:8]) + (" …" if len(v["refs"]) > 8 else ""),
                     ", ".join(sorted(s for s in v["sheets"] if s)), v["desc"]) for k, v in g.items()]
            print(table(["Part", "Qty", "References", "Sheets", "Description"], rows))
        else:
            rows = [(r, nl.comps[r].get("Value", ""), nl.comps[r].get("_sheet", ""), nl.comps[r].get("Description", ""))
                    for r in sorted(sel, key=natural)]
            print(table(["Ref.", "Part", "Sheet", "Description"], rows))
    elif a.kind == "nets":
        rx = re.compile(a.regex)
        rows = []
        for net in sorted((n for n in nl.nets if rx.search(clean_net(n))), key=natural):
            for ref, pin, fn, _ in sorted(nl.nets[net], key=lambda x: natural(x[0])):
                rows.append((clean_net(net), ref, nl.comps.get(ref, {}).get("Value", ""), pin, fn or "—"))
        print(table(["Net", "Ref.", "Part", "Pin", "Pin function"], rows))


if __name__ == "__main__":
    main()
