#!/usr/bin/env python
"""run_tests_app_circuit.py - self-test for scripts/app_circuit_scan.py (drawing from the datasheet's typical
application circuit). System Python with PyMuPDF (fitz); skipped without it.

The test datasheet PARTY456 has: page 1 "7 Typical Application" with "Figure 7-1. Typical Application Circuit";
page 2 a table of contents listing it; page 3 running text "measured in the Typical Application circuit" (graph
conditions, not a figure); page 4 the legal notice ("IMPORTANT NOTICE ... REFERENCE DESIGNS"). The schematic has
U1 = PARTY456 (LCSC C999002), R1 and a GND power symbol.

  scan            U1 matched; only page 1 is a hit, with its caption and a page image
  --write-review  reports entry U1 pending; check FAILs (exit 1)
  followed        figure "PARTY456 Figure 7-1" and a sheet note citing it: check passes, no WARN; a figure the
                  sheet does not cite -> WARN
  incomplete      deviated without deviations, n/a without a note, followed without figure -> FAIL
  re-scan         a reviewed entry is kept
  eval board      (1.6.0) U2 = PLAIN7 (no figure) and an EVM guide for PARTY456: fetch check --eval-board FAILs for
                  PLAIN7 until it has an eval_board "none" row; scan --eval-board finds the EVM schematic page, gives U2
                  an entry and fills eval_board.doc; check --eval-board FAILs for a missing comparison or a justified
                  difference without why, passes when every difference is added / justified
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCR = os.path.normpath(os.path.join(HERE, '..', 'scripts', 'app_circuit_scan.py'))
PASS = FAIL = 0
TMP = tempfile.mkdtemp(prefix='ks_app_')

SCH = '''(kicad_sch (version 20260306) (generator "eeschema") (uuid "00000000-0000-0000-0000-000000000001") (paper "A4")
 (lib_symbols (symbol "lib:PARTY" (property "Reference" "U" (at 0 0 0)) (property "Value" "PARTY" (at 0 0 0))))
 (symbol (lib_id "lib:PARTY") (at 50 50 0) (unit 1) (uuid "00000000-0000-0000-0000-000000000002")
  (property "Reference" "U1" (at 0 0 0)) (property "Value" "PARTY456" (at 0 0 0)) (property "LCSC" "C999002" (at 0 0 0)))
 (symbol (lib_id "Device:R") (at 70 50 0) (unit 1) (uuid "00000000-0000-0000-0000-000000000003")
  (property "Reference" "R1" (at 0 0 0)) (property "Value" "10K" (at 0 0 0)))
 (symbol (lib_id "power:GND") (at 50 60 0) (unit 1) (uuid "00000000-0000-0000-0000-000000000004")
  (property "Reference" "#PWR01" (at 0 0 0)) (property "Value" "GND" (at 0 0 0)))
 (text_box "NOTE%s" (at 10 10 0) (size 40 10))
)
'''


def ok(cond, name, extra=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print('  ok   ' + name)
    else:
        FAIL += 1
        print('  FAIL ' + name + (('\n       ' + str(extra)[-1500:]) if extra else ''))


def run(*args):
    r = subprocess.run([sys.executable, SCR] + list(args), capture_output=True, text=True, encoding='utf-8',
                       errors='replace', cwd=TMP)
    return r.returncode, '\n'.join(l for l in (r.stdout + r.stderr).splitlines() if 'MuPDF' not in l)


def main():
    try:
        import fitz
    except ImportError:
        print('PyMuPDF not found - app circuit tests skipped')
        return 0
    print('app_circuit_scan.py')
    ds = os.path.join(TMP, 'docs', 'datasheets')
    hw = os.path.join(TMP, 'hardware')
    os.makedirs(ds)
    os.makedirs(hw)
    d = fitz.open()
    for t in ["7 Typical Application\nThe PARTY456 needs one input capacitor and a feedback divider.\n"
              "Figure 7-1. Typical Application Circuit\n",
              "Table of Contents\n1 Features ..................... 1\n7 Typical Application ............. 1\n"
              "7.1 Design Requirements ........... 1\n8 Layout ................... 2\n9 Mechanical .............. 3\n",
              "6 Typical Characteristics\nAll curves measured in the Typical Application circuit, unless otherwise noted.\n",
              "IMPORTANT NOTICE AND DISCLAIMER\nTI PROVIDES TECHNICAL AND RELIABILITY DATA, DESIGN RESOURCES (INCLUDING\n"
              "REFERENCE DESIGNS), APPLICATION OR OTHER DESIGN ADVICE ...\n"]:
        d.new_page().insert_text((50, 72), t, fontsize=9)
    d.save(os.path.join(ds, 'PARTY456_datasheet.pdf'))
    open(os.path.join(ds, 'manifest.csv'), 'w', encoding='utf-8').write(
        'part,manufacturer,doc_type,url,filename,revision,sha256,retrieved,status,notes\n'
        'PARTY456,Acme,datasheet,https://example.invalid/y.pdf?productCode=C999002,PARTY456_datasheet.pdf,,,,ok,test\n')
    sch = os.path.join(hw, 'Power.kicad_sch')
    open(sch, 'w', encoding='utf-8').write(SCH % ': Per PARTY456 datasheet Figure 7-1, typical application')

    rc, o = run('scan', 'hardware', '--datasheets', 'docs/datasheets', '--out', 'reports/app_circuits')
    j = json.load(open(os.path.join(TMP, 'reports', 'app_circuits', 'app_circuits.json')))
    u1 = next((p for p in j['parts'] if p['refs'] == ['U1']), {})
    pages = [p for dd in u1.get('docs', []) for p in dd['pages']]
    ok(rc == 0 and u1.get('sheets') == ['Power'], 'U1 PARTY456 matched on sheet Power (R1, #PWR not reported)', o)
    ok([p['page'] for p in pages] == [1], 'only page 1 is a hit: not the contents, the graph conditions or the notice', pages)
    ok(pages and any('Figure 7-1. Typical Application Circuit' in c for c in pages[0]['captions'])
       and os.path.isfile(os.path.join(TMP, 'reports', 'app_circuits', pages[0]['png'])), 'caption kept, page image rendered', pages)

    rc, o = run('scan', 'hardware', '--datasheets', 'docs/datasheets', '--out', 'reports/app_circuits', '--write-review')
    rf = os.path.join(TMP, 'reports', 'app_circuits.json')
    rv = json.load(open(rf))
    ok(rc == 0 and rv['parts'][0]['status'] == 'pending', '--write-review: U1 pending', rv)
    rc, o = run('check', 'hardware')
    ok(rc == 1 and 'not reviewed' in o, 'check FAILs while a part is pending', o)

    def set_entry(**kw):
        r = json.load(open(rf))
        r['parts'][0].update(kw)
        json.dump(r, open(rf, 'w'), indent=1)
    set_entry(status='followed', figure='PARTY456 Figure 7-1')
    rc, o = run('check', 'hardware')
    ok(rc == 0 and '0 FAIL, 0 WARN' in o, 'followed, figure cited by a note on the sheet: check passes', o)
    set_entry(figure='PARTY456 Figure 9-9')
    rc, o = run('check', 'hardware')
    ok(rc == 0 and 'WARN' in o and 'Figure 9-9' in o, 'a figure the sheet does not cite -> WARN', o)
    for kw, why in ((dict(status='deviated', figure='PARTY456 Figure 7-1', deviations=[]), 'deviated without deviations'),
                    (dict(status='n/a', note=''), 'n/a without a note'),
                    (dict(status='followed', figure=''), 'followed without figure')):
        set_entry(**kw)
        rc, o = run('check', 'hardware')
        ok(rc == 1, '%s -> FAIL' % why, o)
    set_entry(status='deviated', figure='PARTY456 Figure 7-1', deviations=[{'what': 'C2 omitted', 'why': 'calc/power.py'}])
    r = json.load(open(rf))
    r['reviewed'] = 'by the owner'
    json.dump(r, open(rf, 'w'), indent=1)
    man = os.path.join(ds, 'manifest.csv')
    txt = open(man, encoding='utf-8').read()
    open(man, 'w', encoding='utf-8').write(txt.replace(',,,,ok,test', ',,,,manual,test'))
    rc, o = run('scan', 'hardware', '--datasheets', 'docs/datasheets', '--out', 'reports/app_circuits', '--write-review')
    rv = json.load(open(rf))
    ok(rv['parts'][0]['status'] == 'deviated' and rv['parts'][0]['deviations'] and rv.get('reviewed') == 'by the owner',
       're-scan keeps the reviewed entry and the added fields; a manual-status document is scanned', rv)

    # ---- 1.6.0: evaluation-board comparison
    fds = os.path.normpath(os.path.join(HERE, '..', 'scripts', 'fetch_datasheets.py'))

    def frun(*args):
        r = subprocess.run([sys.executable, fds] + list(args), capture_output=True, text=True, encoding='utf-8',
                           errors='replace', cwd=TMP)
        return r.returncode, r.stdout + r.stderr
    d = fitz.open()
    d.new_page().insert_text((50, 72), '4 EVM Schematic\nFigure 4-1. PARTY456EVM Schematic\n', fontsize=9)
    d.save(os.path.join(ds, 'PARTY456_eval_board.pdf'))
    d = fitz.open()
    d.new_page().insert_text((50, 72), '1 Features\nA plain buffer with no application figure.\n', fontsize=9)
    d.save(os.path.join(ds, 'PLAIN7_datasheet.pdf'))
    with open(man, 'a', encoding='utf-8') as f:
        f.write('PARTY456,Acme,eval_board,https://example.invalid/evm.pdf,PARTY456_eval_board.pdf,,,,ok,test\n'
                'PLAIN7,Acme,datasheet,https://example.invalid/p7.pdf,PLAIN7_datasheet.pdf,,,,ok,test\n')
    t = open(sch, encoding='utf-8').read()
    t = t.replace(' (text_box', ' (symbol (lib_id "lib:PARTY") (at 90 50 0) (unit 1) (uuid "00000000-0000-0000-0000-000000000005")\n'
                  '  (property "Reference" "U2" (at 0 0 0)) (property "Value" "PLAIN7" (at 0 0 0)))\n (text_box', 1)
    open(sch, 'w', encoding='utf-8').write(t)
    rc, o = frun('check', man, '--kicad', 'hardware')
    ok(rc == 0 and 'NOTE 1 IC(s)' in o and 'PLAIN7' in o, 'fetch check without --eval-board: PASS with a NOTE for PLAIN7', o)
    rc, o = frun('check', man, '--kicad', 'hardware', '--eval-board')
    ok(rc == 1 and 'PLAIN7' in o and 'PARTY456 (' not in o, 'fetch check --eval-board: FAIL for PLAIN7 only', o)
    rc, o = frun('add', man, '--part', 'PLAIN7', '--doc-type', 'datasheet', '--none', 'x')
    ok(rc != 0, '--none refused for a datasheet row', o)
    rc, o = frun('add', man, '--part', 'PLAIN7', '--doc-type', 'eval_board', '--none', 'none published (example.invalid, 2026-11-13)')
    rc, o = frun('check', man, '--kicad', 'hardware', '--eval-board')
    ok(rc == 0, 'fetch check --eval-board: PASS once PLAIN7 has an eval_board "none" row', o)

    rc, o = run('check', 'hardware', '--eval-board')
    ok(rc == 1 and 'without the evaluation-board comparison' in o and 'PLAIN7 (U2): IC with no review entry' in o,
       'app check --eval-board on the old review: FAIL for U1 (no eval_board) and U2 (no entry)', o)
    rc, o = run('scan', 'hardware', '--datasheets', 'docs/datasheets', '--out', 'reports/app_circuits', '--write-review',
                '--eval-board')
    rv = json.load(open(rf))
    e1 = next(x for x in rv['parts'] if x['part'] == 'PARTY456')
    e2 = next((x for x in rv['parts'] if x['part'] == 'PLAIN7'), {})
    ok(any(p.startswith('PARTY456_eval_board.pdf p1') for p in e1['pages']) and e1['status'] == 'pending',
       'EVM schematic page found; U1 back to pending (new figure page)', e1)
    ok(e1.get('eval_board', {}).get('doc') == 'PARTY456_eval_board.pdf' and e2.get('eval_board', {}).get('doc', '').startswith('none: none published'),
       'eval_board.doc filled from the manifest: the EVM file for U1, "none: <reason>" for U2 (entry without a figure)', rv)

    def set_part(part, **kw):
        r = json.load(open(rf))
        next(x for x in r['parts'] if x['part'] == part).update(kw)
        json.dump(r, open(rf, 'w'), indent=1)
    set_part('PARTY456', status='followed', figure='PARTY456 Figure 7-1',
             eval_board={'doc': 'PARTY456_eval_board.pdf', 'differences': [{'what': 'R5 10k pull-up', 'pin': 'EN',
                                                                              'action': 'justified'}]})
    set_part('PLAIN7', status='n/a', note='no application figure; no eval board published')
    rc, o = run('check', 'hardware', '--eval-board')
    ok(rc == 1 and 'R5 10k pull-up' in o, 'a justified difference without why -> FAIL', o)
    set_part('PARTY456', eval_board={'doc': 'PARTY456_eval_board.pdf', 'differences': [
        {'what': 'R5 10k pull-up', 'pin': 'EN', 'action': 'added'},
        {'what': 'J1 jumper', 'pin': 'VIN', 'action': 'justified', 'why': 'lab-only part of the EVM'}]})
    rc, o = run('check', 'hardware', '--eval-board')
    ok(rc == 0 and '0 FAIL' in o, 'every difference added or justified: check --eval-board passes', o)
    set_part('PARTY456', eval_board={'doc': 'none'})
    rc, o = run('check', 'hardware')
    ok(rc == 1 and 'without the reason' in o, 'an existing eval_board record is checked without the flag ("none" alone -> FAIL)', o)

    print('\n%d passed, %d failed' % (PASS, FAIL))
    if not FAIL:
        shutil.rmtree(TMP, ignore_errors=True)
    else:
        print('kept ' + TMP)
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
