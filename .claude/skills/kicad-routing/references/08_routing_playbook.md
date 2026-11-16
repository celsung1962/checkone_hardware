> **Shipped with the kicad-routing skill (1.17.0).** Draft 1.1 by Vladimir Duk for the skill maintainer, kept
> as written. Paths to `trial_tools\` and to the trial folder refer to the BladeOne trial machine; those prototype
> tools are not part of the skill. "Entry N" refers to the improvements proposal of 2026-09-25, implemented in
> skill 1.16.0 (see `CHANGELOG.md`). `kicad-golden` is the former name of this skill.

# kicad-golden — Board routing playbook (BladeOne class)

| Field | Value |
|---|---|
| Document | Routing playbook for the kicad-golden standard |
| Version | 1.1 (draft for maintainer review). 1.1 adds the WARN review procedure (Section 11.1, F2a), the text-edit Fab and silkscreen methods (A15a), the silkscreen and rework-limit start questions (Section 4.2), the checker limitations (Section 19) and maintainer items 14–16 |
| Date | 2026-09-29 |
| Board class | 4-layer boards with two signal layers (F.Cu, B.Cu) and two plane layers (In1.Cu GND, In2.Cu power); a switching power stage (charger or regulator) in a fine-pitch QFN; an MCU or module header; crystal and RF sections; single-sided assembly |
| Toolchain | KiCad 10.0.3 (pcbnew Python, kicad-cli), Freerouting 2.4.1, Node.js, kicad-golden **1.16.0-local.2** (local build, not an official release) |
| Fabricator | JLCPCB, 4-layer 1 oz profile |
| Evidence | `kicad-golden-trial-learnings.md` (runs 1 and 2 of BladeOne 0.1, 2026-09-28/29). Section references in this document (for example "L-12.4") point to that file |
| Tools | `…\20260928_BLADEONE_Trial_V1_16\trial_tools\` (Appendix A) |
| Prepared for | Celso Souza, skill maintainer |
| Prepared by | Vladimir Duk, with Claude Code |

## 1. Purpose and scope

This playbook sets out the procedure that produced a DRC-clean, fully connected BladeOne 0.1 board in the
second trial run, together with every rule, check, tool behaviour and error that the two runs exposed. The
first run followed the skill as written. It ended at 307 audit FAILs, with no DRC run and no visual check.
The second run ended at 0 DRC errors, 0 unconnected items and 11 audit FAILs, all recorded deviations.

The playbook complements `SKILL.md`, `MANUAL.md` and the reference files; it does not replace them. Where it
states a stricter or additional requirement, the reason and the evidence are given. It is written to be
folded into the skill by the maintainer. Until then, it is the working procedure for boards of this class.

The playbook covers:
- the preparation of the board;
- the placement review of the power stage;
- hand-laid critical copper;
- phased autorouting;
- repair and geometry refinement;
- verification and release;
- the rework of a zone after routing.

## 2. How to use this playbook

- The phases (Sections 6 to 13) run in order. Each phase ends with an **exit criterion**; the next phase does
  not start until it is met, or until the user has decided otherwise and the decision is recorded.
- The governing rules (Section 3) apply throughout and override convenience.
- **Stop conditions:**
  - any DRC error introduced by a step;
  - a lock-fingerprint mismatch outside a planned rework;
  - a tool result that cannot be explained;
  - a decision that belongs to the user.

  At a stop, the step is reverted to its backup and the question is put to the user.
- Sections 15 to 20 are reference material: tool status, pcbnew and Freerouting behaviour, shell pitfalls,
  checker interpretation and clearance arithmetic.

## 3. Governing rules

| # | Rule | Reason (evidence) |
|---|---|---|
| G1 | **KiCad closed** before any script writes `.kicad_pcb` or `.kicad_pro`; confirm from the process list, not by assumption | KiCad overwrites both files on exit (`MANUAL.md` §2.1; L-8.1 M1) |
| G2 | **Every pcbnew script runs under a timeout** (background job with a wait limit), and stderr stays visible on any script that modifies the board | A modal wxWidgets assert (int32 bounding-box overflow) hangs a headless run indefinitely; hidden stderr concealed a failure (L-12.4) |
| G3 | **Scratch copy first.** Every change is applied to a copy, checked with KiCad DRC (and the audit where relevant), and only then applied to the real board. A step backup of the real board is written before each application | One-shot geometry runs produced shorts that only DRC revealed (L-6.4, L-12.4) |
| G4 | **KiCad DRC is the judge**, not a tool's own clearance model. Automatic geometry changes are gated per change on DRC, and on the audit | `center_gaps_safe.py` passed its own check on 22 moves and still produced 9 shorts in one pass (L-12.4) |
| G5 | **Dump the current copper on both layers** (items with coordinates, net, width, lock flag) before designing any hand route after an autorouter pass | A link designed from pad geometry alone produced 10 shorts; the router had filled the corridor (L-12.4) |
| G6 | **Completion percentage is not status.** No result is reported before DRC, the audit and a render have been checked | Run 1 reported "89.4 %" as status (L-2) |
| G7 | **Every user decision is recorded as it is made**, in the decisions table (Section 4), marked "Vladimir's decision, date". Engineering choices of the assistant are marked as such and "open for confirmation" | Traceability for the maintainer |
| G8 | **Ask on doubt.** Placement moves, deviations from the standard, net-class assignments, layer-use exceptions and anything irreversible are put to the user with options and a recommendation | User instruction |
| G9 | **Read the datasheet layout section** of every switching IC before placing or hand-routing its power stage, and check its priority list with Meets / Does not meet verdicts | The U6 zone had to be ripped up and re-placed because this was done late (L-12.1) |
| G10 | **Escape analysis before hand copper and before placement changes** near a fine-pitch part: list every pin, its exit direction and layer, and every net that needs the IC interior | Hand copper walled in two pins; bootstrap vias took the interior hub needed by four nets (L-12.4, L-12.5) |
| G11 | **Lock and fingerprint** every completed phase of copper (`lock_nets.py`), verify after every later step, and account item by item for any planned change | Proves later phases did not disturb earlier copper (L-12.4) |
| G12 | **Tools with known defects are not used** (Section 15) | L-6.4, L-12.4 |
| G13 | **Any change to a skill script is followed by the test suite, a CHANGELOG entry and a version bump** | Untested changes in run 1 (L-3, L-8.2 S16) |
| G14 | **Nothing is hard-deleted.** Superseded files are archived (verified zip) and the originals moved to the Recycle Bin | User instruction; recovery |
| G15 | **The final files are named by full path** in every report | The user opened an older look-alike copy (Section 13) |
| G16 | **Deliverable documents use the formal register** (impersonal voice, scope headings, Meets / Does not meet), including table cells. Chat stays direct | AQTech drafting standard |

## 4. Decisions and records

### 4.1 Records kept during a run

| Record | Content | Location |
|---|---|---|
| Decisions table | Topic, decision, basis ("Vladimir's decision, date" / "Engineering choice, open for confirmation" / "superseded by …") | Learnings file, Section 12 |
| Findings | Tool defects, undocumented behaviour, rule conflicts, errors of the session; each with evidence and a recommendation | Learnings file |
| Resume note | State of the board, remaining steps in order, rules in force, tool index | `RESUME_HERE.md` in the trial folder |
| Lock fingerprints | One JSON per locked phase (`*.lockfp.json`) | Next to the board |
| Placement review | Problems traced to placement, datasheet conformance, options, previews, decisions, outcome | `<zone>_placement_review\` |
| Release note | Package content, verification state, recorded deviations, open items | `gerbers_RELEASE_NOTE.md` next to `gerbers\` |

Errors of the session are recorded, not hidden, in the impersonal form ("In the assessment of … it was stated
that …; that holds for …; it does not hold for …").

### 4.2 Questions put to the user before routing (one interaction where possible)

| Topic | Question | BladeOne answer |
|---|---|---|
| Stackup | Layer count, copper weight, plane assignment | 4 layers; 1 oz outer / 0.5 oz inner; In1 GND, In2 +3.3V |
| Fabricator | Profile; re-check the capability page if web access exists | JLCPCB 4L 1 oz |
| Assembly | Single- or double-sided | Single-sided (drives the bootstrap-capacitor placement) |
| Local clearance overrides | Keep or remove each footprint-local override (`--auto-clearance` would raise the whole board) | U6 override removed |
| Signal-layer pours | Keep or remove GND pours on F.Cu/B.Cu | B.Cu pour removed (`MANUAL.md` §2.9) |
| Power nets | Classification of every net touching a power-stage pin, by current, regardless of its name | HIGH_CURRENT class created (1.0 mm, 0.6/0.3 via) |
| Sense taps of power nets | Width of the tap to a sense pin of a power net | 0.2 mm (VAC1, VAC2) |
| Critical nets | Which nets are routed in phase 1 | +VSYS, +BATT, Net-(SW1-A), 24V_SENSE, GND_LED |
| Crystal / inductor protection | Keepout method (export-time keepouts only) | Export-time keepouts over Y1, Y2, L1–L4 |
| Shared pad gaps | Allowed or not; which parts may carry more than one track per gap | Not allowed, except U2 header and J1 (`allowed_parts`) |
| Plane exceptions | Surface ties of plane-net pads (for example PGND to exposed pad) | U7-3, U7-9, U7-11, U11-2, U11-9 |
| Inner-layer signals | Allowed or not (default: not) | One exception: D9-K on In2.Cu |
| Silkscreen references | Hidden or shown (Q-14); the audit exempts connectors | Hidden, connectors visible (decided after the first release; ask before routing) |
| Silkscreen fonts | Designer labels below the fabricator's line minimum (DRC `text_thickness`, usually TrueType): keep, convert to the stroke font, or enlarge | Converted to the stroke font, 0.15 mm line, character width narrowed to the original length |
| WARN rework limit | How far WARN corrections go: groups to correct, and the stopping rule | One gated pass per approved group, then freeze (decided during the rework; ask before it starts) |
| RF impedance | Controlled impedance or default width (Q-13) | Default 0.2 mm, open for confirmation |
| Via-in-pad, teardrops, detour limits | Project parameters | Defaults |
| Schematic sync | Direction and scope of Update PCB from Schematic | Nets only; footprint replacement and deletion disabled |

## 5. Environment

| Item | Requirement | Note |
|---|---|---|
| KiCad | 10.0.3; use its own Python (`C:\Program Files\KiCad\10.0\bin\python.exe`) for pcbnew scripts | Two interpreters differ; `doctor.py` with both |
| Node.js | Required for `kicad_audit.js`, `apply_settings.js`; start from a short working directory (`%USERPROFILE%`) | Long cwd rejected (L-4) |
| Java / Freerouting | Temurin JRE 21; Freerouting 2.4.1 native launcher (`%LOCALAPPDATA%\freerouting\freerouting.exe`) | No headless mode: a window opens; keyboard input into it must be avoided |
| Python packages | shapely, matplotlib in KiCad's Python user site | Renders (`plot_region.py`, `place_preview.py`) |
| winget | `--source winget` | The msstore source prompts interactively (L-4) |
| PATH | Open a new shell after installers; or call tools by full path | L-4 |
| PDF datasheets | If no PDF renderer is available, extract text with `pdf_text.py` (FlateDecode + ToUnicode) | Used for the BQ25798 layout section |
| Check | `doctor.py` before the first run on a machine | Lessons-learned status is machine-specific (L-4) |

## 6. Phase A — Intake and pre-flight

| # | Check | Method | Pass criterion |
|---|---|---|---|
| A1 | Starting file is the intended delivery | SHA-256 against the archive | Byte-identical |
| A2 | Processes | Process list | No kicad / pcbnew / eeschema / freerouting / java |
| A3 | Documentation read | `MANUAL.md` §2, `SKILL.md`, all `references/` | Read in full before the first step (L-8.6) |
| A4 | Schematic parity | `kicad-cli pcb drc --schematic-parity` (schematics must sit next to the board) | No `net_conflict`. Any conflict blocks routing until the user decides the sync (L-12.1) |
| A5 | Update PCB from Schematic (if decided) | User runs it with footprint replacement and deletion disabled; compare before/after (`diff_boards.py`) | Only the intended pad-net changes |
| A6 | Unique reference designators | Scan footprints | No duplicates. `ExportSpecctraDSN` returns False silently on duplicates such as `G***` (L-5.7) |
| A7 | Net-carrying shapes on copper | Scan `GetDrawings()` on copper layers | None; convert to tracks or remove; DRC `track_dangling` finds stubs (L-5.5, L-12) |
| A8 | Edge.Cuts | Item count, stroke, dimension objects | One outline; no dimensions or text on Edge.Cuts (move to User.1) (L-5.4) |
| A9 | Layer count and stackup | Board Setup by the user (layer count, inner layers typed `power`, stackup 35 / 17.5 µm) | Stackup block matches the layer table. `SetCopperLayerCount()` does not update the stackup (L-5.2) |
| A10 | Fabricator rules | `apply_settings.js --fab jlcpcb --layers 4 --copper 1oz` (dry run first) | Rules = stricter of golden and fabricator; via-drill rule harmonised |
| A11 | Planes | GND on In1.Cu, power on In2.Cu, inset from the outline; no competing pours on signal layers | Immutable 4-layer order |
| A12 | Net classes | Every net in a class; power-stage nets classified by current (A13); `kicad_golden.project.json` seeded (`init_project.py`) and the 1.16.0 keys added by hand if missing (`shared_pad_gaps`, `plane_net_exceptions`, `detour_limits`) | `init_project.py` omits the 1.16.0 keys (L-12.1) |
| A13 | Power-net classification | List every net touching a power-stage pin (inductor, FET drain/source, fuse, battery, charger power pins); the user classifies each | `netclass_propose.py` misses auto-named power nets and misclassifies `*_SENSE` input paths (L-12.1) |
| A14 | Local clearance overrides | List; user decides per override | L-8.1 M4 |
| A15 | Keepouts | Enumerate rule areas; confirm `items_not_allowed` is `error` | L-8.1 M5, L-8.2 S5 |
| A15a | Fab-layer hygiene (entries 1, 2) | `fab_hygiene_text.py <in> <out>` (text edit: values hidden, references centred on the outline box as the audit computes it, long-axis aligned, shrunk to fit, added where missing), then `fab_verify.py <in> <out>` (only the allowed bytes changed), audit and DRC on the copy, then copy over the board. Not `fab_layer_fix.py` (Section 15) | 0 visible Fab values, 0 off-centre references, 0 missing. Run 2 did this after the first release; it changed nothing in the fabricated layers (re-export differed only in dates) |
| A15b | Logos and graphics footprints | `exclude_from_bom` and `exclude_from_pos_files` set | L-8.3 R3 |
| A15c | Library tables | `fp-lib-table` / `sym-lib-table` present; project-local `.pretty` with `${KIPRJMOD}` | Or recorded as a board non-conformity (L-8.3 R2) |
| A16 | Pre-route DRC | `kicad-cli pcb drc --severity-all` | Record the baseline (BladeOne: 77 warnings: U2 header courtyards, library items, text thickness); no errors |
| A17 | Audit baseline | `kicad_audit.js --params kicad_golden.project.json` | Recorded |
| A18 | Pre-flight report | `route_report.py` | Connections, long-haul nets, unstitched plane pads, clearance floor, smallest via annulus (Section 20) |

**Exit criterion:** A1–A18 met or decided; decisions recorded; backup `.bak_original` written.

## 7. Phase B — Placement review

Placement is reviewed before any copper is laid, because most of the hard problems in BladeOne were placement
problems. Allow the time here; it is repaid several times over in the U6-class zones.

### B1. Datasheet layout guidance

For every switching IC (charger, buck/boost, LDO with high current):
1. Read the datasheet "Layout Guidelines" and "Layout Example" sections. Use the manufacturer's current
   revision; a third-party application note is not a substitute.
2. Transcribe the priority list into a table: requirement, current state on the board, verdict.
3. Typical items (BQ25798, SLUSDV2C §8.4.1):
   - input and output 0.1 µF capacitors on the IC layer at the pins;
   - SW nodes to the inductor, with minimum copper area;
   - bootstrap capacitors, which may be joined through vias on both sides; the reference layout puts them on
     the bottom layer;
   - REGN or LDO capacitor close to its pin, with at least 2 GND vias;
   - VBUS 0.1 µF at the pin;
   - BAT capacitors at the BAT pins;
   - via count sufficient for the current;
   - sense traces (BATP, TS) away from the SW nodes.
4. Record the source (document number, section, page) for each requirement.

### B2. Current capacity

- Size every power path from the design notes: charge current, system current, fuse ratings.
- Reference widths: 0.6 mm ≈ 1.6 A (skill table D2); 0.4 mm ≈ 1 A; one 0.6/0.3 via ≈ 1.5–2 A.
- A band that must pass between capacitor pads and IC pins is limited by that gap. If the gap cannot carry
  the current, the placement changes, not the width.
- BladeOne residual design items were: SYS band ≈ 1 A against 3.18 A; +BATT 1.0 mm trunk against the 5 A maximum.

### B3. Escape topology of fine-pitch ICs (mandatory)

For every QFN/QFP/BGA-class part in a power or dense zone:
1. List each pin: net, the direction it must leave in, and the layer.
2. Note corner pins separately: a corner pin has one diagonal exit only (L-12.5, error in R1).
3. Identify the **interior hub**. On a QFN without an exposed pad, the area under the body inside the pin ring
   can host vias. With pad clearance and 0.254 mm hole clearance, a 0.45/0.15 via centre must be at least
   0.33 mm from any pad edge (Section 20).
4. Decide which nets use the hub. On two signal layers the hub serves either the bootstrap/SW via connections
   (datasheet reference practice) or signal escapes (STAT/LED, gate drives, sense lines), not both without
   careful planning.
5. Check planarity per layer. Two connections whose end points interleave around the IC boundary must cross,
   and a crossing needs one of them on the other layer at that point. Resolve every crossing before placement
   is fixed, not during routing.
6. Place indicator LEDs and their resistors where both their nets can reach, checking the anode side (supply)
   as well as the cathode side. The D9 move was studied and failed on the anode side (L-12).

### B4. Critical groups

- **Crystals:** load capacitors adjacent, short nets, hand-routed first (L-7).
- **RF:** matching network chain in order; width decided (Q-13).
- **Inductors and crystals:** no other net under their courtyards on the mounted layer (entry 4).
- **Switch-node pours:** placed so that the SW pins reach the inductor directly.

### B5. Dense channels and centring

- Wherever a track must pass several facing pad or via pairs in succession, space the parts so that the pairs
  share one centre line.
- Centring against every facing pair over-constrains channels whose pairs have centre lines 0.1–0.14 mm apart
  (BATP east of U6, L-12.5).
- Avoid placing a stitching via where it narrows an escape channel.

### B6. Previews and decisions

1. **Preview.** For each candidate, `place_preview.py` renders the zone with the moved parts, the zone copper
   hidden (as after a rip-up), courtyards, courtyard overlaps and airlines. It never writes the board.
2. **Courtyard check.** Use KiCad DRC on the saved copy (`--save`). Merged bounding boxes are unreliable
   (int32 overflow, false overlaps 30 mm away, L-12.1).
3. **Options for the user.** Present them with trade-offs (distance, via count, assembly side, blocked
   escapes) and a recommendation.
4. **Record.** Decisions go in the table; the review document gets its datasheet table, options, preview
   images, decision and outcome.

**Exit criterion:** datasheet table complete; escape analysis shows every pin reachable; current paths sized;
previews accepted; placement applied with DRC showing no courtyard overlap beyond the baseline.

## 8. Phase C — Hand-laid critical copper

| Step | Requirement |
|---|---|
| C1 | Dump pad geometry at nanometre resolution. Use exact pad centres; 0.1 µm rounding made a centre check reject entries (L-12.3) |
| C2 | Lay by explicit geometry with a batch tool (`hand_items.py`, `add_path.py`, `replace_path.py`). Every segment on the 45° lattice, entries axial and ending exactly at pad centres, corner centres ≥ 0.2 mm from pad edges |
| C3 | Switch-node pours: local F.Cu zones between SW pins and the inductor pads, solid pad connection (deliberate deviation from thermal relief; recorded) |
| C4 | Bootstrap loops: per datasheet. With vias under the IC: a pin stub from the inner end of the pin to a via inside the hub, a short parallel B.Cu pair to vias beside the capacitor, a stub into each pad. Width 0.2 mm at the pins, 0.3 mm on B.Cu (open for confirmation). Freerouting cannot make the pin-to-via stub (Section 17) |
| C5 | Power pads with pours: a zone covering the pins and the capacitor pads on the same net, with several 0.6/0.3 vias to a B.Cu copper area joined to the trunk. When a zone outline is redrawn, delete the old zone explicitly; overlapping same-net zones raise `zones_intersect` |
| C6 | Sense taps: 0.2 mm tap from the power trunk to the sense pin through a small via where needed, so that the power trunk never passes through the small via (L-12.4) |
| C7 | Crystal and RF own nets routed by hand at the decided width (L-12.3) |
| C8 | GND pads of decoupling capacitors: **one via per pad** (plane-net rule, entry 7); pads joined by a surface track to a shared via FAIL |
| C9 | Exposed-pad ties (PGND to EP): recorded in `plane_net_exceptions` |
| C10 | Before each item: escape check (G10). After each group: DRC on the copy, audit, region render |
| C11 | Lock and fingerprint the hand copper (`lock_nets.py --nets … --fingerprint handcopper.lockfp.json`) |

**Exit criterion:** DRC with no new violations; audit with no new FAIL, or each one explained; render
inspected; fingerprint written.

## 9. Phase D — Autorouting

### D1. Phase plan

- **Phase 1:** long-haul power nets (smallest set), as `priority_routing.critical_nets`.
- **Phase 2:** the remaining nets, after phase 1 is repaired, audited and locked.
- **Zone phases:** a zone rework (Section 14) routes its own nets in further small phases.

### D2. Export copy

1. Copy the board and `.kicad_pro` to a work folder.
2. Add export-time keepouts over crystal and inductor courtyards on the mounted layer
   (`export_keepouts.py Y1 Y2 L1 L2 L3 L4`). The real board never holds them. Their own nets are already
   hand-routed and locked, so the keepouts do not block them (L-12). `remove_export_keepouts.py` exists
   for the reverse.

### D3. Clearance selection

1. Floor = max(footprint-local overrides, hole_clearance − smallest via annulus). With the 0.45/0.15 via and
   the 0.254 mm hole rule the floor is 0.104 mm, so 0.105 mm is used (L-12.4).
2. `route_sweep.py` over the floor and one or two larger candidates, `--passes 100 --threads 1`.
3. A candidate below the floor produces hole-clearance violations even if it wins on completion.

### D4. DSN preparation

1. Export with `route_freerouting.py <copy> --export-only --clearance 0.105 --outdir <dir>`. The plane nets
   are filtered out automatically.
2. Filter to the phase nets: `dsn_filter.py in.dsn out.dsn --nets A,B,…`.
3. **Check every class block** of the filtered DSN (`dsn_census.py`). A net that is both a power path and a
   sense tap (SOLAR_SENSE) or a bootstrap branch (SW1/SW2) inherits the power class width (1.0 mm) and 0.6/0.3
   vias. The router then fails on the narrow connection. Patch the phase DSN's class width and via for such
   connections, and record it (L-12.5).
4. Rules file: `rules_writer.py <dsn> <rules> --params kicad_golden.project.json` (via cost 50).

### D5. Router invocation

`freerouting.exe -de <dsn> -do <ses> -mp 100 -mt 1 -l en -dr <rules>`, with a timeout.
- **Settings no script can reach** (`MANUAL.md` §2.9b) are put to the user before the first export:
  - vias snapping to SMD pad centres;
  - automatic neckdown;
  - drag components;
  - pad-to-turn gap ≥ 200 µm.

  In run 2 the defaults were kept, and the neckdowns were widened afterwards (E2).
- **After a failed export** with `--auto-clearance`, confirm that the netclass clearances were restored. The
  error path of `route_freerouting.py` exits without the restore (L-5.10).
- `-mt 1` always: multi-threaded optimisation creates clearance violations (L-6.2).
- The router's own violation count (for example 1383 or 1535) reflects the export clearance and fixed copper
  of dropped nets. It is not a DRC result.
- "Wiring.write_wire_scope: net not found" warnings are expected for dropped nets.

### D6. Import procedure (every import, in this order)

| Step | Action | Reason |
|---|---|---|
| 1 | `lock_guard.py <board> lock unlocked.json` | The import deletes every unlocked track and via of the board (1048 → 438 tracks, L-12.5) |
| 2 | `route_freerouting.py <board> --import-only <ses>` | |
| 3 | `lock_guard.py <board> unlock unlocked.json` | Restores the exact previous lock state |
| 4 | `dedupe_import.py <before> <board> --apply` | The session echoes fixed copper: 95 co-located via pairs, 314 duplicates (L-12.5). Check for residual co-located holes after it (1 µm grid) |
| 5 | `restore_placement.py <before> <board> --apply` | The import shifts footprints by up to 50 nm (L-12.4) |
| 6 | `snap_residual_ends.py <board> --apply` | Router ends left up to 100 nm off pad centres |
| 7 | Fix via drills | Imported vias may carry the class drill instead of the padstack drill (0.45/0.30 seen); set them to the intended size |
| 8 | Remove zero-length segments | The router leaves some |
| 9 | Refill zones | Stale fills produce false clearance errors in DRC |
| 10 | `lock_nets.py --verify` against every fingerprint | Any loss must be explained item by item |
| 11 | KiCad DRC and audit | Exit gate |

### D7. Post-import checks

- **Small vias on power nets.** Check each one for current it was not sized for. The router used the VAC1
  sense via as a transit point of the 24V_SENSE trunk (L-12.4).
- **Partial joins.** A power net may be joined only through a thin piece of copper (0.079 mm at the BAT vias).
- **Unrouted connections.** Diagnose the reason for each before rerunning: enclosure, class width, QFN inner
  entry, or orphan tails of earlier phases. Prune orphan dangling tails of unlocked copper (`prune_dangling.py`)
  so that the router can re-route whole nets.

**Exit criterion:** DRC no new errors; all phase nets connected or diagnosed; fingerprints verified; phase
locked and fingerprinted.

## 10. Phase E — Repair and geometry refinement

Order of steps, each gated on DRC on a copy and followed by the audit:

| Step | Action | Tool / method |
|---|---|---|
| E1 | Via flags (`remove_unused_layers`, `keep_end_layers`) on every via | `repair_import.py`, or set in the hand-copper tool |
| E2 | Neckdowns: widen every unlocked segment narrower than its class width where copper and hole clearance allow | `widen_neckdowns.py`. Where not possible, re-route the segment at full width through free space (U1-DVI moved 0.22 mm, L-12.5) |
| E3 | Pad-entry necks (entry 5): neck to the pad's smallest dimension inside its clearance area. An excess ≤ 1 µm only sets the width; never create a piece shorter than 0.3 mm | `neck_residual.py`; a scoped neck function for locked stubs. Not `geometry_finish.py --neck-pad-entries` (Section 15) |
| E4 | Exact pad-centre ends (entry 8); sub-micron breaks between segments snapped | Hand snap; a 0.1 µm break blocks the centring tool (L-12.5) |
| E5 | Plane stitching | `stitch_planes.py` (hole-clearance aware, idempotent; `--wide-search`), then `stitch_residual.py` for boxed-in pads (one-bend stubs), then EP ties as decided |
| E6 | Automatic centring rounds | `centre_drc_gated.ps1` + `center_gaps_safe.py` (Section 10.1) |
| E7 | Hand fixes of the remaining cases | `fix_cases.py`-style scripts, one case per run, gated (Section 10.2) |
| E8 | Residuals | Recorded as deviations with a reason each, by user decision (Section 10.3) |

### 10.1 Automatic centring

1. **Input.** The audit JSON of the current board. The gap definition is the audit's by construction.
2. **Moves available:**
   - slide: shift sideways by (c1 − c2)/2, the neighbours sliding along their own lines;
   - 45° jog at a fixed pad or via end;
   - local detour across the facing window only.
3. **Locked copper** is never moved, except the nets named in `--allow-locked-nets`, which is used for
   hand-laid copper being corrected on purpose. Re-fingerprint afterwards and account for every changed
   item.
4. **Gate per move**, applied alone on a work copy. The move is kept only if:
   - KiCad DRC is not worse;
   - the audit's shared-gap count does not rise;
   - the audit FAIL total falls;
   - **the audit has no new FAIL** (1.27.0, `audit_gate.py`; a falling total alone hid 220 new FAILs at ServiceOne
     D133 — Addendum C).
   
   `-relax` accepts an equal FAIL total and is used only for the even-spacing relaxation in allowed shared
   gaps.
5. **Rounds.** Re-audit and run again until nothing is kept. Indices change between rounds, so an exclusion
   (`-exclude`) must be given again each round. A move repeatedly rejected by the gate is left for E7.

### 10.2 Hand fixes

- **Typical fixes:**
  - put the track on the pad's own centre line when that is also the gap centre;
  - replace a jogged chain with a straight run on the centre line;
  - move a via out of a facing window;
  - reach a centre line with a 45° step outside the facing window.
- **Method:**
  - match every replaced item by its exact end points, and abort the case if one is missing;
  - snapshot `GetTracks()` before any `Remove()` (Section 16);
  - gate each case on DRC and on `audit_gate.py` against the board before the case (no new FAIL), never on the
    FAIL count alone.

### 10.3 Residuals

A residual is kept only when a fix would require re-routing a dense channel, moving parts, or trading one
FAIL for another. Each is recorded with net, location, reason and verdict "Does not meet (recorded)", by user
decision.

**Exit criterion:** DRC 0 errors, 0 unconnected; audit FAILs fixed or recorded; lock verified.

## 11. Phase F — Verification

| # | Check | Pass criterion |
|---|---|---|
| F1 | `kicad-cli pcb drc --severity-all --schematic-parity` (also with `--refill-zones` once) | 0 errors, 0 unconnected, warnings equal to the baseline, parity only the known items |
| F2 | `kicad_audit.js --params kicad_golden.project.json` with the schematics present | Every FAIL fixed or a recorded deviation; **every WARN read and either fixed or accepted with a reason** (Workflow step 3), by the procedure of Section 11.1. Run 2 did it after the first release: 550 → 293 WARNs, each with a disposition (`WARN_REVIEW_RECORD.md`) |
| F2a | `acute_scan.py <board> [<baseline>]`, `overlaps.py <board>` | 0 acute joints (turns sharper than 90°), no duplicate or overlapping same-net segments, no new segments below 10 µm. Since 1.27.0 the audit checks acute joints itself (section 32, also at T junctions); `overlaps.py` and the 10 µm check remain extra |
| F2b | `audit_gate.py <board before the work> <board>` (1.27.0) | 0 new FAILs. Run it for every stage of a rework on a board that already carries FAILs; the total is not the measure |
| F3 | Lock verification against every fingerprint | 0 moved, or every change explained |
| F4 | Region renders of every hand-laid or reworked zone, all copper layers | Inspected before reporting |
| F5 | Visual review by the user in KiCad (open, inspect, close without saving) | Done, or explicitly deferred by the user and recorded |
| F6 | Design-review items (current capacity, open confirmations) listed | In the release note |

### 11.1 WARN review procedure

1. **Classify before deciding.** `warn_classify.py <board> <audit.json> <out.json>` tests the preferred
   alternative of every WARN against all other-net copper: widening to the class or pad width; a free axial stub
   for non-axial entries; a corner move or joint slide for short entries; the real lateral room of spreading
   segments. `detour_estimate.py` gives each under-part track the detour length against `detour_limits`. Render
   the doubtful cases (`plot_detours.py`, `plot_cmp.py`).
2. **Dispositions that need no correction** (BladeOne):
   - width: entry-5 necks and their width steps (required geometry); sense taps of power nets; widths the
     clearance does not allow;
   - pad-entry: non-axial entries with both axial exits blocked; checker rounding artefacts (Section 19);
   - route-around: header parts whose gaps the user allowed; a part's own pin; detours beyond the limits;
   - spreading: checker artefacts (pads as circles, free side occupied);
   - schematic-side WARNs (designer's scope); allowed shared gaps.
3. **Put the correctable groups to the user** in one interaction, with counts, the effort and a stopping rule.
4. **Order of the rework:** non-copper first (Fab, silkscreen, by verified text edits); then the mechanical set
   (widening, pours, chamfers, duplicates); pad-entry shapes; local reroutes (detours, necks, spreading); axial
   entries; acute joints; a final clean-up of what the rework itself introduced.
5. **Gate every stage** (`stage.ps1` → `gate.py`): each change has a key; a stage is kept only when DRC gains no
   error, warning or unconnected item and the audit gains no FAIL. Exclude the changes behind new findings and
   re-run the stage from the same input. "New" WARNs are mostly the old ones re-keyed after a split or a move.
6. **Rules learned:**
   - one Python wrapper per item: take items from the index and compare by UUID (a fresh `GetTracks()` list
     matched every segment with itself and removed 960 segments on a copy);
   - shortest-path reroutes hug obstacles and create off-centre gaps: keep the gate; give the router the incoming
     and outgoing directions (no acute joins) and penalise 90° turns (mitre ratio);
   - do not widen the escape stubs of fine-pitch pins (pads narrower than 0.5 mm);
   - spreading: centre only in corridors bounded on both sides; 0.3 mm where one side is open;
   - a pad with two non-axial entries gets one shared axial stub, not two;
   - 1.23.0: `route_finish.py --refinish REF.PAD` does the single-entry case (cut back >= 1.5 mm, re-route with an
     axial stub); run it one pad at a time and keep the result only when DRC does not get worse;
   - after a font conversion, narrow the characters to the original length and check contacts with other
     silkscreen (`label_overlap.py`);
   - after every stage run `acute_scan.py` and `overlaps.py` (F2a).
7. **Stopping rule:** one gated pass per approved group, then freeze; afterwards only defects introduced by the
   rework are corrected (Vladimir's decision, 2026-09-29). The WARN count is not a convergence measure.
8. **Record and release:** `make_review_record.py` (every remaining WARN with its disposition), `lock_report.py`
   (every changed locked item traced to a change; new fingerprint without a pcbnew save), release note, archive of
   the superseded package, re-export G-1 to G-7 and the layer-by-layer comparison with the previous package.

## 12. Phase G — Release

| Step | Action | Note |
|---|---|---|
| G-0 | The board title block carries the revision and date of the schematic (set when the revision started; kicad-schematic `check_revision.py hardware/ --rev X`). The audit WARNs `revision` on a mismatch | A Gerber set that prints the previous revision is the wrong document (ServiceOne rev. 0.2, 2026-10-21) |
| G-1 | `apply_settings.js <pro> --fab jlcpcb --layers 4 --copper 1oz` (dry run first) **as the last writer of `.kicad_pro`** | Every pcbnew save rewrites `.kicad_pro` from its cache (`corner_style` 2 → 1) (L-5.9) |
| G-2 | Re-add project via sizes that `apply_settings.js` removed (for example 0.45/0.15) by a text edit of the `.kicad_pro`, not by a pcbnew save | It replaces `via_dimensions` whole-object; 6 via FAILs reappeared (L-12.5) |
| G-3 | Re-run DRC and the audit | Unchanged state confirmed |
| G-4 | Enumerate drawing layers (`GetDrawings()` per layer); add populated user layers carrying fabrication content (User.1), leave footprint-internal Cmts/Dwgs out; confirm Edge.Cuts holds only the outline | `SKILL.md` Manufacturing Outputs |
| G-5 | `kicad-cli pcb export gerbers --output <board dir>/gerbers/ --check-zones --layers "F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts,User.1" <board>` | X2 is the default; there is no `--use-gerber-x2` flag. Output path with a forward slash (Section 18) |
| G-6 | `kicad-cli pcb export drill --output <dir>/gerbers/ --format excellon --excellon-separate-th --generate-map --map-format gerberx2 <board>` | PTH/NPTH separate |
| G-7 | Verify: file count, first line of every Gerber starts with `%TF.GenerationSoftware`, FileFunction per layer, inner-layer content where expected, board/project hashes unchanged by the export | Do not trust the exit code alone |
| G-8 | Release note next to (not inside) `gerbers\` | Content, verification state, deviations, open items |
| G-9 | Gate | No export while the audit FAILs, unless every FAIL is a recorded deviation and the user has decided to release; the override is recorded |

After any later pcbnew save: G-1 to G-7 again.

## 13. Phase H — Close-out and file hygiene

**End of each working day:**
- nothing running (process list);
- the real board saved with an end-of-day snapshot (`.bak_end_of_day_<date>`);
- `RESUME_HERE.md` updated with the state, the pending decision and the remaining steps in order;
- the tools copied from the session scratchpad to `trial_tools\`;
- the learnings file and the memory updated.

At the end of the work:

1. Update the learnings file (findings, decisions, results), `RESUME_HERE.md` and the tool copy
   (`trial_tools\`).
2. Keep next to the board:
   - the final `.kicad_pcb`, `.kicad_pro` and `kicad_golden.project.json`;
   - the current fingerprint;
   - `gerbers\` and the release note;
   - one or two milestone backups.
3. Pack step backups and working folders into one archive (for example `run2_working_files.zip`) and verify
   it entry by entry: size against source, and a full readback of each entry. Then move the originals to
   the Recycle Bin.
4. Do not touch folders of earlier runs without the user's decision.
5. State the full path of the final files. Look-alike copies to warn about: earlier run folders, test
   copies, KiCad's `.history\`.

## 14. Zone rework procedure (as applied to U6)

Used when a zone's routing problems trace to its placement.

1. **Stop patching.** Prepare a placement review with the problems, their cause, datasheet conformance and
   options (Section 7).
2. **Decisions and previews,** as in B6.
3. **Rip-up on a copy** (`u6_ripup.py`):
   - apply the moves;
   - remove every item of the zone's nets lying entirely inside the rip box, locked or not;
   - remove any item that now touches a moved pad.

   Keep power trunks that still fit (`keep_nets`), pin-to-pour stubs (`keep_segments`) and zones. Items partly
   outside the box are the ends to reconnect.
4. **Prune** dangling leftovers of the zone nets (`prune_dangling.py`, centreline contact as KiCad's own test).
5. **Dump** the remaining copper on both layers (G5).
6. **Hand-lay** the zone's critical copper (Phase C), including the under-IC via stubs.
7. **Route the zone** with Freerouting:
   - the bootstrap/SW vias and pin stubs are fixed anchors;
   - their B.Cu runs are removed, so the router solves loops and signals together;
   - the DSN classes are patched (D4).

   This succeeded where routing the signals around fixed hand loops failed.
8. **Import** by the full procedure (D6), then local fixes, gated.
9. **Verify** that every lost fingerprint item lies inside the rip box, with the same key function as
   `lock_nets.py`. Then re-fingerprint.

## 15. Tool status

| Tool | Status | Reason / replacement |
|---|---|---|
| `geometry_finish.py --center-gaps` | **Do not use** | Moves locked copper, no collision check, old gap definition; 6 shorts on a copy. Replaced by `center_gaps_safe.py` + `centre_drc_gated.ps1` |
| `geometry_finish.py --neck-pad-entries` | **Do not use** | Staircases on fine-pitch pins; misses 0.2002/0.601 mm widths. Replaced by `neck_residual.py` |
| `geometry_finish.py --crystal-inductor-keepouts` | **Do not use** | Hangs headless on the BOX2I overflow assert. Replaced by `export_keepouts.py` |
| `geometry_finish.py --all` | **Do not use** | Created 88 zero-length segments in run 1 |
| `route_finish.py` near zones | **Do not use** | Ignores other-net zone fills and `--layer`; would have shorted SYS to SW2 |
| `stitch_planes.py` | Use (local fix) | Hole clearance and idempotency fixed in 1.16.0-local.1. It does not read rule areas: never run it while keepouts exist on the board (run 1 placed vias inside three keepouts) |
| `route_freerouting.py --import-only` | Use only inside the D6 procedure | Wipes unlocked copper; duplicates fixed copper; shifts footprints |
| `apply_settings.js` | Use last; re-add project via sizes | Replaces `via_dimensions` |
| `netclass_propose.py` | Use as a hint only | Misses auto-named power nets; `_SENSE` heuristic |
| `init_project.py` | Use, then add the 1.16.0 keys | Omits `shared_pad_gaps`, `plane_net_exceptions`, `detour_limits` |
| `fab_layer_fix.py` | **Do not use** | `BOX2I.Merge()` overflow (run 1); aligns to the footprint orientation, not the long axis; its pcbnew save rewrites the `.kicad_pro`. Replaced by `fab_hygiene_text.py` + `fab_verify.py` |
| `mini_router.py`, `s2_mech.py` … `s7_cleanup.py` | Use through `stage.ps1` and `gate.py` only | Local reroutes and corrections; every result passes the exact collision test, then the stage gate |
| `route_freerouting.py --auto-clearance` | Use; check afterwards | A failed export leaves the netclass clearances raised |

## 16. Technical reference: KiCad 10.0.3 and pcbnew Python

| Behaviour | Handling |
|---|---|
| `GetTracks()` fails when called again after `Remove()` | Snapshot the list first; mark removed items |
| `GetStart()` / `GetEnd()` / `GetPosition()` return live references | Copy (`VECTOR2I(p.x, p.y)`) before modifying the item; a split that kept them disconnected D9-K and TS on a copy |
| `PCB_TRACK.GetPosition()` is its start point | Judge proximity by bounding box |
| Via `GetWidth()` without a layer asserts | `GetWidth(pcbnew.F_Cu)` |
| `SHAPE_CIRCLE.Collide` accepts only a SEG | Use a zero-length `SHAPE_SEGMENT(c, c, d)` for a hole |
| Netclass object is opaque from Python | Resolve class widths by name from `.kicad_pro` |
| int32 overflow in bounding boxes (`BOX2I.Merge()`, courtyards, Fab text) | Never merge footprint geometry; sanity-gate every box (> 500 mm or > 100 mm off origin); exit code 5 can follow a completed script |
| `LoadBoard()` needs a `.kicad_pcb` extension | Copy a `.bak_*` to a `.kicad_pcb` name before loading |
| Saving the board rewrites `.kicad_pro` from the cache | `apply_settings.js` last (G-1) |
| Zone fill is not refilled by a script edit | Refill (`ZONE_FILLER`) after adding vias or tracks; stale fills give false DRC clearance items |
| `kicad-cli pcb drc` does not refill by default | `--refill-zones` when in doubt |
| `--schematic-parity` needs the `.kicad_sch` files next to the board | Run parity in the project folder, not in a work copy |
| `SetCopperLayerCount()` does not update the stackup; the stackup is not editable from Python | Layer conversion by the user in Board Setup |
| CRLF line endings in the board file | Preserve them in text edits |
| API names | `GetFields()` (not `Fields()`); `GetShownText(True)`; `SetDoNotAllowZoneFills`; dimensions are `PCB_DIM_ORTHOGONAL` in `GetDrawings()` |
| "Adding duplicate image handler", SWIG "memory leak" messages | Harmless |

## 17. Technical reference: Freerouting 2.4.1

| Behaviour | Handling |
|---|---|
| No headless mode | A window opens; do not type into it; run with a timeout; check for lingering processes |
| Honours copper clearance, not hole clearance | Clearance floor (D3); check hole-clearance DRC after every import |
| Never enters a QFN pad from inside the body | Hand-lay pin-to-via stubs; the router connects the vias |
| Treats fixed copper of dropped nets as obstacles | Works; keep the fingerprint gate (L-12.4) |
| Uses fixed small vias as transit points | D7 check |
| Fills congested corridors completely | G5 |
| Class width from the DSN applies to every connection of the net | D4 step 3 |
| Stops after about 18 passes without improvement since pass 8 | Normal; an unrouted count unchanged over passes signals a topological block, not too few passes |
| Exits within seconds with only its version line | Retry once; check for another instance |
| Session import behaviour | D6 |

## 18. Technical reference: Windows PowerShell 5.1

| Pitfall | Handling |
|---|---|
| A path ending in `\"` passed to a native program escapes the quote (`kicad-cli` then splits the argument and writes nothing) | Use a forward slash or no trailing separator |
| The comma binds tighter than `+` (`@($a.Count + $u, …)` builds an array) | Parenthesise each element |
| A helper function named `H` resolves to the `Get-History` alias | Use distinctive function names (a hash check once compared two empty results) |
| `Get-Content` without `-Encoding UTF8` on a UTF-8 file, then `Set-Content`, garbles non-ASCII characters | Read and write with explicit UTF-8, or use the file tools |
| `2>&1` on native programs wraps stderr lines as errors | Filter, or let the tool capture stderr |
| `&&`, `||`, `?:` not available | `;` with `if ($?)` |
| A guard may block `Remove-Item` on paths with spaces | Write to a new file name instead of deleting |
| Node tools need a short working directory | Start from `%USERPROFILE%` |

