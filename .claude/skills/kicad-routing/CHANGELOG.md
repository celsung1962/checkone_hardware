# Changelog — kicad-routing skill (formerly kicad-golden)

## 1.29.0 - 2026-11-13

Three changes made in the GapOne_V2 copy of the skill (GapOne CON, Celso Souza and Claude, 2026-11-06 to
2026-11-09) and carried into `aqtech-skills`: the KiCad Routing Tools copper-hygiene checker, inner signal layers on
6+ layer boards, and the last-bend distance before a pad as a project parameter.

### Last bend before a pad: project parameter (GapOne D-357)

- `scripts/kicad_audit.js`: new project key `pad_entry` in `kicad_golden.project.json`. `bend_min_mm` sets the
  minimum distance from the pad edge to the last bend (default 0.5 mm, review issue 18 / L11, unchanged when the key
  is absent); `bend_check: false` switches that one check off and the audit reports a single INFO line instead of
  the FAILs. The other pad-entry checks (axial entry, blocking at fine pitch; pad centre; width; short entry;
  staircase) are not affected.
- `templates/kicad_golden.project.json`: `pad_entry` with the defaults (`bend_check` true, `bend_min_mm` 0.5).
- `tests/run_tests.js`: two assertions on the review2 board (0.1 mm limit passes the 0.11 mm bend at R26-2;
  `bend_check` false gives the INFO and keeps the non-axial FAIL at R27-2).
- Why: on the GapOne CON (0.4 mm WQFN, dense 0402 / 0603) the owner first relaxed the limit to 0.1 mm, then
  switched the check off (2026-11-09); the skill had it hard-coded.

### Inner signal layers on 6+ layer boards (GapOne D-346)

- `scripts/kicad_audit.js`: on a board with 6 or more copper layers, an inner layer declared `signal` in the
  board's `(layers)` list is a routing layer and its tracks are no longer reported as tracks on a plane layer
  (`stats.inner_signal_layers` lists them). On 4 layers every inner layer stays plane-only, as before.
- Why: the GapOne CON moved to a 6-layer stack S / GND / S / PWR / GND / S (owner 2026-11-07).

### Copper-hygiene checker (KiCad Routing Tools)

- `scripts/krt_check.py` (new): finds the KiCad Routing Tools plugin (github.com/drandyhaas/KiCadRoutingTools,
  KiCad PCM), runs its read-only `py_router/check_weird.py` with KiCad's Python and parses the findings
  (soft-joint, redundant-cycle, removable-segment, stacked-copper, dangling-end, orphan-island, unsupported-via,
  dangling-via, narrow-pad-joint, kicad-dangling). One board: report. Two boards: the new-finding gate, identity
  category + net + layer, counted. `dangling-via` on a net poured on an inner layer the via spans is filtered as a
  false positive. The plugin is found through `$KRT_DIR`, `--krt`, the KiCad plugin folders and the
  `KICADn_3RDPARTY_DIR` of `kicad_common.json`.
- `scripts/stage_gate.py`: the snapshot records the hygiene findings when the plugin is found (`--no-krt` skips) and
  `compare` blocks on any new one; the report line gains `krt new N`.
- SKILL.md: §The copper-hygiene gate; workflow step 3 and the script list name the checker.
- Why: the GapOne CON clean-up of 2026-11-06 passed DRC and the new-FAIL gate and was committed, then this checker
  found 79 soft joints the hand-off board did not have (55 from `route_finish.py` ending on coordinate chain ends,
  24 from `dedupe_copper.py --tol 0.09` removing the pieces that joined two segments end to end).
- Its router is not adopted: on the same board it closed all 98 open connections but added 1688 audit FAILs, ripped
  copper under `--keep-input-copper` and stepped vias down to 0.25/0.15 mm.
- No test suite covers `krt_check.py` yet: it needs the plugin installed, which the CI container does not have.

## 1.28.1 - 2026-11-02

Continuous integration (no change to any tool or audit result). First release from the `aqtech-skills`
repository, where the skill is now maintained; the projects receive it as an update pull request.

- `tests/run_all.py` (new): runs all 14 suites, each with the interpreter it needs (node, system Python, KiCad's
  Python), and prints one table. `--strict` fails a suite that skipped checks because a tool was missing.
- The suites leave a checkout unchanged: `run_tests_py.py` writes its round-trip board to a temporary folder,
  `run_tests.js` removes the apply_settings backup in `fixtures/finevias/`, and the `*.audit.json` reports the
  suites write on every run (they carry the run date) are git-ignored (`tests/.gitignore`) and no longer tracked.
- `.github/workflows/kicad-routing-tests.yml` (repository root): on every push or pull request that touches the
  skill, runs `run_all.py --strict` in the `kicad/kicad:10.0.8-full` container and fails if the run changed or
  added any file.
- First run on Linux (KiCad 10.0.8 container), two findings:
  - `pcbnew.SaveBoard` writes the `.kicad_pro` for a board made with `pcbnew.BOARD()` on Windows but not on Linux;
    `pcbnew.NewBoard(path)` writes it on both. The guard and pcbnew suites build their fixtures with `NewBoard`.
    Without the `.kicad_pro`, `board_guard.py` (correctly) refused every write and 11 checks failed.
  - matplotlib / numpy / shapely are not part of KiCad on Linux (the system Python runs pcbnew); INSTALL.md now
    lists them. Missing, they failed 19 checks of the axial, gate-tools and plane-plan suites.

## 1.28.0 - 2026-10-31

Finishing a routed board under the gates. The ServiceOne rev. 0.2 review fixes (branch `rev02-adc-region`,
2026-10-22/23) were made by Vladimir Duk with KiCad's interactive router and by Claude with gated scripts: audit
1818 -> 1455 FAIL from Celso's hand-off to 397a6c8, 0 unconnected, no scripted change adding a FAIL. The lessons were
recorded in the review document for the skill maintainer; this release folds them in as L30-L44 (reference 11,
section 9), with the scripts written during that work generalised, and lists what is still planned (section 10,
stage 3). Playbook Addendum D.

