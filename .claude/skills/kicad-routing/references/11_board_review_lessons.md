# 11. Board review lessons (ServiceOne rev. 0.2 review, Vladimir Duk, 2026-10-19/23) — skill 1.20.0, sections 8-10 in 1.27.0 / 1.28.0

Source: ServiceOne `reports/board_review_rev02.md` (21 issues on the routed main board, with a lessons table).
Audit checks are numbered sections 19-29 of `kicad_audit.js` plus stricter rules in sections 6, 7, 13 and 16;
the synthetic fixture `tests/fixtures/review2.kicad_pcb` fires each of them. Every
lesson is now a rule of this skill. This file maps each one to its enforcement:

- **audit**: a check in `kicad_audit.js`;
- **script**: a change in a shipped script;
- **playbook**: a step in `08_routing_playbook.md`, Addendum B;
- **stage 2**: a new tool, planned and not shipped yet. The rule still applies and is checked by hand.

Read the rules as normative. The ServiceOne numbers are observations from one board.

## 1. Finishing and file handling

| # | Rule | Enforced by | Issue |
|---|---|---|---|
| L1 | A script that edits copper refills the zones **and saves the refilled board**. DRC `--refill-zones` and the Gerber `--check-zones` refill in memory only, so they hide a stale saved fill | script: board-writing scripts refill before saving; `zone_fill_check.py [--fix]` compares the saved fill with a fresh fill | 1 |
| L2 | Run KiCad *Tools > Cleanup Tracks and Vias* as a finishing step. Settings: delete tracks connecting different nets **on**; delete redundant vias **off** (stitching, thermal and ESD vias stay); delete vias connected on one layer **off** (plane vias); merge co-linear tracks **on**; delete tracks unconnected at one end **on**; delete tracks fully inside pads **off** (1.28.0, L44: it removes the stub that carries a track to the exact pad centre); refill zones **off**. Then gate the result (`audit_gate.py` / `stage_gate.py`) | playbook E-finish | 2 |
| L3 | Never save a board loaded from a copy that has no `.kicad_pro` beside it: pcbnew writes default rules into a project | script: `board_guard.py` in every board-writing script | release |
| L4 | Check for KiCad lock files before a script writes the board | script: `board_guard.py` | release |
| L5 | After any change to a net with a Kelvin sense line, re-run `layout_measure.py check` **inside the finishing loop**, not only at release. Three gated routes on ServiceOne joined a sense trace to its load copper; `repair_import.py --declang` then deleted the rest of the sense line as a dead branch | script: `finish_gated.py` reverts any route that breaks a passing layout check (`--no-layout-gate` to disable); playbook: rebuild Kelvin lines by hand / `route_finish.py --exclusive` **before** trimming dead ends | release, D117, D124 |
| L6 | *Update PCB from Schematic* can rename an unconnected net shared by two pins (`unconnected-(SW1-MP-PadMP1)` -> `_1`), and DRC then reports a short. After every update, check renamed `unconnected-` nets | playbook A5 | B-5 |
| L7 | `apply_settings.js` must not overwrite approved project deviations (for example `min_hole_clearance` 0.2 after D110). List them in `approved_rule_deviations` of `kicad_golden.project.json`; the script keeps them, or refuses when one is below the fabricator's absolute minimum | script: `apply_settings.js`, templates, `init_project.py` | D110 |
| L8 | Use the fabricator's **price tiers**, not only its minimums: on JLCPCB 4-layer a via drill below 0.2 mm costs extra. The economical tier is the default; finer vias need an explicit approval. Settle every open fabrication choice before the release, not on the order page | script: `fabricators/jlcpcb.json` `economical_via_drill_mm`, `apply_settings.js`; audit: via drill below the tier is FAIL unless `fabricator.fine_vias_approved` | 11 |

## 2. Pads and pad entries

