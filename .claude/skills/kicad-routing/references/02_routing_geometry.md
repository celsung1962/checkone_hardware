# routing geometry

_Physical routing geometry rules (stackup, 45° lattice, widths, vias, pad entries, keepouts, diff pairs, zones, footprints, silkscreen) — section 3 of the full standard._

> **Revised 2026-09-16 (rev B).** Where this file conflicts with `07_review_decisions.md`, the review decision wins.

## 3. Physical routing geometry (`.kicad_pcb`)

### 3.1 Stackup and layer roles **[MEASURED]**

| Layer | Type | Thickness | Role in golden board |
|---|---|---|---|
| F.SilkS / F.Paste | — | — | Standard |
| F.Mask | mask | 0.01 | Standard |
| **F.Cu** | copper | 0.035 | Primary signal layer (5048 segments, 76%) + local power pours |
| dielectric 1 | prepreg FR4, εr 4.5, tanδ 0.02 | 0.10 | |
| **In1.Cu** | copper | 0.035 | **GND plane** (priority 1) + EARTH2 islands. **Zero routed segments.** |
| dielectric 2 | core FR4, εr 4.5, tanδ 0.02 | 1.24 | |
| **In2.Cu** | copper | 0.035 | **Split power planes** (+3.3V, +5.0V, +24V, +5VA, +12VA, +5V_SLED, local LC nodes). **Zero routed segments.** |
| dielectric 3 | prepreg FR4 | 0.10 | |
| **B.Cu** | copper | 0.035 | Secondary signal layer (1596 segments, 24%) + power pours |
| B.Mask / B.Paste / B.SilkS | — | 0.01 mask | Standard |

- Total 1.6 mm, `copper_finish "None"`, `dielectric_constraints no`, `pad_to_mask_clearance 0`, `allow_soldermask_bridges_in_footprints no`, `tenting front back` (vias tented both sides).
- Always route signals on **F.Cu and B.Cu only**. Never place a `segment` on In1.Cu or In2.Cu. Inner layers are plane-only; declare them with layer type `power` (not `signal`) in the layer table so KiCad treats them as planes (field practice, adopted 2026-09-17).
- Always keep In1.Cu as a continuous GND reference directly under F.Cu (0.1 mm prepreg) so every top-layer trace has a tight return path.
- Enable exactly the layers listed in the golden `(layers …)` block: 4 copper + F/B Adhes, Paste, SilkS, Mask, Dwgs.User, Cmts.User, Eco1/Eco2, Edge.Cuts, Margin, F/B CrtYd, F/B Fab, User.1–4.
- Board outline: one closed `gr_rect` on Edge.Cuts, stroke 0.05 mm, `fill no`. Set `grid_origin` to a board-meaningful reference (golden: 200.575, 146.05). Paper size A1.
- All 1032 footprints sit on **F.Cu** (single-sided assembly). Place components on the back only if the user asks.

### 3.2 Trace geometry: orthodiagonal only **[MEASURED]**

Golden statistics: 6641 / 6644 segments (99.95 %) lie at exactly 0°, 45°, 90° or 135°. Corners: 3858 × 45° mitres vs 241 × 90° vs 6 other. The 3 off-angle segments are in the BGA fan-out region of the SD bus.

- Always route with strictly orthodiagonal segments: every `segment` must satisfy `atan2(dy,dx) mod 45° == 0` to within 0.01°.
- Always prefer 45° mitred corners over 90° corners. Use a 90° corner only when a mitre is geometrically impossible inside a pad field.
- Never emit a `(arc …)` track element anywhere (rev B, Q-03). Length-tuning meanders use the straight-corner (chamfer) style; any arc is a FAIL. The 74 arcs in the reference board are a recorded defect.
- Never emit free-form or curved traces, Bezier paths, or teardrops.
- Never leave zero-length segments. Merge collinear same-width joints (golden still has 171 of these; treat them as cleanup debt, not a pattern to copy).
- When parsing a `.kicad_pcb`, you must compute the angle of every `segment` and fail the check if any segment is off the 45° lattice, and fail on any `arc`.

