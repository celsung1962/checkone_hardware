#!/usr/bin/env python3
"""
Extracts from the schematic what the placer needs and the PCB does not carry (any Python 3 with sexpdata):

  pintypes.json  {"U1.18": ["power_in", "DVDD", "/+3V3"], ...} - electrical pin type and pin function of every
                 node, from an exported netlist. Footprint pads in the .kicad_pcb usually have NO pin type, so
                 decoupling capacitors cannot be recognised from the board alone (a placer that relies on
                 pad.GetPinType() silently finds no decoupling at all).
  schpos.json    {"R12": ["Power", 123.19, 45.72], ...} - sheet INSTANCE name (from the netlist sheetpath, the
                 same name the PCB footprints carry) and position of every reference in the
                 schematic. Used as the relative layout inside a block: the schematic is usually drawn in
                 signal-flow order, so mapping it into the block's box gives a sensible first placement.

Usage:
    kicad-cli sch export netlist --format kicadsexpr -o build/<p>.net hardware/<p>.kicad_sch
    python3 extract_schematic.py build/<p>.net hardware/ --out build/placement/
Requires: sexpdata (pip install sexpdata).
"""
import argparse, glob, json, os, re, sys

try:
    import sexpdata
    from sexpdata import Symbol as S
except ImportError:
    sys.exit("Install sexpdata: pip install sexpdata")


def kids(n, tag):
    return [c for c in n if isinstance(c, list) and c and c[0] == S(tag)]


def pintypes(netlist):
    d = sexpdata.loads(open(netlist, encoding="utf-8").read())
    out = {}
    for sec in d:
        if isinstance(sec, list) and sec and sec[0] == S("nets"):
            for n in sec[1:]:
                name = str(kids(n, "name")[0][1])
                for node in kids(n, "node"):
                    kv = {str(e[0]): str(e[1]) for e in node[1:] if isinstance(e, list) and len(e) > 1}
                    out[f"{kv['ref']}.{kv['pin']}"] = [kv.get("pintype", ""), kv.get("pinfunction", ""), name]
    return out


def sheetnames(netlist):
    """ref -> hierarchical sheet instance name from the netlist (e.g. "Sensor 13-24" for the second instance of
    sensor.kicad_sch). This is the name the PCB footprints carry; the file stem is not (one file can hold several
    instances, and a file's stem or title can be anything)."""
    d = sexpdata.loads(open(netlist, encoding="utf-8").read())
    out = {}
    for sec in d:
        if isinstance(sec, list) and sec and sec[0] == S("components"):
            for c in kids(sec, "comp"):
                ref = str(kids(c, "ref")[0][1])
                for sp in kids(c, "sheetpath"):
                    for nm in kids(sp, "names"):
                        out[ref] = str(nm[1]).strip("/")
    return out


def schpos(folder, names=None):
    out = {}
    files = [f for f in sorted(glob.glob(os.path.join(folder, "*.kicad_sch"))) if not re.search(r"(-bak|_old|backups)", f)]
    for f in files:
        sheet = os.path.basename(f)[:-len(".kicad_sch")]
        d = sexpdata.loads(open(f, encoding="utf-8").read())
        for n in d:
            if not (isinstance(n, list) and n and n[0] == S("symbol")):
                continue
            at = kids(n, "at")
            if not at:
                continue
            x, y = float(at[0][1]), float(at[0][2])
            refs = set()
            for inst in kids(n, "instances"):               # every instance of a multi-instance sheet
                for proj in kids(inst, "project"):
                    for path in kids(proj, "path"):
                        for r in kids(path, "reference"):
                            refs.add(str(r[1]))
            if not refs:
                refs = {str(p[2]) for p in kids(n, "property") if str(p[1]) == "Reference"}
            for r in refs:
                if not r.startswith("#"):
                    out.setdefault(r, [(names or {}).get(r) or sheet, x, y])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("netlist", help="netlist exported with kicad-cli (kicadsexpr)")
    ap.add_argument("schematic_dir", help="folder with the .kicad_sch files")
    ap.add_argument("--out", default=".", help="output folder for pintypes.json and schpos.json")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    pt, sp = pintypes(a.netlist), schpos(a.schematic_dir, sheetnames(a.netlist))
    json.dump(pt, open(os.path.join(a.out, "pintypes.json"), "w"), indent=0)
    json.dump(sp, open(os.path.join(a.out, "schpos.json"), "w"), indent=0)
    kinds = {}
    for v in pt.values():
        kinds[v[0]] = kinds.get(v[0], 0) + 1
    print(f"pintypes.json: {len(pt)} pins {dict(sorted(kinds.items(), key=lambda kv: -kv[1]))}")
    print(f"schpos.json:   {len(sp)} references on {len({v[0] for v in sp.values()})} sheets")


if __name__ == "__main__":
    main()
