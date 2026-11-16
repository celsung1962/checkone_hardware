# KiCad files, parsing and command line

## Formats

| File | Format | How to read |
|---|---|---|
| `.kicad_pro` | JSON | `json.load`. Useful sections: `erc.rule_severities`, `schematic.drawing`, `schematic.bom_settings`, `schematic.annotation`, `net_settings.classes`, `board.design_settings.rules` |
| `.kicad_sch` | S-expression | `sexpdata` (`pip install sexpdata`). Nodes: `symbol`, `property`, `label`, `hierarchical_label`, `global_label`, `sheet`, `text_box`, `no_connect`, `junction`, `wire`, `bus`, `title_block`, `paper` |
| `.kicad_sym` | S-expression | Symbols with `pin` (number in `(number "x")`, name in `(name "y")`), including in `NAME_1_1` sub-symbols |
| `.kicad_pcb` | S-expression, large | Read only the header (`layers`) if you need the copper layer count |
| `sym-lib-table`, `fp-lib-table` | S-expression | URIs with `${KIPRJMOD}` = project library |
| exported netlist | S-expression (`kicadsexpr`) | `scripts/netlist_check.py` |

Gotchas:

- Files may use CRLF: normalize with `tr -d '\r'` before `grep`.
- The KiCad version is in `(generator_version "10.0")` in each `.kicad_sch`; the root can differ from sub-sheets if the project was migrated.
- Since KiCad 8, used symbols are embedded in the `.kicad_sch` `lib_symbols` — the project opens without the global libraries, but `lib_id` reveals global libraries from the original machine that are not in the project tables. List them and ask.
- Power symbols: the net name is the `Value`, not the `lib_id`. A `power:+3.3VA` symbol with Value `+12VA` creates net `+12VA` — confusing, do not copy.
- References starting with `#` (`#PWR`, `#FLG`) are virtual; exclude them from component counts.
- `dnp` is a symbol attribute (`(dnp yes)`), not a field.
- Sheets: `sheet` with `property "Sheetname"` and `"Sheetfile"`; `.kicad_sch` files not referenced by any `sheet` are orphans.
- Datasheets with a `.pdf` extension may be plain text (pre-extracted). Check with `file`; if text, use `tr -d '\r'` + `grep`/`sed`.

## kicad-cli (KiCad 8+)

```bash
kicad-cli version
kicad-cli sch erc  project.kicad_sch -o erc.rpt --severity-error --exit-code-violations
kicad-cli sch export netlist project.kicad_sch --format kicadsexpr -o project.net
kicad-cli sch export bom project.kicad_sch -o bom.csv --fields "Reference,Value,Footprint,LCSC,${QUANTITY}"
kicad-cli sch export pdf project.kicad_sch -o schematic.pdf
```

Check the options with `kicad-cli sch erc --help` on the installed version; flag names change between versions.

## Creating the new project from the reference

1. Copy the reference `.kicad_pro` into `hardware/` under the new name; remove `sheets`, `boards` and references to the old project; keep `erc`, `schematic.drawing`, `schematic.bom_settings`, `net_settings`.
2. Create `sym-lib-table`/`fp-lib-table` with the project library (`${KIPRJMOD}/NAME.kicad_sym`, `${KIPRJMOD}/NAME.pretty`), following the reference's scheme.
3. If the reference uses `kicad-jlcpcb-tools`, create an empty `jlcpcb/` folder; the plugin generates the rest.
4. Open it in KiCad so it fills in anything missing; run ERC on the empty project to validate the configuration.

## Generating schematics by script

It is possible to write `.kicad_sch` directly (S-expression), but each symbol needs its embedded `lib_symbols` entry, unique UUIDs and an `instances` block consistent with the hierarchical path. Prefer drawing the structure in KiCad or with a well-tested script, and **always** validate with ERC + exported netlist. Never trust a generated file that has not gone through `kicad-cli`.

## Language of schematic content

All schematic content is in English: sheet names and file names (`Power_Supply`, `ADC_1`), net names, hierarchical labels, text boxes and notes, field values (`Description`), variant names. Use ASCII only in net and sheet names (no accents, no spaces).
