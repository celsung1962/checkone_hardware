# Placement rules

Defaults used by the scripts; a project brief or the user's prompt may tighten them (never loosen silently).

## Fixed elements

- Board outline, mounting holes, fixed connectors, switches, battery holders and parts the engineer already
  placed are never moved, rotated or flipped. Lock them (they are the mechanical anchors).
- Before placing, read every note on non-copper layers. A note that contradicts the task (which side carries the
  electronics, height limits, cut-outs) is a STOP: ask.

## Side, orientation, grid

- Single-sided assembly unless the user says otherwise: every movable part on the top side; flip bottom parts to
  the top and report them.
- Rotations 0 / 90 / 180 / 270 only. Two-terminal passives 0 or 90; polarised parts, ICs, diodes may use all four.
- Origins on a 0.25 mm (or 0.5 mm) grid.
- Consistency where the floorplan allows: same pin-1 corner for ICs of a block, same cathode side for diodes and
  LEDs of a row, identical channels in identical orientation. Report where it was not possible.

## Clearances

| Pair | Minimum |
|---|---|
| Courtyard ↔ courtyard, SMD | 0.3 mm |
| Small part next to a much taller one | 0.5–1.0 mm (report if not applied) |
| Around through-hole parts | 1.0–1.5 mm, soldering-iron access to every pin |
| Around mounting holes (beyond their courtyard / keep-out) | 1.0 mm |
| Courtyard ↔ board edge | 1.0 mm |
| Fine-pitch ICs (≤ 0.65 mm pitch), MLCC > 0805, crystals ↔ edge | 2.5 mm (flex cracking) |

Edge-mounted connectors fixed by the engineer are exempt. Courtyards include the IPC margin already, so 0.3 mm
between courtyards is ~0.8 mm between bodies.

## Decoupling and power

- Each bypass capacitor as close as possible to the power pin it serves (target ≤ 2 mm pad-to-pad), smallest value
  closest, GND pad toward the IC's ground, loop as small as possible.
- When proximity and spacing conflict, spacing wins: place as close as the spacing allows and report the distance.
- If an IC has no identifiable decoupling capacitor in the netlist, do not invent one; flag it.
- Every supply pin gets its own capacitor - op-amp V- included. On a dual-supply op-amp a capacitor 9.5 mm
  from V- was missed because only V+ was looked at (ServiceOne, 2026-10-05).
- High-current loops compact (input → switch → regulator → output); input and output capacitors at the
  regulator, inductor next to its switch pin.

## Datasheet proximity (`near`)

Some datasheet layout rules decide where parts go, and no router can fix them later. Write each one as a `near`
entry in the plan: pad-to-pad distance between `a` and `b` (`REF.PAD`, or `REF` for the nearest pad) at most
`max_mm`. `verify_placement.py` FAILs any that is not met. Starting values, to be tightened from the datasheet:

| Pair | max_mm | Why |
|---|---|---|
| Oscillator / crystal output ↔ IC clock pin (through its series resistor) | 5 | Short clock, placed on the digital side of the IC, so that it never shares a corridor with analog inputs |
| ADC input filter capacitor ↔ ADC input pin | 3 | The datasheet asks for the RC at the pins, with short direct traces |
| Shunt ↔ current monitor (INA2xx and similar) | 6 | Short dedicated Kelvin sense lines; a monitor far from its shunt ends up sensing the power track |
| USB series resistor / capacitor ↔ MCU USB pin | 3 | Series parts close to the chip side |
| Converter inductor ↔ switch pin | 5 | Small switch node (the hot loop) |
| Flying / bootstrap capacitor ↔ its pins | 3 | Charge-pump and bootstrap loops |
| PROG / RSET / feedback resistor ↔ its pin | 3 | Small parasitic capacitance on a high-impedance node |

`make_plan.py` proposes candidates from the netlist (`_near_suggestions`); they are suggestions, and each one
copied into `near` is a decision.
Evidence: On the ServiceOne main board (2026-10-05) six of ten datasheet layout findings made after routing were placement problems no router could fix: the ADC clock oscillator 24 mm from its pin (its trace shared a corridor with the analog inputs), an ADC input filter capacitor 10 mm from the pins, a current monitor 41 mm from its shunt, USB series resistors 31-40 mm from the MCU. None broke a spacing or edge rule.

## Analog signal passives (`signal_near.py`, `pack_passives.py`)

The parts that set an analog circuit's behaviour go at the pins they serve, and the IC floorplan is what makes that
possible. Targets (pad centre to pad centre; with 0.3 mm courtyard spacing about 4 mm is "next to the pin"):