### 3.3 Track widths **[MEASURED]**

> Rev B (Q-04): widths are set by **netclass**, never per segment. The table below documents what the reference board used and remains the guide for choosing class widths.

| Width (mm) | Segments | Usage |
|---|---|---|
| **0.2** | 6285 (94.6 %) | Default signal width, all digital, analog, diff pairs |
| 0.1 | 18 | BGA escape only (SD_CLK/CMD/DAT, EMMC_nRST, EMMC_VDDI) under the 0.5 mm-pitch LFBGA-153 |
| 0.127 / 0.15 | 25 | +3.3V / GND stubs under the BGA |
| 0.5 | 98 | ±15V rails, regulator VIN/OUT nodes, LC filter nodes |
| 0.6 | 40 | +5.0V secondary runs, diode/inductor nodes |
| 0.8 | 112 | LED/diode cathode nodes, +5V_POF1/2/3, EARTH, regulator inputs |
| 1.0 | 19 | +5.0V main runs, +12VA |
| 1.5 | 41 | Relay contact nets (SD_x_NO / NC / CM) |
| 2.0 | 6 | +12VA feed, power connector CN1 pin 2 |

- Always route signals at 0.2 mm. Never go below 0.2 mm except for BGA fan-out (0.1 mm) or BGA power stubs (0.127 / 0.15 mm), and only for the short escape segment.
- Put power nets in POWER_DC (0.6) or a dedicated class; where a rail needs more copper, add a class with one of the discrete steps 0.8 / 1.0 / 1.5 / 2.0 mm or drop into an In2.Cu plane. Do not hand-set widths.
- Only 12 width changes occur mid-run in the whole board (all on power nets or BGA escapes). Always change width at a pad, via or junction, never in the middle of a straight run.

### 3.4 Keepout / rule-area behaviour **[POLICY]**

The golden board has no rule areas, so the following is the owner's stated intent:

- When a `(zone … (keepout (tracks not_allowed)))` exists on a layer, never let any `segment` or `arc` of that layer intersect or cross the keepout polygon.
- Bypass a keepout on the same layer by routing around its perimeter with orthodiagonal segments. Passing under it with a via pair is decided per project (`keepouts.layer_change_allowed`, default false → WARN) — rev B, Q-10.
- Never leave a track endpoint inside a keepout polygon.
- When a keepout forbids vias, keep via centres at least `min_clearance` outside the polygon.
- When parsing, you must test every segment of a layer against every keepout polygon of the same layer (segment–polygon intersection). Any intersection is a hard failure.

### 3.5 Pad entries: single straight perpendicular segment to pad centre **[MEASURED + POLICY]**

Golden statistics: 2989 segment endpoints coincide **exactly** (6-decimal match) with a pad centre on 2459 pads. Entry direction relative to pad axis: 0° 46 %, 90° 34 %, 45°/135° 20 %. Only 4 entry segments are shorter than 0.2 mm; 61 are shorter than 0.5 mm.

