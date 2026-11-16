# settings and rules

_Golden settings, severities, netclass, defaults, and the (absent) .kicad_dru — sections 0–2 of the full standard._

> **Revised 2026-09-16 (rev B).** Where this file conflicts with `07_review_decisions.md`, the review decision wins.

## 0. Provenance and honesty notes (read first)

- The golden project has **no `.kicad_dru` file**. All constraints live in the `.kicad_pro` Board Setup. Section 2 documents this and supplies a derived (not extracted) rule file you may use only when explicitly asked.
- The golden PCB contains **zero rule areas / keepout zones** (no `(keepout …)` block in any zone, no `rule_area` in any schematic). Keepout behaviour in Section 3.4 is therefore **[POLICY]**.
- The golden PCB contains **74 track arcs**. All of them belong to six length-tuned nets (SD bus DAT0–3, ETH4 RX/TX clocks) and are meander-tuning artefacts (radius 0.18–0.27 mm, flanked by 0.1 mm stubs). Everything else is straight segments. Section 3.2 encodes this as "arcs only inside tuning meanders".
- Track-to-pad centering is the dominant practice, not an absolute: 2989 track endpoints land **exactly** on a pad centre (2459 distinct pads); 553 terminal endpoints land inside a pad but off-centre (mostly GND/+3.3V multi-entries into large pads, and BGA fan-out). Section 3.5 states the strict rule and the only tolerated exception.

---

## 1. Global configuration (`.kicad_pro`)

### 1.1 Board design rules (`board.design_settings.rules`) — copy verbatim

| Rule | Value (mm) |
|---|---|
| `min_clearance` | 0.1 |
| `min_connection` | 0.1 |
| `min_copper_edge_clearance` | 0.5 |
| `min_hole_clearance` | 0.15 |
| `min_hole_to_hole` | 0.25 |
| `min_track_width` | 0.1 |
| `min_via_diameter` | 0.45 |
| `min_via_annular_width` | 0.1 |
| `min_through_hole_diameter` | 0.2 |
| `min_microvia_diameter` | 0.25 |
| `min_microvia_drill` | 0.2 |
| `min_resolved_spokes` | 2 |
| `min_silk_clearance` | 0.0 |
| `min_text_height` | 0.7 |
| `min_text_thickness` | 0.08 |
| `solder_mask_to_copper_clearance` | 0.0 |
| `min_groove_width` | 0.0 |
| `max_error` | 0.005 |
| `use_height_for_length_calcs` | true |

- Always set these exact values when creating a new project; never loosen `min_clearance`, `min_track_width`, `min_via_diameter` or `min_hole_to_hole`.
- Copper-to-edge clearance (`min_copper_edge_clearance`, reference 0.5 mm) follows the fabricator capability (rev B, Q-12); the audit reads the project value.

### 1.2 Netclasses (rev B — reviewer's table, Q-04)

The reference board used a single `Default` class with hand-set power widths. **That practice is withdrawn.** Netclasses are defined before routing and decide track width and via stack; the audit checks every segment and via against its class.

| Netclass | Priority | Track | Clearance | Via ø / drill | Diff pair w / gap | Nets (patterns) |
|---|---|---|---|---|---|---|
| Default | — | 0.20 | 0.10 | 0.45 / 0.15 | 0.20 / 0.25 | everything unmatched |
| POWER_DC | 0 | 0.60 | 0.10 | 0.60 / 0.30 | — | `+1.2V` `+2.5V` `+3.3V` `+5.0V` `+24V` `GND` |
| POWER_AC | 1 | 1.50 | 3.00 | 0.60 / 0.30 | — | assign explicitly (mains separation) |
| BUS_SDRAM_CONTROL | 2 | 0.20 | 0.10 | 0.45 / 0.15 | — | project-specific example |
| BUS_SDRAM_ADDR | 3 | 0.20 | 0.10 | 0.45 / 0.15 | — | `*SDRAM0*` `*SDRAM1*` |
| BUS_SDRAM_DATA | 4 | 0.20 | 0.10 | 0.45 / 0.15 | — | project-specific example |

