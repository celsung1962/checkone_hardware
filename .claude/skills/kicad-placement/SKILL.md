---
name: kicad-placement
description: >-
  Component placement on KiCad PCBs (KiCad 8-10) with Claude Code: survey the board and its mechanical notes,
  budget area per functional block, write a placement plan (zones, blocks, anchors, keep-outs), run a block-based
  placer through KiCad's Python API (pcbnew) - or generate several candidate placements automatically and compare
  them in a gallery - then prove the result with DRC, a placement rule check (spacing,
  edge clearance, decoupling distance, thermal separation) and a placement-only diff. ALWAYS use this skill when
  the user wants to place, re-place, floorplan or pack components on a .kicad_pcb, asks to "place the parts",
  "do the placement", "organise the footprints on the board", "get the board ready for routing", pastes a
  placement prompt, asks where to put decoupling capacitors / connectors / regulators on the PCB, wants to move
  footprints from the staging area onto the board, check courtyard or edge clearances, hide silkscreen
  designators, or place a logo or title on the silkscreen - even without the word "skill". Not for routing,
  schematic drawing or footprint creation.
---

# kicad-placement — reviewable component placement on a KiCad board

| | |
|---|---|
| Skill version | 1.5.0 (see `CHANGELOG.md`) — local reachability: `local_reach.py` checks, IC by IC, that the local links still route on the IC's side, the other pins can escape, pin fronts are free, and reports which parts hold the spot of a far capacitor, crowded neighbouring pins, ground pads facing the pin and a better IC rotation (adapted from KiStack, MIT). 1.4.1 — candidate ordering: an overlap between two locked parts, inherited from the source board, no longer hides the candidates that have a defect of their own. 1.4.0 — placement candidates: `scripts/candidates/run_placement.py` generates complete placements by simulated annealing from the netlist, locked parts and the placement rule areas drawn on the board, scores them against the current placement and shows them in a gallery; `route_candidates.py` routes them on equal terms (reference `candidates.md`). 1.3.0 — analog signal passives: `signal_near.py` writes and measures proximity rules for the feedback / filter / detector parts of op-amps, switches and ADC inputs, `pack_passives.py` re-packs them (and the decoupling capacitors) around the pins after the IC floorplan is set. 1.2.0 — review against eight published placement guides: aluminium electrolytics heat-sensitive by default, test-point access and polarity-mark warnings in `verify_placement.py`, unnumbered plated holes are not THT pins. 1.1.1 — version field and changelog added, no change in behaviour. 1.1.0 — datasheet proximity rules (`near`): plan key checked by `verify_placement.py`, `_near_suggestions` written by `make_plan.py`. 1.0.0 — first release: survey, draft plan, block placer, rule check, placement-only diff, silkscreen helpers |

Placement is where a correct schematic turns into a board someone can route, assemble and fit in its enclosure.
Doing it by hand is slow; doing it with a naive script produces a pile of parts that ignores signal flow,
decoupling and mechanics. This skill places parts with a **plan** the engineer can read and change, a placer
that follows the plan, and **independent checks** that prove the result — and it tells you when the board
simply does not fit.

The method came from a real mixed-signal board (≈ 340 parts, one side, dense) and was then run on a second,
unrelated production board (≈ 350 footprints) from an automatic draft plan; every step answers a failure that
actually happened on one of them. `references/pitfalls.md` lists them.

## When the work starts

Typical inputs: a `.kicad_pcb` whose footprints were imported from the schematic (piled outside the outline),
with the outline, mounting holes and some connectors already placed by the engineer; the schematic project; often
a placement prompt with rules (`references/prompt_template.md` is a good one to adopt).

Placement only: never route, add vias, draw zones, change values, references, nets or footprints, and never move
what the engineer fixed (outline, holes, fixed connectors, parts already placed and locked).

## Tools

