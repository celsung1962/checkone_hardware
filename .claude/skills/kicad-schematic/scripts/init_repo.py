#!/usr/bin/env python3
"""
Creates the standard repository layout for a KiCad schematic project driven by
this skill. Idempotent: it never overwrites an existing file or folder content;
it only adds what is missing and reports what it did.

Usage:
    python3 init_repo.py <repo_root> --product "<Product name>" [--company "<Company>"]
                         [--owner "<Hardware owner>"] [--store "<folder outside git>"]
                         [--skill-dir <path to this skill>] [--dry-run]

Repository policy (git holds the SOURCE only; inputs that are copies of other projects and every generated output
live in the company store, by default the OneDrive folder <OneDrive>/<repo name>/, same relative paths):
    .gitignore      KiCad backups / caches, Python, OS, Office locks + the "outside git" block (reference/, build/,
                    generated DOC/ and reports/ binaries, fabrication packages)
    .gitattributes  KiCad files byte-exact (no line-ending conversion), binaries marked binary
    OUTSIDE_GIT.md  what is kept outside git, where, and how it gets there (store_outside_git.py, releases)

Layout created:
    <repo>/
    ├── CLAUDE.md                      brief skeleton (only if absent)
    ├── .gitignore / .gitattributes    repository policy (above)
    ├── OUTSIDE_GIT.md                 the files kept outside git and the store folder
    ├── .claude/skills/kicad-schematic/  copy of this skill (only if absent)
    ├── docs/
    │   ├── requirements/              requirements, architecture, meeting notes
    │   └── datasheets/
    │       └── manifest.csv           one row per datasheet (see fetch_datasheets.py)
    ├── reference/reference_project/   reference KiCad project (read-only)
    ├── hardware/                      the KiCad project (created in Phase 0 from the reference .kicad_pro)
    ├── calc/                          calculation scripts and netlist rules
    ├── bom/                           jlc_summary.md, parts.csv (catalog data), bom_summary.md
    ├── DOC/                           deliverables: <Product>_BOM.xlsx, <Product>_Technical_Documentation.docx/.pdf
    │   └── source/                    technical_doc.md, doc_config.json, generated/ tables
    └── reports/                       one report per STOP
"""
import argparse, os, shutil, datetime, sys

DIRS = {
    "docs/requirements": "Requirements, architecture documents and meeting notes. Mark obsolete revisions in CLAUDE.md.",
    "docs/datasheets": "Datasheets, application notes and vendor hardware design guidelines, one file per document, "
                       "listed in manifest.csv. Filled by scripts/fetch_datasheets.py.",
    "reference/reference_project": "The company's reference KiCad project, extracted here once. READ-ONLY: never edit.",
    "hardware": "The KiCad project. Created in Phase 0 from the reference project's .kicad_pro.",
    "calc": "Versioned calculation scripts (one per decision) and netlist_rules.py for netlist_check.py. "
            "Every component value in the schematic cites one of these scripts.",
    "bom": "jlc_summary.md (Basic/Preferred/Extended counts, Extended justifications), parts.csv (catalog data: "
           "prices, MOQ, stock — only from catalog queries) and bom_summary.md (written by generate_bom_xlsx.py).",
    "DOC": "Board deliverables, regenerated (never hand-edited): <Product>_BOM.xlsx (generate_bom_xlsx.py) and "
           "<Product>_Technical_Documentation.docx + .pdf (build_tech_doc.py).",
    "DOC/source": "Technical document source: technical_doc.md, doc_config.json, gpio_notes.csv and generated/ "
                  "(tables printed by netlist_tables.py and the calc/ scripts).",
    "reports": "One Markdown report per STOP: stop_0.md, stop_1.md, ...",
}

MANIFEST_HEADER = "part,manufacturer,doc_type,url,filename,revision,sha256,retrieved,status,notes\n"
PARTS_HEADER = ("lcsc,manufacturer,mpn,description,jlc_class,lcsc_price_tiers,lcsc_moq,lcsc_multiple,lcsc_stock,"
                "jlc_price_tiers,jlc_stock,notes\n")


