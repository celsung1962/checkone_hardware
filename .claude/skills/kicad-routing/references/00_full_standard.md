# KiCad_Master_Skill.md

**System instruction set for autonomous KiCad PCB design (Claude Code) — rev C, 2026-09-17.**

Derived from the "Golden" reference project **the geometry reference board** (KiCad 9.0, file format `20241229`, 4-layer, 200 × 192.5 mm, 1032 footprints, 959 nets, 6644 track segments, 1536 vias, 29 zones, 18 hierarchical sheets), revised by the specialist review of 2026-09-16 (netclasses, zero arcs, per-project parameters) and by this revision (mandatory pre-routing gate, JLCPCB capability enforcement, immutable 4-layer order).

Every rule is an imperative. Tags: **[MEASURED]** verified numerically in the golden files · **[POLICY]** owner's intent, not observable in the golden board · **[REVIEW]** decided by the 2026-09-16 review · **[GATE]** mandatory interactive step introduced in rev C.

This document is the human-readable standard. The executable form is the Claude Code skill `kicad-routing` (`~/.claude/skills/kicad-routing/`): `scripts/apply_settings.js` (settings and fabricator enforcement), `scripts/kicad_audit.js` (PASS/FAIL audit), `scripts/settings_report.js`, `fabricators/jlcpcb.json`, `templates/kicad_golden.project.json`. Where this text and the scripts disagree, fix the scripts and this text together.

---

## 0. Pre-Routing Setup & Manufacturer Capabilities **[GATE] — MANDATORY, FIRST**

This section runs **before any modification of a `.kicad_pcb` and before the first track is drawn**. It also runs before editing an existing board whose fabricator profile is not yet on record. The audit script fails (`pre-flight`) when the profile is missing, so skipping this section cannot produce a "done" result.

### 0.1 Pause and ask — the pre-flight questionnaire

You MUST stop and ask the user, with a direct question (in Claude Code use `AskUserQuestion`), and you MUST NOT assume, infer from the file, or default these two values:

1. **Layer count** — 2, 4 or 6 copper layers.
2. **Copper weight** — 1 oz or 2 oz outer copper (JLCPCB standard: 1 oz outer with 0.5 oz inner on multilayer; 2 oz outer with 1 oz inner).

Ask both in a single interaction. Offer the JLCPCB-supported options only. If the user answers with something outside the table (e.g. 8 layers, 3 oz), say that no capability profile exists for it and ask again or stop.

Confirm in one line what you will apply, for example: "Configuring for JLCPCB, 4-layer, 1 oz: min track/clearance 0.10 / 0.10 mm (JLC allows 0.09), via 0.45/0.20 (JLC allows 0.25/0.15), immutable order Top signal | In1 GND | In2 POWER | Bottom signal."

Never ask the questionnaire twice in one project: once answered, the profile is written to `kicad_golden.project.json` (`fabricator` block) and every later session reads it from there. If that file already carries a profile, state it and proceed; ask again only if the user wants to change it.

### 0.2 Retrieve and enforce JLCPCB capabilities

Once layer count and copper weight are confirmed:

1. Load the matching profile from `fabricators/jlcpcb.json` (`2L-1oz`, `2L-2oz`, `4L-1oz`, `4L-2oz`, `6L-1oz`, `6L-2oz`). If web access is available, re-check the live capability page (`https://jlcpcb.com/capabilities/pcb-capabilities`), update any changed value in the JSON with today's date in `captured`, and tell the user what changed. Never invent a value that is in neither source.
2. Run `apply_settings.js <project>.kicad_pro --fab jlcpcb --layers <N> --copper <1oz|2oz>`. It writes the golden settings and then sets **every KiCad Board Setup rule to the stricter of (golden value, JLCPCB minimum)**, so no rule can sit below the fabricator's physical limit. Add `--fab-exact` only when the user explicitly asks to exploit the fabricator's full capability (for example a 0.15 mm via drill on 4-layer, which also settles the open netclass conflict of Section 5).
3. Verify the result: `min_track_width`, `min_clearance`, `min_through_hole_diameter` (via hole), `min_via_diameter`, `min_via_annular_width`, `min_hole_to_hole`, `min_copper_edge_clearance`, `min_text_height`, `min_text_thickness` must each be ≥ the profile. The audit fails (`pre-flight`) on any rule below the limit.
4. Check the netclass via stacks against the profile: every class via drill ≥ profile via hole, every class via diameter ≥ profile via diameter. On 2-layer profiles (via hole ≥ 0.3 mm) the template's 0.45/0.15 and 0.45/0.20 vias are **not** manufacturable: raise the Default/BUS via to 0.5/0.3 before routing and tell the user.
5. Correct the stackup editor to the profile's copper: 4L-1oz = 35 µm outer, 17.5 µm inner (the golden file wrongly declares 35 µm on all four layers). Current and impedance figures are meaningless until this is done.

