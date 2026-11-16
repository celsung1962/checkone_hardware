# Parts policy for JLCPCB / LCSC assembly

Ready-to-paste text for the brief's parts-policy section. Adjust batch size, default passive size (the reference project's) and tooling.

## Order of preference

1. **Basic** — first choice. No per-part setup fee, already loaded on the machines.
2. **Preferred Extended** — when no Basic part meets the requirement.
3. **Extended** — last resort. Each distinct Extended part pays a loading fee, so **consolidate values**: repeating the same capacitor or resistor in several places beats using nearly identical values.

## Rules

- **The electrical spec beats the classification.** If the Basic part does not meet the requirement (C0G/NP0 in the signal path, film for AC coupling, tolerance and TCR of precision dividers, voltage rating with derating, temperature range), use Extended and record why. Never swap C0G for X7R, or 0.1 % for 1 %, to gain a Basic part.
- **Calculated values.** Before fixing a filter/divider value, check whether a nearby Basic value keeps the response within tolerance. If so, recompute the response with it (script in `calc/`) and use it.
- **Stock.** Accept only parts with stock ≥ 10 × (quantity per board) × (planned batch). Record stock and query date. Ask for the batch size if it is not in the brief.
- **Key parts first.** MCU, ADCs, references, regulators, clock logic, special connectors, protection: check availability and classification **before drawing the sheet**. If the part number does not exist or is out of stock, report alternatives; **do not substitute on your own**. MCUs and precision ADCs are almost always Extended — accept that.
- **Footprint = exact package of the chosen LCSC part.** Passives in the reference project's default size; confirm the Basic variant exists in that size.
- **Reuse the reference project's LCSC codes** for the same values when the requirement allows — the company has already assembled them. Re-check the current classification (it changes).
- **Parts not in the catalog** (special connectors, modules): mark as hand-assembled and exclude from the CPL.
- **Mounting holes and fiducials**: no LCSC code, excluded from BOM/CPL.
- **Catalog data for the BOM workbook** goes in `bom/parts.csv` (one row per LCSC code: manufacturer, MPN, description, class, LCSC and JLCPCB price tiers, MOQ, multiple, stock, notes) — see `references/deliverables.md`.
- **Where the information lives:** the code goes into the symbol's `LCSC` field; classification and stock live in the plugin database and in a summary `bom/jlc_summary.md` (Basic/Preferred/Extended counts + list of Extended parts with justification). Do not add extra symbol fields if the reference project does not use them.

## Tools

- Search: jlcpcb.com/parts and lcsc.com. **No web access → say so and stop the survey; never fill in codes from memory.**
- KiCad plugin `kicad-jlcpcb-tools` (Bouni): creates `jlcpcb/project.db` (table `part_info`: reference, value, footprint, lcsc, stock, exclude_from_bom, exclude_from_pos), `jlcpcb/production_files/` and `jlcpcb/gerber/`. If the reference project has this folder, use the same plugin and structure.
- Alternative: Fabrication Toolkit.

## Survey report (format)

| Function | Part number | LCSC | Class | Stock (date) | Package | Alternatives | Notes |
|---|---|---|---|---|---|---|---|
