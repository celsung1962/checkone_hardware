# CheckOne rev 1.1 — routing hand-off (2026-11-16)

**State.** The board `hardware/CheckOne/CheckOne.kicad_pcb` is autorouted and handed to the designer for interactive
finishing in KiCad. Connectivity: 1 open connection (J5 pin 1, GND). KiCad DRC: no clearance, short, hole or edge
error; schematic parity 0. AQTech audit (kicad-routing 1.29.0): 590 FAIL, almost all geometry of the router's output
(pad entries, off-centre tracks between pads). Datasheet layout checks: Kelvin and decoupling pass, one analog / digital
separation fails. Nothing committed yet.

## Setup applied (owner decisions 2026-11-16)

| Item | Decision / value |
|---|---|
| Stackup | 2 layers, 1 oz, JLCPCB 2L-1oz profile (`apply_settings.js`): min track 0.127, clearance rule 0.127, via drill 0.3 / pad 0.5 minimum, hole clearance 0.254, edge 0.5 mm, text height 1.0 mm |
| Netclasses | Default 0.2 mm / clearance 0.2 / via 0.5/0.3; POWER 0.5 mm / 0.2 / via 0.6/0.3 (28 nets, owner list + GND) |
| Shared pad gaps | not allowed (`shared_pad_gaps.allowed = false`) |
| Mounting holes | contact 6.4 mm (M3 head, hex spacer): rule areas KO_MECH_H1-H8, radius 3.7 mm, no tracks / vias / pour, both layers |
| Edge.Cuts | one closed rectangle, stroke set to 0.05 mm |
| Datasheet layout review | XL1509, INA226, ADS1115 applied, B2B-XH n/a (`kicad_golden.project.json` -> `datasheet_layout`, `layout_checks`) |

## Method

1. Export copy with export-only keep-outs (Y1, L1, L2 courtyards with pad corridors; 0.55 mm edge band; no vias in
   IC pad-row bands); DSN with every net; Freerouting 2.4.1, 100 passes, 1 thread, via cost 50, F.Cu vertical /
   B.Cu horizontal preferred. Result: 0 violations, 26 open connections (GND), 105 s.
2. SES imported into a copy without the export keep-outs; 10 dangling router vias removed; via flags set on 130 vias.
3. GND pours on F.Cu and B.Cu (0.3 mm clearance, thermal 0.5 / 0.5, min width 0.25), stitched with 0.6/0.3 vias on a
   4 mm grid where both pours have copper (pour islands closed in by long B.Cu tracks were stitched before island
   removal); 9 isolated GND pads joined to the nearest GND via with `route_finish.py`. 325 vias on the board.
4. Board installed; tool locks released (8 items); zones refilled.

## Datasheet layout checks (`layout_measure.py check`)

| Check | Result |
|---|---|
| Kelvin INA226 IN+ (U2.10 - R7.1, load C7.1) | PASS, no shared copper, 25.5 mm, 2 vias |
| Kelvin INA226 IN- (U2.9 - R7.2, load F11.1) | PASS, no shared copper, 8.0 mm |
| Decoupling U1.1-C11, U2.6-C13, U4.8-C40, U5.8-C41, U6.8-C42 | PASS, 2.1-2.6 mm, surface, no via |
| Separation SDA/SCL vs CH5-8_AIN, NTC1/2_ADC | PASS (0.52 mm, 2.15 mm) |
| Separation SDA/SCL vs CH1-4_AIN | **FAIL**: CH4_AIN 0.35 mm from SDA on B.Cu over 0.9 mm at (144.74, 87.65); move one of the two |

## Open items for the interactive router (in order)

1. **J5 pin 1 (GND) unconnected**, pad at (117.12, 115.75) F.Cu. Its axis is boxed in: +3.3V runs on F.Cu under J5,
   +3.3VA on B.Cu just above it, SCL / SDA from pins 2-3. The audit also FAILs the gap J5-1 / J5-MP, which carries
   +3.3V and SCL. Re-route +3.3V away from under J5 and give pin 1 its own GND via.
2. **CH4_AIN vs SDA** separation (above).
3. **Vias between the pads of two-pad parts** (audit `via`, 34 FAIL): R13 (V24_F), C5 (V24_D), D2 / D1 (VIN_F),
   R170 (CH7_IIN), C2 (VIN_S), C12 (+5V), LED4 (GND), and vias closer than 0.15 mm to SMD pads: move each via
   out on the pad axis with a short stub.
4. **Pad entries** (388 FAIL): the router enters most pads off-axis or ends off the pad centre. `refinish_gated.py`
   sampled 10: 3 kept, about 12 s each; the rest need neighbouring vias or tracks moved.
5. **Tracks between pads off centre** (73 FAIL) and **tracks below the class width** (67, mostly CHn_AIN, SDA, SCL,
   OSCO at 0.15 mm by the router).
6. **Under ferrite beads** (5 FAIL, crystal-inductor rule, FB12 and FB16 courtyards): CH2_IIN and CH5_AIN. A bead
   has no stray field worth keeping clear of; move the tracks, or record a project exception for FB* parts.
7. **Geometry**: 2 acute joints (+3.3VA at 117.22, 125.75 B.Cu; V24_D at 200.15, 88.16 B.Cu), 1 off-lattice segment
   (+3.3VA 116.95, 125.48), 1 GND self-crossing (149.60, 114.17 F.Cu), 5 GND track ends up to 0.16 mm off via centres.
8. **Thermal reliefs** starved (DRC): U2 pin 1 and J16 pin 2 (GND); acceptable or add a spoke.
9. ~~Silkscreen text below the JLCPCB 1.0 mm height~~ — done 2026-11-16 (owner: enlarge to 1.0 mm). All 63 board
   texts are 1.0 mm high with a 0.15 mm line (long labels and the LED labels 0.8 mm wide). Moved so that no text
   covers a pad, an outline, a designator or another text: CH labels 0.4 mm further from the terminals; test-pad
   labels vertical under each pad; LED labels right of the LEDs; display I2C labels split into pin names
   ("GND SCL SDA 3V3" above J5, "GND 3V3 SDA SCL" below J6) and module names ("I2C CYD", "I2C JC3248"); jack label
   "24V DC / (+) centro" on two lines left of J1. Designators re-placed: J5, J6, C404, C1, F1, J1, H6, R160, C41;
   LED1-LED4 designators hidden (no free spot; the LEDs are named by their labels). DRC `text_height` 0.
   `hw_checks` now FAILs only on the 2 starved thermal reliefs (item 8).
10. **3D models** (13 FAIL): J11-J18 (KF2EDGRC), L1 / L2 (FCH1040), J1 (DC-005), F1 (path not found).

After the interactive work: refill and save the zones, `kicad_audit.js` with `audit_gate.py` against this board,
`layout_measure.py check`, DRC (0 unconnected, 0 dangling), then the release (`hw_release.py`).

## Files

| File | Content |
|---|---|
| `hardware/CheckOne/CheckOne.kicad_pcb` | routed board (this hand-off) |
| `hardware/CheckOne/CheckOne.kicad_pro` | JLCPCB 2L-1oz rules, netclasses Default / POWER (POWER_DC, POWER_AC added by the template, unused) |
| `hardware/CheckOne/kicad_golden.project.json` | routing project parameters: fabricator, datasheet review, layout checks, mechanical keep-outs |
| `build/route/` (not in git) | DSN, rules, SES, Freerouting log, board snapshots (raw import, before stitching), audit JSON, renders |
| `build/CheckOne.pre_routing.kicad_pcb` (not in git) | the board before routing |
