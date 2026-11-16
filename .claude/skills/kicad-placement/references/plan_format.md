# Placement plan (JSON)

The plan is the reviewable part of a placement: zones, blocks, order, anchors and keep-outs live here, not in
code. Coordinates are board coordinates in mm (KiCad's: x to the right, **y downwards**), rectangles are
`[x0, y0, x1, y1]`. Relative paths are relative to the plan file. `make_plan.py` writes a draft.

## Top level

| Key | Default | Meaning |
|---|---|---|
| `board` | — | Input `.kicad_pcb`. Never modified; `place.py --out` writes a new file. |
| `pintypes` | — | `pintypes.json` from `extract_schematic.py`. Needed to recognise decoupling capacitors. |
| `schpos` | — | `schpos.json` (schematic positions): relative layout inside each block, IC ↔ capacitor pairing. |
| `grid` | 0.25 | Placement grid of footprint origins (mm). 0.5 or 0.25 are the usual choices. |
| `resolution` | 0.05 | Occupancy raster (mm). Do not raise it: a 0.25 mm raster wastes ~40 % of the area. |
| `edge_clearance` | 1.0 | Courtyard to Edge.Cuts (mm). |
| `sensitive_edge_clearance` | 2.5 | For fine-pitch ICs, MLCC > 0805, crystals/oscillators (board flex cracks them). |
| `spacing` | 0.3 | Courtyard to courtyard between SMD parts (mm). A default: take it from the user, the fab rules or the team's existing boards (some production boards use 0.1–0.2 mm). |
| `tht_spacing` | 1.0 | Around through-hole parts (soldering-iron access). |
| `mech_spacing` | 1.0 | Around fixed mechanical parts and holes. |
| `fixed` | `["H*","MH*"]` | Glob patterns of footprints that never move. Add connectors, switches, holders, parts the engineer placed. |
| `treat_locked_as_fixed` | true | Locked footprints are fixed too. |
| `lock_fixed` | true | Lock the fixed footprints that lie inside the outline in the output. |
| `keepouts` | `[]` | `{"name", "rect", "refs"}`: parts matching `refs` (globs; `["*"]` = all) may not touch `rect`. Height limits under displays/covers, antenna areas, mounting zones. |
| `artwork_obstacle` | true | Padless logos and titles on the front layers keep parts off their bounding box. `false` when the team lets parts cover a logo. |
| `regions` | `{}` | Named lists of rectangles. Blocks place inside the union of their regions. |
| `blocks` | `[]` | Ordered list (below). |
| `sensitive` | see below | `fine_pitch_max` (mm, default 0.66), `mlcc_packages` (`1206`, `1210`, `1812`, `2220`), `prefixes` (`Y`, `X`). |
| `decap_max_sch_distance` | 100 | Max schematic distance (mm) between a capacitor and the IC it is assigned to. |
| `heat`, `heat_sensitive`, `heat_min_distance` | `[]`, `[]`, 5 | Thermal separation (courtyard to courtyard, mm): enforced by `place.py` while placing and checked by `verify_placement.py`. Aluminium electrolytics are added to `heat_sensitive` automatically (below). |
| `electrolytic_footprints` | `CP_Elec`, `CP_Radial`, `CP_Axial`, `C_Elec`, `CP_THT` | Footprint-name fragments of aluminium electrolytics; every `C*` matching one is heat-sensitive (1.2.0). `[]` switches it off. |
| `testpoints` | see below | Test-point access, WARN only (1.2.0): `prefixes` (`TP`), `min_pitch` 2.54 (pad centre to pad centre, probe pitch), `min_to_part` 1.0 (pad to any other courtyard), `min_to_edge` 1.0 (pad to Edge.Cuts), `one_side` true. Take the numbers from whoever tests the board (bench probes, flying probe, bed of nails). |
| `polarity` | see below | Polarity / pin-1 marks, WARN only (1.2.0): `prefixes` (`D`, `LED`, `U`, `Q`, `IC`, followed by a digit), `footprints` (name fragments `CP_`, `LED`, `Diode`, `D_`), `exclude_prefixes` (`DS`). Each such part needs a silkscreen graphic that no other courtyard covers. |
| `near` | `[]` | Datasheet proximity: `{"a": "Y1.3", "b": "U1.15", "max_mm": 5, "why": "..."}`. `a`/`b` are `REF.PAD`, or `REF` for any pad. A hard check in `verify_placement.py`; the placer does not pull parts together, so give those parts `anchors`. Entries whose `why` starts with `analog:` are written (and replaced) by `signal_near.py --write`; keep hand-written rules without that prefix. |
| `_near_suggestions` | written by `make_plan.py` | Candidates found in the netlist (oscillator / clock pin, shunt / monitor, USB series parts, ADC input capacitors, inductor / switch pin, flying capacitors). Not checked; copy the ones that apply into `near`. |

## Blocks

Each part goes to the **first** block whose `select` matches it, so small specific blocks (connector parts) come
before broad ones (a whole sheet). Blocks are also placed in this order.

| Key | Meaning |
|---|---|
| `name` | Shown in reports and renders. |
| `select` | Which parts: `refs` (globs, always included) **or** all of the other conditions: `sheet` (name or list of globs; the sheet INSTANCE name as the board shows it, e.g. `Sensor 13-24`; for nested sheets the last level alone also matches), `prefix` (list), `range` `[lo, hi]` (reference number), `regex`, `all: true`; minus `exclude` (globs). |
| `regions` | Region names the block may use. |
| `rects` | Extra rectangles (optional). |
| `box` | Target box: the schematic layout of the block is mapped into it. Defaults to the first region. |
| `mirror_x`, `mirror_y` | Mirror that mapping (e.g. the schematic flows left→right but the output connector is on the left). |
| `anchors` | `{"U3": [x, y]}`: target positions that override the mapping (an IC next to its connector, a regulator by the battery terminal). |

A block with no `regions`, `rects` or `box` may use the whole board. Parts left unassigned make `place.py` stop
with their list — add a catch-all `{"name": "Everything else", "select": {"all": true}}` at the end.

## Example (a small sensor board)

```json
{
  "board": "../../hardware/node.kicad_pcb",
  "pintypes": "pintypes.json",
  "schpos": "schpos.json",
  "fixed": ["H*", "J1", "J2", "SW1", "BT1"],
  "keepouts": [{"name": "under the display", "rect": [-30, -20, 30, 20], "refs": ["L3", "PS1"]},
               {"name": "antenna", "rect": [40, -25, 50, -10], "refs": ["*"]}],
  "regions": {
    "west":  [[-48, -28, -20, 28]],
    "north": [[-20, -28, 45, -12]],
    "south": [[-20, 12, 45, 28]]
  },
  "blocks": [
    {"name": "J1 protection", "select": {"refs": ["D1", "D2", "F1", "C1", "C2"]},
     "regions": ["west"], "box": [-48, -10, -40, 10]},
    {"name": "Sensor front-end", "select": {"sheet": "Analog"}, "regions": ["west"], "box": [-40, -28, -20, 28]},
    {"name": "MCU support", "select": {"sheet": "MCU"}, "regions": ["north"], "anchors": {"Y1": [5, -18]}},
    {"name": "Power", "select": {"sheet": "Power"}, "regions": ["south"], "anchors": {"U7": [30, 20]}},
    {"name": "Test points", "select": {"prefix": ["TP"]}},
    {"name": "Everything else", "select": {"all": true}}
  ],
  "heat": ["U7", "L2", "Q4"], "heat_sensitive": ["U2", "Y1"], "heat_min_distance": 5,
  "near": [{"a": "Y1.3", "b": "U2.15", "max_mm": 5, "why": "ADC datasheet 11.1: clock source at CLKIN"},
           {"a": "R12", "b": "U5", "max_mm": 6, "why": "INA226 8.4.1: Kelvin to the shunt"}]
}
```

## Reading `place.py --budget`

`demand` = Σ (courtyard width + spacing) × (courtyard height + spacing) of the block's parts; `free` = free area
of the block's regions now (fixed parts and edge clearance removed). Aim for `ratio` ≤ 0.65 per block; the
greedy placer starts to fragment above ~0.7. Regions shared by several blocks are counted for each of them —
look at the total line too.
