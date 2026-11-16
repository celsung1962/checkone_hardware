---
name: kicad-schematic
description: >-
  End-to-end method for designing production-grade KiCad schematics (especially mixed-signal boards with ADCs, an MCU and JLCPCB assembly) with Claude and Claude Code. ALWAYS use this skill when the user is going to design, plan, review or prepare a KiCad schematic; asks for a schematic brief / CLAUDE.md, a prompt for Claude Code to draw a board, extraction of design guidelines from a reference KiCad project, JLCPCB/LCSC part selection (Basic/Extended), setting up the project repository, finding and downloading the datasheets a board needs, generating the BOM spreadsheet (Excel) or the board's technical documentation (Word), netlist or ERC verification, a drawing-style pass (overlapping reference/value text, text on symbols or wires, sheet ports, merging sheets), or analysis of .kicad_sch/.kicad_pro/.kicad_sym files — even if they never say "skill" or "KiCad" explicitly (e.g. "I'm starting the board for the new product", "get everything ready for Claude Code to draw the hardware").
---

# kicad-schematic — from requirements to a verified schematic

| | |
|---|---|
| Skill version | 1.6.0 (see `CHANGELOG.md`). Every IC is compared with the maker's evaluation board ("Comparing every IC with the maker's evaluation board"; `--eval-board` in `fetch_datasheets.py` and `app_circuit_scan.py`). 1.5.0: repository policy: `init_repo.py` writes `.gitignore` (outside-git block), `.gitattributes` and `OUTSIDE_GIT.md`, and `store_outside_git.py` copies ignored files to the project's store folder. 1.4.1: every sheet on A3 landscape (`schematic_drawing.md` section 6, `check_structure.py` paper-size). 1.4.0 — drawing rules from the review of a generated schematic (`references/schematic_drawing.md` section 8a and `scripts/check_structure.py`, section 5 tightened: the ports block holds real hierarchical labels and power symbols, power sheets declare their rails, the root is a block diagram, no sheet pin ends in a no-connect). 1.3.1 (see `CHANGELOG.md`) — version field and changelog added, no change in behaviour. 1.3.0 — principle 8 and `check_revision.py` (every title block at the same revision and date). 1.2.1 — `app_circuit_scan.py` reads hand-imported documents and writes LF JSON. 1.2.0 — each IC block drawn from the datasheet's typical application circuit (`app_circuit_scan.py`). 1.1.0 — drawing-style pass (`references/schematic_drawing.md`, `fix_passive_text.py`, `check_drawing.py`, `check_connectivity.py`). 1.0.1 — `generate_bom_xlsx.py --price-source jlc`. 1.0.0 — first release |
| Self-test | `python tests/run_tests_app_circuit.py` (21; needs PyMuPDF and sexpdata) + `python tests/run_tests_structure.py` (12) |

This skill condenses a process that worked on a real project: the schematic is not drawn from memory. First a **contract** (the brief) is written, then the form is copied from the company's **reference project**, and only then an agent (Claude Code) draws it, in phases, with **mandatory stops** and **script-based verification**. Every piece exists because, without it, something concrete goes wrong — the reasons are given next to each step.

## Language

**Everything this skill produces is in English**: the brief, the Claude Code prompt, reports, `calc/` scripts and their output, commit messages, and everything inside the schematic (sheet names, net names, text boxes, notes, field values). Reason: KiCad projects, part libraries and datasheets are English-native, and a single language avoids mixed-language sheets and makes the design reusable by any team. Only the chat replies to the user follow the user's language.

## Which part applies

