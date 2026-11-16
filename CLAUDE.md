# CheckOne — Hardware brief for Claude Code (KiCad)

AQTech Power Prognostics · Hardware owner: Celso Souza · v1 schematic and placement: Sergio Zimath ·
Brief revision: 2026-11-16 (rev. 1 — written from the equipment description and the v1 KiCad project)

This file is the hardware contract. [FROZEN] items are locked; [PROPOSED] items are calculated starting points that
may be refined with justification; [OPEN] items must not be closed by the agent.

The v1 board exists as a schematic and a placement (not routed, not fabricated). This brief takes v1 and the
equipment description as the baseline. The decisions in section 2 come from the description; they are [FROZEN]
once the owner confirms them (O1). Work on v1 goes on as revision 1.1 (principle 8 of the kicad-schematic skill).

## 0. Working rules
1. Language: everything in English — reports, commits, `calc/` scripts and all new schematic content. Chat replies
   follow the user's language. The v1 sheets are in Portuguese (C-11 of the requirements): translate at rev 1.1.
2. Conclusion first, then the justification.
3. Every number backed by a script in `calc/` (`calc/checkone_budget.py`: measurement, NTC, fault current, budget).
4. Pinouts only from datasheets in `docs/datasheets/` (listed in `manifest.csv`). No symbol is drawn or changed
   without its datasheet on disk (none on disk yet: O3).
5. No silent workarounds: infeasibility → stop and report with evidence and alternatives.
6. `kicad-cli sch erc` after every sheet and before every commit; `python tools/hw_checks/hw_checks.py` before every
   commit (ERC / DRC against `tools/hw_checks/baseline/`, datasheet manifest).
7. Form follows the v1 project and the AQTech repositories (GapOne_V2); engineering follows this brief.
8. Source documents: `docs/requirements/` — start with `CheckOne_requirements.md` (English, consolidated, with the
   conflicts C-1…C-14 and gaps G-1…G-8); the Portuguese description is the source of truth for the product.
   `meeting_2026-11-16_Sergio.md` holds Sergio's requests: review the electronics, route, check the fit in the
   enclosure, order with the AMP. He allows any change but wants the important ones reported to him before the
   version is closed: list every such change in the rev 1.1 report.
9. **v1 is generated.** `hardware/CheckOne/gerador/design.py` is the single circuit definition; `gen_sch.py` and
   `gen_pcb.py` write the schematic and the board from it. Until the owner decides otherwise (O2), a circuit change
   goes into `design.py` and both files are regenerated; never hand-edit one side only.

## 0.1 Reference [FROZEN]
- v1 KiCad project (KiCad 7 files, opened with KiCad 10): `hardware/CheckOne/`, copied unchanged from the hand-over
  `reference/import_2026-11-16/` (outside git, `OUTSIDE_GIT.md`) without `producao/` and `.kicad_prl`.
- Form of the repository, checks, release and documentation: GapOne_V2 (`aqtechengenharia/gapone_hardware`).

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
- **O1 — Confirm the description as the contract.** Owner to confirm section 2 and decide the conflicts C-1…C-12 of
  `docs/requirements/CheckOne_requirements.md` (the ones that change the board: C-5 display 5 V path, C-6 INA226
  supply, C-7 test pads, C-9 / C-10 placement, C-12 fault current into 3V3A, C-14 board size).
- **O2 — How v1 is edited.** Keep the generator (`gerador/design.py` → schematic and board) or convert the project to
  KiCad 10 and edit it directly (the AQTech form). The generator writes KiCad 7 files with Portuguese names, bare
  footprint names on the board and no LCSC field on the footprints (G-5). Until decided: generator only (rule 9).
- **O3 — Datasheets.** None on disk. Fetch the datasheets of every part of DS 8 into `docs/datasheets/`
  (`fetch_datasheets.py`), then check every v1 symbol and footprint against them (V1R item 8: BAT54W package,
  FCH1040 pads, MX1.25 connector; ADS1115 / INA226 footprint name). `hw_checks.json` accepts the missing datasheets as
  a known failure until then.
- **O4 — Fault current into 3V3A (C-12).** +24 V on Iin pushes 2.8–3.8 mA per channel into 3V3A through the BAT54S;
  the XC6206 cannot sink it. Options: a clamp to the 3V3A rail that can sink (zener / shunt load), BAT54S to a
  dedicated clamp rail, a larger series resistor, the SMBJ5.0A of DS 9. Needs the rail load (calc 3 assumes 3 mA).
- **O5 — Items to confirm on real parts (DS 11):** CYD size and holes (C-8), enclosure window walls and ribs vs the
  12.5 mm terminal bodies, sensors' start-up current vs the 200 mA PTCs, CYD display controller, JC4880P443C 26-pin
  pinout, SMAJ5.0A leakage at 2.5 V, AQTech logo SVG.
- **O6 — Simulation files (G-1).** The ngspice netlists and results of DS 9 are not in the hand-over.
- **O7 — Sensor consumption (G-3).** GapOne / FluxOne current per sensor, for the budget and the PTC choice.
- **O9 — Fit in the enclosure (C-14, G-8).** The v1 outline is 122.1 × 87.1 mm with holes on 115.00 × 80.00 mm, as
  the description says; whether that already has Sergio's 1 mm per side of clearance needs the AK-P-08A drawing or
  his caliper measurements (inside length / width, hole positions of the lid screws, window positions).
- **O10 — Order with the AMP.** Sergio would like the board ordered with the GapOne AMP if the routing is done the
  same day. Not before O1 / O3 / O4 / O9 are closed and the routing audit passes; owner's call.
- **O8 — Revision and date.** v1 title blocks: rev 1.0, no date, A2 sheets. Next: 1.1 with the date of the first
  change on every sheet and the board (principle 8).

