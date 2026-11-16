#!/usr/bin/env python
"""app_circuit_scan.py - find the datasheets' typical application circuits for every part on the schematic, so each
block is drawn the way the manufacturer draws it (SKILL.md "Drawing from the datasheet's application circuit").
System Python with PyMuPDF (fitz); pypdf / pdftotext as text-only fallbacks.

  app_circuit_scan.py scan <hardware/> --datasheets docs/datasheets [--manifest F] [--parts bom/parts.csv]
                          [--out reports/app_circuits] [--dpi 110] [--write-review [reports/app_circuits.json]]
                          [--refs-regex '^(U|PS|Q|Y)\\d']
  app_circuit_scan.py check <hardware/> [--review reports/app_circuits.json]

scan
  1. Parts: the symbols placed on every .kicad_sch under <hardware/> (Reference, Value, LCSC; power symbols and
     #-references skipped), matched to the manifest's documents by MPN (Value, or the LCSC code through
     --parts bom/parts.csv). Every document of a part counts (datasheet, application note, reference design,
     hardware design guide).
  2. Pages: headings and captions of an application circuit - "Typical Application (Circuit / Schematic / Diagram)",
     "Application Circuit", "Simplified Schematic", "Typical Connection / Configuration", "Reference Design /
     Schematic", "Application Diagram" - found page by page (tables of contents skipped); the figure captions
     ("Figure 9-1. Typical Application ...") are kept, every page is rendered to PNG.
  3. Output: <out>/app_circuits.md (per part: refs, documents, pages, captions, page images), <out>/app_circuits.json,
     <out>/pages/*.png. --write-review merges reports/app_circuits.json: one entry per part with a figure, status
     "pending"; entries already reviewed keep their status while their pages are unchanged.

review (Claude, then the owner): for every pending part, look at the figure and draw the block as drawn there, then
set the status:
  "followed"  - same parts, same arrangement (IC orientation, which pin each part hangs on, input left / output
                right, the order of the parts along the power path); values from calc/ (the figure's values are only
                a starting point); "figure": the caption, e.g. "TPS63001 Figure 9-1"; "sheet": the sheet name;
  "deviated"  - drawn as the figure except the listed "deviations": [{"what": ..., "why": ...}] (a part removed, a
                different topology, a decision of the brief);
  "n/a"       - "note" says why (the figure shows a different use of the part, or the part has no circuit around it).
On the sheet, a note next to the block cites the figure ("Per TPS63001 datasheet Figure 9-1, typical application").

check (exit 1 on FAIL): FAIL for a "pending" entry or an entry without the status fields; FAIL when a part with a
figure has no entry (scan again); WARN when a followed / deviated entry's "figure" text is not found in any note of
its sheet (or of any sheet, without "sheet").

Evaluation-board comparison (1.6.0; `scan ... --write-review --eval-board` and `check ... --eval-board`):
every IC (--ic-regex, default ^(U|IC|PS)\\d) gets an entry, with or without a figure, carrying
  "eval_board": {"doc": "<eval-board / reference-design file compared>" | "none: <reason>",
                 "differences": [{"what": "10k pull-up R3", "pin": "EN", "action": "added" | "justified",
                                  "why": "..."}]}
The scan fills "doc" from the manifest (an eval_board / user_guide / reference_design / hw_design_guide document
of the part, or its eval_board row with status none). The reviewer compares the drawn circuit with the board pin by
pin and lists every part the board has on a pin we use that our circuit lacks or changes (pull-ups, RC on enable /
reset, bulk and decoupling capacitors, series resistors, snubbers, soft-start): "added" (now on our schematic) or
"justified" (why it is not needed). Parts that exist only for lab use (jumpers, test loads, optional footprints) are
justified, not copied. An empty list means no difference. When the datasheet and the board disagree the board wins
unless a calc/ script or a measurement says otherwise - record it either way. check --eval-board FAILs for an IC
without an entry or without eval_board, an empty doc, "none" without a reason, or a difference without what /
action / why; without the flag an eval_board record that exists is still checked.
"""
import csv
import datetime
import glob
import hashlib
import json
import os
import re
import subprocess
import sys

