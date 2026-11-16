# Installing the kicad-routing skill

A Claude Code skill that applies the AQTech "golden" KiCad PCB standard: an executable audit,
a settings template enforced against real fabricator limits, an automated Freerouting round-trip,
and a rulebook.

## Requirements

| | Needed for | If missing |
|---|---|---|
| **Claude Code** | loading the skill | — |
| **Node.js 18+** | `kicad_audit.js`, `apply_settings.js`, `settings_report.js` | the audit cannot run |
| **KiCad 9 or 10** | `kicad-cli` (DRC, plots) and **KiCad's own Python** for everything importing `pcbnew` | no routing, no DRC |
| **Freerouting 2.x** | the automated routing round-trip | audit and settings still work |
| **A system Python 3.8+** | `dsn_filter.py`, `stitch_planes.py`, `repair_import.py`, most test suites | those tools cannot run |
| shapely *(optional)* | `rail_zones.py` only | that one script degrades with a message |
| matplotlib, numpy *(Linux)* | `route_finish.py`, `via_relocate.py`, `via_spot.py`, `plane_plan.py`, `export_keepouts.py` | those tools stop with an ImportError. KiCad's Windows and macOS Python bundles them (and shapely); on Linux pcbnew uses the system Python: `apt install python3-matplotlib python3-numpy python3-shapely` |

**Run the doctor first — it reports what this machine can actually do:**

```
python  scripts/doctor.py                          # the system interpreter
"<kicad>/bin/python" scripts/doctor.py             # KiCad's interpreter
```

Run it with **both**. They differ, and the difference matters: `pcbnew` exists only in KiCad's
Python, and `shapely` is frequently installed in one and not the other. The doctor also reports
whether your Freerouting is the native launcher or a `.jar` — the jar needs Java 21+, and on a
machine whose only Java is 8 it will not run at all.

KiCad's Python lives at:

```
Windows   C:\Program Files\KiCad\10.0\bin\python.exe
Linux     /usr/lib/kicad/bin/python   or  /usr/bin/python3  (distro-dependent)
macOS     /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/.../bin/python3
```

## Install

**User-level** (available in every project):

```
Windows      mkdir "%USERPROFILE%\.claude\skills"
             tar -xf kicad-routing-<version>.zip -C "%USERPROFILE%\.claude\skills"

macOS/Linux  mkdir -p ~/.claude/skills
             unzip kicad-routing-<version>.zip -d ~/.claude/skills
```

You should end up with `.../.claude/skills/kicad-routing/SKILL.md`.

**Project-level** (ships with one repository): unzip into `<repo>/.claude/skills/` and commit it.
A project skill takes precedence over the user-level copy.

Start a new Claude Code session. The skill loads when KiCad files or the phrases "golden",
"padrão AQTech" or "check against the standard" come up.

## Verify

All suites in one command (the CI workflow runs exactly this; `--strict` fails any suite that skipped checks because KiCad, kicad-cli, node or PyMuPDF is missing):

```
python tests/run_all.py --strict [--kicad-python <kicad>]   -> 14 of 14 suites OK
```

One at a time:

```
node tests/run_tests.js              -> 131/131 assertions passed
python tests/run_tests_py.py         ->  34/34
python tests/run_tests_boards.py     ->   8/8      (also needs node)
python tests/run_tests_phased.py     ->  11/11
python tests/run_tests_rules.py      ->  16/16
python tests/run_tests_guard.py      ->  45/45
python tests/run_tests_planeplan.py  ->  11 passed
python tests/run_tests_padrow.py     ->  10 passed
python tests/run_tests_datasheet.py  ->  16 passed  (needs PyMuPDF or pypdf)
<kicad> tests/run_tests_kicad.py     ->  22/22     (KiCad's Python; node + kicad-cli for two of them)
<kicad> tests/run_tests_axial.py     ->  14 passed
<kicad> tests/run_tests_fanout.py    ->   9 passed
<kicad> tests/run_tests_models.py    ->  13 passed
<kicad> tests/run_tests_gate_tools.py -> 26/26     (KiCad's Python; kicad-cli for two of them)
```

All fourteen should pass on a fresh install (366 assertions in 1.28.0). On Windows, run Node from a short working directory —
a long OneDrive path as the *current* directory makes Node refuse to start. Paths passed as
arguments may be long.

## First use on a new board

```
python  scripts/doctor.py
<kicad> scripts/init_project.py BOARD.kicad_pcb --fab jlcpcb --layers 4 --copper 1oz
node    scripts/apply_settings.js BOARD.kicad_pro --fab jlcpcb --layers 4 --copper 1oz
<kicad> scripts/netclass_propose.py BOARD.kicad_pcb --apply
<kicad> scripts/route_report.py BOARD.kicad_pcb
```

The templates deliberately ship **no netclass patterns and no length groups**. A rule copied from
another design matches nothing on yours, while your own power rails silently stay on `Default` and
route at signal width — nothing fails, the board is simply manufactured with under-sized power
copper. `netclass_propose.py` derives them from your netlist, and the audit FAILs if a
current-carrying rail is left unclassed.

## Regression corpus (recommended)

`tests/corpus/` ships empty. Drop a few of your own boards in, run
`python tests/run_corpus.py tests/corpus --record` once, then re-run it after any change to the
skill. Synthetic fixtures only contain defects their author already imagined — it took a real
board to find the footprint-internal keepout bug that three releases of synthetic tests missed.

## Update

Close Claude Code sessions that use the skill, delete the old `kicad-routing` folder and unzip the new one in
its place (do not unzip over it: a script removed in a release would stay behind). Per-project files
(`kicad_golden.project.json` next to each board) live outside the skill folder and are preserved. Then run the
doctor and the test suites above. `RELEASE_NOTES.md` in the package lists what changed since 1.20.0.

