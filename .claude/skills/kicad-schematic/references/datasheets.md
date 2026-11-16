# Datasheet library: what to fetch, where from, how to verify

In Claude Code the agent builds and maintains `docs/datasheets/` itself, with `scripts/fetch_datasheets.py` managing `docs/datasheets/manifest.csv`. A symbol is never drawn, and a part is never chosen, without its datasheet on disk: pinouts, limits and application circuits come from the file, not from memory.

## What to fetch

| Category | Documents |
|---|---|
| Every IC and active part (MCU, ADC, DAC, op-amp, reference, regulator, logic, PHY, transceiver, sensor, memory) | Datasheet (`datasheet`); errata/silicon notes if they exist (`errata`) |
| MCU / SoC | Datasheet, **hardware design guidelines** (`hw_design_guide`), the relevant technical reference manual chapters (`user_guide`), errata, the vendor's reference-board schematic (`reference_design`) |
| **Every IC with a function of its own** (not passives, discretes or simple logic buffers) | Evaluation-board / EVM user guide or reference design with its schematic (`eval_board`), whose schematic and layout show the vendor's pull-ups, enable/reset RC, decoupling and grounding. If the maker publishes none, add an `eval_board` row with `--none "none published (<site>, <date>)"`. The drawn circuit is compared with it pin by pin (SKILL.md, "Comparing every IC with the maker's evaluation board"). |
| Crystals, oscillators, clock buffers | Datasheet (load capacitance, ESR, drive level, jitter) |
| Connectors, relays, magnetics, modules | Datasheet with the land pattern / mechanical drawing |
| Protection (TVS, fuses, PTC, varistors) | Datasheet (clamping voltage, energy) |
| Passives | Only when a parameter matters: film capacitors, precision/low-TCR resistors, power inductors (saturation current), ferrites (impedance curve). Generic 0603 R/C need no datasheet |

Also fetch the application notes for the exact use case: the ones the brief cites, the ones the datasheet points to, and the ones the maker lists for the part's application (`app_note`).

## When

1. **Phase 0**: every key part named in the brief, plus the MCU guides. Run `init_repo.py` first, then `add` one row per document, `fetch`, and report in STOP 0.
2. **Before drawing any symbol or picking any new part** during later phases: add and fetch its datasheet first.
3. **Before every commit** from Phase 2 on: `fetch_datasheets.py check docs/datasheets/manifest.csv --kicad hardware/` must pass (every schematic part has a datasheet on disk; no file changed since it was recorded).
4. After the key-part survey changes a part (alternative chosen, package changed), fetch the new one and mark the old row in `notes` as superseded.

## Where from (in this order)

1. **Manufacturer's product page** — find it with a web search such as `<part number> datasheet <manufacturer>` and take the direct PDF link from the official domain. Prefer the "latest revision" link over a versioned URL.
2. **Major distributor** hosting the manufacturer's PDF (LCSC, Mouser, Digi-Key, Farnell) when the manufacturer's link is blocked or login-only.
3. **Never** a datasheet aggregator site (alldatasheet, datasheetspdf, datasheet4u, datasheetarchive…) unless nothing else exists — the files are often old revisions or other manufacturers' second-source parts. `fetch_datasheets.py` flags these URLs and `check` fails on them.

If the download returns a landing page, login wall or captcha (`not a PDF`), look for the direct PDF link once more; if there is none, **stop and ask the owner** to download it by hand, then register it with `fetch_datasheets.py import`. Never bypass a login or captcha.

## Verify every file

- The part number **and package** in the PDF match the part in the brief/BOM (a family datasheet must cover the exact variant and package suffix).
- It is the **latest revision**: compare with the manufacturer's page; record the revision (the script guesses it from the text; correct it in the manifest if wrong).
- Errata exist or not — record either way in `notes`.
- The `.txt` extraction is readable (tables intact). If it is not (scanned PDF, broken extraction), note it: pin tables must then be read from the rendered page.

## Using the library

- Pin tables for `check_symbol_pins.py` are extracted from the `.txt` file and saved as `docs/datasheets/<PART>_pins.csv`; cite the table number in the CSV header comment.
- The symbol's `Datasheet` field holds the official URL recorded in the manifest.
- Brief appendices cite the file, revision and table (e.g. "SBAS949A, Table 5-1").
- Application circuits: `scripts/app_circuit_scan.py scan` finds the "Typical Application" / "Application Circuit" / "Reference Design" figures of every part on the schematic and renders their pages. Each block is drawn as its figure (SKILL.md, "Drawing from the datasheet's application circuit"). Fetch the application notes and reference designs that carry these figures together with the datasheet.

## Repository policy

Datasheets are vendor documents used for internal engineering. By default they are committed so every clone has the same revisions. If company policy forbids committing them, add `docs/datasheets/*.pdf` and `*.txt` to `.gitignore` and keep `manifest.csv` (with URL and SHA-256) committed, so anyone can re-fetch and `check` detects a different file.
