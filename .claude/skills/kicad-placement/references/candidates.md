# Placement candidates (`scripts/candidates/`)

A second, independent way to get a placement: instead of a plan the agent writes, a simulated-annealing engine
generates many complete placements from the netlist and the constraints drawn on the board, scores each one the
same way as the board's current placement, and shows them side by side for the engineer to choose. It needs no
plan. Use it to get starting points quickly, or to challenge a plan-based placement; the checks of Phase 3 still
apply to whatever is chosen.

All scripts run with KiCad's Python. The source board is never modified: results go to an output folder.

## What the engine reads from the board

| On the board | Meaning |
|---|---|
| Locked footprints | Fixed. Never moved. A locked through-hole part only blocks the other side at its pins |
| `Edge.Cuts` outline, rule areas that forbid footprints | Forbidden ground. The outline is inset by the board's copper-to-edge rule |
| Rule area with the **Placement** tab enabled (sheet, group or component class), drawn **on** the board | Hard region: its members must be inside |
| The same, with a name that starts with `ISO_` | Exclusive hard region: its members inside, everything else outside |
| The same, drawn **outside** the outline | Grouping only: the members are kept together, anywhere |
| Schematic connectivity | Clusters: a part with 4 or more connected pads is a hub; passives on its small signal nets join it; a cluster with a locked member is anchored there |
| `kicad_golden.project.json` beside the board, `layout_checks.decoupling` | Pin pairs with a maximum distance (the placer uses the smaller of the entry's `max_mm` and `--decoupling-mm`, 3.5 mm by default) |

Drawing a region in KiCad 10: Place → Draw Rule Area (`Ctrl+Shift+K`), give it a name, clear every keep-out
option, and on the **Placement** tab choose the sheet, the group or the component class.

## Commands

```
<kicad-python> scripts/candidates/run_placement.py BOARD.kicad_pcb --out OUT --check
<kicad-python> scripts/candidates/run_placement.py BOARD.kicad_pcb --out OUT -n 12 --apply 3
```

`--check` only reads the board and prints the regions (members, free area, occupancy, parts outside); run it first.
The second command takes 3-5 minutes for ~330 parts and writes `OUT/gallery.html` (open it), `OUT/summary.json`,
`OUT/candidates/cand_XX.json` and the best candidates as board copies in `OUT/boards/cand_XX/` (bare: old tracks
removed, zones unfilled, project files copied beside them).

| Option | Use |
|---|---|
| `--margin MM` | Gap kept between courtyards. Default `auto`: the lower quartile of the nearest-neighbour gaps of the source placement (0.15 to 0.6 mm). **On a board that has no placement yet, give the value**: a pile of parts has no gap to measure |
| `--profiles a,b` | What to favour: `balanced`, `wirelength`, `blocks`, `decoupling` (candidates cycle through them) |
| `--cluster X` | Scale of the schematic-cluster pull (1.0 default, 0 turns it off) |
| `--freeze REFS`, `--freeze-nets NETS` | Keep these parts, or every part on these nets, where they are |
| `--keep-tight MM` | Keep pin pairs of 2-3 pin signal nets that the source placement holds within MM (only with an existing placement) |
| `--repair CAND.json` | Start every job from one candidate (after adding constraints) instead of from scratch |
| `--decoupling-mm MM`, `--no-layout-checks` | Limit for, or ignore, the project's decoupling entries |
| `--refine N` | Extra candidates that start from the current placement (weak: it rarely leaves the local optimum) |

`apply_placement.py BOARD cand.json OUT_DIR` writes one more candidate as a board copy and proves the rotation
convention by comparing every pad position with the prediction.

## Reading the gallery

The source placement is the reference (index 100, lower is better). The index mixes ratsnest length (40 %),
ratsnest crossings (25 %), peak ratsnest density (15 %) and mean decoupling distance (20 %), plus one point per
percent of plane pads that lost the room for their via. Rows without a weight are gates, not scores: courtyard
overlaps, area outside the board or in a keep-out, parts outside their region, pin pairs beyond their limit,
typical gap between neighbours, parts with a neighbour under 0.3 mm.

**The index is an estimate, not a routing result.** Measured on GapOne CON (2026-11): it ranked the direction
right and the order wrong, and candidates that packed parts tighter than the engineer does looked 24 % better
while being no easier to route. Compare candidates at the spacing the team actually uses, and treat a difference
of a few index points as a tie.

When the source board has no real placement, the index has no meaning (the reference is a pile): compare the
candidates with each other on the individual rows.

## Routed comparison (optional, needs the kicad-routing skill)

```
<kicad-python> scripts/candidates/route_candidates.py OUT --ids "05,02" --baseline --passes 1
```

Routes each candidate copy, and with `--baseline` a bare copy of the source placement, with the kicad-routing
skill's `route_freerouting.py` on equal terms, and collects connections routed, track length, vias and DRC errors
in `OUT/routing.json`. Quote the id list: an unquoted `02,09` is parsed as numbers by PowerShell.

- Placement-only rule areas are removed from the routing copies first: KiCad's Specctra export writes **every**
  rule area as a full keep-out, so a placement region blocks the router.
- One board at a time (`--parallel 1`, the default): four Freerouting instances exhausted 32 GB of RAM.
- `--passes 1`: on this class of board the first pass is the best; later passes got worse and did not converge
  in 30 minutes.
- The routed copies are for comparison only: no stitching, repair or audit is done.

## Limits (state them in the report)

- No row alignment, no change of side, rotations in 90° steps only.
- A candidate can leave pin pairs beyond their limit and, rarely, an overlap inherited from frozen or locked
  parts; the gallery counts both. `--repair` with `--keep-tight` / `--freeze-nets` fixes most of them, and moves
  many parts while doing it: have the engineer look again.
- Developed and measured on one board (6 layers, 326 footprints, one side). At equal spacing its candidates tied
  with the manual placement; they did not beat it.
- Automatic routing completion did not depend on the placement in that test (86-88 % of connections in one
  Freerouting pass for the manual placement and for every candidate, at 0.18 mm and at 0.53 mm gaps). Do not
  promise that a better index gives a routable board.