- Always terminate a track on the **exact pad centre coordinate** (footprint `at` + rotated pad `at`). Match to 1 µm.
- Always make the entry a **single straight segment** whose axis is parallel or perpendicular to the pad's long axis (0° or 90° relative angle). Use a 45° entry only when the pad is round/square or when the pad field geometry (0.5 mm-pitch BGA, fine-pitch QFN) leaves no orthogonal approach.
- Never "staircase" into a pad: no sequence of two or more sub-0.3 mm segments with alternating directions in the final 1 mm before the pad. (Golden: 58 such joints out of ~3900 corners; do not add to them.)
- Never neck down at a pad: the entry segment keeps the width of the run feeding it. A 0.2 mm run enters a 0.2 mm segment; a 0.8 mm power run enters at 0.8 mm unless the pad is physically narrower than the run, in which case step down **once**, at the last corner before the pad, never mid-straight.
- Never let the entry segment be wider than the pad's smaller dimension (golden has 2 such cases, both on R1 pad 2; treat as defects).
- Tolerated exception to centring: a pad whose larger dimension is ≥ 2 mm may receive **additional** power entries off-centre, on the pad axis, provided the primary entry is at the centre. Do not apply this exception to pads < 1 mm.
- When parsing, you must: (1) build absolute pad centres, (2) find every segment endpoint that lies inside a pad outline of the same net and layer, (3) flag any endpoint that is inside but not at the centre on a pad < 2 mm, (4) flag any entry whose relative angle is not in {0, 45, 90, 135}.

### 3.6 Via discipline **[MEASURED]**

- The reference used one padstack (0.45 / 0.2). Rev B: the via stack comes from the **netclass** (Default 0.45/0.15, POWER_* 0.60/0.30) or a predefined size (0.45/0.2, 0.6/0.4); anything else is FAIL. Through `F.Cu`–`B.Cu` only; no blind, buried or micro vias.
- Always set `(remove_unused_layers yes)` and `(keep_end_layers yes)` on every via. **Missing either is a FAIL** (rev B, Q-06). The reference has 410 vias without them — a recorded defect.
- 25 vias are `(free yes)` stitching vias on +5.0V / +3.3V; 49 vias have no track at all and stitch plane-to-pour. Use free vias only for plane stitching.
- Via spacing is governed by the fabricator hole-to-hole limit as stored in the project rules (`min_hole_to_hole`, reference 0.25 mm) — rev B, Q-11. The reference board minimum is 0.296 mm hole-to-hole.
- Via net distribution: GND 695, +3.3V 223, +5.0V 56. Stitch GND generously; signal nets use 1–2 vias each.
- Explicit `(tenting front back)` appears on 19 vias; the board default is also tented both sides. Do not untent vias.
- Never place a via inside an SMD pad, except same-net thermal vias in exposed/heatsink pads of parts approved in the project parameters (`via_in_pad.allowed_refs`), assessed per chip datasheet (rev B, Q-05).

### 3.7 Track endpoint centring on vias **[MEASURED]**

- 1988 segment endpoints land exactly (6 decimals) on a via centre; only 1 endpoint in the entire board is a near-miss (0.07 mm off, on +5.0V). Always snap the segment endpoint to the via `at` coordinate; never approximate.
- 1059 vias have tracks on only one layer; the other side lands directly in a plane or pour. This is the standard way to drop a power/GND connection into In1/In2.
- `track_not_centered_on_via` is ignored in DRC only because the router guarantees centring; do not rely on the ignore.

### 3.8 Differential pairs **[MEASURED]**

- 32 pairs detected by `_P/_N` or `P/N` suffix: ADC inputs `AD_VxIN_P/N` (16), PHY `TXP/TXN`, `RXP/RXN` (8), SFP `TDP/TDN`, `RDP/RDN` (8).
- Coupled sections run at **0.2 mm width, 0.45 mm centre-to-centre = 0.25 mm gap**, exactly the netclass values. 72 % on F.Cu, 28 % on B.Cu.
- Always name pairs with `_P/_N` (preferred) or trailing `P/N` so KiCad's pair detection works.
- Always keep the pair coupled at 0.2 / 0.25 through corners (mitred 45°) and split only for the last straight segment into the pads.

### 3.9 Copper zones and pours **[MEASURED]**

| Attribute | Value used |
|---|---|
| Outline display | `hatch edge 0.5` |
| `connect_pads` | thermal relief (no mode atom) with `clearance 0.1` (0.05 for small local LC-node pours) |
| `min_thickness` | 0.1 for planes, 0.25 for F.Cu/B.Cu power pours, 0.05 for small local pours |
| `thermal_gap` / `thermal_bridge_width` | 0.5 / 0.5 |
| `filled_areas_thickness` | no |
| `fill` | yes (solid) |
| Priority | unique integer per overlapping zone, 0–17 |