Predefined extra sizes (allowed in addition to the class value): tracks 0.1 · 0.13459 · 0.2 · 0.3 · 0.45 · 0.8 · 1.0 mm; vias 0.45/0.2 and 0.6/0.4; diff pair 0.2 / gap 0.2 / via gap 0.25. Schematic wire 6 mil, bus 12 mil.

- Always assign every net to a class before routing (name pattern or explicit assignment). Lower priority number wins when several patterns match.
- Always create one class per bus group (rename the `BUS_SDRAM_*` examples); keep `Default`, `POWER_DC`, `POWER_AC` in every project.
- Never hand-set a track width; if a net needs another width, move it to a class.
- **Open conflict**: Default/BUS via drill 0.15 mm vs `min_through_hole_diameter` 0.20 mm. Settle with the fabricator; the audit warns until then.

### 1.3 DRC severities (`board.design_settings.rule_severities`)

**Intentionally `ignore`:**
`footprint_filters_mismatch`, `missing_courtyard`, `npth_inside_courtyard`, `silk_edge_clearance`, `silk_over_copper`, `silk_overlap`, `track_not_centered_on_via`, `tuning_profile_track_geometries`.

**Intentionally `warning`:**
`copper_sliver`, `courtyards_overlap`, `drill_out_of_range`, `duplicate_footprints`, `extra_footprint`, `footprint_symbol_field_mismatch`, `footprint_symbol_mismatch`, `footprint_type_mismatch`, `hole_clearance`, `hole_to_hole`, `holes_co_located`, `isolated_copper`, `lib_footprint_issues`, `lib_footprint_mismatch`, `mirrored_text_on_front_layer`, `missing_tuning_profile`, `net_conflict`, `nonmirrored_text_on_back_layer`, `padstack`, `pth_inside_courtyard`, `solder_mask_bridge`, `text_height`, `text_thickness`, `track_width`, `unconnected_items`, `via_dangling`.

**Everything else stays `error`**, notably: `annular_width`, `clearance`, `connection_width`, `copper_edge_clearance`, `creepage`, `diff_pair_gap_out_of_range`, `diff_pair_uncoupled_length_too_long`, `footprint`, `invalid_outline`, `item_on_disabled_layer`, `items_not_allowed`, `length_out_of_range`, `malformed_courtyard`, `microvia_drill_out_of_range`, `missing_footprint`, `shorting_items`, `skew_out_of_range`, `starved_thermal`, `text_on_edge_cuts`, `through_hole_pad_without_hole`, `too_many_vias`, `track_angle`, `track_dangling`, `track_on_post_machined_layer`, `track_segment_length`, `tracks_crossing`, `unresolved_variable`, `zones_intersect`.

- Always reproduce this severity map exactly in new projects.
- Never downgrade `track_angle`, `track_dangling`, `tracks_crossing`, `clearance`, `starved_thermal` or `zones_intersect` below `error`.
- Silkscreen checks are deliberately ignored because references are hidden (see 3.9); do not re-enable them unless silkscreen references are turned on.

### 1.4 DRC exclusions policy

The golden project carries 20 `drc_exclusions`, all of one of three types (`courtyards_overlap`, `footprint_type_mismatch`, `pth_inside_courtyard`) and all tied to the same four footprint UUIDs (stacked connector/mechanical parts).

- Always resolve a DRC complaint by adding a **specific, per-instance exclusion** for a reviewed false positive; never resolve it by lowering the rule severity globally.
- Keep exclusions limited to mechanical/courtyard categories. Never exclude a `clearance`, `shorting_items`, `tracks_crossing` or `unconnected_items` marker.

### 1.5 Text, silkscreen and graphic defaults (`board.design_settings.defaults`)

