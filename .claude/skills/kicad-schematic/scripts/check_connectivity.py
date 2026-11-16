#!/usr/bin/env python3
"""
Connectivity-equivalence check for drawing-only changes (references/schematic_drawing.md, section 0): the set of
pin groups (ref.pin that share a net) of the current netlist must equal the one of a reference netlist, ignoring
net names. Pin 1/2 swaps on non-polarized two-terminal parts (R, C, L, F, FB and bidirectional TVS: value
containing "CA") count as equivalent. Power-symbol and PWR_FLAG pins (references starting with '#') are ignored.

Any difference is a drawing bug (a wire shorted something or left something open), not an acceptable change.

Usage:
    kicad-cli sch export netlist --format kicadsexpr -o build/reference_<commit>.net hardware/<project>.kicad_sch
    ... drawing changes ...
    kicad-cli sch export netlist --format kicadsexpr -o build/current.net hardware/<project>.kicad_sch
    python3 check_connectivity.py build/reference_<commit>.net build/current.net
Requires: sexpdata (pip install sexpdata).
"""
import os, re, sys

try:
    import sexpdata
    from sexpdata import Symbol as S
except ImportError:
    sys.exit("Install sexpdata: pip install sexpdata")


def find(x, tag):
    return [e for e in x if isinstance(e, list) and e and e[0] == S(tag)]


SYMMETRIC = re.compile(r"^(R|C|L|F|FB)\d+$")


def groups(path):
    d = sexpdata.loads(open(path, encoding="utf-8").read())
    vals = {str(find(c, "ref")[0][1]): str(find(c, "value")[0][1]) for c in find(find(d, "components")[0], "comp")}
    out, names = set(), {}

    def tag(ref, pin):
        if SYMMETRIC.match(ref) or (ref.startswith("D") and "CA" in vals.get(ref, "")):
            return f"{ref}.~"
        return f"{ref}.{pin}"
    for n in find(find(d, "nets")[0], "net"):
        nm = str(find(n, "name")[0][1])
        pins = tuple(sorted(tag(str(find(x, "ref")[0][1]), str(find(x, "pin")[0][1])) for x in find(n, "node")
                            if not str(find(x, "ref")[0][1]).startswith("#")))
        if pins:
            out.add(pins)
            names[pins] = nm
    return out, names


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    a, an = groups(sys.argv[1])
    b, bn = groups(sys.argv[2])
    only_a = sorted(a - b, key=lambda g: sorted(g))
    only_b = sorted(b - a, key=lambda g: sorted(g))
    if not only_a and not only_b:
        print(f"Connectivity: PASS - {len(a)} pin groups identical to {os.path.basename(sys.argv[1])}")
        return 0
    print(f"Connectivity: FAIL - {len(only_a)} groups only in the reference, {len(only_b)} only in the current")
    for g in only_a:
        print(f"  - ref  {an[g]}: {' '.join(sorted(g))}")
    for g in only_b:
        print(f"  + cur  {bn[g]}: {' '.join(sorted(g))}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
