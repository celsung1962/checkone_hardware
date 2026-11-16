# Decision rules

_When to do what. The rulebook says how the golden board looks; this file says how to choose. Every number is measured from the geometry reference board unless marked "engineering guidance"._

> **Revised 2026-09-16 (rev B).** Where this file conflicts with `07_review_decisions.md`, the review decision wins.

## D1. Which nets are differential pairs

| Interface | Net naming in golden | Treatment |
|---|---|---|
| PHY SerDes / SGMII to SFP (PHYn_TXP/TXN, PHYn_RXP/RXN) | `_P`-less suffix `P`/`N` | **Diff pair.** 0.2 mm / 0.25 mm gap, intra-pair mismatch **0.00 mm** in golden (all 8 pairs). Target ≤ 0.1 mm. |
| SFP module lanes (SFPn_TDP/TDN, SFPn_RDP/RDN) | suffix `P`/`N` | **Diff pair.** Same rules. TD pairs 0.00 mm mismatch; RD pairs 1.2–1.5 mm (ends at cage pads). Target ≤ 1.5 mm. |
| ADC differential inputs (AD_VxIN_P/_N) | `_P`/`_N` | **Coupled routing, no length matching.** Low-bandwidth analog: golden mismatch up to 4.4 mm. Keep the pair side-by-side at 0.45 mm centre spacing for common-mode rejection; do not add meanders. |
| RGMII data/clock (ETHn_TXD0–3, TX_EN, TX_CLK, RXD0–3, RX_DV, RX_CLK) | single-ended | **Single-ended bus group** (see D4). Never pair them. |
| ETHn_CLK_IN, PPS, MDIO/MDC, I2C, SPI, GPIO, resets, SD/eMMC | single-ended | Single-ended, 0.2 mm. |

- Always name new pairs `<base>_P` / `<base>_N`; KiCad's pair router and the audit both key on the suffix.
- Never route one leg of a pair on F.Cu and the other on B.Cu. Golden pairs are 72 % F.Cu, 28 % B.Cu, always both legs together.
- Split the pair only for the last straight segment into each pad.

## D2. Track width by current and function → choose the netclass

> Rev B (Q-04): the width is a property of the netclass. Use this table to decide which class a net belongs to, or what width a new class gets. Never set a width on a segment.

Golden mapping by function (measured):

| Function | Width |
|---|---|
| All logic, analog, clocks, diff pairs | 0.2 |
| BGA escape (within the 0.5 mm-pitch field) | 0.1; power stubs 0.127 / 0.15 |
| ±15 V analog rails, op-amp supply, regulator FB/OUT nodes | 0.5 |
| +5.0 V secondary branches, diode/inductor nodes | 0.6 |
| LED/photodiode drive, +5V_POF1–3, EARTH, regulator VIN | 0.8 |
| +5.0 V trunk, +12VA branches | 1.0 |
| Relay contact nets (SD_x_NO / NC / CM) | 1.5 |
| +12VA main feed, power-connector entry (CN1) | 2.0 |

Engineering guidance (IPC-2221 external layer, 35 µm copper, 10 °C rise, approximate):

| Width (mm) | ≈ Continuous current (A) |
|---|---|
| 0.2 | 0.7 |
| 0.5 | 1.4 |
| 0.6 | 1.6 |
| 0.8 | 2.0 |
| 1.0 | 2.4 |
| 1.5 | 3.2 |
| 2.0 | 3.9 |

- Pick the class whose width rating is ≥ 1.5 × the expected continuous current (POWER_DC = 0.6 mm ≈ 1.6 A). Above that, create a class at 0.8 / 1.0 / 1.5 / 2.0 mm or drop into an In2.Cu plane; never invent an intermediate width.
- Above 2 A, prefer dropping the current into an In2.Cu power plane through 2–4 vias over widening a top-layer track further.
- Change width only at a pad, via or corner. Where a wide feed meets a small pad (e.g. 0.8 mm run into an 0603), step down once at the last corner, ≥ 1 mm before the pad.

## D3. Layer and via policy

Measured: 76 % of segments (57 % of signal length) on F.Cu, 24 % (43 %) on B.Cu. F.Cu leans vertical (39 % of length at 90° vs 32 % at 0°); B.Cu leans horizontal (35 % vs 32 %). The bias is mild: the board is not strictly H/V layered.

Via budget per **signal** net (314 signal nets):

| Vias | Nets | Share |
|---|---|---|
| 0 | 162 | 52 % |
| 1 | 23 | 7 % |
| 2 | 91 | 29 % |
| 3 | 12 | 4 % |
| ≥ 4 | 26 | 8 % (only I2C, PPS, resets, MDIO, SFP I2C, ADC monitor lines) |