| User request | Go to |
|---|---|
| "Write the brief / CLAUDE.md for the schematic" | Steps 1–4 and `references/brief_template.md` |
| "I have a reference project, follow its guidelines" | Step 3 and `scripts/analyze_kicad_project.py` |
| "Set up the repository" / starting in Claude Code | "Repository layout" below and `scripts/init_repo.py` |
| "Get the datasheets" / any new part | `references/datasheets.md` and `scripts/fetch_datasheets.py` |
| Starting a new revision of the board / title-block revision and date | Principle 8 and `scripts/check_revision.py` |
| Drawing a block around an IC / "follow the datasheet's typical application" | "Drawing from the datasheet's application circuit" below and `scripts/app_circuit_scan.py` |
| "Find parts at JLCPCB" | `references/jlcpcb_policy.md` |
| "Generate the BOM spreadsheet" / "the board's technical documentation" | "Deliverables" below and `references/deliverables.md` |
| "Write the prompt for Claude Code" | Step 5 and `references/prompt_template.md` |
| "Review the schematic / front-end / clock tree" | `references/mixed_signal_checklist.md` |
| Filter, divider or switching-frequency calculation | `scripts/filter_design.py`, `scripts/fsw_check.py` |
| Check a symbol against the datasheet | `scripts/check_symbol_pins.py` |
| Verify an exported netlist | `scripts/netlist_check.py` |
| "Tidy the drawing" / overlapping text / merge sheets / ports blocks | Step 7 and `references/schematic_drawing.md` |
| Reference or value text on a symbol, wire or neighbour (resistors, capacitors) | `scripts/fix_passive_text.py` |
| Check the plotted schematic for overlaps | `scripts/check_drawing.py` |
| Check sheet ports, root diagram, power symbols, PWR_FLAG, values, reference order, notes | `scripts/check_structure.py` |
| Prove a drawing change did not change connectivity | `scripts/check_connectivity.py` |
| Align net labels (text starts) / text width of a label or value | `references/schematic_drawing.md` 4a, `scripts/kicad_text.py` |
| KiCad file formats, parsing, kicad-cli | `references/kicad_files.md` |

## Principles (apply to everything)

1. **Conclusion first, then the justification.** The reviewing engineer needs the result before reading the math.
2. **Every number comes from a versioned script in `calc/`.** A component value without a calculation is a guess, and a guess cannot be reviewed. The script is the evidence and lets the value be recomputed when a requirement changes.
3. **No silent workarounds.** If a decision turns out infeasible, stop and show evidence plus alternatives. A question costs minutes; a hidden workaround costs a board respin.
4. **Three certainty levels on every item**: **[FROZEN]** (only the owner reopens it), **[PROPOSED]** (calculated, may be refined with justification), **[OPEN]** (the agent does not close it; keeps options open and asks). Without these tags the agent treats assumptions as facts.
5. **Documents change mid-project.** When a new revision of a requirement arrives, re-read it and **re-verify earlier conclusions that depended on it** — a rejected option may have become viable (or vice versa). Mark obsolete documents explicitly in the brief and state what still holds in them.
6. **Pinouts and part numbers only from a source.** Datasheet for pins, catalog for LCSC codes and stock. Never from memory.
7. **Form vs. engineering.** The reference project rules the form (names, fields, style, libraries, ERC); the brief rules engineering decisions. A conflict between them is reported, not resolved unilaterally.
8. **A new revision starts in the title blocks.** When work on a new revision begins (0.1 → 0.2, A → B), its number and date go into the title block of every schematic sheet and of the board with the first change, not at the release. In a generated schematic that means the generator's revision constant. A sheet left at the old number gets printed, reviewed and archived as the wrong revision. On ServiceOne (2026-10-21) every sheet still read 0.1 after the first rev. 0.2 changes. `scripts/check_revision.py hardware/ --rev <new>` FAILs on any title block with another revision or date.

## Repository layout

Every project uses the same tree, created by `scripts/init_repo.py` (idempotent: it only adds what is missing, never overwrites):

```
<repo>/
├── CLAUDE.md                         the brief (skeleton created if absent)
├── .gitignore / .gitattributes       repository policy (below)
├── OUTSIDE_GIT.md                    what is kept outside git and the store folder
├── .claude/skills/kicad-schematic/   this skill, versioned with the project
├── docs/
│   ├── requirements/                 requirements, architecture, meeting notes
│   └── datasheets/                   PDFs + .txt extractions + manifest.csv
├── reference/reference_project/      reference KiCad project (read-only)
├── hardware/                         the KiCad project
├── calc/                             calculation scripts + netlist_rules.py
├── bom/                              jlc_summary.md, parts.csv (catalog data), bom_summary.md
├── DOC/                              deliverables: <Product>_BOM.xlsx, <Product>_Technical_Documentation.docx/.pdf
│   └── source/                       technical_doc.md, doc_config.json, generated/ tables
└── reports/                          stop_0.md, stop_1.md, …
```

```bash
python3 .claude/skills/kicad-schematic/scripts/init_repo.py . --product "<Product>" --company "<Company>" --owner "<Owner>"
```

**Repository policy.** Git holds the source only. That means:
- schematics, board, project libraries and 3D models;
- datasheets;
- `calc/`;
- Markdown reports and document sources.

