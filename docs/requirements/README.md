# docs/requirements

Requirements, architecture documents and meeting notes. Mark obsolete revisions in CLAUDE.md. Start with
`CheckOne_requirements.md`.

| File | What it is | Source |
|---|---|---|
| `CheckOne_requirements.md` | Consolidated hardware requirements in English, with the source of each item, conflicts C-1…C-12 and gaps G-1…G-6 | written 2026-11-16 from the files below and the v1 KiCad project |
| `CheckOne_Descricao_do_equipamento_2026-11-16.html` | Equipment description (Portuguese): purpose, sensors, specifications, operator interface, electronics, logging, mechanics and connectors, BOM with JLCPCB / LCSC codes, ngspice verification, industry comparison, items to confirm, future ideas | claude.ai artifact `Xh4kmXWBBsN2iChEBn26U2`, version 1794796794-94c8, copied 2026-11-16 (unchanged HTML) |
| `CheckOne_Descricao_do_equipamento_2026-11-16.md` | Text extraction of the description, for grep; the HTML is the source | made from the HTML on 2026-11-16 |
| `CheckOne_web_page_demo_2026-11-16.html` | The embedded web page in demo mode: Painel, Histórico, Configuração | claude.ai artifact `Ht5hfXcbP4EHC8VT1EJMPc`, version 1794751478-bc3b, copied 2026-11-16 |
| `ui_screens/` | Screen designs: 5 screens at 320 × 480 (CYD, JC3248W535) and 480 × 800 (JC4880P443C); `canvas.json` index, one `.dc.html` per screen, `ds/aqtech-windy/tokens.json` | claude.ai Design canvas `7FB1cQbtUXRaEiTuMSN7uk`, version 1794833347-169e, project files copied 2026-11-16 |

Outside git, in `reference/import_2026-11-16/artifacts/` (`OUTSIDE_GIT.md`): the screens rendered in real pixels
(artifact `S2LDsuwh11eCxLrDsTVLyd`, 120 KB of embedded images) and the 3D placement viewer in the AK-P-08A enclosure
(artifact `PQkZPZsN5XBAJPcJZDhCea`, 1.7 MB).