- Stop rule (L30, Vladimir's rule): `scripts/stop_rule.py` (new). `finish_gated.py` and `refinish_gated.py` print an
  estimate and stop after 10 attempts or 30 min when fewer than 1 in 5 is kept or the projected time exceeds
  `--budget` (default 60 min); `--min-keep-rate`, `--no-stop-rule`. `finish_gated.py` writes the connections left to
  `<board>.finish_open.json`.
- Locks (L39, L40): `scripts/locks.py` (new) reads the locked tracks and vias from the file text; `finish_gated.py`,
  `refinish_gated.py`, `centre_gated.py`, `stage_gate.py` and `gate_each.py` revert a change that moved, changed,
  removed or unlocked one. ServiceOne: scratch via tools had moved 43 locked stitching items and `refinish_gated.py`
  removed 3, all gate-clean.
- Fast per-attempt gate (L32): `finish_gated.py` refills the zones for the per-attempt DRC only when the routed net
  has a zone and ignores zone-fill violations otherwise; DRC with `--refill-zones` at the end
  (`--refill-every-attempt` restores 1.27).
- Area filters (L37): `--box` / `--exclude-box` in `refinish_gated.py` and `centre_gated.py` (and the new tools).
- `kicad_audit.js` section 33 `diagonal` (L41, Vladimir's rule, ServiceOne issue 22): WARN for a 45-degree segment
  longer than `routing_style.diagonal_max_mm` (default 3) outside the fan-out zone of an IC (pad bounding box +
  `fanout_zone_mm`, default 1.5); nets in `routing_style.diagonal_exceptions` exempt; INFO with the diagonal share of
  the track length per layer. Stats `long_diagonals`. ServiceOne 397a6c8: 170 WARNs, B.Cu 45 % / F.Cu 32 % diagonal.
- `kicad_audit.js` section 16 (L42): the shared-gap message lists its nets sorted, so it no longer depends on the
  order of the tracks in the file (a pcbnew save "added" a FAIL to an unchanged board and blocked a centring run).
- New tools (from the ServiceOne work, generalised): `stage_gate.py` (snapshot and per-change gate: DRC, unconnected,
  new audit FAILs, layout checks, locks; `--normalise`, `--refill`), `gate_each.py` (runs a candidate-indexed tool one
  candidate at a time under `stage_gate.py` and the stop rule), `via_relocate.py` (`--mode web`: via slid along its
  stub for the 0.15 mm mask web, L15; `--mode axis`: plane via onto the pad axis past the stub zone, L38),
  `open_ends.py` (copper ends of open connections, L31), `dangling_classify.py` (lead-in / unused stubs, L33),
  `via_spot.py` (legal via spots along a line, L34), `dedupe_copper.py` (same-net copper inside other copper, L19;
  keeps pad-centre stubs), `edit_tracks.py` (exact scoped edit from a JSON spec; refuses to delete a locked item).
- KiCad Cleanup (L44, amends L2): "Delete tracks fully inside pads" OFF - it removed the stubs that carry tracks to
  the pad centres (8 new pad-entry FAILs on ServiceOne).
- `templates/kicad_golden.project.json`: `routing_style` (diagonal_max_mm 3, fanout_zone_mm 1.5, layer_direction F.Cu
  H / B.Cu V, diagonal_exceptions empty). `golden_settings.json` `_meta.skill_version` 1.28.0.
- SKILL.md: §The stop rule, locks and the gated tools; Core rules (finishing under the gates, orthogonal-first
  routing); scripts list. MANUAL.md: troubleshooting rows for the stop rule and locks.
- Tests: run_tests.js 127 -> 131 (diagonal WARN, short and excepted diagonals, good board, shared-gap order);
  new `tests/run_tests_gate_tools.py` (26: stop rule, locks, edit_tracks, dedupe_copper, via_relocate both modes and
  locked vias, open_ends and dangling_classify with kicad-cli, usage errors). 14 suites, 366 assertions.
- Tried on ServiceOne 397a6c8 (copies): `via_relocate.py --mode axis` 84 candidates / 11 movable, `--mode web` 170 / 19,
  `dedupe_copper.py` 6 duplicates; `gate_each.py` over 4 axis moves kept none (each left a neighbour off-centre
  between two vias, refused in about 10 s per candidate). On the D133 board (9176be8): `open_ends.py` ends for all 32
  open connections; `dangling_classify.py` 33 lead-ins kept, 12 unused stubs and 1 via removed.

## 1.27.0 - 2026-10-22

Rules enforced, not counted. Vladimir Duk's review of the scripted ADC-region rework on ServiceOne (D133, branch
`rev02-adc-region`): the U1 entries improved, but rules already defined were broken - acute joints, vias in and
beside pads, tracks between pads where a route outside was easy, open tracks. Against the board before the rework:
220 new FAILs (93 between-pads, 82 pad-entry, 31 via, 6 acute joints), 32 unconnected and 45 dangling stubs. Every
scripted step had passed because every gate compared only the total FAIL count, which fell 1932 -> 1795 as the
rip-up removed 357 old FAILs. Lessons L27-L29 (reference 11, section 8), playbook Addendum C.

- `kicad_audit.js` section 32 `acute` (L28): FAIL where same-net tracks meet on one layer, away from a pad centre or
  a via, with two neighbouring branches less than 90 degrees apart (a 135-degree turn, a T branch 45 degrees off its
  run, a doubled collinear piece). Section 3 counted a 135-degree turn as a mitre, so nothing caught it before. Stats
  `acute_joints`. ServiceOne `rev02-adc-region`: 25 (11 corners, 14 at T junctions), 14 new in D133.
- `scripts/audit_gate.py` (new, L27): the new-FAIL gate. Baseline and result are boards or audit JSON; a finding's
  identity is its check plus its message with the measured numbers blanked (net names, references and layers keep
  their digits), counted; exit 1 lists the FAILs the result added. Module API `audit`, `fail_ids`, `new_fails`.
  ServiceOne D133 (6e30d10 -> 9176be8): 209 new FAILs by identity, BLOCKED.
- `finish_gated.py`: audit gate after the DRC and layout gates; a route that adds a FAIL is reverted
  (`--no-audit-gate` turns it off). `centre_gated.py` and `refinish_gated.py`: a kept batch / attempt must also add
  no FAIL (the total-falls condition stays).
- `route_finish.py` (L28): the A* state carries the arrival direction and takes no step more than 90 degrees from it;
  a stub start continues in the stub's direction and the goal is entered against the goal stub; the simplifier keeps
  the rule on its shortcuts (a corner on the start cell checks the remaining leg); a route left with an acute joint
  exits 5 without writing. `--allow-acute` restores the 1.26 search. The 1.23 SOIC test route had an acute joint at
  its pin stub.
- SKILL.md: §The new-FAIL gate (mandatory for every change to a routed board; hand-off with no dangling copper, L29),
  Core rules (no acute joints; rules enforced, not counted), Workflow step 3. Playbook: 10.1 / 10.2 gates, F2a / F2b,
  Addendum C.
- `golden_settings.json` `_meta.skill_version` 1.27.0 (it still read 1.26.3, so the audit reported the wrong
  version).
- Tests: run_tests.js 123 -> 127 (acute: turn, T branch, 90-degree turn / mitre / via exempt, good board 0);
  run_tests_py.py 28 -> 34 (gate identity, counting, CLI); run_tests_axial.py 12 -> 14 (stub pointing away from the
  target: no acute joint; with `--allow-acute` the audit FAILs it). 13 suites, 336 assertions.

## 1.26.6 - 2026-10-21

- `route_finish.py --avoid-exempt` takes several circles, `X,Y,R;X,Y,R`: a clock kept 1 mm from the ADC inputs must
  be exempt both at the ADC pins and at its own test pad (ServiceOne CLKIN, rev. 0.2).
- ServiceOne project tools for re-placing on a routed board (`hardware/routing/`): `clip_box.py` (clear a rectangle,
  pieces outside kept as routed), `place_cluster.py` (datasheet-target placement in order, explicit spots with the
  reason a spot is refused), `strip_old_stubs.py` (copper left on moved pads), `corridor.py` (a long-haul route found
  on a stripped copy laid into the routed board, cutting only what it crosses).

## 1.26.5 - 2026-10-21

- `kicad_audit.js` rule 17 (`plane-net`, improvements #7): a pin-capacitor pair named by a datasheet decoupling
  check with `"surface": true` (`layout_checks`, playbook B0) may be joined by a surface track - INFO instead of FAIL.
  The datasheet asks for that link (ADS131M04 Fig. 11-1, INA226 Fig. 8-4, LM2776 10.1, MT3608 Fig. 3), so the two
  checks no longer contradict each other. Any other pad joined to the pair by surface copper still FAILs.
  Tests: run_tests.js 121 -> 123.

## 1.26.4 - 2026-10-21

- `route_finish.py` island mode: a route that starts at a coordinate (a DRC open end, a `--refinish` cut vertex) treats
  its own copper island as an obstacle (except around the start point) and ends on the first cell of any other island of
  the net. Before, own copper was passable everywhere, so a route could run back along its own island and be refused as
  duplicate copper (exit 4). The free circle around the start includes the radius of the via or track the start lies
  on (a via start was sealed in). Off for plane nets, `--exclusive`, pad starts and `--no-islands`.
- `finish_gated.py`: unconnected items that name a pad are routed pad-to-pad (axial entries) instead of by coordinates.
- ServiceOne rev. 0.2 phase 2: U7 (TP4056) cluster re-placed and rerouted with these tools; project tools in
  `hardware/routing/` (relocate, ripzone, route_seq, fix_after_update).

## 1.26.3 - 2026-10-21

- `kicad_audit.js`: the board's title-block revision and date are compared with the root schematic beside it (same
  stem). A different revision or date -> WARN `revision`; a board without a revision next to a schematic that has one
  -> WARN; the same -> INFO. Stats `title_block`. Playbook G-0. Pairs with the new kicad-schematic
  `check_revision.py` (every title block of the project at the same revision). ServiceOne: rev. 0.2 set on the 8
  sheets and the board. Tests: run_tests.js 118 -> 121.

## 1.26.2 - 2026-10-21

- `datasheet_layout_scan.py`:
  - documents with manifest status `manual` (placed by hand with `fetch_datasheets.py import`) are scanned. Before,
    only `ok` was, so ServiceOne's L2 (SWPA8040S100MT catalog, D109) was reported as having no document;
  - `--write-params` keeps the fields the review added to the `datasheet_layout` block (e.g. `reviewed`, notes);
  - JSON written with LF on Windows.
- The same fixes in kicad-schematic `app_circuit_scan.py`. Tests: run_tests_datasheet.py 15 -> 16.

## 1.26.1 - 2026-10-21

- `kicad_audit.js` pre-flight: a board rule below the fabricator profile value is INFO, not FAIL, when it matches
  an `approved_rule_deviations` entry (the value apply_settings.js keeps). It still FAILs below the recorded
  `fabricator.absolute_min`. ServiceOne: `min_hole_clearance` 0.2 (D110) is no longer a FAIL, so the audit total
  goes from 1947 to 1946 FAIL. Tests: run_tests.js 115 -> 118.

## 1.26.0 - 2026-10-21

Datasheet layout suggestions before routing (Celso, 2026-10-21): every datasheet of every part on the board is scanned
for layout sections before routing, and its suggestions drive the placement and the routing. Until 1.25 the datasheet
review (reference 10) ran only after routing. Tests: new run_tests_datasheet.py 15; the other suites unchanged.

- `datasheet_layout_scan.py` (new, system Python with PyMuPDF; pypdf / pdftotext as text-only fallbacks):
  - matches the board's parts to their documents through the manifest, by MPN or LCSC code (`--parts bom/parts.csv`);
    every document of a part counts, hardware design guides too;
  - finds layout pages and classes them as guidelines, example or land pattern; tables of contents are skipped;
  - extracts rule sentences and renders each layout page to PNG;
  - writes a Markdown / JSON report;
  - `--write-params` merges a `datasheet_layout` review block: one entry per part, `pending`. Entries already
    reviewed are kept while their pages are unchanged.
- `kicad_audit.js` pre-flight: no `datasheet_layout` on a board with ICs -> WARN; a `pending` part -> FAIL; reviewed
  -> INFO. Also WARNs for a part marked applied without a recorded rule, and for parts without a document.
- `route_freerouting.py`: refuses to export (exit 4) while a part is `pending` (`--skip-datasheet-review`); WARNs
  when no review is on record.
- `layout_measure.py check --pre-route`: each decoupling entry is judged by straight pin-to-pad distance before
  routing. Kelvin and separation checks need copper and run after routing.
- Docs: SKILL.md §Datasheet layout suggestions (and the new-board command list), reference 10 §0, playbook B0.
  ServiceOne scan: 40 parts with a document, 11 with layout pages, L2 without a document.

## 1.25.0 - 2026-10-21

Stage 2, item 5 of reference 11: approximate 3D models (lesson L26) and mounting holes that carry their keep-out (L24,
ServiceOne review issues 17 and 20). Stage 2 is complete. Tests: new run_tests_models.py 13; the other suites
unchanged.

- `model_builder.py` (new, any Python; from the ServiceOne `box_model.py` prototype): box models as STEP (AP214) and
  VRML, named `*_approx`.
  - `spec` takes boxes from the datasheet drawing, given in JSON.
  - `footprint` builds a body over the F.Fab outline (or the courtyard, or the pads) up to `--height`, with leads or
    pins from the pads.
  - `--assign` writes or replaces the footprint's (model ...) block with a `${KIPRJMOD}` path.
  - Check: its rebuild of the ServiceOne SW1 model from the prototype's boxes is identical (same STEP points,
    VRML byte-identical).
