# Appendix: minor details

_Facts recorded from the golden project that rarely change a routing decision. Moved out of the working references to keep them short. Consult only when a specific question arises._

## Local project state (`.kicad_prl`)

- `auto_track_width` true (router takes width from the netclass or the existing track).
- Selection filter defaults: `footprints` and `lockedItems` on; tracks, vias, pads, zones, text, graphics, dimensions, keepouts off.
- `net_color_mode` 1, `zone_display_mode` 0, ratsnest and DRC markers visible, `high_contrast_mode` 0.
- Schematic selection filter: everything on except locked items.

## Footprint text and graphics defaults observed

- Fab layer `${REFERENCE}` text: 0.4 × 0.4 mm, 0.06 mm stroke (KiCad library default) on 736 footprints; larger variants 0.5–1.27 mm on custom parts.
- Footprint graphics widths: F.CrtYd 0.05 (KiCad libs) / 0.1 (custom); F.Fab 0.1; F.SilkS 0.12 (KiCad libs) / 0.2 (the geometry reference board custom lib) / 0.15–0.1524 (imported parts).
- 10 footprints have no courtyard (logos, imported connectors); `missing_courtyard` is ignored in DRC for that reason.
- Footprint rotations used: 0 (308), −90 (267), 90 (234), 180 (223).

## Fine-pitch and special pads

- BGA: `Package_BGA:LFBGA-153_11.5x13mm_Layout14x14_P0.5mm` (U6), 153 circle pads 0.24 mm, `(property pad_prop_bga)`, escaped with 0.1 mm tracks and 0.45/0.2 dog-bone vias in the channels.
- Heatsink pads: U1-9, U3-9 carry `(property pad_prop_heatsink)` and `(zone_connect 2)`; IC3-9 is an exposed pad. All three hold same-net GND thermal vias (the only vias inside SMD pads on the board).
- Mounting holes MH1–MH8: `(zone_connect 2)` (solid) on each of their three pad entries.
- Pads with explicit `solder_mask_margin 0.25`: 4 (connector pads). Everything else uses the footprint/board default of 0.
- Pad shape census: roundrect 2335 (ratio 0.25: 2197), circle 535, rect 470, oval 35. `connect` type pads: 14 (SMD pads without mask opening on the CPU module footprint).
- Through-hole drill census: 0.8 (236), 1.05 (40), 0.95 (36), 1.2 (32), 1.0 (18), 0.84 (16), 0.66 (16), 1.3 (10), 0.85 (9), 1.4 (9), 0.7 (8), 3.2 (7, mounting holes), 1.46 (2). NPTH: 24.

## Groups

- 9 anonymous `(group …)` objects (5 × 2 members, 1 × 10, 2 × 22, 1 × 20). Used to move repeated front-end blocks as units. Names are empty.

## Symbol fields imported from vendor databases (hidden in the BOM preset)

`CURRENT RATING`, `DUTY CYCLE - MAX`, `FREQUENCY`, `FREQUENCY STABILITY`, `HEIGHT`, `HEIGHT (MAX)`, `LOAD CAPACITANCE`, `MAXIMUM/MINIMUM OPERATING TEMPERATURE`, `MINIMUM ORDER QUANTITY`, `OPERATING SUPPLY VOLTAGE`, `OUTPUT FORMAT`, `PRODUCT STATUS`, `PRODUCT TYPE`, `REELING`, `ROHS - MOUSER`, `SERIES`, `STANDARD PACK QTY`, `SUBCATEGORY`, `#PART NUMBER`, `CURRENT - TEST`, `DESIGNATOR`, `FEATURES`, `MILLICANDELA RATING`, `MANUFACTURER`, `MANUFACTURER PART NUMBER`, `Mouser Part Number`, `Mouser Price/Stock`, `PN DIGIKEY 1`, `PN MACNICA`, `PACKAGE`, `SIZE / DIMENSION`, `TECHNOLOGY`, `VALIDATED`, `BRAND`, `CATEGORY`, `Sim.*`. Tolerate them; never require them; never show them in the BOM.

## Library census

- Symbols: `Device` 974, `power` 629, `BASE_the reference board_V02-altium-import` 214, `the geometry reference board` 75, `Amplifier_Operational` 36, `database_local_mapped` 19, `LED` 19, `Mechanical` 19, `Diode` 14, `Connector_Generic` 9, `AQTECH` 6, `74xx` 5, `ROGOVSKI_V20` 4, `the reference board_ANALOG_DEVBOARD` 4.
- Footprints: `Resistor_SMD` 483, `Capacitor_SMD` 332, `the geometry reference board` 77, `Inductor_SMD` 25, `Vlad_2024` 19, `Package_SO` 18, `Package_TO_SOT_SMD` 17, `LED_SMD` 15, `MountingHole` 9, `Diode_SMD` 9, `Package_QFP` 6, `Varistor` 5, `Connector_Phoenix_MC` 4, `Fiducial` 4.
- Custom footprints in `the geometry reference board.pretty`: KH-IPEX-K501-29 (40 uses), Photodiode_36078, SOIC127P600X170-9N, U77A11133001, 16581971, AFBR2418Z, SWITCH_TS1187A, PinSocket 2x35/2x17 P2.00, Relay_RZ01-1C3-D005, OSC_SIT5155, Logo_PowerOpticks_the reference board, FTW0H104ZF, SOIC127P600X175-8N, HEADER_1X10_90_1.00.

## Sheet inventory (golden)

| Sheet | Paper | Symbols | no_connect | Hier. labels |
|---|---|---|---|---|
| Root | A1 | 0 | 0 | 0 (18 sheet symbols) |
| BORAX (CPU module) | A3 | 23 | 47 | 149 |
| Fiber_ETH_1&2 / 3&4 | A2 | 176 / 176 | 52 / 56 | 46 / 42 |
| ADC_1 / ADC_2 | A3 | 119 / 109 | 5 / 0 | 16 / 16 |
| FiberXY_Frontend_1/2/3 | A2 | 136 each | 0 | 4 each |
| Memory_&_Clock | A3 | 104 | 126 | 19 |
| Power_Supply / _1 / _2 | A3 | 267 / 210 / 129 | 8 / 3 / 4 | 0 / 5 / 0 |
| POF_Interface | A3 | 96 | 10 | 12 |
| HMI_Program_Debug | A3 | 46 | 1 | 17 |
| Rogowski_Interface | A3 | 57 | 3 | 3 |
| SLED_Interface, Expansion, HV_Digital_IOs, Reset | A4 | 56 / 46 / 19 / 12 | 1 / 5 / 0 / 0 | 3 / 2 / 2 / 5 |