JLCPCB profile summary (captured 2026-09-17; the JSON is authoritative):

| Profile | Min track / clearance | Via hole / diameter | Annular | Hole-to-hole | Copper-to-edge |
|---|---|---|---|---|---|
| 2L-1oz | 0.127 / 0.127 | 0.30 / 0.50 | 0.10 | 0.254 | 0.30 (0.40 V-cut) |
| 2L-2oz | 0.20 / 0.20 | 0.30 / 0.50 | 0.10 | 0.254 | 0.30 |
| 4L-1oz | 0.09 / 0.09 (inner 0.5 oz) | 0.15 / 0.25 | 0.05 | 0.254 | 0.30 |
| 4L-2oz | 0.20 / 0.20 | 0.15 / 0.25 | 0.05 | 0.254 | 0.30 |
| 6L-1oz / 6L-2oz | as 4L | 0.15 / 0.25 | 0.05 | 0.254 | 0.30 |

The golden standard is stricter than JLCPCB on 4-layer for track/clearance (0.10/0.10), via hole (0.20) and edge (0.5); keep those unless the user asks otherwise. It is **looser** than the captured JLCPCB minimums on four rules: `min_hole_clearance` 0.15 (JLC 0.254), `min_hole_to_hole` 0.25 (JLC 0.254), `min_text_height` 0.7 (JLC 1.0), `min_text_thickness` 0.08 (JLC 0.15). `apply_settings.js --fab` raises exactly these four; the audit reports them as "raised to the fabricator minimum", not as deviations.

### 0.3 Strict 4-layer stackup rule **[GATE]**

If the user specifies **4 layers**, configure and route with this immutable order. Do not reorder, do not swap the planes, do not put signals on the inner layers.

| KiCad layer | Role | What is allowed on it |
|---|---|---|
| **F.Cu** (Layer 1, Top) | **Signal** | Tracks, components, local power pours |
| **In1.Cu** (Layer 2) | **GND plane** | One GND zone covering the board (EARTH/chassis islands tolerated). No tracks. Declare layer type `power`. |
| **In2.Cu** (Layer 3) | **POWER plane** | Split power zones only (+3.3V, +5.0V, +24V, LC-node islands…). No tracks, no GND-only plane. Declare layer type `power`. |
| **B.Cu** (Layer 4, Bottom) | **Signal** | Tracks, power pours; components only if the user asks |

The audit enforces this: a track on In1/In2 is FAIL; In1.Cu without a GND zone is FAIL; In2.Cu without any zone is FAIL; a GND-only In2 is WARN. For 2-layer boards there are no planes: pour GND on B.Cu and route signals on F.Cu. For 6-layer boards propose Top S | In1 GND | In2 S | In3 S | In4 POWER | Bottom S and confirm it with the user before drawing anything.

### 0.4 Only then: proceed

After 0.1–0.3 are done and the audit's `pre-flight` and `stackup-order` checks are clean, continue with Section 1 (settings) and the routing rules of Sections 3–4. If at any point the user changes layer count or copper, return to 0.1.

---

## 1. Global configuration (`.kicad_pro`)

### 1.1 Board design rules — golden baseline

These are the golden values. After Section 0 they are raised wherever the JLCPCB profile is stricter (2-layer, 2 oz); they are never lowered below the profile.

| Rule | Golden (mm) |
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
| `min_microvia_diameter` / `min_microvia_drill` | 0.25 / 0.2 |
| `min_resolved_spokes` | 2 |
| `min_silk_clearance` | 0.0 |
| `min_text_height` / `min_text_thickness` | 0.7 / 0.08 |
| `solder_mask_to_copper_clearance` | 0.0 |
| `max_error` | 0.005 |

