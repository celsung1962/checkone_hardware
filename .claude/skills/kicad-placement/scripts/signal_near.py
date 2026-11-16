"""Signal-passive proximity rules for analog ICs (run with KiCad's Python) - kicad-placement 1.3.0.

The block placer puts each block in its region and the supply capacitors at the supply pins, but it knows nothing of
the SIGNAL passives of an op-amp, a comparator or an analog switch: feedback resistors, filter capacitors, the diodes
of a peak detector. This script writes one `near` rule per (passive pad, IC signal pin) pair that share a net and
measures them, so verify_placement.py can hold them.

For every part in the config's "passives" and each of its pads that shares a net with a signal pin of an IC in "ics":
  input / switch pin (weight 3, the default)  -> target 4 mm, pad centre to pad centre
  low-impedance output pin (weight 1)          -> target 6 mm
  ADC input pin (an IC in "adc")               -> target 8 mm (an input divider sits at the ADC, not at the op-amp)
  weight 0                                     -> no rule (a net that is only a trace: a low-impedance output driving
                                                  a switch input, a net that passes to another block)
A rule is written only when the passive and the IC are on the same schematic sheet (or the IC is an ADC): a net that
leaves the block is a trace, not a part rule. Parts in "adc_side" skip the op-amp output rule. Supply and ground nets
never make rules ("supply_nets" regex). A follower (OUT tied to -IN) gives one rule, to the nearest pin.

Usage: <kicad-python> signal_near.py plan.json board.kicad_pcb config.json [--write] [--targets]
  --write    replace the plan's earlier "analog:" near entries with these (max_mm = the accepted "limits" if given,
             else the targets)
  --targets  measure against the targets even when "limits" exist (report only)
config (JSON): {"ics": ["U13", "U14"], "adc": ["U6"], "passives": ["R61", "C32", ...],
                "weight": {"U13.7": 1, "U14.3": 0}, "adc_side": ["R75"],
                "limits": {"input": 7.5, "output": 8, "adc": 11}, "supply_nets": "<regex>"}
"""
import json, math, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcbnew
from placement_core import mm, matches

SUPPLY = r"(?i)(GND|^[+-]?\d+(\.\d+)?V|^[+-]\d|VCC|VDD|VEE|VSS|VBAT|CHASSIS|EARTH|SHIELD)"
TARGET = {"input": 4.0, "output": 6.0, "adc": 8.0}


def build(cfg, fps):
    sup = re.compile(cfg.get("supply_nets", SUPPLY))
    W = cfg.get("weight", {})
    adc = cfg.get("adc", [])
    ics = [r for r in fps if matches(r, cfg["ics"] + adc)]
    pins = {}
    for u in ics:
        for p in fps[u].Pads():
            n = p.GetNetname().strip("/")
            if n and not sup.search(n) and not n.startswith("unconnected"):
                pins.setdefault(n, []).append((u, p))
    out = {}
    for r in [x for x in fps if matches(x, cfg["passives"])]:
        for p in fps[r].Pads():
            n = p.GetNetname().strip("/")
            for u, q in pins.get(n, []):
                w = W.get(f"{u}.{q.GetNumber()}", 3)
                is_adc = matches(u, adc)
                if w == 0 or (not is_adc and fps[u].GetSheetname() != fps[r].GetSheetname()):
                    continue
                if is_adc:
                    kind = "adc"
                elif r in cfg.get("adc_side", []):
                    continue
                else:
                    kind = "input" if w >= 3 else "output"
                d = math.hypot(mm(p.GetPosition().x - q.GetPosition().x), mm(p.GetPosition().y - q.GetPosition().y))
                key = (f"{r}.{p.GetNumber()}", u, n)
                if key not in out or d < out[key]["dist"]:
                    out[key] = {"a": key[0], "b": f"{u}.{q.GetNumber()}", "kind": kind, "dist": round(d, 2), "net": n}
    return list(out.values())


def main():
    plan_path, board, cfg_path = sys.argv[1:4]
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    b = pcbnew.LoadBoard(board)
    fps = {f.GetReference(): f for f in b.GetFootprints()}
    rules = build(cfg, fps)
    lim = {} if "--targets" in sys.argv else cfg.get("limits", {})
    fails = sorted([e for e in rules if e["dist"] > lim.get(e["kind"], TARGET[e["kind"]])],
                   key=lambda e: e["dist"] - lim.get(e["kind"], TARGET[e["kind"]]), reverse=True)
    excess = sum(e["dist"] - lim.get(e["kind"], TARGET[e["kind"]]) for e in fails)
    print(f"{len(rules)} rules, {len(fails)} not met, sum of excess {excess:.1f} mm")
    for e in fails:
        print(f"   {e['a']:10s} -> {e['b']:8s} {e['dist']:6.2f} mm (max {lim.get(e['kind'], TARGET[e['kind']])}, {e['kind']}) {e['net']}")
    if "--write" in sys.argv:
        j = json.load(open(plan_path, encoding="utf-8-sig"))
        why = {"input": "signal passive at an IC input / switch pin", "output": "signal passive at a low-impedance output pin",
               "adc": "input divider / filter at the ADC pin"}
        new = [{"a": e["a"], "b": e["b"], "max_mm": cfg.get("limits", {}).get(e["kind"], TARGET[e["kind"]]),
                "why": f"analog: {why[e['kind']]} (target {TARGET[e['kind']]:g} mm)"} for e in rules]
        j["near"] = [e for e in j.get("near", []) if not str(e.get("why", "")).startswith("analog:")] + new
        json.dump(j, open(plan_path, "w", encoding="utf-8"), indent=1)
        print(f"{len(new)} near entries written to {plan_path}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
