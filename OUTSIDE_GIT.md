# Files kept outside git

Policy since 2026-11-15 (repository created by `init_repo.py`): this repository holds the **source** only - schematics,
board, project libraries, 3D models, datasheets, `calc/` scripts, Markdown reports and document sources. Files that
are copies of other projects or are generated from the source are kept in the company store:

`OneDrive - AQTech Engenharia e Instrumentação S.A\CheckOne_Hardware`

Each file keeps its repository path under that folder: `reference/x/y.kicad_pcb` is stored at
`<store>/reference/x/y.kicad_pcb`.

| What | Repository path (ignored) | How it gets to the store |
|---|---|---|
| Reference projects | `reference/` | `store_outside_git.py --only reference/ --copy`, once when they arrive (read-only) |
| Generated deliverables (BOM .xlsx, technical document .docx / .pdf) | `DOC/*.xlsx, *.docx, *.pdf` | published with the release package of each tag (below) |
| Renders, PDFs, delivery packages of the reports | `reports/**/*.png, pdf, docx, zip, xlsx, kicad_pcb` | `store_outside_git.py --copy` when one has to be kept |
| Fabrication packages | `hardware/**/production/`, `hardware/**/gerbers/` | release package of each tag |
| Script work folders | `build/` | never stored (scratch) |

**The store is a copy, not a mirror.** Editing or regenerating a file in the working folder does not change the
store. `.claude/skills/kicad-schematic/scripts/store_outside_git.py` lists what is new or changed (sha256) and, with
`--copy`, copies it one way, keeping `store_manifest.txt`; it never deletes anything in the store.

**Releases** are the official versions: the release tool of the repository builds the package of a tag and
publishes it to `<store>/releases/<tag>/`, refusing to overwrite a published tag.

The store must be visible to the whole team. Use a SharePoint / Teams library synced to each machine, or added as a
shortcut, rather than one person's OneDrive space.

A fresh clone needs `reference/` from the store: copy `<store>/reference` into the clone (git ignores it).

The datasheets (`docs/datasheets/`) stay in git: they are stable inputs and the design method needs them on disk.
Large or frequently regenerated binaries never go into git, and git LFS is not used.