Each project has one **store folder** outside git, by default `<OneDrive>/<repo folder name>/` (override with `--store`). It holds:
- the reference projects (`reference/`);
- generated deliverables (DOC .xlsx / .docx / .pdf);
- report renders, PDFs and delivery zips;
- fabrication packages.

The store keeps the same relative paths as the repository. `build/` is scratch and is never stored. Git LFS is not used.

Two scripts keep the store current, and both copy one way and never delete:
- `scripts/store_outside_git.py` (`--copy`) copies new or changed ignored files and keeps `store_manifest.txt`;
- the repository's release tool publishes each tag to `<store>/releases/<tag>/`.

On an existing repository, `init_repo.py` never edits `.gitignore` / `.gitattributes`. It lists the policy lines they lack instead.

The store must be a folder the team can see: a SharePoint / Teams library synced or added as a shortcut, not someone's personal OneDrive space.

In Claude Code this is the first action of Phase 0. In chat there is no repository: produce the brief and prompt as files and tell the user where each goes in this tree. A fixed layout matters because the brief, the prompt and every script refer to these paths; a project that invents its own tree breaks them silently.

## Datasheets

In Claude Code the agent **fetches every datasheet the design needs** into `docs/datasheets/`, before drawing any symbol or choosing any part. Read `references/datasheets.md` for what to fetch (ICs, MCU hardware design guides and reference designs, the evaluation-board guide of every IC, crystals, connectors, protection, special passives), the source order (manufacturer → major distributor → never aggregators), and how to verify part number, package and revision. `scripts/fetch_datasheets.py` downloads, rejects non-PDF responses (landing/login/captcha pages), records URL, revision, SHA-256 and date in `manifest.csv`, extracts text for grepping pin tables, and `check --kicad hardware/` fails if any schematic part lacks a datasheet. Blocked download → ask the owner to download it and register it with `import`; never bypass a login or captcha.

In chat, datasheets come from the user's uploads or project files; if one is missing, ask for it or look it up with web search, and say which ones were not available.

## Drawing from the datasheet's application circuit

When a datasheet shows how the part is wired, draw the block the same way. The figure may be called "Typical
Application (Circuit)", "Application Circuit", "Simplified Schematic", "Typical Connection", "Reference Design" or
"Application Example", or it may sit in a hardware design guide. The reviewer compares the sheet with the figure:
a block drawn like the figure is checked in a minute, and a missing part stands out. A block drawn another way has
to be traced pin by pin.

1. **Scan** the schematic's parts before drawing a block (and again when parts change):
   `python3 scripts/app_circuit_scan.py scan hardware/ --datasheets docs/datasheets --parts bom/parts.csv --write-review`.
   It matches every placed part to its documents, finds the application-circuit pages, skipping tables of contents,
   running text and legal notices, keeps the figure captions and renders each page to
   `reports/app_circuits/pages/*.png`. It also writes `reports/app_circuits.md` and the review file
   `reports/app_circuits.json`, with every part `pending`.
2. **Look at the figure (the image, not only the text) and draw the block as drawn there:**
   - the same parts: every capacitor, resistor, diode and inductor of the figure is present, or its absence is
     recorded as a deviation;
   - the same arrangement: the IC in the figure's orientation where the sheet allows, each part on the pin it hangs
     on in the figure, input on the left and output on the right, and the order of the parts along the power or
     signal path;
   - the values come from `calc/`. The figure's values are a starting point, and a different value is not a
     deviation when the calculation gives it;
   - a note next to the block cites the figure, for example "Per TPS63001 datasheet Figure 2, typical application
     circuit; values: calc/power.py".
3. **Record** the result in `reports/app_circuits.json`:
   - `followed` with `figure` (the caption);
   - `deviated` with `figure` and `deviations: [{what, why}]` (a part left out, another topology, a decision of the
     brief);
   - `n/a` with `note` (the figure shows another use of the part, or no circuit around it).
   A deviation that changes the design is an owner decision: ask before drawing it.
4. **Check**: `app_circuit_scan.py check hardware/` FAILs while a part is pending or a record is incomplete, and
   WARNs when the sheet note does not cite the figure. It runs with the other checks before every commit (Step 6).

The drawing-style pass (Step 7) tidies text and labels but keeps the figure's arrangement.

### Comparing every IC with the maker's evaluation board