- Always give every zone a `net_name` (no orphan zones). Zone nets in the golden board: GND, EARTH2, +3.3V, +5.0V, +5VA, +12VA, −12VA, +24V, +5V_SLED, plus small `Net-(Cxx-Padn)` islands for regulator output LC nodes on In2.Cu.
- Always assign distinct priorities so smaller pours cut cleanly out of larger planes; never leave two overlapping zones at the same priority.
- Always keep thermal reliefs as the pad connection. Override to solid (`zone_connect 2`) only on mounting-hole pads (MH1–MH8) and thermal/heatsink pads (U1-9, U3-9), which is exactly where the golden board does it.
- Never enable `filled_areas_thickness`.
- Never place zones on signal layers that would compete with routing corridors; on F.Cu/B.Cu, use small local pours only where a power node needs current capacity.

### 3.10 Footprint and pad conventions **[MEASURED]**

- Footprint sources: KiCad standard libraries (Resistor_SMD 483, Capacitor_SMD 332, Package_SO, Package_TO_SOT_SMD, LED_SMD, Diode_SMD, Package_QFP, Package_BGA, MountingHole, Fiducial…) plus **one project-local library** `the geometry reference board.pretty` registered in `fp-lib-table` via `${KIPRJMOD}`. Always keep custom footprints in a project-local `.pretty` with a `${KIPRJMOD}` URI.
- Keep library pad shapes; roundrect ratio 0.25 is the standard.
- BGA (U6, 0.5 mm pitch): fan out with 0.1 mm tracks and 0.45/0.2 dog-bone vias in the channels; never via-in-pad. Pad details in the appendix.
- Never add per-pad solder-mask margins; the board default (0) applies.
- Footprint `attr`: `smd` (887), `smd dnp` (88), `through_hole exclude_from_bom` (30), `exclude_from_pos_files exclude_from_bom` for fiducials/logos, `board_only exclude_from_pos_files exclude_from_bom` for logos. Always mark mechanicals (MH*, FID*, logos, panel connectors CONN*, PS1) `exclude_from_bom`, and non-placed items `exclude_from_pos_files`.
- Always set `(attr … dnp)` on the footprint whenever the schematic symbol is `(dnp yes)` (golden: 89 = 89).
- Lock (`(locked yes)`) connectors and mechanically constrained parts (golden: 222 locked footprints, 826 locked items total).
- 3D models: 1018 / 1032 footprints reference `${KICAD9_3DMODEL_DIR}/…step`. Always keep a model link.
- Use `Fiducial_0.5mm_Mask1mm` (3–4 per board) and M3 3.2 mm mounting holes.
- Footprint rotations are restricted to 0 / ±90 / 180.

### 3.11 Silkscreen and fab layers **[MEASURED]**

- **References are hidden** on 1022 / 1032 footprints (Reference property on F.SilkS, 1.0 × 1.0 mm, 0.15 mm stroke, `hide yes`). Values are on F.Fab and hidden on 1017 / 1032.
- Free-standing silkscreen consists of **33 functional `gr_text` labels** (connector/function names such as SFP1–4, POF1–3, SLED, RGA/RGC, PH xx, +24V, LD2) at 1.0 / 1.2 / 2.0 mm height, 0.1524 mm stroke, and **16 filled `gr_poly` logos** on F.SilkS (0.2 mm stroke). One `gr_text` on F.Fab.
- Always keep silkscreen minimal and functional: hide references, label connectors and user-facing features only.
- Never place text on Edge.Cuts (`text_on_edge_cuts` is an error).

### 3.12 Groups

Group repeated sub-blocks so they move as one (details in the appendix).

---