| Item | Size (mm) | Thickness / line (mm) |
|---|---|---|
| Silkscreen text | 1.0 × 1.0 | 0.1 |
| Silkscreen line | — | 0.1 |
| Copper text | 1.5 × 1.5 | 0.3 |
| Copper line | — | 0.2 |
| Fab text | 1.0 × 1.0 | 0.15 |
| Fab line | — | 0.1 |
| Other text | 1.0 × 1.0 | 0.15 |
| Other line | — | 0.1 |
| Courtyard line | — | 0.05 |
| Board outline line | — | 0.05 |
| Default pad | 2.54 × 1.27, drill 0.8 | — |

- Always keep all `apply_defaults_to_fp_*` flags `false`. Library footprints keep their own text and line widths.
- Always keep silkscreen text ≥ 0.7 mm high and ≥ 0.08 mm stroke (the DRC minimums). Golden free-standing silkscreen labels use 1.0, 1.2 or 2.0 mm height with 0.1524 mm stroke.
- Dimensions: units 3 (automatic), precision 4, suppress zeroes, arrow 1.27 mm, extension offset 0.5 mm.

### 1.6 Zone defaults (`defaults.zones`)

| Field | Value |
|---|---|
| `min_clearance` | 0.1 |
| `min_thickness` | 0.25 |
| `pad_connection` | 1 (thermal relief) |
| `thermal_relief_gap` | 0.5 |
| `thermal_relief_spoke_width` | 0.5 |
| `remove_islands` | 0 (always remove) |
| `min_island_area` | 10 mm² |
| `fill_mode` | 0 (solid) |
| `border_display_style` | 2 (hatch edge) |
| `border_hatch_pitch` | 0.5 |
| `corner_smoothing` | 0 |
| `zones_allow_external_fillets` | false |

### 1.7 Teardrops and tuning

- Teardrop options are configured (`td_onpthpad`, `td_onsmdpad`, `td_onvia` true, `td_ontrackend` false; length ratio 0.5, height ratio 1.0, max len 1.0, max height 2.0, filter ratio 0.9) **but the golden board contains zero teardrops**. Never add teardrops unless the user explicitly requests them.
- Tuning pattern defaults (rev B): `corner_style` 2 (chamfer — straight corners, so boards carry zero arcs, Q-03), `corner_radius_percentage` 80, `min_amplitude` 0.2, `max_amplitude` 1.0, spacing 0.6 (single track and skew) / 1.0 (diff pair), `single_sided` false. Arcs are no longer permitted anywhere (3.2).

### 1.8 ERC severities (`erc.rule_severities`)

**`ignore`:** `footprint_filter`, `footprint_link_issues`, `four_way_junction`, `lib_symbol_issues`, `lib_symbol_mismatch`, `net_not_bus_member`, `pin_to_pin`.

**`warning`:** `endpoint_off_grid`, `field_name_whitespace`, `global_label_dangling`, `ground_pin_not_ground`, `hier_label_mismatch`, `isolated_pin_label`, `label_multiple_wires`, `missing_bidi_pin`, `missing_input_pin`, `missing_unit`, `multiple_net_names`, `no_connect_connected`, `no_connect_dangling`, `same_local_global_label`, `similar_label_and_power`, `similar_labels`, `similar_power`, `simulation_model_issue`, `stacked_pin_name`, `unconnected_wire_endpoint`.

**`error`:** `bus_definition_conflict`, `bus_entry_needed`, `bus_to_bus_conflict`, `bus_to_net_conflict`, `different_unit_footprint`, `different_unit_net`, `duplicate_reference`, `duplicate_sheet_names`, `extra_units`, `label_dangling`, `missing_power_pin`, `pin_not_connected`, `pin_not_driven`, `power_pin_not_driven`, `single_global_label`, `unannotated`, `undefined_netclass`, `unit_value_mismatch`, `unresolved_variable`, `wire_dangling`.

- `pin_not_connected` is an **error**. This is what forces the `no_connect` discipline in Section 4.
- `pin_to_pin` is ignored, so the pin-type conflict matrix is not the gate; explicit no-connects and PWR_FLAGs are.
- Copy the 12 × 12 `erc.pin_map` from the golden `.kicad_pro` verbatim when cloning the project settings; do not hand-edit it.

### 1.9 Schematic editor settings (`schematic.drawing`)