- `mounting_hole_fp.py` (new, KiCad's Python):
  - Writes an NPTH or `--plated` hole footprint.
  - Adds a KO_MECH rule area (no tracks, vias or pours) of radius = the largest contact diameter / 2 + 0.5 mm, on
    F.Cu and B.Cu or all layers.
  - The courtyard is the keep-out circle; the contact circles go on the Fab layers.
  - Excluded from BOM and position files.
  - KiCad's DRC and the Specctra export enforce the keep-out.
- `kicad_audit.js` section 27: a mounting-hole footprint with its own keep-out rule area counts as covered (INFO),
  without a `mechanical_keepouts` entry. New stat `mounting_holes_own_keepout`.

## 1.24.0 - 2026-10-21

Stage 2, item 4 of reference 11: the fan-out pattern (lesson L22, ServiceOne review issue 19) and the pin-array
channel centreline (L21, issue 21). Tests: new run_tests_fanout.py 9; the other suites unchanged (run_tests.js 115).

- `kicad_audit.js`:
  - section 31 `fan-out` (WARN): per pad row of a U*/IC* part (rows as section 26), the tracks that leave a pin
    straight along the outward axis and then bend the same way form a group; first bends more than 0.1 mm apart
    -> WARN (aligned bends make the parallel runs equally spaced). Stats `fanout_groups`, `fanout_unaligned`.
  - section 29 `pin-array`: an orthogonal run inside the array, in a channel wider than the between-pads limit
    (1.5 mm), with clearances to the nearest pad on each side differing by more than 0.02 mm -> FAIL "off-centre".
    The message has the between-pads form. Stat `pin_array_off_centre`.
- `center_gaps_safe.py`: also centres the `pin-array` "off-centre" findings (so does `centre_gated.py`).
- `fanout_regularise.py` (new, KiCad's Python):
  - `--list` (read-only) and `--apply`.
  - Slides each first bend to a common distance (the largest current one, at least pad edge + 0.5 mm). The next
    vertex moves along its own run, so directions and far ends are kept.
  - When no slide fits, re-routes the group's pins with `route_finish.py --refinish --refinish-force`.
  - Each group is gated by DRC and the audit. Locked tracks and Kelvin pads are left.
- `route_finish.py`: new `--refinish-force`, which re-routes an entry even when it is already axial.

## 1.23.0 - 2026-10-20

Stage 2, item 3 of reference 11: axial pad entries (lessons L10 / L11, ServiceOne review issues 6 and 18). Tests: new
run_tests_axial.py 12; the other suites unchanged (run_tests_kicad.py 22 still passes with the stubs on).

- `route_finish.py`:
  - with `--from-pad` / `--to-pad` every pad end is an axial stub: one straight segment from the exact pad centre
    along the pad axis (elongated pad: long axis; square: either axis; IC pin, part with >= 6 pads: outer end first;
    passive: the side facing the route) to pad edge + 0.5 mm, no wider than the pad's smallest dimension (the rest
    keeps `--width`). The search starts / ends at the stub ends with the stub and the pad area closed to it, so the
    last bend lies >= 0.5 mm beyond the pad edge. The grid origin is shifted (less than one cell) so each stub axis
    passes through the exact pad centre. A round pad needs no stub; a pad off the 45-degree lattice or with a
    blocked axis exits 1. `--no-axial` restores the 1.19 behaviour.
  - `--refinish REF.PAD [--refinish-length 1.5]`: realigns an existing entry. The track into the pad is cut back
    along its chain (same layer, no via, no branch) to a vertex >= 1.5 mm of copper away and re-routed with a stub;
    a chain that starts in another pad of the net is re-routed pad to pad. Nothing is saved without a route.
  - one non-axial entry per run (several entries: run again); an existing axial stub of the pad is shared, not
    doubled; a cut point inside the stub zone (a via next to the pad) is refused with that reason.
  - a route that would run along same-net copper (< 0.3 mm over > 0.5 mm, the audit's loop rule) exits 4 without
    writing (`--allow-overlap` overrides). Each segment carries its own width.
- `refinish_gated.py` (new, system Python): pads from the audit's pad-entry FAILs (or `--pads`), `--refinish` one at
  a time, kept only when the DRC error + unconnected count does not rise, the audit FAIL count falls and no passing
  layout check breaks; Kelvin pads skipped; backup `.bak_prerefinish`. ServiceOne rev. D copy, 30 pads: 3 kept, audit
  FAIL 1947 -> 1943, DRC unchanged; the rest need a via or a track moved first.

## 1.22.0 - 2026-10-20

Stage 2, item 2 of reference 11: pad-row band keep-outs (lesson L16, ServiceOne review issue 16). Tests: new
run_tests_padrow.py 10; run_tests.js 115 (review2 fixture: the GND plane via moved 0.1 mm out so its copper clears the
band); the other suites unchanged.

- `pad_row_keepouts.py` (new, KiCad's Python): "no vias" rule areas (all copper layers; tracks, pads, pours allowed)
  over every IC pad-row band, with the geometry of audit section 26. `--list` (read-only, `--json`), `--write` on the
  real board (`KO_ROW_<ref>_<n>`, board_guard, edited in place, stale ones removed, item nets verified from the saved
  file), `--export-copy` for a DSN copy (`KO_EXPORT_ROW_*`). The footprint frame is fitted on the pads, so rotation
  and the bottom-side mirror come out right. KiCad's Specctra export writes them as `via_keepout`.
- `export_keepouts.py --pad-row-bands`: the same areas on a Freerouting export copy.
- `kicad_audit.js` section 26: a via counts when its copper reaches the band (was: its centre), so the audit, the
  router's via keep-out and KiCad's DRC agree; a row whose pads all carry one number (an exposed pad split into a
  grid, e.g. an ESP32 module's GND pads) is not a pad row. ServiceOne rev. D: 48 -> 45 bands, 31 -> 45 vias.

## 1.21.0 - 2026-10-20

Stage 2, item 1 of reference 11: the plane plan (lesson L23, ServiceOne review issue 13). Tests: run_tests.js 107 -> 115,
new run_tests_planeplan.py 11; the other suites unchanged.

- `plane_plan.py` (new, KiCad's Python):
  - `map` (read-only): per power rail on an inner layer, single-linkage pad clusters -> candidate island (pad hull +
    1 mm, inside the main plane's pourable area). Per candidate: pads served and pads still without their own via,
    voltage from the net name and gap from `gap_by_voltage`, crossings by tracks on the adjacent signal layer,
    main-plane pieces and thin copper left (opening by `min_neck_mm`), Kelvin sense vias inside
    (`layout_checks.kelvin`). Writes PNG, Markdown trade-off table and JSON for `plane_plan.islands`. Refuses a
    `never_split` layer. Auto-named nets (`Net-(...)`) only with `--rails`.
  - `apply` (board_guard, refill): named zones above the main plane, clearance = gap, settings from the main plane.
    An existing zone is edited in place: removing a zone through the API saved a lone via under another net on KiCad
    10.0. Item nets are compared from the saved file and the board is restored if one changed.
  - `check` (exit 1 on FAIL): empty or isolated island fill, main plane split, Kelvin broken; WARN thin copper,
    adjacent-layer crossings, pads inside without their own via.
- `kicad_audit.js` section 30 `plane-plan` (fixture `tests/fixtures/planeplan.kicad_pcb`): undeclared island WARN,
  island on a `never_split` layer FAIL, adjacent-layer crossing WARN (a plane layer in between shields), clearance
  below the gap for the voltage FAIL, island serving < 2 pads WARN, declared island missing WARN, INFO summary.
  Thin plane pieces and sense vias are left to `plane_plan.py check`.
- Template and `init_project.py`: `plane_plan` block (islands empty). Docs: SKILL.md, playbook B7, reference 11.

## 1.20.0 - 2026-10-20

The rules of the ServiceOne rev. 0.2 board review (Vladimir Duk, ServiceOne `reports/board_review_rev02.md`):
26 lessons, mapped in the new `references/11_board_review_lessons.md`. Stage 1: rules, audit checks and script
fixes. Stage 2 (planned): plane_plan.py, pad-row band keep-out generator, route_finish axial end-finishing, fan-out
regulariser, approximate 3D model builder. Tests: run_tests.js 77 -> 107, new run_tests_guard.py 45; the other suites
unchanged (28, 16, 8, 11, kicad 22).

- `kicad_audit.js` - new sections 19-29 and stricter rules (fixture `tests/fixtures/review2.kicad_pcb`):
  - `pad-entry`: end cap outside the pad (§19); non-axial entry is FAIL for every rectangular pad, a bend closer than
    0.5 mm beyond the pad edge is FAIL, and at pitch <= 0.65 mm the message says "blocking, no deviation" (§7);
  - `via`: plane via larger than the small via at fine pitch (WARN, §20); via between the pads of a two-pad part
    (§22); ring < 0.15 mm from an SMD pad, same net included (§23); via inside an IC pad-row band (§26); drill below
    `fabricator.economical_via_drill_mm` unless `fine_vias_approved` (§6);
  - `geometry`: same-net crossing tracks (§21); `loop`: cycles and near-parallel duplicates (§25);
    `detour` WARN: ratio, U-turn and bump (§24);
  - `between-pads` / `shared-gap` (§16): every mutually nearest facing pair of flanks is checked (the single-flank
    search missed U102 10/11 and J3 8/9); the shared-gap message names a free neighbouring gap;
  - `mech-keepout` (§27) from `mechanical_keepouts`; `model` (§28): missing model or file, `*_approx` listed;
    `pin-array` (§29): diagonal longer than half a pitch (`pin_array.max_diagonal_pitch_fraction`, default 0.5)
    inside a regular THT pin grid;
  - §13: a netclass drill raised to the economical tier is INFO, not a template mismatch.
- `board_guard.py` (new): every board-writing script refuses when KiCad lock files exist or no `.kicad_pro` is next
  to the board (`--force-write`, `--allow-no-pro` / env overrides); wired into route_finish, geometry_finish,
  fab_layer_fix, stitch_planes, stitch_residual, repair_import, rail_zones, lock_nets, center_gaps_safe,
  export_keepouts, route_freerouting, finish_gated, centre_gated.
- `zone_fill_check.py` (new): saved fill vs fresh fill by XOR area (a moved via leaves the total area unchanged);
  `--fix` refills and saves. Board-writing scripts refill before saving (text writers call it after writing).
- `finish_gated.py`: layout gate - a route that breaks a passing `layout_measure.py check` is reverted
  (`--params`, `--no-layout-gate`).
- `apply_settings.js`: keeps `approved_rule_deviations` from `kicad_golden.project.json`, refuses one below the
  profile's `absolute_min`; JLCPCB 4L/6L profiles carry `economical_via_drill_mm` 0.2 / diameter 0.45, the small
  predefined via is 0.45/0.2 unless `--fine-vias`; `fabricator.economical_via_drill_mm` and `fine_vias_approved`
  recorded. Template and `init_project.py` gain `approved_rule_deviations`.
- `stitch_planes.py`: no 0.25/0.15 fallback via when the tier is set and fine vias are not approved.
- Docs: SKILL.md Core rules (board-review rules), playbook Addendum B, reference 11.

## 1.19.1-local.2 - 2026-10-20

- `route_finish.py`: new `--max-expansions N` (A* budget, default 4 000 000 as before). A long dedicated
  (`--exclusive`) route can need more; a run that ends below the budget is exhaustive: there is no path.
- Lesson (ServiceOne D124): a dedicated Kelvin line rerouted by `finish_gated.py` is joined to the load copper
  again (twice so far); `repair_import.py --declang` then deletes the rest of the sense line as a dead branch.
  Rebuild Kelvin lines by hand / with `--exclusive` after every reroute, before trimming dead ends.

## 1.19.1-local.1 - 2026-10-20

From the ServiceOne display-standoff keep-outs (D116, D117): rerouting 41 tracks out of four r 4.0 mm rule areas.
Tests unchanged (run_tests_kicad.py 22/22).

- `route_finish.py`, fixed:
  - rule areas were stamped as their BOUNDING BOX and not dilated: a track hugging the square entered a circular
    keep-out at the tangent points (`items_not_allowed` after the route). They are now rasterised from the real
    outline and dilated by half the track width (vias: half the via diameter) plus the safety margin;
  - own-net copper no longer clears a keep-out cell (it was applied after the keep-out).
- `finish_gated.py`, new options:
  - `--no-narrow`: keep the given width - the 0.6 / 0.2 mm fallback put a 1.0 mm battery rail at 0.2 mm;
  - `--via-cost N`: passed to route_finish.py.
- Lessons (ServiceOne `reports/spacer_keepout.md` §6):
  - Rip-up by whole segments plus `repair_import.py --declang` deleted long dangling chains (a 19 mm trunk) and the
    router rebuilt them with many vias. Clip the copper at the keep-out instead and close the gaps around it.
  - Start and end route_finish on free track ends at least half-width + safety outside the keep-out; an end on
    the keep-out edge sits in a blocked cell. DRC "nearest points" may lie on a pad: a via there is a via-in-pad.
  - Kelvin sense lines: after any reroute run `layout_measure.py check`; a DRC-gated route joined the sense line to
    the load copper twice. Redo it with `--exclusive --from-pad SHUNT --to-pad FILTER_CAP`.
  - Git Bash rewrites arguments that start with `/` (`/USB_DP` -> a Windows path): set `MSYS_NO_PATHCONV=1`.
  - pcbnew `board.Add()` / `board.Remove()` inside a script makes the next `GetTracks()` fail (SwigPyObject not
    iterable): one edit per load / save, or collect and apply at the end.

## 1.19.0 - 2026-10-05

What the ServiceOne datasheet layout review found (2026-10-05, ServiceOne `reports/layout_vs_datasheets.md`), folded
into the skill. The board passed DRC (0 errors), parity and the audit, yet had both INA226 sense lines tapping the
power track 8 / 58 mm from the shunt (+20 % / +47 % current error), an 8.192 MHz ADC clock 0.11 mm from a 24-bit
input over 10 mm, and converter / decoupling capacitors reached only through the plane. Tests: run_tests_kicad.py
13 -> 22 (+9); the other suites unchanged (77, 28, 8, 11, 16).

- New `layout_measure.py` (KiCad's Python, read-only):
  - `path`, `return`, `kelvin`, `gap` and `check` over a per-net copper graph that includes vias, T-junctions,
    vias in pads and plane hops;
  - `kelvin` reports the copper shared by the sense and load paths and whether the sense pad reaches the load
    without the shunt pad. It reproduces the ServiceOne numbers (13 / 34 / 4 mOhm before, 0 after the fix);
  - `check` runs the new `layout_checks` block of the project file.
- `route_finish.py`:
  - New options:
    - `--from-pad/--to-pad`: exact pad-centre ends, on the pad's own layers, with the grid aligned to 0.05 mm;
    - `--exclusive` and `--allow`: a dedicated trace, the rest of the same net being an obstacle;
    - `--block-courtyards` and `--courtyard-exempt`;
    - `--avoid`, `--avoid-margin`, `--avoid-exempt` and `--avoid-layers`;
    - `--edge`.
  - Fixed:
    - other-net vias and drilled pads (NPTH included) now keep the board HOLE clearance, not only the copper
      clearance - hole_clearance warnings and a track inside a mounting hole's clearance before;
    - the outline keeps the board copper-to-edge clearance instead of a fixed 0.3 mm (edge errors on a 0.5 mm
      board);
    - new vias get remove_unused_layers / keep_end_layers (audit Q-06 FAIL before).
- `init_project.py` and the template: new `layout_checks` block (`kelvin`, `decoupling`, `separation`, all empty).
- New reference `10_datasheet_layout_review.md`: the procedure, the fixes that worked, the ones that need
  re-placement, auditing by message, and the tool gotchas:
  - pcbnew `SwigPyObject` after Remove;
  - re-filling zones after moving a via;
  - Git Bash rewriting `/NET` arguments (MSYS_NO_PATHCONV=1);
  - sub-micron segments.
- SKILL.md: section "Datasheet layout review"; script list and reference list updated.

## 1.18.0 - 2026-10-04

What the ServiceOne main board routing (2026-10-04) found, folded into the skill. Tests: run_tests.js 77,
run_tests_py.py 28 (+6), new run_tests_kicad.py 13 (KiCad's Python; the pcbnew tools). Every new assertion was
checked to FAIL on the 1.17.1 code.

- `apply_settings.js`: predefined via sizes and track widths are merged with the project's (union) instead of
  replaced (playbook 22 item 5; the project's 0.45/0.15 via had to be re-added by hand); `unconnected_items` is
  never lowered below a project `error` (the template value hid 14 open connections from DRC); an existing
  schematic `connection_grid_size` is kept (a drawing decision); new `--no-schematic`.
- `init_project.py`: writes `via_in_pad`, `shared_pad_gaps`, `plane_net_exceptions`, `detour_limits`,
  `priority_routing`, `router_costs` with empty decision lists. Template `via_in_pad.allowed_refs` emptied (it
  carried the reference board's U1, U3, IC3, contradicting the template's own "every list starts empty").
- `kicad_sexp.collect()`: Edge.Cuts read from gr/fp line, poly, rect, circle and arc (lines only before: a
  polygon outline gave the stitcher no board edge); rule areas, board-level and footprint-internal, returned as
  `rule_areas` with layers, flags and polygon; pads modelled by half their diagonal (round pads by half the
  diameter) and custom pads by their primitives. New helpers `pt_poly_dist`, `on_layer`, `find_kicad_cli`,
  `find_kicad_python`.
- `stitch_planes.py`: vias and stubs that would touch a rule area forbidding them are rejected (a via had
  landed in a push-button keepout).
- New `export_keepouts.py` (export copy only): crystal / inductor corridors, edge band, fiducial keepouts.
- New in the skill, from the BladeOne trial tools: `stitch_residual.py` (with three fixes: same-net hole-to-hole,
  drill-to-track hole clearance, rule areas) and `center_gaps_safe.py` (new `--indices` batch option).
- New `centre_gated.py` (batched, bisected, DRC- and audit-gated centring) and `finish_gated.py` (DRC-gated
  finishing with `route_finish.py`).
- SKILL.md: sections "Export-time keepouts" and "Finishing and centring under a DRC gate"; boxed-in pads;
  `geometry_finish.py --pad-centre-entries` not to be used ungated. Playbook: Addendum A (maintainer).
- Correction of a ServiceOne report finding: the lost keepout rings were not a DSN-export limit - pcbnew saves
  only the first outline of a zone (asserted in run_tests_kicad.py so a KiCad change is noticed).

## 1.17.1 - 2026-10-04

`via` (check 6, via-in-pad), found on the ServiceOne main board:
- Pads with no copper layer are skipped. KiCad's `Package_SON:Texas_DRC0010J` (and similar QFN/SON footprints)
  subdivide the exposed-pad paste into unnumbered `F.Paste`-only pads; a thermal via under one of them was
  reported "via inside SMD pad U10- ... is forbidden", and the loop stopped there before reaching the real pad.
- An exposed pad is also recognised as the dominant copper pad of its footprint (>= 3x the area of every other
  copper pad, footprint with >= 5 copper pads). The 2 mm minimum-side heuristic alone missed the TPS63001 DRC
  pad (1.65 x 2.4 mm) and the ADS131M04 RUK pad (1.7 x 1.7 mm), so listed parts still FAILed.
- Unchanged: the part must be listed in `via_in_pad.allowed_refs` and the via must be on the pad's net; a via in a
  signal pad of a listed part still FAILs.
- Tests: 3 new assertions with a new fixture `vip.kicad_pcb` (73 in total).

## 1.17.0 - 2026-10-04

Renamed from `kicad-golden` to `kicad-routing` (maintainer's decision, Celso Souza, 2026-10-04); no rule or
checker behaviour changed.
- Skill folder, frontmatter name and description: routing-focused, with explicit hand-offs to `kicad-placement`
  and `kicad-schematic`, so the three skills do not trigger on the same request.
- Installation paths and docstrings say `kicad-routing`; the doctor banner reads `KICAD-ROUTING DOCTOR`.
- Kept for compatibility: the standard is still called "golden"; the per-project file keeps its name
  `kicad_golden.project.json`; historical mentions such as "kicad-golden 1.16.0" stay as written.
- New references: `08_routing_playbook.md` (Vladimir Duk's routing playbook, draft 1.1, 2026-09-29) and
  `09_trial_learnings.md` (BladeOne 0.1 trial runs 1 and 2) with its image. The trial's prototype tools are not
  included.
- Includes the local builds 1.16.0-local.1 and 1.16.0-local.2 below as received; their review by the maintainer
  is still open (playbook §22, item 7).
- `golden_settings.json` `skill_version` 1.17.0.

## 1.16.0-local.2 - 2026-09-29 (local fix, not yet reviewed by the maintainer)

`shared-gap` / `between-pads` (check 16): per-part shared-gap exceptions.
- New project parameter `shared_pad_gaps.allowed_parts` lists parts whose pin gaps may carry more than one
  track (BladeOne: the U2 DevKit header at 2.54 mm pitch, and J1). A gap flanked by a pad of one of these
  parts reports `shared-gap` as WARN, not FAIL.
- In such a gap each track must be evenly spaced: its clearance to its nearest neighbour on each side
  (the flank, or another net's track in the same gap on the same layer) must match within 0.01 mm. A gap
  with one track reduces to the ordinary centring test. The FAIL keeps the `between-pads` wording, so
  centring tools read it unchanged.
- The global `shared_pad_gaps.allowed` flag is unchanged.
- Tests: 4 new assertions (70/70).

## 1.16.0-local.1 - 2026-09-28 (local fix, not yet reviewed by the maintainer)

`between-pads` / `route-around` / `shared-gap` (check 16) scope, found on the BladeOne run-2 power stage:
- A segment that starts or ends inside one of its own pads no longer treats the pads abreast of that own
  pad as a gap. Those pads flank the pad, not a gap, and entries 8/9 fix the track at the pad centre there.
  This removes the false FAILs on axial exit stubs from QFN corner pins (unequal neighbours) and on entries
  ending at a pad centre between two unrelated pads.
- The 0.5 mm look-ahead past a segment end now applies only at free ends (junctions or dangling ends),
  not at an end that terminates in same-net copper (pad, zone fill, via). This removes the false FAILs,
  and the derived `shared-gap` FAIL, on stubs that end inside their own switch-node pour.
- "Under two-pad part" is reported only for footprints with two distinct pad numbers. Other same-footprint
  cases are worded "between pads X-a / X-b".
- Gap width: between pads of different parts, or of a multi-pad part, a gap is at most 1.5 mm of free
  copper-edge width (`GAP_MAX_MM`). Wider spaces are open board, and neither `between-pads` nor `shared-gap`
  applies. Under a two-pad part (entry 4) any width still counts. The limit covers the improvements
  document's own example (J3 at 2.54 mm pitch, 0.84 mm free). It replaces the fixed 6 mm centre-distance
  test as the operative filter, which had flagged pads 1.7–4.1 mm apart on BladeOne. The entry-3 fixture
  TP3 moved from y 11.5 (1.9 mm free) to y 10.5 (0.9 mm free) so that it still tests a gap.
- New stats `between_pad_own_pad_flanks_skipped` and `between_pad_wide_gaps_skipped`.
- `golden_settings.json` `skill_version` bumped to 1.16.0, so the audit banner no longer reports 1.15.0.
- Tests: 10 new assertions (63 in total). The regression guards, which must still FAIL, cover:
  - a genuine off-centre pass in a multi-pad footprint;
  - the pour stub's twin with a free end;
  - a header-pitch gap;
  - an off-centre pass under a 1206.

  Against the previous logic, the new fixtures reproduce the three false FAILs seen on the board.
- Severity is unchanged (FAIL). Returning entries 3/4 to WARN, as the improvements document specifies,
  remains an open decision for the maintainer.
- Via flanks: an other-net via counts as a flank. It is measured from its binding keep-out: copper plus
  clearance, or drill plus `min_hole_clearance`, whichever is larger.
- Facing test: two flanks form a gap only when their offset along the track does not exceed the sum of
  their reaches. New stat `between_pad_non_facing_skipped`. Tests: 66 in total. The VIA_CTR/VIA_OFF fixtures
  now place their vias level with the pad.
- `stitch_planes.py` enforces `min_hole_clearance` between a new via's drill and other-net copper, and
  between a stub and other-net drills. `kicad_sexp.rules_from_project()` now reads `min_hole_clearance`,
  default 0, so other callers are unchanged. On BladeOne, the 5 hole_clearance DRC items went to 0
  (114 placed, 20 skipped, where 117 and 17 before). No automated test yet; validated by KiCad DRC.

## 1.16.0 - 2026-09-28 (rev P: the improvements review)

Eleven rules collected by hand from routing BladeOne 0.1 (`kicad-golden-improvements.zip`, sent to the
maintainer 2026-09-25), each rewritten from a one-line request into a normative rule, an audit check and
(where the source's own test found it tractable) a fixer. Source doc's own conclusion after trying all
eleven on a fresh route of BladeOne 0.1: entries 1, 2, 7 and the crystal/inductor half of entry 4 are
fully automatable; the rest need tooling that did not exist before this rev, and naively applying all of
them by hand made completion worse (98.3% -> 96.3%, 6 -> 13 open connections) because nothing enforced
the order or the limits below. This rev adds that tooling and those limits.

**New Core rules** (SKILL.md): Fab-layer hygiene (values hidden, references centred/shrunk/added — entries
1, 2); between-pad centring for tracks passing between two unrelated pads or a two-pad part's own pads,
and a hard FAIL on any other net's track under a crystal or inductor's courtyard on its mounted side
(entries 3, 4); pad entries rewritten as one straight 8-direction segment ending exactly at the pad
centre, axial preferred on elongated pads, necked to the pad's smallest dimension inside the clearance
area (entries 5, 8, 9 — **supersedes Q-01/Q-02**, no more exemption for pads >= 2 mm); route around a
component instead of under it within a configurable detour budget (entry 10); spread tracks evenly across
free space (entry 11); at most one track through a pad gap unless the project opts in (entry 6, new
pre-routing question, Q-16); plane-net pads are via-only, promoted from an unenforced decision-rules note
(D3) to an audited Core rule (entry 7, Q-17).

**New scripts**: `fab_layer_fix.py` (entries 1, 2) and `geometry_finish.py` (entries 3-11, see SKILL.md
§Post-Routing Geometric Refinement for what each flag does and does not fix automatically).
`route_freerouting.py` now filters plane nets out of the DSN by default (entry 7) and a new
`--crystal-inductor-keepouts` step in `geometry_finish.py` covers those courtyards before export.

**New audit checks** in `kicad_audit.js` for all eleven entries — see the check names `fab-values`,
`fab-refs`, `between-pads`, `crystal-inductor`, `pad-entry` (rewritten), `shared-gap`, `plane-net`,
`route-around`, `spreading`. `tests/run_tests.js` grew fixtures and assertions for each.

**New project parameters** in `templates/kicad_golden.project.json`: `shared_pad_gaps.allowed` (Q-16),
`plane_net_exceptions.allowed` (Q-17), `detour_limits` (Q-18).

**The source material's own test results**, reproduced here because they set expectations for
`geometry_finish.py` honestly rather than promising a clean sweep — measured trying all eleven rules by
hand on a fresh route of BladeOne 0.1 (KiCad 10, JLCPCB 4-layer 1 oz), 2026-09-25:

| Rule | Current skill (before this rev) | Hand-applied test board |
| --- | --- | --- |
| 1. Visible values on Fab | 165 | 0 |
| 2. Fab references off-centre / beyond outline | 11 / 8 | 0 / 0 |
| 4. Tracks under crystals or inductors | 3 | 0 |
| 7. Surface links joining plane-net pads | 30 links, 122 pads | 8 links, 17 pads |
| 10. Tracks passing under a part | 33 | 31 |
| 3. Off-centre tracks in gaps between pads | 169 | 199 |
| 4. Off-centre tracks under two-pad parts | 11 | 16 |
| 5. Entries wider than the pad's smallest dimension | 14 | 12 |
| 6. Pad gaps carrying 2+ tracks | 28 | 29 |
| 8. Entries not ending at the pad centre | 3 | 28 |
| 9. Non-axial entries into elongated pads | 63 | 70 |
| 11. Tight runs beside free space | 40 | 44 |
| Routing completion | 98.3% (6 open) | 96.3% (13 open) |

Reading this table straight: entries 1, 2, 4 (ban) and 7 improved sharply and stayed improved; entries 3,
4 (centring), 5, 6, 8, 9 and 11 barely moved or got worse **by hand**, because nothing in the pipeline
before this rev implemented them — this is the reason those checks now exist as both an audit rule and a
`geometry_finish.py` flag, not just a rule. Entry 10 as a pre-routing keepout stalled Freerouting at 31
unrouted for 10 passes; as a post-import fix it rehomed 10 of 32 offending runs. Treat `--route-around`
and `--spread` as best-effort tools that reduce a count, not ones that are guaranteed to zero it — read
the report `geometry_finish.py` prints rather than assuming success.

## 1.15.0 - 2026-09-21 (rev O: finishing the last connections becomes a tool)

The standard forbids a second Freerouting pass over routed copper (it corrupts via padstacks) and
then said "route the remainder by hand" without offering anything to do it with. **New
`scripts/route_finish.py`**: a grid maze router that takes ONE connection at a time, on the
45-degree lattice, so each result is DRC-checkable before the next. Used on the test board it took
9 unrouted to 3 with **zero** new DRC violations.

Three things it encodes, all measured rather than assumed:

- **`--safety` is a real parameter, not padding.** Obstacles are dilated by
  (half-width + clearance + safety); without the safety term a grid cell centre sits up to
  `GRID*sqrt(2)/2` off the true edge and DRC reports a near-miss - **0.0594 mm against a 0.1 mm
  rule** at 0.1 mm grid. Raising it too far sealed five nets that had routed a moment earlier.
  `--grid 0.05 --safety 0.05` is the compromise.
- **Routing ORDER changes the outcome.** Same 8 connections, three orderings: **3 / 4 / 4** left
  unrouted. Long-haul-first and congested-corner-first each won a net the other lost. No ordering
  is right in general; try two and keep the best.
- **The lattice check is load-bearing.** The script exits 3 without writing if any segment is not
  H/V/45. It caught two genuine bugs during development, including a zero-length step at a via that
  made the collinearity test merge an entire run into one skewed segment.
  `tests/run_tests_py.py` (18 -> 22) now asserts the check exists AND runs before any board
  mutation - a gate after the write would be decorative.

**New rule: a geometric snap must be scoped to what it is repairing.** Measured twice on this
standard: once dragging interior nodes onto pads (42 off-lattice segments from zero), and again
moving sub-micron endpoints on three uninvolved nets while fixing one 198 nm gap - `geometry 3,
angle 2` FAILs from a one-endpoint repair.

MANUAL.md section 5 rewritten: finishing step, the user-layer check, the `Edge.Cuts` profile trap,
and X2 verification. Five new rows in the troubleshooting table. Also repaired shell line
continuations that an earlier edit had flattened in both documents.

## 1.14.2 - 2026-09-21 (rev N.2: user layers belong in the fab package when they carry content)

1.14.0 said to name `--layers` explicitly and listed only copper/mask/silk/paste/profile. That
silently drops a User.4-style fabrication drawing. Refined: enumerate what is actually on each user
layer, then include the populated ones by untranslated name (`User.1`, `Cmts.User`, `Dwgs.User`),
which export as `%TF.FileFunction,Other,User` / `Other,Comment` / `OtherDrawing,Comment`. Empty
ones stay out - the original warning was about the nine empty `User_*` files, not about content.

Also documented: **a dimension object on `Edge.Cuts` is plotted into the profile gerber**, where a
fabricator reads it as outline geometry. DRC flags it `text_on_edge_cuts` at error severity.
MEASURED on one board: 3 orthogonal dimensions sat on `Edge.Cuts` beside the single real outline
shape, while 5 more sat correctly on `User.1`.

## 1.14.1 - 2026-09-20 (rev N.1: hand-drawn copper is invisible to the router)

A `PCB_SHAPE` on a copper layer is not exported in the Specctra DSN, so Freerouting routes through
it. Found the hard way: a GND track crossed a pre-existing 0.2 mm hand-drawn line on F.Cu and
produced a real short (`nets GND and Net-(D10-A1)`) that the golden audit passed and
`route_report.py` scored as fully connected - only `kicad-cli pcb drc` caught it. SKILL.md now
carries the trap, the detection command, and the two fixes (convert the shape to a track, or cover
it with a keepout so it reaches the DSN).

Corollary worth stating: **completion percentage is not correctness.** route_report counts ratsnest
connections; a short is not a missing connection.

## 1.14.0 - 2026-09-20 (rev N: Manufacturing Outputs Generation)

**New mandatory final phase.** After the post-routing audit passes and the board is saved, the
fabrication outputs are generated automatically — a routed board that has not been exported is not
a deliverable. SKILL.md gains *Manufacturing Outputs Generation*; MANUAL.md section 5 and the
single-pass pipeline block carry the commands.

**The requested flag does not exist.** The rule was specified as
`kicad-cli pcb export gerbers --use-gerber-x2 <board>.kicad_pcb`. KiCad 10 rejects that:

    Unknown argument: --use-gerber-x2

**X2 is already the default.** The only format flag is the opt-*out*, `--no-x2`. So the correct
action for X2 output is to pass no format flag at all. Verified on 10.0.6, same board, same command,
only `--no-x2` differing:

| | first header line | `%TF.` attributes |
|---|---|---|
| default | `%TF.GenerationSoftware,KiCad,Pcbnew,10.0.6*%` | **6** |
| `--no-x2` | `G04 #@! TF.GenerationSoftware,...` | **0** (demoted to X1 comments) |

Had the flag been documented as given, every export would have failed outright.

**Two additions the rule needs to be manufacturable:**

- **Drill files.** Gerbers contain no holes. The phase runs `kicad-cli pcb export drill` with
  `--excellon-separate-th` (plated / non-plated split, which is what fabricators expect) and drill
  maps. The gerber export also writes the X2 `.gbrjob` job file, which ties the layer set, stackup
  order and drills together — it ships with the package.
- **An explicit `--layers` list.** With none, KiCad plots every *enabled* layer: on the test board
  that was `User_1`..`User_9`, both `Courtyard`, both `Fab` and `Adhesive` — none of which belong in
  a fab package. Untranslated names are used, and a renamed inner layer still resolves correctly
  (`In1.Cu` renamed `GND` exports to `-GND.g1`).

**Gated on the audit, and on zone fill.** The phase refuses to export while the audit reports a FAIL
— exporting a board that failed the standard moves the defect downstream, where it costs money
instead of minutes. `--check-zones` is passed so a stale zone fill cannot plot the old copper
silently.

## 1.13.2 - 2026-09-20 (rev M.2: auto-clearance did not survive the save; via_cost re-measured end to end)

**`--auto-clearance` left the raised clearance on the board.** It raises the netclass clearance for
the DSN export, restores it before the router runs, and logs "restored" - then `SaveBoard` at the
end of the import rewrites the .kicad_pro from the project settings pcbnew cached back at
`LoadBoard`, putting the raised value back. Measured: a 3-candidate sweep (0.150/0.200/0.250) left
both netclasses at **0.250 mm instead of 0.100**, having logged "restored" three times. Every later
DRC would have run against an inflated clearance, and the next run's clearance floor is derived
from it.

- **Fixed**: the restore is re-asserted AFTER `SaveBoard`.
- **`tests/run_tests_py.py` +3 assertions (15 -> 18)**: parses route_freerouting.py and requires a
  `restore_clearance` call both before the export and after the save.

This is the same cached-project hazard already documented for `SaveBoard`; the lesson is that
*writing a file pcbnew also owns* is never final until after the last save.

**MANUAL.md: section 3 now opens with the prompt.** Most bad runs are bad prompts. The section
carries a worked prompt (board file, fabricator + layers + copper, the stackup layer by layer, what
is locked, whether to rip up existing copper, BGA presence, the workflow steps, and a truthful
finish line), a table saying what each line prevents, and a table of nine weak prompts with what
actually goes wrong. The failure modes are the measured ones: no fabricator = audit pre-flight FAIL
and routing refused; layer count without layer *types* = signal tracks on a plane, an audit FAIL
found only at the end; a guessed clearance = a wasted router run, because clearance is not monotonic
(0.15 -> 36 unrouted, 0.20 -> 59); "route it 100%" = a target the tool does not hit, since the best
automated result on that board left 2 of 350.

Also documents that **there is no rip-up script**: "rip up the existing tracks" is carried out
directly, and `.bak_prerouting` is written when routing starts, i.e. *after* the tracks are gone -
so the user's own backup has to exist first.

**MANUAL.md gains section 0 - installing the tools.** The manual began at "prepare your board",
which assumed a machine that was already set up. Section 0 now covers, in dependency order: update
KiCad first (it supplies both `kicad-cli` and the bundled Python, so updating it later wipes
whatever you pip-installed); Freerouting and why the native launcher beats the `.jar` (the jar needs
Java 21+, and a machine whose only Java is 8 cannot run it at all - the launcher carries its own
runtime); installing `shapely`/`matplotlib` into KiCad's Python rather than the system one, with the
per-interpreter trap spelled out; and the `kicad-cli pcb export svg` + Inkscape layer-render
workflow, which is optional but is what catches geometry errors that every numeric check passes.
Ends with the doctor run against both interpreters, showing real output and how to read it.
Section 0.6 covers asking Claude Code to do the installs, including that it should be made to ask
before each one. Numbered 0 deliberately: sections 1-7 keep their numbers and every existing
cross-reference stays valid. winget IDs verified against the live catalogue.

**via_cost 150 re-measured through the whole pipeline, on a bare board.** The earlier entry stopped
at the pre-stitch ratsnest, which flattered it:

| | via_cost 50 | via_cost 150 |
|---|---|---|
| unrouted, full pipeline | **2  (99.43%)** | 9  (97.43%) |
| routing vias | 105 | **72  (-31%)** |
| tracks necked to 0.15 mm | **20** | 44 |
| golden audit | **PASS** | FAIL - 16 neckdowns |
| DRC clearance errors | 4 | **0** |
| DRC shorts / dangling vias | **0 / 0** | 1 / 5 |

**Denied a via, the router necks the track down instead** - that is where part of the -31% comes
from. Widening the 16 offending segments back to 0.2 mm restored the audit to PASS and introduced
**no** new DRC violation, so the narrowing was never needed. SKILL.md and MANUAL.md now say to
re-audit after changing `via_costs`, and no longer present 150 as a straight improvement.

## 1.13.1 - 2026-09-20 (rev M.1: the --auto-rules wiring was broken in 1.13.0)

**1.13.0's headline feature did not work from route_sweep.py.** `--auto-rules` generated a correct
.rules file and then died before the router ran:

    NameError: name 'FR_CMD' is not defined

The `-dr` append in route_freerouting.py was written against a variable that does not exist
(`FR_CMD` rather than `cmd`), and one indent level too far left, which also pulled the whole
routing block inside `if RULES:`. Every sweep candidate failed; the sweep dutifully reported
"every candidate failed; board restored" and restored the bare board.

- **Fixed** the append: correct name, correct block.
- **`tests/run_tests_rules.py` +3 assertions (13 -> 16)** that would have caught it.

Why no existing test caught this is the part worth keeping. The code is valid Python, so no syntax
check sees it, and it is not reachable by the obvious smoke test: the only test covering
`--auto-rules` used `--export-only`, which returns *before* the router is ever invoked. The new
assertions therefore do not run the router at all - they parse route_freerouting.py with `ast` and
check that the statement appending `-dr` targets the same variable, in the same block, as the one
built with `-de`/`-do`. Verified to FAIL against the broken shape and PASS against the fixed one.

**The lesson generalises: a test that stops short of the side-effecting call tests the argument
parser, not the feature.** Any future flag that only shows up in a subprocess argv needs either a
stub executable or a structural check like this one.

## 1.13.0 - 2026-09-20 (rev M: autorouter costs become project state)

- **route_sweep.py now generates and passes the .rules file by default** (--no-rules opts out),
  so a clearance sweep is reproducible instead of inheriting GUI state.
- **MANUAL.md**: new section 3 step putting via_cost ahead of phased routing, the GUI-settings
  checklist at 2.9b, and two new entries in the troubleshooting table.
- **INSTALL.md**: rules_writer.py and run_tests_rules.py added to the manifest; five suites.

Freerouting's autorouter costs live in the GUI session, not in freerouting.json, so a batch run
inherits whatever the last person clicked and two engineers get different boards from the same
inputs. `-dr <file.rules>` reads them from a file instead.

- **`scripts/rules_writer.py`** (new): generates the `.rules` file - via cost, plane via cost,
  rip-up cost, per-layer preferred direction and trace costs - from `router_costs` in
  kicad_golden.project.json. Reads the design name and layer types out of the DSN rather than
  guessing. Runs on any python.
- **`route_freerouting.py --auto-rules`** generates and passes it; `--rules FILE` for an explicit one.
- **`router_costs`** added to the per-project template.

- **The quoting trap, which fails silently.** The design name in `(rules PCB "<name>")` MUST be
  quoted: unquoted, Freerouting's reader stops at the first space, the designName check fails and
  the ENTIRE rules file is ignored with no error - the run looks completely normal and none of the
  costs apply. Verified: unquoted gave `designName not matching ... got 'BladeOne'`; quoted gave no
  warning. Any board with a space in its name would have hit this.

- **MEASURED - via cost is a bigger lever than the phased-routing machinery.** One 4-layer
  350-connection board, identical inputs, only `via_costs` changed 50 -> 150:
  total vias 105 -> 72 (-31%), vias on the 8 key nets 24 -> 11 (-54%), length of those nets
  896.6 -> 763.5 mm (-15%), unrouted 36 -> 43 pre-stitch. For comparison, rev L's two-phase routing
  reached 10 vias on the same 8 nets - **one parameter did essentially the same job, with shorter
  nets, and no locking contract to verify.** SKILL.md now says to try via_costs first and treat
  phased routing as the fallback.

- **Documented what is NOT reachable**: automatic neckdown, vias-snap-to-SMD-pad-centers and
  drag-components are interactive-editor state - absent from the rules vocabulary, from
  freerouting.json and from the CLI flags, confirmed by searching the shipped classes. The standard
  defends against their effects rather than their settings, which catches the defect regardless of
  which tool or person produced it.
- Also confirmed: Freerouting forces plane layers inactive itself, so a rules file cannot open a
  plane to signal routing.
- **`tests/run_tests_rules.py`** (new, 13 assertions), including the quoting guard.

## 1.12.0 - 2026-09-19 (rev L: opt-in priority-based iterative routing)

Route the nets you care about first on an empty board, lock them, then route the rest around
them. Added as OPT-IN after measuring it, not before.

- **The lock contract is verified, not assumed.** `SetLocked(True)` exports to Specctra as
  `(type fix)` and Freerouting honours it: 225/225 phase-1 items byte-identical after a full
  second pass, and 165/165 on an independent second trial. Zero moved. The post-import geometric
  repair also leaves locked copper alone.
- **`scripts/lock_nets.py`** (new): locks a phase's copper AND fingerprints its exact geometry;
  `--verify` proves a later phase did not move it. A silent lock failure would corrupt precisely
  the nets the phase existed to protect, so the verify is part of the procedure, not an extra.
- **`scripts/dsn_filter.py`** (new): Freerouting has no "route only these nets" switch, so a
  phase is expressed by filtering the DSN's `(network)` block. Runs on any python.
- **`SKILL.md`**: new section, explicitly OPT-IN, with the mandatory order
  `route -> repair -> audit -> LOCK -> next phase`. Locking before the repair either leaves the
  phase unrepaired or defeats the lock; the natural reading of "generate, audit, lock" gets this
  wrong.
- **`priority_routing.critical_nets`** added to the per-project template, empty by default.

- **MEASURED, on one 4-layer 350-connection board** - recorded as an observation, not a default:
  critical-net vias HALVED (24 -> 10) and the figure was identical under two independently derived
  critical sets, so it is not run-to-run variance. Cost: unrouted 2 -> 11/12. **That cost did not
  shrink when the critical set was halved (16 nets -> 8).** The cost is not how many nets route
  first; it is that phase-1 nets take globally direct paths that become walls for the remainder.
  Guidance is therefore: pick the SMALLEST set whose via count you care about, and judge the
  result on critical-net vias, not on completion, which gets worse.

- **Three DSN parsing facts learned the hard way**, all now encoded in tests:
  a Specctra DSN is NOT KiCad s-expression - backslashes are literal (the header carries Windows
  paths) and `(string_quote ")` uses a bare quote as a value, so an absolute paren-balance check
  reports a healthy DSN as broken; class member lists contain quoted names with spaces, which a
  plain `.split()` shreds; and net names contain parentheses (`Net-(U7-EN)`), so finding the first
  `(` to split a class header must skip quoted regions.
- Disclosure: the first experiment ran with a DSN whose `kicad_default` member list was truncated
  by the parenthesis bug above. It was checked and found behaviourally inert - that class's rule
  is identical to the DSN's global default rule - so the measured results stand.
- **`tests/run_tests_phased.py`** (new, 11 assertions) covers all three parsing hazards.

## 1.11.0 - 2026-09-19 (rev K: the skill stops shipping one board's design to every other board)

Written for reuse across projects. Until now most defaults were captured from the boards the
standard was extracted from, and when they did not match a new design they failed SILENTLY.

- **The netclass template no longer carries another board's buses or rails.** It shipped three
  SDRAM bus classes and patterns for six specific supply names. Applied to a different design
  those patterns match nothing while the new board's own rails stay on Default and route at
  signal width - no FAIL, no WARN, just under-sized power copper on a manufactured board. The
  template now defines Default, POWER_DC and POWER_AC only, and ships ZERO patterns.
- **`scripts/netclass_propose.py`** (new): derives POWER_DC patterns from the actual netlist.
  Distinguishes current-carrying rails from sense/feedback taps, because a divider tap looks like
  a supply and must not be widened. Exits 1 when a rail would be left on Default.
- **The audit now FAILs on an unclassed current-carrying rail**, where it previously emitted a
  loose warning based on a pattern that also matched every `Net-(...)` autoname. Pad-count aware,
  sense-taps excluded.
- **A rule that matches no net is now a WARN.** Length groups, diff-pair rules, via-budget
  patterns and netclass patterns inherited from another design match zero nets and then report a
  clean pass while auditing nothing. Silence was indistinguishable from success.
- **The per-project template ships EMPTY lists**, not a worked example from another board.
  **`scripts/init_project.py`** (new) seeds it from a real board and records that board's bus
  candidates, diff-pair candidates, long-haul nets and clearance floor as observations to decide
  from - it never invents a length group or a via budget.
- **`scripts/doctor.py`** (new): reports what each interpreter can actually do. On the development
  machine shapely was installed in KiCad's python and NOT in the system one, while rail_zones.py
  was documented as running on the system python - so the tool reported shapely missing when it
  was present. Also reports the Java version against the Freerouting jar's requirement.
- **KiCad 10 net enumeration fixed.** Several checks walked the top-level `(net id name)` table,
  which does not exist on KiCad 10 - they saw zero nets and reported a vacuous pass. The net
  universe is now derived from the items actually on the board.
- **Audit verdict block**: a passing board still emits hundreds of findings. The tail now states
  plainly what blocks, what is only advice, and the numbers that decide manufacturability.
- **`tests/run_tests_boards.py`** (new, 8 assertions): 2-layer and 6-layer boards. Every previous
  fixture was 4-layer, so those branches of the stackup rules had never been executed by a test.
- **`tests/run_corpus.py`** (new): regression-tests the audit against REAL boards and reports drift
  in FAIL/WARN counts and tracked stats. Synthetic fixtures only contain defects their author
  already imagined - the footprint-internal keepout bug survived three releases for that reason.
  `tests/corpus/` ships empty by design; boards are yours, often proprietary, and large.
- **De-identified**: all references to the two source project names were removed from the rulebook,
  reference documents, templates, scripts and settings metadata. The only remaining occurrences are
  filenames inside a source archive in `review_inputs/`, which is input material, not skill logic.
- Tests: 38 node + 15 python + 8 board-stackup assertions.

## 1.10.0 - 2026-09-19 (rev J: make "route it completely" measurable, and stop losing runs to guesswork)

Written after a full route of `a 4-layer 350-connection test board` reached 348 of 350 connections
(99.4%) but took four router runs to get there. Every item below is a thing that cost a run.

- **`scripts/route_report.py`** (new): the completion metric the workflow never had. Connections
  routed out of `pads - 1` overall and per netclass, against KiCad's own unconnected count. Also
  reports the three routability hazards - footprint-local clearance overrides, long-haul nets, and
  plane-stitch gaps - plus a via padstack inventory. `--fail-on-gap` makes it a CI gate.
- **Footprint-local clearance now reaches the router.** A footprint may carry `(clearance X)`, and
  the Specctra DSN has no field for it, so the router undercuts that part and the violations only
  appear after the import. On the 4-layer test board one VQFN-29 produced 21 of 21 clearance violations this way.
  `route_freerouting.py --auto-clearance` raises every netclass clearance to the largest local
  override for the export and restores the golden values as soon as the DSN is written.
  `--clearance MM` forces a specific value.
- **Documented the lever that actually works.** The DSN clearance comes from the NETCLASS, not from
  the `min_clearance` board rule. Editing `min_clearance` produces a byte-identical DSN and costs a
  full router run to discover.
- **`scripts/route_sweep.py`** (new): runs the router once per candidate clearance and scores each
  with `route_report.py`. Clearance is not monotonic - measured 0.10 -> 40 unrouted, 0.15 -> 36,
  0.20 -> 59 - so the right value has to be measured. The floor never drops below the local override.
- **Padstack integrity gate.** A DSN/SES round-trip over already-routed copper returned 17 vias with
  a 0.250 mm pad on a 0.300 mm drill (annular -0.025 mm), which KiCad saves without complaint.
  `route_freerouting.py` now refuses to save such a board and points at the backup;
  `route_report.py` flags it `<< INVALID`. SKILL.md says plainly: never top up an already-routed
  board, route from bare or finish by hand.
- **Long-haul nets are surfaced before routing.** Autorouters serve short nets first and starve long
  ones. the 4-layer test board's `+BATT` spans 69 mm and its far pad defeated a corridor search, a hand-built
  path and a dedicated router pass. Named up front it is ten minutes of manual work.
- **Two pcbnew traps documented**: `PCB_VIA.GetWidth()` without a layer argument trips an assertion
  that can pop a modal dialog and hang a headless script (use `GetFrontWidth()`), and `pcbnew`
  caches the project by path, so a `.kicad_pro` edit between `LoadBoard` and `SaveBoard` is silently
  reverted. Both cost debugging time during this work.
- **`rail_zones.py` prerequisite corrected**: `shapely` lives in KiCad's python on the reference
  machine, not the system one, so running it on the system interpreter reports it missing when it
  is in fact installed.
- **Shared helpers** `footprint_local_clearances`, `clearance_floor` and `sweep_candidates` moved
  into `kicad_sexp.py` so the router and the sweep cannot drift apart.
- **Tests**: new `tests/run_tests_py.py`, 15 assertions, dependency-free and pcbnew-free. Covers the
  logic that decides how the router is driven, including that a pad-level `(clearance ...)` must not
  be read as a footprint override - doing so would raise the export clearance to 0.9 mm on the test
  fixture and cripple routing. The Node suite stays at 37.

## 1.9.0 - 2026-09-18 (rev I: footprint-internal keepouts are found, and reported out loud)

Found on `a 4-layer 350-connection test board` when the user asked why three keepout zones had not been
respected. They had been respected - but nothing had ever checked them, and nothing said so.

- **The audit was blind to footprint-internal rule areas.** `kids(pcb,'zone')` returns only top-level
  zones, so a board whose keepouts all live inside footprints reported `keepout_zones: 0` and emitted no
  finding. the 4-layer test board has 3 such keepouts (J1 x1, SW3 x2). `kicad_audit.js` now scans footprints too;
  their polygons carry absolute coordinates, so no transform is needed.
- **Silence is no longer a valid answer.** The audit now always emits an INFO naming the keepout count
  and how many are footprint-internal - including "zero rule_area keepouts, nothing to check". The
  standard already required saying so; nothing enforced it.
- **`SKILL.md`**: new MANDATORY pre-flight section "Keepout Enumeration", covering the enumeration
  idiom for both `pcbnew` and the s-expression path, the `items_not_allowed` severity trap (an `ignore`
  there makes KiCad's DRC silently pass violations), and the requirement to report measured margins
  rather than a bare "no violations".
- **Documented two related blind spots**: neither the Specctra DSN export nor `stitch_planes.py` knows
  about footprint-local `(clearance ...)` overrides, so both work to the board-global value. On the 4-layer test board
  this put a stitching stub 0.075 mm from a U6 pad whose footprint demands 0.15 mm, and produced 21 of
  the clearance violations in the first routing run.
- **Tests**: 35 -> 37 assertions. The good fixture now carries a footprint-internal keepout, and two new
  assertions check that it is counted and that the audit states the count. Both fail against 1.8.0.

## 1.8.0 - 2026-09-18 (rev H: high-density via allowance on 4-layer and denser boards)

Found while routing `a 4-layer 350-connection test board` (KiCad 10.0.6, Freerouting 2.4.1, JLCPCB 4L-1oz).

- **The golden via floor was unbuildable on fine-pitch parts and the standard was fighting itself.**
  `min_via_diameter` 0.45 / `min_via_annular_width` 0.10 cannot be placed beside a DFN/QFN pad at
  0.4-0.5 mm pitch, so `stitch_planes.py` fell back to the fabricator minimum (0.25 / 0.15) and every
  via it placed became a DRC error against our own rules. Measured: 17 of 113 stitching vias across 12
  footprints, 34 audit FAILs, none fixable by routing - only by deleting the plane connection.
- **`apply_settings.js`**: on profiles with `layers >= 4` the fabricator's `min_via_diameter` and
  `min_via_annular_width` now REPLACE the template values instead of being `Math.max()`'d with them
  (the same treatment `min_through_hole_diameter` received in rev D). JLCPCB 4L/6L therefore yields
  0.25 / 0.05. 2-layer is unaffected - its profile limits (0.5 / 0.1) are stricter and still win.
- **`apply_settings.js`**: on 4L+ the profile's minimum via is inserted into `via_dimensions`. Without a
  predefined entry `kicad_audit.js` still FAILed a legitimately placed via with "matches neither its
  netclass nor a predefined via size", so the rule change alone would not have cleared the audit.
- **`SKILL.md`**: new MANDATORY section "High-Density Via Allowance (4-layer and denser)", plus the core
  Vias bullet now points at it. The allowance governs via SIZE only - `min_through_hole_diameter`,
  hole-to-hole, clearance and the Q-06 flags are untouched.
- Scope note: this is the only place the standard deliberately relaxes a limit rather than tightening it.
  It is justified by manufacturability, not convenience - JLCPCB builds 0.25 / 0.05 on 4L+ as a standard
  service, so the stricter rule bought no yield margin and cost connectivity.

## 1.7.0 - 2026-09-17 (rev G: the post-router toolchain becomes executable)

1.6.0 documented what to do after a Specctra import; 1.7.0 ships the tools that do it. All four were
used end to end on `a 6-layer FPGA devboard` before being generalised.

- **`scripts/kicad_sexp.py`** (new): shared depth-tracking s-expression parser plus `verify_write()`,
  which refuses to save unless parens balance, the top-level census matches the declared delta, protected
  blocks (footprints, graphics, setup) are byte-identical and indentation is uniform.
- **`scripts/stitch_planes.py`** (new): places the stitching vias Freerouting never emits. Plane nets are
  discovered from the board's inner-layer zones rather than configured. On the reference board it found
  all five (+1.2V, +3.3V, FPGA_1.2V, FPGA_2.5V, GND) unprompted and cut unconnected 129 -> 68.
- **`scripts/repair_import.py`** (new): Q-06 via flags, sub-minimum width raise, optional DRC-driven
  deletion, and the dangling-stub convergence loop. Locates `kicad-cli` on its own. Reports regressed
  nets, because removing copper to satisfy a rule is a trade and the report must say so.
- **`scripts/rail_zones.py`** (new): interleaved-rail polygon zones with the two rules from rev F encoded
  as behaviour - obstacles veto corridors instead of cutting them, and the incumbent plane is verified by
  connected components. Exits 3 rather than stranding plane vias, exits 4 when shapely is absent.
- Shapely stays an optional dependency behind a guarded import; everything else runs without it.
- Generated `tests/fixtures/*` remain excluded from the package (they are rebuilt by `run_tests.js`).

## 1.6.0 - 2026-09-17 (rev F: plane stitching, zone-outline geometry, visual verification)

Findings from a full route of `a 6-layer FPGA devboard` (KiCad 10.0.6, Freerouting 2.4.1).
Final state: 605 of 665 ratsnest connections (91.0%), 206 of 228 nets complete.

- **Freerouting places no vias on plane nets.** Documented as a mandatory post-import step with the
  measured evidence (180 GND + 100 +3.3V SMD pads, 0 vias on either). Stitching them converted 129
  unconnected to 68 with zero new violations. Diagonal placement is required at fine pitch.
- **Fine-pitch channel arithmetic** added: at 0.8 mm pitch / 0.45 mm pads, max track is 0.150 mm
  orthogonal and 0.481 mm diagonal, so a 0.6 mm POWER_DC track cannot cross a BGA at any router effort.
- **Hole-to-hole is drill-edge to drill-edge**, not centre to centre. Comparing centres produced 0.077 mm
  spacing on real vias before it was caught.
- **Zone outlines must not have obstacles subtracted.** The filler already clears them; subtraction gave
  polygons of 30 x 9 mm bbox with 814 vertices and 0.15 mm2 area. Added simplify, sliver rejection
  (area >= 1 mm2, fill ratio >= 0.08) and exterior-ring-only export.
- **Starvation check corrected**: test the incumbent plane's connected components, not point containment,
  and include the plane being carved. Omitting it cost 8 +3.3V connections.
- **Visual verification** via `kicad-cli pcb export svg` + Inkscape/matplotlib. Caught a 20 mm plane
  sliver that every numeric check passed.
- **Optional shapely/matplotlib** in KiCad's Python, with a guarded-import requirement so the shipped
  tooling still runs without them. Noted that Shapely tied the convex-hull approach on connectivity; its
  value is verification, not routing.
- **Edge.Cuts sanitization** extended to footprint-internal cutouts (27 LED openings, 108 `fp_line`
  items on the reference board) and to checking that the clearance rule is geometrically satisfiable.
- **Copper removal**: dangling stubs must be cleaned iteratively to convergence and zones re-filled;
  regressed nets must be reported. Connections are counted as `pads - 1`, not as a DRC delta.

## 1.5.0 - 2026-09-17 (rev E: automated Freerouting round-trip)

Verified against KiCad 10.0.6 and Freerouting 2.4.1 on Windows.

- **`kicad-cli` cannot do Specctra in KiCad 10, but `pcbnew` can.** The rev D claim that the DSN/SES
  round-trip "is a GUI operation the user performs" was **wrong** and is retracted. `pcbnew` exposes
  `ExportSpecctraDSN(BOARD, path)` and `ImportSpecctraSES(BOARD, path)` - two-argument overloads that
  take an explicit board and therefore work headless. Confirmed present in 10.0.6.
- **New `scripts/route_freerouting.py`**: backs up the board, fills zones, exports the DSN, discovers and
  runs Freerouting, verifies the `.ses` is non-empty, imports it, re-fills and saves. Aborts with the board
  untouched on timeout or an empty session. Flags: `--fr-cmd --passes --timeout --threads --outdir
  --export-only --import-only --no-fill`.
- **Portable router discovery, no hard-coded paths**: `--fr-cmd` -> `FREEROUTING_CMD` -> `PATH` ->
  per-OS install locations (Windows `%LOCALAPPDATA%`/`%PROGRAMFILES%`, macOS `/Applications`, Linux
  `~/.local/share`, `/opt`) -> `freerouting*.jar` via `java -jar`. Native launcher preferred: the jpackage
  build bundles its own runtime (Java 25 in 2.4.1) while the jar needs a system Java 21+, and the script
  refuses an too-old java with a clear message instead of failing obscurely.
- **Interpreter split documented**: `pcbnew` is a compiled extension bound to KiCad's Python
  (`C:\Program Files\KiCad\10.0\bin\python.exe`). The previous blanket "use `py`" tooling note was
  misleading and is corrected; `pip install pcbnew` is not a thing.
- **DSN plane-layer check added**: the exporter maps KiCad layer types into the DSN, so planes typed
  `power` come out as `(type power)` and Freerouting will not route them. A plane left typed `signal`
  yields inner-layer tracks (a FAIL). Verified on the reference board: `F.Cu`/`B.Cu` `(type signal)`,
  `In1.Cu`/`In2.Cu` `(type power)`.
- Freerouting 2.4.1 CLI recorded: `-de <in.dsn> -do <out.ses> -mp <passes> -l en [-mt <threads>]`.
  Note `-l en` - the help and logs otherwise follow the system locale.
- The mandatory post-import repair (45 deg lattice, pad-entry snapping, neckdown removal, via flags,
  no inner-layer tracks) is unchanged from rev D but is now explicitly *not optional* and must be
  quantified in the report.

## 1.4.0 — 2026-09-17 (rev D: KiCad 10 syntax, Edge.Cuts sanitization, BGA plane policy)

Discovered during a KiCad 10 unroute/re-route attempt on `a 6-layer FPGA devboard` (file format 20260206).

- **KiCad 10 s-expression syntax** documented in `SKILL.md`: zone nets are `(net "NAME")` (not `net_name`); via tenting is nested `(tenting (front yes) (back yes))`; track/pad nets are name strings, so there is no top-level net table. Detect the format from `(version …)` before reading or writing.
- **Known stale checks** in `kicad_audit.js` <= 1.3.0 listed as false positives on KiCad 10 boards: `zone without net`, the downstream `In1.Cu carries no GND zone ()`, and `via tenting is not "front back"`. Verified by auditing an unmodified KiCad 10 board, which reproduced all three. **Fixed in `kicad_audit.js`**: new `zoneNet()` helper reads `(net "NAME")` on KiCad 10 and `net_name` on KiCad 9, type-discriminated (the parser returns strings for quoted atoms and numbers for bare ones); the tenting check accepts both the flat and the nested form.
- **Complex Power Plane Splits (BGA/FPGA)**: hard prohibition on auto-generating rectangular split planes for interleaved multi-rail components on inner power layers. Pour the primary global plane, leave the interleaved rails unpoured, notify the user. Measured evidence: bbox splits orphaned 68 pads across four FPGA rails.
- **Edge.Cuts Sanitization** added as a mandatory pre-flight gate: detect doubled/nearly-coincident items (0.05 mm tolerance), deduplicate to one closed polygon, enforce stroke 0.05 mm. Respects a standing user instruction not to modify the outline — report and wait instead.
- **Rule Harmonization** (implemented, not merely documented): `apply_settings.js` now sets `min_through_hole_diameter` to exactly the active profile value, and after the netclass merge raises any class `via_drill` / `via_diameter` sitting below that minimum. Verified on 4L-1oz (rule 0.15), 6L-1oz (0.15) and 2L-2oz (0.30): zero classes left below the rule on any profile. `golden_settings.json` template drill changed 0.20 → 0.15 to match the adopted netclass table. This supersedes the rev B "Open conflict" section, which is removed.
- Tests updated to the new behaviour: the two assertions that required the drill conflict to be *reported* now require it to be *absent*, and the good board must be entirely WARN-free. 35/35 assertions pass.
- **External Router Workflow**: documented that `kicad-cli` does not expose Specctra DSN export/import in KiCad 10; the round-trip is a GUI operation, after which the agent audits and fixes the `.ses` geometry (lattice, snapping, via flags, class widths).
- Corrected the stale claim that Python is unavailable: Python 3.14.5 is present as `py`. Shipped tooling stays Node-only and dependency-free.
- Added s-expression editing discipline (depth-aware scanner, post-write balance and census verification, EOL/indentation preservation).

## 1.3.0 — 2026-09-17 (rev C: mandatory pre-routing gate)

- New Section 0 in `SKILL.md` and in `KiCad_Master_Skill.md` (rev C, also `references/00_full_standard.md`): before any `.kicad_pcb` edit the agent must ask layer count (2/4/6) and copper weight (1oz/2oz), enforce the JLCPCB profile, and for 4 layers keep the immutable order Top Signal | In1 GND | In2 POWER | Bottom Signal.
- Added `fabricators/jlcpcb.json`: capability profiles 2L/4L/6L × 1oz/2oz mapped to KiCad rules (captured 2026-09-17; re-check before each order).
- `apply_settings.js --fab jlcpcb --layers N --copper 1oz|2oz [--fab-exact]`: rules set to the stricter of template and fabricator limit (or exactly the limit with `--fab-exact`); profile written to `kicad_golden.project.json`.
- Audit: `pre-flight` FAIL when no fabricator profile is on record, when the copper layer count differs from the profile, or when any rule is below the profile; `stackup-order` FAIL/WARN for the 4-layer roles (In1 GND zone, In2 power zones); copper thickness checked against the profile (inner 17.5 µm on 4L-1oz).
- Tests: 35 assertions (fabricator enforcement, 2L-2oz raise, incomplete triple refused, params merge).
- `KiCad_Master_Skill.md` rewritten as rev C: gate first, then settings, netclasses, geometry (orthodiagonal, keepouts, no neckdown/staircase), schematic, verification, checklist — reconciled with the 2026-09-16 review.

## 1.2.1 — 2026-09-17 (second pass over that devboard project's settings package)

- Added `scripts/settings_report.js`: Markdown configuration report of any `.kicad_pro` (+ board stackup), `--diff` against the template; flags fabrication checks not at error.
- Added `templates/import_source/` (minimal `.kicad_pcb` + generated `.kicad_pro`) for the KiCad UI path "Import Settings from Another Board…"; README included.
- Inner plane layers: declare as layer type `power`; audit INFO when In*.Cu are typed `signal`.
- `references/07_review_decisions.md`: second-pass section (what was adopted, the severity set deliberately not adopted, fabricator-dependent values observed).
- Parameter template: `fabricator._alternatives` block with that devboard project's limits as an example profile.

## 1.2.0 — 2026-09-16 (specialist review applied)

Source: `20260916_KiCad_Golden_Spec_Review_Points_FilledForm.docx` and `a devboard settings export`. Full record in `references/07_review_decisions.md`.

- **Netclasses (Q-04)**: `golden_settings.json` now carries the reviewer's six classes (Default, POWER_DC, POWER_AC, BUS_SDRAM_CONTROL/ADDR/DATA), eight name patterns and the predefined track/via/diff-pair sizes. `apply_settings.js` inserts/replaces template classes by name and adds missing patterns. The audit resolves each net's class (assignment → pattern → priority) and judges track width (WARN) and via stack (FAIL) against it.
- **Zero arcs (Q-03)**: any track arc is FAIL; tuning `corner_style` set to 2 (chamfer) in the template.
- **Unused-layer removal (Q-06)**: missing `remove_unused_layers`/`keep_end_layers` is FAIL.
- **Per-project parameters** (`templates/kicad_golden.project.json`, read from `<board>.golden.json` or `kicad_golden.project.json`): length groups and clock rule (Q-07, Q-08), diff-pair mismatch limits, via budget (Q-09), keepout layer-change policy (Q-10), fabricator limits (Q-11, Q-12), stackup reference (Q-13), silkscreen references (Q-14), teardrops (Q-15), via-in-pad approved parts (Q-05).
- Via spacing judged as hole-to-hole against the project rule; edge clearance read from the project rule; rule deviations from the template downgraded to WARN ("fabricator governs").
- Audit reports the inherited conflict "netclass via drill 0.15 < min through-hole 0.20" as WARN.
- Tests: 31 assertions (netclass resolution, arc FAIL, rul FAIL, hole-to-hole, via budget, length group, pattern merge).
- Docs: `SKILL.md` rev B, `references/07_review_decisions.md`, updates to 01/02/05; spec artifact republished as rev B.
- Reference board now audits FAIL 488 (74 arcs, 410 vias, 4 known defects) — recorded, not corrected.

## 1.1.0 — 2026-09-16

- Added `tests/run_tests.js`: generates `good.kicad_pcb` / `bad.kicad_pcb` fixtures, exercises `apply_settings.js`, asserts 23 expectations (0 FAIL/0 WARN on good; every hard rule fires on bad). Run with `node tests/run_tests.js`.
- Added `references/05_decision_rules.md` (diff-pair identification, width-by-current table, layer/via budget, length-matching targets, zone priority ordering, order of work).
- Added `references/06_worked_examples.md` (golden before/after s-expression snippets).
- Added `references/99_appendix_minor_details.md`; moved PRL settings, vendor field list, fp_text defaults, BGA/heatsink pad details, groups, library and sheet censuses out of the working references.
- Added versioning header to `SKILL.md` and source hashes to `golden_settings.json` `_meta`.
- Audit calibration: arcs accepted only as clusters (≥ 4, r ≤ 0.3 mm) on one net; same-net vias in heatsink/exposed pads allowed; per-check grouped console output; DNP and power symbols excluded from the LCSC check; diff-pair spacing judged only on runs ≥ 3 mm.

## 1.0.0 — 2026-09-16

- Initial extraction from `the geometry reference board` (KiCad 9.0, format 20241229).
- `SKILL.md`, `golden_settings.json`, `scripts/kicad_audit.js`, `scripts/apply_settings.js`, `references/00–04`.

## Golden source fingerprint

| File | SHA-256 |
|---|---|
| `reference_board.kicad_pcb` | `9ac5342756d9e8a0cf71573c0a00cbb207035fd25673db4d517ffd3f4f7d51b2` |
| `reference_board.kicad_pro` | `9c76d43dc25de1fae3e2c2be7892fc0402a648e4d4a8ad72e3bd5677379ca5ac` |

If the golden project changes, re-extract `golden_settings.json`, re-run the audit on it, update the known-defects list in `SKILL.md`, bump the version here and replace the hashes.