- Route on F.Cu first; components are all top-side, so a via is never needed to reach a pad.
- Drop to B.Cu only to cross another F.Cu track. Return with a second via (the 0-or-2 pattern covers 81 % of signal nets). Never leave a fast signal with 1 via unless its destination pad is through-hole.
- Via caps are a **per-project parameter** (`via_budget`, Q-09). The reference histogram suggests 2 for fast nets and 3 for GPIO; write the numbers for each bus into `kicad_golden.project.json` rather than assuming them.
- Every GND and power pad gets its own via straight into the plane, adjacent to the pad, with the track on one layer only (1059 vias in golden have tracks on a single layer). Do not daisy-chain GND pads on the surface.
- Use `(free yes)` stitching vias for outer-layer power pours (golden: 25 on +5.0V / +3.3V) and plane-to-plane stitching (49 track-less vias). Keep stitching pitch ≥ 0.5 mm between centres.
- Never route a signal on In1.Cu or In2.Cu.

## D4. Length matching targets

> Rev B (Q-07, Q-08): matching targets are decided **per bus, per project** and written into `kicad_golden.project.json` (`length_groups`). The values below are the reference board measurements, offered as starting points only.

Measured group spreads on the golden board (max − min routed length, mm):

| Group | Members | Spread | Rule |
|---|---|---|---|
| SD/eMMC (BRX_SD_CLK, CMD, DAT0–3) | 6 | 2.67 (CLK 19.7 shortest; DAT ≈ 22.4) | Keep CMD/DAT0–3 within **3 mm** of each other; CLK shorter than or equal to the data lines. Meanders on DAT0–3 are how the golden board achieved this. |
| RGMII TX (TXD0–3, TX_EN, TX_CLK) per PHY | 6 | 7.1–7.8 | Keep within **10 mm** (≈ 60 ps). Tune TX_CLK with a meander if it lands outside the group. |
| RGMII RX (RXD0–3, RX_DV, RX_CLK) per PHY | 6 | 6.9–10.8 | Same 10 mm target; RX_CLK on ETH4 was meander-tuned in golden. |
| SerDes pairs P vs N | 2 | 0.00 | ≤ 0.1 mm intra-pair. |
| SFP RD pairs P vs N | 2 | 1.2–1.5 | ≤ 1.5 mm (cage pad geometry limits this). |
| ADC input pairs | 2 | up to 4.4 | No requirement. |
| I2C SCL/SDA | 2 | 9.9 (330 mm long) | No requirement. |

- Use the KiCad tuning tool with the template defaults (**chamfered corners**, amplitude 0.2–1.0 mm, spacing 0.6 mm). Boards must carry zero arcs (Q-03); the audit fails on any arc.
- Add length on the shortest member, never remove it from the longest by re-routing a clean path.

## D5. Zone priority ordering

Measured priority map (higher number wins where zones overlap):

| Layer | Zone | Priority |
|---|---|---|
| In1.Cu | GND plane (whole board) | 1 |
| In1.Cu | EARTH2 islands (isolated I/O areas) | 5, 13 |
| In2.Cu | +12VA base pour | 0 |
| In2.Cu | +3.3V main plane / +5VA / +3.3V second area | 1 / 2 / 3 |
| In2.Cu | +5.0V areas | 4, 8 |
| In2.Cu | +24V areas | 6, 7 |
| In2.Cu | +5V_SLED | 9 |
| In2.Cu | +3.3V island | 10 |
| In2.Cu | Local LC-node islands `Net-(Cxx-Padn)` | 11, 12 |
| B.Cu | −12VA base pour / +5.0V pours | 0 / 14, 15 |
| F.Cu | +5VA / +5.0V pours | 16 / 17 |

- Give the layer's largest plane the **lowest** priority on that layer; every island cut into it gets a strictly higher number; the smallest local islands (regulator output nodes) get the highest.
- Never let two overlapping zones of different nets share a priority (the audit warns on this).
- Same-net zones may share a priority (golden: five EARTH2 islands at 5).
- Outer-layer pours (F.Cu/B.Cu) use `min_thickness 0.25`; inner planes 0.1; small LC-node islands 0.05 with clearance 0.05.

## D6. Order of work for a new board

1. Clone settings (`apply_settings.js`), copy `templates/kicad_golden.project.json` next to the board and fill it in, set the 4-layer stackup, draw Edge.Cuts as one closed shape, set grid origin.
1b. Define the netclasses and name patterns for every bus and rail (D1, D2) before the first track.
2. Place all components on F.Cu; lock connectors and mechanicals.
3. Zones first: In1.Cu GND plane at priority 1, In2.Cu power planes per D5. Fill.
4. Fan out every GND/power pad with a via into its plane (D3).
5. Route diff pairs (D1), then length-critical groups (D4), then everything else at 0.2 mm on the 45° lattice.
6. Power routing on F.Cu/B.Cu at the D2 widths; pours only where a node needs current the plane cannot supply.
7. Hide references, add functional silkscreen labels only, place fiducials and logos.
8. Run `kicad_audit.js`; clear all FAIL, justify every remaining WARN; then KiCad DRC/ERC with the golden severities.
