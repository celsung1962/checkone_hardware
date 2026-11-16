# CheckOne hardware

AQTech Power Prognostics · hardware of the CheckOne product. The repository was created on 2026-11-16 with the
FluxOne_hardware / GapOne_V2 layout and repository policy (kicad-schematic skill 1.6.0, `init_repo.py`). There is no board yet: each
board gets its own folder, named after the board, under `hardware/`, `bom/` and `reports/`, as in GapOne
(`hardware/GapOne_CON/`, `hardware/GapOne_AMP/`).

```
checkone_hardware/
|-- CLAUDE.md                       design brief for Claude Code (skeleton, to fill from the requirements)
|-- OUTSIDE_GIT.md                  what is kept outside git (OneDrive store CheckOne_Hardware) and how it gets there
|-- bitbucket-pipelines.yml         CI for Bitbucket: hardware checks, release build on <board>-v<version> tags, skill updates
|-- hw_checks.json                  config of tools/hw_checks (boards, checks, release); no board yet
|-- .claude/skills/                 kicad-schematic 1.6.0, kicad-placement 1.3.0, kicad-routing 1.29.0 (versioned with the project)
|-- docs/requirements/              specs, architecture, meeting notes, decision_register.md
|-- docs/datasheets/                PDFs + .txt + manifest.csv (fetch_datasheets.py)
|-- reference/reference_project/    reference KiCad project - READ-ONLY, outside git (store)
|-- hardware/<Board>/               KiCad project of each board (.kicad_pro/.kicad_sch/.kicad_pcb), generator scripts in hardware/
|-- calc/                           design calculations and netlist rules (every number comes from here)
|-- bom/<Board>/                    parts.csv (catalog data), jlc_summary.md, bom_summary.md
|-- DOC/                            deliverables (generated, outside git); DOC/source/ holds their sources
|-- reports/<Board>/                ERC/DRC, stops, design reviews, placement and routing reports (Markdown in git)
`-- tools/                          hw_checks/ (checks, release), update_skills.py, filter_history.py (Bitbucket move)
```

## Tags

| Tag | Meaning |
|---|---|
| `<BOARD>_V<version>_fab_<date>` | the design as sent for fabrication (date of the production files) |
| `<board>-v<version>` | a board release: `tools/hw_checks/hw_release.py` builds and gates the package; the Bitbucket pipeline runs it on push |

## Starting a board

1. Requirements in `docs/requirements/`; the reference project in `reference/reference_project/` (and in the store).
2. Fill `CLAUDE.md` with `.claude/skills/kicad-schematic/references/brief_template.md`.
3. Create `hardware/<Board>/` from the reference `.kicad_pro`; add the board to `hw_checks.json` (`boards`, and
   `release.boards`), then `python tools/hw_checks/hw_checks.py --update-baseline` and commit the baseline.

## Checks

```
python tools/hw_checks/hw_checks.py                 ERC / DRC against tools/hw_checks/baseline, datasheet manifest
python tools/hw_checks/hw_release.py <board>-v1.0   release package and gate (build/release/<tag>/)
python tools/update_skills.py                       newer skill releases (skills_hardware)
```
