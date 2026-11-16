# Review decisions (2026-09-16)

_Outcome of the specialist review of SPEC-KICAD-GOLDEN rev A, Section 17. Source: `20260916_KiCad_Golden_Spec_Review_Points_FilledForm.docx` plus the netclass package `a devboard settings export` (extracted from `a 6-layer devboard project`). Each row records the reviewer's answer verbatim in substance and how the skill implements it. Skill version 1.2.0._

| Q | Topic | Reviewer's decision | Implementation |
|---|---|---|---|
| Q-01 | Pad-entry angle (PAD-02) | "The current tolerance is right." | Unchanged: 45° entries into rectangular pads are INFO; WARN above 25 % of entries. |
| Q-02 | Off-centre power entries (PAD-01/06) | "The 2 mm threshold is appropriate." | Unchanged: secondary on-axis entries allowed on pads ≥ 2 mm; everything else WARN. |
| Q-03 | Arcs from tuning (RTE-03) | Require straight-corner meanders so the board has **zero arcs**. | **Any track arc is FAIL.** `golden_settings.json` sets tuning `corner_style` to 2 (chamfer) for single track, diff pair and skew. Verify the label reads "Chamfer" in Board Setup → Length-tuning patterns after applying. |
| Q-04 | Single netclass (NCL-01) | "We will not hand-set the track widths anymore. We will define the netclasses prior to the routing process." Netclass table supplied. | Template now carries the six classes and eight name patterns from the table (see below). Audit resolves each net's class with KiCad semantics (assignment → pattern → priority, lower wins) and checks track width against the class width (WARN if different, unless a predefined width or a BGA escape) and via stack against the class via or a predefined via size (FAIL otherwise). `apply_settings.js` inserts/replaces template classes and adds missing patterns, keeping the project's own. |
| Q-05 | Via-in-pad exception (VIA-05) | Do not forbid for exposed pads; assess case by case per chip. | Same-net vias in exposed/heatsink pads are allowed only for reference designators listed in the project parameter `via_in_pad.allowed_refs`; others FAIL. Reported as INFO with "assess per chip datasheet". |
| Q-06 | Unused-layer removal (VIA-02) | "It should be labeled as FAIL." | Missing `remove_unused_layers`/`keep_end_layers` on a via is **FAIL**. |
| Q-07 | RGMII matching (DIF-07) | Case by case per bus specification. | Length groups are **project parameters** (`length_groups[]` with regex, `max_spread_mm`, clock rule). No fixed number in the standard. Template file carries the reference board values as an example. |
| Q-08 | SD/eMMC relation (DIF-06) | Case by case per bus specification. | Same mechanism; `clock_rule` is `shorter_or_equal`, `within_spread` or `none` per group. |
| Q-09 | Signal via budget (VIA-08) | Case by case per bus specification. | Project parameter `via_budget` (fast-net regexes, caps). WARN when exceeded; no default cap. |
| Q-10 | Keepout bypass (KEE-02) | Case by case. | Crossing a keepout on its layer stays FAIL. A via pair used to pass under a keepout is WARN only when `keepouts.layer_change_allowed` is false (default). |
| Q-11 | Minimum via spacing (VIA-04) | Manufacturer specs govern. | Spacing is now judged as **hole-to-hole against the project rule** `min_hole_to_hole` (or the fabricator value in params), not a fixed 0.45 mm centre distance. |
| Q-12 | Copper-to-edge (CON-03) | Manufacturer specs govern. | Edge clearance is read from the project rule `min_copper_edge_clearance` (or params). Deviations of rules from the template are WARN with the note "acceptable only if it reflects the fabricator's capability". |
| Q-13 | Stackup and impedance (STK-01) | Depends on project specs. | `stackup_reference` in project params; echoed in the report. Inner-copper 35 µm flagged for fabricator confirmation. |
| Q-14 | Hidden silkscreen references (FPT-05) | Intended for most boards; project may differ. | `silkscreen.references_hidden` parameter (default true). WARN either way when the board disagrees with the parameter. |
| Q-15 | Teardrops | Specified per project. | `teardrops.allowed` parameter (default false). Teardrops present while not allowed → WARN. |

## Adopted netclass table (verbatim from the reviewer's package)