- Never loosen a rule below the fabricator profile of Section 0. **[GATE]**
- Deviations from the golden baseline are acceptable only when they mirror the fabricator's capability sheet; the audit warns on every deviation. **[REVIEW Q-11, Q-12]**

### 1.2 Netclasses **[REVIEW Q-04]**

The golden board used a single class with hand-set power widths. That practice is withdrawn. Define the netclasses **before routing**; widths and via stacks come from the class, never from the segment.

| Netclass | Priority | Track | Clearance | Via ø / drill | Diff pair w / gap | Assigned by name pattern |
|---|---|---|---|---|---|---|
| Default | — | 0.20 | 0.10 | 0.45 / 0.15 | 0.20 / 0.25 | everything unmatched |
| POWER_DC | 0 | 0.60 | 0.10 | 0.60 / 0.30 | — | `+1.2V` `+2.5V` `+3.3V` `+5.0V` `+24V` `GND` |
| POWER_AC | 1 | 1.50 | 3.00 | 0.60 / 0.30 | — | explicit assignment (mains separation) |
| BUS_SDRAM_CONTROL / ADDR / DATA | 2 / 3 / 4 | 0.20 | 0.10 | 0.45 / 0.15 | — | `*SDRAM0*` `*SDRAM1*` → ADDR; examples of "one class per bus" |

Predefined extra sizes: tracks 0.1 · 0.13459 · 0.2 · 0.3 · 0.45 · 0.8 · 1.0; vias 0.45/0.2 and 0.6/0.4; diff pair 0.2 / gap 0.2 / via gap 0.25.

- Always assign every net to a class (pattern or explicit; lower priority number wins). Keep Default, POWER_DC and POWER_AC in every project; rename the BUS_* examples per project.
- Never hand-set a width. A track not at its class width is WARN (predefined widths and BGA escapes excepted); a via matching neither its class nor a predefined size is FAIL.
- **Open conflict**: class via drill 0.15 vs golden `min_through_hole_diameter` 0.20. On a JLCPCB 4-layer profile 0.15 is manufacturable; settle it in Section 0.2 (`--fab-exact` or raise the class drill to 0.20).

### 1.3 DRC severities

**`ignore`:** `footprint_filters_mismatch`, `missing_courtyard`, `npth_inside_courtyard`, `silk_edge_clearance`, `silk_over_copper`, `silk_overlap`, `track_not_centered_on_via`, `tuning_profile_track_geometries`.
**`warning`:** `copper_sliver`, `courtyards_overlap`, `drill_out_of_range`, `duplicate_footprints`, `extra_footprint`, `footprint_symbol_field_mismatch`, `footprint_symbol_mismatch`, `footprint_type_mismatch`, `hole_clearance`, `hole_to_hole`, `holes_co_located`, `isolated_copper`, `lib_footprint_issues`, `lib_footprint_mismatch`, `mirrored_text_on_front_layer`, `missing_tuning_profile`, `net_conflict`, `nonmirrored_text_on_back_layer`, `padstack`, `pth_inside_courtyard`, `solder_mask_bridge`, `text_height`, `text_thickness`, `track_width`, `unconnected_items`, `via_dangling`.
**Everything else `error`**, notably `clearance`, `connection_width`, `copper_edge_clearance`, `annular_width`, `track_angle`, `track_dangling`, `tracks_crossing`, `shorting_items`, `starved_thermal`, `zones_intersect`.

