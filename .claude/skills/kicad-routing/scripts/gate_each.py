#!/usr/bin/env python
"""gate_each.py - run a candidate-indexed board tool one candidate at a time, each change gated by stage_gate.py,
under the stop rule (lessons L27, L30, L37, L40; ServiceOne rev. 0.2 board-wide passes, 2026-10-22/23).

Several finishing tools take an audit JSON and act on candidate i of their own list (via_relocate.py,
dedupe_copper.py, center_gaps_safe.py: --indices i --apply). This driver runs such a tool for i = 0 .. N-1 on the
board in place. After each run that changed the board it gates the board against the snapshot taken at the start
(DRC no worse, unconnected not up, no new audit FAIL, passing layout checks still passing, locked items unchanged); a
blocked change is restored from the copy taken just before it. The gate is cumulative: the board after any number of
kept changes still has nothing new against the start, and no snapshot is retaken between candidates. The candidate list and the indices come from the audit JSON given to
the tool, so the tool's view does not shift while the board changes; a candidate whose copper is gone is skipped by
the tool itself.

Usage (system Python; node and KiCad installed; KiCad closed):
    gate_each.py BOARD (--count N [--start 0] | --indices a,b,c) [--snap-dir DIR] [--budget MIN] [--min-keep-rate R] [--no-stop-rule]
                 [--refill-every N] [--log FILE] -- TOOL_ARGV...
TOOL_ARGV is the tool's command line; {i} is replaced by the candidate index and {board} by BOARD. Example:
    gate_each.py hw/b.kicad_pcb --count 120 -- "<kicad>/bin/python" scripts/via_relocate.py {board} \\
        work/audit.json --mode axis --apply --indices {i}
--indices runs only the listed candidates (take them from the tool's own dry run, e.g. the "nudged [i]" lines of
via_relocate.py without --apply). Every --refill-every kept changes (default 20) and at the end, the gate runs with the zones refilled. A backup
<board>.bak_pregate is written first. Run a sample (--count 10) before a long pass and look at the keep rate.
"""
import hashlib
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kicad_sexp as KS  # noqa: E402
import board_guard  # noqa: E402
import stage_gate  # noqa: E402
import stop_rule  # noqa: E402


def main(argv):
    if '--' not in argv or not argv or argv[0].startswith('-'):
        sys.stdout.write(__doc__)
        return 2
    tool = argv[argv.index('--') + 1:]
    a = argv[:argv.index('--')]
    opt = lambda n, d=None: a[a.index(n) + 1] if n in a else d
    board = os.path.abspath(a[0])
    board_guard.check_board_writable(board, argv=a[1:], script='gate_each.py')
    kp, cli = KS.find_kicad_python(opt('--kicad-python')), KS.find_kicad_cli(opt('--kicad-cli'))
    if not (kp and cli):
        sys.exit("need KiCad's python (%s) and kicad-cli (%s); pass --kicad-python / --kicad-cli" % (kp, cli))
    n, start = int(opt('--count', '0')), int(opt('--start', '0'))
    idx = [int(v) for v in opt('--indices').split(',') if v.strip()] if opt('--indices') else list(range(start, start + n))
    snap = os.path.abspath(opt('--snap-dir', os.path.splitext(board)[0] + '.gate_snap'))
    every = int(opt('--refill-every', '20'))
    log = open(opt('--log', os.path.splitext(board)[0] + '.gate_each.log'), 'a', encoding='utf-8')
    rule = stop_rule.StopRule.from_argv(a)

    def say(s):
        s = time.strftime('%H:%M:%S ') + s
        print(s, flush=True)
        log.write(s + '\n')
        log.flush()

    digest = lambda: hashlib.sha256(open(board, 'rb').read()).hexdigest()
    shutil.copy2(board, board + '.bak_pregate')
    stage_gate.snapshot(snap, board, opt('--params'), kp, cli)
    say('start: %d candidate(s); tool %s' % (len(idx), ' '.join(os.path.basename(t) for t in tool[:2])))
    if rule:
        say(rule.estimate(len(idx), 1, 1.0))
    kept = since_refill = 0
    stopped = None
    for k, i in enumerate(idx):
        if rule:
            stopped = rule.should_stop(len(idx) - k)
            if stopped:
                say('STOP RULE: %s; candidates not tried: %s' % (stopped, ','.join(map(str, idx[k:]))))
                break
        h0 = digest()
        shutil.copy2(board, board + '.try')
        cmd = [t.replace('{i}', str(i)).replace('{board}', board) for t in tool]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace',
                           env=dict(os.environ, MSYS_NO_PATHCONV='1'))
        if digest() == h0:
            last = [l for l in (r.stdout + r.stderr).splitlines() if l.strip() and 'image handler' not in l]
            say('  [%d] no change (exit %d) %s' % (i, r.returncode, (last[-1] if last else '')[:120]))
            continue
        ok, lines = stage_gate.compare(snap, board, opt('--params'), kp, cli)
        if rule:
            rule.attempt(ok)
        if not ok:
            shutil.copy2(board + '.try', board)
            say('  [%d] REVERTED %s' % (i, lines[0]))
            for l in lines[1:3]:
                say('  ' + l)
            continue
        kept += 1
        since_refill += 1
        say('  [%d] KEPT %s' % (i, lines[0]))
        if since_refill >= every:
            ok, lines = stage_gate.compare(snap, board, opt('--params'), kp, cli, refill=True)
            say('  refill check: %s' % lines[0])
            if not ok:
                say('  the refilled board fails the gate: stopping; restore %s if needed' % (board + '.bak_pregate'))
                stopped = 'refill check failed'
                break
            since_refill = 0
    ok, lines = stage_gate.compare(snap, board, opt('--params'), kp, cli, refill=True)
    say('end refill check: %s' % lines[0])
    if os.path.exists(board + '.try'):
        os.remove(board + '.try')
    if rule:
        say(rule.summary())
    say('end: %d kept; backup %s%s' % (kept, os.path.basename(board) + '.bak_pregate',
                                       ' (stopped: %s)' % stopped if stopped else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