| Netclass | Priority | Track | Clearance | Via ø / drill | µVia ø / drill | Diff pair w / gap |
|---|---|---|---|---|---|---|
| Default | — | 0.20 | 0.10 | 0.45 / 0.15 | 0.45 / 0.15 | 0.20 / 0.25 |
| POWER_DC | 0 | 0.60 | 0.10 | 0.60 / 0.30 | 0.60 / 0.30 | — |
| POWER_AC | 1 | 1.50 | 3.00 | 0.60 / 0.30 | 0.60 / 0.30 | — |
| BUS_SDRAM_CONTROL | 2 | 0.20 | 0.10 | 0.45 / 0.15 | 0.45 / 0.15 | — |
| BUS_SDRAM_ADDR | 3 | 0.20 | 0.10 | 0.45 / 0.15 | 0.45 / 0.15 | — |
| BUS_SDRAM_DATA | 4 | 0.20 | 0.10 | 0.45 / 0.15 | 0.45 / 0.15 | — |

Name patterns: `+1.2V`, `+2.5V`, `+3.3V`, `+5.0V`, `+24V`, `GND` → POWER_DC; `*SDRAM0*`, `*SDRAM1*` → BUS_SDRAM_ADDR. The empty pattern in the source was dropped. Predefined extra sizes: tracks 0.1 · 0.13459 · 0.2 · 0.3 · 0.45 · 0.8 · 1.0; vias 0.45/0.2 and 0.6/0.4; diff pair 0.2 / gap 0.2 / via gap 0.25.

`BUS_SDRAM_*` classes are project-specific examples of "one class per bus group"; new projects rename them for their own buses. `POWER_AC` (3.0 mm clearance) is the mains-separation class and has no pattern; assign its nets explicitly.

## Second pass over that devboard project's settings package (2026-09-17, skill 1.2.1)

The same `a devboard settings export` was resubmitted as "more info used on other projects". Beyond the netclass table already adopted, four things were taken from it:

| Item in the package | Adopted as |
|---|---|
| In1.Cu and In2.Cu declared as layer type `power` (golden: `signal`) | Recommendation in 02 §3.1 and an audit INFO when plane-only inner layers are typed `signal`. The import-source board in `templates/import_source/` carries the `power` typing. |
| README procedure: Board Setup → "Import Settings from Another Board…" | Documented in `SKILL.md` as the no-script path. `templates/import_source/Golden_Import_Source.kicad_pcb/.kicad_pro` is a minimal project generated from `golden_settings.json` for exactly that dialog. |
| The configuration report (docx) | `scripts/settings_report.js`: Markdown report of any project's stackup, rules, netclasses, patterns, predefined sizes, zone/teardrop/tuning defaults and non-error severities, with `--diff` against the golden template. Use it to review other projects' settings without a board. |
| `solder_mask_min_width 0.1` in the board setup | Recorded as a fabricator-dependent value in the parameter template (`fabricator._alternatives`). Not enforced. |

**Deliberately not adopted** — that devboard project's severity set. It downgrades `clearance`, `connection_width`, `track_dangling`, `missing_footprint` to warning and ignores `copper_edge_clearance`, `annular_width`, `drill_out_of_range`, `solder_mask_bridge`, `invalid_outline`; its own report lists five of these as the checks that most often precede fabrication rejection. The audit's settings comparison and the report's "checks not at error" note both flag such imports. Never tick "Severities" when importing from a project other than the golden import source.

