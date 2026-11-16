#!/usr/bin/env python
"""board_guard.py - pre-write guard for every kicad-routing script that SAVES a board (board review rev. 0.2,
2026-10-20, lessons "Check the KiCad lock files before a script writes the board" and "Never save a board loaded
from a copy without its .kicad_pro beside it").

check_board_writable(board_path) refuses (SystemExit, exit code 3, clear message) when
  1. KiCad holds a lock on the board or on its project. KiCad 9/10 write the lock file beside the file as
     "~<file name>.lck" (common/lockfile.h: prefix "~", extension "lck"), e.g. ~ServiceOne_Main.kicad_pcb.lck and
     ~ServiceOne_Main.kicad_pro.lck. The variants without the "~" (older releases) are checked too. A script that
     writes the board while pcbnew has it open loses its work at the next save from KiCad, or KiCad loses its own.
  2. No <name>.kicad_pro sits beside the board. pcbnew loads the project rules from that file and, on save,
     rewrites it from its cache: a board loaded from a copy without its project is saved with KiCad's DEFAULT
     rules written into a brand-new .kicad_pro (release work 2026-10-19).

Overrides (use only when you know why):
  --force-write   argument, or KICAD_ROUTING_FORCE_WRITE=1   skip both checks (stale lock after a KiCad crash)
  --allow-no-pro  argument, or KICAD_ROUTING_ALLOW_NO_PRO=1  skip only the .kicad_pro check (export copies)
An override given as an argument is exported to the environment, so the scripts a driver calls (finish_gated.py ->
route_finish.py, centre_gated.py -> center_gaps_safe.py) inherit it.

Command line (system Python is enough, no dependency):
    board_guard.py <board.kicad_pcb> [--force-write] [--allow-no-pro]     exit 0 writable, 3 refused
"""
import os
import sys

FORCE_ENV = 'KICAD_ROUTING_FORCE_WRITE'
NO_PRO_ENV = 'KICAD_ROUTING_ALLOW_NO_PRO'
REFUSED = 3


def _flag(name, env, argv):
    if name in argv:
        os.environ[env] = '1'          # children (drivers calling other scripts) inherit the override
        return True
    return os.environ.get(env, '').strip().lower() in ('1', 'yes', 'true', 'on')


def lock_files(board_path):
    """Existing KiCad lock files that concern this board (the board itself and its project)."""
    board_path = os.path.abspath(board_path)
    d = os.path.dirname(board_path)
    stem = os.path.splitext(os.path.basename(board_path))[0]
    found = []
    for name in (os.path.basename(board_path), stem + '.kicad_pro'):
        for cand in ('~' + name + '.lck', name + '.lck', '~' + os.path.splitext(name)[0] + '.lck'):
            p = os.path.join(d, cand)
            if os.path.isfile(p) and p not in found:
                found.append(p)
    return found


def project_file(board_path):
    board_path = os.path.abspath(board_path)
    return os.path.splitext(board_path)[0] + '.kicad_pro'


def problems(board_path, check_locks=True, require_pro=True):
    """List of human-readable reasons why the board must not be written (empty = writable)."""
    out = []
    if check_locks:
        for p in lock_files(board_path):
            who = ''
            try:
                with open(p, encoding='utf-8', errors='replace') as f:
                    who = f.read(300).strip().replace('\n', ' ')
            except OSError:
                pass
            out.append('KiCad lock file present: %s%s - close the board/project in KiCad first'
                       % (p, ('  (%s)' % who) if who else ''))
    if require_pro and not os.path.isfile(project_file(board_path)):
        out.append('no project file beside the board: %s - pcbnew would save the board with DEFAULT rules and write '
                   'them into a new .kicad_pro. Copy the .kicad_pro (and .kicad_dru, kicad_golden.project.json) next '
                   'to the board, or work on the board in place' % project_file(board_path))
    return out


def check_board_writable(board_path, check_locks=True, require_pro=True, argv=None, script=None):
    """Refuse (SystemExit) when the board must not be written. Returns None when it may be written."""
    argv = sys.argv[1:] if argv is None else argv
    if _flag('--force-write', FORCE_ENV, argv):
        return None
    if _flag('--allow-no-pro', NO_PRO_ENV, argv):
        require_pro = False
    p = problems(board_path, check_locks=check_locks, require_pro=require_pro)
    if not p:
        return None
    name = script or os.path.basename(sys.argv[0] or 'script')
    msg = ['%s: REFUSED to write %s' % (name, os.path.abspath(board_path))]
    msg += ['  - ' + x for x in p]
    msg.append('  (override: --force-write, or --allow-no-pro for the project check only)')
    sys.stderr.write('\n'.join(msg) + '\n')
    sys.stderr.flush()
    raise SystemExit(REFUSED)


if __name__ == '__main__':
    a = sys.argv[1:]
    if not a or a[0].startswith('--'):
        sys.stderr.write(__doc__)
        sys.exit(2)
    check_board_writable(a[0], argv=a[1:])
    print('writable: %s' % os.path.abspath(a[0]))
