# Changelog — kicad-placement skill

## 1.5.0 - 2026-11-19

Local reachability, adapted from KiStack's layout-placement (MIT, `references/third_party_kistack.md`), after a
comparison of KiStack with this skill (owner C. Souza). Distance rules said how far a part was from its pin, not
whether the tracks could still reach it.

- **`scripts/local_reach.py`** (new, KiCad's Python, read-only): per IC, a grid router on the IC's side checks the
  local links (signal nets as a spanning tree; supply rails only capacitor to pin) and the escapes of the other
  pins out of a ring around the IC. Two start orders and re-ordering passes; a link that fails even alone on an
  empty grid is BLOCKED (exit 1), one that never fits with the others is a WARN. Also: blocked pin fronts, the parts
  holding the strip in front of a pin whose part is farther than 2.6 mm, crowded neighbouring pins (radial widths
  over twice the pitch), ground pad facing the pin, ground pads without a via site, unbalanced two-pin parts across
  two signal pins, and an IC rotation score (advisory).
- Rules per net from the `.kicad_pro` net classes and the pads' resolved clearance, wider nets necked down to the
  Default width near the IC (`--neck`, `--no-neck`); `.kicad_dru` clearance rules are listed, not evaluated.
- Calibration on GapOne CON: the fabricated, routed layout passes with no WARN (39 s, 20 ICs); candidate 02 of the
  1.4.0 study passes with WARNs at U5 and U6. Two earlier versions of the selection were wrong on the fabricated
  board and were corrected before release: every part of four pads or fewer near the IC counted as local (a module
  pulled in parts 20 mm away), and rail capacitors of different ICs were linked part to part (the real board joins
  them through planes).
- SKILL.md Phase 3: `local_reach.py` after `verify_placement.py`; `placement_rules.md`: section "Local
  reachability" (placement order by tolerated distance, move the tolerant part, radial parts, neighbouring pins,
  pin fronts, pad orientation, IC rotation).

## 1.4.1 - 2026-11-15

- `candidates/run_placement.py`: candidates without a defect of their own come first, then by index. Before, one
  courtyard overlap between two locked parts (inherited from the source board, the same in every candidate) put
  all candidates in the "has a defect" class, so the order was by index alone and `--apply 3` wrote two boards
  with parts the engine had not legalised (GapOne CON: `08` and `06`, 2 parts each, ahead of the clean `02`).
- `candidates/evaluate.py`: metric `ov_fixed` (overlapping pairs whose two parts are locked or frozen).
- Gallery notes: "overlap" only for a candidate's own overlaps; a separate note for parts left without the
  requested spacing or against forbidden ground; the inherited overlap is stated as inherited.
- `candidates/route_candidates.py`: finds kicad-routing in `$KICAD_ROUTING_SCRIPTS`, then next to this skill (the
  project's copy), then in `~/.claude/skills`, and prints which one it uses. Before, only `~/.claude/skills`: the
  candidates were routed with whatever global copy was there (1.27.0 on the study machine), and the script failed in
  a project that carries only its own copy.

## 1.4.0 - 2026-11-15

Placement candidates, from the autorouter study on GapOne CON (owner C. Souza): an engine that generates complete
placements without a plan, so the engineer can compare several and choose.

- **`scripts/candidates/run_placement.py`** (new, with `extract_model.py`, `place_core.py`, `evaluate.py`):
  simulated annealing over position and 90° rotation of every unlocked footprint. Reads locked parts, the outline
  (inset by the copper-to-edge rule), footprint keep-outs, KiCad 10 placement rule areas (sheet / group /
  component class; on the board = hard region, name `ISO_*` = exclusive, outside the outline = grouping only),
  schematic clusters (hub = part with 4+ connected pads) and the decoupling entries of
  `kicad_golden.project.json` as pin pairs with a maximum distance. Weight profiles `balanced`, `wirelength`,
  `blocks`, `decoupling`; `--check`, `--freeze`, `--freeze-nets`, `--keep-tight`, `--repair`. Writes a gallery
  (HTML), a summary and the best candidates as bare board copies; the source board is never modified.
- **`--margin auto`** (default): the gap between courtyards is measured from the source placement (lower quartile
  of nearest-neighbour gaps, 0.15-0.6 mm). Before, a fixed 0.15 mm packed parts at a median 0.16 mm where the
  engineer keeps 0.55 mm, and the index rewarded it.
- New gallery rows: typical gap between neighbours, parts with a neighbour under 0.3 mm, plane pads without room
  for their via (`via_room`, also `via_room_report.py`; one index point per percent lost against the baseline).
- **`apply_placement.py`** (new): one candidate into a bare copy, with a pad-position proof of the rotation
  convention. **`route_candidates.py`** (new): routes candidate copies and the current placement with the
  kicad-routing skill on equal terms; strips placement-only rule areas first (KiCad's Specctra export writes them
  as full keep-outs); one board at a time.
- `references/candidates.md` (new); `SKILL.md`: section "Alternative — placement candidates", tools table;
  `pitfalls.md`: six entries.

Measured, and written into the skill so it is not oversold: at equal spacing the candidates tied with the manual
placement (index 102-104 vs 100); one Freerouting pass routed 590-604 of 684 connections on every placement at
either spacing. The index estimates; it does not predict routing completion.

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
