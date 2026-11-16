#!/usr/bin/env python
"""refinish_gated.py - realign pad entries with route_finish.py --refinish, one pad at a time, every attempt gated by
KiCad DRC and the audit (lessons L10 / L11, ServiceOne review issues 6 and 18).

The pads come from the audit's pad-entry FAILs (non-axial entry, last bend closer than 0.5 mm to the pad edge, track
end off the pad centre, staircase, entry wider than the pad), or from --pads. For each pad route_finish.py --refinish
is run; a pad with several non-axial entries is run again until none is left (up to --tries, default 4). An attempt
is KEPT only if the DRC error + unconnected count does not rise, the audit's total FAIL count falls and the audit has
no NEW FAIL (1.27.0, audit_gate.py: an acute joint or a via in a pad elsewhere is not paid for by one fixed entry); otherwise the
board is restored from the copy taken just before. With layout_checks in the project parameters, a check that passed
at the start and now fails also reverts the attempt (as finish_gated.py). Kelvin pads (layout_checks.kelvin sense /
shunt) are skipped unless named in --pads.

1.28.0: the stop rule (L30, stop_rule.py: --budget MIN, --min-keep-rate R, --no-stop-rule) ends a run that keeps
fewer than 1 in 5 attempts after 10 attempts or 30 min; an attempt that moves, changes or removes a locked track or
via is reverted (L40, locks.py); --box / --exclude-box x0,y0,x1,y1 keep the pass to (or away from) an area, such as a
region left for the designer (L37). Run a sample (--max 10) before a board-wide pass: on a routed board most refusals
are plane vias inside the stub zone, which via_axis.py relocates first (L38).

What it cannot do (ServiceOne rev. D, 30 pads tried, 8 kept: audit FAIL 1947 -> 1937, DRC unchanged): move a via
that sits inside the stub zone (pad edge + 0.5 mm), free a pad axis blocked by other copper, or route around parts
without passing between foreign pads. Those entries need the via or the neighbouring track moved first - the
refusal messages say which. --block-courtyards made it worse there (3 kept) and is not passed by default.

Usage (system Python; KiCad installed):
    refinish_gated.py <board.kicad_pcb> [--pads R1.2,U3.4 | --max N] [--tries 4] [--params FILE] [--log FILE]
                      [--box x0,y0,x1,y1] [--exclude-box x0,y0,x1,y1] [--budget MIN] [--min-keep-rate R]
                      [--no-stop-rule] [--no-layout-gate] [--kicad-python PATH] [--kicad-cli PATH] [--force-write] [-- ROUTE_FINISH_ARGS]
Arguments after "--" go to route_finish.py (default: --grid 0.05 --safety 0.05). The board is modified in place;
a backup <board>.bak_prerefinish is written first. Close KiCad (board_guard.py).
"""
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kicad_sexp as KS  # noqa: E402
import board_guard  # noqa: E402
import audit_gate  # noqa: E402
import locks  # noqa: E402
import stop_rule  # noqa: E402

argv = sys.argv[1:]
if '--' in argv:
    RF_EXTRA = argv[argv.index('--') + 1:]
    argv = argv[:argv.index('--')]
else:
    RF_EXTRA = ['--grid', '0.05', '--safety', '0.05']
if not argv or argv[0].startswith('-'):
    print(__doc__)
    sys.exit(2)


def opt(n, d=None):
    return argv[argv.index(n) + 1] if n in argv else d


PCB = os.path.abspath(argv[0])
board_guard.check_board_writable(PCB, argv=argv[1:], script='refinish_gated.py')
KP = KS.find_kicad_python(opt('--kicad-python'))
CLI = KS.find_kicad_cli(opt('--kicad-cli'))
if not KP or not CLI:
    sys.exit('need KiCad\'s python (%s) and kicad-cli (%s); pass --kicad-python / --kicad-cli' % (KP, CLI))
PARAMS = opt('--params') or os.path.join(os.path.dirname(PCB), 'kicad_golden.project.json')
params = json.load(open(PARAMS, encoding='utf-8')) if os.path.isfile(PARAMS) else {}
LOG = open(opt('--log'), 'w', encoding='utf-8') if opt('--log') else None
TMP = PCB + '.refinish_tmp'
ENV = dict(os.environ, MSYS_NO_PATHCONV='1')


def say(m):
    print(m)
    if LOG:
        LOG.write(m + '\n')
        LOG.flush()


def drc():
    j = TMP + '.drc.json'
    subprocess.run([CLI, 'pcb', 'drc', '--format', 'json', '-o', j, PCB], capture_output=True)
    d = json.load(open(j, encoding='utf-8'))
    return sum(1 for v in d['violations'] if v['severity'] == 'error') + len(d.get('unconnected_items', []))


def audit():
    j = TMP + '.audit.json'
    cmd = ['node', os.path.join(HERE, 'kicad_audit.js'), PCB, '--no-sch', '--quiet', '--json', j]
    if os.path.isfile(PARAMS):
        cmd[3:3] = ['--params', PARAMS]
    subprocess.run(cmd, capture_output=True)
    return json.load(open(j, encoding='utf-8'))


def layout_passing():
    if '--no-layout-gate' in argv or not (params.get('layout_checks') or {}):
        return None
    j = TMP + '.layout.json'
    subprocess.run([KP, os.path.join(HERE, 'layout_measure.py'), 'check', PCB, '--params', PARAMS, '--json', j],
                   capture_output=True, env=ENV)
    try:
        res = json.load(open(j, encoding='utf-8'))
    except (OSError, ValueError):
        return None
    rows = res if isinstance(res, list) else res.get('results', [])
    return {json.dumps({k: v for k, v in r.items() if k in ('check', 'sense', 'shunt', 'load', 'pad', 'a', 'b')},
                       sort_keys=True) for r in rows if r.get('pass')}


