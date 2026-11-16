# Changelog — kicad-placement skill

## 1.3.0 - 2026-11-05

Analog signal passives, from the GapOne CON placement (owner C. Souza, D-339). The block placer passed every rule
while the parts that set the analog behaviour sat far from their pins: peak-detector diodes 12-16 mm from the
op-amp, a Sallen-Key capacitor 20 mm away, ADC input resistors in another block (36 of 53 proximity targets missed,
worst 27 mm).

- **`signal_near.py`** (new): one rule per (passive pad, IC signal pin) pair that share a net, for the ICs, ADCs and
  passives listed in a JSON config. Targets 4 mm at an input / switch pin, 6 mm at a low-impedance output, 8 mm from
  an ADC input divider to its ADC pin (pad centre to pad centre); per-pin weights (0 = a trace, no rule); rules only
  within one schematic sheet (except the ADC); supply nets excluded. Prints misses, count and sum of excess;
  `--write` puts the rules into the plan's `near` (at accepted `limits` when given), `--targets` measures against the
  targets.
- **`pack_passives.py`** (new): optional IC moves and rotations first (`ic_moves`), then the listed passives and the
  ICs' decoupling capacitors (`decaps`) are re-packed by wire length to the pins, one region per block, greedy then
  relocation passes then pair swaps; `mode: improve` only improves the current positions. Same box rules as
  `verify_placement.py`; bottom-side through-hole parts block the top side with their pads only; artwork only on the
  front layers. On GapOne CON it reproduces the result: 36 -> 22 misses, sum of excess 215.5 -> 35.7 mm.
- `placement_rules.md`: section "Analog signal passives" (targets, what is a trace and not a rule, IC floorplan of a
  chain, dual op-amps stacked by channel, packing order). `SKILL.md`: Phase 1 step 4, Phase 2 and Phase 3 steps.
  `pitfalls.md`: four new rows.

## 1.2.0 - 2026-10-30

Review of the skill against eight published placement guides (Altium, Sierra Circuits / ProtoExpress, Quick-teck,
PCBWay, EMA, PCB Power, JLCPCB, Cadence) on GapOne V2 (owner C. Souza). Most of their rules were already covered,
several with tighter numbers; three gaps were closed:

- **Electrolytic capacitors are heat-sensitive by default.** Aluminium electrolytics (footprint names in
  `electrolytic_footprints`: `CP_Elec`, `CP_Radial`, `CP_Axial`, `C_Elec`, `CP_THT`) join the plan's `heat_sensitive`
  list in `place.py` and `verify_placement.py` (`heat_sensitive_refs`). Evidence: on the GapOne CON board a 330 uF
  electrolytic (C48) sat 1.9 mm from the URB2405S module, unflagged because nobody had listed it.
- **Test-point access (WARN).** Plan key `testpoints`: probe pitch between test-point pads (2.54 mm), pad to any
  other courtyard (1.0 mm), pad to Edge.Cuts (1.0 mm), all test points on one side.
- **Polarity marks (WARN).** Plan key `polarity`: every polarised part (diodes, LEDs, ICs, transistors, polarised
  capacitors) keeps a silkscreen graphic that no other courtyard covers; parts without any silkscreen graphic are
  listed too. On GapOne CON it flags the 12 diodes and LEDs whose marks sit under overlapping parts.
- `is_tht` counts only numbered plated holes: an unnumbered plated hole (an LED light hole) no longer turns an SMD
  LED into a through-hole part with 1 mm iron-access spacing (GapOne CON D-319 / D-320 side-view LEDs).
- `placement_rules.md`, `plan_format.md`, `pitfalls.md` and `SKILL.md` updated. Warnings never fail the board.

## 1.1.1 - 2026-10-22

- Version field in `SKILL.md` and this changelog. No change in behaviour; the scripts and references are those of 1.1.0.

## 1.1.0 - 2026-10-05

- Datasheet proximity rules from the ServiceOne review: six of ten datasheet layout findings on the routed board were
  placement problems (ADC oscillator 24 mm from its pin, input filter capacitors far from the ADC, current monitor
  41 mm from its shunt) that passed every spacing and decoupling check.
- Plan key `near`: pad-to-pad maximum between two parts, a hard rule in `verify_placement.py`.
- `make_plan.py` writes `_near_suggestions` from the netlist: oscillator / clock pin (through a series part), shunt /
  current monitor, USB series parts / MCU, ADC input capacitors, inductor / switch pin, flying capacitors.
- `placement_rules.md`, `plan_format.md`, `pitfalls.md`, the prompt template and `SKILL.md` updated. Tested on
  ServiceOne: 12 suggestions; the 6 unmet ones are the review's placement findings.

## 1.0.0 - 2026-10-04

- First release: generic component placement for KiCad 8-10. Board survey (`board_survey.py`), draft plan
  (`make_plan.py`), block-based placer through pcbnew (`place.py`, `placement_core.py`), rule check
  (`verify_placement.py`), placement-only board comparison (`compare_boards.py`), render, silkscreen helpers
  (`hide_silk_refs.py`), `find_clear_spot.py`, `extract_schematic.py`, `dump_board.py`.
- Tested on the ServiceOne board (hand plan) and the TempOne board (automatic draft plan): verify and compare PASS on
  both, DRC parity 0. Pitfalls from the second board fixed and recorded in `references/pitfalls.md`.
