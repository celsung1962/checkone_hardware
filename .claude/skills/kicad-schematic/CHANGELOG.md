# Changelog — kicad-schematic skill

## 1.6.0 - 2026-11-13

Every IC is now compared with the maker's evaluation board, as proposed in aqtech-skills issue #1 (Vladimir, from the
VibraOne test jig; accepted by the owner 2026-11-13). The case behind it: an ESP32 board did not boot because the
datasheet's internal pull-up on EN was trusted. The maker's boards use 10 kΩ + 1 µF.

- SKILL.md: new section "Comparing every IC with the maker's evaluation board" (scope, fetch, pin-by-pin
  comparison, precedence: the board wins unless calc/ or a measurement says otherwise). `references/datasheets.md`
  and `prompt_template.md` (step 0.4 and the NEVER rules) now ask for the evaluation-board guide of every IC, not only
  of critical converters, plus the app notes of the use case.
- `fetch_datasheets.py`:
  - new doc_type `eval_board`, and status `none` via `add --none "<reason>"`, for an eval_board,
    reference_design or app_note row the maker does not publish;
  - `check --eval-board` FAILs for an IC (U / IC / PS) with neither a board document nor a "none" row;
    without the flag it prints a NOTE with the count;
  - the GapOne-specific probe-pad footprint pattern is replaced by `--no-datasheet-footprint REGEX`
    (default `^Connector_Wire:SolderWirePad_`).
- `app_circuit_scan.py`:
  - the scan also finds evaluation-board schematic pages ("EVM / Evaluation Board / Board Schematic",
    "Schematic Diagram");
  - `scan --write-review --eval-board` gives every IC a review entry, with or without a figure, carrying
    `eval_board: {doc, differences: [{what, pin, action: added | justified, why}]}`, with `doc` filled from the
    manifest;
  - `check --eval-board` FAILs for a missing or incomplete comparison. An existing `eval_board` record is
    checked even without the flag.
- Projects that started before 1.6.0 keep passing until they add `--eval-board`.

## 1.5.0 - 2026-11-13

Repository policy for every project (owner 2026-11-13, after the GapOne move to Bitbucket). The rule: git holds the
source, and copies of other projects and generated outputs live in one store folder per project.

- `init_repo.py`:
  - `.gitignore` gains the outside-git block (`build/`, `reference/`, DOC .xlsx / .docx / .pdf, report binaries, `production/`, `gerbers/`).
  - New `.gitattributes`: KiCad files byte-exact, with no line-ending conversion; binaries marked binary.
  - New `OUTSIDE_GIT.md`.
  - `--store` sets the store folder; the default is `<OneDrive>/<repo folder name>`.
  - On an existing repository it lists the policy lines missing from its `.gitignore` / `.gitattributes` and does not edit them.
- New `scripts/store_outside_git.py`:
  - copies the ignored files one way to the store, as new or changed by sha256;
  - never deletes, and writes `store_manifest.txt`;
  - skips scratch, caches, lock files and the skills' test outputs;
  - without `--copy`, only lists what it would copy.

## 1.4.1 - 2026-11-11

- Every sheet on **A3 landscape** (owner 2026-11-11): `references/schematic_drawing.md` section 6 (new first rule;
  "use a larger paper size" and "before shrinking the paper size" reworded to measure against A3), rule 8a.16.
- `check_structure.py`: `paper-size` FAIL for a sheet not on A3 landscape (A2 / A1 / A0 landscape: WARN, a recorded
  deviation). Self-test 12 cases. GapOne CON (A4, drawn before this rule): 11 sheets reported.

## 1.4.0 - 2026-11-11

Drawing rules from the review of a schematic generated with this skill (VibraOne test jig, CTRL and PROBE boards,
seven sheets; owner review 2026-11-11). `references/schematic_drawing.md`:

- Section 5 tightened. The SHEET PORTS block holds real objects (hierarchical labels for signals, power symbols with
  an in / out text for rails); a text box that only lists the ports is not a port. A power-only sheet declares its
  rails in and out under its sheet symbol on the root. The root reads as a block diagram: sheets in flow order,
  sheet pins joined by wires. A sheet pin never ends in a no-connect: draw the destination sheet empty, with its
  ports and a "TBD" note.
