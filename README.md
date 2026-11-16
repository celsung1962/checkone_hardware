# CheckOne hardware

AQTech Power Prognostics · hardware of the CheckOne production test fixture: powers up to eight GapOne / FluxOne
sensors with 24 V, measures their 4–20 mA loops (3 × ADS1115, INA226), two NTC temperatures and the time (PCF8563),
with a 3.5" ESP32 display module and a web page; AK-P-08A DIN-rail enclosure. One board, **CheckOne**
(`hardware/CheckOne/`).

The repository was created on 2026-11-16 with the FluxOne_hardware / GapOne_V2 layout and repository policy
(kicad-schematic skill 1.6.0). It holds the v1 schematic and placement by S. Zimath, imported on 2026-11-16
(`reports/import_2026-11-16.md`), now revision 1.1 after the review (`reports/CheckOne/review_2026-11-16.md`), the
project documents and all later work.

```
checkone_hardware/
|-- CLAUDE.md                       design brief for Claude Code (v1 baseline, decisions, open items O1-O8)
|-- OUTSIDE_GIT.md                  what is kept outside git (OneDrive store CheckOne_Hardware) and how it gets there
|-- bitbucket-pipelines.yml         CI for Bitbucket: hardware checks, release build on <board>-v<version> tags, skill updates
|-- hw_checks.json                  config of tools/hw_checks (board CheckOne, checks, release prefix checkone)
|-- .claude/skills/                 kicad-schematic 1.6.0, kicad-placement 1.3.0, kicad-routing 1.29.0 (versioned with the project)
|-- docs/requirements/              CheckOne_requirements.md (consolidated), equipment description, web page, screen designs
|-- docs/datasheets/                PDFs + .txt + manifest.csv (fetch_datasheets.py), pin tables *_pins.csv
|-- reference/import_2026-11-16/    the hand-over (v1 zip, production files, large artifacts) - READ-ONLY, outside git (store)
|-- hardware/CheckOne/              KiCad 10 project, rev 1.1; hardware/*.py generate the schematic and sync the board
|-- calc/                           checkone_budget.py (measurement, NTC, fault current, power budget)
|-- bom/                            parts.csv (catalog data), jlc_summary.md, bom_summary.md
|-- DOC/                            deliverables (generated, outside git); DOC/source/ holds their sources
|-- reports/                        import report; reports/CheckOne/ for board work (Markdown in git)
`-- tools/                          hw_checks/ (checks, release), update_skills.py, filter_history.py (Bitbucket move)
```

## Tags

| Tag | Meaning |
|---|---|
| `<BOARD>_V<version>_fab_<date>` | the design as sent for fabrication (date of the production files) |
| `checkone-v<version>` | a board release: `tools/hw_checks/hw_release.py` builds and gates the package; the Bitbucket pipeline runs it on push |

## Checks

```
python tools/hw_checks/hw_checks.py                 ERC / DRC against tools/hw_checks/baseline, datasheet manifest
python tools/hw_checks/hw_release.py checkone-v1.1  release package and gate (build/release/<tag>/)
python calc/checkone_budget.py                      measurement, NTC, fault current and power budget of v1
python tools/update_skills.py                       newer skill releases (skills_hardware)
```