A datasheet can be wrong for your use, and the maker's own board shows what actually works. One AQTech ESP32 board
would not start because the datasheet said the internal pull-up on the enable pin was enough. Espressif's boards fit
10 kΩ + 1 µF there, so a comparison with the maker's board would have caught it.

The rule covers **every IC with a function of its own**: anything that is not a passive, a discrete or a simple
logic buffer.

1. **Fetch the documents.** Get the maker's evaluation-board guide, or reference design, with its schematic
   (`doc_type eval_board`), plus the app notes for the use case. If the maker publishes none, record that with
   `fetch_datasheets.py add --doc-type eval_board --none "none published (<site>, <date>)"`.
2. **Scan with the comparison on:** `app_circuit_scan.py scan ... --write-review --eval-board`. Every IC then gets an
   entry, with or without a figure, and its `eval_board.doc` is filled from the manifest. The scan also finds the
   board-schematic pages ("EVM Schematic", "Evaluation Board Schematic", "Schematic Diagram").
3. **Compare pin by pin, before drawing the block.** Take every part the board has on a pin we use that our circuit
   lacks or changes: pull-ups, RC on enable or reset, bulk and decoupling capacitors, series resistors, snubbers,
   soft-start capacitors. Record each one in `eval_board.differences` as `{what, pin, action, why}`, with action
   `added` (now on our schematic) or `justified` (why it is not needed).
   - Lab-only parts (jumpers, test loads, optional footprints) are justified, not copied. The rule is "explain every
     difference", not "copy the board".
   - An empty list means the circuit matches the board.
4. **Precedence.** When the datasheet and the board disagree, **the board wins**, unless a `calc/` script or a
   measurement says otherwise. Record the disagreement either way.
5. **Check:**
   - `fetch_datasheets.py check --kicad hardware/ --eval-board` FAILs for an IC with no board document and no
     "none" row.
   - `app_circuit_scan.py check hardware/ --eval-board` FAILs for an IC with no comparison or with an incomplete
     difference.

   Without the flag, both checks only count the missing comparisons, so a project that started before 1.6.0 keeps
   passing until it adopts the rule.

## Deliverables in `DOC/`

When the schematic is complete and verified, the skill generates two deliverables in `DOC/` — never hand-edited, regenerated whenever the schematic or the catalog data changes. Read `references/deliverables.md` for the full procedure.

- **`DOC/<Product>_BOM.xlsx`** — `scripts/generate_bom_xlsx.py` groups identical parts from the exported netlist, joins the catalog data in `bom/parts.csv` (price tiers, MOQ, multiple, stock, JLCPCB class — only from catalog queries), and writes three sheets: Summary, BOM (costs per board and per batch, stock criterion) and DNP and no LCSC. Every derived number is a formula; `--recalc` caches the values with LibreOffice and fails on any formula error.
- **`DOC/<Product>_Technical_Documentation.docx`** (+ review PDF) — `scripts/build_tech_doc.py` turns `DOC/source/technical_doc.md` into a branded Word document (cover with metadata table, contents, header/footer with page X of Y, styled tables). Pin maps, connector pinouts, test points and active-part lists are generated from the netlist by `scripts/netlist_tables.py`, calculated tables by the `calc/` scripts, and the BOM annex by the BOM generator — all pulled in with `{{include …}}`, never retyped. The section outline (purpose, description, power, MCU, acquisition, front-ends, buses, communication, peripherals, connectors, init sequence, test points, open items, project documents, BOM annex) is in the reference.

Brand: logo and colours come from the company's brand skill when one exists; otherwise neutral defaults. Both files are in English, like everything else.

## Step 1 — Collect what is already decided

Read every project document (requirements, architecture, meeting notes, datasheets) and separate:

- frozen decisions, with the reason and the **rejected alternatives and why** (this stops the agent from "rediscovering" a bad option);
- numbers that depend on each other (sample rate → clock → SPI → bus occupancy): build the calculation chain and verify it with a script;
- genuinely open items, phrased as questions with options.

Datasheets with a `.pdf` extension are sometimes plain text: check with `file` and use `tr -d '\r' < x.pdf | grep ...` instead of `pdftotext`. Extract the **pin table** and the **limits that drive the schematic** (absolute input range, SPI t_c/t_p, sync t_su, supply ranges, mandatory capacitors) into the brief's appendices.

## Step 2 — Write the brief (`CLAUDE.md`)

Use `references/brief_template.md`. Name it `CLAUDE.md` at the root of the KiCad repository, because Claude Code loads it automatically in every session — a single source of truth, with no rules copied into the prompt.