def doc_config(product, company, owner, today):
    import json
    return json.dumps({
        "product": product, "doc_title": "Board technical documentation",
        "subtitle": "<one-line description of the product>",
        "cover_lines": ["Main board, revision A · <MCU> + <converters> · <n> inputs",
                        "Hardware reference for firmware development, assembly and test"],
        "metadata": [["Document no.", "TBD"], ["Product", f"{product} — main board"],
                     ["Board revision", "A (schematic in progress)"], ["Schematic", "KiCad <version>, <pages>, commit <hash> (<date>)"],
                     ["Design contract", "CLAUDE.md rev. <n>"], ["Hardware", owner],
                     ["Data source", "KiCad netlist and calc/ scripts"], ["Date", today]],
        "company": company, "date": today, "logo": None,
        "primary": "1F4E79", "accent": "2E75B6", "zebra": "F7F9FA", "text": "292929", "muted": "6D6D6D",
        "font": "Calibri", "page": "A4"}, indent=2, ensure_ascii=False) + "\n"


TECH_DOC = """# 1. Purpose and scope

<!-- Audience, data sources and precedence (schematic and calc/ scripts prevail), pointer to DOC/<Product>_BOM.xlsx, naming conventions. See references/deliverables.md -->

# 2. General description

## 2.1 Function

## 2.2 Blocks

## 2.3 Key specifications

# 3. Power

# 4. MCU

## 4.1 System

## 4.2 GPIO map

<!-- {{include generated/gpio_map.md}} -->

# 5. Acquisition

# 6. Analog front-ends

# 7. Buses

# 8. Communication

# 9. Peripherals

# 10. Connectors

<!-- {{include generated/connectors.md}} -->

# 11. Recommended initialization sequence

# 12. Test points and bench tests

<!-- {{include generated/testpoints.md}} -->

# 13. Open items and firmware checks

# 14. Project documents

# Annex A — BOM summary

<!-- {{include ../../bom/bom_summary.md}} -->
"""

GITIGNORE = """# KiCad
*-backups/
*.kicad_prl
fp-info-cache
*.lck
\\#auto_saved_files\\#
_autosave-*
.history/
# Python
__pycache__/
*.pyc
# OS
.DS_Store
Thumbs.db
# Office lock files
~$*
# ---- Kept OUTSIDE git (repository policy: git holds the source only; see OUTSIDE_GIT.md) ----
# script work folders: scratch boards, logs, renders - never stored
build/
# reference projects: read-only copies of other projects, kept in the store
reference/
# generated deliverables (rebuilt from the source; published per release tag)
/DOC/*.xlsx
/DOC/*.docx
/DOC/*.pdf
reports/**/*.png
reports/**/*.pdf
reports/**/*.docx
reports/**/*.zip
reports/**/*.xlsx
reports/**/*.kicad_pcb
# fabrication packages (Gerber / drill / BOM / CPL), rebuilt per release
hardware/**/production/
hardware/**/gerbers/
"""

GITATTRIBUTES = """# KiCad files are stored byte-exact: no line-ending conversion on any machine (Windows, Linux CI), so a
# checkout never shows a whole-file diff. git still diffs them as text.
*.kicad_pcb -text
*.kicad_sch -text
*.kicad_pro -text
*.kicad_sym -text
*.kicad_mod -text
*.kicad_dru -text
*.kicad_wks -text
fp-lib-table -text
sym-lib-table -text
# binaries (the few that are allowed in git: datasheets, 3D models, logos)
*.pdf binary
*.png binary
*.jpg binary
*.jpeg binary
*.zip binary
*.step binary
*.stp binary
*.stpZ binary
*.wrl binary
*.xlsx binary
*.docx binary
"""


def outside_git_md(product, store, today):
    return f"""# Files kept outside git

Policy since {today} (repository created by `init_repo.py`): this repository holds the **source** only - schematics,
board, project libraries, 3D models, datasheets, `calc/` scripts, Markdown reports and document sources. Files that
are copies of other projects or are generated from the source are kept in the company store:

`{store}`

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
"""