- Never downgrade `track_angle`, `track_dangling`, `tracks_crossing`, `clearance`, `starved_thermal` or `zones_intersect`.
- Never import severities from another project (that devboard project's severity set leaves clearance at warning and ignores edge clearance, annular width, drill range, mask bridges and invalid outlines).
- Resolve false positives with per-instance `drc_exclusions` (courtyard / footprint-type / PTH-in-courtyard only); never by lowering a rule.

### 1.4 ERC severities

**`ignore`:** `footprint_filter`, `footprint_link_issues`, `four_way_junction`, `lib_symbol_issues`, `lib_symbol_mismatch`, `net_not_bus_member`, `pin_to_pin`.
**`error`:** `pin_not_connected`, `pin_not_driven`, `power_pin_not_driven`, `missing_power_pin`, `wire_dangling`, `label_dangling`, `unannotated`, `duplicate_reference`, `single_global_label`, `undefined_netclass`, bus conflicts, unit mismatches.
**`warning`:** the rest (`endpoint_off_grid`, `hier_label_mismatch`, `no_connect_*`, `similar_*`, `missing_*_pin`, …). Copy the 12 × 12 `pin_map` verbatim from the template.

### 1.5 Defaults, zones, teardrops, tuning **[MEASURED, REVIEW Q-03/Q-15]**

- Text/line defaults: silk 1.0 × 1.0 / 0.1, line 0.1; fab 1.0 / 0.15, line 0.1; copper 1.5 / 0.3, line 0.2; courtyard 0.05; outline 0.05. All `apply_defaults_to_fp_*` false.
- Zone defaults: clearance 0.1, min thickness 0.25, thermal relief (gap 0.5, spoke 0.5), remove islands always, min island 10 mm², hatch-edge outline 0.5, no external fillets.
- Teardrops: configured but **off** unless the project parameters allow them.
- Tuning patterns: **corner style chamfer (straight corners)**, amplitude 0.2–1.0 mm, spacing 0.6 (1.0 for pairs). Boards carry zero arcs.

### 1.6 BOM, plot, local settings

- BOM preset fields: Reference, LCSC, Value, Datasheet, DNP, Exclude from BOM/Board, Footprint, AqtechPN, Description, #, VOLTAGE - SUPPLY, Qty; grouped by Value/DNP/Exclude/Footprint; sorted by AqtechPN; CSV.
- Gerber: X2 attributes on, job file on, no Protel extensions, DNP sketched and crossed out on Fab, black and white.
- `.kicad_prl`: `auto_track_width` true.

---

## 2. Custom rules (`.kicad_dru`)

The golden project has **no `.kicad_dru`**; all constraints live in Board Setup and are enforced by Section 0 and Section 1. Do not create one unless the user asks. If asked, restate the Board Setup values and add nothing new.

---

## 3. Physical routing geometry (`.kicad_pcb`)

### 3.1 Stackup and layer roles

- 4-layer, 1.6 mm, FR4 εr 4.5: F.Mask 0.01 | F.Cu | prepreg 0.10 | In1.Cu | core 1.24 | In2.Cu | prepreg 0.10 | B.Cu | B.Mask 0.01. Copper per Section 0.2 (outer 35 µm, inner 17.5 µm on JLCPCB 4L-1oz).
- Layer roles are those of Section 0.3 and are immutable for 4 layers. Declare In1/In2 as layer type `power`.
- `tenting front back`, `pad_to_mask_clearance 0`, no mask bridges in footprints, `copper_finish` left as "None".
- Board outline: one closed shape on Edge.Cuts, stroke 0.05. Set `grid_origin`. All components on F.Cu unless the user asks.
- Signals on F.Cu and B.Cu only. A `segment` on any In*.Cu is FAIL.

### 3.2 Trace geometry: orthodiagonal only **[MEASURED]**

Golden: 6641 / 6644 segments on the exact 0/45/90/135° lattice; 3858 mitred corners vs 241 right angles.

- Every segment satisfies `atan2(dy,dx) mod 45° == 0` within 0.01°. Off-lattice is FAIL.
- Prefer 45° mitres; a 90° corner only where a mitre is geometrically impossible inside a pad field.
- **Zero arcs.** Never emit `(arc …)`; never draw curves or free-form traces; length-tuning meanders use straight corners. Any arc is FAIL. **[REVIEW Q-03]**
- No zero-length segments; merge collinear same-width joints.
- F.Cu is the primary layer; drop to B.Cu only to cross, and return (0-or-2 via pattern covers 81 % of golden signal nets).

### 3.3 Track widths **[MEASURED → netclass]**

Golden usage, now the guide for class widths: 0.2 all signals · 0.1 BGA escape only (within 2.5 mm of a 0.5 mm-pitch field) · 0.5 ±15 V rails and regulator nodes · 0.6 +5 V branches · 0.8 LED/diode/inductor nodes, +5V_POF · 1.0 +5 V trunk · 1.5 relay contacts · 2.0 power entry.

- Widths come from the netclass (Section 1.2). Never hand-set.
- Change width only at a pad, via or corner, never mid-straight.
- Below the profile's `min_track_width` is FAIL; below 0.2 mm outside a BGA escape is FAIL.

### 3.4 Keepout / rule-area avoidance **[POLICY, REVIEW Q-10]**

- Never let a segment or arc intersect or enter a track keepout on its own layer — FAIL. Never leave a track endpoint inside one. Via centres stay outside via keepouts.
- Bypass a keepout **on the same layer** with orthodiagonal segments around its perimeter. Passing under it with a via pair is decided per project (`keepouts.layer_change_allowed`, default false → WARN).
- When parsing, test every same-layer segment against every keepout polygon (segment–edge intersection plus point-in-polygon on both ends).

### 3.5 Pad entries: single straight perpendicular segment to the pad centre **[MEASURED, REVIEW Q-01/Q-02]**

Golden: 2989 endpoints exactly on pad centres; entry direction 0° 46 %, 90° 34 %, 45° 20 %.

- Terminate on the exact pad centre (`fp.at + rotate(pad.at, fp.rot)`), matched to 1 µm.
- One straight entry segment, parallel or perpendicular to the pad axis, ≥ 0.2 mm long, no wider than the pad's smaller dimension. 45° entries into rectangular pads are tolerated up to 25 % of entries (INFO), warned above that.
- **No neckdown**: the entry keeps the class width of the run; where the pad is narrower than the run, step down once at the last corner ≥ 1 mm before the pad, never mid-straight.
- **No staircase**: no two consecutive sub-0.3 mm segments within 1 mm of the pad.
- Off-centre entries only as secondary, on-axis entries into pads ≥ 2 mm after the primary entry is centred.

### 3.6 Vias **[MEASURED, REVIEW Q-05/Q-06/Q-11]**

- Through F.Cu–B.Cu only; no blind, buried or micro vias. Stack from the netclass or a predefined size; anything else FAIL. Every via ≥ the fabricator profile (hole, diameter, annular).
- `remove_unused_layers yes` and `keep_end_layers yes` on every via — **missing is FAIL**.
- Track endpoints equal the via centre to 1 µm (golden: 1988 exact, 1 miss).
- Hole-to-hole ≥ the project rule (fabricator limit). Golden minimum 0.296 mm.
- No via inside an SMD pad, except same-net thermal vias in exposed/heatsink pads of parts listed in the project parameters, assessed per chip datasheet.
- Every GND/power pad drops into its plane through an adjacent via with track on one layer only (golden: 1059 such vias). `free` vias only for stitching.
- Via budget per signal net is a project parameter (`via_budget`); the golden histogram suggests 2 for fast nets.

### 3.7 Differential pairs and length matching **[MEASURED, REVIEW Q-07/Q-08]**

- Name pairs `_P/_N`. Coupled runs at the class width and gap (Default 0.2 / 0.25 = 0.45 mm centre spacing); both legs on the same layer; split only for the last segment into each pad.
- Golden intra-pair mismatch: SerDes and SFP TD 0.00 mm, SFP RD ≤ 1.5 mm, ADC pairs unmatched (analog).
- Length-matching groups, spread limits and clock rules are **project parameters** (`length_groups`), decided per bus. Golden reference spreads: SD/eMMC 2.7 mm, RGMII 7–11 mm.
- Tune with straight-corner meanders only (Section 3.2).

### 3.8 Copper zones **[MEASURED]**

- Every zone has a net. Outline `hatch edge 0.5`. Thermal reliefs, gap 0.5 / spoke 0.5, clearance 0.1 (0.05 for small LC-node islands). `min_thickness` 0.1 inner planes / 0.25 outer pours / 0.05 small islands. `filled_areas_thickness no`. Solid fill.
- Priorities: the layer's largest plane lowest, each island cut into it strictly higher, local LC-node islands highest (golden 11–12), outer pours 14–17. Overlapping zones of different nets never share a priority.
- Solid pad connection only on mounting-hole pads and heatsink pads (`zone_connect 2`).
- In1.Cu = one GND zone; In2.Cu = power zones (Section 0.3).

### 3.9 Footprints, silkscreen, fabrication layers **[MEASURED, REVIEW Q-14]**

- Custom footprints in a project-local `.pretty` via `${KIPRJMOD}`; KiCad library parts with roundrect ratio 0.25; 3D model on every footprint.
- Mechanicals (holes, fiducials, logos, panel connectors) `exclude_from_bom`; non-placed `exclude_from_pos_files`; connectors and mechanicals locked. DNP on both symbol and footprint (golden 89 = 89).
- References hidden on silkscreen unless the project parameters say otherwise (third-party assembly). Silkscreen carries functional labels only (connector names, 1.0–2.0 mm, 0.1524 stroke) and logos. Values on F.Fab hidden.
- 4 fiducials (0.5 mm, 1 mm mask), M3 3.2 mm mounting holes. Never place text on Edge.Cuts.

---

## 4. Schematic best practices (`.kicad_sch`) **[MEASURED]**

- Root sheet holds only sheet symbols and their interconnect (golden: 18 sheets, 0 components). Inter-sheet signals use **hierarchical labels with the correct direction and sheet pins; zero global labels**. Power via power symbols only.
- **Every unused IC, connector and module pin carries a `no_connect`** (golden 321). `pin_not_connected` is an ERC error. No flags dangling or on wired pins.
- `PWR_FLAG` on every externally driven rail (golden 23).
- Labels and text 1.27 mm; wires default width; explicit junctions; 50 mil connection grid.
- Mandatory fields: Reference, Value, Footprint, Datasheet, Description, `LCSC` (purchasable parts), `AqtechPN` (stock items).
- Repeated blocks are separate sheet files with unique annotation; sheet paper sized to content (A1 root, A2–A4 children).
- Custom symbols in the project-local `.kicad_sym`.

---

## 5. Verification procedure

1. **Gate**: `kicad_golden.project.json` carries `fabricator.layers` / `copper`; every Board Setup rule ≥ the profile; copper layer count equals the profile; 4-layer roles as in 0.3. Any miss is FAIL (`pre-flight`, `stackup-order`).
2. Parse the board as an s-expression tree; count segments per layer (inner layers must be 0).
3. Angle lattice on every segment; **any arc is FAIL**.
4. Netclass resolution per net (assignment → pattern → priority); widths vs class (WARN), via stacks vs class or predefined (FAIL), via drill vs profile.
5. `remove_unused_layers` / `keep_end_layers` on every via (FAIL); via centring; hole-to-hole vs rule; via-in-pad vs approved parts.
6. Pad entries: exact centre, angle, length, width, staircase.
7. Keepouts: same-layer intersection (FAIL); via pairs under a keepout (WARN unless allowed).
8. Diff pairs and length groups per project parameters.
9. Zones: net, hatch, thermal, thickness, priorities; In1 GND / In2 POWER.
10. Footprints, silkscreen policy, Edge.Cuts and copper-to-edge vs rule.
11. Settings vs template (rules, severities, netclasses, tuning corner style).
12. Schematic: global labels, no_connects, PWR_FLAG, label size, LCSC, DNP parity.

Acceptance: audit exit 0; every remaining WARN justified in writing; KiCad DRC/ERC clean with the golden severities.

---

## 6. One-page checklist

- **First, always**: ask layer count and copper weight; load the JLCPCB profile; run `apply_settings.js --fab jlcpcb --layers N --copper …`; fix the stackup copper; for 4 layers keep Top S | In1 GND | In2 POWER | Bottom S.
- Define netclasses and patterns for every rail and bus before the first track; never hand-set widths.
- Route on F.Cu / B.Cu only, 0/45/90/135° lattice, mitred corners; zero arcs, zero teardrops (unless allowed), no curves.
- Vias from the netclass, through-hole only, unused layers removed, hole-to-hole per fabricator; no via-in-pad except approved thermal pads.
- End tracks on the exact pad and via centres; one straight perpendicular entry, no neckdown, no staircase.
- Route around same-layer keepouts; never cross them.
- Diff pairs `_P/_N` at the class width/gap; length targets and via budgets from the project parameter file.
- Zones thermal 0.5/0.5, hatch-edge, unique priorities; solid connection only on holes and heatsink pads.
- Hide references, functional silkscreen only; DNP on symbol and footprint; mechanicals out of the BOM; `LCSC` and `AqtechPN` populated.
- Hierarchical labels only; `no_connect` on every unused pin; `PWR_FLAG` on external rails.
- Run the audit; exit 0 or not done. Never add a `.kicad_dru`, never lower a rule below the fabricator, never import another project's severities.
