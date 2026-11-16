#!/usr/bin/env python
"""datasheet_layout_scan.py - scan the datasheets of every part on the board for PCB layout suggestions BEFORE
routing (playbook B0, references/10_datasheet_layout_review.md section 0). System Python with PyMuPDF (fitz);
pypdf or pdftotext as text-only fallbacks.

Many datasheets carry a "Layout Guidelines" / "Layout Example" / "PCB Layout Recommendations" section: capacitors at
the pins, loop areas, Kelvin sensing, keep-away zones, thermal vias, ground handling. Those are design rules from the
manufacturer, and a board routed without reading them can pass DRC and the audit and still measure wrong (ServiceOne,
reference 10). This script finds them; Claude then reads every hit (the text AND the rendered page: the drawing
is the suggestion) and turns each rule into a placement fix, a routing constraint or a layout_checks entry.

  datasheet_layout_scan.py <board.kicad_pcb> --datasheets DIR [--manifest DIR/manifest.csv] [--parts bom/parts.csv]
                           [--out DIR] [--dpi 110] [--write-params [FILE]] [--refs-regex '^(U|PS|Q|D|Y|L|J)\\d']

1. Parts: the board's footprints (Reference, Value, LCSC). A part is matched to the manifest's documents by MPN
   (Value, or the LCSC code through --parts bom/parts.csv) - every document of the part counts (datasheet, hardware
   design guide, reference design). Parts matching --refs-regex with no document are listed: get the datasheet.
2. Pages: headings and phrases of a layout section (layout guideline / example / recommendation / consideration,
   PCB / board layout, routing guideline, suggested / recommended layout, grounding, thermal pad / vias) are found
   page by page and classed: "guidelines", "example" (a figure: read the page image) or "land pattern" (footprint
   check only - not a routing rule).
3. Rule sentences: in each guidelines / example page, sentences with an imperative layout cue (as close as
   possible, short, wide, Kelvin, away from, avoid, keep, loop, via, ground plane, place, route, separate, under)
   are extracted as candidates.
4. Output: <out>/datasheet_layout.md (per part: refs, documents, pages, class, rule candidates, page images),
   <out>/datasheet_layout.json and <out>/pages/<doc>_p<N>.png for every guidelines / example page.
   --write-params merges a `datasheet_layout` block into kicad_golden.project.json (beside the board unless a FILE
   is given): one entry per part with layout pages, status "pending". Entries already reviewed (status "applied" or
   "n/a") keep their status, rules and notes; a part whose pages changed goes back to "pending".

After the review every entry carries status "applied" (each rule recorded with what it became: layout_checks entry,
placement move, netclass / width, route constraint, keep-out) or "n/a" with the reason. The audit FAILs
pre-flight while any entry is "pending", and route_freerouting.py refuses to export (--skip-datasheet-review).
"""
import csv
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys

HEAD = re.compile(r'layout\s+(guide\s*lines?|guidelines?|examples?|recommendations?|considerations?|notes?)|'
                  r'(pcb|board|printed[- ]circuit[- ]board)\s+layout|routing\s+guidelines?|'
                  r'(suggested|recommended|typical)\s+(pcb\s+)?layout|layout\s+(design|tips|rules)|'
                  r'grounding\s+(guidelines?|considerations?)|thermal\s+(pad|vias?)\b', re.I)
LAND = re.compile(r'land\s+pattern|pad\s+layout|solder\s+pad|footprint|stencil|recommended\s+(pcb\s+)?pad|'
                  r'mounting\s+pad|example\s+board\s+layout|soldering\s+pad', re.I)
LANDHEAD = re.compile(r'(recommended|suggested|typical)\s+(pcb\s+)?(land\s+pattern|pad\s+layout|footprint)|'
                      r'land\s+pattern|pad\s+layout', re.I)
CUE = re.compile(r'as close as possible|close to|closest|short(est)?\b|wide\b|width|kelvin|4-wire|four-wire|'
                 r'away from|avoid|keep\b|loop|vias?\b|ground plane|gnd plane|place\b|placed|route|routing|separate|'
                 r'under(neath)?\b|isolat|parallel|copper (area|pour)|star|return path|decoupl|bypass', re.I)