def claude_md(product, company, owner, today):
    return f"""# {product} — Schematic brief for Claude Code (KiCad)

{company} · Hardware owner: {owner} · Brief revision: {today} (rev. 0 — skeleton created by init_repo.py)

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
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--product", required=True)
    ap.add_argument("--company", default="<Company>")
    ap.add_argument("--owner", default="<Hardware owner>")
    ap.add_argument("--store", help="folder for the files kept outside git (default: <OneDrive>/<repo folder name>)")
    ap.add_argument("--skill-dir", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    root = os.path.abspath(a.root)
    today = datetime.date.today().isoformat()
    created, kept = [], []

    def mkdir(p):
        full = os.path.join(root, p)
        if os.path.isdir(full):
            kept.append(p + "/")
        else:
            created.append(p + "/")
            if not a.dry_run:
                os.makedirs(full, exist_ok=True)

    def write(p, text):
        full = os.path.join(root, p)
        if os.path.exists(full):
            kept.append(p)
            return
        created.append(p)
        if not a.dry_run:
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as f:
                f.write(text)

    if not a.dry_run:
        os.makedirs(root, exist_ok=True)
    for d, readme in DIRS.items():
        mkdir(d)
        write(os.path.join(d, "README.md"), f"# {d}\n\n{readme}\n")
    write("docs/datasheets/manifest.csv", MANIFEST_HEADER)
    write("bom/parts.csv", PARTS_HEADER)
    mkdir("DOC/source/generated")
    write("DOC/source/doc_config.json", doc_config(a.product, a.company, a.owner, today))
    write("DOC/source/technical_doc.md", TECH_DOC)
    write(".gitignore", GITIGNORE)
    write(".gitattributes", GITATTRIBUTES)
    od = os.environ.get("OneDriveCommercial") or os.environ.get("OneDrive")
    store = a.store or (os.path.join(od, os.path.basename(root)) if od else
                        f"<OneDrive>/{os.path.basename(root)}  (set the real folder here)")
    write("OUTSIDE_GIT.md", outside_git_md(a.product, store, today))
    # an existing repository keeps its own files: report the policy lines they lack (never edit them)
    policy_gaps = []
    for fn, tmpl in ((".gitignore", GITIGNORE), (".gitattributes", GITATTRIBUTES)):
        p = os.path.join(root, fn)
        if os.path.isfile(p):
            have = {ln.strip() for ln in open(p, encoding="utf-8", errors="replace")}
            gap = [ln for ln in tmpl.splitlines() if ln.strip() and not ln.startswith("#") and ln.strip() not in have]
            if gap:
                policy_gaps.append(f"{fn} lacks {len(gap)} policy line(s): {', '.join(gap)}")
    write("CLAUDE.md", claude_md(a.product, a.company, a.owner, today))

    skill_dst = os.path.join(".claude", "skills", "kicad-schematic")
    if os.path.isdir(os.path.join(root, skill_dst)):
        kept.append(skill_dst + "/")
    elif os.path.isfile(os.path.join(a.skill_dir, "SKILL.md")) and \
            os.path.abspath(a.skill_dir) != os.path.abspath(os.path.join(root, skill_dst)):
        created.append(skill_dst + "/")
        if not a.dry_run:
            shutil.copytree(a.skill_dir, os.path.join(root, skill_dst),
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "evals"))
    else:
        print(f"> Skill folder not found at {a.skill_dir}; copy it to {skill_dst}/ manually.", file=sys.stderr)

    print(f"# Repository layout — {root}{' (dry run)' if a.dry_run else ''}\n")
    print("Created:" if created else "Created: nothing (everything already existed)")
    for c in created:
        print(f"  + {c}")
    if kept:
        print("Kept (already existed, not touched):")
        for k in kept:
            print(f"  = {k}")
    missing = []
    ref = os.path.join(root, "reference", "reference_project")
    if not any(f.endswith(".kicad_pro") for _, _, fs in os.walk(ref) for f in fs):
        missing.append("reference/reference_project/ has no .kicad_pro — extract the reference project there (or record in CLAUDE.md that there is none).")
    req = os.path.join(root, "docs", "requirements")
    if not [f for f in os.listdir(req) if f != "README.md"] if os.path.isdir(req) else True:
        missing.append("docs/requirements/ is empty — add the requirements and architecture documents.")
    missing += [g + " - add them by hand (and untrack files they now ignore: git rm --cached)"
                for g in policy_gaps]
    if missing:
        print("\nNext steps for the owner:")
        for m in missing:
            print(f"  - {m}")


if __name__ == "__main__":
    main()