## What is in the package

```
SKILL.md                      entry point; Section 0 is the mandatory pre-routing gate
MANUAL.md                     user manual; section 0 installs the tools, section 2 is the KiCad prep checklist
CHANGELOG.md                  what changed and, more usefully, why
golden_settings.json          settings template (rules, severities, netclasses)
fabricators/jlcpcb.json       JLCPCB capabilities, 2/4/6 layers x 1oz/2oz
templates/                    per-project parameter file + KiCad UI import source
references/                   the rulebook, split by topic

scripts/  doctor.py             what this machine can do, per interpreter
          init_project.py       seed a per-project parameter file from a real board
          netclass_propose.py   derive netclasses from the netlist
          apply_settings.js     merge settings, enforce fabricator limits
          kicad_audit.js        PASS/FAIL audit, exit 1 on any FAIL
          settings_report.js    configuration report, --diff against the template
          route_report.py       completion metric + routability hazards
          route_freerouting.py  the DSN/SES round-trip
          route_sweep.py        pick the clearance by measurement
          route_finish.py       route the last connections by hand, on the 45° lattice; --exclusive dedicated traces (1.19.0)
          layout_measure.py     datasheet layout checks along the copper: Kelvin, pin-to-capacitor, analog/digital gap (1.19.0)
          rules_writer.py       autorouter costs (via cost, directions) as a .rules file
          stitch_planes.py      the plane vias the router never emits
          stitch_residual.py    plane vias for boxed-in pads, one-bend stubs, true shapes (1.18.0)
          export_keepouts.py    export-copy rule areas: edge band, fiducials, crystal/inductor corridors (1.18.0)
          finish_gated.py       DRC-gated finishing of open connections with route_finish.py (1.18.0)
          center_gaps_safe.py   per-move centring of between-pads FAILs (1.18.0, from the BladeOne trial)
          centre_gated.py       batched, bisected, DRC- and audit-gated centring rounds (1.18.0)
          repair_import.py      post-import via flags and width repair
          rail_zones.py         interleaved-rail inner-layer zones (needs shapely)
          dsn_filter.py         subset a DSN for phased routing
          lock_nets.py          lock a phase's copper and prove it was not moved
          kicad_sexp.py         shared s-expression parser + write verifier
          fab_layer_fix.py      Fab-layer hygiene: hide values, centre/add references (rev P)
          geometry_finish.py    pad-entry, gap-centring, plane-link and spreading repair (rev P)
          board_guard.py        refuses a board write while KiCad holds the board or the .kicad_pro is missing (1.20.0)
          zone_fill_check.py    stale zone fills: find, refill, save (1.20.0)
          plane_plan.py         inner power planes planned before routing: map / apply / check (1.21.0)
          pad_row_keepouts.py   "no vias" rule areas over every IC pad-row band (1.22.0)
          refinish_gated.py     realign pad entries one pad at a time, DRC-gated (1.23.0)
          fanout_regularise.py  first bends of an IC fan-out on one line per side (1.24.0)
          model_builder.py      approximate box 3D models, STEP + VRML (1.25.0)
          mounting_hole_fp.py   mounting-hole footprints with their own keep-out (1.25.0)
          datasheet_layout_scan.py  layout sections of every datasheet, before routing (1.26.0)
          audit_gate.py         new-FAIL gate: a change may add no audit FAIL, whatever the total (1.27.0)
          stop_rule.py          stop a scripted run that does not pay: keep rate, projected time, budget (1.28.0)
          locks.py              locked tracks / vias fingerprint; gated drivers never move one (1.28.0)
          stage_gate.py         snapshot + per-change gate: DRC, new FAILs, layout checks, locks (1.28.0)
          gate_each.py          run a candidate-indexed tool one candidate at a time, each change gated (1.28.0)
          via_relocate.py       plane vias: mask web (slide along the stub) or onto the pad axis (1.28.0)
          open_ends.py          copper ends of every open connection, for routing or a hand-off (1.28.0)
          dangling_classify.py  lead-in vs unused dangling copper, before anything is removed (1.28.0)
          via_spot.py           legal via spots along a line, before a fix is attempted (1.28.0)
          dedupe_copper.py      same-net copper lying inside other copper (1.28.0)
          edit_tracks.py        exact, scoped copper edit from a JSON spec (1.28.0)

tests/    run_all.py            every suite below, each with its interpreter; --strict for CI
          run_tests.js          131 assertions (audit + settings)
          run_tests_py.py       34 (python helpers, stitch geometry, new-FAIL gate)
          run_tests_boards.py    8 (2-layer and 6-layer stackups)
          run_tests_phased.py   11 (DSN subsetting)
          run_tests_rules.py    16 (rules file; quoting guard + router wiring)
          run_tests_kicad.py    22 (pcbnew tools; KiCad's Python)
          run_tests_guard.py    45 (board guard, zone fills)
          run_tests_gate_tools.py 26 (1.28.0 finishing tools; KiCad's Python)
          run_tests_planeplan.py, run_tests_padrow.py, run_tests_axial.py, run_tests_fanout.py,
          run_tests_models.py, run_tests_datasheet.py   one suite per 1.21-1.26 feature
          run_corpus.py         regression-test against your own boards
          corpus/               empty by design; see its README
```

## Provenance and how to read the rulebook

Derived from an internal AQTech fabrication reference and a specialist review. The rulebook
distinguishes **rules** (normative) from **observations** (measurements from one board, shown so
you can judge the rule) — see "How to read this document" in SKILL.md. Do not adopt an observation
as a default for your design; measure your own board with `route_report.py`.