def opt(a, n, d=None):
    return a[a.index(n) + 1] if n in a and a.index(n) + 1 < len(a) and not a[a.index(n) + 1].startswith('--') else d


def norm(s):
    return re.sub(r'[^A-Z0-9]', '', str(s).upper())


def board_parts(path):
    txt = open(path, encoding='utf-8').read()
    parts = {}
    for m in re.finditer(r'\n\t\(footprint "([^"]*)"', txt):
        i = m.start() + 1
        depth, j = 0, i
        while True:
            c = txt[j]
            if c == '"':
                j = txt.index('"', j + 1)
            elif c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
                if depth == 0:
                    break
            j += 1
        blk = txt[i:j + 1]
        prop = dict(re.findall(r'\(property "([^"]+)" "([^"]*)"', blk))
        ref = prop.get('Reference', '?')
        if ref.startswith('#') or 'board_only' in blk[:400]:
            continue
        key = (prop.get('Value', ''), prop.get('LCSC', ''))
        parts.setdefault(key, []).append(ref)
    return parts


def doc_text(pdf):
    """[(page_no, text)]"""
    try:
        import fitz
        with fitz.open(pdf) as d:
            return [(i + 1, p.get_text()) for i, p in enumerate(d)]
    except ImportError:
        pass
    try:
        import pypdf
        r = pypdf.PdfReader(pdf)
        return [(i + 1, p.extract_text() or '') for i, p in enumerate(r.pages)]
    except ImportError:
        pass
    out = subprocess.run(['pdftotext', '-layout', pdf, '-'], capture_output=True, text=True, errors='replace').stdout
    return [(i + 1, t) for i, t in enumerate(out.split('\f'))]