| # | Rule | Enforced by | Issue |
|---|---|---|---|
| L9 | At a fine-pitch pad a track is no wider than the pad: neck down before the pad and widen only after the pin row. A round track end must not stick out of the pad outline. DRC flags neither case | audit `pad-entry` (§19: every track end inside a same-net pad; rectangle, circle and oval pads; custom pads skipped) | 3, 5 |
| L10 | At pitch ≤ 0.65 mm a pad-entry finding is a **defect to fix, never a deviation**. The track arrives on the pad axis from the outer end. Finishing moves the whole last segment onto the axis instead of adding a jog inside the pad | audit `pad-entry` FAIL at fine pitch; `route_finish.py` (1.23.0): axial stubs on every pad end, `--refinish REF.PAD` realigns an existing entry | 6 |
| L11 | Every pad, passives included, is entered straight along its axis into the pad centre. The last bend sits at least 0.5 mm from the pad edge; a diagonal corner entry is a defect | audit `pad-entry` (§7: non-axial entry is FAIL for every rectangular pad, round pads exempt; a bend closer than 0.5 mm beyond the pad edge is FAIL unless the far end is a via or a same-net pad); `route_finish.py` (1.23.0) ends each pad route in an axial stub to pad edge + 0.5 mm, no wider than the pad | 18 |
| L12 | Each plane pin of an IC gets its own via, straight on its pin axis. No tracks crossing between pins, and no ground loop around a neighbouring supply pin (U202: GND pin 6 looped round VEE pin 7 into pin 8) | audit `geometry` FAIL (§21: same-net segments on one layer crossing away from their ends), existing plane-net check | 7 |

## 3. Vias

