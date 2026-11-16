# schematic

_Schematic practice (hierarchy, no_connect discipline, labels, fields, libraries) — section 4 of the full standard._

## 4. Schematic best practices (`.kicad_sch`)

### 4.1 Hierarchy **[MEASURED]**

- Root sheet (A1) contains **only 18 sheet symbols, wires and junctions** (0 components, 0 labels). All connectivity between blocks is drawn on the root via sheet pins (BORAX has 148 pins, Fiber_ETH_1&2 46, Fiber_ETH_3&4 42).
- **Zero global labels in the entire project.** Inter-sheet signals use `hierarchical_label` (349: 167 input, 154 output, 28 bidirectional) and sheet pins. Power uses power symbols only.
- Always use hierarchical labels + sheet pins for inter-sheet signals. Never use global labels for signals.
- Always pick the sheet pin shape that matches signal direction (`input` / `output` / `bidirectional`); this is what makes `hier_label_mismatch` meaningful.
- Repeated blocks are **separate sheet files** with unique annotation (FiberXY_Frontend_1/2/3, Power_Supply_1/2), not multi-instance sheets.
- Sheet paper is sized to content: A1 root, A2 for dense fiber/ETH pages, A3 for ADC/power/memory, A4 for small blocks (Reset, Expansion, HV_Digital_IOs, SLED).

### 4.2 No-connect discipline **[MEASURED]**

- 321 `no_connect` flags project-wide: Memory_&_Clock 126, Fiber_ETH_3&4 56, Fiber_ETH_1&2 52, BORAX 47, POF_Interface 10, Power_Supply 8, and so on.
- Always place a `no_connect` on **every** unused IC pin, connector pin and module pin. `pin_not_connected` is an ERC **error** in this project, so an unflagged pin fails ERC.
- Never leave `no_connect_dangling` (a flag not on a pin end) or `no_connect_connected` (a flag on a wired pin); both are warnings that must be cleared before release.
- Add `power:PWR_FLAG` (23 in golden) on every externally driven power net (connector inputs, regulator outputs that are not power-output pins) so `power_pin_not_driven` (error) passes.

### 4.3 Wiring and labels **[MEASURED]**

- Wires and buses at default width (`stroke width 0`), 4825 wires, 819 buses, 761 bus entries, 1044 junctions.
- Labels and text at **1.27 × 1.27 mm** (1282 of 1283 labels). Never use other label sizes.
- Local labels (934) name every meaningful net within a sheet; buses group ETH/SD/parallel signals.
- Junctions are explicit; four-way junctions are ignored by ERC but avoid them for readability.
- Symbols are freely rotated (0/90/180/270) and mirrored (1191 mirrored) for clean flow left-to-right; fields are placed manually (`fields_autoplaced` on only 101 / 2053 symbols).

### 4.4 Symbol fields and libraries **[MEASURED]**

- Mandatory fields on every symbol: `Reference`, `Value`, `Footprint`, `Datasheet`, `Description`.
- Sourcing fields: `LCSC` (present on 1149 symbols, non-empty on 1118) and `AqtechPN` (non-empty on 914). Always populate `LCSC` for every purchasable part and `AqtechPN` for internal stock items. `VOLTAGE - SUPPLY` is shown in the BOM.
- Vendor-import fields (MANUFACTURER, SERIES, PACKAGE, …) are tolerated but hidden in the BOM; list in the appendix.
- Custom symbols live in the project-local `the geometry reference board.kicad_sym` (registered in `sym-lib-table` via `${KIPRJMOD}`); standard parts come from `Device`, `power`, `Amplifier_Operational`, `LED`, `Diode`. Full census in the appendix.
- Power symbols: `power:GND` 525, `power:+3.3VA` 52, `power:GNDPWR` 11, `power:GND2` 8, `power:PWR_FLAG` 23, plus project bars `+5V_POF_BAR`, `+5V_SLED_BAR`, `GND_POWER_GROUND`.
- Mark unfitted parts with `(dnp yes)` (89 symbols) and mechanicals with `(in_bom no)` (58 symbols). Never delete a DNP part from the schematic; flag it.
- `embedded_fonts no` on every sheet.

---
