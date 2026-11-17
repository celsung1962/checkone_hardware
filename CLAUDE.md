# CheckOne — Hardware brief for Claude Code (KiCad)

AQTech Power Prognostics · Hardware owner: Celso Souza · v1 schematic and placement: Sergio Zimath ·
Brief revision: 2026-11-16 (rev. 2 — rev 1.1 of the board: review changes applied, schematic redrawn in the GapOne style)

This file is the hardware contract. [FROZEN] items are locked; [PROPOSED] items are calculated starting points that
may be refined with justification; [OPEN] items must not be closed by the agent.

The v1 board (S. Zimath: schematic and placement, not routed, not fabricated) is now **revision 1.1**: the changes of
`reports/CheckOne/review_2026-11-16.md` applied by the owner's decision of 2026-11-16 ("aplique todas as mudanças"),
the schematic redrawn in the GapOne V2 style, the placement kept. The decisions in section 2 come from the
description; they are [FROZEN] once the owner confirms them (O1).

## 0. Working rules
1. Language: everything in English — reports, commits, `calc/` scripts and all schematic content. Chat replies
   follow the user's language.
2. Conclusion first, then the justification.
3. Every number backed by a script in `calc/` (`calc/checkone_budget.py`: measurement, NTC, fault current, budget).
4. Pinouts only from datasheets in `docs/datasheets/` (listed in `manifest.csv`, 27 documents). No symbol is drawn or
   changed without its datasheet on disk and its pin table `docs/datasheets/<part>_pins.csv`.
5. No silent workarounds: infeasibility → stop and report with evidence and alternatives.
6. `kicad-cli sch erc` after every sheet and before every commit; `python tools/hw_checks/hw_checks.py` before every
   commit (ERC / DRC against `tools/hw_checks/baseline/`, datasheet manifest).
7. Form follows the v1 project and the AQTech repositories (GapOne_V2); engineering follows this brief.
8. Source documents: `docs/requirements/` — start with `CheckOne_requirements.md` (English, consolidated, with the
   conflicts C-1…C-14 and gaps G-1…G-8); the Portuguese description is the source of truth for the product.
   `meeting_2026-11-16_Sergio.md` holds Sergio's requests: review the electronics, route, check the fit in the
   enclosure, order with the AMP. He allows any change but wants the important ones reported to him before the
   version is closed: list every such change in the rev 1.1 report.
9. **The schematic is generated** (as GapOne): `hardware/build_symbol_lib.py` (project symbols, pins checked
   against the pin tables; `hardware/check_all_symbols.py`), `hardware/gen_checkone.py` (root + 6 A4 sheets with
   `hardware/schgen.py`) — never hand-edit the `.kicad_sch`. Then export the netlist and run
   `hardware/sync_board.py` with KiCad's Python: it reloads every footprint from its library at the same place and
   sets values, fields, paths and nets (the "Update PCB from Schematic"); the board itself (placement, routing) is
   edited in KiCad. Gate after a schematic change: ERC 0, `check_drawing.py` 0 hits, `fix_passive_text.py` 0 to
   move, `check_revision.py --rev 1.1`, DRC parity 0, `hw_checks.py` PASS. S. Zimath's v1 generator
   (`gerador/design.py`) is retired; it stays in `reference/import_2026-11-16/` and in the git history.

## 0.1 Reference [FROZEN]
- v1 KiCad project (KiCad 7 files): hand-over in `reference/import_2026-11-16/` (outside git, `OUTSIDE_GIT.md`),
  including S. Zimath's update of 10:56 (`update_S_Zimath_1057/`); imported as is at commit `eac4dd2`.
- Form of the repository, the schematic, the checks, release and documentation: GapOne_V2
  (`aqtechengenharia/gapone_hardware`).

## 1. The product in one paragraph
CheckOne is AQTech's production test fixture for GapOne and FluxOne sensors: up to eight sensors are powered with
24 V and their isolated 4–20 mA loops are measured on 120 Ω 0.1 % shunts by two ADS1115s; the reading is converted
to millimetres (GapOne-15 / -25 / -50), millitesla (FluxOne) or raw mA, judged against NAMUR NE43 and shown on a
3.5" display module (CYD ESP32-3248S035R inside the AK-P-08A DIN-rail enclosure, or a Guition JC3248W535 / external
4.3" JC4880P443C) and on a web page served over Wi-Fi. It also measures the sensor supply (INA226), two NTC
temperatures (third ADS1115, probe up to 150 °C), keeps time (PCF8563 + CR2032) and logs 48 h of data. One main board,
122 × 87 mm, 2 layers, JLCPCB SMD assembly with hand-soldered THT parts. Not sold; up to five units per network.

