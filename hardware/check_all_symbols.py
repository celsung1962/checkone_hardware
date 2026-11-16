#!/usr/bin/env python3
"""Run the skill's check_symbol_pins.py on every part of both project libraries (kickoff Phase 2).
Prints one line per symbol and exits non-zero if any symbol differs from its datasheet pin table.
One accepted difference: a hidden pin stacked on a visible pin of the same name is passive (KiCad library convention;
hardware/build_symbol_lib.py custom_symbol) - a hidden power_in pin would create an implicit global net.
    python hardware/check_all_symbols.py
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from build_symbol_lib import BOTH, PARTS  # noqa: E402

CHECK = os.path.join(ROOT, ".claude", "skills", "kicad-schematic", "scripts", "check_symbol_pins.py")


def hidden_passive(lib, name):
    """Pin numbers of `name` that are hidden and passive (stacked duplicates)."""
    t = open(lib, encoding="utf-8").read()
    i = t.find(f'(symbol "{name}"')
    j = t.find('\n\t(symbol "', i + 1)
    s = t[i:j if j > 0 else len(t)]
    return {m.group(1) for m in re.finditer(r'\(pin passive line\s*\(at[^)]*\)\s*\(length[^)]*\)\s*\(hide yes\)'
                                            r'[\s\S]{0,200}?\(number "([^"]+)"', s)}


fails = 0
for board in BOTH:
    lib = os.path.join(HERE, board, f"{board}.kicad_sym")
    for p in PARTS:
        if board not in p["boards"]:
            continue
        csvp = os.path.join(ROOT, "docs", "datasheets", f"{p['csv']}_pins.csv")
        r = subprocess.run([sys.executable, "-X", "utf8", CHECK, lib, p["name"], csvp], capture_output=True, text=True)
        lines = r.stdout.strip().splitlines()
        stacked = hidden_passive(lib, p["name"])
        errs = [ln for ln in lines if re.match(r"\s*- pin ", ln)]
        other = [ln for ln in lines if re.match(r"\s*- ", ln) and ln not in errs]
        real = other + [ln for ln in errs if not (re.match(r"\s*- pin (\S+) .*≠ symbol \['passive'\]$", ln)
                                                  and re.match(r"\s*- pin (\S+)", ln).group(1) in stacked)]
        ok = r.returncode == 0 or bool(errs and not real)
        last = (lines or [""])[-1] if r.returncode == 0 else \
            (f"PASS — all pins match ({len(errs)} hidden stacked pin(s) passive)" if ok else
             next((ln for ln in lines if "FAIL" in ln), lines[-1]).strip())
        print(f"{'PASS' if ok else 'FAIL'}  {board:11s} {p['name']:20s} {last}")
        if not ok:
            fails += 1
            for ln in real[:8]:
                print("      ", ln)
print(f"\n{fails} symbol(s) FAIL")
sys.exit(1 if fails else 0)
