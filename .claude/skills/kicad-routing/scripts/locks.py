#!/usr/bin/env python
"""locks.py - locked tracks and vias of a board, read from the file text (lessons L39, L40; ServiceOne 2026-10-22/23).

The DRC and audit gates do not see a lock: on ServiceOne two scratch via tools moved 43 locked stitching items and
refinish_gated.py removed 3, all gate-clean. Every gated driver therefore takes the locked-item fingerprint of the
board before an attempt and reverts the attempt when a locked item moved, changed or disappeared.

Locks are of two kinds and must be told apart (L39): design locks (Kelvin sense, datasheet loops, hand-laid critical
copper) and tool locks (stitch_residual.py locks the vias and stubs it places). Tool locks become fixed walls for
KiCad's shove router. --list prints the locked items per net, so a hand-off note can say what is locked and why.

System Python, no pcbnew (KiCad 9 and 10 files: a top-level (segment|arc|via ...) block with (locked yes)).

Module API:
    fp = fingerprint(path)            # {uuid: canonical text of the locked item}
    msgs = changed(fp_before, fp_after)   # [] when every locked item is unchanged
CLI:
    locks.py BOARD [--list]                  summary (and the items per net)
    locks.py BOARD --compare OTHER_BOARD     exit 1 when a locked item of BOARD moved / changed / is gone in OTHER
"""
import collections
import re
import sys

_ITEM = re.compile(r'^\t\((segment|arc|via)\b.*?^\t\)', re.S | re.M)
_UUID = re.compile(r'\(uuid "?([0-9a-fA-F-]+)"?\)')
_NET = re.compile(r'\(net (?:\d+ )?"([^"]*)"\)|\(net (\d+)\)')


def fingerprint(path):
    """{uuid: (kind, net, canonical geometry text)} of every locked track, arc and via."""
    text = open(path, encoding='utf-8').read()
    out = {}
    for m in _ITEM.finditer(text):
        blk = m.group(0)
        if '(locked yes)' not in blk and not re.search(r'^\t\t\(locked\)', blk, re.M):
            continue
        u = _UUID.search(blk)
        n = _NET.search(blk)
        geo = ' '.join(l.strip() for l in blk.splitlines()[1:-1]
                       if not l.strip().startswith(('(uuid', '(locked', '(net')))
        out[u.group(1) if u else 'no-uuid-%d' % m.start()] = (m.group(1), (n.group(1) or n.group(2)) if n else '', geo)
    return out


def changed(before, after):
    msgs = []
    for u, (kind, net, geo) in before.items():
        if u not in after:
            msgs.append('locked %s of %s removed or unlocked (%s)' % (kind, net, u[:8]))
        elif after[u][2] != geo:
            msgs.append('locked %s of %s moved or changed (%s)' % (kind, net, u[:8]))
    return msgs


def main(argv):
    if not argv or argv[0].startswith('-'):
        sys.stdout.write(__doc__)
        return 2
    fp = fingerprint(argv[0])
    if '--compare' in argv:
        msgs = changed(fp, fingerprint(argv[argv.index('--compare') + 1]))
        for m in msgs:
            print(m)
        print('%d locked item(s); %d moved, changed, removed or unlocked' % (len(fp), len(msgs)))
        return 1 if msgs else 0
    by = collections.Counter((net, kind) for kind, net, _ in fp.values())
    print('%d locked item(s)' % len(fp))
    if '--list' in argv:
        for (net, kind), n in sorted(by.items()):
            print('  %-30s %-7s %d' % (net, kind, n))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