| Passive on … | Target | Examples |
|---|---|---|
| an op-amp input or feedback node, a switch / mux pin (weight 3) | 4 mm | gain and feedback resistors, filter and hold capacitors, peak-detector diodes, the series R of a switch output |
| a low-impedance op-amp output (weight 1) | 6 mm | output series R, the far end of a feedback network, Sallen-Key feedback C |
| an ADC input pin | 8 mm | input divider, anti-alias R / C (the datasheet `near` rule for the input capacitor stays at 3 mm) |

What is a trace, not a rule (weight 0 or excluded):

- a net that leaves the block (an output that feeds another block's input): the trace is low-impedance, the
  passive belongs to the block it is drawn in. Rules apply only between a passive and an IC on the same sheet,
  except for the ADC;
- a low-impedance output driving a switch input (op-amp → mux S pins);
- source terminations: a series resistor on a clock or reference line sits at the driver (the GPIO, the oscillator),
  not at the receiving pin;
- an input divider in front of an ADC sits at the ADC; the op-amp output carries the long trace.

Floorplan of the analog ICs, before packing:

- one chain = ICs side by side in signal order, connected pins facing (turn a mux so its outputs face the next
  op-amp, a dual op-amp so the channel that feeds the next stage faces it);
- a dual op-amp has channel A on one side and channel B on the other: two duals of a two-channel circuit (peak
  detector + buffer) are stacked with the same rotation, channel A parts on one side, channel B on the other;
- a stage that ends at an ADC sits next to the ADC inputs;
- room at the input / feedback pins: no decoupling capacitor, module or foreign-block part there. Supply pins of
  most op-amps are at the corners, so decaps take the corners and the signal passives the sides.

Packing: `pack_passives.py` with one region per block (without regions a greedy packer mixes blocks), decaps first
with a high weight (12) so the swaps cannot trade them away, then the parts at input pins, then the rest, test points
last. Rail test points and stray parts near the core may be listed as movable without a region: they stay near their
old spot. Result accepted when every rule is within a few millimetres of its target; write the accepted limits to
`near` (`signal_near.py --write`) so later changes cannot undo it.

## Thermal

- Regulators, power switches and transistors, shunts and power resistors (> ~0.25 W): away from precision
  references, ADCs, crystals and analog front-ends (≥ 5 mm), not clustered together, room left for copper.
- Aluminium electrolytic capacitors are heat-sensitive too: their life halves for about every 10 K. They are added to
  `heat_sensitive` automatically by footprint name (1.2.0); keep them ≥ 5 mm from DC/DC modules, regulators and
  power resistors, the bulk capacitor of a module included (place it on the side away from the module's hot face).

## Test points (warnings)

- Probe access: pad centre to pad centre ≥ 2.54 mm, pad ≥ 1.0 mm from any other courtyard and from the board edge,
  all on one side (bench probing or a single-sided fixture). Defaults; the tester sets the real numbers.
- Test points go last in the placement order, so these are the first to run out of room: budget them.

## Polarity marks (warnings)

- Polarised parts in a row point the same way (see "Side, orientation, grid").
- Every polarised part (diode, LED, IC, transistor, polarised capacitor) keeps its silkscreen polarity or pin-1
  graphic visible: not under another part's courtyard, not deleted. Hiding designators (`hide_silk_refs.py`) does not
  touch these graphics. A board whose designators stay visible (a prototype, bench rework) says so in the plan.

## Functional zones

- Follow signal flow from the fixed connectors; keep each circuit together; do not interleave zones.
- Parts that protect or filter a connector sit at that connector.
- Heights: no tall part in an area with a height limit (display, cover, module above).

## STOP conditions

- The parts do not fit at the minimum spacing (utilisation > ~75 % or failures after rebalancing): report the
  area deficit and the overflowing zone; never shrink spacing below the minimums or move a fixed part.
- A mechanical note on the board contradicts the instructions.
- A part's function is ambiguous: place it next to the part it shares most nets with and flag it.
- Three rounds of fixes did not clear a placement violation: stop and list what remains.

## Report

1. **Summary** — board size, parts placed, all on top (yes/no), DRC result.
2. **Floorplan** — zones and their location.
3. **Decoupling check** — IC | capacitor | pin | distance (mm).
4. **Thermal notes** — heat sources and their distance to sensitive parts.
5. **Flags & open issues** — ambiguities, rules not met and why, DRC items left.
6. **Files** — saved board and backup.
