#!/usr/bin/env python
"""run_all.py - run every test suite of the skill and report one result.

    python tests/run_all.py [--strict] [--kicad-python PATH] [--only NAME ...]

Each suite runs in its own process with the interpreter it needs: node for run_tests.js, this Python
for the pure suites, KiCad's Python (--kicad-python, KICAD_PYTHON, then the usual install paths) for the
pcbnew suites. Exit 0 only when every suite exits 0.

--strict also fails a suite that skipped anything ("SKIP ..." or a "not found ... skipped" line). The
suites skip quietly when KiCad, kicad-cli, node or PyMuPDF is missing, so without --strict a machine
without KiCad passes with half the checks unrun. CI runs with --strict.

The suites write only to tests/fixtures*/ outputs that are git-ignored and to temporary folders, so a
clean checkout stays clean: CI checks this with `git status --porcelain` after the run.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'scripts'))
import kicad_sexp as KS  # noqa: E402

# (suite, interpreter): 'node', 'py' = this Python, 'kicad' = KiCad's Python
SUITES = [
    ('run_tests.js', 'node'),
    ('run_tests_py.py', 'py'),
    ('run_tests_boards.py', 'py'),
    ('run_tests_phased.py', 'py'),
    ('run_tests_rules.py', 'py'),
    ('run_tests_guard.py', 'py'),
    ('run_tests_planeplan.py', 'py'),
    ('run_tests_padrow.py', 'py'),
    ('run_tests_datasheet.py', 'py'),
    ('run_tests_kicad.py', 'kicad'),
    ('run_tests_axial.py', 'kicad'),
    ('run_tests_fanout.py', 'kicad'),
    ('run_tests_models.py', 'kicad'),
    ('run_tests_gate_tools.py', 'kicad'),
]
# A suite that cannot run part of itself says so with "SKIP ..." or "... not found / not importable ... skip(ped)".
# Other lines may contain the word (an option name, a tool reporting that it skipped a locked track) and are not skips.
SKIP_LINE = re.compile(r'^\s*SKIP\b|(?i:skip.*not (found|importable)|not (found|importable).*skip)')
RESULT_LINE = re.compile(r'^\s*(PASS|FAIL|ok)\b')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--strict', action='store_true', help='fail a suite that skipped any check')
    ap.add_argument('--kicad-python', help="interpreter with pcbnew (default: KICAD_PYTHON, then the usual paths)")
    ap.add_argument('--only', nargs='+', metavar='NAME', help='run only these suites (file names)')
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')   # suite output is not always ASCII
    except AttributeError:
        pass

    node = shutil.which('node')
    kp = KS.find_kicad_python(a.kicad_python)
    if kp and not os.path.isfile(kp):
        kp = None
    interp = {'node': node, 'py': sys.executable, 'kicad': kp}
    env = dict(os.environ)
    if kp:
        env.setdefault('KICAD_PYTHON', kp)
    print('node          %s' % (node or 'NOT FOUND'))
    print('python        %s' % sys.executable)
    print('KiCad python  %s' % (kp or 'NOT FOUND'))
    print('kicad-cli     %s\n' % (shutil.which('kicad-cli') or 'not on PATH'))

    rows, bad = [], 0
    for name, kind in SUITES:
        if a.only and name not in a.only:
            continue
        exe = interp[kind]
        if not exe:
            rows.append((name, 'MISSING', '%s interpreter not found' % kind, 0.0))
            bad += 1
            continue
        t0 = time.time()
        p = subprocess.run([exe, os.path.join(HERE, name)], cwd=os.path.dirname(HERE), env=env,
                           capture_output=True, text=True, encoding='utf-8', errors='replace')
        dt = time.time() - t0
        out = (p.stdout or '') + (p.stderr or '')
        lines = [l for l in out.splitlines() if l.strip()]
        skips = [l.strip() for l in lines if SKIP_LINE.search(l) and not RESULT_LINE.match(l)]
        fails = [l.strip() for l in lines if l.lstrip().startswith('FAIL')]
        last = lines[-1].strip() if lines else ''
        if p.returncode != 0:
            status = 'FAIL'
        elif skips and a.strict:
            status = 'SKIPPED'
        else:
            status = 'ok'
        if status != 'ok':
            bad += 1
            print('---- %s (exit %d)' % (name, p.returncode))
            for l in (fails + skips)[:20] or lines[-20:]:
                print('    ' + l)
        rows.append((name, status, last[:70] + ('  [%d skip]' % len(skips) if skips else ''), dt))

    print('\n%-26s %-8s %7s  %s' % ('suite', 'result', 'time', 'last line'))
    for name, status, last, dt in rows:
        print('%-26s %-8s %6.1fs  %s' % (name, status, dt, last))
    print('\n%d of %d suites OK%s' % (len(rows) - bad, len(rows), '' if not bad else ' - FAILED'))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
