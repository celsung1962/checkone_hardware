#!/usr/bin/env python
"""run_tests_datasheet.py - self-test for the datasheet layout scan before routing (playbook B0, 1.26.0).

System Python with PyMuPDF (fitz) for the scan and the test PDF; KiCad's Python for the board, node for the audit.
Skipped when either is missing.

The test datasheet PARTX123 has a table of contents that lists "10.1 Layout Guidelines ..... 2" (page 1), the layout
section (page 2: bypass capacitor as close as possible, Kelvin connection, digital traces away from the inputs) and a
land pattern page (page 3). The board has U1 = PARTX123 (LCSC C999001), C1 and R1 (no document needed).

  scan            U1 matched through the manifest; page 2 "guidelines" with the three rule sentences and a page image;
                  the table of contents is not a hit; page 3 is "land pattern"; R1 / C1 are not reported missing
  --write-params  datasheet_layout block: U1 pending; a second scan keeps an entry marked applied
  audit           no block -> WARN pre-flight; pending -> FAIL pre-flight; applied with a rule -> INFO, no FAIL
  route_freerouting.py --export-only  pending -> refused (exit 4); --skip-datasheet-review passes the gate
  layout_measure.py check --pre-route  decoupling U1.1 - C1.1 (3.5 mm) judged by straight distance: max 4 PASS, max 1 FAIL
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCR = os.path.normpath(os.path.join(HERE, '..', 'scripts'))
sys.path.insert(0, SCR)
import kicad_sexp as KS  # noqa: E402

PASS = FAIL = 0
TMP = tempfile.mkdtemp(prefix='kr_dslayout_')
KP = KS.find_kicad_python()

BOARD = r'''
import os, sys, pcbnew
out = sys.argv[1]
base = None
for b_ in (r"C:\Program Files\KiCad\10.0\share\kicad\footprints", "/usr/share/kicad/footprints",
           "/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"):
    if os.path.isdir(os.path.join(b_, "Package_SO.pretty")):
        base = b_
b = pcbnew.BOARD(); b.SetCopperLayerCount(2)
def mm(v): return pcbnew.FromMM(v)
def V(x, y): return pcbnew.VECTOR2I(mm(x), mm(y))
for a, c in (((0, 0), (40, 0)), ((40, 0), (40, 30)), ((40, 30), (0, 30)), ((0, 30), (0, 0))):
    s = pcbnew.PCB_SHAPE(b); s.SetShape(pcbnew.SHAPE_T_SEGMENT); s.SetLayer(pcbnew.Edge_Cuts)
    s.SetStart(V(*a)); s.SetEnd(V(*c)); b.Add(s)
n = pcbnew.NETINFO_ITEM(b, "VDD"); b.Add(n)
for ref, lib, name, x, y, val, lcsc in (("U1", "Package_SO", "SOIC-8_3.9x4.9mm_P1.27mm", 15, 15, "PARTX123", "C999001"),
                                         ("C1", "Capacitor_SMD", "C_0603_1608Metric", 15, 10, "100nF", "C14663"),
                                         ("R1", "Resistor_SMD", "R_0603_1608Metric", 25, 15, "10K", "C25804")):
    fp = pcbnew.FootprintLoad(os.path.join(base, lib + ".pretty"), name); b.Add(fp)
    fp.SetReference(ref); fp.SetValue(val); fp.SetPosition(V(x, y))
    f = pcbnew.PCB_FIELD(fp, pcbnew.FIELD_T_USER, "LCSC") if hasattr(pcbnew, "FIELD_T_USER") else None
    try:
        fp.SetField("LCSC", lcsc)
    except Exception:
        if f is not None:
            f.SetText(lcsc); fp.Add(f)
    for p in fp.Pads():
        if (ref, p.GetNumber()) in (("U1", "1"), ("C1", "1")):
            p.SetNet(n)
b.Save(out)
'''


def ok(cond, name, extra=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print('  ok   ' + name)
    else:
        FAIL += 1
        print('  FAIL ' + name + (('\n       ' + str(extra)[-1500:]) if extra else ''))


def run(args, **kw):
    r = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', errors='replace', **kw)
    return r.returncode, '\n'.join(l for l in (r.stdout + r.stderr).splitlines()
                                   if 'image handler' not in l and 'memory leak' not in l)


def make_pdf(path):
    import fitz
    d = fitz.open()
    pages = [
        "PARTX123 Precision Widget\nTable of Contents\n1 Features ......................... 1\n"
        "5 Specifications ................... 1\n10 Layout ......................... 2\n"
        "10.1 Layout Guidelines .................. 2\n10.2 Layout Example ................. 2\n"
        "11 Mechanical ...................... 3\n",
        "10 Layout\n10.1 Layout Guidelines\nPlace the bypass capacitor as close as possible to the VDD pin using short,\n"
        "direct traces. Connect IN+ and IN- to the sense resistor with a Kelvin connection.\n"
        "Route digital traces away from the analog inputs.\nThe device is rated from -40 C to 125 C.\n"
        "10.2 Layout Example\n[figure: bypass capacitor next to pin 1, via to ground plane]\n",
        "11 Mechanical\nRecommended Land Pattern\nSolder pad dimensions and stencil openings for the SOIC-8 footprint.\n",
    ]
    for t in pages:
        p = d.new_page()
        p.insert_text((50, 72), t, fontsize=9)
    d.save(path)


def audit(pcb):
    j = pcb + '.audit.json'
    run(['node', os.path.join(SCR, 'kicad_audit.js'), pcb, '--no-sch', '--quiet', '--json', j])
    a = json.load(open(j))
    return [f for f in a['findings'] if f['check'] == 'pre-flight' and 'datasheet' in f['msg']]


def main():
    try:
        import fitz  # noqa: F401
    except ImportError:
        print('PyMuPDF not found - datasheet scan tests skipped')
        return 0
    if not KP:
        print('KiCad Python not found - datasheet scan tests skipped')
        return 0
    print('datasheet_layout_scan.py')
    ds = os.path.join(TMP, 'datasheets')
    os.makedirs(ds)
    make_pdf(os.path.join(ds, 'PARTX123_datasheet.pdf'))
    open(os.path.join(ds, 'manifest.csv'), 'w', encoding='utf-8').write(
        'part,manufacturer,doc_type,url,filename,revision,sha256,retrieved,status,notes\n'
        'PARTX123,Acme,datasheet,https://example.invalid/x.pdf?productCode=C999001,PARTX123_datasheet.pdf,,,,ok,test\n')
    hw = os.path.join(TMP, 'hw')
    os.makedirs(hw)
    pcb = os.path.join(hw, 'b.kicad_pcb')
    open(os.path.join(TMP, 'board.py'), 'w').write(BOARD)
    rc, o = run([KP, os.path.join(TMP, 'board.py'), pcb])
    if rc:
        ok(False, 'test board built', o)
        return 1
    open(os.path.join(hw, 'b.kicad_pro'), 'w').write('{}\n')
    json.dump({'fabricator': {'layers': 2, 'profile': '2L-1oz'}}, open(os.path.join(hw, 'kicad_golden.project.json'), 'w'))
    sc = os.path.join(SCR, 'datasheet_layout_scan.py')
    out = os.path.join(TMP, 'out')
    rc, o = run([sys.executable, sc, pcb, '--datasheets', ds, '--out', out])
    j = json.load(open(os.path.join(out, 'datasheet_layout.json'))) if os.path.isfile(os.path.join(out, 'datasheet_layout.json')) else {}
    u1 = next((p for p in j.get('parts', []) if p['refs'] == ['U1']), None)
    pages = {p['page']: p for d in (u1 or {}).get('docs', []) for p in d['pages']}
    ok(rc == 0 and u1 is not None, 'U1 PARTX123 matched to its datasheet through the manifest', o)
    ok(2 in pages and pages[2]['cls'] in ('guidelines', 'example') and 1 not in pages,
       'page 2 is the layout section; the table of contents (page 1) is not a hit', pages)
    rules = ' | '.join(pages.get(2, {}).get('rules', []))
    ok('as close as possible' in rules and 'Kelvin' in rules and 'away from the analog inputs' in rules and 'rated from' not in rules,
       'the three layout rule sentences are extracted, not the temperature line', rules)
    ok(pages.get(3, {}).get('cls') == 'land pattern', 'page 3 is classed land pattern (footprint check only)', pages.get(3))
    ok(pages.get(2, {}).get('png') and os.path.isfile(os.path.join(out, pages[2]['png'])), 'the layout page is rendered as an image', pages.get(2))
    ok(not j.get('missing'), 'C1 / R1 need no document (only U, PS, Q, Y, L parts are reported missing)', j.get('missing'))

    f = audit(pcb)
    ok(any(x['level'] == 'WARN' and 'no datasheet layout review' in x['msg'] for x in f), 'audit: no review on record -> WARN pre-flight', f)
    rc, o = run([sys.executable, sc, pcb, '--datasheets', ds, '--out', out, '--write-params'])
    pj = os.path.join(hw, 'kicad_golden.project.json')
    p = json.load(open(pj))
    ent = (p.get('datasheet_layout') or {}).get('parts', [])
    ok(rc == 0 and len(ent) == 1 and ent[0]['part'] == 'PARTX123' and ent[0]['status'] == 'pending' and p['fabricator']['layers'] == 2,
       '--write-params: datasheet_layout block with U1 pending, other params kept', p)
    f = audit(pcb)
    ok(any(x['level'] == 'FAIL' and 'not reviewed' in x['msg'] and 'PARTX123' in x['msg'] for x in f), 'audit: pending part -> FAIL pre-flight', f)
    rc, o = run([KP, os.path.join(SCR, 'route_freerouting.py'), pcb, '--export-only', '--outdir', os.path.join(TMP, 'fr')])
    ok(rc == 4 and 'REFUSED' in o, 'route_freerouting.py refuses to export while a part is pending (exit 4)', o)
    rc, o = run([KP, os.path.join(SCR, 'route_freerouting.py'), pcb, '--export-only', '--skip-datasheet-review', '--outdir', os.path.join(TMP, 'fr')])
    ok('REFUSED' not in o, '--skip-datasheet-review passes the gate', o)

    ent[0]['status'] = 'applied'
    ent[0]['rules'] = [{'rule': 'bypass capacitor as close as possible to VDD', 'source': 'PARTX123_datasheet.pdf p.2',
                        'applied_as': 'layout_checks.decoupling U1.1-C1.1 max 4 mm'}]
    p['layout_checks'] = {'decoupling': [{'pin': 'U1.1', 'cap': 'C1.1', 'max_mm': 4, 'why': 'PARTX123 10.1'}]}
    json.dump(p, open(pj, 'w'), indent=1)
    f = audit(pcb)
    ok(not any(x['level'] == 'FAIL' for x in f) and any(x['level'] == 'INFO' and '1 part(s) applied' in x['msg'] for x in f),
       'audit: reviewed (applied with a rule) -> INFO, no FAIL', f)
    p = json.load(open(pj))
    p['datasheet_layout']['reviewed'] = '2026-10-21 (review report)'
    json.dump(p, open(pj, 'w'), indent=1)
    rc, o = run([sys.executable, sc, pcb, '--datasheets', ds, '--out', out, '--write-params'])
    blk = json.load(open(pj))['datasheet_layout']
    ent2 = blk['parts']
    ok(ent2[0]['status'] == 'applied' and ent2[0]['rules'] and blk.get('reviewed') == '2026-10-21 (review report)',
       'a second scan keeps the reviewed entry and the fields the review added', blk)
    man = os.path.join(ds, 'manifest.csv')
    txt = open(man, encoding='utf-8').read()
    open(man, 'w', encoding='utf-8').write(txt.replace(',,,,ok,test', ',,,,manual,test'))
    rc, o = run([sys.executable, sc, pcb, '--datasheets', ds, '--out', os.path.join(TMP, 'out2')])
    ok('1 part(s) with a document' in o, 'a document imported by hand (manifest status manual) is scanned too', o)

    print('layout_measure.py check --pre-route')
    lm = os.path.join(SCR, 'layout_measure.py')
    rc, o = run([KP, lm, 'check', pcb, '--pre-route'])
    ok(rc == 0 and 'decoupling-placement' in o and '"pass": true' in o, 'U1.1 - C1.1 3.5 mm apart in a straight line, max 4: PASS', o)
    p = json.load(open(pj))
    p['layout_checks']['decoupling'][0]['max_mm'] = 1
    json.dump(p, open(pj, 'w'), indent=1)
    rc, o = run([KP, lm, 'check', pcb, '--pre-route'])
    ok(rc == 1 and '"pass": false' in o, 'max 1 mm: FAIL before routing (move the capacitor)', o)

    print('\n%d passed, %d failed' % (PASS, FAIL))
    if not FAIL:
        shutil.rmtree(TMP, ignore_errors=True)
    else:
        print('kept ' + TMP)
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