HEAD = re.compile(r'typical\s+application(s)?(\s+(circuit|schematic|diagram|example))?|application\s+(circuit|schematic|diagram)s?|'
                  r'simplified\s+(application\s+)?schematic|typical\s+(connection|configuration|circuit|operating\s+circuit)|'
                  r'reference\s+(design|schematic|circuit)|basic\s+(application|connection)|application\s+examples?|'
                  # evaluation-board user guides (1.6.0)
                  r'(evaluation|eval)\s+(board|module|kit)\s+schematics?|(EVM|EVB|EVK|EVAL)\s+schematics?|'
                  r'(board|kit|module)\s+schematics?|schematic\s+diagram', re.I)
EVAL_DOC = ('eval_board', 'user_guide', 'reference_design', 'hw_design_guide')
ACTIONS = ('added', 'justified')
CAPTION = re.compile(r'(Figure|Fig\.)\s*[\dA-Z][\w.\-]*\.?\s+[^\n]{0,90}', re.I)


def opt(a, n, d=None):
    if n not in a:
        return d
    i = a.index(n)
    return a[i + 1] if i + 1 < len(a) and not a[i + 1].startswith('--') else d


def norm(s):
    return re.sub(r'[^A-Z0-9]', '', str(s).upper())


# ------------------------------------------------------------------ schematic parts
def tokens(text):
    return re.findall(r'"(?:[^"\\]|\\.)*"|\(|\)|[^\s()"]+', text)


def top_symbols(path):
    """Placed symbols of a .kicad_sch: direct children (symbol ...) of the root, with their properties."""
    tk = tokens(open(path, encoding='utf-8').read())
    out, depth, i = [], 0, 0
    while i < len(tk):
        t = tk[i]
        if t == '(':
            depth += 1
            if depth == 2 and i + 1 < len(tk) and tk[i + 1] == 'symbol':
                j, d, props = i + 1, 2, {}
                while d >= 2 and j < len(tk):
                    if tk[j] == '(':
                        d += 1
                        if d == 3 and tk[j + 1] == 'property' and len(tk) > j + 3:
                            props[tk[j + 2].strip('"')] = tk[j + 3].strip('"')
                    elif tk[j] == ')':
                        d -= 1
                    j += 1
                out.append(props)
                depth = 1
                i = j
                continue
        elif t == ')':
            depth -= 1
        i += 1
    return out


def sch_parts(hw):
    parts = {}
    for f in sorted(glob.glob(os.path.join(hw, '*.kicad_sch'))):
        for p in top_symbols(f):
            ref = p.get('Reference', '')
            if not ref or ref.startswith('#'):
                continue
            key = (p.get('Value', ''), p.get('LCSC', ''))
            e = parts.setdefault(key, {'refs': [], 'sheets': set()})
            e['refs'].append(ref)
            e['sheets'].add(os.path.splitext(os.path.basename(f))[0])
    return parts


def sch_texts(hw):
    """{sheet: all text of its notes / text boxes / texts}"""
    out = {}
    for f in glob.glob(os.path.join(hw, '*.kicad_sch')):
        t = open(f, encoding='utf-8').read()
        out[os.path.splitext(os.path.basename(f))[0]] = ' '.join(
            m.group(2) for m in re.finditer(r'\((text|text_box) "((?:[^"\\]|\\.)*)"', t)).replace('\\n', ' ')
    return out


# ------------------------------------------------------------------ PDFs
def doc_text(pdf):
    try:
        import fitz
        with fitz.open(pdf) as d:
            return [(i + 1, p.get_text()) for i, p in enumerate(d)]
    except ImportError:
        pass
    try:
        import pypdf
        return [(i + 1, p.extract_text() or '') for i, p in enumerate(pypdf.PdfReader(pdf).pages)]
    except ImportError:
        pass
    out = subprocess.run(['pdftotext', '-layout', pdf, '-'], capture_output=True, text=True, errors='replace').stdout
    return [(i + 1, t) for i, t in enumerate(out.split('\f'))]


NOTICE = re.compile(r'important\s+notice|notice\s+and\s+disclaimer|disclaimer', re.I)


def heading_hit(text):
    """The phrase as a heading or a caption - at the start of a line (after a section number) or in a figure caption;
    not inside running text such as the graph conditions "... in the Typical Application circuit"."""
    for line in text.splitlines():
        l = line.strip()
        m = HEAD.search(l)
        if not m:
            continue
        if m.start() <= 12 and re.match(r'^(\d+(\.\d+)*\s+)?[A-Za-z]', l) and not re.match(r'^(in|on|of|the|using|as|with|from|see)', l, re.I):
            return True
        if CAPTION.search(l):
            return True
    return False