Sections that must exist: working rules; reference project and precedence; frozen decisions (table); open items; sheet structure; parts policy; channel/signal map; connections of each critical IC; clock/sync; MCU pin allocation with criteria; front-ends with calculations; power with constraints; critical nets for automated verification; conventions; execution order; pinout appendices.

Where the architecture is still undecided (e.g. how the ADC will be read), **design to keep the options open**: per-IC local nets, 0 Ω resistors at the bus junction, spare GPIOs, DNP footprints. Changing the assembly is cheap; changing the layout is not.

After writing it, do at least one fresh-eyes review looking for: numbers without a source, implementation details the documents do not cover (e.g. a flip-flop that only triggers on the rising edge when the requirement says "falling edge"), pin conflicts, inconsistencies between tables.

## Step 3 — Extract the reference project's guidelines

If the company has a production reference project, **extract the rules by script, not by visual impression**:

```bash
python3 scripts/analyze_kicad_project.py <reference_folder> > docs/reference_guidelines_raw.md
```

The script reports: KiCad version, hierarchy and page sizes, fields used and how often, passive sizes, internal part-number format, reference prefixes, label types, net prefixes and active-low style, power symbols (including name ≠ value), text-box styles, ERC configuration, net classes, libraries and JLCPCB plugin presence, and **junk fields** (fields with the same value spread over unrelated components — inherited by symbol copying).

Then turn the report into rules for the brief's conventions section:

- Where the reference is **inconsistent with itself**, adopt the majority form and record which form was discarded.
- **Do not copy defects**: junk fields, power symbols imported from another tool, symbols whose name differs from their value, ERC with important rules set to `ignore`.
- List **reusable blocks** (power input, regulators, references, ID EEPROM, rail LEDs, mounting holes/fiducials) with LCSC code and source sheet — and the **specific caveat** for reusing each (e.g. a buck that free-runs in the reference may violate a switching-frequency constraint of the new project).
- Intentional departures from the reference become an open item ("deviations from the reference"); until approved, follow the reference.
- Ignore during analysis: `.history/`, `*-backups/`, `*_old`, `*-bak`, orphan sheets (not referenced from the root).

## Step 4 — Parts policy

Read `references/jlcpcb_policy.md` and copy the policy into the brief, adapting batch size and tooling. In short: Basic → Preferred Extended → Extended; **the electrical spec beats the classification**; consolidate values; check stock with a date; survey the key parts **before** drawing; report missing parts without substituting.

## Step 5 — Kickoff prompt for Claude Code

Use `references/prompt_template.md`. The prompt **does not repeat the brief**: it defines how to work and tells the agent to read `CLAUDE.md`. Structure: `<role>`, `<context>`, `<open_item_answers>` (a block the owner fills in before pasting), `<instructions>` in phases with a **STOP** at the end of each, `<conditional_logic>` (IF/THEN), `<constraints>` (NEVER), report `<output_format>`, good/bad `<examples>` taken from **real project risks**, `<reflection>`, `<critical_reminders>`.

A phase order that works: setup (`init_repo.py`, environment, reference extraction, **datasheet library**, new project created from the reference `.kicad_pro`, key-part survey) → symbols and footprints with pin-by-pin checks → `app_circuit_scan.py scan --write-review` (the application-circuit figures of every part) → critical core (clock/sync/ADCs) → MCU → **one** complete front-end channel, reviewed before instantiating the others → power → peripherals → sheets that depend on open items → **drawing-style pass** (Step 7) → **deliverables** (`bom/parts.csv` from catalog queries, BOM workbook, technical document, review of the rendered PDF).

Include 2–3 tests of the prompt, one of which tries to talk the agent into reopening a frozen decision (it must refuse, citing the recorded reason).

## Step 6 — Continuous verification

- `kicad-cli sch erc` after every sheet; zero errors, every kept warning justified.
- Export the netlist and run `scripts/netlist_check.py` with project-specific rules (clock only through the buffer, correct capacitor on CAP pins, NC pins left floating, DRDY on a GPIO of the right domain, no MCU pin used twice, convention compliance).
- `scripts/check_symbol_pins.py` for every symbol created, against the pin table extracted from the datasheet on disk.
- `scripts/app_circuit_scan.py check hardware/ --eval-board` before every commit. It checks that:
  - every part with an application circuit in its datasheet is `followed`, `deviated` (with the deviations) or `n/a` (with the reason);
  - the sheet note cites the figure;
  - every IC has its evaluation-board comparison.

  Re-scan with `--write-review --eval-board` when parts change.