## 19. Checker interpretation (kicad-golden 1.16.0-local.2)

`kicad_audit.js` check 16, as corrected locally with tests (70/70):

- **Own-pad flanks.** Pads abreast of a segment's own terminal pad are not gap candidates. Such a segment is a
  pad exit or entry, governed by entries 8/9.
- **Look-ahead.** The 0.5 mm look-ahead past a segment end applies only at free ends, not at ends in same-net
  pad, zone fill or via.
- **Wording.** "Two-pad part" means two distinct pad numbers.
- **Gap width.** Between different parts, or within a multi-pad part, a gap is at most 1.5 mm of free
  copper-edge width. Under a two-pad part any width counts.
- **Via flanks.** An other-net via is a flank, measured from its binding keep-out: copper + clearance, or
  hole + 0.254 mm, whichever is larger.
- **Facing test.** Two flanks form a gap only if their offset along the track does not exceed the sum of
  their reaches.
- **Allowed shared gaps.** `shared_pad_gaps.allowed_parts` lists parts whose pin gaps may carry more than one
  track. `shared-gap` becomes a WARN there, and each track must be evenly spaced: equal clearance, within
  0.01 mm, to its nearest neighbour (flank or other track, same layer) on each side. A single track reduces to
  ordinary centring.
- **Known limitation.** The per-pair requirement over-constrains dense channels (B5). A per-channel
  definition is recommended to the maintainer.
