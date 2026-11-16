# Schematic brief template (`CLAUDE.md`)

Copy, fill in and delete the `<!-- -->` instructions. Every item gets **[FROZEN]**, **[PROPOSED]** or **[OPEN]**. Quoted examples are illustrative — replace them with your project's. Write the brief in English.

---

```markdown
# <Product> — Schematic brief for Claude Code (KiCad)

<Company> · Hardware owner: <name> · Brief revision: <date> (rev. N — <what changed>)

This file is the schematic contract. [FROZEN] items are locked; [PROPOSED] items are calculated starting points that may be refined with justification; [OPEN] items must not be closed by the agent.

## 0. Working rules
1. Language: everything in English — reports, commits, `calc/` scripts, and all schematic content (sheet names, nets, text boxes, fields).
2. Conclusion first, then the justification.
3. Every number backed by a script in `calc/`.
4. Pinouts only from datasheets in `docs/datasheets/` (listed in `manifest.csv`). No symbol is drawn without its datasheet on disk. If a library symbol disagrees, the datasheet wins.
5. No silent workarounds: infeasibility → stop and report with evidence and alternatives.
6. `kicad-cli sch erc` after every sheet and before every commit; netlist checked by script (section 12).
7. Form follows the reference project (0.1); engineering follows this brief.
8. Source documents in `docs/requirements/` and `docs/datasheets/`: <list>. Repository layout per the kicad-schematic skill. <!-- Mark obsolete ones explicitly: "Document X dated <date> is superseded on A, B, C; only D and E still hold." -->

## 0.1 Reference project [FROZEN]
<!-- Location, what to ignore (.history, backups, _old, orphan sheets), what it is, precedence, table of reusable blocks with LCSC code and caveats. Generate with scripts/analyze_kicad_project.py. -->

## 1. The product in one paragraph

## 2. Frozen decisions [FROZEN]
| Item | Value | Notes (reason; rejected alternative and why) |
|---|---|---|

## 3. Open items [OPEN]
<!-- One per item: On — title. Context. Options. **Action:** how to draw so the options stay open. -->
<!-- Always include: "On — Deviations from the reference project" as a numbered list, and the planned batch size (stock criterion). -->

## 4. KiCad project structure
<!-- Version (the reference's). Create from the reference .kicad_pro. Table: sheet | page | content | equivalent in the reference. -->

## 4.1 Parts policy [FROZEN]
<!-- Copy from references/jlcpcb_policy.md, adjusting supplier, batch and tooling. -->

## 5. Channel / signal map [FROZEN]
| Channel | Sensor/signal | Range | Bandwidth | Front-end | IC · pin |
|---|---|---|---|---|---|

## 6. Critical IC connections
<!-- Pin-by-pin table: pin | name | connection (with decoupling and resistors). Then: electrical limits the front-end must respect (absolute range, max current, input impedance). -->

## 7. Clock and synchronization
<!-- ASCII tree; implementation details the documents do not cover (e.g. edge inversion, fanout, reset hold, terminations, test points). -->

## 8. MCU pin allocation
<!-- 8.1 pins fixed by the datasheet; 8.2 acquisition [PROPOSED] with explicit criteria (IO MUX vs matrix, low-power domain, physical grouping); 8.3 reservations for open peripherals. Mandatory checks before freezing. -->

## 9. Analog front-ends
<!-- Common requirements; per type: chain, table block|requirement|proposed value, values already calculated (with the script). -->

## 10. Power
<!-- 10.1 rails (names in the reference's style); 10.2 sequencing; 10.3 switching-frequency constraints with the rule and the script. -->

## 11. Peripherals (storage, communication, HMI…)

## 12. Critical nets for automated verification
<!-- Numbered assertions that calc/check_netlist.py must prove. Last one: compliance with the section 13 conventions. -->

## 13. Conventions (extracted from the reference project) [FROZEN]
<!-- 13.1 nets and labels (MCU prefix, active-low, pairs); 13.2 rails; 13.3 reference prefixes; 13.4 fields and internal part-number format; 13.5 libraries; 13.6 text styles. For every inconsistency in the reference: adopted form and discarded form. -->

## 14. Execution order
<!-- 0 setup and key-part survey; 1 symbols; 2 critical core; 3 MCU; 4 one front-end channel; 5 power; 6 peripherals; 7 stop and ask about open items; F deliverables in DOC/ (BOM workbook, technical document). -->

## 15. Bench validation (note on the root sheet)
<!-- Measurements that validate the critical decisions (clock duty at the pin, resync flag, shorted-input noise, switching tones in the FFT, AAF response). -->

## Appendix A/B — Critical IC pinouts (source: datasheet, table X)
```

---

## Filling tips

- **Rejected alternatives** in the decisions table save hours: without them, the agent proposes the bad option again (e.g. a "cleaner" external oscillator that breaks the MCU PLL).
- **The ADC absolute input range** decides whether the front-end needs a level shift. Many modern ΔΣ ADCs accept a few hundred mV below ground — check before designing an unnecessary level shifter.
- **Filter values** always with the commercial series (E24/E96) already applied and the response recomputed with them; the brief must show the final values and the loss at the band edge.
- **Critical nets** are written as testable assertions ("each CLKIN receives exactly one buffer branch"), not as wishes.
