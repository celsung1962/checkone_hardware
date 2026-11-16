#!/usr/bin/env python
"""audit_gate.py - the NEW-FAIL gate (1.27.0): a board change is accepted only if it adds no audit FAIL.

Why: on ServiceOne rev. 0.2 (D133, 2026-10-21) the ADC region was re-placed and re-routed under a gate that only
asked "did the board's total FAIL count go down?". The rip-up removed 357 old FAILs, which hid 220 new ones
(93 between-pads, 82 pad-entry, 31 via - two of them inside pads - and 6 acute joints). A total count over a board
that carries hundreds of known FAILs measures nothing about the change. Compare the findings themselves.

A finding's identity is its check plus its message with the measured numbers blanked (coordinates, distances,
angles), so a pre-existing FAIL on copper that only moved keeps its identity, and a FAIL of the same kind on a new
pad pair, a new net or a new check is new. Identities are counted: two vias-in-pad where the baseline had one is one
new FAIL. Net names (+3.3VA, -24V), references (R111-2) and layer names keep their digits.

Usage (system Python; node must be installed):
    audit_gate.py <baseline> <result> [--params FILE] [--json OUT] [--quiet]
<baseline> / <result>: a .kicad_pcb (audited here) or a kicad_audit.js --json report. Exit 0: no new FAIL;
1: new FAILs (listed); 2: usage / audit error.

As a module (the gated drivers): audit(pcb, out, params=None) -> findings; new_fails(base, cur) -> list.
"""
import collections
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
AUD = os.path.join(HERE, 'kicad_audit.js')
# a number that is not part of a name: not after a letter, digit, '_', '+', '-', '.', and not followed by a letter
# (3.3VA, 24V_SW) - so "R111-2", "+3.3VA", "-3.3VA", "In1.Cu" survive and "@ -27.45,-18.9", "0.575 mm" do not
_NUM = re.compile(r'(?<![A-Za-z0-9_+\-.])-?\d+(?:\.\d+)?(?![\d.]*[A-Za-z_])')


def identity(f):
    return (f['check'], _NUM.sub('#', f['msg']))


def audit(pcb, out, params=None, sch=False):
    """Run kicad_audit.js on PCB, write the JSON to OUT, return the findings."""
    if params is None:
        p = os.path.join(os.path.dirname(os.path.abspath(pcb)), 'kicad_golden.project.json')
        params = p if os.path.exists(p) else None
    cmd = ['node', AUD, os.path.abspath(pcb), '--json', os.path.abspath(out), '--quiet'] + ([] if sch else ['--no-sch'])
    if params:
        cmd += ['--params', os.path.abspath(params)]
    subprocess.run(cmd, capture_output=True, cwd=os.path.expanduser('~'))     # node wants a short cwd on Windows
    if not os.path.exists(out):
        raise RuntimeError('kicad_audit.js wrote no report for %s' % pcb)
    return json.load(open(out, encoding='utf-8'))['findings']


def fail_ids(findings):
    return collections.Counter(identity(f) for f in findings if f['level'] == 'FAIL')


def new_fails(base, cur):
    """FAIL findings of CUR whose identity occurs more often than in BASE (findings lists or Counters)."""
    b = base if isinstance(base, collections.Counter) else fail_ids(base)
    seen = collections.Counter()
    out = []
    for f in cur:
        if f['level'] != 'FAIL':
            continue
        i = identity(f)
        seen[i] += 1
        if seen[i] > b.get(i, 0):
            out.append(f)
    return out


def _load(arg, tag, params):
    if arg.lower().endswith('.json'):
        return json.load(open(arg, encoding='utf-8'))['findings']
    out = os.path.join(tempfile.gettempdir(), '%s.gate_%s.audit.json' % (os.path.splitext(os.path.basename(arg))[0], tag))
    return audit(arg, out, params)


if __name__ == '__main__':
    a = sys.argv[1:]
    if len(a) < 2 or a[0].startswith('--'):
        sys.stderr.write(__doc__)
        sys.exit(2)
    opt = lambda n: a[a.index(n) + 1] if n in a else None
    try:
        base, cur = _load(a[0], 'base', opt('--params')), _load(a[1], 'result', opt('--params'))
    except (OSError, RuntimeError, ValueError) as e:
        sys.stderr.write('audit_gate: %s\n' % e)
        sys.exit(2)
    new = new_fails(base, cur)
    gone = new_fails(cur, base)
    nb, nc = sum(f['level'] == 'FAIL' for f in base), sum(f['level'] == 'FAIL' for f in cur)
    if opt('--json'):
        json.dump({'baseline_fail': nb, 'result_fail': nc, 'new': new, 'removed': len(gone)},
                  open(opt('--json'), 'w', encoding='utf-8'), indent=1)
    print('audit FAIL %d -> %d: %d new, %d removed' % (nb, nc, len(new), len(gone)))
    if new:
        by = collections.Counter(f['check'] for f in new)
        print('NEW FAILs by check: ' + ', '.join('%s %d' % kv for kv in by.most_common()))
        if '--quiet' not in a:
            for f in new:
                print('  [%s] %s' % (f['check'], f['msg']))
        print('result: BLOCKED - the change adds %d FAIL(s); a lower total does not excuse them' % len(new))
        sys.exit(1)
    print('result: PASS - no new FAIL')