- **Unchanged.** `between-pads` stays at FAIL severity (Vladimir's decision), and the global
  `shared_pad_gaps.allowed` flag is unchanged.

Limitations found in the WARN review (not corrected in the checker; read the WARNs with them in mind):
- `width` does not exempt the necks entry 5 requires nor their width steps (113 of 191 on BladeOne).
- Non-axial entry: the rounded relative angle can be 180, compared with 0 (false WARNs on entries within
  0.001°).
- `spreading` models pads as circles (negative distances) and ignores tracks, vias and zones on the free side.
- The corner statistic (`angle`) counts pad centres and vias as corners, and a 135° turn as a 45° mitre: acute
  joints are never reported (F2a).
- Messages carry only a segment's start point; two segments from one point give identical messages.
- The netclass INFO about sense taps "left on Default" does not check the resolved class.
- No check for duplicate or overlapping same-net segments or segments below 10 µm (F2a).

## 20. Clearance arithmetic (JLCPCB 4L: copper 0.10 mm rule, hole-to-copper 0.254 mm, hole-to-hole 0.254 mm)

| Quantity | Formula | Values |
|---|---|---|
| Copper clearance needed track-to-via so that the hole rule holds | ≥ hole_clearance − annulus | 0.45/0.15 (annulus 0.15): 0.104 mm; 0.25/0.15 (0.05): 0.204 mm; 0.45/0.20 (0.125): 0.129 mm; 0.6/0.3 (0.15): 0.104 mm |
| Via centre to other-net pad edge | ≥ max(r_via + 0.10, r_drill + 0.254) | 0.45/0.15: 0.33 mm; 0.25/0.15: 0.33 mm; 0.6/0.3: 0.404 mm |
| Via centre to via centre (other nets) | ≥ max(r1 + r2 + 0.10, r_drill1 + r2 + 0.254, r1 + r_drill2 + 0.254) and hole gap ≥ 0.254 | Two 0.45/0.15: 0.55 mm |
| Track centre to via hole | ≥ w/2 + r_drill + 0.254 | 0.2 mm track, 0.15 drill: 0.429 mm |
| Two 0.2 mm tracks in a gap | Free width ≥ 3 × 0.1 + 2 × 0.2 | 0.7 mm |
| Router export clearance | ≥ hole_clearance − smallest annulus of the vias it places | 0.105 mm with 0.45/0.15 |

## 21. Calibration data from BladeOne 0.1

| Stage | DRC errors | Unconnected | Audit FAIL |
|---|---|---|---|
| Run 1, end (skill as written, no DRC) | Not run | 37 | 307 |
| Run 2, after phases 1–2 and repairs (2026-09-28) | 0 | 2 | 47 |
| Run 2, after the U6 zone rework (2026-09-29) | 0 | 0 | 46 |
| After automatic and relaxed centring, allowed shared gaps | 0 | 0 | 19 |
| After hand fixes and U1-DVI (Gerber Issue 1) | 0 | 0 | 11 (all recorded); 550 WARN |
| After the WARN review and rework (Gerber Issue 2) | 0 | 0 | 10 (all recorded); 293 WARN, each with a disposition |

**Gaps of run 2 against this playbook**, recorded so that they are not repeated:
- Fab-layer hygiene (A15a) and the WARN review (F2) were done only after the first release, which caused a second
  fabrication output the same day.
- The silkscreen questions (Q-14, fonts below the fabricator minimum) were asked only at the WARN review.
- The visual review in KiCad (F5) was deferred by the user at release.
- The U6 datasheet section (B1) and escape topology (B3) were done only after the first routing, which caused
  the zone rework.
- Hand-laid copper and the U6 placement also left design items open: U6 PGND (pin 27) reaches the GND plane
  through a single 0.25/0.15 via, and the U7 VIN/VOUT decoupling capacitors are remote from their pins
  (L-12.2). Both belong in the B2 current and loop review.

**Expected effect of this playbook on a new board of the class.** The largest saving is in Phase B:
- datasheet-first placement;
- escape topology before placement;
- current-sized paths;
- channel spacing for centring.

On BladeOne, the zone rework alone took most of a day. Phases D and E become predictable with the import
procedure and the gated tools. Freerouting still does not know the golden geometry rules, so Phase E remains
necessary.

## 22. Open items for the maintainer

The full list of recommendations is in L-10, L-12.1, L-12.4 and L-12.5. The ones this playbook depends on:

1. **Fold this playbook into the skill:**
   - Phase B (datasheet table, escape topology, current sizing, channel spacing);
   - the D6 import procedure;
   - the gated centring;
   - the tool-status table.
2. **Build the import guards into `route_freerouting.py --import-only`:** lock guard, de-duplication,
   placement restore, end snap, via-drill fix and zero-length removal.
3. **Floor `route_sweep.py`** at hole_clearance − smallest annulus; report the annulus in `route_report.py`.
4. **Per-connection widths in phase DSNs** (sense taps, bootstrap branches), or class splitting by connection.
5. **`apply_settings.js`:** merge `via_dimensions` and `track_widths` instead of replacing them.
6. **Centring requirement** defined per channel, not per facing pair.
7. **Review the local checker changes** (1.16.0-local.1 and .2) and the tests; bump the version string.
8. **Net classes:**
   - `netclass_propose.py` should flag every net on a power-stage pin;
   - the standard needs a HIGH_CURRENT class;
   - the audit's "sense taps correctly left on Default" INFO should check the resolved class, not the name.
9. **Pre-flight gate:**
   - unique references;
   - net-carrying shapes;
   - dimensions on Edge.Cuts;
   - schematic parity blocking on `net_conflict`;
   - pins without an escape channel.
10. **Crystal and inductor protection:** export-time keepouts with own nets hand-routed first.
11. **Inner-layer signal policy:** state whether a short signal on a plane layer is ever acceptable, and how it
    is recorded (D9-K precedent).
12. **Power-stage grounds versus entry 7** (PGND to capacitor grounds on the top layer).
13. **Repair tooling:** fix or retire the `geometry_finish.py` flags of Section 15; add backups to
    `fab_layer_fix.py` and `geometry_finish.py`; share the bounding-box sanity gate.
14. **Checker corrections from the WARN review** (Section 19): exempt entry-5 necks and their width steps from
    `width`; normalise the rounded angle of the non-axial check modulo 180; count corners only at free joints and
    report acute joints; model pads by their real shape in `spreading` and include tracks, vias and zones; give
    both end points in messages; report the detour length in `route-around`; add duplicate, overlap and
    sub-10 µm checks.
15. **Fab layers:** replace `fab_layer_fix.py` by the text-edit method (outline box as the audit computes it,
    long-axis alignment as `SKILL.md` states, no pcbnew save).
16. **WARN work as a workflow step:** the classification tools, the gated stages and the stopping rule of
    Section 11.1, and the start questions of Section 4.2 (silkscreen references, fonts, WARN rework limit).

## Appendix A. Tool index (`trial_tools\`)

| Tool | Purpose |
|---|---|
| `place_preview.py` | Placement preview: moves, zone copper hidden, courtyards, overlaps, airlines; optional saved copy for DRC |
| `u6_ripup.py` | Zone rip-up with keep lists; dry run lists every item by net and lock flag |
| `prune_dangling.py` | Iterative removal of tracks with a free end (centreline contact) and of isolated vias |
| `hand_items.py` | Batch hand copper from JSON: tracks, vias (flags set), zones, rotations; lattice check; locked; refill |
| `add_path.py`, `replace_path.py` | Single locked F.Cu runs with end checks against pad centres or zones |
| `astar_in2.py` | 45° lattice path on one layer keeping copper and hole clearance to every via and plated hole |
| `lock_guard.py` | Lock all unlocked copper before an SES import and restore the exact state after it |
| `dedupe_import.py` | Remove import duplicates of pre-existing copper |
| `restore_placement.py`, `snap_residual_ends.py` | Undo import placement shifts; snap router ends to pad centres |
| `export_keepouts.py`, `remove_export_keepouts.py` | Export-time crystal/inductor keepouts |
| `neck_residual.py`, `widen_neckdowns.py` | Pad-entry necks; neckdown removal |
| `stitch_residual.py`, `ep_ties.py`, `tie_u7_pgnd.py` | Stitching of boxed-in plane pads; exposed-pad ties |
| `center_gaps_safe.py`, `centre_drc_gated.ps1` | Centring from the audit JSON (slide, jog, detour, allow-list) with the DRC and audit gate (`-relax`, `-exclude`, `-allowLocked`) |
| `fix_cases.py` | Pattern for gated one-case hand fixes |
| `plot_region.py`, `dump_copper.py`, `dump_at.py`, `dump_nets.py`, `padbb.py` | Renders and geometry dumps |
| `dsn_census.py`, `diff_boards.py`, `lost_in_box.py`, `list_new.py` | DSN inspection; board comparison; fingerprint loss location; new-item listing |
| `pdf_text.py` | Datasheet text extraction without a PDF renderer |
| `u3_fix.py`, `u5_fix.py`, `u6_audit_fix*.py`, `p1b_repairs.py`, `u6_prefix.py`, `sys_link.py`, `vac1_tap.py` | Board-specific repair records (reference only) |
| `fab_hygiene_text.py`, `fab_verify.py` | Fab-layer hygiene as a text edit, and its byte-level check |
| `silk_text.py`, `silk_verify.py`, `label_overlap.py` | Silkscreen references hidden, TrueType labels to the stroke font (character width to the original length), and the contact check |
| `warn_classify.py`, `detour_estimate.py`, `plot_detours.py`, `plot_cmp.py`, `net_branches.py` | WARN evidence: widening, axial stub, corner move / slide, lateral room, detour length; renders; runs of a net by width |
| `rw_lib.py`, `mini_router.py` | Rework library (index that follows every edit, exact collision test incl. hole and edge clearance) and the 45° lattice router (A*, direction constraints, exact end corner) |
| `stage.ps1`, `gate.py`, `s2_mech.py` … `s7_cleanup.py` | Gated rework stages with keyed changes and `--exclude` |
| `acute_scan.py`, `overlaps.py`, `lock_report.py`, `make_review_record.py` | Checks the audit lacks; lock verification with change attribution and new fingerprint; per-WARN record |

## Appendix B. Command reference

```text
DRC            kicad-cli pcb drc --format json --severity-all [--schematic-parity] [--refill-zones] -o drc.json <board>
Audit          node kicad_audit.js <board> --json audit.json --params kicad_golden.project.json [--no-sch] --quiet
Tests          node tests/run_tests.js
Settings       node apply_settings.js <pro> --fab jlcpcb --layers 4 --copper 1oz [--dry-run]
Lock           python lock_nets.py <board> --nets A,B --fingerprint <f.json> [--verify] [--quiet]
Export DSN     python route_freerouting.py <copy> --export-only --clearance 0.105 --outdir <dir>
Filter DSN     python dsn_filter.py <in.dsn> <out.dsn> --nets A,B --quiet
Rules          python rules_writer.py <dsn> <rules> --params kicad_golden.project.json --quiet
Fab hygiene    py fab_hygiene_text.py <in> <out> --log log.json ; py fab_verify.py <in> <out>
WARN evidence  kicad-python warn_classify.py <board> <audit.json> <classify.json> ; kicad-python detour_estimate.py <board> <classify.json> <detour.json>
Rework stage   powershell -File stage.ps1 -script <sN.py> -inBoard <prev board> -stageDir <dir> -prevDir <prev dir> [-extra "<arg>"] [-exclude "k1;k2"]
Extra checks   py acute_scan.py <board> [<baseline>] ; py overlaps.py <board>
Lock report    kicad-python lock_report.py <board> <old.lockfp.json> <new.lockfp.json> <changes.json ...>
Route          freerouting.exe -de <dsn> -do <ses> -mp 100 -mt 1 -l en -dr <rules>
Import         lock_guard lock -> route_freerouting.py <board> --import-only <ses> -> lock_guard unlock -> dedupe -> restore -> snap
Centring       powershell -File centre_drc_gated.ps1 -board <b> -auditJson <a> -work <dir> [-exclude i,j] [-allowLocked "N1,N2"] [-relax]
Gerbers        kicad-cli pcb export gerbers --output <dir>/gerbers/ --check-zones --layers "<list>" <board>
Drill          kicad-cli pcb export drill --output <dir>/gerbers/ --format excellon --excellon-separate-th --generate-map --map-format gerberx2 <board>
```

## Addendum A (kicad-routing 1.18.0, Celso Souza, 2026-10-04) — ServiceOne main board

Added by the maintainer after the second board routed with this playbook (`reports/routing_report.md` of the
ServiceOne repository). Vladimir's text above is unchanged; where this addendum differs, it reflects tools that
now ship in the skill.

| Section | Addition |
|---|---|
| 4.2 Start questions | Add: **switch-node lengths of every converter** (inductor and diode to the IC pins) before routing - the ServiceOne TPS63001 inductor had been placed 15 mm from its pins and was moved (phase B) |
| 6 A12 | `init_project.py` now writes `shared_pad_gaps`, `plane_net_exceptions`, `detour_limits`, `via_in_pad`, `priority_routing`, `router_costs` with empty decision lists: do not copy them from the template or another project (the template carried the reference board's via-in-pad parts) |
| 6 A10 / 12 G-1, G-2 | `apply_settings.js` merges predefined vias and track widths with the project's, never lowers `unconnected_items` below error and keeps the schematic connection grid; re-adding via sizes by hand is no longer needed |
| 9 D2 | `export_keepouts.py --export-copy`: `--corridors auto` (crystal/inductor courtyard minus one entry corridor per pad - works in a single pass, no hand-routing first), `--edge-band <rule + 0.05>` (Freerouting ignores the copper-to-edge rule), `--fiducials` (pad-local clearance is not in the DSN), `--pad-row-bands` (1.22.0: "no vias" over every IC pad-row band, L16; or `pad_row_keepouts.py --write` once on the real board so DRC and the interactive router keep the rule too). pcbnew saves only the first outline of a zone: one zone per ring |
| 9 D3 | Export clearance floor must include **every via already on the board** (thermal vias, footprint vias), not only the class vias: 0.45/0.2 thermal vias (annulus 0.125) raised the floor to 0.129 mm and gave 3 hole-clearance warnings at 0.105 mm |
| 10 E5 | `stitch_planes.py` honours rule areas and reads polygon / circle outlines; `stitch_residual.py` ships in the skill with same-net hole-to-hole, drill-to-track hole clearance and rule areas |
| 10 E6 | `centre_gated.py`: batches with bisection instead of one move per DRC (195 candidates in about ten minutes, ServiceOne 427 -> 225 FAIL in four rounds) |
| 10 E7 | `finish_gated.py`: open connections one at a time with `route_finish.py` under a DRC gate; boxed-in pads are left for KiCad's interactive router |
| 15 Tool status | **Do not use** `geometry_finish.py --pad-centre-entries` on a routed board without a per-change gate (one pass: 48 snaps, 2 shorts, 3 clearance errors). `widen_neckdowns.py` (trial tool) does not read rule areas - gate its result with DRC |

## Addendum B (kicad-routing 1.20.0, Celso Souza, 2026-10-20) — ServiceOne rev. 0.2 board review

Added by the maintainer from Vladimir Duk's review of the routed ServiceOne main board (21 issues;
`references/11_board_review_lessons.md` maps the 26 lessons L1–L26 to their enforcement). Where this addendum
differs from the text above, it governs.

| Section | Addition |
|---|---|
| 4.2 Start questions | Add: **mechanical contact diameters** at every mounting hole and pillar (screw head, nut, washer, standoff hex, enclosure post), written to `mechanical_keepouts` in `kicad_golden.project.json` with radius = largest diameter / 2 + 0.5 mm (L24). Add: **approved rule deviations** (`approved_rule_deviations`) so `apply_settings.js` keeps them (L7). Add: **via drill tier** — economical tier by default, finer vias only with `fabricator.fine_vias_approved` (L8) |
| 6 A5 | After *Update PCB from Schematic*, list renamed `unconnected-` nets (a `_1` suffix on a net shared by two pins makes DRC report a short) (L6) |
| 6 A15d (new) | **3D models**: every footprint has a verified model (position, rotation, height) with a project-relative path. Search the KiCad library, EasyEDA by LCSC code, then the manufacturer; for the rest the designer chooses between finding one and an approximate `*_approx` model built from the datasheet drawing (`model_builder.py`, 1.25.0). The audit FAILs a footprint without a model (L25, L26) |
| 6 A19 (new) | **Mechanical keep-outs** written before routing as rule areas on the copper layers the parts touch, and exported to Freerouting (L24). Best carried by the hole footprints themselves (`mounting_hole_fp.py`, 1.25.0) |
| 7 B0 (new, 1.26.0) | **Datasheet layout suggestions before routing**: `datasheet_layout_scan.py --write-params` over every datasheet of the board; read each layout page and its image; each rule becomes a placement move, a `layout_checks` entry or a routing constraint, recorded per part (`applied` / `n/a`); `layout_measure.py check --pre-route`. The audit FAILs pre-flight and `route_freerouting.py` refuses to export while a part is pending (SKILL.md §Datasheet layout suggestions, reference 10 §0) |
| 7 B7 (new) | **Plane plan**, after placement and before routing: a power map per rail, candidate islands and a trade-off table. The designer decides or draws the outlines, and the decision is stored as `plane_plan`. Rules: never split GND; gap by voltage; boundaries away from adjacent-layer signals; minimum neck width; sense-trace vias stay out of islands (L23). Tool (1.21.0): `plane_plan.py map` -> decide -> record in `plane_plan.islands` -> `plane_plan.py apply` -> `plane_plan.py check` + audit section 30 |
| 7 B3 | Escape design of fine-pitch ICs: no via inside a pad-row band (L16); plane vias use the small via (L13); fan-out as a pattern — axial exits, bends aligned per side, equal spacing (L22; 1.24.0: audit `fan-out` WARN, `fanout_regularise.py --apply`) |
| 8 / 9 Pin arrays | Inside any pin array tracks run on the channel centreline, orthogonal, with 45° corners only at turns; wide power tracks that block a signal channel go on the other layer (L21). One track per THT gap where a neighbouring gap is free (L17) |
| 10 E-finish (new, in this order) | 1. Rebuild every Kelvin sense line touched by the pass with `route_finish.py --exclusive` and run `layout_measure.py check` **before** trimming dead ends — `finish_gated.py` now reverts routes that break a passing layout check, but a hand edit does not (L5). 2. `repair_import.py --declang` only after all nets are connected (with open nets it deletes long chains). 3. Straighten detours and remove same-net duplicates / loops (audit `detour`, `loop`) (L18, L19). 4. KiCad *Cleanup Tracks and Vias* with the L2 settings (designer, in KiCad). 5. Refill and **save** the zones (`zone_fill_check.py --fix`) (L1) |
| 11 Verification | `between-pads` and fine-pitch `pad-entry` findings are fixed, not recorded as deviations (L10, L20). The deviation groups of earlier boards are not carried forward automatically |
| 12 Release | Gate: no open engineering choice (via tier, via covering, stackup) — settle each before export, not on the order page (L8). List `*_approx` models in the release note (L26) |
| Scripts | Every board-writing script calls `board_guard.py`: it refuses when KiCad lock files exist or no `.kicad_pro` sits next to the board (L3, L4). Board-writing scripts refill zones before saving (L1) |

## Addendum C (kicad-routing 1.27.0, Celso Souza, 2026-10-22) — ServiceOne D133 review: rules enforced, not counted

Vladimir Duk's review of the scripted ADC-region rework (D133, branch `rev02-adc-region`): the entries to U1 improved,
but rules that already existed were broken - acute joints, vias in and beside pads, tracks between pads where a route
outside was easy, and open tracks (32 unconnected and 45 dangling stubs left at the hand-off). Measured against the
board before the rework: 220 new FAILs, hidden because every gate in the scripts compared only the board's total FAIL
count, which fell from 1 932 to 1 795 as the rip-up removed 357 old ones. Section 11.1 step 5 already said "the audit
gains no FAIL", and F2a already asked for zero acute joints; the scripted drivers applied neither. Lessons L27-L29 in
`references/11_board_review_lessons.md`. Where this addendum differs from the text above, it governs.

| Section | Addition |
|---|---|
| 3 Governing rules | **A change to a routed board adds no audit FAIL** (L27). Before the change, keep the board (or its audit JSON) as the baseline; after it, `audit_gate.py <baseline> <board>` must exit 0. A falling total never excuses a new FAIL, and "the board already had 1 900 FAILs" is not a reason to accept one more |
| 9 / 10 Scripted routing | `finish_gated.py`, `centre_gated.py` and `refinish_gated.py` gate every kept change on `audit_gate.py` (1.27.0); `finish_gated.py --no-audit-gate` exists for experiments only. A re-placement or rip-up done by any other script is gated by hand, per stage, with `audit_gate.py` |
| 10 Geometry | **No acute joints** (L28): audit section 32 FAILs any meeting of same-net tracks, away from a pad centre or via, where two neighbouring branches are less than 90° apart (T junctions included). `route_finish.py` searches with its arrival direction and refuses to write an acute route (exit 5) |
| Hand-off | **No dangling copper at a hand-off** (L29): DRC `track_dangling` and `via_dangling` are 0 before a board goes to the interactive router, a reviewer or the fabricator. Open connections left for someone else are listed with their ends, and the copper around them is clean |
| 11 F2b (new) | `audit_gate.py <board before the work> <board>`: 0 new FAILs, recorded in the hand-off note with the baseline commit |

## Addendum D (kicad-routing 1.28.0, 2026-10-31) — ServiceOne rev. 0.2: finishing a routed board under the gates

The rev. 0.2 review fixes on ServiceOne (Vladimir Duk with KiCad's interactive router, Claude with gated scripts,
2026-10-22/23) took the board from 1818 to 1455 audit FAILs with 0 unconnected, with no scripted change adding a FAIL.
The lessons are L30-L44 in `references/11_board_review_lessons.md`, section 9. Where this addendum differs from the
text above, it governs.

| Section | Addition |
|---|---|
| 3 Governing rules | **Stop rule** (L30, Vladimir's rule): estimate every scripted run (items x attempts x time per attempt) and show the estimate to the designer when it is over 15 min; after 10 attempts or 30 min, stop when fewer than 1 in 5 is kept or the projected time exceeds the budget (default 1 h), and hand the rest to the interactive router with its ends. Run a sample of about 10 before any board-wide pass |
| 3 Governing rules | **Locks are honoured** (L39, L40): no gated change moves a locked item (`locks.py` fingerprint in every gated driver). Before a hand-off, list the locks (`locks.py BOARD --list`), release tool locks (stitching placed by `stitch_residual.py`) and lock what the hand-off says is critical |
| 9 / 10 Scripted routing | D1. Ends from the copper (L31): `open_ends.py BOARD DRC.json ENDS.json`; route pad ends pad-to-pad, free ends by coordinate. D2. Before a scripted fix places a via, scan the spots (`via_spot.py`, L34); no legal spot = a list item, not a forced move. D3. Dense fine-pitch IC clusters (QFN / QFP fan-out) are routed interactively, never ripped up and rebuilt by script (L43) |
| 10 E-finish | Step 2 amended: on a board with open connections, `dangling_classify.py` (after `open_ends.py`) instead of iterating `repair_import.py --delete track_dangling` (L33). Step 4 amended: KiCad *Cleanup Tracks and Vias* with **"Delete tracks fully inside pads" OFF** (D4, L44), then `audit_gate.py` / `stage_gate.py` against the board before the Cleanup; restore any pad-centre stub it removed |
| 10 Plane vias | Plane-pad vias beside the pad block the axial entry (L38): `via_relocate.py --mode axis` under `gate_each.py`, then `refinish_gated.py`. Vias too close to an SMD pad: `via_relocate.py --mode web` (L15) |
| 10 Gates | Per change: `stage_gate.py SNAP BOARD` (DRC without refill, zone-fill violations ignored; L32), refill check per stage. Normalise the baseline once with `stage_gate.py --snap --normalise` (L42). `--box` / `--exclude-box` keep a board-wide pass out of a region the designer is routing (L37) |
| 10 Geometry | **Orthogonal-first routing** (L41, Vladimir's rule): H / V runs, 45° only for corners and links <= 3 mm (`routing_style`), longer diagonals only for listed nets with a reason; audit section 33 WARNs the rest. Ask the designer for the exceptions in the routing setup questions (§0) |
| 16 Technical reference | D5. Git Bash rewrites an argument that starts with "/" (a hierarchical net name) into a Windows path: run with `MSYS_NO_PATHCONV=1` (L36). D6. EasyEDA 3D models: use the easyeda2kicad .wrl (the STEP is in the raw frame), align to the F.Fab outline, check with `kicad-cli pcb render`; KiCad 10 renamed library models (L35) |