## 2. Decisions from the description [FROZEN after O1]
| Item | Value | Notes (reason; rejected alternative) |
|---|---|---|
| D1 Channels | 8 × 24 V always on, 4–20 mA measured on 120 Ω 0.1 % to GND, Iout = fixture GND | sensor outputs are isolated, so no isolation in the fixture; 120 Ω leaves more voltage to the sensor than 250 Ω (DS 10). Per-channel switching, automatic pass / fail and galvanic isolation rejected for v1 (DS 10, 12) |
| D2 Converters | 3 × ADS1115 on I²C 400 kHz (0x48, 0x49, 0x4A), polled; INA226 0x40; PCF8563 0x51 | ADS131M08 kept as a future idea only (DS 12.3) |
| D3 Processor | the display module's ESP32 (CYD / JC3248W535 / JC4880P443C), no MCU on the board | |
| D4 Displays | three modules, one at a time; J_PWR + J_I2C_CYD / J_I2C_JC (MX1.25), J_EXT 1 × 4 2.54 mm | both modules are I²C masters on the same bus |
| D5 Input | 24 V ±5 % (25.2 V max), 1.6 A PTC, SMBJ24A, SS34, AO4485 soft start, π filter 68 µH | soft start removes the plug spark (DS 5.1) |
| D6 Rails | XL1509-5.0 (5 V, 2 A) → XC6206P332 (3.3 V); 3V3A by 10 Ω / 1 µF; display 3.3 V pins only drive the 3V3D LED | measurement does not depend on the display's regulator |
| D7 Channel protection | PTC 200 mA, bead + 100 nF at the terminal; input SMAJ5.0A, 1 kΩ, BAT54S, 10 nF | |
| D8 Mechanics | AK-P-08A, board 122 × 87 mm, holes 115 × 80 mm; CH1–4 + 24 V left, CH5–8 + NTC1 + LEDs right (in use, turned 90°); KF2EDGRC-5.08-4P, pinout +24 / GND / Iin / Iout | DS 7 |
| D9 Assembly | JLCPCB SMD (codes in DS 8.1), THT hand-soldered from LCSC | |

## 3. Open items [OPEN]
- **O1 — Confirm the description as the contract.** Owner to confirm section 2. The conflicts that changed the board
  were decided on 2026-11-16 ("aplique todas as mudanças") and are in rev 1.1: C-5 (R6 fitted, D4 DNP), C-6 (INA226
  stays on +3.3V; the description is to be corrected), C-7 (test pads 2.0 mm), C-9 / C-10 (J2, LED1-LED4 moved),
  C-12 (R1n1 4.7 kΩ). Still open: C-1…C-4, C-8, C-13, C-14. **Sergio is to be told the rev 1.1 changes before the
  version is closed** (`reports/CheckOne/review_2026-11-16.md`, "Applied in rev 1.1").
- **O2 — How the project is edited.** Decided 2026-11-16: schematic generated in the GapOne style (rule 9), board
  edited in KiCad after `sync_board.py`; v1 generator retired.
- **O3 — Datasheets.** 27 on disk (`docs/datasheets/manifest.csv`, incl. the 25 ppm shunt C2989146); pin tables for
  the 12 project symbols; the datasheet check passes. Still missing: GZ2012D601TF (no PDF at LCSC; a passive, not
  enforced) and the display modules (O5).
- **O4 — Fault current into 3V3A (C-12).** Closed in rev 1.1: R1n1 4.7 kΩ (0.6–0.8 mA per channel, filter 3.4 kHz,
  gain error 0.11 % calibrated out, `calc/checkone_budget.py` item 3). Bench check in section 15.
- **O5 — Items to confirm on real parts (DS 11):** CYD size and holes (C-8; H5–H8 at 87 × 49 mm), enclosure window
  walls and ribs vs the 12.2 mm terminal bodies, sensors' start-up current vs the 200 mA PTCs, CYD display
  controller, JC4880P443C 26-pin pinout, SMAJ5.0A leakage at 2.5 V, AQTech logo SVG.
- **O6 — Simulation files (G-1).** The ngspice netlists and results of DS 9 are not in the hand-over.
- **O7 — Sensor consumption (G-3).** GapOne / FluxOne current per sensor, for the budget and the PTC choice.
- **O8 — Revision and date.** Done: rev 1.1, 2026-11-16 in every title block and on the board
  (`check_revision.py --rev 1.1` PASS); silkscreen "rev 1.1".