## 4. KiCad project structure
`hardware/CheckOne/`: root `CheckOne.kicad_sch` with four hierarchical sheets — `alimentacao` (input, soft start,
filter, buck, INA226, 3.3 V, LEDs, test pads), `canais` (CH1–CH8), `adcs` (3 × ADS1115, NTC1 / NTC2), `display_rtc`
(display connectors, RTC, battery, holes); nets by global labels. Board `CheckOne.kicad_pcb`: 122 × 87 mm, 2 layers,
all parts placed, no tracks. Project library `CheckOne` (`CheckOne.kicad_sym`: AO4485, XL1509; `CheckOne.pretty`:
KF2EDGRC-5.08-4P, DC-005-A200, BS-02-A1AJ006). `CheckOne.net`: netlist exported with KiCad 10 (166 parts).

## 4.1 Parts policy [FROZEN]
SMD parts assembled by JLCPCB with the LCSC code in the `LCSC` field; THT parts and loose items bought from LCSC
and hand-soldered (DS 8). For new parts copy `.claude/skills/kicad-schematic/references/jlcpcb_policy.md` here.

## 5. Channel / signal map [FROZEN after O1]
| Signal | Path | Level | Terminal |
|---|---|---|---|
| CHn +24 | +24V_SENS → F1n (200 mA) → FB1n → OUTn, C1n0 100 nF | 24 V | Jn pin 1 |
| CHn loop | IINn → R1n0 120 Ω → GND; D1n SMAJ5.0A; R1n1 1 kΩ → AINn, D2n BAT54S, C1n1 10 nF → U4 (n = 1–4) / U5 (n = 5–8) | 0.48–2.52 V for 4–21 mA | Jn pin 3 Iin, pin 4 Iout = GND, pin 2 GND |
| NTC1 / NTC2 | R4x0 10 kΩ from 3V3A, C4x3 1 µF, R4x1 1 kΩ, D4x BAT54S, C4x4 10 nF → U6 AIN0 / AIN2; U6 AIN1 = 3V3A | 0.55–3.27 V | J2 (front), J3 (inside) |
| Sensor supply | V24_F → R7 ∥ R13 (50 mΩ) → +24V_SENS, INA226 U2 | 24 V | — |

(Jn = J11…J18 for CH1…CH8.)

## 6. Critical IC connections (v1, to check against the datasheets — O3)
ADS1115 VSSOP-10: 1 ADDR (U4 GND → 0x48, U5 VDD → 0x49, U6 SDA → 0x4A), 2 ALERT/RDY (NC), 3 GND, 4–7 AIN0–3,
8 VDD (3V3A), 9 SDA, 10 SCL. INA226 VSSOP-10: 1 A1, 2 A0 (both GND → 0x40), 3 ALERT (NC), 4 SDA, 5 SCL, 6 VS (+3V3 in
v1, 3V3A in DS: C-6), 7 GND, 8 VBUS, 9 IN−, 10 IN+. PCF8563T SO-8: 1 OSCI, 2 OSCO, 3 INT, 4 VSS, 5 SDA, 6 SCL,
7 CLKOUT, 8 VDD (VRTC). XL1509-5.0 SO-8: 1 VIN, 2 OUTPUT, 3 FB (+5V), 4 ON/OFF (GND = on), 5–8 GND. XC6206 SOT-23:
1 VSS, 2 VOUT, 3 VIN. AO4485 SO-8: 1–3 S, 4 G, 5–8 D.

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
Not yet written (`calc/netlist_rules.py`). To add with rev 1.1:
1. Each CHn: Iin reaches its ADS1115 input only through R1n1 1 kΩ; R1n0 120 Ω, D1n and D2n on the right nets.
2. ADS1115 / INA226 / PCF8563 addresses as section 5 / 6; no address used twice.
3. The display 3.3 V pins (J5, J6) drive nothing but the 3V3D LED.
4. No part between OUTn of two channels; each channel has its own PTC.
5. Every 3V3A load (ADS1115s, NTC dividers, INA226 per O1 / C-6) after R9.

## 13. Conventions
v1 as seen: Portuguese sheet names (`alimentacao`, `canais`, `adcs`, `display_rtc`); nets `VIN_RAW`, `VIN_F`, `VIN_S`,
`V24_D`, `V24_F`, `+24V_SENS`, `+5V`, `+5V_DISP`, `+3V3`, `+3V3A`, `DISP_3V3`, `OUTn`, `IINn`, `AINn`, `NTCn`,
`NTCn_ADC`, `SDA`, `SCL`; references by channel (`F1n`, `R1n0`, `D1n` …); LCSC field on every assembled part.
To extract with `analyze_kicad_project.py` at rev 1.1, together with O2.

## 14. Execution order
0 owner decisions O1 / O2, rev 1.1 in every title block (O8); 1 datasheets (O3) and the symbol / footprint check;
2 circuit fixes decided in O1 / O4; 3 ERC / DRC / netlist rules (section 12) and the V1R layout points; 4 routing
(kicad-routing); F deliverables in `DOC/` (BOM workbook, technical documentation) and the JLCPCB package.

## 15. Bench validation
DS 9 cases on the first boards (power-up, plug-in spark, surge, sensor hot-plug, channel short, +24 V on Iin with a
2 A supply, reversed loop and supply, supply removed), the 3V3A voltage during the +24 V on Iin fault (O4), calibration
of all channels with a 0.05 % calibrator, sensors' start-up current vs the PTCs (O5), CYD supply voltage (C-5).

## Appendix — Critical IC pinouts
To fill from the datasheets (O3); section 6 lists the v1 pin use.
