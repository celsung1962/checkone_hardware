#!/usr/bin/env python3
"""Self-test for scripts/check_structure.py: small synthetic schematics, one rule each.
Run: python tests/run_tests_structure.py   (exit 0 = all pass)"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'scripts'))
import check_structure as CS  # noqa: E402

LIB = '''(lib_symbols
 (symbol "Device:R" (pin_numbers (hide yes)) (property "Reference" "R" (at 0 0 0)) (property "Value" "R" (at 0 0 0))
  (symbol "R_0_1" (rectangle (start -1 -2.5) (end 1 2.5)))
  (symbol "R_1_1" (pin passive line (at 0 3.81 270) (length 1.27) (number "1")) (pin passive line (at 0 -3.81 90) (length 1.27) (number "2"))))
 (symbol "Conn:J2" (property "Reference" "J" (at 0 0 0)) (property "Value" "J" (at 0 0 0))
  (symbol "J2_0_1" (rectangle (start -2.54 2.54) (end 2.54 -2.54)))
  (symbol "J2_1_1" (pin passive line (at -5.08 0 0) (length 2.54) (number "1"))))
 (symbol "power:GND" (power) (pin_numbers (hide yes)) (property "Reference" "#PWR" (at 0 0 0)) (property "Value" "GND" (at 0 0 0))
  (symbol "GND_0_1" (polyline (pts (xy 0 0) (xy 0 -1.27) (xy 1.27 -1.27) (xy 0 -2.54) (xy -1.27 -1.27) (xy 0 -1.27))))
  (symbol "GND_1_1" (pin power_in line (at 0 0 270) (length 0) (number "1"))))
 (symbol "power:PWR_FLAG" (power) (pin_numbers (hide yes)) (property "Reference" "#FLG" (at 0 0 0)) (property "Value" "PWR_FLAG" (at 0 0 0))
  (symbol "PWR_FLAG_0_1" (polyline (pts (xy 0 0) (xy 0 1.27) (xy -1.016 1.905) (xy 0 2.54) (xy 1.016 1.905) (xy 0 1.27))))
  (symbol "PWR_FLAG_1_1" (pin power_out line (at 0 0 90) (length 0) (number "1")))))'''


def sym(lib, ref, val, x, y, rot=0, extra=''):
    return (f'(symbol (lib_id "{lib}") (at {x} {y} {rot}) (unit 1) {extra}'
            f'(property "Reference" "{ref}" (at {x + 2} {y} 0)) (property "Value" "{val}" (at {x + 2} {y + 2} 0)))')


def sch(body, title_comment='', paper='A3'):
    tb = f'(title_block (title "t") (comment 1 "{title_comment}"))' if title_comment else ''
    return f'(kicad_sch (version 20250114) (generator "eeschema") (paper "{paper}") {tb} {LIB} {body})'


def run(files, root='root.kicad_sch'):
    d = tempfile.mkdtemp()
    for n, t in files.items():
        open(os.path.join(d, n), 'w', encoding='utf-8').write(t)
    return CS.check(os.path.join(d, root))


def has(fs, check, level=None):
    return any(f['check'] == check and (level is None or f['level'] == level) for f in fs)


CHILD_OK = sch('(hierarchical_label "A" (shape input) (at 10 20 180))')
TESTS = []


def test(fn):
    TESTS.append(fn); return fn


@test
def sheet_without_pins_fails():
    root = sch('(sheet (at 20 20) (size 20 10) (property "Sheetname" "P" (at 20 19 0)) (property "Sheetfile" "c.kicad_sch" (at 20 31 0)))')
    assert has(run({'root.kicad_sch': root, 'c.kicad_sch': CHILD_OK}), 'sheet-no-pins', 'FAIL')


@test
def sheet_with_rails_text_passes():
    root = sch('(sheet (at 20 20) (size 20 10) (property "Sheetname" "P" (at 20 19 0)) (property "Sheetfile" "c.kicad_sch" (at 20 31 0)))'
               '(text "in: +24V - out: +5V" (at 21 25 0))')
    assert not has(run({'root.kicad_sch': root, 'c.kicad_sch': CHILD_OK}), 'sheet-no-pins')


@test
def sheet_pin_on_no_connect_fails():
    root = sch('(sheet (at 20 20) (size 20 10) (property "Sheetname" "P" (at 20 19 0)) (property "Sheetfile" "c.kicad_sch" (at 20 31 0))'
               ' (pin "A" input (at 40 25 0))) (no_connect (at 40 25))')
    assert has(run({'root.kicad_sch': root, 'c.kicad_sch': CHILD_OK}), 'pin-no-connect', 'FAIL')


@test
def text_only_ports_block_fails():
    child = sch('(text_box "SHEET PORTS\\nA in, B out" (at 10 10) (size 40 10))')
    assert has(run({'root.kicad_sch': child}), 'ports-text-only', 'FAIL')


@test
def ports_block_with_labels_passes():
    child = sch('(text_box "SHEET PORTS" (at 10 10) (size 30 5)) (hierarchical_label "A" (shape input) (at 20 20 180))')
    assert not has(run({'root.kicad_sch': child}), 'ports-text-only')


@test
def sideways_ground_fails_and_down_ground_passes():
    bad = sch(sym('power:GND', '#PWR01', 'GND', 50, 50, 90))
    good = sch(sym('power:GND', '#PWR01', 'GND', 50, 50, 0))
    assert has(run({'root.kicad_sch': bad}), 'power-sideways', 'FAIL')
    assert not has(run({'root.kicad_sch': good}), 'power-sideways')


@test
def two_pwr_flags_on_one_net_fail():
    body = (sym('power:GND', '#PWR01', 'GND', 50, 50) + sym('power:PWR_FLAG', '#FLG01', 'PWR_FLAG', 50, 40)
            + sym('power:PWR_FLAG', '#FLG02', 'PWR_FLAG', 60, 40)
            + '(wire (pts (xy 50 40) (xy 50 50))) (wire (pts (xy 50 40) (xy 60 40)))')
    assert has(run({'root.kicad_sch': sch(body)}), 'pwr-flag-count', 'FAIL')


@test
def label_on_connector_pin_fails_but_not_on_resistor():
    body = sym('Conn:J2', 'J1', 'J', 50, 50) + '(label "X" (at 44.92 50 180))'
    assert has(run({'root.kicad_sch': sch(body)}), 'label-on-pin', 'FAIL')
    body = sym('Device:R', 'R1', '10k', 50, 50) + '(label "X" (at 50 46.19 0))'
    assert not has(run({'root.kicad_sch': sch(body)}), 'label-on-pin')


@test
def long_value_warns():
    assert has(run({'root.kicad_sch': sch(sym('Device:R', 'R1', 'RC0402FR-0710KL', 50, 50))}), 'long-value', 'WARN')
    assert not has(run({'root.kicad_sch': sch(sym('Device:R', 'R1', '10k', 50, 50))}), 'long-value')


@test
def reference_order_warns():
    body = sym('Device:R', 'R1', '1k', 60, 50) + sym('Device:R', 'R2', '1k', 50, 50)
    assert has(run({'root.kicad_sch': sch(body)}), 'ref-order', 'WARN')


@test
def long_note_and_title_remark_warn():
    body = '(text "' + 'x' * 450 + '" (at 20 20 0))'
    fs = run({'root.kicad_sch': sch(body, 'Generated by gen; do not edit by hand')})
    assert has(fs, 'long-note', 'WARN') and has(fs, 'title-process', 'WARN')


@test
def paper_size_a3_required():
    assert has(run({'root.kicad_sch': sch('', paper='A4')}), 'paper-size', 'FAIL')
    assert not has(run({'root.kicad_sch': sch('', paper='A3')}), 'paper-size')
    assert has(run({'root.kicad_sch': sch('', paper='A2')}), 'paper-size', 'WARN')


if __name__ == '__main__':
    bad = 0
    for t in TESTS:
        try:
            t(); print('PASS', t.__name__)
        except AssertionError as e:
            bad += 1; print('FAIL', t.__name__, e)
    print(f'{len(TESTS) - bad}/{len(TESTS)} passed')
    sys.exit(1 if bad else 0)