- `connection_grid_size` 50 mil, `default_line_thickness` 6 mil, `default_text_size` 50 mil, `junction_size_choice` 3, `label_size_ratio` 0.375, intersheet references **off**, `hop_over_size_choice` 0.
- Annotation: `annotate_start_num` 0, method 0, sort order 0.

### 1.10 BOM export preset (`schematic.bom_settings`)

- Field order (visible): `Reference`, `LCSC`, `Value`, `Datasheet`, `${DNP}`, `${EXCLUDE_FROM_BOM}`, `${EXCLUDE_FROM_BOARD}`, `Footprint`, `AqtechPN`, `Description`, `${ITEM_NUMBER}`, `VOLTAGE - SUPPLY`, `${QUANTITY}`.
- Group by `Value`, `DNP`, `Exclude from BOM`, `Exclude from Board`, `Footprint`. `group_symbols` true, `include_excluded_from_bom` true, `exclude_dnp` false, sort ascending by `AqtechPN`.
- CSV format: field delimiter `,`, string delimiter `"`, ref delimiter `,`, no range delimiter.
- Always keep `LCSC` and `AqtechPN` as first-class symbol fields (Section 4.4).

### 1.11 Plot / fabrication output (`setup.pcbplotparams`)

- Gerber: `usegerberattributes yes`, `usegerberadvancedattributes yes`, `creategerberjobfile yes`, `usegerberextensions no`, `disableapertmacros no`, `subtractmaskfromsilk no`, `plot_black_and_white yes`, `drillshape 1`, `mode 1`, `useauxorigin no`.
- DNP handling on Fab: `sketchdnponfab yes`, `crossoutdnponfab yes`, `hidednponfab no`.
- Layer selection mask `0x00000000_00000000_55555555_5755f5ff`.
- STEP export path is the project name (`<project>.step`).
- Fabrication deliverables live in `jlcpcb/gerber` and `jlcpcb/production_files` (JLCPCB workflow, `jlcpcb/project.db`).

### 1.12 Local project settings (`.kicad_prl`)

Moved to `99_appendix_minor_details.md`. Only `auto_track_width` true matters for routing.

---

## 2. Custom rules (`.kicad_dru`)

**[MEASURED] The golden project defines no `.kicad_dru` file and therefore no `(version 1)` custom rules.** Hole clearance (0.15), hole-to-hole (0.25), edge clearance (0.5), annular width (0.1) and via size are enforced entirely from Board Setup (Section 1.1).

- Do not fabricate a `.kicad_dru` for a cloned project. Reproduce Section 1.1 instead.
- Via-in-pad is not used (only 3 of 1536 vias fall inside an SMD pad outline, and none on fine-pitch pads). Treat via-in-pad as forbidden by convention, not by rule file.
- If, and only if, the user asks for a rule file, start from the derived template below. It restates the golden constraints; it does not add new ones.

```lisp
(version 1)
;; Derived from the geometry reference board Board Setup — not present in the golden project.
(rule "golden_hole_clearance"
  (constraint hole_clearance (min 0.15mm)))
(rule "golden_hole_to_hole"
  (constraint hole_to_hole (min 0.25mm)))
(rule "golden_edge_clearance"
  (condition "A.Type == 'Track' || A.Type == 'Via' || A.Type == 'Zone' || A.Type == 'Pad'")
  (constraint edge_clearance (min 0.5mm)))
(rule "golden_via_stack"
  (condition "A.Type == 'Via'")
  (constraint via_diameter (min 0.45mm))
  (constraint hole_size (min 0.2mm)))
(rule "golden_no_via_in_smd_pad"
  (condition "A.Type == 'Via' && B.Type == 'Pad' && B.Pad_Type == 'SMD'")
  (constraint physical_hole_clearance (min 0.1mm)))
(rule "golden_diff_pair"
  (condition "A.inDiffPair('*')")
  (constraint track_width (min 0.2mm) (opt 0.2mm))
  (constraint diff_pair_gap (min 0.25mm) (opt 0.25mm)))
```

---
