# 1. Purpose and scope

This document describes the CheckOne main board, revision 1.1, for firmware development, assembly and bench test.
CheckOne is AQTech's production test fixture for GapOne and FluxOne sensors.

| Item | Source |
|---|---|
| Pinouts, connector tables, test points and part lists | generated from the KiCad netlist `hardware/CheckOne/CheckOne.net` (`netlist_tables.py`) |
| Numbers (measurement range, filters, NTC curve, fault currents, power budget) | `calc/checkone_budget.py` |
| Bill of materials and cost | `DOC/CheckOne_BOM.xlsx` (catalog data in `bom/parts.csv`) |
| Design decisions and open items | `CLAUDE.md` (design contract) and `docs/requirements/CheckOne_requirements.md` |

Where this text and the schematic or the scripts disagree, the schematic and the scripts prevail.

Conventions: CHn is a measurement channel (n = 1–8, terminal J1n). Part references follow the channel: F1n, FB1n,
C1n0, R1n0, D1n, R1n1, D2n, C1n1. DNP means "do not populate". Net names are those of the schematic (`CHn_AIN`,
`+3.3VA`, `V24_F`).

# 2. General description

## 2.1 Function

The board powers up to eight sensors with 24 V and measures their isolated 4–20 mA loops on 120 Ω 0.1 % shunts with
two ADS1115 converters. A third ADS1115 reads two NTC temperatures. An INA226 measures the sensor supply bus, and a
PCF8563 with a CR2032 keeps the time. The processor is not on the board: it is the ESP32 of the display module
(CYD ESP32-3248S035R inside the enclosure, or a Guition JC3248W535 / external JC4880P443C). The module reads every
device over one I²C bus and shows the readings on its screen and on a web page.

## 2.2 Blocks

| Block | Implementation | Schematic sheet |
|---|---|---|
| 24 V input | DC jack, PTC 1.6 A, SMBJ24A, SS34 reverse protection, AO4485 soft start, π filter 68 µH | Power_Input |
| Rails | XL1509-5.0 buck (5 V, 2 A), XC6206 LDO (3.3 V), 3V3A RC (10 Ω / 1 µF), display 5 V path, INA226, LEDs, I²C pull-ups, test pads | Power_Rails |
| Loop channels | 8 × (PTC 200 mA, bead, 100 nF, terminal, 120 Ω shunt, SMAJ5.0A, 4.7 kΩ, BAT54S, 10 nF) | Channels_1_4, Channels_5_8 |
| Converters | 3 × ADS1115 (CH1–4, CH5–8, NTC), NTC dividers and input filters | ADC_NTC |
| Display and clock | display connectors J4–J7, PCF8563 + crystal + CR2032, mounting holes | Display_RTC |

## 2.3 Key specifications

| Item | Value |
|---|---|
| Supply | 24 V DC ±5 % (25.2 V max), ≥ 2 A, 5.5 × 2.1 mm plug, centre positive |
| Channels | 8, 24 V always on, PTC 200 mA each |
| Loop measurement | 0.48–2.52 V on 120 Ω for 4–21 mA; 1.04 µA per count; readable to ~27.5 mA |
| Temperature | 2 × NTC 100 kΩ B3950, ratiometric, probe up to 150 °C |
| Supply monitor | INA226 on the sensor bus, 50 mΩ shunt (2 × 100 mΩ) |
| Clock | PCF8563, 32.768 kHz, CR2032 backup |
| Bus | I²C 400 kHz, 4.7 kΩ pull-ups, polled (no interrupt lines) |
| Board | 122 × 87 mm, 2 layers, 1 oz, holes M3 on 115 × 80 mm; enclosure AK-P-08A |

# 3. Power

## 3.1 Input and protection

The 24 V input (J1) passes the input PTC F1 (1.6 A, 1812), the TVS D1 (SMBJ24A, conducts from 26.7 V) and the
reverse-polarity diode D2 (SS34). The P-MOSFET Q1 (AO4485) soft-starts the bus: R2 / R3 set the gate, C2 (220 µF
gate–source) and R4 with C3 / C4 (gate–drain) slow the turn-on so the plug-in does not spark. The π filter
(C5 220 µF, C6 1 µF, L1 68 µH, C7 220 µF, C8 1 µF, C9 100 nF) gives the filtered bus V24_F. LED1 shows the 24 V input.

