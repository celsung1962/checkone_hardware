# Board deliverables in `DOC/`: BOM workbook and technical document

When the schematic is complete and verified, the skill produces two deliverables in `DOC/`:

| File | Built by | From |
|---|---|---|
| `DOC/<Product>_BOM.xlsx` | `scripts/generate_bom_xlsx.py` | exported netlist + `bom/parts.csv` (catalog data) |
| `DOC/<Product>_Technical_Documentation.docx` (+ review PDF) | `scripts/build_tech_doc.py` | `DOC/source/technical_doc.md` + `DOC/source/doc_config.json` + generated tables |

`DOC/` holds outputs only; inputs stay in `docs/`. Both files are regenerated — never hand-edited — whenever the schematic or the catalog data changes, and both are committed with the schematic revision they describe.

## Prerequisites

- ERC clean, `netlist_check.py` passing, `fetch_datasheets.py check --kicad hardware/` passing.
- Netlist exported: `kicad-cli sch export netlist hardware/<project>.kicad_sch --format kicadsexpr -o hardware/<project>.net`.
- `bom/parts.csv` complete for every LCSC code in the schematic (below).

## 1. Catalog data: `bom/parts.csv`

One row per LCSC code, filled **only from catalog queries** (jlcpcb.com/parts for the assembly library, lcsc.com for the store), never from memory. Record the query date and time once, and pass it to the generator with `--query`.

```csv
lcsc,manufacturer,mpn,description,jlc_class,lcsc_price_tiers,lcsc_moq,lcsc_multiple,lcsc_stock,jlc_price_tiers,jlc_stock,notes
C14663,YAGEO,CC0603KRX7R9BB104,50V 100nF X7R ±10% 0603 multilayer ceramic capacitor,Basic,1:0.0080;50:0.0074;500:0.0060,50,50,8687300,1:0.0073,51150528,
```

- `*_price_tiers`: `quantity:unit price` in US$, ascending, as listed by the catalog.
- `jlc_class`: `Basic`, `Preferred` or `Extended`.
- `notes`: why the part was chosen when it is not Basic (e.g. "40 MHz ±10 ppm CL 15 pF 3225 — no Basic"), from `bom/jlc_summary.md`.
- Parts supplied by the customer: pass their codes with `--consigned`; their cost stays in the totals as a reference and the Notes column says so.

No web access → say so and stop; a BOM with invented prices is worse than no BOM.

## 2. BOM workbook

```bash
python3 scripts/generate_bom_xlsx.py --netlist hardware/<project>.net --parts bom/parts.csv \
    --product "<Product>" --revision A --batch <N> --company "<Company>" \
    --query "<YYYY-MM-DD hh:mm>, jlcpcb.com (assembly library) and lcsc.com (store)" \
    --primary <brand hex> --font Calibri --recalc
```

Three sheets, in this order:

| Sheet | Content |
|---|---|
| Summary | board, component count, assembled lines, parts per board, cost per board, batch purchase cost, query, pricing rule, lines with JLCPCB stock below 10 × batch, Basic/Preferred/Extended distinct lines and parts per board, lines without catalog data — all counts and totals are formulas over the BOM sheet |
| BOM | one row per group of identical parts: item, qty/board, qty/batch, compressed references (`C39–C45`), value, description, footprint, manufacturer / PN, LCSC, JLCPCB class, LCSC unit cost (at the purchased-quantity tier), line cost per board, LCSC purchase qty (MOQ and multiple respected), purchase cost, LCSC stock, JLCPCB unit cost, JLCPCB stock, stock ≥ 10 × batch (formula), notes; totals row; header frozen, auto-filter on |
| DNP and no LCSC | DNP parts and parts without a code (test points, holes, fiducials) |

Check the script's warnings before delivering: lines without catalog data, parts without LCSC that are not test points/holes/fiducials, and low stock. `--recalc` must report no formula errors. The script also writes `bom/bom_summary.md`, the BOM annex of the technical document.

## 3. Technical document

### Purpose

A hardware reference for writing firmware, assembling and testing the board. It describes; it does not decide — decisions live in `CLAUDE.md`. Its first section says that tables come from the netlist, numbers from `calc/`, and that the schematic and scripts prevail over the text.

### Generated tables (never retyped)