def _box(n):
    v = opt(n)
    return tuple(float(x) for x in v.split(',')) if v else None


BOX, XBOX = _box('--box'), _box('--exclude-box')
inbox = lambda b, x, y: b[0] <= x <= b[2] and b[1] <= y <= b[3]
RE_AT = re.compile(r'@ ?(-?[\d.]+),(-?[\d.]+)')
RE_PAD = re.compile(r'(?:into (?:elongated )?pad|before pad|centre of pad|staircase \(jog inside the clearance area\) '
                    r'entering|wider than pad) ([A-Za-z_]+\d+)-(\w+)')
a0 = audit()
if opt('--pads'):
    pads = [p for p in opt('--pads').split(',') if p]
else:
    kel = {k.get(x) for k in (params.get('layout_checks') or {}).get('kelvin') or [] for x in ('sense', 'shunt')}
    seen = []
    for f in a0['findings']:
        if f['check'] == 'pad-entry' and f['level'] == 'FAIL':
            m = RE_PAD.search(f['msg'])
            at = RE_AT.search(f['msg'])
            if at and BOX and not inbox(BOX, float(at.group(1)), float(at.group(2))):
                continue
            if at and XBOX and inbox(XBOX, float(at.group(1)), float(at.group(2))):
                continue
            if m and '%s.%s' % m.groups() not in seen and '%s.%s' % m.groups() not in kel:
                seen.append('%s.%s' % m.groups())
    pads = seen[:int(opt('--max'))] if opt('--max') else seen
shutil.copy(PCB, PCB + '.bak_prerefinish')
base = drc()
fail = a0['summary']['FAIL']
ids = audit_gate.fail_ids(a0['findings'])
pe0 = sum(1 for f in a0['findings'] if f['check'] == 'pad-entry' and f['level'] == 'FAIL')
lay0 = layout_passing()
say('start: %d pad(s); DRC errors + unconnected %d; audit FAIL %d (pad-entry %d)%s' % (
    len(pads), base, fail, pe0, '' if lay0 is None else '; layout checks passing %d' % len(lay0)))
kept = reverted = refused = 0
LOCKS = locks.fingerprint(PCB)
RULE = stop_rule.StopRule.from_argv(argv)
if RULE:
    say(RULE.estimate(len(pads), 1.2, 0.5))
STOPPED = None
for i_pad, tag in enumerate(pads):
    if RULE:
        STOPPED = RULE.should_stop(len(pads) - i_pad)
        if STOPPED:
            say('STOP RULE: %s; %d pad(s) not tried, left for the interactive router: %s' % (
                STOPPED, len(pads) - i_pad, ','.join(pads[i_pad:])))
            break
    for attempt in range(int(opt('--tries', '4'))):
        bak = open(PCB, 'rb').read()
        r = subprocess.run([KP, os.path.join(HERE, 'route_finish.py'), PCB, '--refinish', tag] + RF_EXTRA +
                           (['--force-write'] if '--force-write' in argv else []),
                           capture_output=True, text=True, encoding='utf-8', errors='replace', env=ENV)
        if 'nothing to do' in r.stdout:
            break
        if r.returncode != 0:
            refused += 1
            if RULE:
                RULE.attempt(False)
            msg = [l for l in r.stderr.splitlines() if l.strip() and 'memory leak' not in l]
            say('  %-10s not re-routed (exit %d): %s' % (tag, r.returncode, (msg or [''])[-1][:160]))
            open(PCB, 'wb').write(bak)
            break
        e = drc()
        a = audit()
        lay = layout_passing() if lay0 is not None else None
        broke = sorted(lay0 - lay) if lay is not None else []
        new = audit_gate.new_fails(ids, a['findings'])
        moved = locks.changed(LOCKS, locks.fingerprint(PCB))
        if e > base or a['summary']['FAIL'] >= fail or broke or new or moved:
            reverted += 1
            if RULE:
                RULE.attempt(False)
            open(PCB, 'wb').write(bak)
            say('  %-10s REVERTED (DRC %d vs %d, audit FAIL %d vs %d%s%s%s)' % (
                tag, e, base, a['summary']['FAIL'], fail, ', layout check broke' if broke else '',
                ', %d new FAIL, first [%s] %s' % (len(new), new[0]['check'], new[0]['msg'][:100]) if new else '',
                ', %s' % moved[0] if moved else ''))
            break
        fail = a['summary']['FAIL']
        ids = audit_gate.fail_ids(a['findings'])
        kept += 1
        if RULE:
            RULE.attempt(True)
        say('  %-10s kept (audit FAIL %d)' % (tag, fail))
a1 = audit()
pe1 = sum(1 for f in a1['findings'] if f['check'] == 'pad-entry' and f['level'] == 'FAIL')
if RULE:
    say(RULE.summary())
say('end: %d kept, %d reverted, %d refused; DRC %d; audit FAIL %d -> %d, pad-entry %d -> %d; backup %s%s' % (
    kept, reverted, refused, drc(), a0['summary']['FAIL'], a1['summary']['FAIL'], pe0, pe1,
    os.path.basename(PCB) + '.bak_prerefinish', ' (stopped: %s)' % STOPPED if STOPPED else ''))
for ext in ('.drc.json', '.audit.json', '.layout.json'):
    try:
        os.remove(TMP + ext)
    except OSError:
        pass
