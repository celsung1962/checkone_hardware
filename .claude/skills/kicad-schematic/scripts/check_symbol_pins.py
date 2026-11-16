#!/usr/bin/env python3
"""
Compares the pins of a KiCad symbol (.kicad_sym, or lib_symbols embedded in a
.kicad_sch) with a table extracted from the datasheet.

Usage:
    python3 check_symbol_pins.py <file.kicad_sym|.kicad_sch> <SymbolName> <pins.csv>
    python3 check_symbol_pins.py <file> <SymbolName> --dump   # exports the symbol pin table

CSV: columns number,name[,type]  (optional type: power_in, input, output, bidirectional,
passive, no_connect, power_out, tri_state, open_collector, unspecified).
Names are compared case-insensitively, ignoring '~{...}' (overbar).
Non-zero exit code on any mismatch — use it in CI / pre-commit.
"""
import sys, csv, re

try:
    import sexpdata
    from sexpdata import Symbol
except ImportError:
    sys.exit("Install sexpdata: pip install sexpdata --break-system-packages")


def name(x):
    return x[0].value() if isinstance(x, list) and x and isinstance(x[0], Symbol) else None


def walk(x):
    if isinstance(x, list):
        yield x
        for c in x:
            yield from walk(c)


def norm(s):
    s = re.sub(r"~\{([^}]*)\}", r"\1", str(s))
    return s.replace("~", "").strip().upper()


def symbol_pins(path, symname):
    tree = sexpdata.loads(open(path, encoding="utf-8").read())
    cands = [n for n in walk(tree) if name(n) == "symbol" and len(n) > 1 and isinstance(n[1], str)
             and (n[1] == symname or n[1].split(":")[-1] == symname)]
    if not cands:
        names = sorted({n[1] for n in walk(tree) if name(n) == "symbol" and len(n) > 1 and isinstance(n[1], str)
                        and not re.search(r"_\d+_\d+$", n[1])})
        sys.exit(f"Symbol '{symname}' not found. Available: {', '.join(names[:60])}")
    pins = {}
    for n in walk(cands[0]):
        if name(n) == "pin":
            ptype = n[1].value() if isinstance(n[1], Symbol) else str(n[1])
            nm = next((c[1] for c in n if name(c) == "name"), "")
            num = next((c[1] for c in n if name(c) == "number"), "")
            pins.setdefault(str(num), []).append((str(nm), ptype))
    return pins


def main():
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    path, symname, arg = sys.argv[1], sys.argv[2], sys.argv[3]
    pins = symbol_pins(path, symname)
    if arg == "--dump":
        w = csv.writer(sys.stdout)
        w.writerow(["number", "name", "type"])
        for num in sorted(pins, key=lambda s: (len(s), s)):
            for nm, t in pins[num]:
                w.writerow([num, nm, t])
        return
    ref = {}
    with open(arg, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ref.setdefault(row["number"].strip(), []).append((row["name"].strip(), (row.get("type") or "").strip()))
    errs = []
    for num, entries in ref.items():
        if num not in pins:
            errs.append(f"pin {num} ({entries[0][0]}) missing from the symbol")
            continue
        got_names = {norm(n) for n, _ in pins[num]}
        for nm, t in entries:
            if norm(nm) not in got_names:
                errs.append(f"pin {num}: datasheet '{nm}' ≠ symbol {sorted(got_names)}")
            if t:
                got_types = {tt for n, tt in pins[num] if norm(n) == norm(nm)}
                if got_types and t not in got_types:
                    errs.append(f"pin {num} ({nm}): type '{t}' ≠ symbol {sorted(got_types)}")
    for num in pins:
        if num not in ref:
            errs.append(f"pin {num} ({pins[num][0][0]}) exists in the symbol but not in the table")
    print(f"Symbol {symname}: {len(pins)} pin numbers; table: {len(ref)}")
    if errs:
        print(f"FAIL — {len(errs)} mismatch(es):")
        for e in errs:
            print("  -", e)
        sys.exit(1)
    print("PASS — all pins match.")


if __name__ == "__main__":
    main()