All scripts are in `scripts/`. The ones that touch the board run with **KiCad's Python** (it has `pcbnew` and
`numpy`): Windows `C:\Program Files\KiCad\<ver>\bin\python.exe`, macOS
`/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3`, Linux the
system `python3` with the KiCad package. `kicad-cli` (same folder on Windows) runs DRC. A KiCad MCP server, if the
session has one, can replace the API calls — but the checks below still apply.

| Script | Python | Purpose |
|---|---|---|
| `board_survey.py` | KiCad | Outline, **every note on Fab/User/Comments layers**, keep-outs, fixed/locked/outside parts, area budget |
| `extract_schematic.py` | any (sexpdata) | `pintypes.json` (pin type + function per pin, from the netlist) and `schpos.json` (schematic positions) |
| `make_plan.py` | KiCad | Draft plan: free-area regions, one block per sheet, catch-all; a to-do list for the agent; datasheet proximity candidates (`_near_suggestions`) |
| `place.py --budget` | KiCad | Demand vs free area per block of the plan |
| `place.py` | KiCad | The placer: plan → new board + report (decoupling distances, spills, improvements) |
| `verify_placement.py` | KiCad | Rule check: side, rotation, grid, spacing, edge, sensitive edge, keep-outs, datasheet proximity (`near`), decoupling, thermal (electrolytics included); warnings for test-point access and covered polarity marks |
| `compare_boards.py` | KiCad | Proves only placement changed (footprint content, drawings, tracks, zones, fixed parts) |
| `dump_board.py` + `render_placement.py` | KiCad + any (matplotlib) | Picture of the placement by block, with regions and keep-outs |
| `signal_near.py` | KiCad | Analog signal-passive proximity rules (op-amp / switch input and output pins, ADC inputs): measures them against targets, writes them to `near` |
| `pack_passives.py` | KiCad | Re-packs signal passives and decoupling capacitors around their analog ICs (optional IC moves first), by wire length, per block region |
| `local_reach.py` | KiCad | Local reachability per IC: local links routed on the IC's side (BLOCKED = fail), escapes out of a ring, blocked pin fronts, parts holding the spot of a far capacitor, crowded neighbouring pins, ground pad facing the pin, via sites, unbalanced two-pin parts, IC rotation score |
| `find_clear_spot.py` | KiCad | Clear spot for a title / logo artwork on either side; places it |
| `hide_silk_refs.py` | KiCad | Hides silkscreen designators (keeps the field) |
| `candidates/run_placement.py` | KiCad | Placement candidates without a plan: annealing from the netlist, locked parts and placement rule areas; gallery, scores against the current placement, board copies |
| `candidates/apply_placement.py` | KiCad | Writes one candidate into a bare copy of the board |
| `candidates/route_candidates.py` | KiCad (+ kicad-routing skill) | Routes candidate copies and the current placement on equal terms; comparison only |
| `candidates/via_room_report.py` | KiCad | Plane pads without room for their own via, per candidate |

## Phase 0 — Survey before touching anything

