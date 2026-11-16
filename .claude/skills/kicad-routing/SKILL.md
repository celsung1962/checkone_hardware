---
name: kicad-routing
description: >-
  Route and finish KiCad PCBs (KiCad 9-10) to the AQTech "golden" standard: pre-routing setup against real
  fabricator limits (JLCPCB 2/4/6 layers), netclasses derived from the netlist, routability pre-flight, automated
  Freerouting DSN/SES round-trip (single pass or phased), post-import repair, plane stitching, geometric
  refinement, an executable PASS/FAIL audit, DRC, and manufacturing outputs (Gerbers, drill, BOM/CPL). ALWAYS use
  this skill when the user wants to route a board, autoroute, run Freerouting, finish or clean up routing, set up
  board rules / netclasses / stackup before routing, stitch planes, audit a routed board, "check against the
  standard", says "golden" or "padrão AQTech", or wants Gerbers and drill files - even without the word "skill".
  Not for component placement (kicad-placement) or schematic drawing (kicad-schematic).
---

# kicad-routing — KiCad Golden Standard (the geometry reference board, rev G)

| | |
|---|---|
| Skill version | 1.29.0 (see `CHANGELOG.md`) — KiCad Routing Tools' copper-hygiene checker as a second checker (`krt_check.py`, §The copper-hygiene gate): soft joints, redundant loops, removable and stacked copper; `stage_gate.py` gates on it when the plugin is installed; the last bend before a pad is a project parameter (`pad_entry.bend_min_mm`, default 0.5 mm; `pad_entry.bend_check: false` turns that one check into an INFO); on 6+ layers an inner layer declared `signal` is a routing layer for the audit. 1.28.1 — continuous integration, no change to any tool or audit result: `tests/run_all.py` runs the 14 suites (`--strict` fails skips), the suites leave a checkout unchanged, fixtures built with `pcbnew.NewBoard` so the `.kicad_pro` is written on Linux too; released from `aqtech-skills`. 1.28.0 — finishing a routed board under the gates (ServiceOne rev. 0.2, Vladimir Duk and Claude, lessons L30–L44 in reference 11): the stop rule (`stop_rule.py`) in `finish_gated.py`, `refinish_gated.py` and the new `gate_each.py`; no gated driver moves a locked track or via (`locks.py`); audit section 33 `diagonal` WARN for orthogonal-first routing (`routing_style`); the shared-gap message no longer depends on the order of the file; new tools `stage_gate.py`, `gate_each.py`, `open_ends.py`, `dangling_classify.py`, `via_spot.py`, `via_relocate.py`, `dedupe_copper.py`, `edit_tracks.py`; KiCad Cleanup with "Delete tracks fully inside pads" off. 1.27.0 — rules already defined are enforced, not counted (ServiceOne D133 review by Vladimir Duk): audit section 32 FAILs acute joints, `audit_gate.py` blocks any change that adds a FAIL however much the total falls, the gated drivers use it, `route_finish.py` never turns sharper than 90°, and a board is not handed off with dangling copper. 1.26.6 — `route_finish.py --avoid-exempt` takes several circles. 1.26.5 — a datasheet `"surface": true` decoupling pair is excused from the plane-net rule. 1.26.4 — `route_finish.py` island mode for coordinate starts; `finish_gated.py` routes pad ends pad-to-pad. 1.26.3 — the audit compares the board's title-block revision with the schematic's. 1.26.2 — the datasheet scan reads hand-imported documents and keeps the review's own fields. 1.26.1 — the pre-flight honours `approved_rule_deviations`. 1.26.0 — datasheet layout suggestions before routing: `datasheet_layout_scan.py` scans every datasheet of the board for layout sections, the suggestions become placement moves, `layout_checks` and routing constraints, `layout_measure.py check --pre-route`; the audit and `route_freerouting.py` gate on the review (playbook B0). 1.25.0 — approximate 3D models and mounting holes with their own keep-out (L24, L26): `model_builder.py`, `mounting_hole_fp.py`; audit section 27 counts a hole footprint with its own keep-out as covered. Stage 2 of reference 11 is complete. 1.24.0 — fan-out pattern and pin-array centreline (L21, L22): audit section 31 `fan-out` WARN, section 29 `pin-array` "off-centre" FAIL (centred by `center_gaps_safe.py`), `fanout_regularise.py` (stage 2, item 4 of reference 11). 1.23.0 — axial pad entries (L10, L11): `route_finish.py` ends every `--from-pad` / `--to-pad` route in an axial stub to pad edge + 0.5 mm, and `--refinish REF.PAD` realigns an existing entry (stage 2, item 3 of reference 11). 1.22.0 — pad-row band keep-outs (L16): `pad_row_keepouts.py` and `export_keepouts.py --pad-row-bands` write "no vias" rule areas over every IC pad-row band; audit section 26 now counts the via's copper, as KiCad's DRC does (stage 2, item 2 of reference 11). 1.21.0 — plane plan (L23): `plane_plan.py map|apply|check` and audit section 30 (stage 2, item 1 of reference 11). 1.20.0 — board review rules from ServiceOne rev. 0.2 (Vladimir Duk): 16 new or stricter audit checks, `board_guard.py` before every board write, `zone_fill_check.py`, the layout (Kelvin) gate in `finish_gated.py`, approved deviations kept by `apply_settings.js`, the fabricator's economical via tier (reference 11). 1.19.0 — datasheet layout review: `layout_measure.py` (Kelvin, decoupling, analog/digital gap checks along the copper), `route_finish.py` dedicated (`--exclusive`) and pad-centre routes with hole/edge clearance from the board, reference 10. 1.18.0 — the ServiceOne routing folded in: export-time keepouts, gated finishing and centring, stitcher geometry fixes, apply_settings / init_project keep project decisions. 1.17.1 — via-in-pad check fixed for paste-only apertures and small exposed pads. 1.17.0 — renamed from kicad-golden; the routing playbook and the trial learnings are now references 08 and 09. Previous: 1.16.0 — rev P: the improvements review (Fab layer hygiene, pad-entry geometry, plane-net via-only, spreading) |
| Geometry reference | `the geometry reference board` — KiCad 9.0, file format 20241229, 4-layer, 200 × 192.5 mm |
| Netclass reference | `a 6-layer devboard project` (reviewer's table, adopted 2026-09-16) |
| File formats supported | KiCad 9 (`20241229`) and KiCad 10 (`20260206`) — see §KiCad 10 Syntax |
| Review | `references/07_review_decisions.md` — 15 decisions, all implemented |
| Source fingerprint | `.kicad_pcb` sha256 `9ac53427…7d51b2`, `.kicad_pro` sha256 `9c76d43d…9ca5ac` (full hashes in CHANGELOG) |
| Self-test | All suites: `python tests/run_all.py [--strict] [--kicad-python PATH]` (one table, exit 0 only when every suite passes). Individually: `node tests/run_tests.js` (131) + `python tests/run_tests_guard.py` (45) + `python tests/run_tests_planeplan.py` (11) + `python tests/run_tests_padrow.py` (10) + `python tests/run_tests_axial.py` (14) + `python tests/run_tests_fanout.py` (9) + `python tests/run_tests_models.py` (13) + `python tests/run_tests_datasheet.py` (16) + `python tests/run_tests_py.py` (34) + `python tests/run_tests_boards.py` (8) + `python tests/run_tests_phased.py` (11) + `python tests/run_tests_rules.py` (16) + `<kicad-python> tests/run_tests_kicad.py` (22, pcbnew tools) + `<kicad-python> tests/run_tests_gate_tools.py` (26, 1.28.0 finishing tools). Real boards: `python tests/run_corpus.py tests/corpus` |

Everything here is imperative; do not re-derive it from the golden files.

**Detect the file format before anything else.** Read `(version NNNNNNNN)` at the top of the `.kicad_pcb`. `20260206` or later is KiCad 10 — apply §KiCad 10 Syntax to every read and every write. Never emit KiCad 9 syntax into a KiCad 10 file or the reverse.

---

**New to this skill, or preparing a board?** Read `MANUAL.md` first - section 0 installs the tools this skill needs (KiCad, Freerouting, KiCad-Python packages, kicad-cli/Inkscape), section 2 is the KiCad checklist to complete BEFORE calling the skill, and section 3 opens with a worked prompt plus the prompt mistakes that cost a run.

## How to read this document

Two kinds of statement appear here and they carry different weight.

- **Rules** are normative. "A track on an inner layer is a FAIL" is a rule.
- **Observations** are evidence from a specific board, shown so you can judge the rule. Anything
  presented as a measurement - a clearance sweep table, a pad count, a percentage - is an
  observation from one design and is **not a default for yours**. Numbers that came from a single
  board are labelled as such.

When an observation and your board disagree, your board is right. Measure it with
`route_report.py` rather than adopting a number from here.

## Starting a NEW board - the five commands that matter

Run these in order. Each one refuses to guess something that belongs to your design.

```
python  scripts/doctor.py                       # what this machine can actually do
<kicad> scripts/init_project.py BOARD --fab jlcpcb --layers 4 --copper 1oz
node    scripts/apply_settings.js PROJ.kicad_pro --fab jlcpcb --layers 4 --copper 1oz
<kicad> scripts/netclass_propose.py BOARD --apply
python  scripts/datasheet_layout_scan.py BOARD --datasheets DIR --write-params   # then review: §Datasheet layout suggestions
<kicad> scripts/route_report.py BOARD          # the pre-flight, and later the completion metric
```

**Why each exists**, because skipping one has a specific cost:

| Step | What it prevents |
|---|---|
| `doctor.py` | Discovering mid-run that shapely is in the other interpreter, or that the Freerouting jar needs a newer Java than this machine has |
| `init_project.py` | Inheriting another design's length groups and via budget, which match zero nets and then report a clean pass while auditing nothing |
| `apply_settings.js` | Rules looser than the fabricator can build |
| `netclass_propose.py` | **A current-carrying rail silently left on Default and routed at signal width.** The settings template cannot catch this for you: patterns captured from another board match nothing on yours. This is the one defect that reaches copper without any warning, and the audit now FAILs on it |
| `datasheet_layout_scan.py` | Routing against the manufacturer's layout suggestions: a converter loop, a Kelvin connection or a clock beside an analog input that DRC and the audit cannot see (ServiceOne, reference 10). The review is recorded per part; routing is refused while one is pending |
| `route_report.py` | Routing blind - no completion number, no warning about footprint-local clearance, no list of the long-haul nets that must be routed first |

The templates ship **no netclass patterns and no length groups on purpose.** An empty rule is
visible; an inherited rule that matches nothing looks like success.

## 0. Pre-Routing Setup & Manufacturer Capabilities — MANDATORY, BEFORE ANY `.kicad_pcb` EDIT

Do this before modifying a board file or drawing a single track, and before editing an existing board whose `kicad_golden.project.json` has no `fabricator.layers`. The audit fails (`pre-flight`) while the profile is missing, so skipping this cannot end in "done".

1. **Pause and ask** (use `AskUserQuestion`, one interaction, all three questions). Never assume, infer or default them:
   - **Layer count**: 2, 4 or 6.
   - **Copper weight**: 1 oz or 2 oz outer (JLCPCB: 1 oz outer + 0.5 oz inner, or 2 oz outer + 1 oz inner on multilayer).
   - **Shared pad gaps** (Q-16): may the router narrow two or more tracks to pass them through the same gap between two adjacent pads? Default **no**. Record the answer in `kicad_golden.project.json` → `shared_pad_gaps.allowed`.
   If the layer/copper answer has no profile in `fabricators/jlcpcb.json` (e.g. 8 layers, 3 oz), say so and ask again or stop.
2. **Enforce JLCPCB limits**: run `apply_settings.js <project>.kicad_pro --fab jlcpcb --layers <N> --copper <1oz|2oz>`. It sets every Board Setup rule to the stricter of the golden value and the JLCPCB minimum (track, clearance, via hole, via diameter, annular ring, hole-to-hole, edge, text) and records the profile in `kicad_golden.project.json`. Use `--fab-exact` only when the user explicitly wants the fabricator's full capability. If web access exists, re-check `https://jlcpcb.com/capabilities/pcb-capabilities` first and update the JSON (`captured` date) when a value changed. Then fix the stackup copper (4L-1oz / 6L-1oz: 35 µm outer, 17.5 µm inner; 2 oz profiles: 70 / 35 µm).
3. **Harmonize the via drill rule** — see §Rule Harmonization below. Run it as part of step 2, never as an afterthought.
4. **Sanitize `Edge.Cuts`** — see §Edge.Cuts Sanitization below. This is a pre-flight gate: do not route, do not pour zones and do not export to an external router until the outline is a single closed polygon.
5. **4 layers → immutable order**: F.Cu **Signal** | In1.Cu **GND plane** (one GND zone, type `power`, no tracks) | In2.Cu **POWER plane** (power zones, type `power`, no tracks) | B.Cu **Signal**. Never reorder or swap. The audit fails on tracks on In*, on In1 without a GND zone and on In2 without a zone. 2 layers: no planes, GND pour on B.Cu. 6 layers: propose Top S | In1 GND | In2 S | In3 S | In4 POWER | Bottom S and confirm before drawing.
6. **Assign every net to a netclass** before drawing (patterns or explicit assignment). Widths and via stacks come from the class; never hand-set them. Audit the pattern list against the real netlist: any multi-pad rail matching `*V`, `VCC`, `VDD`, `VBAT`, `AVDD` that resolves to `Default` is a setup defect — add a `POWER_DC` pattern for it and say so.
7. State in one line what was applied, then continue with the workflow below. If the user later changes layer count or copper, return to step 1.

### Rule Harmonization (via drill) — MANDATORY

The board's `min_through_hole_diameter` rule must equal the active fabricator profile's `min_through_hole_diameter`, and every netclass `via_drill` must be **≥** that value. A rule stricter than the class drill turns every via in that class into a DRC error against your own board; a rule looser than the fabricator's limit yields boards the fabricator cannot make.

**Take the value from the profile. Never hard-code it.** For JLCPCB:

| Profile | `min_through_hole_diameter` | Netclass `via_drill` action |
|---|---|---|
| 4L-1oz, 4L-2oz, 6L-1oz, 6L-2oz | **0.15** | Default / BUS classes keep 0.15 — conflict resolved |
| 2L-1oz, 2L-2oz | **0.30** | Raise Default / BUS vias to 0.5 / 0.3 |

Do this without asking; it is a mechanical consequence of the profile the user already chose. State the applied value in the one-line summary. If the user wants the golden 0.20 kept instead of the profile value, they must say so — record that in `kicad_golden.project.json` and expect the WARN to persist.

### High-Density Via Allowance (4-layer and denser) — MANDATORY

**On 4-layer and denser boards the fabricator's via limits REPLACE the golden defaults; they are not
max()'d with them.** This is the one place where the standard deliberately relaxes rather than tightens.

| Profile | `min_via_diameter` | `min_via_annular_width` | Predefined via added |
|---|---|---|---|
| 4L-1oz, 4L-2oz, 6L-1oz, 6L-2oz (JLCPCB) | **0.25** | **0.05** | **0.25 / 0.15** |
| 2L-1oz, 2L-2oz (JLCPCB) | 0.5 (profile, stricter) | 0.1 | — |
| no fabricator profile | 0.45 (golden template) | 0.1 | — |

**Why this is a rule and not a waiver.** The golden 0.45 mm / 0.10 mm via cannot be physically placed
beside a fine-pitch pad. At DFN/QFN pitches of 0.4–0.5 mm the channel beside the pad is narrower than a
0.45 mm via plus clearance, so `stitch_planes.py` is forced down to the fabricator minimum and **every
via it places becomes a DRC error against the board's own rules** — an error the designer cannot fix by
routing, only by deleting the connection. Measured on `a 4-layer 350-connection test board` (2026-09-18): 17 of
113 stitching vias, across 12 footprints, 34 audit FAILs, all self-inflicted. JLCPCB builds 0.25 / 0.05
on 4L+ as a standard (not advanced) service, so the stricter rule bought nothing and cost connectivity.

`apply_settings.js` applies this automatically from the profile — do not hand-edit the two rules, and do
not "restore" them to 0.45 / 0.1 on a 4-layer board. It also inserts the profile's minimum via into
`via_dimensions`, without which `kicad_audit.js` still FAILs the via with *"matches neither its netclass
nor a predefined via size"*.

**This allowance governs via SIZE only.** It does not relax `min_through_hole_diameter` (see Rule
Harmonization above), hole-to-hole, clearance, or the Q-06 via flags. A 2-layer board is untouched.

### Routability Pre-Flight — MANDATORY, run `route_report.py` before routing

**Run `route_report.py` on the board before the first export and after every stage.** It answers
"am I done?" with a number — connections routed out of `pads - 1` — and surfaces the three things
that decide whether a board can be finished automatically at all.

```bash
"C:\Program Files\KiCad\10.0\bin\python.exe" scripts/route_report.py <board> --json r.json
```

**1. Footprint-local clearance overrides.** A footprint may carry its own `(clearance X)`. The
Specctra DSN has **no per-footprint clearance field**, so the router never sees it, undercuts that
part, and every violation appears only after the import. On the 4-layer test board a single VQFN-29 at 0.4 mm
pitch with `(clearance 0.15)` produced **21 of 21** clearance violations in the first run.

Always export with `route_freerouting.py --auto-clearance`, which raises every netclass clearance
to the largest local override for the export and restores the golden values immediately after the
DSN is written. **The DSN takes its clearance from the NETCLASS, not from the `min_clearance`
board rule** — editing `min_clearance` changes nothing and costs a full router run to discover.

**2. Long-haul nets.** Autorouters serve short connections first and starve long ones of channels.
`route_report.py` lists every net whose pad span exceeds 50 mm. **Route those first**, on a bare
board or by hand, so they claim their corridors while the board is still empty. On the 4-layer test board the
`+BATT` net spans 69 mm; its far pad defeated a geometric corridor search (56 candidate landings,
all colliding), a hand-built path, and a dedicated Freerouting pass. Identified up front it is ten
minutes of manual routing; discovered at the end it is three failed strategies.

**3. Plane-stitch coverage.** Every plane-net SMD pad with no via near it is a latent unconnected
item. `stitch_planes.py` gives up with "no clear position" and says nothing further; the report
counts what it left behind.

### Choosing the clearance — measure, do not guess

Clearance is the setting that most changes how much of a board the router can finish, and the
relationship is **not monotonic**. Measured on the 4-layer test board:

| Export clearance | Unrouted | Violations | |
|---|---|---|---|
| 0.10 mm | 40 | 21 | undercut the footprint-local override |
| **0.15 mm** | **36** | **4** | **best** |
| 0.20 mm | 59 | 7 | more clearance, far worse |

`route_sweep.py` runs the candidates, scores each with `route_report.py`, and reports the winner.
Its floor is never below the largest local override.

### Never top up an already-routed board

A DSN/SES round-trip over existing copper is **lossy for via padstacks**. Attempted on the 4-layer test board to
route one remaining connection: the target net was still unrouted afterwards, and **17 vias came
back with a 0.250 mm pad on a 0.300 mm drill** — a hole larger than its own pad, annular
−0.025 mm — which KiCad saves without complaint. Route from a bare board in one pass, or route the
remainder by hand. `route_freerouting.py` now refuses to save such a board (`--no-padstack-gate`
overrides, and `route_report.py` flags it as `<< INVALID`).

### Finishing the last connections - `route_finish.py`

Since a top-up pass is forbidden, "route the remainder by hand" needs a tool. `route_finish.py` is a
grid maze router that does ONE connection at a time on the 45-degree lattice, so each result is
DRC-checkable before the next is attempted.

```bash
<kicad> scripts/route_finish.py BOARD --net "SCL" --from 109.411,161.925 --to 86.250,101.200 \
  --width 0.2 --grid 0.05 --safety 0.05 --dry-run
```

Take the endpoints from the DRC report's `unconnected_items`, and take the *width* from the
netclass - a POWER_DC net routed at the 0.2 mm default is a neckdown, which is a WARN you then have
to explain.

**Three things decide whether this works, and all three were learned the hard way:**

1. **`--safety` is not optional padding.** Obstacles are dilated by
   (half-width + clearance + safety). Without the safety term, a grid cell centre can sit up to
   `GRID*sqrt(2)/2` from the true copper edge, and DRC reports a near-miss: **measured 0.0594 mm
   against a 0.1 mm rule** at `--grid 0.1`. Raise it too far and narrow channels seal shut and nets
   stop routing entirely - that same bump took five nets from "routed" to "no path".
   `--grid 0.05 --safety 0.05` is the useful compromise.

2. **ORDER changes the result.** Routing one net changes what the next can reach. **MEASURED** on
   one board, identical 8 connections, three orderings: **3, 4 and 4** left unrouted. Long-haul-first
   and congested-corner-first each won a different net and lost another. There is no ordering that
   is right in general - try two or three and keep the best.

3. **DRC after every net, and revert any route that raises the violation count.** Cheap, and it
   makes a bad path impossible to accumulate. A "no path" result is information, not failure: on one
   board `Net-(U6-BTST1)` expanded 2.87M cells against a ~3.4M cell space - effectively exhaustive -
   which says the connection genuinely cannot be made without ripping up its neighbours.

**The lattice check is load-bearing.** The script refuses to write (exit 3) if any segment is not
horizontal, vertical or exactly 45 degrees. It caught two real bugs during development, including a
zero-length step at a via that made the collinearity test merge an entire run into one skewed
segment. Do not remove it.

### Any geometric "snap" must be scoped to what you are fixing

A snapper that pulls every endpoint within a tolerance onto the nearest via centre **will move other
nets' geometry and break their angles**. Measured twice on this standard: once dragging interior
nodes onto pads and creating 42 off-lattice segments from zero, and again moving sub-micron
endpoints on three uninvolved nets (`geometry 3, angle 2` FAILs) while fixing one 198 nm gap.

Scope every snap to the net - ideally the item - you are repairing, and re-run `kicad_audit.js`
immediately after. The audit is what tells you whether the repair cost more than it fixed.

### Keepout Enumeration (Pre-Flight Check) — MANDATORY

**Rule areas can live inside footprints, and the obvious way of looking for them does not see them.**
A top-level scan (`kids(pcb,'zone')`, or `board.GetAreaCount()` / `GetArea(i)` in `pcbnew`) returns
**only** board-level zones. A board whose keepouts are all footprint-internal reports **zero** and is
never checked — while the report still reads as though the keepout rule had been applied.

Enumerate both, always:

```python
keepouts = [z for i in range(b.GetAreaCount()) if (z := b.GetArea(i)).GetIsRuleArea()]
keepouts += [z for fp in b.GetFootprints() for z in fp.Zones() if z.GetIsRuleArea()]
```

Footprint zone polygons carry **absolute** board coordinates, so they need no footprint transform —
treat them exactly like top-level zones.

Then, before routing:

1. **Report the count explicitly, including zero.** "3 rule_area keepouts (3 footprint-internal)" or
   "zero rule_area keepouts — nothing to check". Silence is not an acceptable substitute: it reads as
   "checked and clean" when it may mean "never looked". `kicad_audit.js` emits this as an INFO from
   1.9.0; earlier versions are silently blind to footprint-internal rule areas.
2. **Confirm `items_not_allowed` is not `ignore`** in `rule_severities`. If it is, KiCad's own DRC will
   pass keepout violations without a word, and the audit's silence means nothing.
3. **State the measured margin, not just "no violations".** Nearest copper to each keepout, so the
   reader can tell a genuine clearance from a keepout nowhere near any routing.
4. **Freerouting honours keepouts** — the DSN export carries them as obstacles, so a clean SES is
   expected, not lucky. **`stitch_planes.py` does not know about footprint-local clearance overrides**
   (`(clearance ...)` inside a footprint), and neither does the DSN: both use the board-global value.
   Re-run DRC after stitching and expect local-override violations around fine-pitch parts.

Worked evidence — `a 4-layer 350-connection test board` (2026-09-18): 3 keepouts, all footprint-internal
(J1 x1, SW3 x2), all F.Cu, all `tracks/vias/pads/copperpour not_allowed`. The audit reported
`keepout_zones: 0` and emitted no finding. The routing was in fact clean (nearest copper 0.327 mm),
but nothing in the report established that.

### Edge.Cuts Sanitization (Pre-Flight Check) — MANDATORY

An ambiguous board edge corrupts zone fills, edge-clearance DRC and every external-router export. Before routing:

1. **Inspect every graphical item on `Edge.Cuts`** — `gr_line`, `gr_arc`, `gr_rect`, `gr_poly`, `gr_circle`, and the same items inside footprints. **Footprint-internal Edge.Cuts is common and legitimate**: on the reference board 27 LED footprints each carry 4 `fp_line` cutouts (108 items, 27 internal openings). Counting only top-level items understates the outline and makes later edge-clearance findings unexplainable. Cutouts spaced 0.700 mm apart leave **negative** room at a 0.5 mm clearance rule — check that the rule is geometrically satisfiable before blaming the router.
2. **Detect doubled, overlapping and nearly-coincident items.** Treat two items as duplicates when their endpoints agree within **0.05 mm**. Real boards carry offsets as small as 9 µm that are invisible on screen and silently produce two competing outlines. Compare the distinct X and Y coordinates: a clean rectangle has exactly two of each, and four or more means a doubled outline.
3. **Deduplicate to exactly one single, continuous, closed polygon.** Every vertex must be shared by exactly two segments; zero dangling endpoints, zero crossings, zero interior duplicates. Cutouts are separate closed loops and are allowed — count them and name them.
4. **Enforce stroke `0.05 mm` on every `Edge.Cuts` item.** Any other width is a defect to correct, not to report.
5. **Verify** afterwards and state the result: item count before and after, the resulting polygon's vertex count and bounding box.

**Edge.Cuts is normally protected from modification.** If the user has told you not to touch `Edge.Cuts` or the board outline, do not silently override that. Stop, report the exact duplicate coordinates you measured, and get explicit approval before deduplicating. Report-and-wait is the correct outcome in that case; routing on an ambiguous outline is not.

---

## KiCad 10 Syntax (file format `20260206` and later)

KiCad 10 changed several s-expression forms. **Parse and write these forms whenever the board declares `20260206` or later.** Getting this wrong produces false audit failures on perfectly valid boards, and writing the legacy form into a KiCad 10 file risks corrupting it.

**Zone nets — use the net name directly:**

```lisp
; KiCad 10 — CORRECT
(zone
  (net "GND")
  (layer "In1.Cu")
  ...
)

; KiCad 9 legacy — do NOT write this into a KiCad 10 file
(zone
  (net 1)
  (net_name "GND")
  ...
)
```

Read the zone's net from `(net "…")` on KiCad 10 and from `(net_name "…")` on KiCad 9. Never inject a `net_name` field into a KiCad 10 file to satisfy a stale checker.

**Via tenting — nested form:**

```lisp
; KiCad 10 — CORRECT
(tenting
  (front yes)
  (back yes)
)

; KiCad 9 legacy
(tenting front back)
```

A KiCad 10 board carrying `(tenting (front yes) (back yes))` already satisfies "tented both sides". Do not rewrite it.

**Track and pad nets** are likewise net-name strings on KiCad 10 — `(net "/FPGA/FPGA_SDRAM1_CLK")` — so there is no top-level net table to preserve. Do not look for one.

### KiCad 9/10 dual-format parsing — fixed in `kicad_audit.js` 1.4.0

The audit reads both formats from 1.4.0 (`zoneNet()` helper; dual-form tenting check). **Audit scripts at 1.3.0 or older parse the KiCad 9 forms only** and emit these false positives on a KiCad 10 board. If you see them, you are running an old audit — recognise them as format artefacts and never "fix" the board to silence them:

| Reported | Reality |
|---|---|
| `[zone] zone without net on <layer>` | Zone uses `(net "…")`; the check reads `net_name` |
| `[stackup-order] In1.Cu carries no GND zone ()` | Downstream of the same bug — the net name read as empty |
| `[stackup] via tenting is not "front back"` | Board uses the nested `(tenting (front yes) (back yes))` |

**Confirm before you dismiss.** Run the audit against a known-good KiCad 10 board — the user's own pre-edit backup is ideal. If that board produces the identical finding, the check is stale, not the board. Say so explicitly, with the evidence, and upgrade the skill to 1.4.0. Never let a stale check block a correct deliverable, and never claim a PASS the script did not give.

---

## Automated External Routing (Freerouting / Specctra) — MANDATORY METHOD

**You do not autoroute a board yourself.** You have no geometric collision engine and no rip-up-and-retry;
emitting `(segment ...)` blocks by hand at any real scale yields a file that is syntactically perfect and
electrically ruined. Freerouting does the routing. Your job is to drive it, then repair its geometry.

**`kicad-cli` does not expose Specctra DSN/SES in KiCad 10 — but the `pcbnew` Python API does.**
Never ask the user to perform GUI menu steps. Automate the whole round-trip.

Verified on KiCad 10.0.6:

```
pcbnew.ExportSpecctraDSN(BOARD aBoard, wxString aFullFilename) -> bool
pcbnew.ImportSpecctraSES(BOARD aBoard, wxString aFullFilename) -> bool
```

Both have a two-argument overload taking an explicit `BOARD`, which is what makes headless operation possible.
The one-argument overloads act on the GUI's open board and must not be used from a script.

### Interpreter

`pcbnew` is a compiled extension bound to KiCad's own Python. **Use KiCad's interpreter, never the system one**:

```
C:\Program Files\KiCad\10.0\bin\python.exe        (Windows)
/usr/lib/kicad/bin/python  or  /usr/bin/python3        (Linux, distro-dependent)
```

Import errors for `_pcbnew` mean the wrong interpreter. Do not try to `pip install pcbnew`.

### The shipped script

Use `scripts/route_freerouting.py` rather than writing a new one each time:

```bash
"C:\Program Files\KiCad\10.0\bin\python.exe" \
  "%USERPROFILE%\.claude\skills\kicad-routing\scripts\route_freerouting.py" \
  "<board>.kicad_pcb" --passes 500 --timeout 14400 [--outdir DIR] [--fr-cmd "..."]
```

`--export-only` stops after writing the `.dsn` (use it to inspect the export before committing to a long
run); `--import-only <file.ses>` skips routing and imports an existing session. It shells out as:

```
<freerouting> -de <board>.dsn -do <board>.ses -mp <passes> -l en [-mt <threads>]
```

Its core, for reference:

```python
import pcbnew, subprocess, os, shutil
brd = os.path.abspath(BOARD_PATH)
shutil.copy2(brd, brd + '.bak_prerouting')          # always, before anything
board = pcbnew.LoadBoard(brd)
assert pcbnew.ExportSpecctraDSN(board, dsn), 'DSN export failed'
r = subprocess.run(FR_CMD + ['-de', dsn, '-do', ses, '-mp', str(passes)],
                   capture_output=True, text=True, timeout=SECONDS)
assert os.path.exists(ses) and os.path.getsize(ses) > 0, 'Freerouting produced no .ses'
board = pcbnew.LoadBoard(brd)                        # reload: the export may have mutated state
assert pcbnew.ImportSpecctraSES(board, ses), 'SES import failed'
pcbnew.SaveBoard(brd, board)
```

Rules for the script:

1. **Back up the `.kicad_pcb` before the import.** The import mutates the board in place.
2. **Discover Freerouting automatically. Never hard-code a path** — the skill must work on any machine
   that has it installed. `scripts/route_freerouting.py` implements this resolution order, first hit wins:
   `--fr-cmd` → `FREEROUTING_CMD` env → `PATH` → platform install location
   (`%LOCALAPPDATA%\freerouting\freerouting.exe`, `%PROGRAMFILES%\Freerouting\`,
   `/Applications/Freerouting.app/Contents/MacOS/Freerouting`, `~/.local/share/freerouting/bin/`,
   `/opt/freerouting/bin/`) → `freerouting*.jar` via `java -jar`.
   Prefer the **native launcher over the jar**: the jpackage build carries its own runtime (Java 25 in
   2.4.1), whereas the jar needs a system Java 21+. The script refuses a jar when the only `java` on PATH
   is older, and says so rather than failing obscurely. Ask the user only when discovery finds nothing.
3. **Freerouting 2.4.1 has no headless flag** — `-h` lists only `-de -di -dr -do -mp -l -mt -us -hr -is`.
   It opens a window even when driven from the CLI, and with `-do` it routes, writes the session and exits
   on its own. Do not promise headless operation. Instead: always pass a `--timeout`, tell the user a
   Freerouting window will appear and must not be closed, and treat the timeout as the safety net. Confirm
   it is actually working rather than blocked on a dialog by checking CPU time and thread count, not the
   window. If it times out or returns no `.ses`, report that and stop — never fall back to hand-routing.
4. **Check the `.ses` exists and is non-empty** before importing. A zero-byte session file silently wipes
   routing on import.
5. **Zones**: pour planes before export so the router sees the copper it must avoid, and re-fill after import.
   **Verify the exported DSN declares the plane layers as `(type power)` and only the signal layers as
   `(type signal)`.** Freerouting will happily route on any layer typed `signal`, so a plane typed `signal`
   produces inner-layer tracks, which are a FAIL. This is why §0 step 5 insists on the `power` layer type.
6. Report the router's own exit code and stderr verbatim. Do not paraphrase a failure into a success.

### Mandatory post-import repair

Freerouting does not obey this standard. Immediately after the import, parse the `.kicad_pcb` and
mathematically correct its output. This is not optional and not a review step:

- **45° lattice**: every segment on 0/45/90/135° (+/- 0.01 deg). Snap off-lattice endpoints.
- **Zero arcs**: convert any track arc to straight chamfered segments (FAIL otherwise).
- **Pad-entry snapping**: endpoints equal to pad and via centres within 1 um; one straight entry segment
  per pad, perpendicular or axial, >= 0.2 mm, no staircase.
- **No neckdowns**: one width per net run. Remove mid-run width changes; restore the netclass width.
- **Via stacks**: through F.Cu-B.Cu only, at the netclass stack, with `remove_unused_layers yes` and
  `keep_end_layers yes` on every via. Freerouting does not emit these flags — add them.
- **Inner layers**: no tracks on In* (FAIL). The DSN must declare the plane layers as unroutable.
- **Pad-entry geometry** (rev P, improvements entries 3, 4, 5, 6, 8, 9): centre tracks between pads,
  neck down to the pad's smallest dimension inside the clearance area, enter each pad as one straight
  8-direction segment ending at its centre (axial first for elongated pads), and flag shared pad
  gaps and remaining under-part tracks. `scripts/geometry_finish.py` runs all of these in one pass —
  see §Post-Routing Geometric Refinement below.
- **Plane-net links** (improvements entry 7): replace any surface track joining two plane-net pads
  with a via at each pad (`scripts/geometry_finish.py --fix-plane-links`, or prevent it at export —
  see §Plane-net pads are via-only in Core rules).

Then re-run `kicad_audit.js` and report FAIL/WARN honestly. Quantify the repair: how many segments were
off-lattice, how many endpoints were snapped, how many neckdowns removed.

### Post-Routing Geometric Refinement (rev P) — `geometry_finish.py`

The improvements review (2026-09-25, see `CHANGELOG.md` 1.16.0) found that entries 1, 2 and 7 and the
crystal/inductor ban are fully automatable, but entries 3, 4, 5, 6, 8, 9, 10 and 11 need real tooling —
nothing in the pre-1.16.0 pipeline touched pad-entry geometry, gap centring or track spacing.
`scripts/geometry_finish.py` implements them, run with **KiCad's Python**, after the post-import repair
above and before the final `kicad_audit.js`:

```bash
"C:\Program Files\KiCad\10.0\bin\python.exe" scripts/geometry_finish.py <board> --all --params kicad_golden.project.json
```

Flags run individually: `--center-gaps` (3, 4), `--crystal-inductor-keepouts` (4 exception, run **before**
routing, not after), `--neck-pad-entries` (5), `--pad-centre-entries` (8, 9), `--route-around` (10,
**report-only**, see below), `--spread` (11), `--fix-plane-links` (7), `--report-shared-gaps` (6). Each
flag prints a before/after count; `--dry-run` previews without saving.

**What it fixes automatically, and what it only reports.** Centring (3, 4), necking (5), pad-centre
entries (8) and spreading (11) rewrite the simple, common topology — an isolated straight segment
between two lattice joints (both ends free of any pad/via), or a pad-entry run whose direction into the
pad is already lattice-exact. A segment that is part of a longer multi-branch run, touches a pad/via at
both ends, or whose reshaping would move a neighbouring net's geometry (see "Any geometric snap must be
scoped to what you are fixing"), is left alone and named in the report for manual attention rather than
guessed at. Entry 9's axial-vs-perpendicular preference is WARN-only in the audit and is **not**
rewritten by any flag here — changing which side of a pad a track enters from is a reroute, not a snap.
**`--route-around` (10) does not attempt a reroute at all — it only lists candidates.** The improvements
review's own test found that a pre-routing keepout over the footprint stalls Freerouting outright, and a
post-import bounding-box detour needs real collision-checked pathfinding this rev does not implement;
rather than ship an untested detour, the flag reports which nets pass under which part so a human (or a
`route_finish.py` run by hand) can judge each one. Never let a partial `--spread` or `--center-gaps` run
block finishing the board — re-run `kicad_audit.js` and revert any change that regresses it.

**Order matters.** `--crystal-inductor-keepouts` must run before the DSN export (it is a rule area, not a
repair). Everything else runs after import and after the 45°/neckdown/via-stack repair above, because it
assumes lattice-clean geometry to begin with. Re-run `kicad_audit.js` after every flag, not just at the
end — a fix that regresses DRC should be reverted, the same discipline as any other geometric snap.
---

## Autorouter costs - set them in the project, not in somebody's GUI

Freerouting's autorouter costs are **GUI settings held in the session**, not in `freerouting.json`.
A batch run therefore inherits whatever the last person clicked, and two engineers get different
boards from the same inputs. `freerouting -dr <file.rules>` reads them from a file instead.

`rules_writer.py` generates that file from `router_costs` in `kicad_golden.project.json`;
`route_freerouting.py --auto-rules` does it automatically.

### The quoting trap - this one fails silently

**The design name in `(rules PCB "<name>")` must be QUOTED.** Unquoted, Freerouting's reader stops
at the first space: a board named `My Board v2` is read as `My`, the designName check fails, and
**the entire rules file is ignored**. The run completes normally and nothing in the output says the
costs were not applied. Verified against 2.4.1 - unquoted produced
`designName not matching ... got 'BladeOne'`, quoted produced no warning.

The name must also equal the DSN's basename without extension. `rules_writer.py` reads it from the
file rather than guessing.

### Via cost is the lever worth knowing

Vias on power and long-haul nets are inductance and return-path discontinuities. `via_costs` makes
the router work to avoid them. Freerouting's default is 50.

**OBSERVED** - one 4-layer 350-connection board, identical inputs, only `via_costs` changed:

| | via_costs 50 | via_costs 150 |
|---|---|---|
| total vias | 105 | **72  (-31%)** |
| vias on the 8 key nets | 24 | **11  (-54%)** |
| length of those nets | 896.6 mm | **763.5 mm  (-15%)** |
| unrouted (pre-stitch) | 36 | 43  (+7) |
| unrouted after the FULL pipeline | **2  (99.43%)** | 9  (97.43%) |
| tracks necked to 0.15 mm | **20** | 44 |
| golden audit | **PASS** | FAIL - 16 neckdowns |

`SCL` went 6 vias to 0, `+VSYS` 4 to 2, `GND_LED` 3 to 1.

**The via saving is partly paid for in NECKDOWNS, and that is the part to watch.** Denied a via,
the router threads the gap at reduced width instead: sub-0.2 mm segments went 20 -> 44, and 16 of
them were outside any fine-pitch escape, which is a `width` FAIL. The board only passed after those
16 were widened back to 0.2 mm - which, measured, introduced no new DRC violation, so the narrowing
was never necessary in the first place. **Raising `via_costs` therefore requires a neckdown check
afterwards; treat a clean `route_report.py` as insufficient on its own.** On the same run the
router also left a GND / Net-(D10-A1) short and 5 dangling vias that the `via_costs` 50 board did
not have, while conversely clearing that board's 4 clearance errors.

**Recommendation, revised:** `via_costs` 150 is worth trying when via count is the binding
constraint, but it is not free and it is not a default. Re-audit after changing it.

**This matters for how you choose a strategy.** Phased routing (below) reached 10 vias on the same
8 nets, at a cost of a two-phase workflow, a locking contract and a verification step. **One
parameter reached 11 - and with shorter nets.** Try `via_costs` first; reach for phased routing
only if a single cost knob cannot express what you need.

### What is NOT settable from any script

`automatic neckdown`, `vias snap to SMD pad centers` and `drag components` are interactive-editor
state. They are absent from the rules vocabulary, absent from `freerouting.json`, and have no CLI
flag - confirmed by searching the shipped classes. Turn them off in the GUI before routing
interactively. The standard defends against their effects instead of their settings: via-in-pad is
a FAIL, neckdowns are stripped and re-audited, and footprint identity is verified - which catches
the defect whoever or whatever produced it.

Freerouting also forces plane layers inactive itself (`dedicated power plane and cannot be
routed`), so a rules file cannot open your planes to signal routing.

## Priority-Based Iterative Routing (phased) - OPT-IN, never the default

Route the nets you care about first, on an empty board where every channel is still free; lock
them; then route everything else around them. **This is opt-in.** It is enabled only by listing
nets in `priority_routing.critical_nets`; with that list empty the workflow is a single pass,
which is the right default for most boards.

### The mechanism is verified, not assumed

`SetLocked(True)` on a track exports to Specctra as `(type fix)`, and Freerouting honours it.
Confirmed on a 4-layer board by fingerprinting every phase-1 item and re-checking after a full
second routing pass: **225 of 225 identical, then 165 of 165 on a second trial.** Zero moved.
The post-import geometric repair also leaves locked copper alone.

Do not take that on trust on your own board. `lock_nets.py` records a geometry fingerprint when
it locks, and `--verify` re-checks it afterwards. **Run the verify before trusting a phased
result** - a silent lock failure would corrupt exactly the nets the phase existed to protect.

### Freerouting cannot route a subset, so the DSN must

There is no command-line option for "route only these nets": hand Freerouting a board and it
routes everything it can reach. Phase 1 is therefore expressed by filtering the DSN's `(network)`
block with `dsn_filter.py`, which keeps the phase's nets, drops the rest, and prunes the class
member lists to match.

### The order is not negotiable

```
route phase 1  ->  repair geometry  ->  audit  ->  LOCK  ->  route phase 2  ->  verify lock
```

**Repair before locking, never after.** Lock first and the geometric repair either skips those
tracks - leaving phase-1 geometry unrepaired, the opposite of the intent - or edits locked items
and defeats the lock. The natural reading of "generate, audit, lock" puts the lock too early.

### Worked sequence

```
<kicad> route_freerouting.py BOARD --auto-clearance --export-only --outdir P1
python  dsn_filter.py P1/BOARD.dsn P1/phase1.dsn --params kicad_golden.project.json
<freerouting> -de P1/phase1.dsn -do P1/phase1.ses -mp 100 -l en -mt 1
<kicad> route_freerouting.py BOARD --import-only P1/phase1.ses
        ... neckdown / 45-degree repair, then kicad_audit.js ...
<kicad> lock_nets.py BOARD                      # locks + writes BOARD.lockfp.json
<kicad> route_freerouting.py BOARD --auto-clearance --export-only --outdir P2
<freerouting> -de P2/BOARD.dsn -do P2/phase2.ses -mp 100 -l en -mt 1
<kicad> route_freerouting.py BOARD --import-only P2/phase2.ses
<kicad> lock_nets.py BOARD --verify             # MUST report "lock held"
        ... stitch_planes.py, repair, kicad_audit.js ...
```

### OBSERVATION - what it actually bought, on one board

Measured on a 4-layer, 350-connection board (2026-09-19). **These are one board's numbers, not a
default to expect.**

| | single pass | phased, 16 nets | phased, 8 nets |
|---|---|---|---|
| unrouted | **2** | 12 | 11 |
| vias on the 8 key nets | 24 | **10** | **10** |
| length of those nets | 896.6 mm | 861.0 mm | 855.1 mm |

Two findings worth carrying to another board:

- **The via reduction is real and reproducible.** Critical-net vias halved, and the figure was
  identical under two independently derived critical sets, so it is not run-to-run variance.
  On power rails and long-haul signals those vias are inductance and return-path discontinuities.
- **The completion cost does NOT shrink with a smaller critical set** - 11 against 12 unrouted
  when the set went from 16 nets to 8. The cost is not how many nets route first; it is that
  phase-1 nets take globally direct paths across the whole board, and those paths become walls
  the residual routing cannot get past. A single pass can interleave everything at once.

So: pick the **smallest** set whose via count you actually care about. Adding more nets to phase 1
buys nothing and locks more copper. Expect to finish the remainder by hand, and judge the result
on critical-net via count - not on unrouted count, which will get worse.

### When not to use it

When the goal is maximum automatic coverage. The default single pass reached 99.4% on the same
board; phasing took it to about 96.9%. Phasing is for boards where the quality of a few nets
matters more than the completeness of the rest.

## After the Router: Plane Stitching — MANDATORY

**Freerouting places ZERO vias on plane nets.** This is the single biggest trap in the DSN round-trip.
The exporter marks inner planes `(type power)`, which correctly stops the router from routing on them —
but it also means the router never generates the vias that connect pads *to* them. Every surface-mount
GND and power pad comes back with no path to its plane, and a filled zone on In1/In2 does not touch an
F.Cu pad. Measured on a 277-part board: 180 GND and 100 +3.3V SMD pads, **0 vias on either net**,
accounting for 186 of the unconnected ratsnest entries.

After every import, before judging the result:

1. Count vias per plane net. Zero (or far fewer than the pad count) means stitching is missing, not that
   routing failed.
2. Place one via beside each plane-net SMD pad — **outside** the pad, joined by a short stub. Never
   via-in-pad unless the project parameters allow it for that part.
3. **Prefer diagonal placement at fine pitch.** For an 0.8 mm-pitch BGA with 0.45 mm pads the orthogonal
   gap is 0.350 mm but the diagonal gap is 0.681 mm — a 0.25 mm via fits diagonally and not orthogonally.
4. Re-fill zones after placing them, and again after removing anything.

On the reference board this converted 129 unconnected to 68 in one pass, with zero new violations.

**Boxed-in pads.** Where the router has filled every side of a pad, `stitch_planes.py` reports "no clear position".
`stitch_residual.py` tries a straight or one-bend stub to a via further out, checked with the true shapes; what it
cannot place either needs a neighbouring track shoved aside - finish it in KiCad's interactive router, or record
the pad in `plane_net_exceptions` with a reason when it can reach a same-net via. Measured on ServiceOne (338
footprints): 214 plane pads, 114 stitched by `stitch_planes.py`, 76 by `stitch_residual.py`, 11 left for KiCad.

## Export-time keepouts — what the DSN does not carry (1.18.0)

Freerouting sees only the Specctra DSN. Three things the board relies on are not in it; add them as rule areas
to the **export copy only** with `export_keepouts.py --export-copy`, never to the real board:

| Missing from the DSN | Effect seen | Option |
|---|---|---|
| The copper-to-edge rule (Freerouting keeps only its own clearance to the boundary) | 22 `copper_edge_clearance` errors after one import (ServiceOne) | `--edge-band <rule + 0.05>`: a band along the outline and around every cut-out, one zone per ring |
| Pad-local clearance (fiducials) | a track 0.12 mm from a fiducial with a 0.35 mm local clearance | `--fiducials` |
| The crystal / inductor ban (audit `crystal-inductor`) | other nets under the part body | `--corridors auto`: courtyard minus one entry corridor per pad, so the part's own nets still route in a single pass |

**pcbnew saves only the first outline of a zone** built with several (KiCad 10.0.6): build one zone per ring or
piece, as the tool does - a multi-ring zone silently loses its rings at the save, before any export.

## The new-FAIL gate — MANDATORY for every change to a routed board (1.27.0)

**A change is accepted only if it adds no audit FAIL. A lower FAIL total never excuses a new one.**

Run the audit on the board before the change (the baseline) and after it, and compare the findings themselves:

```bash
python scripts/audit_gate.py <baseline.kicad_pcb | baseline.audit.json> <result.kicad_pcb | result.audit.json>
```

Exit 1 lists every FAIL the result has and the baseline did not. A finding's identity is its check plus its message
with the measured numbers blanked: a FAIL on copper that only moved keeps its identity, while the same kind of FAIL on a
new pad pair, net or via is new. `finish_gated.py`, `centre_gated.py` and `refinish_gated.py` apply the gate to every
route, batch or attempt they keep.

**Why this is a rule.** ServiceOne rev. 0.2, D133 (2026-10-21): the ADC region was re-placed and re-routed by script
under a gate that asked only whether the board's total FAIL count fell. The board carried about 1 900 known FAILs.
The rip-up removed 357 of them, and that hid 220 new ones: 93 between-pads, 82 pad-entry, 31 via (two inside pads,
four inside an IC pad-row band, 17 with the ring on a pad), and 6 acute joints. The total went from 1 932 to 1 795,
so every step "passed". The reviewer (Vladimir Duk) found them at once, and every one broke a rule that already
existed. A count over a board with hundreds of known FAILs measures nothing about the change.

**Hand-off.** A board handed to someone else (the interactive router, a reviewer, the fabricator) carries no
dangling copper: DRC `track_dangling` and `via_dangling` are 0. Clean the stubs of a rip-up before the hand-off,
not after; the 45 stubs left at D133 read as defects to the reviewer, and they were.

## The copper-hygiene gate — KiCad Routing Tools as a second checker (1.29.0)

**When the KiCad Routing Tools plugin is installed, a change must also add no copper-hygiene finding.** The plugin
(github.com/drandyhaas/KiCadRoutingTools, from the KiCad PCM) ships a read-only checker, `py_router/check_weird.py`,
that sees joint defects the audit does not: `krt_check.py` runs it with KiCad's Python and gates on it the way
`audit_gate.py` gates on the audit.

```bash
python scripts/krt_check.py board.kicad_pcb                      # report: exit 0 clean, 1 findings, 2 not installed
python scripts/krt_check.py baseline.kicad_pcb result.kicad_pcb   # gate: exit 1 lists every NEW finding
```

| Finding | What it is |
|---|---|
| `soft-joint` | two same-net segments that meet only by overlapping end caps, not end point to end point: the "patched" look a reviewer sees as a defect, and fragile under any later edit |
| `redundant-cycle` | a loop edge whose removal leaves the net's connectivity identical |
| `removable-segment` | copper that can go without disconnecting anything or leaving a new dangling end |
| `stacked-copper`, `dangling-end`, `orphan-island`, `unsupported-via`, `dangling-via`, `narrow-pad-joint`, `kicad-dangling` | duplicates, stubs, islands, floating vias, corner joints thinner than the track floor |

- Identity is category + net + layer, counted (coordinates blanked): copper that only moved keeps its identity.
- `dangling-via` on a net poured on an inner layer the via spans is a false positive (the checker does not read
  inner fills; KiCad's DRC passes the via) and is filtered.
- `stage_gate.py` includes the check in every snapshot and compare when the plugin is found (`--no-krt` to skip);
  the plugin is located through `$KRT_DIR`, `--krt DIR`, the KiCad 3rdparty / scripting plugin folders, and the
  `KICADn_3RDPARTY_DIR` set in KiCad's own settings (a PCM folder under a company OneDrive is found that way).
- **Use only its checker.** Its router was tried on the GapOne CON board (2026-11-06): it closed all 98 open
  connections but added 1688 audit FAILs, ripped copper it had been told to keep (`--keep-input-copper`) and
  stepped plane-tap vias down to 0.25/0.15 mm, the fabricator's costlier tier. It has no push-and-shove.

**Why this is a rule.** GapOne CON clean-up (2026-11-06): chain re-routing with `route_finish.py` to coordinate
ends, then `dedupe_copper.py --tol 0.09`, passed DRC and the new-FAIL gate (audit 1722 -> 1682 FAIL, 0 new), and
was committed. The hygiene checker then found 79 soft joints that the hand-off board did not have: 55 from
`route_finish.py` ending on a chain end it could not reach exactly, 24 from removing the sub-0.1 mm pieces that had
joined two segments end to end. The audit has no check for an end-cap joint.

## The stop rule, locks and the gated tools — MANDATORY for scripted finishing (1.28.0)

**Estimate a scripted run before it starts and stop it when it does not pay** (L30, Vladimir's rule). Before: items
x attempts per item x time per attempt; show the estimate to the designer when it is over 15 min and agree a budget
(default 1 h). During: after 10 attempts or 30 min, stop when fewer than 1 in 5 attempts is kept or the projected
time exceeds the budget; report what was kept and why the rest failed, and hand the rest to the interactive router
with its ends (`open_ends.py`). `finish_gated.py`, `refinish_gated.py` and `gate_each.py` apply it themselves
(`--budget`, `--min-keep-rate`; `--no-stop-rule` only for experiments). Run a sample (10 candidates) before any
board-wide pass. ServiceOne D133 spent 3.5 h for 5 kept routes out of 74 attempts; a scripted rip-up of the U1 QFN
cluster kept 0 of 16 routes in 18 min. **Dense fine-pitch IC clusters are routed interactively, not ripped up by
script** (L43).

**A gated driver never moves a locked item** (L40). DRC and the audit do not see locks: every gated driver compares the
locked-item fingerprint (`locks.py`) after each attempt and reverts a change that moved, changed, removed or unlocked
one; the single-step tools skip locked items. Tell design locks (Kelvin sense, datasheet loops, hand-laid copper) from
tool locks (stitching vias placed by `stitch_residual.py`) before a hand-off: `locks.py BOARD --list` (L39). Tool
locks are fixed walls for KiCad's shove router.

**Gate each change against the board before it** with `stage_gate.py` (DRC no worse, unconnected not up, no new audit
FAIL, passing layout checks still passing, locks unchanged; about 30 s without the zone refill, L32), or drive a
candidate-indexed tool with `gate_each.py`:

```bash
python scripts/stage_gate.py work/snap board.kicad_pcb --snap --normalise   # baseline (pcbnew round-trip, L42)
python scripts/stage_gate.py work/snap board.kicad_pcb                      # after the change: exit 0 PASS, 1 BLOCKED
python scripts/gate_each.py board.kicad_pcb --indices 8,10,12 -- "<kicad-python>" scripts/via_relocate.py {board} \
    work/audit.json --mode axis --apply --indices {i}
```

Keep a region the designer is routing out of a board-wide pass with `--exclude-box` (L37). After KiCad's *Cleanup
Tracks and Vias*, gate the board too: "Delete tracks fully inside pads" removes the stub that carries a track to the
exact pad centre (L44), so leave it off.

## Finishing and centring under a DRC gate (1.18.0)

Two drivers apply many small geometry changes and keep each only when KiCad DRC (and, for centring, the audit)
does not get worse - the discipline of playbook G3/G4, made fast enough to use. Since 1.27.0 both also apply the
new-FAIL gate above:

- `finish_gated.py` - each open connection with `route_finish.py`, one at a time, kept only if DRC gains nothing,
  the unconnected count falls and the audit gains no FAIL. It cannot shove copper: boxed-in pads stay for the
  interactive router.
- `centre_gated.py` - the `between-pads` FAILs: `center_gaps_safe.py` proposes the moves, which are applied in
  batches and bisected on failure. ServiceOne: 195 candidates, 194 kept in the first round (about ten minutes),
  FAIL 427 -> 225 over four rounds. One-move-per-DRC gating would have taken hours per round.

Do NOT use `geometry_finish.py --pad-centre-entries` on a routed board without such a gate: in one pass it
snapped 48 entries and created 2 shorts, 3 clearance errors and a dangling track (ServiceOne) - the failure mode
that put `--center-gaps` on the playbook's "Do not use" list.

### Fine-pitch channel arithmetic — do this before attempting, not after

Compute what physically fits before asking a router for it:

```
orthogonal gap = pitch - pad_diameter
diagonal gap   = pitch * sqrt(2) - pad_diameter
max track      = gap - 2 * clearance
max via        = gap - 2 * clearance
```

For 0.8 mm pitch / 0.45 mm pads / 0.1 mm clearance: max track is **0.150 mm** orthogonally and
**0.481 mm** diagonally. A 0.6 mm POWER_DC track needs 0.800 mm and therefore **cannot** route between
BGA balls at any effort level — say so instead of running the router again. Power distribution inside a
BGA is a plane job, not a track job.

### Hole-to-hole is measured between DRILL EDGES

`min_hole_to_hole` is the gap between drill *edges*, not between centres:

```
gap = centre_distance - (drill_a / 2 + drill_b / 2)
```

Comparing centre distance against the rule directly is wrong by the sum of the two drill radii — 0.3 mm
for two 0.3 mm drills — and silently produces overlapping holes. Verify with `kicad-cli pcb drc` after
placing any via programmatically.

## Datasheet layout suggestions — BEFORE routing (1.26.0, playbook B0)

Many datasheets suggest a PCB layout, usually under headings such as "Layout Guidelines", "Layout Example", "Layout
Consideration" or "Suggested Layout", or in a hardware design guide. Use them before the first track is drawn,
because afterwards a wrong placement costs a re-route. **Scan every datasheet of every part on the board, then use
what they suggest.**

1. **Scan.** Run `python scripts/datasheet_layout_scan.py BOARD --datasheets DIR [--parts bom/parts.csv]
   --write-params`. It:
   - matches each part to its documents (the manifest, by MPN or LCSC code);
   - finds the layout pages and classes each one: guidelines, example (a figure) or land pattern (footprint check only);
   - extracts the rule sentences and renders each layout page as an image;
   - writes the report `datasheet_layout/datasheet_layout.md`, plus a `datasheet_layout` block in
     kicad_golden.project.json with every part `pending`.
   An IC, converter, crystal or inductor without a document is listed: get its datasheet and scan again.
2. **Read every hit: the text and the page image.** The drawing is the suggestion, and text extraction loses it.
   For each rule decide what it becomes:
   - a **placement** move: capacitor at the pin on the IC layer, crystal or RC next to its pin, small switch node,
     feedback divider at FB and away from SW;
   - a **`layout_checks`** entry: `decoupling` (pin, capacitor, max_mm, surface), `kelvin` (sense, shunt, load),
     `separation` (clock / digital vs analog inputs);
   - a **routing constraint**: netclass width for the power loop, `priority_routing` / route first, `route_finish.py
     --exclusive` (Kelvin) or `--avoid` (keep away), a keep-out, thermal vias under the pad (`via_in_pad`).
   Design choices go to the owner, for example split analog / digital grounds or a guard ring: ask, do not decide.
3. **Record** each rule under its part in `datasheet_layout.parts[].rules`, as `{rule, source ("doc p.N"),
   applied_as}`, and set the part's status to `applied`, or to `n/a` with the reason in `note`.
4. **Check the placement before routing:** `layout_measure.py check BOARD --pre-route` judges each `decoupling` entry
   by straight pin-to-pad distance, since the routed length can only be longer. Move every part that FAILs.
5. **Gates.**
   - The audit WARNs pre-flight when no review is on record, and FAILs while any part is `pending`.
   - `route_freerouting.py` refuses to export (exit 4) while a part is `pending`; `--skip-datasheet-review`
     overrides it, and you say why.
   - After routing, `layout_measure.py check` measures the same entries along the copper (section below).

## Datasheet layout review — after routing, before the outputs (1.19.0)

DRC and the audit prove clearances, connectivity and geometry; they do not read the **layout sections of the
datasheets**. A board can pass both while it breaks three of them:
- A current monitor's sense line taps the power track away from the shunt. This is legal copper on the same net.
- A clock runs 0.1 mm from an ADC input over 10 mm. Every clearance is met.
- An output capacitor 2 mm from a converter pin is joined only through two vias and the plane.

On ServiceOne (2026-10-05) these gave an estimated +20 % and +47 % current error and a clock beside a 24-bit input,
on a board with 0 DRC errors.

Do this for every IC whose datasheet has a layout section (`references/10_datasheet_layout_review.md`):
1. Find the sections. Separate guidelines and examples from land patterns, and drop the parts that are no longer in
   the BOM.
2. Turn each rule into a measurement with `layout_measure.py`. It follows the copper, plane hops included;
   straight-line distance hides exactly these defects:
   - `kelvin SENSE SHUNT LOAD`: PASS = no shared copper and no bypass of the shunt pad;
   - `path PIN CAP [--no-plane]`: routed length from a pin to its capacitor;
   - `gap --a NETS --b NETS --exempt X,Y,R`: same-layer separation;
   - `return PAD`: path to the nearest plane via.
3. Record the decisions in `kicad_golden.project.json` -> `layout_checks` and run `layout_measure.py check`.
4. Fix:
   - Kelvin: `route_finish.py --exclusive --from-pad SHUNT.PAD --to-pad MON.PAD`, after removing the old sense
     branch.
   - Part placement (oscillator, input RC, decoupling): a courtyard search first. Where no legal spot exists, it is
     a re-placement - record it, do not force it.
   - A converter capacitor joined on the surface: record both pads in `plane_net_exceptions`, citing the datasheet.
5. Re-verify with DRC, the open-connection list and the audit **diffed by message**. A moved part or a new via makes
   untouched neighbouring tracks reappear as between-pads FAILs.

**Prevent the clock-beside-analog case before autorouting.** Once Freerouting has put them in one corridor, only a
re-placement separates them:
- place the oscillator at the clock pin, on the digital side;
- or give the clock or the analog inputs a netclass with a larger clearance in the DSN.

## Zone Outlines: Territory, Not Fill

**Never subtract obstacles from a zone outline.** A KiCad zone polygon declares the *region* the filler
may use; the filler already clears foreign vias, pads and tracks by the clearance rule. Subtracting them
from the outline produces hole-riddled slivers whose exterior ring encloses almost no copper — observed:
polygons with a 30 x 9 mm bounding box, 814 vertices and 0.15 mm2 of actual area.

Rules for generated zone polygons:

- Build the outline from **union of buffered target points plus corridors**. Obstacles may only *veto* a
  corridor, never cut one.
- Simplify to a sane vertex count (0.03 mm tolerance is ample). Hundreds of vertices means something is
  wrong.
- **Reject slivers**: require area >= 1 mm2 and area / bbox-area >= 0.08.
- Export the exterior ring only. With no subtraction there are no meaningful holes, and any enclosed void
  is territory the filler will clear correctly by itself.
- A long thin corridor is a **plane split**. Keep them short and few; a 0.5 mm slot running 20 mm across
  a power plane is a return-path defect even when connectivity checks pass.

### Starvation check — the one that is easy to get wrong

When adding a higher-priority zone over an existing plane, verify **the incumbent plane**, not just the
new zones against each other. The correct test is connectivity, not containment:

```
plane_left = board_interior.difference(union(new_zones).buffer(clearance))
pieces     = sorted(plane_left, key=area, descending)
assert every incumbent via lies in pieces[0]
```

"Is this point inside a higher-priority polygon" is too weak — it misses copper that is technically
present but cut into islands. Checking only the new rails against each other (and not the plane they are
carving) cost 8 +3.3V connections on the reference board before it was caught.

Bounding-box splits over interleaved BGA rails remain forbidden — see §Complex Power Plane Splits.

## Verify Visually — Numbers Alone Are Not Enough

Every numeric check can pass while the geometry is wrong. Render the layer and look at it:

```bash
kicad-cli pcb export svg --layers "In2.Cu" --page-size-mode 2 --exclude-drawing-sheet \
  --output layer.svg board.kicad_pcb
inkscape --export-type=png --export-dpi=420 --export-filename=layer.png layer.svg
```

Then read the PNG. On the reference board this exposed a 20 mm sliver slicing the +3.3V plane that every
connectivity and clearance check had passed. Crop with matplotlib when a region needs magnifying.

**Optional geometry tooling.** `shapely` (polygon union / difference / connectivity) and `matplotlib`
(rendering) installed into KiCad's own Python are a large help for zone work and for the starvation check
above. They are **not required** — guard the import and fall back, because the shipped tooling must keep
working without them:

```python
try:
    from shapely.ops import unary_union
    HAVE_SHAPELY = True
except ImportError:
    HAVE_SHAPELY = False
```

Note what the tooling is actually for: on the reference board Shapely-built zones tied the simpler convex
hull approach on connectivity (60 unconnected either way). Its value was the **verification gate** and the
polygon hygiene, not better routing.

## Removing Copper Has Consequences

Deleting tracks or vias to clear a DRC error leaves **dangling stubs**, and removing those exposes more.
Iterate to convergence (8 passes were needed on the reference board), then re-fill zones.

Deletion also breaks connections that were previously good. Always report which nets regressed: on the
reference board, clearing 17 edge-clearance errors broke 8 nets that had been routed, three of them SDRAM
bits. Removing copper to satisfy a rule is a trade, not a fix — state both sides.

**Count connections as `pads - 1` per net**, not as a delta in DRC unconnected items. The two differ, and
the ratsnest denominator is the honest one.

## Hand-drawn copper is INVISIBLE to the router

A graphic line drawn on a copper layer (`PCB_SHAPE` on F.Cu/B.Cu, net assigned) is **not exported
in the Specctra DSN**. The DSN carries pads, tracks, zones and keepouts - nothing else. Freerouting
therefore routes straight through it, and the result is a genuine short that only `kicad-cli pcb
drc` catches: the golden audit passes, `route_report.py` reports full connectivity, and the DSN/SES
round-trip reports success.

**MEASURED**: one 0.2 mm hand-drawn line on F.Cu feeding a pad. A GND track crossed it at exactly
one point. DRC: `Items shorting two nets (nets GND and Net-(D10-A1))`. The same board routed at a
different via cost never crossed that spot, so the defect appeared only in one run - it is luck,
not a property of the design.

**Before routing**, either convert such copper into a real track (Edit > "Create tracks from
selected shapes", or redraw it), or cover it with a keepout rule area so the DSN exports the
obstacle. **After routing**, run `kicad-cli pcb drc` and grep for `shorting_items` - the audit alone
will not tell you.

This is also why `route_report.py` completion is not proof of correctness: it counts ratsnest
connections, and a short is not a missing connection.

## Manufacturing Outputs Generation — MANDATORY, the final phase

Immediately after the Post-Routing Geometric Audit passes and the `.kicad_pcb` is saved, generate
the fabrication outputs. This is not optional and it is not a separate request: a routed board that
has not been exported is not a deliverable.

### The gate

**Do not export while the audit reports a FAIL.** Gerbers are what the fabricator builds; exporting
a board that failed the standard just moves the defect downstream, where it costs money instead of
minutes. Audit first, fix, save, then export.

Zones must be filled before plotting. Pass `--check-zones` and let KiCad refill if needed — a stale
zone fill plots the *old* copper, silently.

### The command

```bash
kicad-cli pcb export gerbers \
  --output gerbers/ \
  --check-zones \
  --layers "F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts" \
  "<board>.kicad_pcb"

kicad-cli pcb export drill \
  --output gerbers/ \
  --format excellon --excellon-separate-th \
  --generate-map --map-format gerberx2 \
  "<board>.kicad_pcb"
```

**There is no `--use-gerber-x2` flag.** KiCad 10's `export gerbers` rejects it with
`Unknown argument`, and the run produces nothing. **X2 is the default**; the flag that exists is the
opt-*out*, `--no-x2`. So the correct action for X2 output is to pass no format flag at all.

VERIFIED on KiCad 10.0.6, same board, same command, only `--no-x2` differing:

```
default   %TF.GenerationSoftware,KiCad,Pcbnew,10.0.6*%      <- 6 real X2 attributes
--no-x2   G04 #@! TF.GenerationSoftware,KiCad,Pcbnew,10.0.6*  <- 0; demoted to X1 comments
```

That `G04 #@!` form is the X1 fallback: the same text, carried as a comment that no fabricator
parses as metadata. If a header looks like that, X2 was switched off.

A correct X2 header carries the project metadata the fabricator reads:

```
%TF.GenerationSoftware,KiCad,Pcbnew,10.0.6*%
%TF.CreationDate,2026-09-20T21:08:31-03:00*%
%TF.ProjectId,<project>,<uuid>,<rev>*%
%TF.SameCoordinates,Original*%
%TF.FileFunction,Copper,L1,Top*%
%TF.FilePolarity,Positive*%
```

### Drill files are part of the package, not an extra

Gerbers alone cannot be manufactured — there are no holes in them. The export above produces
`-PTH.drl` and `-NPTH.drl` plus drill maps. `--excellon-separate-th` keeps plated and non-plated
holes in separate files, which is what fabricators expect and what avoids a plating argument later.

The gerber export also writes a **`.gbrjob`** job file. Keep it: it is the X2 job description that
ties the layer set, stackup order and drill files together. Send the whole directory.

### Output location and layer list

- Output to a dedicated **`gerbers/`** (or `outputs/`) directory next to the board. Never into the
  project root, where the files are indistinguishable from source.
- **Name the layers explicitly, but do NOT blanket-exclude the user layers.** With no `--layers`,
  KiCad plots every *enabled* layer: on one real board that meant `User_1` through `User_9`, both
  `Courtyard` layers, both `Fab` layers and `Adhesive`. Most of that is noise. **The exception is a
  user layer that actually carries fabrication content** - dimensions, a fab drawing, stackup or
  assembly notes. Excluding those silently drops drawings the fabricator is meant to read, and the
  export reports success either way. **Enumerate before choosing:**

  ```python
  import pcbnew, collections
  b = pcbnew.LoadBoard(board); c = collections.Counter()
  for d in b.GetDrawings(): c[b.GetLayerName(d.GetLayer())] += 1
  ```

  Add the populated ones by untranslated name: `User.1`, `Cmts.User`, `Dwgs.User`. They export with
  `%TF.FileFunction,Other,User`, `Other,Comment` and `OtherDrawing,Comment`. Leave empty ones out.
- **A dimension on `Edge.Cuts` is a trap.** `Edge.Cuts` becomes the profile the board is cut to, so
  a dimension object living there is plotted into `*-Edge_Cuts.gm1` as if it were outline geometry.
  DRC reports it as `text_on_edge_cuts`, at error severity. **MEASURED:** one board carried 3
  orthogonal dimensions on `Edge.Cuts` beside the single real outline shape, while 5 more sat
  correctly on `User.1`. Move them to a user layer before exporting.
- Use **untranslated** layer names (`In1.Cu`, not the nickname). A renamed inner layer still exports
  correctly — a layer renamed `GND` is still selected as `In1.Cu` and lands in `-GND.g1`.
- Adjust the copper list to the stackup: 2-layer boards drop `In1.Cu,In2.Cu`; 6-layer boards add
  `In3.Cu,In4.Cu`.

### Report what was produced

State the output directory, the file count, and confirm the X2 attributes are present — do not
assume the export succeeded because the command returned 0. A one-line check:

```bash
head -1 gerbers/*F_Cu.gtl     # must start with %TF.GenerationSoftware, not G04 #@!
```

## Workflow

1. **New project** → close it in KiCad, run `apply_settings.js` on the `.kicad_pro` (rules, severities, defaults, **netclasses and name patterns**, straight-corner tuning). Copy `templates/kicad_golden.project.json` next to the board as `kicad_golden.project.json` and fill in the per-project decisions (length groups, via budget, fabricator limits, silkscreen, teardrops, via-in-pad parts).
2. **Before routing** → read `references/05_decision_rules.md`. Complete §0 in full, including Edge.Cuts sanitization and rule harmonization.
3. **After any change, and before saying "done"** → run `kicad_audit.js`. Fix every FAIL. Read every WARN and either fix it or state in the reply why it is accepted. Exit code 1 means not done — except for the documented stale checks above, which you must name and justify rather than silently pass over. On a board that already carries FAILs (a revision in progress), run `audit_gate.py` against the board as it was before the change: any new FAIL is yours and blocks the change, and "the total went down" is never the answer (§The new-FAIL gate). With KiCad Routing Tools installed, run `krt_check.py` the same way: a new soft joint, loop or removable segment blocks the change too (§The copper-hygiene gate).
4. **Schematic work** → `references/03_schematic.md`. The audit's schematic pass runs automatically when `.kicad_sch` files sit next to the board.
5. **Audit passes and the board is saved** → generate the fabrication outputs immediately: gerbers (X2, which is the default — there is no `--use-gerber-x2` flag) and drill files, into a dedicated `gerbers/` directory. See **Manufacturing Outputs Generation** above. Never export a board whose audit still FAILs.

## Scripts (Node.js, no dependencies)

```bash
# Windows: cwd MUST be short (Node refuses a long OneDrive cwd); the file paths may be long.
cd %USERPROFILE%     (Windows: keep the cwd short)
node "%USERPROFILE%\.claude\skills\kicad-routing\scripts\apply_settings.js" "<path>\project.kicad_pro" --dry-run
node "%USERPROFILE%\.claude\skills\kicad-routing\scripts\kicad_audit.js" "<path>\board.kicad_pcb" --json audit.json
```

- `kicad_audit.js <board.kicad_pcb> [--json out.json] [--no-sch] [--quiet] [--params file.json]` — exit 0 = PASS, 1 = FAIL, 2 = usage/parse error. Finds `<board>.kicad_pro`, `*.kicad_sch` and `<board>.golden.json` / `kicad_golden.project.json` next to the board. Console groups findings per check; the JSON holds every finding with coordinates and `stats`.
- `apply_settings.js <project.kicad_pro> [--fab jlcpcb --layers <N> --copper <1oz|2oz>] [--fab-exact] [--dry-run] [--no-bom] [--no-erc] [--no-schematic]` — merges `golden_settings.json`. Inserts or replaces the template netclasses by name, adds missing name patterns, keeps the project's own classes, patterns and `drc_exclusions`; writes a `.bak-<timestamp>`. 1.18.0: predefined via sizes and track widths are MERGED with the project's (union), `unconnected_items` is never lowered below a project `error`, an existing schematic connection grid is kept, and `--no-schematic` skips the schematic block. Its `--help` string omits the `--fab` flags; they are supported.
- `settings_report.js <project.kicad_pro> [--pcb board] [--diff] [--out report.md]` — Markdown report of any project's configuration, with `--diff` against the template. Use it when another team's project is offered as input: read the report, adopt what the review process approves, never import its severities.
- `krt_check.py <board> | <baseline> <result> [--json F] [--tolerance 0.1] [--krt DIR] [--kicad-python P]` — runs KiCad Routing Tools' `check_weird.py` (copper hygiene) and reports, or gates on new findings. Exit 2 when the plugin is not installed. See §The copper-hygiene gate.
- `doctor.py [--json F] [--quiet]` - reports what THIS machine can do, per interpreter: pcbnew,
  shapely, node, kicad-cli, java version, and which Freerouting it found (native launcher vs jar).
  Run it with both interpreters; they differ, and the difference has cost real debugging time.
- `init_project.py <board> --fab NAME --layers N --copper 1oz|2oz [--force]` - seeds
  `kicad_golden.project.json` from a REAL board. Length groups, diff-pair rules and the via budget
  are left EMPTY; the board's actual bus candidates, diff-pair candidates, long-haul nets and
  clearance floor are recorded alongside them as observations to decide from. 1.18.0: also writes
  `via_in_pad`, `shared_pad_gaps`, `plane_net_exceptions`, `detour_limits`, `priority_routing` and
  `router_costs` with every decision list EMPTY - do not copy those blocks from another project.
  1.29.0: `pad_entry` (`bend_min_mm`, default 0.5; `bend_check`, default true) may be added by hand
  on an owner decision recorded in the project's decision register; absent = the skill default.
- `netclass_propose.py <board> [--apply] [--min-pads N] [--json F]` - derives POWER_DC patterns
  from the netlist. Distinguishes current-carrying rails from sense/feedback taps (a divider tap
  must NOT be widened) and exits 1 when a rail would be left on Default.
- `rules_writer.py <board.dsn> <out.rules> [--via-cost N] [--params FILE]` - generates the
  Freerouting `.rules` file (`-dr`): via cost, plane via cost, rip-up cost, per-layer preferred
  direction and trace costs. Quotes the design name, which is what stops the whole file being
  silently ignored. Runs on any python.
- `dsn_filter.py <in.dsn> <out.dsn> [--nets A,B | --params FILE] [--invert]` - restricts a Specctra
  DSN to a subset of nets, the only way to make Freerouting route a phase. Runs on any python.
  Verifies the output's structure against the input's before writing; note that a DSN is NOT
  KiCad s-expression (backslashes are literal, and `(string_quote ")` uses a bare quote as a
  value), so an absolute paren-balance check gives false failures.
- `lock_nets.py <board> [--nets A,B] [--verify] [--unlock]` - locks a phase's copper and
  fingerprints its exact geometry; `--verify` proves a later phase did not move it. Reads
  `priority_routing.critical_nets` when `--nets` is absent, and refuses to guess otherwise.
- `route_report.py <board> [--json F] [--span-mm N] [--stitch-mm N] [--quiet] [--fail-on-gap]` —
  **the completion metric**: connections routed out of `pads - 1`, per netclass; footprint-local
  clearance overrides; long-haul nets; plane-stitch gaps; via padstack inventory with an
  `<< INVALID` flag on any drill >= its own pad. Run it before routing and after every stage.
- `route_sweep.py <board> [--clearances A,B,C] [--passes N] [--threads N] [--keep-all] [--dry-run]` —
  runs the router once per candidate clearance, scores each with `route_report.py`, names the
  winner. Floor defaults to the largest footprint-local override. Each candidate is a full run.
- `route_freerouting.py <board.kicad_pcb> [--fr-cmd C] [--passes N] [--timeout S] [--threads N] [--outdir D] [--export-only] [--import-only F] [--no-fill]` [--auto-clearance] [--clearance MM] [--no-padstack-gate] [--no-plane-filter] — **run with KiCad's Python, not the system one.** Backs the board up, fills zones, exports the DSN, filters inner-layer plane nets out of it by default (improvements #7 — pass `--no-plane-filter` to restore the pre-1.16.0 behaviour), auto-discovers and runs Freerouting, verifies the `.ses` is non-empty, imports it, re-fills and saves. Never leaves a half-imported board: on timeout or an empty session it aborts with the board untouched.
- `plane_plan.py map|apply|check <board> [--layer In2.Cu] [--rails A,B] [--cluster-mm 6] [--min-pads 3] [--out DIR] [--params F] [--dry-run] [--json F]` — **KiCad's Python.** Plane plan after placement, before routing (L23). `map` (read-only) proposes islands per power rail on an inner layer and measures each one: pads served, pads still without their own via, voltage and gap, crossings by tracks on the adjacent signal layer, main-plane pieces and thin copper left, Kelvin sense vias inside; writes a PNG, a Markdown trade-off table and JSON ready for `plane_plan.islands`. The designer decides. `apply` (board_guard, refill) writes the decided islands as named zones above the main plane, editing an existing one in place. `check` (exit 1 on FAIL): empty or isolated island fill, main plane split, Kelvin broken; WARN thin copper, adjacent crossings, pads without a via. Audit section 30 checks the plan without KiCad.
- `layout_measure.py path|return|kelvin|gap|check <board> ...` — **KiCad's Python, read-only.** Measures a routed board against datasheet layout rules along the copper (tracks, vias, plane hops): pin-to-capacitor routed length, return path, Kelvin connection (shared copper with the load path, shunt bypass), same-layer gap and parallel length between net groups. `check` runs `layout_checks` from the project file and exits 1 on a FAIL; `check --pre-route` (1.26.0) judges the decoupling entries by straight distance before routing. See §Datasheet layout review.
- `datasheet_layout_scan.py <board> --datasheets DIR [--manifest F] [--parts bom/parts.csv] [--out DIR] [--write-params [FILE]] [--refs-regex RE]` — system Python with PyMuPDF. BEFORE routing: finds the layout sections (guidelines / example / land pattern) in every document of every part on the board, extracts the rule sentences, renders the pages, writes a report and a `datasheet_layout` review block (status pending / applied / n/a, merged on re-scan). See §Datasheet layout suggestions.
- `route_finish.py <board> --net N (--from X,Y | --from-pad REF.PAD) (--to X,Y | --to-pad REF.PAD) [--width MM] [--grid MM] [--safety MM] [--via-cost N] [--dry-run] [--exclusive [--allow REF.PAD,..]] [--block-courtyards [--courtyard-exempt REF,..]] [--avoid NETS --avoid-margin MM --avoid-exempt X,Y,R --avoid-layers L] [--edge MM] [--no-axial] [--allow-acute]`, or `route_finish.py <board> --refinish REF.PAD [--refinish-length 1.5]` — 1.27.0: no turn sharper than 90° (the search carries its arrival direction; a route with an acute joint exits 5 without writing). 1.23.0: every pad end is an **axial stub** from the exact pad centre along the pad axis (elongated: long axis; square: either; IC pin: outer end first; passive: the side facing the route) to pad edge + 0.5 mm, no wider than the pad's smallest dimension; the grid origin is shifted so the stub axis passes through the exact centre; a pad off the 45-degree lattice or with a blocked axis exits 1 (`--no-axial` routes the 1.19 way). `--refinish` cuts the track into a pad back to a vertex >= 1.5 mm of copper away (a pad-to-pad chain is re-routed whole) and re-routes it with a stub; one non-axial entry per run, an existing axial stub of the pad is shared; nothing is saved without a route. A route that would duplicate same-net copper exits 4. `refinish_gated.py <board> [--pads ..|--max N]` (system Python) takes the pad-entry FAIL pads from the audit and keeps each re-route only when DRC holds, the audit FAIL count falls and no passing layout check breaks. 1.19.0: `--exclusive` draws a dedicated trace (the rest of the same net is an obstacle: Kelvin sense lines), `--from-pad/--to-pad` end exactly on pad centres, `--block-courtyards` keeps out of other parts, `--avoid` keeps a margin from given nets; hole and edge clearance come from the board settings, and new vias get the audit's layer flags. Grid maze router for the connections the autorouter left, one at a time, on the 45° lattice. **Run with KiCad's Python.** Exits 3 without writing if any segment would be off-lattice. Routing ORDER changes the result (measured 3 / 4 / 4 unrouted for three orderings of the same 8 connections) — try a couple and keep the best. DRC after each net.
- `stitch_planes.py <board> [--nets A,B] [--report] [--dry-run]` — places the plane stitching vias the
  external router never emits. **Discovers the plane nets from the board's own inner-layer zones**;
  nothing hard-coded. Diagonal-first placement, widest predefined via that fits, hole-to-hole measured
  drill-edge to drill-edge. Runs on the system python. `--report` just prints SMD-vs-via counts per plane.
  1.18.0: honours rule areas (board-level and footprint-internal) that forbid vias or tracks; reads Edge.Cuts
  drawn as polygons, rectangles, circles and arcs (lines only before - a polygon outline had no edge at all);
  models a pad by half its diagonal (half its larger side left the corners out) and a custom pad by its primitives.
- `stitch_residual.py <board> REF-PAD [REF-PAD ...] [--apply]` — **KiCad's Python.** For the plane pads
  `stitch_planes.py` could not reach: a straight or one-bend 45° stub to a via, checked with the true pcbnew shapes
  (copper and hole clearance, hole-to-hole for every drill including same-net ones, edge, rule areas, crystal /
  inductor courtyards). New copper is locked. Gate the result with DRC.
- `pad_row_keepouts.py <board> --list|--export-copy|--write [--refs U1,..] [--exclude U9] [--ref-pattern RE] [--min-pads 6] [--margin 0.5] [--json F]` — **KiCad's Python.** "No vias" rule areas over every IC pad-row band (L16), with the geometry of audit section 26: U*/IC* parts with >= 6 copper pads, rows of >= 3 equal pads at a uniform pitch, not through the origin, not an exposed pad split into same-number pads; band from the inner pad ends to 0.5 mm beyond the outer ends, first to last pin. `--list` (read-only) also lists the vias whose copper already reaches a band; `--write` puts `KO_ROW_<ref>_<n>` on the real board (board_guard, edited in place, item nets verified from the saved file), so Freerouting (via_keepout), the interactive router and DRC keep vias out; `--export-copy` writes `KO_EXPORT_ROW_*` on a DSN copy only.
- `export_keepouts.py <export-copy> --export-copy [--edge-band MM] [--fiducials] [--corridors auto|REF[:side],..] [--pad-row-bands]`
  — **KiCad's Python, export copy only.** See §Export-time keepouts.
- `finish_gated.py <board> [--width NET=MM ...] [--default-width MM] [--no-audit-gate]` — system python; drives
  `route_finish.py` connection by connection under a DRC, layout and (1.27.0) new-FAIL gate; backup `.bak_prefinish`.
  See §Finishing and centring.
- `audit_gate.py <baseline> <result> [--params F] [--json OUT] [--quiet]` — system python + node. The new-FAIL gate:
  baseline and result are boards (audited here) or audit JSON reports; exit 1 lists the FAILs the result added. Also a
  module (`audit`, `fail_ids`, `new_fails`) for the gated drivers. See §The new-FAIL gate.
- `stop_rule.py` / `locks.py` (1.28.0) — modules used by the gated drivers: the stop rule (L30) and the locked-item fingerprint read from the file text (L40). `locks.py BOARD [--list] [--compare OTHER]` lists the locked items per net or compares two boards (exit 1 when a locked item moved). Any Python.
- `stage_gate.py SNAP BOARD --snap [--normalise]` / `stage_gate.py SNAP BOARD [--refill]` (1.28.0) — system python + node + KiCad. Snapshot of the baseline (board, project files, parameters, 3D-model folder), then the per-change gate: DRC no worse, unconnected not up, no new audit FAIL, passing layout checks kept, locks unchanged. Without `--refill` the zone-fill violations are ignored (L32). Also a module (`snapshot`, `compare`).
- `gate_each.py BOARD (--count N [--start S] | --indices a,b) [--budget MIN] [--min-keep-rate R] [--refill-every N] -- TOOL...` (1.28.0) — runs a candidate-indexed tool (`{i}`, `{board}` in its command line) one candidate at a time, each change gated by `stage_gate.py` against the start, under the stop rule; a refill check every N kept changes and at the end; backup `.bak_pregate`.
- `via_relocate.py BOARD AUDIT.json --mode web|axis [--apply] [--indices a,b] [--box ..] [--exclude-box ..]` (1.28.0) — **KiCad's Python.** `web`: slides a plane via along its stub until the ring keeps the 0.15 mm mask web (L15). `axis`: moves a plane pad's via onto the pad axis past the stub zone, with a straight stub from the pad centre (L38), so `refinish_gated.py` can then work. Locked vias are skipped. No gate of its own: drive it with `gate_each.py`.
- `open_ends.py BOARD DRC.json OUT.json [--pairs 3]` (1.28.0) — **KiCad's Python.** For every open connection, the two copper islands and the best end pairs (pad, free track end, via) to route between - not the DRC marker positions (L31). Also the hand-off list (L29).
- `dangling_classify.py BOARD ENDS.json DRC.json OUT.json [--apply]` (1.28.0) — **KiCad's Python.** Keeps lead-ins of open connections (and locked copper), removes unused stubs and vias whole; never iterate it (L33).
- `via_spot.py BOARD NET x0,y0 x1,y1 STEP [--d 0.45] [--drill 0.2]` (1.28.0) — **KiCad's Python.** Copper and hole-to-hole clearance of a via at each point along a line: scan the legal spots before a fix, list the item when there is none (L34). Read-only.
- `dedupe_copper.py BOARD [--apply] [--box ..] [--exclude-box ..] [--indices K]` (1.28.0) — **KiCad's Python.** Removes a same-net segment that lies inside another (L19); keeps pad-centre stubs (L44) and locked segments.
- `edit_tracks.py BOARD SPEC.json [--allow-locked]` (1.28.0) — **KiCad's Python.** An exact, scoped copper edit from a JSON spec (segments and vias matched by their end points; aborts on a missing or ambiguous match; refuses to delete a locked item).
- `center_gaps_safe.py <board> <audit.json> [--apply] [--index N | --indices a,b,c] [--allow-locked-nets A,B]` —
- `fanout_regularise.py <board> --list|--apply [--refs U1,..] [--params F] [--force-write]` — **KiCad's Python.** Aligns the first bends of each IC fan-out group (audit section 31: the tracks of one pad row that leave axially and bend the same way) on one line, at the largest current bend distance, never closer than pad edge + 0.5 mm. It slides each first bend along the exit axis and the next vertex along its own run, so every segment keeps its direction and the far vertex stays put. When no slide fits, it re-routes the group's pins with `route_finish.py --refinish --refinish-force`, which puts every bend at pad edge + 0.5 mm. Each group is kept only when DRC, the audit FAIL count and the fan-out WARN count do not rise and one of the two counts falls. Groups with a locked track or a Kelvin pad are left.
- `model_builder.py spec <spec.json> --out DIR [--assign FP.kicad_mod]` / `model_builder.py footprint <FP.kicad_mod> --height H --out DIR [--body fab|courtyard|pads] [--standoff Z] [--pin-length L] [--assign]` — any Python. Approximate box models as STEP (AP214) and VRML, named `*_approx` (L26). Use it only after the search has failed: KiCad's library, EasyEDA by LCSC code, then the manufacturer. `spec` takes boxes in the footprint frame (mm, y down, z up from the board) from the datasheet drawing. `footprint` builds a body over the F.Fab outline up to H and one box per pad (a lead on the board for SMD, a pin below it for THT). `--assign` writes or replaces the footprint's (model ...) block with a `${KIPRJMOD}` path. The audit lists every `*_approx` model (section 28) for the release note.
- `mounting_hole_fp.py --lib DIR.pretty --hole D --contact-top D1 --contact-bottom D2 [--margin 0.5] [--plated RING] [--layers F.Cu,B.Cu|all] [--pour-allowed] [--name N] [--note TEXT]` — **KiCad's Python.** Mounting-hole footprint that carries its mechanical keep-out (L24). The rule area KO_MECH forbids tracks, vias and pours within max(D1, D2) / 2 + 0.5 mm, and the courtyard is the keep-out circle. KiCad's DRC, the Specctra export and the audit (section 27: covered, no `mechanical_keepouts` entry needed) all see it. Ask the contact diameters (pillar, standoff, screw head, nut, washer) at setup.
  **KiCad's Python.** Per-move centring of the audit's `between-pads` FAILs (playbook E6); never run unattended -
  use it through `centre_gated.py`.
- `centre_gated.py <board> <workdir> [--apply] [--rounds N]` — system python + node + kicad-cli; batched, bisected,
  DRC- and audit-gated centring rounds. The board changes only with `--apply`.
- `repair_import.py <board> [--drc r.json --delete TYPE,...] [--declang] [--kicad-cli PATH] [--dry-run]`
  — post-SES repair: adds the Q-06 via flags, raises sub-minimum track widths, and optionally deletes
  DRC-implicated Track/Via items then iterates the dangling-stub cleanup to convergence. Finds
  `kicad-cli` itself. **Always reports which nets the copper removal made worse.** On a board with open
  connections, do not iterate the dangling clean-up: classify with `dangling_classify.py` first (1.28.0, L33).
- `fab_layer_fix.py <board> [--hide-values] [--center-refs] [--add-missing-refs] [--all] [--min-height MM] [--dry-run]`
  — improvements entries 1 & 2. Hides (never deletes) Value text on F.Fab/B.Fab and any `${VALUE}`
  user text; centres and shrinks-to-fit the Fab reference text on the Fab outline's bounding-box
  centre (fallback courtyard, then footprint origin), aligned to the long axis, floor 0.3 mm; adds a
  `${REFERENCE}` text to a footprint that has none on its Fab layer. **Run with KiCad's Python.**
- `geometry_finish.py <board> [--all | --center-gaps --neck-pad-entries --pad-centre-entries --spread --route-around --fix-plane-links --report-shared-gaps] [--crystal-inductor-keepouts] [--params FILE] [--dry-run]`
  — improvements entries 3-11, see §Post-Routing Geometric Refinement. **Run with KiCad's Python.**
  `--crystal-inductor-keepouts` is pre-routing (adds rule areas), everything else is post-import
  repair. Fixes the common single-segment topology and reports the rest by reference/net for manual
  attention; `--route-around` reports candidates only (no automated reroute); `--spread` is
  best-effort, not guaranteed to zero the count.
- `rail_zones.py <board> --nets A,B --layer In2.Cu [--plane-net N] [--dry-run]` — polygon zones for
  interleaved BGA rails, built as a union of buffered via points plus vetoed-not-cut corridors, with
  simplify + sliver rejection. Verifies the incumbent plane by **connected components**, and exits 3
  rather than stranding its vias. Needs `shapely`; exits 4 with instructions when absent. **Check which interpreter has it** — on the
  reference machine `shapely` is installed in KiCad's python and NOT in the system one, so running
  this on the system interpreter reports it missing while it is in fact available.
- `kicad_sexp.py` — shared depth-tracking s-expression parser and the `verify_write()` gate
  (balance, census, byte-identity of protected blocks, indentation) used by the three above.
- **No-script path (KiCad UI)**: Board Setup → "Import Settings from Another Board…" → `templates/import_source/Golden_Import_Source.kicad_pcb`; tick Constraints and Netclasses (separate categories), Layers only for a 4-layer board. Regenerate that folder with `apply_settings.js` after editing `golden_settings.json`.
- **Tooling policy**: the audit and settings scripts are Node and must stay dependency-free. The post-router python tools ship alongside them and are dependency-free too, except `rail_zones.py`, which needs `shapely` behind a guarded import and degrades with a clear message. Python is available two ways and they are not interchangeable: the system interpreter (3.14.5, invoked as `py`) for ad-hoc board analysis, and **KiCad's own interpreter** (`C:\Program Files\KiCad\10.0\bin\python.exe`) for anything importing `pcbnew` — see §Automated External Routing.
- **`PCB_VIA.GetWidth()` needs a layer on KiCad 10.** Vias may carry a per-layer width; the arg-less
  call trips a wxWidgets assertion that can pop a **modal dialog and hang a headless script**. Use
  `GetFrontWidth()` (or `GetWidth(pcbnew.F_Cu)`). `GetDrill()` is unaffected.
- **`pcbnew` caches the project by path.** `LoadBoard` pins the `.kicad_pro` settings in memory, so
  editing that file afterwards has no effect on the same run — and `SaveBoard` writes the cached
  copy back, silently reverting the edit. Make project edits before the first `LoadBoard`, or after
  the last `SaveBoard`, and read board facts from the file when both must happen in one run.
- **S-expression editing**: never edit a board with line-based regex alone. Use a depth-tracking scanner that respects quoted strings and backslash escapes. After every write, verify that paren depth returns to 0, never goes negative, no string is left unterminated, top-level block censuses match expectation, and every preserved block is byte-identical. Preserve the file's CRLF/LF style and tab indentation; delete whole lines so no orphan indentation is left behind. Back up before writing.

## Core rules (the ones that decide PASS/FAIL)

- **Layers**: 4-layer, 1.6 mm. Route on F.Cu and B.Cu only. In1.Cu = GND plane, In2.Cu = power plane, both declared with layer type `power`. A track on an inner layer is a FAIL.
- **Geometry**: every segment on the 0/45/90/135° lattice (±0.01°). Prefer 45° mitres (reference 94 %). **No acute joints** (1.27.0): where tracks of one net meet on one layer, away from a pad centre or a via, two neighbouring branches are at least 90° apart — a 135° turn (interior 45°) or a T branch 45° off its run is a FAIL (audit section 32); route the corner as two 45° bends. **Zero arcs**: any track arc is a FAIL. Length-tuning meanders use straight (chamfered) corners. No teardrops unless the project parameters allow them.
- **Netclasses decide widths and vias** (Q-04): Default 0.2 mm; POWER_DC 0.6 mm / via 0.6/0.3; POWER_AC 1.5 mm, 3.0 mm clearance; one class per bus group. A track not at its class width is WARN (predefined widths and BGA escapes excepted); a via matching neither its class nor a predefined size is FAIL. Below 0.2 mm only within 2.5 mm of BGA/fine-pitch pads.
- **Vias**: size floors come from the fabricator profile on 4L+ (see High-Density Via Allowance: JLCPCB 0.25 / 0.05, predefined 0.25/0.15); through F.Cu–B.Cu only, tented both sides, `remove_unused_layers yes` and `keep_end_layers yes` on every via (**FAIL if missing**, Q-06). Hole-to-hole ≥ the project rule (fabricator limit, Q-11). No via inside an SMD pad except same-net thermal vias in exposed pads of parts listed in the project parameters (Q-05).
- **Snapping** (rev P / Q-01, Q-02 superseded — see improvements entries 8, 9): inside a pad's clearance area a track may reach the pad only as **one straight segment along one of eight directions through the pad centre** (0/45/90/135/180/225/270/315°), ending exactly at the centre within 1 µm — never at the pad edge or a corner, and never with a jog inside the clearance area. Elongated pads (≥ 1.5× longer than wide) take the **axial** entry (straight through the short outer end); a non-axial entry is a FAIL since 1.20.0 (was WARN), and the last bend sits at least 0.5 mm from the pad edge. At pitch ≤ 0.65 mm any pad-entry finding is a defect to fix, never a recorded deviation (reference 11, L10–L11). Inside the clearance area the segment is also no wider than the pad's smallest dimension (Q-04a / improvements entry 5) — step down to it before crossing the clearance outline; outside the clearance area a track keeps its full netclass width. `route_finish.py` and the post-import repair both enforce this; large pads (≥ 2 mm) are no longer exempt.
- **Between-pad centring** (improvements entries 3, 4): a track passing through the gap between two pads it does not connect to — whether the pads belong to different footprints or to the same two-pad part (resistor, capacitor, LED, diode) — must run along the centre of that gap: equal copper-edge clearance to both pads within 0.01 mm. A gap between pads of different parts, or of a multi-pad part, is at most 1.5 mm of free copper-edge width; wider spaces are open board. Under a two-pad part any width counts. Pads beside the pad a track starts or ends in are not a gap: there the pad-entry rule governs (local 1.16.0-local.1). Never route a track of another net under a crystal or inductor (ref prefix `Y`/`X`/`L`, footprint library `Crystal*`/`Inductor*`) on the copper layer it is mounted on — this is a hard FAIL regardless of centring, and pre-routing keepouts should cover those courtyards.
- **Route around, not under** (improvements entry 10): prefer detouring a track around a component to passing it between two of its pads. Pass under only when no detour fits within `detour_limits` in the project parameters (default ≤ 50 % / ≤ 10 mm longer, no added via); remaining under-part tracks are WARN, listed with the detour length that would have been needed.
- **Even spacing** (improvements entry 11): do not leave a track at minimum clearance when free space exists on one side; spread tracks and component-outline gaps as evenly as the space allows. Never at the cost of a lattice break, a new via, a DRC violation, or the detour limits above; pad entries (Snapping, above) are left alone.
- **Shared pad gaps** (Q-16 / improvements entry 6): by default, at most one track passes through the gap between two adjacent pads, at full netclass width. Ask the user before routing (§0); when not allowed, a gap carrying 2+ tracks is FAIL, otherwise WARN.
- **Plane-net pads are via-only** (D3, promoted to a Core rule / improvements entry 7): a net with its own inner-layer plane (GND, and any power rail with an In\*.Cu zone) is never joined pad-to-pad by a surface track on F.Cu/B.Cu. Every SMD pad of that net gets its own short stub and its own via straight to the plane — nothing more. FAIL when a surface track's connected component touches two or more pads of a plane net, unless the pair is listed with a reason in `plane_net_exceptions` (project parameters), in which case it is INFO. `route_freerouting.py` filters plane nets out of the DSN before export by default so Freerouting cannot invent these links; `stitch_planes.py` then places the real vias.
- **Board-review rules (1.20.0, reference 11)** — each is an audit check unless marked otherwise:
  - a track at a fine-pitch pad is no wider than the pad and its round end does not stick out of it (L9);
  - no same-net tracks crossing each other, no same-net loops or duplicate parallel copper (L12, L19);
  - vias: none between the pads of a two-pad part (L14); ring ≥ 0.15 mm from any SMD pad, same net included (L15); none inside an IC pad-row band (L16); plane vias at fine-pitch ICs use the small predefined via (L13, WARN); drill not below the fabricator's economical tier unless approved (L8);
  - one track per THT gap where a neighbouring gap is free (L17, WARN); straighten detours (L18, WARN); orthogonal channel routing inside pin arrays, no diagonal longer than half a pitch (L21);
  - between-pads findings are fixed, never accepted as deviations (L20);
  - mechanical keep-outs around every mounting hole / pillar: largest contact diameter / 2 + 0.5 mm, from `mechanical_keepouts` (L24);
  - every footprint has a 3D model, `*_approx` models listed (L25, L26);
  - finishing (script / playbook): zones refilled **and saved** after scripted copper edits (L1), KiCad Cleanup Tracks and Vias with the settings of L2, board-writing scripts refuse lock files and a missing `.kicad_pro` (L3, L4), `finish_gated.py` reverts routes that break a layout (Kelvin) check (L5), `apply_settings.js` keeps `approved_rule_deviations` (L7);
  - planning: plane plan after placement (L23) with `plane_plan.py` and audit section 30 (1.21.0); fan-out pattern (L22) with audit section 31 and `fanout_regularise.py` (1.24.0).
- **Rules are enforced, not counted (1.27.0, reference 11, L27–L29)**: every change to a routed board passes the new-FAIL gate (`audit_gate.py`: zero new FAILs against the board before it, however much the total falls) (L27); no acute joints (L28); no hand-off with dangling copper (L29).
- **Finishing under the gates (1.28.0, reference 11, L30–L44)**: the stop rule for every scripted run (L30); no gated change moves a locked item (L40); dangling copper is classified (lead-in, overhang, unused) before anything is removed (L33); a fix that needs a neighbour moved goes on the interactive router's list (L34, L43).
- **Orthogonal-first routing (1.28.0, L41, Vladimir's rule)**: tracks run horizontal or vertical; a 45° segment is a corner chamfer or a link of at most `routing_style.diagonal_max_mm` (default 3 mm; one pin pitch inside pin arrays). A longer diagonal needs a listed reason in `routing_style.diagonal_exceptions` (fan-out escape, datasheet loop, clock or analog line where length matters). Preferred directions F.Cu horizontal, B.Cu vertical as a soft cost. Audit section 33: WARN per long diagonal outside IC fan-out zones, INFO with the diagonal share per layer.
- **Keepouts**: enumerate top-level **and footprint-internal** rule areas (see Keepout Enumeration) and report the count even when zero; never cross or enter a same-layer track keepout (FAIL). Passing under one with a via pair is WARN unless the project parameters allow it (Q-10). If a board declares zero `rule_area` keepouts, say so rather than implying the rule was applied.
- **Diff pairs**: `_P/_N` naming; width and gap from the class (Default 0.2 / 0.25); intra-pair mismatch limits per project parameters.
- **Length matching and via budget**: per-project parameters (Q-07, Q-08, Q-09); the standard fixes the mechanism, not the numbers.
- **Zones**: net-assigned, `hatch edge 0.5`, thermal reliefs 0.5/0.5, clearance 0.1 (0.05 small local pours), min_thickness 0.1 planes / 0.25 outer pours / 0.05 small pours, unique priorities where zones overlap. Solid connection only on mounting-hole and heatsink pads. Inset every plane polygon so it clears **every** `Edge.Cuts` item by at least the edge-clearance rule. Zones are written unfilled; tell the user to run **Edit → Fill All Zones (B)**.
- **Power plane splits**: see §Complex Power Plane Splits below — a hard prohibition.
- **Edge**: single closed Edge.Cuts outline, stroke 0.05; copper clearance ≥ the project rule (default 0.5, fabricator governs, Q-12). Sanitize per §Edge.Cuts Sanitization before routing.
- **Settings**: `.kicad_pro` must define the template netclasses (Default, POWER_DC, POWER_AC at least); rule and severity deviations from the template are WARN and acceptable only when they mirror the fabricator's capability. No `.kicad_dru` unless asked.
- **Footprints / silk**: all on F.Cu unless told otherwise; references hidden unless the project parameters say otherwise (Q-14); mechanicals `exclude_from_bom`; DNP set on both symbol and footprint; 3D model linked.
- **Fab layers** (improvements entries 1, 2): hide the Value field and any `${VALUE}` user text on F.Fab/B.Fab — hide, never delete; KiCad's BOM and "Update PCB from Schematic" both read the Value field. Move the Fab reference text (usually a `${REFERENCE}` user text) to the centre of the Fab outline's bounding box (fallback: courtyard centre, then footprint origin), aligned to the part's long axis, shrunk to fit down to a 0.3 mm floor — never enlarged. A footprint with no Fab reference text gets one added. `scripts/fab_layer_fix.py` does all three.
- **Schematic**: zero global labels (hierarchical labels + sheet pins), `no_connect` on every unused pin (`pin_not_connected` is an ERC error), `PWR_FLAG` on externally driven rails, labels 1.27 mm, `LCSC` populated on purchasable parts.

---

## Complex Power Plane Splits (BGA / FPGA) — PROHIBITION

**Never auto-generate rectangular split planes for interleaved multi-rail components on an inner power layer.** BGAs and FPGAs place several rails' balls in a woven pattern within one footprint. Their pad bounding boxes overlap heavily, so bounding-box partitioning — under any priority ordering — carves copper away from pads that need it and **starves the rails**. A pour that looks correct in the file can leave a core rail with no copper over its own balls.

**Required procedure on an inner power layer:**

1. **Generate the primary global power plane only.** Pick the rail with the widest pad distribution and the highest pad count (typically `+3.3V`) and pour it across the whole board at priority 0.
2. **Leave the interleaved BGA/FPGA rails unpoured.** Do not invent split polygons for them.
3. **Notify the user explicitly**, naming each affected rail and its pad count, and give them the two valid options:
   - **hand-drawn polygons** following the BGA's power-ball groupings — read the ball map from the datasheet or the footprint, never from a bounding box; or
   - **`POWER_DC` track routing** (0.6 mm), the right choice for rails with few, scattered pads.
4. **Prove the prohibition applies** before invoking it. Compute each rail's pad bounding box, apply the candidate priority order, and count how many pads would fall inside a higher-priority rail's zone. Report that orphan count as evidence. A non-zero count forbids the automatic split.

Worked evidence from `a 6-layer FPGA devboard` (2026-09-17): four rails under one FPGA — `+3.3V` (101 pads), `+1.2V` (33), `FPGA_2.5V` (11), `FPGA_1.2V` (6). Smallest-area-highest-priority bbox splits orphaned **68 pads**, including 28 of the 33 `+1.2V` pads. The global `+3.3V` plane was poured; the other three rails were handed back to the user.

This prohibition governs *inner-layer plane partitioning*. Small local pours on outer layers, and a single-rail plane of any shape, remain allowed under the normal zone rules.

**Computing pad centres** (needed for step 4): a pad's absolute position is the footprint origin plus the pad offset rotated by the footprint angle, using KiCad's `RotatePoint` convention —

```
X = fp_x + pad_x·cos(θ) + pad_y·sin(θ)
Y = fp_y − pad_x·sin(θ) + pad_y·cos(θ)
```

Validate the convention on any board that still has routing by checking that computed pad centres coincide with existing track endpoints.

---

## Reference board status

Under 1.2.0 the geometry reference audits **FAIL 488**: 74 arcs (now forbidden), 410 vias without unused-layer removal (now FAIL), 3 off-lattice SD-bus segments, 1 via near-miss. Its single netclass and hand-set widths yield 316 width WARNs. Treat it as the model for geometry (lattice, snapping, planes, zones, schematic discipline), not for settings.

## Reference files (load only the one you need)

- `references/07_review_decisions.md` — the 15 review answers and how each is implemented; adopted netclass table; open conflicts.
- `references/05_decision_rules.md` — **read before routing**: netclass assignment, diff-pair identification, layer/via policy, per-project parameters, zone priority order, order of work.
- `references/06_worked_examples.md` — golden before/after s-expression snippets.
- `references/01_settings_and_rules.md` — exact severities, rules, netclass template, defaults, BOM preset, plot params, absent `.kicad_dru`.
- `references/02_routing_geometry.md` — stackup, widths, via discipline, pad-entry rules, zones, footprints, silkscreen.
- `references/03_schematic.md` — hierarchy, no_connect, labels, fields, libraries.
- `references/04_verification_and_checklist.md` — manual verification procedure (automated by the audit) and checklist.
- `references/99_appendix_minor_details.md` — censuses and inventories; rarely needed.
- `references/08_routing_playbook.md` — **read before routing a real board**: the phased procedure (intake, placement review, hand-laid critical copper, autorouting, repair, verification, release), governing rules G1–G16, the start questions (§4.2), tool status (§15: tools marked "Do not use"), checker limitations (§19). Draft 1.1 from the BladeOne 0.1 trial; where it is stricter than this file, follow it. Its Appendix A tools (`trial_tools\`) are not shipped.
- `references/09_trial_learnings.md` — the evidence behind the playbook: runs 1 and 2 of BladeOne 0.1, decisions, tool defects. Load the section the playbook cites (`L-12.4` = Section 12.4).
- `references/10_datasheet_layout_review.md` — **read after routing**: finding the datasheet layout sections, turning them into `layout_measure.py` checks, the fixes that work and the ones that need re-placement, tool gotchas (ServiceOne, 2026-10-05).
- `references/11_board_review_lessons.md` — **read before routing and before release**: the 26 rules from the ServiceOne rev. 0.2 board review (Vladimir Duk) and where each is enforced (audit check, script, playbook step, or stage 2 tool).
- `references/00_full_standard.md` — archival copy of the original rev A rulebook (pre-review; superseded where 07 says so).
- `golden_settings.json` — settings template consumed by `apply_settings.js` and compared by the audit.
- `templates/kicad_golden.project.json` — per-project parameter file with the reference board values as an example.
- `tests/run_tests.js` — synthetic good/bad boards; run after any change to the scripts or the rules they encode.