- New section 8a, 15 rules, each one seen on the reviewed schematic: ports with directions; root as a block diagram;
  no text over anything (examples); short visible values with the part number in the MPN / LCSC fields; spacing set
  for the texts (7.62 / 10.16 mm minimums); grounds down, rails up; one PWR_FLAG per rail at its source; no label or
  power symbol on a pin; readable DNP parts; identical blocks drawn identically; references in drawing order;
  short notes next to their block (calculations and decision histories to the report); a title block for the reader
  (process remarks to the README); destination sheets drawn before their pins are wired; the page used, not
  crowded.
- Acceptance criteria extended to match.
- New `scripts/check_structure.py` (section 9a): reads the `.kicad_sch` files and checks what a plot cannot show -
  sheet symbols without pins, text-only ports blocks, sheet pins on no-connects, labels and power symbols on
  numbered pins, power-symbol orientation, PWR_FLAG count per net (FAIL); long values, reference order, long notes,
  title-block process remarks (WARN). Pins with hidden numbers are exempt from the on-pin rules. Self-test
  `tests/run_tests_structure.py` (11 cases). Run on GapOne CON: 3 FAIL (power symbols on numbered pins of U23 and
  L242), 76 WARN; GapOne AMP: 0 FAIL, 6 WARN. Added to the pre-commit list (SKILL.md, section 10).

## 1.3.1-gapone.1 - 2026-10-22 (local change in the GapOne V2 project copy, not upstream)

- `fetch_datasheets.py check --kicad` skips copper pads with no part number: symbols whose footprint is
  `Connector_Wire:SolderWirePad_*` or `GapOne_AMP:AG1_Probe_*` (owner decision, GapOne STOP 3 Q1 (b)). To be proposed
  upstream as a general rule (no part number -> no datasheet).

## 1.3.1 - 2026-10-22

- Version field in `SKILL.md` and this changelog. No change in behaviour; the scripts and references are those of 1.3.0.

## 1.3.0 - 2026-10-21

- Principle 8: a new revision starts in the title blocks. `scripts/check_revision.py` checks that every title block of
  the project carries the same revision and date; it is in the pre-commit checks and the prompt template. Pairs with
  kicad-routing 1.26.3, whose audit compares the board's title block with the root schematic.

## 1.2.1 - 2026-10-21

- `app_circuit_scan.py`: documents with manifest status `manual` (placed by hand with `fetch_datasheets.py import`)
  are scanned; a re-scan keeps the fields the review added (`reviewed`, notes). Tests: `run_tests_app_circuit.py` 11.
- `app_circuit_scan.py` writes its JSON with LF on Windows (a CRLF rewrite made the whole file a diff).

## 1.2.0 - 2026-10-21

- Each IC block is drawn from the datasheet's typical application circuit: same parts and arrangement as the figure,
  values from `calc/`, a sheet note citing the figure, deviations recorded.
- `scripts/app_circuit_scan.py` (new): matches the placed parts to their documents (manifest, MPN / LCSC), finds the
  "Typical Application" / "Application Circuit" / "Simplified Schematic" / "Reference Design" / "Application Example"
  figures, renders the pages and writes `reports/app_circuits.json` (pending / followed / deviated / n/a). `check`
  FAILs while a part is pending or a record is incomplete, WARNs when the sheet note does not cite the figure.
- `SKILL.md` section "Drawing from the datasheet's application circuit"; `prompt_template.md`, `datasheets.md`,
  `schematic_drawing.md` updated. `tests/run_tests_app_circuit.py` (new).

## 1.1.0 - 2026-10-04

- Drawing-style pass: `references/schematic_drawing.md` with the mandatory R/C text sweep (3a) and net-label alignment
  (4a); `SKILL.md` Step 7 and the drawing phase of the prompt template.
- New scripts: `fix_passive_text.py`, `check_drawing.py`, `check_connectivity.py`, `kicad_text.py`.
- `generate_bom_xlsx.py`: KiCad 10 `dnp` / `exclude_from_bom` flags without a value.

## 1.0.1 - 2026-10-02

- `generate_bom_xlsx.py --price-source jlc`: prices and stock from the JLCPCB parts-library query.

## 1.0.0 - 2026-10-01

- First release: brief and prompt templates, JLCPCB parts policy, datasheet library (`fetch_datasheets.py`),
  reference-project analysis (`analyze_kicad_project.py`), repository layout (`init_repo.py`), symbol pin check,
  filter and switching-frequency calculators, netlist checks and tables, BOM workbook and technical document builders.