def is_toc(text):
    """A table-of-contents page lists the layout headings too: dot leaders or many lines ending in a page number."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    leaders = len(re.findall(r'(\.\s?){6,}', text))
    numbered = sum(1 for l in lines if re.search(r'\D\s\d{1,3}$', l) and re.match(r'^\d+(\.\d+)*\s+[A-Z]', l))
    return leaders >= 5 or re.search(r'^\s*(table of )?contents\s*$', text, re.I | re.M) is not None and numbered >= 5


def render(pdf, page, png, dpi):
    try:
        import fitz
    except ImportError:
        return False
    with fitz.open(pdf) as d:
        d[page - 1].get_pixmap(dpi=dpi).save(png)
    return True


def sentences(text):
    flat = re.sub(r'-\n(\w)', r'\1', text)
    flat = re.sub(r'\s*\n\s*', ' ', flat)
    out = []
    for s in re.split(r'(?<=[.;:])\s+(?=[A-Z0-9•\-])|•', flat):
        s = s.strip(' •-\t')
        if 25 <= len(s) <= 400 and CUE.search(s) and not re.search(r'\.{5,}', s):
            out.append(s)
    return out


def main():
    a = sys.argv[1:]
    if not a or a[0].startswith('-') or '--datasheets' not in a:
        print(__doc__)
        return 2
    board = os.path.abspath(a[0])
    dsdir = opt(a, '--datasheets')
    man = opt(a, '--manifest') or os.path.join(dsdir, 'manifest.csv')
    out = opt(a, '--out') or os.path.join(os.path.dirname(board), 'datasheet_layout')
    dpi = int(opt(a, '--dpi', '110'))
    want_re = re.compile(opt(a, '--refs-regex', r'^(U|PS|Q|Y|L)\d'))
    os.makedirs(os.path.join(out, 'pages'), exist_ok=True)

    docs = []
    for row in csv.DictReader(open(man, encoding='utf-8')):
        if row.get('status', 'ok') not in ('ok', 'manual', '') or not row.get('filename', '').lower().endswith('.pdf'):
            continue
        f = os.path.join(dsdir, row['filename'])
        if os.path.isfile(f):
            docs.append(dict(part=row['part'], type=row.get('doc_type', ''), file=f, name=row['filename'],
                             lcsc=' '.join(re.findall(r'C\d{3,}', (row.get('url', '') + ' ' + row.get('notes', ''))))))
    mpn_of = {}
    pp = opt(a, '--parts') or (os.path.join(os.path.dirname(board), '..', 'bom', 'parts.csv'))
    if os.path.isfile(pp):
        for row in csv.DictReader(open(pp, encoding='utf-8')):
            mpn_of[row.get('lcsc', '')] = row.get('mpn', '')

    def match(value, lcsc):
        keys = {norm(value), norm(mpn_of.get(lcsc, ''))} - {''}
        hits = []
        for d in docs:
            pn = norm(d['part'])
            if len(pn) < 4:
                continue
            if any(k == pn or (len(k) >= 5 and (k.startswith(pn) or pn.startswith(k))) for k in keys) or \
                    (lcsc and lcsc in d['lcsc'].split()):
                hits.append(d)
        return hits

    parts = board_parts(board)
    report, missing, cache = [], [], {}
    for (value, lcsc), refs in sorted(parts.items(), key=lambda kv: sorted(kv[1])[0]):
        ds = match(value, lcsc)
        if not ds:
            if any(want_re.search(r) for r in refs):
                missing.append(dict(value=value, lcsc=lcsc, refs=sorted(refs)))
            continue
        entry = dict(part=value, lcsc=lcsc, refs=sorted(refs), docs=[])
        for d in ds:
            if d['file'] not in cache:
                pages = []
                for no, text in doc_text(d['file']):
                    if not (HEAD.search(text) or LANDHEAD.search(text)) or is_toc(text):
                        continue
                    cls = 'land pattern' if LAND.search(text) and not re.search(r'layout\s+(guide|recommend|consider)', text, re.I) \
                        else ('example' if re.search(r'layout\s+example|suggested\s+layout|recommended\s+(pcb\s+)?layout|'
                                                      r'typical\s+layout|board\s+layout\b', text, re.I) else 'guidelines')
                    heads = sorted({m.group(0).strip() for m in list(HEAD.finditer(text)) + list(LANDHEAD.finditer(text))})[:4]
                    rules = sentences(text) if cls != 'land pattern' else []
                    png = None
                    if cls != 'land pattern':
                        png = os.path.join(out, 'pages', '%s_p%d.png' % (os.path.splitext(d['name'])[0], no))
                        if not render(d['file'], no, png, dpi):
                            png = None
                    pages.append(dict(page=no, cls=cls, headings=heads, rules=rules[:25],
                                      png=os.path.relpath(png, out).replace('\\', '/') if png else None))
                cache[d['file']] = pages
            if cache[d['file']]:
                entry['docs'].append(dict(doc=d['name'], type=d['type'], pages=cache[d['file']]))
        report.append(entry)

    with_layout = [e for e in report if any(p['cls'] != 'land pattern' for d in e['docs'] for p in d['pages'])]
    json.dump(dict(board=os.path.basename(board), scanned=datetime.date.today().isoformat(), parts=report,
                   missing=missing), open(os.path.join(out, 'datasheet_layout.json'), 'w', encoding='utf-8'), indent=1)
    md = ['# Datasheet layout scan - %s (%s)' % (os.path.basename(board), datetime.date.today().isoformat()), '',
          '%d part(s) matched to a document, %d with layout guidance (guidelines / example pages), %d without a '
          'document. Read every guidelines / example page - the text AND the page image - and record what each rule '
          'became in `datasheet_layout` (kicad_golden.project.json): a layout_checks entry, a placement move, a '
          'netclass / width, a route constraint or a keep-out; or "n/a" with the reason.' % (
              len(report), len(with_layout), len(missing)), '']
    for e in with_layout:
        md += ['## %s (%s)%s' % (e['part'], ', '.join(e['refs'][:12]) + (' ...' if len(e['refs']) > 12 else ''),
                                  ' LCSC ' + e['lcsc'] if e['lcsc'] else ''), '']
        for d in e['docs']:
            for p in d['pages']:
                if p['cls'] == 'land pattern':
                    continue
                md.append('- **%s p. %d** (%s, %s): %s%s' % (d['doc'], p['page'], d['type'] or 'doc', p['cls'],
                                                            '; '.join(p['headings']),
                                                            ' - image `%s`' % p['png'] if p['png'] else ''))
                md += ['  - %s' % r for r in p['rules']]
        lp = ['%s p. %d' % (d['doc'], p['page']) for d in e['docs'] for p in d['pages'] if p['cls'] == 'land pattern']
        if lp:
            md.append('- land pattern only (footprint check): ' + ', '.join(lp))
        md.append('')
    others = [e for e in report if e not in with_layout]
    if others:
        md += ['## Parts with a document but no layout section', '',
               ', '.join('%s (%s)' % (e['part'], ','.join(e['refs'][:4])) for e in others), '']
    if missing:
        md += ['## Parts without a document (get the datasheet, then scan again)', '',
               ', '.join('%s (%s)' % (m['value'] or '?', ','.join(m['refs'][:4])) for m in missing), '']
    open(os.path.join(out, 'datasheet_layout.md'), 'w', encoding='utf-8').write('\n'.join(md) + '\n')
    print('%d part(s) with a document, %d with layout guidance, %d without a document -> %s' % (
        len(report), len(with_layout), len(missing), os.path.join(out, 'datasheet_layout.md')))
    for e in with_layout:
        n = sum(1 for d in e['docs'] for p in d['pages'] if p['cls'] != 'land pattern')
        print('  %-26s %-14s %d layout page(s)' % (e['part'][:26], ','.join(e['refs'][:3]), n))

    if '--write-params' in a:
        pf = opt(a, '--write-params') or os.path.join(os.path.dirname(board), 'kicad_golden.project.json')
        params = json.load(open(pf, encoding='utf-8')) if os.path.isfile(pf) else {}
        blk = params.get('datasheet_layout') or {}
        old = {x['part']: x for x in blk.get('parts', [])}
        new = []
        for e in with_layout:
            pages = ['%s p%d' % (d['doc'], p['page']) for d in e['docs'] for p in d['pages'] if p['cls'] != 'land pattern']
            sig = hashlib.sha1('|'.join(pages).encode()).hexdigest()[:10]
            o = old.get(e['part'])
            if o and o.get('pages_sig') == sig and o.get('status') in ('applied', 'n/a'):
                o['refs'] = e['refs']
                new.append(o)
                continue
            new.append(dict(part=e['part'], refs=e['refs'], pages=pages, pages_sig=sig, status='pending',
                            rules=(o or {}).get('rules', []), note=(o or {}).get('note', '')))
        keep = {k: v for k, v in blk.items() if k not in ('_doc', 'scanned', 'missing_documents', 'parts')}
        params['datasheet_layout'] = dict({
            '_doc':'Datasheet layout suggestions (playbook B0, reference 10 section 0), written by '
                    'datasheet_layout_scan.py before routing. Each part with layout pages is reviewed: every rule gets '
                    '{"rule": text, "source": "doc p.N", "applied_as": "layout_checks.decoupling U10.1-C31.1 | '
                    'placement: C31 moved to the pin | netclass POWER_DC | route_finish --avoid | keep-out | n/a: '
                    'reason"}; status "applied" or "n/a" (with note). The audit FAILs pre-flight while any part is '
                    '"pending"; route_freerouting.py refuses to export (--skip-datasheet-review).',
            'scanned': datetime.date.today().isoformat(),
            'missing_documents': [m['value'] or ','.join(m['refs']) for m in missing],
            'parts': new}, **keep)                # fields the review added (reviewed, notes) are kept
        open(pf, 'w', encoding='utf-8', newline='\n').write(json.dumps(params, indent=2, ensure_ascii=False) + '\n')
        pend = sum(1 for x in new if x['status'] == 'pending')
        print('datasheet_layout written to %s: %d part(s), %d pending review' % (pf, len(new), pend))
    return 0


if __name__ == '__main__':
    sys.exit(main())
