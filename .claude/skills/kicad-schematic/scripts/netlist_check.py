#!/usr/bin/env python3
"""
Automated verification of a KiCad netlist (kicadsexpr format).

1) Export:  kicad-cli sch export netlist project.kicad_sch --format kicadsexpr -o project.net
2) Run:     python3 netlist_check.py project.net [--rules calc/netlist_rules.py] [--fields Reference,Value,Footprint,LCSC]

Built-in generic checks:
  - components missing required fields (--fields), except holes/fiducials/virtual parts
  - single-node nets (possibly a forgotten pin; declared NC pins are ignored)
  - net names ending in '_N' without a '_P' pair (forbidden active-low style)  [--no-active-low-check to disable]

Project rules: a Python file with a `rules(nl, check)` function. Example:

    def rules(nl, check):
        # every ADC CLKIN gets a branch of buffer U10, never the MCU directly
        for adc in nl.refs("U2[0-3]"):
            net = nl.net_of(adc, "23")
            check(net is not None, f"{adc}.23 has no net")
            check(nl.connected_to(net, "U10"), f"{adc} CLKIN not driven by the buffer: {net}")
            check(not nl.connected_to(net, "U1"), f"{adc} CLKIN tied directly to the MCU")
        check(nl.net_of("U20", "24") and nl.has_part_on(nl.net_of("U20","24"), value="220nF"), "CAP pin without 220 nF")

Non-zero exit code if any check fails.
"""
import sys, re, argparse, runpy, collections

try:
    import sexpdata
    from sexpdata import Symbol
except ImportError:
    sys.exit("Install sexpdata: pip install sexpdata --break-system-packages")


def _n(x):
    return x[0].value() if isinstance(x, list) and x and isinstance(x[0], Symbol) else None


def _get(x, k):
    for c in x:
        if _n(c) == k:
            return c
    return None


def _val(x, k, default=""):
    c = _get(x, k)
    return str(c[1]) if c is not None and len(c) > 1 else default


class Netlist:
    def __init__(self, path):
        tree = sexpdata.loads(open(path, encoding="utf-8").read())
        self.comps = {}
        for c in _get(tree, "components")[1:]:
            if _n(c) != "comp":
                continue
            ref = _val(c, "ref")
            fields = {"Reference": ref, "Value": _val(c, "value"), "Footprint": _val(c, "footprint"),
                      "Datasheet": _val(c, "datasheet"), "Description": _val(c, "description")}
            fl = _get(c, "fields")
            if fl is not None:
                for f in fl[1:]:
                    if _n(f) == "field":
                        nm = _val(f, "name")
                        fields[nm] = str(f[2]) if len(f) > 2 and not isinstance(f[2], list) else fields.get(nm, "")
            for p in c:
                if _n(p) == "property":
                    fields[_val(p, "name")] = _val(p, "value")
            sp = _get(c, "sheetpath")
            fields["_sheet"] = _val(sp, "names").strip("/") if sp is not None else ""
            self.comps[ref] = fields
        self.nets = {}
        self.pin_net = {}
        for n in _get(tree, "nets")[1:]:
            if _n(n) != "net":
                continue
            nm = _val(n, "name")
            nodes = []
            for nd in n:
                if _n(nd) == "node":
                    node = (_val(nd, "ref"), _val(nd, "pin"), _val(nd, "pinfunction"), _val(nd, "pintype"))
                    nodes.append(node)
                    self.pin_net[(node[0], node[1])] = nm
            self.nets[nm] = nodes

    # ---- queries ----
    def refs(self, pattern):
        rx = re.compile(f"^{pattern}$")
        return sorted((r for r in self.comps if rx.match(r)), key=lambda s: (re.sub(r"\d", "", s), int(re.sub(r"\D", "", s) or 0)))

    def net_of(self, ref, pin):
        return self.pin_net.get((ref, str(pin)))

    def nodes(self, net):
        return self.nets.get(net, [])

    def refs_on(self, net):
        return sorted({n[0] for n in self.nodes(net)})

    def connected_to(self, net, ref_pattern):
        rx = re.compile(f"^{ref_pattern}$")
        return any(rx.match(r) for r in self.refs_on(net))

    def has_part_on(self, net, value=None, prefix=None):
        for r in self.refs_on(net):
            c = self.comps.get(r, {})
            if prefix and not r.startswith(prefix):
                continue
            if value is None or c.get("Value", "").replace(" ", "").lower() == value.replace(" ", "").lower():
                return True
        return False

    def other_end(self, ref, pin):
        """For a 2-terminal passive: the net on the other terminal."""
        pins = [p for (r, p) in self.pin_net if r == ref]
        others = [p for p in pins if p != str(pin)]
        return self.net_of(ref, others[0]) if len(others) == 1 else None

    def nets_matching(self, pattern):
        rx = re.compile(pattern)
        return sorted(n for n in self.nets if rx.search(n))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("netlist")
    ap.add_argument("--rules")
    ap.add_argument("--fields", default="Reference,Value,Footprint,Datasheet")
    ap.add_argument("--no-active-low-check", action="store_true")
    a = ap.parse_args()
    nl = Netlist(a.netlist)
    fails, passes = [], 0

    def check(cond, msg):
        nonlocal passes
        if cond:
            passes += 1
        else:
            fails.append(msg)

    req = [f.strip() for f in a.fields.split(",") if f.strip()]
    for ref, f in nl.comps.items():
        if re.match(r"^(MH|FID|H|#)", ref):
            continue
        for k in req:
            check(bool(str(f.get(k, "")).strip()), f"{ref}: field '{k}' is empty")
    for net, nodes in nl.nets.items():
        real = [n for n in nodes if n[3] != "no_connect"]
        if len(real) == 1 and not net.startswith("unconnected-"):
            check(False, f"net '{net}' has a single node: {real[0][0]}.{real[0][1]}")
    if not a.no_active_low_check:
        base = {re.sub(r"^.*/", "", n) for n in nl.nets}
        for n in base:
            if n.endswith("_N") and n[:-2] + "_P" not in base:
                check(False, f"net '{n}' uses a _N suffix without a _P pair (forbidden active-low style?)")
    if a.rules:
        ns = runpy.run_path(a.rules)
        ns["rules"](nl, check)

    print(f"{len(nl.comps)} components, {len(nl.nets)} nets — {passes} checks passed, {len(fails)} failed")
    for m in fails:
        print("  FAIL:", m)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