The supply must stay at or below 25.2 V: above it the TVS starts to conduct.

## 3.2 Rails

| Rail | Voltage | Source | Main loads |
|---|---|---|---|
| V24_F | 24 V | π filter output | buck U1, sensor bus shunt |
| +24V_SENS | 24 V | V24_F through R7 ∥ R13 (50 mΩ) | 8 channel PTCs F11–F18 |
| +5V | 5.0 V | U1 XL1509-5.0 (2 A, 150 kHz) | LDO U3, display path, LED2 |
| +5V_DISP | ~5 V | +5V through R6 (0 Ω, fitted) or D4 (SS34, DNP), then FB1 ∥ FB2 | display module (J4, J7) |
| +3.3V | 3.3 V | U3 XC6206P332 (200 mA) | INA226, PCF8563 (through D50), I²C pull-ups, LED3 |
| +3.3VA | 3.3 V | +3.3V through R9 (10 Ω) and C17 (1 µF) | the three ADS1115s, NTC dividers, BAT54S clamps |
| DISP_3V3 | 3.3 V | the display module's own regulator | LED4 only (shows that the module is powered) |

The measurement does not depend on the display's regulator: the converters run from +3.3VA. With the CYD module the
0 Ω R6 must be fitted (rev 1.1: R6 fitted, D4 DNP), because the CYD regulator needs about 4.4 V.

## 3.3 Sensor bus monitoring

The INA226 (U2) measures the current of the eight channels only, on the 50 mΩ shunt between V24_F and +24V_SENS,
with Kelvin sense lines to R7. VBUS (pin 8) reads +24V_SENS. Full-scale shunt voltage 81.92 mV gives 1.64 A at
50 mΩ, above the 1.6 A input PTC.

## 3.4 Power budget

{{include generated/budget.md}}

# 4. Processor and display modules

There is no processor on the board. The display module is the I²C master; only one module is connected at a time,
because each one is a master on the same bus.

