# CheckOne — Schematic brief for Claude Code (KiCad)

AQTech Power Prognostics · Hardware owner: Celso Souza · Brief revision: 2026-11-15 (rev. 0 — skeleton created by init_repo.py)

This file is the schematic contract. [FROZEN] items are locked; [PROPOSED] items are calculated starting points that may be refined with justification; [OPEN] items must not be closed by the agent.

<!-- Fill this skeleton using .claude/skills/kicad-schematic/references/brief_template.md -->

## 0. Working rules
1. Language: everything in English — reports, commits, `calc/` scripts, and all schematic content.
2. Conclusion first, then the justification.
3. Every number backed by a script in `calc/`.
4. Pinouts only from datasheets in `docs/datasheets/` (listed in `manifest.csv`). No symbol is drawn without its datasheet on disk.
5. No silent workarounds: infeasibility → stop and report with evidence and alternatives.
6. `kicad-cli sch erc` after every sheet and before every commit; netlist checked by script (section 12).
7. Form follows the reference project (0.1); engineering follows this brief.
8. Source documents: `docs/requirements/`, `docs/datasheets/`.

## 0.1 Reference project [FROZEN]
## 1. The product in one paragraph
## 2. Frozen decisions [FROZEN]
## 3. Open items [OPEN]
## 4. KiCad project structure
## 4.1 Parts policy [FROZEN]
## 5. Channel / signal map [FROZEN]
## 6. Critical IC connections
## 7. Clock and synchronization
## 8. MCU pin allocation
## 9. Analog front-ends
## 10. Power
## 11. Peripherals
## 12. Critical nets for automated verification
## 13. Conventions (extracted from the reference project) [FROZEN]
## 14. Execution order
## 15. Bench validation
## Appendix — Critical IC pinouts