def is_toc(text):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    leaders = len(re.findall(r'(\.\s?){6,}', text))
    numbered = sum(1 for l in lines if re.search(r'\D\s\d{1,3}$', l) and re.match(r'^\d+(\.\d+)*\s+[A-Z]', l))
    return leaders >= 5 or (re.search(r'^\s*(table of )?contents\s*$', text, re.I | re.M) is not None and numbered >= 5)


def render(pdf, page, png, dpi):
    try:
        import fitz
    except ImportError:
        return False
    with fitz.open(pdf) as d:
        d[page - 1].get_pixmap(dpi=dpi).save(png)
    return True


def load_docs(dsdir, man):
    docs = []
    for row in csv.DictReader(open(man, encoding='utf-8')):
        if row.get('status', 'ok') not in ('ok', 'manual', '') or not row.get('filename', '').lower().endswith('.pdf'):
            continue
        f = os.path.join(dsdir, row['filename'])
        if os.path.isfile(f):
            docs.append(dict(part=row['part'], type=row.get('doc_type', ''), file=f, name=row['filename'],
                             lcsc=re.findall(r'C\d{3,}', row.get('url', '') + ' ' + row.get('notes', ''))))
    return docs


def cmd_scan(a):
    hw = a[1]
    dsdir = opt(a, '--datasheets', 'docs/datasheets')
    man = opt(a, '--manifest') or os.path.join(dsdir, 'manifest.csv')
    out = opt(a, '--out', 'reports/app_circuits')
    dpi = int(opt(a, '--dpi', '110'))
    want = re.compile(opt(a, '--refs-regex', r'^(U|PS|Q|Y)\d'))
    os.makedirs(os.path.join(out, 'pages'), exist_ok=True)
    docs = load_docs(dsdir, man)
    mpn = {}
    pp = opt(a, '--parts', 'bom/parts.csv')
    if os.path.isfile(pp):
        for row in csv.DictReader(open(pp, encoding='utf-8')):
            mpn[row.get('lcsc', '')] = row.get('mpn', '')

    def match(value, lcsc):
        keys = {norm(value), norm(mpn.get(lcsc, ''))} - {''}
        return [d for d in docs if len(norm(d['part'])) >= 4 and (
            any(k == norm(d['part']) or (len(k) >= 5 and (k.startswith(norm(d['part'])) or norm(d['part']).startswith(k)))
                for k in keys) or (lcsc and lcsc in d['lcsc']))]

    ev = '--eval-board' in a
    ic = re.compile(opt(a, '--ic-regex', r'^(U|IC|PS)\d'))
    none_rows = {}
    for row in csv.DictReader(open(man, encoding='utf-8')):
        if row.get('doc_type') == 'eval_board' and row.get('status') == 'none':
            none_rows[norm(row['part'])] = 'none: ' + (row.get('notes') or '').strip()
    cache, report, missing = {}, [], []
    for (value, lcsc), e in sorted(sch_parts(hw).items(), key=lambda kv: sorted(kv[1]['refs'])[0]):
        ds = match(value, lcsc)
        refs = sorted(set(e['refs']))
        if not ds:
            if any(want.search(r) for r in refs):
                missing.append(dict(value=value, lcsc=lcsc, refs=refs))
            continue
        ent = dict(part=value, lcsc=lcsc, refs=refs, sheets=sorted(e['sheets']), docs=[])
        for d in ds:
            if d['file'] not in cache:
                pages = []
                for no, text in doc_text(d['file']):
                    if not heading_hit(text) or is_toc(text) or NOTICE.search(text):
                        continue
                    caps = [c.group(0).strip() for c in CAPTION.finditer(text)
                            if HEAD.search(c.group(0)) or re.search(r'application|schematic|circuit', c.group(0), re.I)]
                    heads = sorted({m.group(0).strip() for m in HEAD.finditer(text)})[:4]
                    png = os.path.join(out, 'pages', '%s_p%d.png' % (os.path.splitext(d['name'])[0], no))
                    png = os.path.relpath(png, out).replace('\\', '/') if render(d['file'], no, png, dpi) else None
                    pages.append(dict(page=no, headings=heads, captions=caps[:6], png=png))
                cache[d['file']] = pages
            if cache[d['file']]:
                ent['docs'].append(dict(doc=d['name'], type=d['type'], pages=cache[d['file']]))
        report.append(ent)
    with_fig = [e for e in report if e['docs']]
    json.dump(dict(scanned=datetime.date.today().isoformat(), parts=report, missing=missing),
              open(os.path.join(out, 'app_circuits.json'), 'w', encoding='utf-8'), indent=1)
    md = ['# Typical application circuits - %s' % datetime.date.today().isoformat(), '',
          '%d part(s) with a document, %d with an application-circuit page, %d without a document. For every part '
          'below, open the page image and draw the block as the figure does (parts, arrangement, which pin each part '
          'hangs on, input left / output right); values from calc/. Record followed / deviated / n/a in '
          'reports/app_circuits.json.' % (len(report), len(with_fig), len(missing)), '']
    for e in with_fig:
        md += ['## %s (%s) - sheet %s' % (e['part'], ', '.join(e['refs'][:10]) + (' ...' if len(e['refs']) > 10 else ''),
                                           ', '.join(e['sheets'])), '']
        for d in e['docs']:
            for p in d['pages']:
                md.append('- **%s p. %d** (%s): %s%s' % (d['doc'], p['page'], d['type'] or 'doc', '; '.join(p['headings']),
                                                        ' - image `%s`' % p['png'] if p['png'] else ''))
                md += ['  - %s' % c for c in p['captions']]
        md.append('')
    if missing:
        md += ['## Parts without a document', '', ', '.join('%s (%s)' % (m['value'] or '?', ','.join(m['refs'][:4]))
                                                             for m in missing), '']
    open(os.path.join(out, 'app_circuits.md'), 'w', encoding='utf-8').write('\n'.join(md) + '\n')
    print('%d part(s) with a document, %d with an application circuit, %d without a document -> %s' % (
        len(report), len(with_fig), len(missing), os.path.join(out, 'app_circuits.md')))
    for e in with_fig:
        print('  %-26s %-14s %d page(s)  %s' % (e['part'][:26], ','.join(e['refs'][:3]),
                                              sum(len(d['pages']) for d in e['docs']), ', '.join(e['sheets'])))
    if '--write-review' in a:
        rf = opt(a, '--write-review') or 'reports/app_circuits.json'
        prev = json.load(open(rf, encoding='utf-8')) if os.path.isfile(rf) else {}
        old = {x['part']: x for x in prev.get('parts', [])}
        keep = {k: v for k, v in prev.items() if k not in ('_doc', 'scanned', 'missing_documents', 'parts')}
        new = []
        # with --eval-board every IC gets an entry, with or without a figure (the eval-board comparison applies to all)
        entries = [e for e in report if e['docs'] or (ev and any(ic.search(r) for r in e['refs']))]
        for e in entries:
            pages = ['%s p%d' % (d['doc'], p['page']) for d in e['docs'] for p in d['pages']]
            sig = hashlib.sha1('|'.join(pages).encode()).hexdigest()[:10]
            o = old.get(e['part'])
            is_ic = any(ic.search(r) for r in e['refs'])
            if ev and is_ic:
                eb = dict((o or {}).get('eval_board') or {})
                if not eb.get('doc'):
                    eb['doc'] = none_rows.get(norm(e['part'])) or next(
                        (d['doc'] for d in e['docs'] if d['type'] in EVAL_DOC), '')
                eb.setdefault('differences', [])
            if o and o.get('pages_sig') == sig and o.get('status') in ('followed', 'deviated', 'n/a'):
                o['refs'], o['sheets'] = e['refs'], e['sheets']
                if ev and is_ic:
                    o['eval_board'] = eb
                new.append(o)
                continue
            ent = dict(part=e['part'], refs=e['refs'], sheets=e['sheets'], pages=pages, pages_sig=sig,
                       status='pending', figure=(o or {}).get('figure', ''), deviations=(o or {}).get('deviations', []),
                       note=(o or {}).get('note', ''))
            if ev and is_ic:
                ent['eval_board'] = eb
            new.append(ent)
        os.makedirs(os.path.dirname(os.path.abspath(rf)), exist_ok=True)
        json.dump({'_doc': 'Typical application circuits of the datasheets (kicad-schematic SKILL.md, "Drawing from the '
                           'datasheet\'s application circuit"). status: pending | followed (figure: caption; sheet note '
                           'cites it) | deviated (deviations: [{what, why, source}]) | n/a (note). app_circuit_scan.py '
                           'check FAILs while one is pending. eval_board (ICs, --eval-board): doc = the evaluation-board '
                           '/ reference-design file compared, or "none: <reason>"; differences = every part the board '
                           'has on a pin we use and our circuit lacks or changes: [{what, pin, action: added | '
                           'justified, why}].',
                   'scanned': datetime.date.today().isoformat(),
                   'missing_documents': [m['value'] or ','.join(m['refs']) for m in missing], 'parts': new, **keep},
                  open(rf, 'w', encoding='utf-8', newline='\n'), indent=1, ensure_ascii=False)
        print('review written to %s: %d part(s), %d pending' % (rf, len(new), sum(1 for x in new if x['status'] == 'pending')))
    return 0