| Module | Connector on the board | I²C pins on the module | Notes |
|---|---|---|---|
| CYD ESP32-3248S035R | J5 (I²C) + J4 (5 V) | CN1 GPIO21 SDA, GPIO22 SCL | inside the enclosure, on spacers H5–H8 |
| Guition JC3248W535 | J6 (I²C) + J4 (5 V) | P4 IO17 SDA, IO18 SCL | inside the enclosure |
| Guition JC4880P443C (4.3") | J7 (5 V, GND, SDA, SCL) | GPIO7 SDA, GPIO8 SCL (shared with its touch controller) | outside the enclosure, 4-wire cable |

J4 pins 2 and 3 (TX, RX) are not connected. The 3.3 V pins of J5 and J6 come from the module and only drive LED4.

# 5. Acquisition

## 5.1 Converters

| Device | Address (ADDR pin) | Inputs | Supply |
|---|---|---|---|
| U4 ADS1115 | 0x48 (ADDR = GND) | AIN0–AIN3 = CH1–CH4 | +3.3VA |
| U5 ADS1115 | 0x49 (ADDR = VDD) | AIN0–AIN3 = CH5–CH8 | +3.3VA |
| U6 ADS1115 | 0x4A (ADDR = SDA) | AIN0 = NTC1, AIN1 = +3.3VA (reference), AIN2 = NTC2, AIN3 = GND | +3.3VA |

ALERT/RDY is not connected on any ADS1115: the firmware polls the conversion-ready bit.

U4 pin map:

{{include generated/pins_U4.md}}

U5 pin map:

{{include generated/pins_U5.md}}

U6 pin map:

{{include generated/pins_U6.md}}

## 5.2 Suggested configuration

Single-shot conversions, one input at a time, ±4.096 V range, 128 SPS, comparator disabled (ADS1115 datasheet
SBAS444E, Config register field descriptions):

| Input | Config register |
|---|---|
| AIN0 single-ended | 0xC383 |
| AIN1 single-ended | 0xD383 |
| AIN2 single-ended | 0xE383 |
| AIN3 single-ended | 0xF383 |

At 128 SPS one conversion takes 7.8 ms; a full scan of four inputs on U4 and U5 in parallel takes about 32 ms.

## 5.3 Loop current

The loop current flows from the sensor into Iin (terminal pin 3), through R1n0 (120 Ω 0.1 % 25 ppm) to GND, and back
to the sensor through Iout (pin 4 = GND). The ADC reads the shunt voltage through R1n1 (4.7 kΩ) and C1n1 (10 nF).

| Quantity | Value |
|---|---|
| Code to current | I = code × 4.096 V / 32768 / 120 Ω = code × 1.0417 µA |
| Range used | 0.432 V at 3.6 mA to 2.64 V at 22 mA; readable to ~27.5 mA (input limited by VDD) |
| Input filter | 4.7 kΩ / 10 nF, 3.4 kHz |
| Gain error from the 4.7 kΩ and the ADS1115 input impedance | 0.11 %, removed by the per-channel gain calibration |
| Calibration | I = (reading − offset) × gain per channel; offset with no sensor, gain at 20.00 mA |

{{include generated/loop_table.md}}

## 5.4 Conversion to the sensor quantity

| Sensor | Conversion (I in mA, linear over 4–20 mA) |
|---|---|
| GapOne-15 | d = 3 + (I − 4) × 12 / 16 mm (3–15 mm) |
| GapOne-25 | d = 5 + (I − 4) × 20 / 16 mm (5–25 mm) |
| GapOne-50 | d = 10 + (I − 4) × 40 / 16 mm (10–50 mm) |
| FluxOne | B = (I − 12) × 250 mT (±2000 mT) |
| Raw | I in mA |

Loop condition (NAMUR NE43): below 3.6 mA open loop; above 21 mA short circuit; 3.6–4 mA and 20–21 mA out of range.
In raw mode only > 21 mA is flagged. A negative reading means a reversed loop.

# 6. Analog front-ends

## 6.1 Loop input (each channel)

| Part | Function |
|---|---|
| F1n (PTC 200 mA) and FB1n (bead) | channel supply from +24V_SENS to terminal pin 1, net CHn_PTC between them |
| C1n0 (100 nF) | decoupling at the terminal |
| D1n (SMAJ5.0A) | clamps Iin to GND (reversed loop: Iin near −0.7 V) |
| R1n0 (120 Ω 0.1 %) | loop shunt |
| R1n1 (4.7 kΩ), D2n (BAT54S), C1n1 (10 nF) | series resistor, clamp to +3.3VA / GND, filter at the ADC pin |

With +24 V wired to Iin by mistake, the SMAJ5.0A clamps Iin and R1n1 limits the current pushed into +3.3VA through
the BAT54S to 0.6–0.8 mA per channel, which the rail load absorbs (calc item 3).

## 6.2 NTC inputs

Each NTC forms a divider with a 10 kΩ resistor from +3.3VA (R400, R410), with 1 µF across the NTC at the connector
(C403, C413) and the same series resistor / clamp / 10 nF as the loops (R401 / R411, D40 / D41, C404 / C414). U6 AIN1
reads +3.3VA itself, so the ratio AIN0 / AIN1 (or AIN2 / AIN1) is independent of the supply:

R_NTC = 10 kΩ × r / (1 − r), with r = V_NTC / V_3V3A.

{{include generated/ntc_table.md}}

NTC1 is the front probe (up to 150 °C), NTC2 the internal sensor. Use the Beta equation (B3950), or Steinhart–Hart
with a 2–3 point calibration for the 140 °C probes.

# 7. I²C bus

One bus, 400 kHz, pull-ups R11 / R12 (4.7 kΩ to +3.3V), test pads TP5 (SDA) and TP6 (SCL).

| Address | Device |
|---|---|
| 0x40 | U2 INA226 (A0 = A1 = GND) |
| 0x48 | U4 ADS1115, CH1–CH4 |
| 0x49 | U5 ADS1115, CH5–CH8 |
| 0x4A | U6 ADS1115, NTC |
| 0x51 | U7 PCF8563 |

No address conflicts with the 4.3" module's own devices (GT911 0x5D / 0x14, codec 0x18).

{{include generated/i2c_nets.md}}

INA226 suggested setup (INA226 datasheet, calibration register): Current_LSB = 100 µA, R_SHUNT = 0.05 Ω,
CAL = 0.00512 / (Current_LSB × R_SHUNT) = 1024 (0x0400). Bus voltage LSB 1.25 mV.

# 8. Communication

The board has no communication interface of its own: Wi-Fi and the web page are on the display module.

# 9. Peripherals

| Peripheral | Details |
|---|---|
| RTC | U7 PCF8563 at 0x51, crystal Y1 32.768 kHz with C50 (22 pF); VRTC from +3.3V through D50 or from the CR2032 (BT1) through D51 (BAT54W); INT and CLKOUT not connected. Check the VL bit of the seconds register at start-up (clock integrity lost) |
| LEDs | LED1 24 V input (R1), LED2 +5V (R5), LED3 +3.3V (R8), LED4 display 3.3 V (R10); green, labelled 24V / 5V / 3V3 / 3V3D |
| Battery | CR2032 in BT1 (BS-02-A1AJ006); the coin slides in from the side away from the + tower |

# 10. Connectors

{{include generated/connectors.md}}

Channel terminals J11–J18 (KF2EDGRC-5.08-4P, plug KF2EDGK-5.08-4P): pin 1 +24 V, pin 2 GND, pin 3 Iin, pin 4 Iout
(GND); CH1–CH4 on one long side, CH5–CH8 on the other. J2 is the front NTC probe (NTC1), J3 the internal one (NTC2).

# 11. Recommended initialization sequence

1. Wait until the sensor bus is above 20 V (INA226 bus voltage) and ignore channel readings for 2–3 s after power-up.
2. Start I²C at 400 kHz; recover the bus (nine SCL clocks) if SDA is held low.
3. Probe 0x40, 0x48, 0x49, 0x4A and 0x51; report any missing device.
4. INA226: write the calibration register (0x0400) and the configuration (averaging as needed).
5. ADS1115s: single-shot conversions with the configuration of section 5.2; poll the OS bit for completion.
6. PCF8563: read the time; if the VL bit is set, mark the time invalid until NTP or the web page sets it.
7. Load the per-channel offset / gain and the sensor type of each channel from NVS; start the 5 s logging cycle.

# 12. Test points and bench tests

Test pads on the bottom side, Ø2.0 mm:

{{include generated/testpoints.md}}

Bench tests on the first boards (`CLAUDE.md` section 15): power-up and plug-in spark, surge, sensor hot-plug,
channel short, +24 V on Iin with a 2 A supply (watch +3.3VA), reversed loop and supply, supply removed, calibration
of every channel with a 0.05 % calibrator, sensor start-up current against the 200 mA PTCs, CYD supply voltage.

# 13. Open items and firmware checks

| Item | Status |
|---|---|
| Description conflicts C-1…C-4, C-8, C-13, C-14 | open (`CLAUDE.md` O1) |
| CYD size and holes, enclosure walls vs the terminals, sensor start-up current, CYD display controller, JC4880P443C pinout, SMAJ5.0A leakage at 2.5 V | to confirm on real parts (O5) |
| ngspice files of the description | missing (O6) |
| GapOne / FluxOne supply current | missing; the budget assumes 75 mA per sensor (O7) |
| Enclosure fit | confirm against the AK-P-08A drawing (O9) |
| Board routing | routed and DRC clean; audit geometry findings open (`reports/CheckOne/routing_handoff_2026-11-16.md`) |
| Firmware | ALERT pins not used (polling); RTC VL bit; reversed-loop message; ignore readings below 20 V bus |

# 14. Project documents

| File | Content |
|---|---|
| `CLAUDE.md` | design contract: decisions, open items, conventions |
| `docs/requirements/` | equipment description (source of truth), consolidated requirements, meeting notes |
| `docs/datasheets/` | 27 datasheets with `manifest.csv` and pin tables |
| `hardware/CheckOne/` | KiCad 10 project: schematic (root + 6 A4 sheets), board, libraries, 3D models |
| `hardware/*.py` | schematic generator, symbol library builder, board sync |
| `calc/checkone_budget.py` | measurement, NTC, fault current and power budget |
| `bom/` | catalog data (`parts.csv`), JLCPCB class summary, BOM summary |
| `DOC/CheckOne_BOM.xlsx` | BOM with cost per board and per batch |
| `reports/CheckOne/` | review of v1, routing hand-off |

# Annex A — BOM summary

{{include ../../bom/bom_summary.md}}

Active parts:

{{include generated/active_parts.md}}