| # | Rule | Enforced by | Issue |
|---|---|---|---|
| L13 | At fine-pitch ICs, plane vias use the small via (0.45 / 0.2). It fits closer to the pin, and a shorter stub matters more than the via size. The netclass via (0.6 / 0.3) is for high-current, thermal and ESD paths | audit `via` WARN (§20: a plane-net via within 1.5 mm of a pad at pitch <= 0.65 mm, larger than the smallest predefined via not below the economical drill; INFO when already that size) | 4 |
| L14 | Vias go outside the body of two-pad parts when there is room. A via between the pads of a passive is a last resort: tombstoning, trapped solder and flux, no inspection or rework | audit `via` FAIL (§22, "own-pad" or "other-net") | 9 |
| L15 | Same-net via rings keep a solder-mask web of at least 0.15 mm from SMD pads | audit `via` FAIL (§23: ring < 0.15 mm from any SMD pad edge, same net included; vias with the centre inside a pad are left to via-in-pad; approved thermal vias skipped); stage 2: stub / stitch scripts place vias at pad edge + 0.15 mm + via radius | 10 |
| L16 | No via inside an IC pad-row band: from the inner pad ends to 0.5 mm beyond the outer pad ends, between adjacent pins. Vias go outside the row, or under the body between the rows when there is no exposed pad | audit `via` FAIL (§26: U* / IC* parts with >= 6 pads, rows of >= 3 equal pads at a uniform pitch, not an exposed pad split into same-number pads; since 1.22.0 a via whose copper reaches the band counts, as in KiCad's DRC); `pad_row_keepouts.py` (1.22.0) writes "no vias" rule areas over every band - `--write` on the real board, `--export-copy` / `export_keepouts.py --pad-row-bands` for Freerouting (DSN via_keepout) | 16 |

## 4. Tracks

| # | Rule | Enforced by | Issue |
|---|---|---|---|
| L17 | One track per gap between THT / DIP pins, even where the project allows two. Keep set-point and analog lines out of gaps next to PWM or clock pins. The shared-gap exception is allowed only where no free neighbouring gap exists | audit `shared-gap` (§16: the message names a neighbouring gap of the same pin row with no track; WARN for `allowed_parts`, FAIL otherwise) | 8 |
| L18 | The autorouter leaves detours that go up and come back down; the finishing pass straightens them | audit `detour` WARN (§24: ratio > 1.8 over 3 mm, a U-turn > 135°, or a "bump" that leaves and returns >= 0.2 mm sideways); playbook: straighten with the interactive router (drag + optimise) | 12 |
| L19 | The router can leave duplicate parallel copper of one net (a loop). KiCad's Cleanup merges co-linear pieces only | audit `loop` FAIL (§25: cycles in a net's track graph — vias join layers, a segment running over a same-net pad joins it; near-parallel duplicates < 0.3 mm apart over > 0.5 mm) | 14 |
| L20 | A between-pads (centring) finding is a defect to fix, never a deviation. The check covers every track that passes between the pins of a footprint | audit `between-pads` (§16: every mutually nearest facing pair of flanks is its own gap — the old single-nearest-flank search missed U102 pins 10/11 and J3 pins 8/9; synthetic U40/TP41 test) | 15 |
| L21 | Routing through any pin array (connectors, DIP, SOIC / SOP, QFP / QFN fan-out, rows of PTH pins, pads, test points, vias): inside the array a track runs on the centreline of the channel between two rows or columns, orthogonal to them, with 45° corners only where it turns. No long diagonals across the array. A wide power track that would block a signal channel goes on the other layer | audit `pin-array` FAIL (§29: THT footprints with a full regular grid >= 2x3; diagonal longer than `pin_array.max_diagonal_pitch_fraction` x pitch, default 0.5 (Celso, 2026-10-20: the review's "one pitch" let 8 of the 9 J1 diagonals through); `pin_array.include_smd` optional); 1.24.0: an orthogonal run in a channel wider than 1.5 mm whose clearances to the pads on each side differ by more than 0.02 mm -> FAIL `pin-array` "off-centre", centred by `center_gaps_safe.py` / `centre_gated.py` (narrower gaps are `between-pads`) | 21 |
| L22 | An IC fan-out is laid out as a pattern: axial exits, bends aligned on one line per side, equal spacing between parallel tracks | playbook; audit `fan-out` WARN (§31, 1.24.0: per pad row, tracks that leave axially and bend the same way; first bends more than 0.1 mm apart); `fanout_regularise.py` aligns them (slide, else re-route with axial stubs) | 19 |

## 5. Planes, mechanics, models

| # | Rule | Enforced by | Issue |
|---|---|---|---|
| L23 | **Plane plan** is a new step after placement and before routing: the power planes are planned, not taken as given. Claude prepares a power map per rail and a trade-off table; the designer decides or draws the outlines; the decision is stored as `plane_plan`. The map covers pad clusters, current, voltage, candidate islands with the pads they serve, adjacent-layer crossings, main-plane continuity, neck width and sense nets. Rules: never split GND; the gap depends on the voltage; boundaries stay away from adjacent-layer signals (or get a stitching capacitor); keep a minimum neck width; sense-trace vias skip islands | playbook B7; `plane_plan.py map|apply|check` (1.21.0: proposal with trade-off table, zones, post-fill check: empty or isolated fill, main plane split, Kelvin, thin copper, crossings, pads without a via); audit §30 (undeclared island WARN, island on a never_split layer FAIL, adjacent-layer crossing WARN, clearance below gap_by_voltage FAIL, island serving < 2 pads WARN) | 13 |
| L24 | Every mounting hole and pillar contact gets a mechanical keep-out. Radius = the largest contact diameter / 2 + 0.5 mm: pillar, screw head, nut or washer. ServiceOne: H1-H4 r 4.0 (steel standoff hex / M3 washer), H5-H12 r 3.0 (post d 5.00). The contact diameters are a project input asked at setup, and the keep-outs are exported to Freerouting | audit `mech-keepout` FAIL (§27: tracks and vias of other nets inside `mechanical_keepouts` entries — refs or glob pattern, `radius_mm`, layers or "all"; zone fills not checked; INFO for an unlisted MountingHole*; 1.25.0: a hole footprint with its own keep-out rule area counts as covered); `mounting_hole_fp.py` (1.25.0) writes hole footprints that carry the keep-out; playbook A19; ServiceOne scripts `add_spacer_keepouts.py` / `clip_keepouts.py` as worked example | 17, D116, D124 |
| L25 | Every footprint gets a verified 3D model (position, rotation, height) at library setup, stored with project-relative paths | audit `model` FAIL (§28: no model unless `models_not_needed` / board-only / default exemptions — MountingHole, Fiducial, TestPoint, Logo, Symbol libraries, refs H*, FID*, TP*, LOGO*; a `${KIPRJMOD}`, relative or `${KICADn_3DMODEL_DIR}` file that does not exist); playbook A15d | 20 |
| L26 | Missing 3D models: search first (KiCad library, EasyEDA by LCSC code, manufacturer). For every part still without a model, the designer either finds one or lets Claude build an approximate box-and-pins model from the datasheet drawing, named `*_approx` and listed in the release note | audit `model` INFO lists `*_approx` models; `model_builder.py` (1.25.0: `spec` from the datasheet drawing, `footprint` from the F.Fab outline and pads, `--assign`); prototype ServiceOne `hardware/routing/model_tools/box_model.py` (its SW1 model rebuilt by `model_builder.py spec` is identical) | 20 |

## 6. ServiceOne result (audit 1.20.0, read-only, rev. D board)

Before / after: 269 FAIL / 797 WARN -> 1933 FAIL / 663 WARN. Every named review case is caught (C26, U202, Q302, U203,
J3 OUT1/OUT2_VSET, U102 10/11, U1 9/10, U8 10, SW3 -> R8, missing 3D models), including the J1 diagonals: 45° legs of about 2.47 mm,
shorter than the 3.5 mm pitch, so the default limit is half a pitch (`pin_array.max_diagonal_pitch_fraction` 0.5;
at one pitch only 1 of 9 is caught). Mechanical keep-outs: 12 holes, 0 violations. These are the rev. 0.2 work list.

## 7. Stage 2 (planned tools)

1. ~~`plane_plan.py` and the plane-plan audit checks (L23).~~ Shipped in 1.21.0. On the ServiceOne rev. D board
   (read-only copy) `map` In2.Cu proposes 9 islands; the +24V island under the MT3608 output (PP_P24V_1: D3,
   C39-C41, R57, TP21) has 2 U13 Kelvin sense vias at its edge, 3 Net-(Q3-S) crossings on B.Cu, 4 pads without
   their own via and a 0.29 mm sliver of +3.3V beside it; `check` after `apply`: 0 FAIL, 3 WARN, Kelvin still
   passes.
2. ~~Pad-row band keep-out generator (L16).~~ Shipped in 1.22.0 (`pad_row_keepouts.py`). On the ServiceOne rev. D
   board (read-only): 45 bands on 21 parts (the ESP32 module's 3 x 3 grid of pads "41" is no longer taken for 3
   rows); 45 vias reach a band - script, audit §26 and KiCad's DRC with the rule areas on a copy all give the same
   45 (the audit counted 31 by via centre; total 1933 -> 1947 FAIL).
3. ~~`route_finish.py` axial end-finishing: last segment on the pad axis, last bend at pad edge + 0.5 mm (L10,
   L11).~~ Shipped in 1.23.0: axial stubs on every `--from-pad` / `--to-pad` end, `--refinish`, `refinish_gated.py`.
   On the ServiceOne rev. D board (copy) `refinish_gated.py --max 30` kept 3, reverted 5, refused 23: audit FAIL
   1947 -> 1943, DRC and the 5 layout checks unchanged. A hand-gated run over another 30 pads kept 8 (FAIL -10).
   The refusals are placement work: a via inside the stub zone (pad edge + 0.5 mm), a pad axis blocked by other
   copper, no corridor without passing between foreign pads. `--block-courtyards` kept fewer (3 of 30).
4. ~~Fan-out regulariser and its audit WARN (L22); channel-centreline snap for pin arrays (L21).~~ Shipped in
   1.24.0. ServiceOne rev. D (copy): the audit finds 10 fan-out groups, 6 unaligned (U1 pins 6/7 at 0.10 and
   0.55 mm, the review's case). `fanout_regularise.py --apply` improved 3 of 5 movable groups (U2, U4 and U5).
   Audit FAIL went 1947 -> 1945 and fan-out WARN 6 -> 4, with DRC unchanged. Sliding alone fitted none: the
   runs are short or end in vias. U1's axis is blocked, U401 would duplicate copper, and U13's tracks are
   locked (Kelvin). The pin-array centreline check finds none: J1's channels are narrower than 1.5 mm, so
   `between-pads` covers them.
5. ~~Approximate 3D model builder (L26) and mounting-hole footprints that carry their keep-out (L24).~~ Shipped in 1.25.0
   (`model_builder.py`, `mounting_hole_fp.py`). With it stage 2 is complete: every lesson L1-L26 has its audit check,
   script or playbook step.

## 8. Rules enforced, not counted (ServiceOne D133 review, Vladimir Duk, 2026-10-22) — skill 1.27.0

Vladimir's review of the scripted ADC-region rework: the entries to U1 improved, but rules that were already defined
were broken. Measured against the board before the rework: 220 new FAILs (93 between-pads, 82 pad-entry, 31 via, 6
acute joints, and smaller groups), 32 open connections and 45 dangling stubs. Every scripted step had "passed",
because each gate compared only the board's total FAIL count, which fell from 1 932 to 1 795 when the rip-up removed
357 old FAILs. The lesson is about enforcement: a rule the audit checks still has to stop the change that breaks it.

| # | Rule | Enforced by | Issue |
|---|---|---|---|
| L27 | **A change to a routed board adds no audit FAIL.** Compare the findings of the board before and after the change, never the totals: on a revision in progress the board carries hundreds of known FAILs, and removing copper removes FAILs, so a falling total hides new defects | `audit_gate.py` (1.27.0: identity = check + message with the measured numbers blanked, counted; exit 1 lists the new FAILs); `finish_gated.py`, `centre_gated.py`, `refinish_gated.py` revert any kept change that adds one; playbook Addendum C, F2b | D133 review |
| L28 | **No acute joints.** Where tracks of one net meet on one layer, away from a pad centre or a via, two neighbouring branches are at least 90° apart: no 135° turn (interior 45°) and no T branch 45° off its run | audit `acute` FAIL (§32; before 1.27.0 only the trial tool `acute_scan.py` saw it, and §3 counted a 135° turn as a mitre); `route_finish.py` searches with its arrival direction, keeps it in the simplifier and refuses an acute route (exit 5, `--allow-acute` for experiments) | D133 review |
| L29 | **No hand-off with dangling copper.** Before a board goes to the interactive router, a reviewer or the fabricator, DRC `track_dangling` and `via_dangling` are 0; open connections left for someone else are listed with their ends, and the copper around them is clean | playbook Addendum C (hand-off); SKILL.md §The new-FAIL gate | D133 review |

ServiceOne result (audit 1.27.0, read-only, `rev02-adc-region` at 9176be8): 25 acute joints on the whole board, 14 of
them new in D133; `audit_gate.py` against the board before D133 (6e30d10): 209 new FAILs by identity, BLOCKED.

## 9. Finishing a routed board under the gates (ServiceOne rev. 0.2, Vladimir Duk and Claude, 2026-10-22/23) — skill 1.28.0

The rev. 0.2 fixes were made on a routed board with hundreds of known FAILs, by scripts gated per change (L27) and by
Vladimir with KiCad's interactive router. From Celso's hand-off to commit 397a6c8 the audit went 1818 -> 1455 FAIL
with 0 unconnected, and no scripted change added a FAIL. The lessons below came from that work: Vladimir's rules
(stop rule, orthogonal-first routing, Cleanup settings, locks) and what the gated passes taught. They were recorded in
the ServiceOne review document (`reports/board_review_rev02.md`, "Lessons for the kicad-routing skill") and are
folded in here. The scripts marked "shipped" were written during that work and generalised for 1.28.0.

| # | Rule | Enforced by | Source |
|---|---|---|---|
| L30 | **Stop rule for scripted finishing.** Estimate the run before starting it (items x attempts per item x time per attempt) and show the estimate to the designer when it is over 15 min. After the first 10 attempts or 30 min: when fewer than 1 in 5 attempts is kept, or the projected time exceeds the budget agreed with the designer (default 1 h), stop, report what was kept and why the rest failed, and hand the remaining items to the interactive router with a list of ends. ServiceOne D133: 3.5 h for 5 kept routes out of 74 attempts | `stop_rule.py` (shipped); `finish_gated.py`, `refinish_gated.py`, `gate_each.py`: `--budget MIN` (60), `--min-keep-rate R` (0.2), `--no-stop-rule` for experiments; `finish_gated.py` writes `<board>.finish_open.json` with the connections left | D133 finishing (Vladimir's rule) |
| L31 | **Route ends come from the copper, not from the DRC marker.** For a track, kicad-cli's unconnected-item position is not on the track, so a route to it ends on nothing (23 of 41 attempts reverted with no connection gained). Build the two copper islands of the connection and route between their nearest pad, free track end or via; pad ends pad-to-pad | `open_ends.py` (shipped: islands and ranked end pairs per open connection, also the hand-off list of L29); `finish_gated.py` already routes pad ends pad-to-pad (1.26.4); stage 3: `finish_gated.py` takes its ends from `open_ends.py` | D133 finishing |
| L32 | **Per-attempt gates must be fast.** A zone refill in every DRC costs minutes. Refill once per stage; per attempt, ignore only the violations against a zone fill. Attempt time fell to about 30 s | `finish_gated.py` (refills per attempt only for a net with a zone, where a via connects through the fill; full DRC with `--refill-zones` at the end; `--refill-every-attempt` restores 1.27); `stage_gate.py` / `gate_each.py` (refill check every 20 kept changes and at the end) | D133 finishing |
| L33 | **Classify dangling copper before removing it.** A lead-in (its free end is where an open connection continues) is kept and listed; an overhang (runs past the pad it connects) is trimmed, never deleted (deleting them broke 4 nets); an unused stub is removed whole. Deleting dangling stubs to convergence peeled unfinished nets back to their pads (112 segments, 30-46 mm gaps) | `dangling_classify.py` (shipped, with `open_ends.py`); `repair_import.py --delete track_dangling` must not be iterated on a board with open connections; the L29 hand-off allows lead-ins listed with their ends | D133 clean-up |
| L34 | **A fix that needs a neighbour moved is not forced.** Scan the legal spots first (copper clearance, mask web, hole-to-hole on the pad axis); no spot = a list item for the interactive router, not a forced move. ServiceOne: U8 pin 10 (axial entry blocked by a track and two vias), U202 pin 6 (pin 7's track under the body) | `via_spot.py` (shipped); playbook Addendum D, D2 | issues 3, 7 |
| L35 | **3D models from EasyEDA.** The EasyEDA STEP files are in the manufacturer's raw frame (J1 upside down below the board); the WRL from easyeda2kicad is aligned. Align a model to the footprint's F.Fab outline, not to the pad centroid. KiCad 10 renamed library models: a footprint path to a KiCad 9 name is a missing file | audit `model` (§28) flags missing files; playbook Addendum D, D6; stage 3: `model_builder.py` / library setup use the EasyEDA .wrl, offset from the F.Fab bounding box, check with `kicad-cli pcb render` (top and side) | issue 20 |
| L36 | **Git Bash rewrites an argument that starts with "/"** into a Windows path: the net `/Outputs/OUT1_RB_N` reaches the script as `C:/Program Files/Git/Outputs/...` and matches nothing | MANUAL.md troubleshooting (`MSYS_NO_PATHCONV=1`); the gated drivers set it for the tools they call | tooling |
| L37 | **Gated drivers take an area filter.** Board-wide centring and via moves also moved copper in a region left for the designer (lead-in ends listed in a hand-off) | `--box` / `--exclude-box x0,y0,x1,y1` in `refinish_gated.py`, `centre_gated.py`, `via_relocate.py`, `dedupe_copper.py` | board-wide passes |
| L38 | **Plane vias belong on the pad axis from the start.** refinish cannot fix an entry whose first vertex is inside the stub zone (pad edge + 0.5 mm); on a routed board that is mostly a plane via placed right beside the pad. ServiceOne outside the ADC box: a sample kept 6 of 25, then 2 of 40 (20 refused for the stub zone); of 520 pads with pad-entry FAILs only 107 were on plane nets, the rest need a re-route with shove | Repair: `via_relocate.py --mode axis` (shipped) moves the via onto the pad axis past the stub zone, driven by `gate_each.py`; then `refinish_gated.py`. `--mode web` slides a via along its stub for the 0.15 mm mask web (L15). Prevention, stage 3: `stitch_planes.py` places the plane via on the pad axis at pad edge + 0.5 mm + via radius. Never start a board-wide refinish without a sample and the stop rule | issue 18 pass |
| L39 | **Locks are of two kinds.** Design locks (Kelvin sense, datasheet loops such as U10, hand-laid critical copper) and tool locks (`stitch_residual.py` locks every via and stub it places). At the D133 hand-off the board carried 171 locked items, 165 of them GND / +3.3V stitching tool locks, while the copper the hand-off said to lock (AIN, CLKIN, supply and CAP at U1) was not locked at all. Tool locks are fixed walls for KiCad's shove router and blocked the interactive routing | `locks.py --list` (shipped: locked items per net, for the hand-off note); playbook Addendum D, D5; stage 3: `stitch_residual.py` does not lock (or tags the lock as a tool lock), `lock_nets.py --list` tells design from tool locks, the audit checks that the copper a hand-off says to lock is locked | U1 routing (Vladimir) |
| L40 | **Gated drivers honour locks.** The audit and DRC gates do not see a lock: two scratch via tools moved 43 locked stitching items and `refinish_gated.py` removed 3, all gate-clean | `locks.py` fingerprint compared after every attempt in `finish_gated.py`, `refinish_gated.py`, `centre_gated.py`, `stage_gate.py` / `gate_each.py` (a moved, changed or removed locked item reverts the attempt); `via_relocate.py`, `dedupe_copper.py`, `dangling_classify.py` skip locked items; `edit_tracks.py` refuses to delete one without `--allow-locked` | board-wide passes |
| L41 | **Orthogonal-first routing.** Tracks run horizontal or vertical; 45° only as corner chamfers or short links (<= 3 mm, one pin pitch in pin arrays, L21). A longer diagonal needs a recorded reason: fan-out escape, datasheet loop (converter, Kelvin), clock or analog line where length matters. Preferred layer directions F.Cu horizontal, B.Cu vertical, as a soft cost. Why: long diagonals leave triangles where no via, part or shoved track fits later. Cost accepted: a straight H + V route is up to ~41 % (average ~27 %) longer than the diagonal, so length-critical nets are the listed exception (Altium layer directions; 45° only in critical zones; the 90° corner concern matters only above ~10 GHz) | audit `diagonal` (§33: WARN per 45° segment longer than `routing_style.diagonal_max_mm`, default 3, outside IC fan-out zones; nets in `routing_style.diagonal_exceptions` with their reason exempt; INFO: diagonal share of the track length per layer); project parameter `routing_style`; stage 3: `rules_writer.py` writes the layer directions and costs, `route_finish.py` gets a turn cost that favours H / V runs | issue 22 (Vladimir's rule) |
| L42 | **Normalise the baseline before a gated pass.** The shared-gap message listed its nets in file order, and a pcbnew save writes a different order from a KiCad GUI save: on the board Vladimir routed (837b594) a pcbnew save with no change "added" one shared-gap FAIL, so every batch of the centring driver was refused (0 of 118 kept in 30 min) | audit §16: net names sorted in the shared-gap message (test: reversed track order, same message); `stage_gate.py --snap --normalise` saves the baseline through pcbnew once | clean-up after the U1 routing |
| L43 | **No scripted rip-up of a dense IC cluster.** In the U1 (ADS131M04, 3 x 3 mm QFN) cluster every single route either left a neighbour off-centre between two pads, put a via ring too close to a pad, ended 0.025 mm off a pad centre, or reused the net's own copper: 0 of 16 attempts kept in 18 min, stopped by L30 and the board restored. Route dense IC clusters interactively from the start (priority corridor for clocks, axial fan-out) | playbook Addendum D, D3; stage 3: `route_finish.py` ends exactly on pad and via centres (the off-grid ends caused most reverts), a cluster mode that gates the finished cluster, not each route | U1 cluster attempt |
| L44 | **KiCad Cleanup: "Delete tracks fully inside pads" off.** It removes the short last stub that takes a track to the exact pad centre, so the track then ends off-centre (8 new pad-entry FAILs on ServiceOne: C2-1, C29-1, C210-2, R38-1 and others). "Merge co-linear tracks" can also change how the audit reads a gap (1 new between-pads finding, copper unchanged). Gate the board after any Cleanup and restore pad-centre stubs | L2 settings amended; playbook Addendum D, D4; `dedupe_copper.py` keeps pad-centre stubs | issue 2, Vladimir's Cleanup |

ServiceOne result (audit 1.28.0, read-only, `rev02-adc-region` at 397a6c8): 170 diagonal WARNs over 3 mm; 45 % of the
B.Cu and 32 % of the F.Cu track length is diagonal (issue 22's list). Dry runs: `via_relocate.py --mode axis` finds 84
plane pads with pad-entry FAILs and moves 11 of them; `--mode web` moves 19 of 170 vias; `dedupe_copper.py` finds 6
duplicates. A gated sample of 4 axis moves (`gate_each.py`) kept none: each new via left a neighbouring track off-centre
between two vias (a new between-pads FAIL), so the gate refused it in about 10 s per candidate. On the D133 board (9176be8): `open_ends.py` gives copper ends for all 32 open connections;
`dangling_classify.py` keeps 33 lead-ins and removes 12 unused stubs (27 segments, 55.6 mm) and 1 via.

## 10. Stage 3 (planned)

Every rule of section 9 applies now and is checked by the audit, a shipped script or the playbook. These items make
the tools prevent the defect instead of finding it:

1. `stitch_planes.py` / `stitch_residual.py`: plane vias on the pad axis at pad edge + 0.5 mm + via radius (L38);
   no plain locks on tool-placed copper, or a tool-lock tag (L39).
2. `lock_nets.py --list`: design locks vs tool locks; audit INFO when the copper a hand-off says to lock is not
   locked (L39).
3. `route_finish.py`: end exactly on pad and via centres; a cluster mode gated per cluster (L43); a turn cost that
   favours H / V runs from `routing_style` (L41).
4. `rules_writer.py`: layer directions and costs from `routing_style` for Freerouting (L41).
5. `finish_gated.py`: ends from `open_ends.py` (L31).
6. Library setup / `model_builder.py`: EasyEDA .wrl, F.Fab alignment, render check (L35).