```bash
mkdir -p DOC/source/generated
python3 scripts/netlist_tables.py hardware/<project>.net pins --ref U1 --pin-regex '^GPIO' --notes DOC/source/gpio_notes.csv > DOC/source/generated/gpio_map.md
python3 scripts/netlist_tables.py hardware/<project>.net connectors > DOC/source/generated/connectors.md
python3 scripts/netlist_tables.py hardware/<project>.net testpoints > DOC/source/generated/testpoints.md
python3 scripts/netlist_tables.py hardware/<project>.net parts --group > DOC/source/generated/active_parts.md
python3 scripts/netlist_tables.py hardware/<project>.net nets --regex '_I2C_' > DOC/source/generated/i2c_nets.md
```

`gpio_notes.csv` (`pin_function,note`) adds the human "Function" column (e.g. `GPIO7,CS of ADC #1 (IO MUX SPI2_CS)`). Tables derived from calculations (rail table, scaling, address maps, timing) are printed by the `calc/` scripts as Markdown into `DOC/source/generated/` too. The source pulls each file in with `{{include generated/<file>.md}}`, and the BOM annex with `{{include ../../bom/bom_summary.md}}`.

### Section outline

Adapt to the board; drop sections that do not apply, keep the order.

| # | Section | Content and source |
|---|---|---|
| 1 | Purpose and scope | Audience (firmware, assembly, test); data sources and precedence; pointer to the BOM workbook; naming conventions (MCU prefix, active-low, channel IDs, DNP) |
| 2 | General description | 2.1 Function (one paragraph); 2.2 Blocks table (block · implementation · schematic sheet); 2.3 Key specifications table |
| 3 | Power | Input and protection; rails table (rail · voltage · source · max load · main loads); sequencing; switching frequencies vs the ADC constraint (`fsw_check.py`); rail monitoring (channel → rail → scaling); power budget (`calc/`) |
| 4 | MCU | System table (crystal, RTC, flash, PSRAM, core supply, reset, boot, strapping, programming/debug); GPIO map (generated) |
| 5 | Acquisition | Overview table (ADC · bus · CS · DRDY · channels); clock and sync (configuration table); SPI interface and suggested register values with the datasheet table numbers; channel map; code-to-voltage conversion per front-end mode; ADC start-up sequence; assembly options kept open |
| 6 | Analog front-ends | Signal chain; modes and control bits; channel monitoring; special inputs |
| 7 | Buses (I²C/SPI peripherals) | Topology; address map; per-expander bit maps |
| 8 | Communication | Each interface: PHY/transceiver, pins, isolation, termination, firmware notes |
| 9 | Peripherals | Storage, ID EEPROM, LEDs, relays, displays |
| 10 | Connectors | Generated pinout table + function per pin |
| 11 | Recommended initialization sequence | Numbered firmware bring-up order (power checks, clocks, ADC reset/sync, buses, peripherals) |
| 12 | Test points and bench tests | Generated test-point table; bench measurements that validate the frozen decisions |
| 13 | Open items and firmware checks | Every [OPEN] item and every hardware feature that still needs firmware confirmation |
| 14 | Project documents | Table: file → content (CLAUDE.md, decisions log, KiCad project, calc/, bom/, DOC/ workbook, datasheets) |
| A | Annex A — BOM summary | `bom/bom_summary.md` |

### Writing rules

- English, conclusions first, short sentences; tables for anything with rows.
- Every number either comes from a generated table or cites its script (`Source: calc/power.py §3`).
- Register values cite the datasheet revision and table (e.g. "SBAS949A, Tables 8-16 to 8-18").
- No design rationale debates: one line of "why" at most, pointing to `CLAUDE.md`.

### Config and build

`DOC/source/doc_config.json` (created by `init_repo.py`): product, document title, subtitle, cover lines, metadata table (document no., product, board revision, schematic version/commit, design contract revision, hardware owner, data source, date), company, date, logo, colours, font, page size. Take logo and colours from the company's brand skill when one exists (e.g. a `<company>-brand` skill); otherwise leave the neutral defaults.

```bash
python3 scripts/build_tech_doc.py --source DOC/source/technical_doc.md --config DOC/source/doc_config.json --pdf
```

The result: cover page with the metadata table, table of contents, header with logo and document title, footer with company · title · date · "Page X of Y", headings in the brand colours, tables with a coloured header row and zebra rows. `--pdf` writes a review PDF with the table of contents filled in; the `.docx` refreshes its fields when first opened in Word.

**Look at the PDF before delivering**: render 3–4 pages (cover, contents, a table-heavy page, the annex) and check for overflowing tables, empty includes and broken characters.