- **O9 — Fit in the enclosure (C-14, G-8).** Outline 122.1 × 87.1 mm, holes on 115.00 × 80.00 mm (unchanged). The
  terminals J11–J18 are on v1's pin rows (9.95 mm from the long edges): the KF2EDGRC body is 12.2 mm deep on the board
  (S. Zimath measured it, 2026-11-16), so its front sits 0.95 mm beyond the edge, as v1's 3D study assumed. The rev 1.1
  8.4 mm outline and 3.8 mm shift were wrong and are reverted. Confirm against the AK-P-08A drawing.
- **O10 — Order with the AMP.** Owner's call, after routing and the routing audit.

## 4. KiCad project structure
`hardware/CheckOne/`, KiCad 10 files: root `CheckOne.kicad_sch` and six A4 sheets — `Power_Input` (DC jack, PTC,
TVS, reverse diode, soft start, pi filter), `Power_Rails` (5 V buck, display 5 V, INA226, 3.3 V / 3.3VA, LEDs, I²C
pull-ups, test pads), `Channels_1_4`, `Channels_5_8`, `ADC_NTC` (3 × ADS1115, NTC inputs), `Display_RTC` (display
connectors, RTC, mounting holes). Inter-sheet nets through SHEET PORTS (CHn_AIN, SDA, SCL) and power symbols. Board
`CheckOne.kicad_pcb`: 122 × 87 mm, 2 layers, S. Zimath's placement, not routed. Project library `CheckOne`
(`CheckOne.kicad_sym`, built; `CheckOne.pretty`: KF2EDGRC-5.08-4P, DC-005-A200, BS-02-A1AJ006, L_Fangcheng_FCH1040).
`CheckOne.net`: netlist (166 parts, 70 nets).
## 4.1 Parts policy [FROZEN]
SMD parts assembled by JLCPCB with the LCSC code in the `LCSC` field; THT parts and loose items bought from LCSC
and hand-soldered (DS 8). For new parts copy `.claude/skills/kicad-schematic/references/jlcpcb_policy.md` here.

## 5. Channel / signal map [FROZEN after O1]
| Signal | Path | Level | Terminal |
|---|---|---|---|
| CHn +24 | +24V_SENS → F1n (200 mA) → FB1n → CHn_OUT, C1n0 100 nF | 24 V | Jn pin 1 |
| CHn loop | CHn_IIN → R1n0 120 Ω 0.1 % 25 ppm → GND; D1n SMAJ5.0A; R1n1 4.7 kΩ → CHn_AIN, D2n BAT54S, C1n1 10 nF → U4 (n = 1–4) / U5 (n = 5–8) | 0.48–2.52 V for 4–21 mA | Jn pin 3 Iin, pin 4 Iout = GND, pin 2 GND |
| NTC1 / NTC2 | R4x0 10 kΩ from +3.3VA, C4x3 1 µF, R4x1 1 kΩ, D4x BAT54S, C4x4 10 nF → U6 AIN0 / AIN2; U6 AIN1 = +3.3VA | 0.55–3.27 V | J2 (front), J3 (inside) |
| Sensor supply | V24_F → R7 ∥ R13 (50 mΩ) → +24V_SENS, INA226 U2 | 24 V | — |

(Jn = J11…J18 for CH1…CH8.)

## 6. Critical IC connections (rev 1.1, pin tables from the datasheets: `docs/datasheets/*_pins.csv`)
ADS1115 VSSOP-10 (TSSOP-10_3x3mm footprint): 1 ADDR (U4 GND → 0x48, U5 VDD → 0x49, U6 SDA → 0x4A), 2 ALERT/RDY (NC), 3 GND, 4–7 AIN0–3,
8 VDD (3V3A), 9 SDA, 10 SCL. INA226 VSSOP-10: 1 A1, 2 A0 (both GND → 0x40), 3 ALERT (NC), 4 SDA, 5 SCL, 6 VS (+3.3V; the
description says 3.3VA: C-6), 7 GND, 8 VBUS, 9 IN−, 10 IN+. PCF8563T SO-8: 1 OSCI, 2 OSCO, 3 INT, 4 VSS, 5 SDA, 6 SCL,
7 CLKOUT, 8 VDD (VRTC). XL1509-5.0 SO-8: 1 VIN, 2 OUTPUT, 3 FB (+5V), 4 ON/OFF (GND = on), 5–8 GND. XC6206 SOT-23:
1 VSS, 2 VOUT, 3 VIN. AO4485 SO-8: 1–3 S, 4 G, 5–8 D. BAT54S SOT-23: 1 A1, 2 K2, 3 K1/A2. BAT54W SOD-123: 1 K, 2 A.