def cmd_check(a):
    hw = a[1]
    rf = opt(a, '--review', 'reports/app_circuits.json')
    if not os.path.isfile(rf):
        print('FAIL no review file %s - run app_circuit_scan.py scan ... --write-review' % rf)
        return 1
    rv = json.load(open(rf, encoding='utf-8'))
    texts = sch_texts(hw)
    fails = warns = 0
    ev = '--eval-board' in a
    ic = re.compile(opt(a, '--ic-regex', r'^(U|IC|PS)\d'))
    if ev:
        have = {norm(x['part']) for x in rv.get('parts', [])}
        for (value, _), e in sorted(sch_parts(hw).items(), key=lambda kv: sorted(kv[1]['refs'])[0]):
            if any(ic.search(r) for r in e['refs']) and norm(value) not in have:
                fails += 1
                print('FAIL %s (%s): IC with no review entry - scan again with --write-review --eval-board'
                      % (value, ','.join(sorted(e['refs'])[:3])))
    for x in rv.get('parts', []):
        st = x.get('status', 'pending')
        tag = '%s (%s)' % (x['part'], ','.join(x.get('refs', [])[:3]))
        eb = x.get('eval_board')
        if eb is None and ev and any(ic.search(r) for r in x.get('refs', [])):
            fails += 1
            print('FAIL %s: IC without the evaluation-board comparison (eval_board)' % tag)
        elif eb is not None:
            doc = (eb.get('doc') or '').strip()
            difs = eb.get('differences')
            if not doc:
                fails += 1
                print('FAIL %s: eval_board.doc empty - the board document compared, or "none: <reason>"' % tag)
            elif doc.lower().startswith('none') and len(doc) < 10:
                fails += 1
                print('FAIL %s: eval_board "none" without the reason' % tag)
            elif not doc.lower().startswith('none') and not isinstance(difs, list):
                fails += 1
                print('FAIL %s: eval_board.differences missing (an empty list means: no difference)' % tag)
            for d in (difs or []) if not doc.lower().startswith('none') else []:
                if not d.get('what') or d.get('action') not in ACTIONS or (d['action'] == 'justified' and not d.get('why')):
                    fails += 1
                    print('FAIL %s: eval-board difference %r needs what, action (added | justified) and, when '
                          'justified, why' % (tag, d.get('what') or d))
        if st == 'pending':
            fails += 1
            print('FAIL %s: application circuit not reviewed (%s)' % (tag, '; '.join(x.get('pages', [])[:3])))
        elif st not in ('followed', 'deviated', 'n/a'):
            fails += 1
            print('FAIL %s: unknown status %r' % (tag, st))
        elif st == 'n/a' and not x.get('note'):
            fails += 1
            print('FAIL %s: n/a without a note' % tag)
        elif st == 'deviated' and not x.get('deviations'):
            fails += 1
            print('FAIL %s: deviated without the list of deviations' % tag)
        elif st in ('followed', 'deviated'):
            fig = (x.get('figure') or '').strip()
            if not fig:
                fails += 1
                print('FAIL %s: %s without "figure" (the caption the block follows)' % (tag, st))
                continue
            core = re.search(r'(Figure|Fig\.)\s*[\w.\-]+', fig, re.I)
            needle = norm(core.group(0) if core else fig)
            where = [s for s in (x.get('sheets') or texts.keys()) if needle in norm(texts.get(s, ''))]
            if not where:
                warns += 1
                print('WARN %s: no note on %s cites "%s"' % (tag, '/'.join(x.get('sheets') or ['any sheet']),
                                                              core.group(0) if core else fig))
    print('app circuits: %d part(s), %d FAIL, %d WARN' % (len(rv.get('parts', [])), fails, warns))
    return 1 if fails else 0


def main():
    a = sys.argv[1:]
    if len(a) < 2 or a[0] not in ('scan', 'check'):
        print(__doc__)
        return 2
    return cmd_scan(a) if a[0] == 'scan' else cmd_check(a)


if __name__ == '__main__':
    sys.exit(main())