- `scripts/fetch_datasheets.py check docs/datasheets/manifest.csv --kicad hardware/ --eval-board` before every commit.
- `scripts/check_revision.py hardware/ [--rev X --date YYYY-MM-DD]` before every commit: every sheet and the board carry the same revision and date (Principle 8).
- Calculations (`scripts/filter_design.py`, `scripts/fsw_check.py`, timing margins) versioned in `calc/` and cited in a note on the sheet.
- **Every resistor and capacitor, every sheet:** `scripts/fix_passive_text.py hardware/ --check` after any placement change and before every commit — 0 to move, 0 unresolved. It sweeps all R\*/C\* references and values against their own body (DNP cross included), other bodies and pins, wires, labels, junctions, no-connects, notes, other texts, the frame and the title block, using the full character advance. Hand-drawn schematic: `--apply` moves the texts to the conventional position (vertical body: beside it; horizontal: reference above, value below; other side or shifted when blocked). Generated schematic: fix the rule in the generator. Unresolved = parts too close: make room, never shrink fonts or hide fields. Reason: these are the most numerous texts, packed in rows, and a value whose last letter touches the next part passes both a visual review and a PDF check that ignores touching boxes.
- `scripts/check_drawing.py` on the plotted PDF (text/text, text/wire, text/DNP, text/body, text/NC, frame): 0 hits.
- `scripts/check_structure.py` on the root `.kicad_sch` (sheet ports made of real labels, no sheet pin on a no-connect, power symbols oriented and not on numbered pins, one PWR_FLAG per net; long values, reference order, long notes and title-block remarks reported): 0 FAIL, every WARN fixed or explained.

## Step 7 — Drawing-style pass

When the schematic is electrically complete and verified, make it readable and printable without touching the design. Read `references/schematic_drawing.md` (it can be pasted as a prompt): no overlaps anywhere; passives wired to the pins they serve, labels only for nets that leave the sheet; text conventions; labels on a wire under their whole text, sized from the real (proportional) font widths in `scripts/kicad_text.py`; **every column of labels aligned on its text starts** — all label wires of a column start on the same coordinate, the far-end anchor is computed from the real text width (`aligned_label_anchor`) and snapped to a 25 mil connection grid (KiCad's minimum; set it in the project), so the names line up within ±0.3 mm next to the pins; a wire is lengthened only where it touches nothing else (a lengthened label wire that reached a neighbouring wire once shorted three nets; the connectivity check catches it); test pads show their reference only; a SHEET PORTS block on every sheet, made of real hierarchical labels and power symbols (a text box that only lists the ports is not a port), every sheet symbol on the root showing its pins or its rails in and out, and the root drawn as a block diagram in flow order with no sheet pin ending in a no-connect; every sheet on A3 landscape; identical channels on one sheet and small related sheets merged; staircase lanes with vertical pull resistors on many-pin parts; left-to-right flow. Section 8a lists the rules learned from a generated schematic's review: short values with the part number in a field, room before tidying, grounds down and rails up, one PWR_FLAG per rail, no label on a pin, readable DNP parts, identical blocks drawn identically, references in drawing order, short notes next to their block, a title block for the reader, and a page that is used, not crowded in one corner.

Before the first change, save the reference netlist; after every step run `scripts/check_connectivity.py` (pin groups must be identical — any difference is a drawing bug), the R/C sweep `scripts/fix_passive_text.py --check` and `scripts/check_drawing.py`, then ERC and the netlist rules. If the schematic is generated by a script, every fix goes into the generator; hand edits made in KiCad by the owner are ported into the generator (and proven identical by a semantic diff) before the next regeneration, or they are lost.

## Engineering review

To review or design an acquisition system, walk through `references/mixed_signal_checklist.md`. It collects the pitfalls that cost the most on ΔΣ ADC + MCU boards: clock-tree coherence, sync retiming, reset held until the clock is stable, f_sw vs f_MOD, SPI margin, GPIO power domains, strapping pins, AC coupling at low frequency, fault current into the ADC input, assembly options for reuse in another application.

## Deliverables

- Chat replies in the user's language, conclusions first.
- All files and all schematic content in English (see "Language").
- Brief and prompt as downloadable `.md` files.
- At the end of each deliverable, list what is still open and the 2–3 questions that unblock the most work.