## 7. Clock and synchronization
None on the board (RTC crystal 32.768 kHz only).

## 8. MCU pin allocation
On the display module: CYD CN1 GPIO21 SDA / GPIO22 SCL; JC3248W535 P4 IO17 SDA / IO18 SCL; JC4880P443C I²C GPIO7 / 8
(shared with its touch controller). No other signal between the board and the module.

## 9. Analog front-ends
Loop: ADS1115 ±4.096 V, 128 SPS, 1.04 µA per count, readable to ~27.5 mA; input filter 15.9 kHz. NTC: ratiometric,
10 kΩ divider, 17.5 Hz filter. Source: `calc/checkone_budget.py`.

## 10. Power
Budget and fault current: `calc/checkone_budget.py` (8 × 75 mA assumed + display ≈ 0.70 A of the 2 A supply; O7).
Supply limited to 25.2 V (D5). Behaviour under a channel short or +24 V on Iin with a 2 A supply: DS 9 reservations.

## 11. Peripherals
RTC + CR2032; four green LEDs (24V, 5V, 3V3, 3V3D); bottom test pads 24V, 5V, 3V3, 3V3A, SDA, SCL, 2 × GND.

## 12. Critical nets for automated verification
Not yet written (`calc/netlist_rules.py`). To add before routing:
1. Each CHn: Iin reaches its ADS1115 input only through R1n1 4.7 kΩ; R1n0 120 Ω, D1n and D2n on the right nets.
2. ADS1115 / INA226 / PCF8563 addresses as section 5 / 6; no address used twice.
3. The display 3.3 V pins (J5, J6) drive nothing but the 3V3D LED.
4. No part between OUTn of two channels; each channel has its own PTC.
5. Every 3V3A load (ADS1115s, NTC dividers, INA226 per O1 / C-6) after R9.

## 13. Conventions
GapOne V2 form (schgen): A4 sheets, section title boxes, SHEET PORTS block for inter-sheet nets, calc notes citing the
datasheet and `calc/`. Rails: `GND`, `+5V`, `+3.3V` (KiCad power), `+3.3VA`, `+24V_SENS`, `+5V_DISP`, `V24_F`
(project power symbols). Nets: `VIN_RAW`, `VIN_F`, `VIN_S`, `SS_GATE`, `SS_CGD`, `V24_D`, `BUCK_SW`, `5V_D`, `DISP_3V3`,
`CHn_OUT`, `CHn_IIN`, `CHn_AIN`, `NTCn`, `NTCn_ADC`, `OSCI`, `VRTC`, `VBAT`, `SDA`, `SCL`. References as v1 (by channel:
`F1n`, `FB1n`, `C1n0`, `J1n`, `R1n0`, `D1n`, `R1n1`, `D2n`, `C1n1`). Value = part number (passives: value); fields
Footprint, Datasheet, Description, LCSC on every assembled part.

## 14. Execution order
Done: 0 setup, rev 1.1 in every title block (O8); 1 datasheets (O3) and the symbol / footprint check; 2 circuit fixes
(O1 / O4); schematic redrawn (GapOne style), board synced. Next: 3 netlist rules (section 12) and the layout points of
v1's readme (Kelvin on R7 / R13, TVS D1 at the jack, buck loop U1-D3-L2-C12, 100 nF at the terminals, 1 uF at the NTC
connectors); 4 routing (kicad-routing); F deliverables in `DOC/` (BOM workbook, technical documentation) and the
JLCPCB package (`hw_release.py`).
## 15. Bench validation
DS 9 cases on the first boards (power-up, plug-in spark, surge, sensor hot-plug, channel short, +24 V on Iin with a
2 A supply, reversed loop and supply, supply removed), the 3V3A voltage during the +24 V on Iin fault (O4), calibration
of all channels with a 0.05 % calibrator, sensors' start-up current vs the PTCs (O5), CYD supply voltage (C-5).

## Appendix — Critical IC pinouts
Pin tables: `docs/datasheets/<part>_pins.csv` (12 parts, with the datasheet section); section 6 lists their use.