1. Back up the board (`<name>.pre-placement.kicad_pcb`) — or rely on a clean git state and say so.
2. `board_survey.py`. Read **all** the notes it prints. Mechanical notes on Fab/User layers ("electronics on the
   B side", "max height 3 mm under the module", "display rises through this cut-out") outrank a generic
   instruction such as "all parts on top": when they conflict, stop and ask — do not pick one silently.
3. Decide what is fixed. Parts already inside the outline but not locked were usually placed by the engineer
   (side-view LEDs at a panel, the MCU module): treat them as fixed and confirm. Footprints without pads (logos,
   artwork) are fixed automatically and, on the front layers, keep parts off (`artwork_obstacle`); rule areas drawn on the board that forbid footprints are honoured as
   keep-outs. A fixed pattern (`SW*`, `J*`) must not catch a part still outside the outline - it would never be
   placed (the scripts warn).
4. Settle the spacing. 0.3 mm between SMD courtyards is the default, not a law: production boards of some
   teams use 0.1-0.2 mm. Take the value from the user, the fab rules or the team's existing boards
   (`verify_placement.py` on an existing board shows its practice), and write it in the plan and the report.
5. Read the utilisation verdict. Courtyard area + spacing halo against free area: below ~55 % is comfortable,
   55–70 % needs careful regions, above ~75 % is probably infeasible at the requested spacing — **stop and report
   the deficit** (which zone overflows, by how much, and the options: other side, smaller packages, more area)
   instead of squeezing spacing.
6. An old or baseline layout is a hint, not a guide: check it for overlaps and parts inside other parts' bodies
   before borrowing its zones.

## Phase 1 — Plan

1. Export the netlist and run `extract_schematic.py`. Pin types matter: footprint pads in the board usually carry
   **no** pin type, so without `pintypes.json` decoupling capacitors cannot be recognised.
2. `make_plan.py` writes a draft: free area cut into rectangles, one block per sheet instance, each block given
   regions near each other at a common utilisation, shared rectangles sliced per block. The draft places every
   part legally but knows nothing of signal flow or heat; turn it into a floorplan (`references/plan_format.md`):
   - **signal flow from the fixed connectors**: connector → protection → conditioning → main ICs → outputs; parts
     that belong at a connector (TVS, ESD, PPTC, rail capacitors, output clamps) get their own small block placed
     first, next to it;
   - **one block per function**, not per sheet when a sheet holds several (one per channel; battery side vs.
     regulators); identical channels side by side or stacked, same orientation;
   - **heat sources and sensitive parts in different regions** (≥ 5 mm), fill `heat` / `heat_sensitive`;
   - **height**: tall parts out of areas under displays, covers or modules (`keepouts` with `refs`);
   - **utilisation per block region ≤ ~0.65** (`place.py --budget`); rebalance by moving a block, not by hoping;
   - block order = placement order: tight regions and big parts first, flexible blocks later, test points and
     fiducials last.
3. **Datasheet proximity (`near`).** Read the layout section of every IC datasheet: switching converters,
   current monitors, ADCs, clock sources, MCU modules, chargers. Turn each "close to" rule into a `near` entry,
   meaning a pad-to-pad maximum (`references/placement_rules.md`, "Datasheet proximity"). `make_plan.py` lists
   candidates it finds in the netlist under `_near_suggestions`:
   - oscillator ↔ clock pin, also through a series resistor;
   - shunt ↔ current monitor;
   - USB series resistor ↔ MCU pin;
   - ADC input capacitor ↔ input pin;
   - inductor ↔ switch pin;
   - flying capacitor ↔ its pins.

   Copy the ones that apply into `near`, add what the netlist cannot show, and give those parts `anchors` so the
   placer meets them. The placer does not move parts toward `near` targets by itself; `verify_placement.py` FAILs
   any entry that is not met.
   Why: On the ServiceOne main board (2026-10-05) six of ten datasheet layout findings made after routing were placement problems no router could fix: the ADC clock oscillator 24 mm from its pin (its trace shared a corridor with the analog inputs), an ADC input filter capacitor 10 mm from the pins, a current monitor 41 mm from its shunt, USB series resistors 31-40 mm from the MCU. None broke a spacing or edge rule. A clock that shares a corridor with analog inputs after autorouting can only be
   separated by moving parts.
4. **Analog signal passives.** Decoupling and datasheet rules do not cover the parts that set an analog
   circuit's behaviour: feedback and gain resistors, filter capacitors, the diodes and hold capacitors of a peak
   detector, the RC of a Sallen-Key, the series resistors of an analog switch. Plan the analog ICs as a chain (see
   `references/placement_rules.md`, "Analog signal passives"):
   - ICs of one signal chain next to each other, in signal order, with the pins that talk to each other facing;
     a dual op-amp has channel A on one side and B on the other, so stack two duals of a two-channel circuit
     with the same rotation and put each channel's parts on its own side;
   - leave room at the input and feedback pins - an IC hemmed in by decaps, modules and other blocks cannot get
     its passives close however they are packed;
   - write a `signal_near.py` config (ICs, ADCs, passives, pin weights) and treat its rules as part of the plan.
   Why: On GapOne CON (2026-11-05) the block placer passed every rule while the peak-detector diodes sat 12-16 mm
   from their op-amp, a Sallen-Key capacitor 20 mm from its op-amp and the ADC input resistors in another block
   (36 of 53 rules missed, worst 27 mm). Re-packing the passives alone, ICs fixed, only reached 38 misses: the
   space next to the pins was taken. Moving and turning the ICs first, then re-packing, gave 22 misses within
   3 mm of target.
5. Show the plan (zones, order, open questions) before placing when the user expects to review it.

## Phase 2 — Place

`place.py plan.json --out build/placement/placed.kicad_pcb` (about 6 min for 300 parts; run it in the
background on a slow machine). Always to a new file; iterate on the plan, not on
the output. After each run: read the report (failed, spilled, out of zone, decoupling), render it, and fix the
cause in the plan — a block that spills needs more region or less demand; a capacitor far from its pin usually
means its IC sits against an edge or another IC (move the IC's anchor or region).

Decoupling: the target is ≤ 2 mm pad-to-pad, but with 0.3 mm between courtyards 2.0–2.6 mm is often the
practical minimum. When spacing and proximity conflict, spacing wins — report the distance.

Analog blocks, after `place.py`: `signal_near.py plan.json placed.kicad_pcb analog.json` lists the signal passives
far from their pins. When it reports misses, set the IC floorplan (`ic_moves`: position and rotation of each analog
IC, chosen so the chain runs pin to pin) and run `pack_passives.py plan.json placed.kicad_pcb packed.kicad_pcb
analog.json`. It lifts the listed passives and the ICs' decoupling capacitors and re-packs them by wire length to
the pins, one region per block, then improves by relocation and pair swaps. Try two or three IC floorplans and keep
the one with the fewest misses (each run takes a minute or two). Finally `signal_near.py ... --write` puts the rules
into `near`, at the accepted limits when the targets cannot all be met, so `verify_placement.py` holds them from then
on.

## Alternative — placement candidates (no plan)

When the user wants several placements to choose from, a quick starting point, or a second opinion on a
plan-based placement, use the candidate generator instead of (or beside) Phases 1-2. Read
`references/candidates.md` first.

1. Phase 0 still applies: survey, decide what is fixed, and have the fixed parts **locked** on the board — the
   generator moves everything that is not locked.
2. Regions are drawn on the board, not written in a plan: a rule area with the Placement tab (sheet, group or
   component class). On the board it is a hard region; a name starting with `ISO_` makes it exclusive; drawn
   outside the outline it only keeps its members together. Run `run_placement.py BOARD --out OUT --check` and
   show the user what was read before generating.
3. `run_placement.py BOARD --out OUT -n 12 --apply 3`. Give `--margin` on a board with no placement yet; with an
   existing placement the default measures the gap that placement keeps. Show `OUT/gallery.html`.
4. The engineer chooses. A candidate with pin pairs beyond their limit goes through `--repair` (with
   `--keep-tight` and `--freeze-nets` as needed); say how many parts moved, the repaired board is not the one they
   looked at.
5. Phase 3 on the chosen copy, all of it. The generator's own scores are not a verification.

Report its limits with the result: no row alignment, no change of side, and an index that estimates — it does
not predict routing. Never write that a candidate "routes better" without a routed comparison
(`route_candidates.py --baseline`), and never promise a finished board from it.
Why: On GapOne CON (2026-11-14) candidates with index 76 (current = 100) were packed at 0.16 mm between
neighbours where the engineer keeps 0.55 mm; at equal spacing the best legal candidates scored 102-104. One
Freerouting pass routed 590-604 of 684 connections on every placement, the manual one included, at either
spacing: the advantage on paper came from the squeeze, and routing completion did not follow the index.

## Phase 3 — Verify (all of it, every time)

- Copy the project's `.kicad_pro` **and** `.kicad_dru` next to the new board under its name (`placed.kicad_pro`,
  `placed.kicad_dru`): without them DRC runs with default rules and reports the engineer's accepted exceptions
  as errors. Run the same DRC on the original board too: errors already there (fixed connectors butted
  together, a connector's own pads) are not placement errors - separate them in the report.
- `kicad-cli pcb drc --schematic-parity --format json` → 0 violations, 0 parity issues; "unconnected" is expected
  (not routed). `silk_over_copper` warnings from designators are a silkscreen job (`hide_silk_refs.py`), not a
  placement failure — say so.
- `verify_placement.py plan.json --board placed.kicad_pcb` → PASS, including every `near` entry. Report each `near`
  rule with its measured distance.
- Boards with analog circuits: `signal_near.py ... --targets` → report the rules against their targets (count,
  sum of excess, worst), and the remaining misses part by part.
- `local_reach.py placed.kicad_pcb --json reach.json` → no BLOCKED local link (exit 0). 40-90 s for the 20 ICs of
  GapOne CON; `--ic` for the ones you changed. For every WARN (links that route alone but not together, escapes) look at the corridor
  in the render; for every "far" pin move a part from the "held by" list - the one that tolerates distance - and
  run it again; treat "crowded", "GROUND PAD FACES PIN" and the rotation hint as placement suggestions to report.
  It routes with the net classes of the `.kicad_pro` (wider nets necked down to the Default width), ignores zones,
  and lists `.kicad_dru` clearance rules it does not evaluate. A pass is feasibility, not a route.
  Why: on GapOne CON (2026-11-14) one Freerouting pass completed 590-604 of 684 connections on every placement;
  distance rules passed while pins were boxed in. Calibration (2026-11-19): the fabricated, routed layout passes
  with no WARN and 3 blocked pin fronts; candidate 02 of the same study passes with WARNs at U5 and U6 and 6
  blocked pin fronts.
- `compare_boards.py original.kicad_pcb placed.kicad_pcb --plan plan.json` → placement-only PASS.
- Render and look. Numbers do not show a block split in two or a capacitor on the wrong side of an IC.
- At most three fix-and-rerun rounds on the same violation; then stop and list what remains.

## Phase 4 — Install and report

Copy the verified board over the project board (the backup or git holds the original), re-run DRC there (project
rules such as custom `.kicad_dru` apply only in the project), and report in this order: **Summary** (board size,
parts placed, all top side, DRC result) · **Floorplan** (zone → location) · **Decoupling** table (IC, capacitor,
pin, distance) · **Datasheet proximity** table (`near`: a, b, max, measured, datasheet section) · **Thermal** notes · **Flags & open issues** (conflicts, ambiguities, rules not met and why) ·
**Files**. Commit only when the user asks.

Afterwards, if asked: `hide_silk_refs.py` for designators; `find_clear_spot.py` for a title or a logo footprint
(the bottom side is usually free when the top is full; JLCPCB minimum silkscreen text 1.0 mm high, 0.15 mm stroke).

## References

- `references/placement_rules.md` — spacing, edge, decoupling, local reachability, thermal, orientation rules and
  STOP conditions.
- `references/plan_format.md` — the plan JSON, field by field, with an example.
- `references/pitfalls.md` — what went wrong on a real board and how the scripts now avoid it.
- `references/prompt_template.md` — a placement prompt for Claude Code that uses this skill.
- `references/third_party_kistack.md` — origin and licence of `local_reach.py` and the local reachability rules.
- `references/candidates.md` — the candidate generator: what it reads from the board, commands, how to read the
  gallery, routed comparison, limits.