**Fabricator-dependent values observed there** (candidates when a fabricator's sheet asks for them, not standard): hole clearance 0.20, hole-to-hole 0.20, via annular 0.125, silk clearance 0.15, min text 1.0 × 0.153, mask-to-copper 0.09, zone min clearance 0.05, mask min width 0.1. Also present: tuning corner style 1 (round) — superseded by Q-03; teardrops enabled on vias and pads — superseded by Q-15 (per project).

## Rev C — mandatory pre-routing gate (2026-09-17, skill 1.3.0)

Requested by the owner after the review: the standard became an interactive workflow. Before any `.kicad_pcb` edit the agent asks **layer count** (2/4/6) and **copper weight** (1 oz/2 oz), loads the matching JLCPCB profile from `fabricators/jlcpcb.json`, runs `apply_settings.js --fab jlcpcb --layers N --copper …` (rules = stricter of golden and JLCPCB), and for 4 layers keeps the immutable order **Top Signal | In1 GND | In2 POWER | Bottom Signal**. The audit gates on it (`pre-flight`, `stackup-order`).

Findings produced by the gate on the golden board itself (4L-1oz profile): four rules sit below the captured JLCPCB minimums — `min_hole_clearance` 0.15 < 0.254, `min_hole_to_hole` 0.25 < 0.254, `min_text_height` 0.7 < 1.0, `min_text_thickness` 0.08 < 0.15 — and the stackup declares 35 µm inner copper where the profile delivers 17.5 µm. `--fab` raises the four rules; the copper must be corrected in the stackup editor. Also noted: the profile allows a 0.15 mm via hole on 4-layer, so the open conflict below can be settled with `--fab-exact` if the owner accepts the fabricator's full capability.

## Rev P — the improvements review (2026-09-25, skill 1.16.0)

Eleven items collected from routing BladeOne 0.1 by hand and sent to the skill's maintainer,
rewritten as rules and implemented. Full text, images and the reviewer's own test results are in
`CHANGELOG.md` 1.16.0; this table is the short form.

| Q | Topic | Decision | Implementation |
|---|---|---|---|
| Q-16 | Shared pad gaps (improvements #6) | Ask; default no. | New pre-routing question in §0. `shared_pad_gaps.allowed` in project params. A gap with 2+ tracks is FAIL when not allowed, WARN when it is. |
| Q-17 | Plane-net pad exceptions (improvements #7) | Pad-to-pad surface links on a plane net are always wrong; a pad with no room for its own via is the only exception, and it must be named with a reason. | `plane_net_exceptions.allowed` in project params, audited as INFO; everything else is FAIL. `route_freerouting.py` filters plane nets out of the DSN by default so the router cannot create the link in the first place. |
| Q-18 | Detour limits (improvements #10) | Go around a component unless the detour costs a via or exceeds the limits. | `detour_limits` in project params (default 50 % / 10 mm, whichever is smaller governs, no added via). Remaining under-part tracks are WARN with the detour length that would have been needed. |

Superseded by this review: **Q-01 and Q-02 no longer apply.** The old tolerance (45° entries into
rectangular pads up to 25 %, off-centre secondary entries allowed on pads ≥ 2 mm) is replaced by
improvements entries 8 and 9 — one straight 8-direction entry ending exactly at the pad centre, axial
preferred on elongated pads, no exemption for large pads. Q-04's pad-entry width limit is tightened by
entry 5 (neck to the pad's smallest dimension inside the clearance area, now FAIL not WARN). D3's
"do not daisy-chain GND pads on the surface" is promoted from an unenforced decision-rules note to a
Core rule with an audit FAIL (entry 7).

**Not fully closed by automation** (see the test-results table in `CHANGELOG.md` 1.16.0): entries 3, 4
(centring), 5, 6, 8, 9 and 11 needed new tooling that did not exist before this rev, and entry 10's
keepout approach failed outright in testing. `scripts/geometry_finish.py` handles the common single-
segment topology for each and reports the rest — see SKILL.md §Post-Routing Geometric Refinement for
what to expect and what not to.

## Open conflicts to settle (not decided by the review)

1. **Via drill 0.15 mm vs minimum through-hole 0.20 mm.** The table's Default and BUS classes use a 0.15 mm drill; the constraint set (kept from the golden board, and identical in the reviewer's project) sets `min_through_hole_diameter` 0.20. KiCad flags this as `drill_out_of_range`. The audit reports it as WARN on every board until one side is changed with the fabricator's capability in hand (JLCPCB allows 0.15 mm on 4-layer; the golden board was built with 0.20).
2. **The golden board itself no longer passes.** Under 1.2.0 it audits FAIL 488: 74 arcs (Q-03), 410 vias without unused-layer removal (Q-06), plus the four defects known since rev A. Its single-netclass, hand-set widths produce 316 width WARNs. It remains the geometry reference, not a settings reference.
3. **BUS_SDRAM_CONTROL / BUS_SDRAM_DATA** receive no nets by pattern in the source project (flagged in the reviewer's own report). Add patterns when these classes are used.
