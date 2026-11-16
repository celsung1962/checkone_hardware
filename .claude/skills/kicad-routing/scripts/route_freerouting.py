#!/usr/bin/env python
"""
route_freerouting.py - automated Specctra DSN/SES round-trip for the kicad-routing skill.

MUST be run with KiCad's own Python interpreter, because it imports `pcbnew`:

    Windows  "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" route_freerouting.py <board.kicad_pcb> [opts]
    Linux    /usr/bin/python3 route_freerouting.py <board.kicad_pcb> [opts]

kicad-cli does not expose Specctra DSN/SES in KiCad 10; the pcbnew API does, via the
two-argument overloads ExportSpecctraDSN(BOARD, path) / ImportSpecctraSES(BOARD, path).

Options:
  --fr-cmd "<command>"   Freerouting invocation; overrides auto-discovery.
  --passes N             -mp value (default 100).
  --timeout SECONDS      hard cap on the router (default 3600).
  --threads N            -mt value (default: leave to Freerouting).
  --export-only          write the .dsn, print the discovered router, then stop.
  --import-only PATH     skip routing; import an existing .ses.
  --outdir DIR           where .dsn/.ses/log are written (default: next to the board).
  --no-fill              skip the zone re-fill after import.
  --no-plane-filter      do NOT filter inner-layer plane nets out of the DSN (rev P default: filter
                         them, so Freerouting cannot surface-link plane-net pads - improvements #7).

Exit codes: 0 ok, 1 failure (message on stderr), 2 usage.
"""

import io
import os
import sys
import shutil
import subprocess
import glob
import re
import time

# ---------------------------------------------------------------- arg parsing


def die(msg, code=1):
    sys.stderr.write('ERROR: ' + msg + '\n')
    sys.exit(code)


args = sys.argv[1:]
if not args or args[0].startswith('--'):
    die(__doc__, 2)
BOARD = os.path.abspath(args[0])
if not os.path.isfile(BOARD):
    die('no such board: ' + BOARD, 2)


def opt(name, default=None):
    if name in args:
        i = args.index(name)
        if i + 1 >= len(args):
            die(name + ' needs a value', 2)
        return args[i + 1]
    return default


FR_CMD_RAW = opt('--fr-cmd')
PASSES = int(opt('--passes', '100'))
TIMEOUT = int(opt('--timeout', '3600'))
THREADS = opt('--threads')
OUTDIR = os.path.abspath(opt('--outdir', os.path.dirname(BOARD)))
EXPORT_ONLY = '--export-only' in args
IMPORT_ONLY = opt('--import-only')
NO_FILL = '--no-fill' in args
AUTO_CLEARANCE = '--auto-clearance' in args
CLEARANCE = opt('--clearance')
NO_PADSTACK_GATE = '--no-padstack-gate' in args
NO_PLANE_FILTER = '--no-plane-filter' in args
RULES = opt('--rules')
AUTO_RULES = '--auto-rules' in args

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board_guard  # noqa: E402
if not EXPORT_ONLY:
    # the import saves the board in place: no KiCad lock, and its .kicad_pro beside it (pcbnew rewrites it)
    board_guard.check_board_writable(BOARD, script='route_freerouting.py')

# 1.26.0 (playbook B0): the datasheets' layout suggestions are applied before routing
if not IMPORT_ONLY and '--skip-datasheet-review' not in args:
    import json as _json
    _pp = opt('--params') or os.path.join(os.path.dirname(os.path.abspath(BOARD)), 'kicad_golden.project.json')
    _dl = (_json.load(open(_pp, encoding='utf-8')) if os.path.isfile(_pp) else {}).get('datasheet_layout')
    if _dl is None:
        sys.stderr.write('WARNING: no datasheet layout review on record (%s -> datasheet_layout). Run '
                         'datasheet_layout_scan.py --write-params and review the pages first (playbook B0).\n' % _pp)
    else:
        _pend = [p['part'] for p in _dl.get('parts', []) if p.get('status', 'pending') == 'pending']
        if _pend:
            sys.stderr.write('REFUSED: the datasheet layout suggestions of %d part(s) are not reviewed yet: %s.\n'
                             'Read their pages (datasheet_layout_scan.py report), apply each rule and set status '
                             'applied / n/a in %s - or pass --skip-datasheet-review.\n' % (len(_pend), ', '.join(_pend[:10]), _pp))
            sys.exit(4)

if not os.path.isdir(OUTDIR):
    os.makedirs(OUTDIR)

stem = os.path.splitext(os.path.basename(BOARD))[0]
DSN = os.path.join(OUTDIR, stem + '.dsn')
SES = os.path.join(OUTDIR, stem + '.ses')
LOG = os.path.join(OUTDIR, stem + '.freerouting.log')


def log(msg):
    print(msg)
    sys.stdout.flush()


# ---------------------------------------------------------------- discovery

def _exists(p):
    return p and os.path.isfile(p)


def java_major(java):
    """Return the major version of a java executable, or None."""
    try:
        r = subprocess.run([java, '-version'], capture_output=True, text=True, timeout=30)
        blob = (r.stderr or '') + (r.stdout or '')
    except Exception:
        return None
    m = re.search(r'version "(\d+)(?:\.(\d+))?', blob)
    if not m:
        return None
    maj = int(m.group(1))
    if maj == 1 and m.group(2):
        maj = int(m.group(2))
    return maj


def discover_freerouting():
    """Portable resolution order. Returns (argv_list, how_it_was_found)."""
    # 1. explicit override
    if FR_CMD_RAW:
        import shlex
        return shlex.split(FR_CMD_RAW, posix=(os.name != 'nt')), 'explicit --fr-cmd'

    # 2. environment
    env = os.environ.get('FREEROUTING_CMD')
    if env:
        import shlex
        return shlex.split(env, posix=(os.name != 'nt')), 'FREEROUTING_CMD env var'

    # 3. PATH
    for name in ('freerouting', 'freerouting.exe'):
        p = shutil.which(name)
        if p:
            return [p], 'PATH'

    # 4. per-platform install locations (native launchers first - they bundle a JRE)
    home = os.path.expanduser('~')
    cands = []
    if os.name == 'nt':
        for base in (os.environ.get('LOCALAPPDATA', os.path.join(home, 'AppData', 'Local')),
                     os.environ.get('PROGRAMFILES', r'C:\Program Files'),
                     os.environ.get('PROGRAMFILES(X86)', r'C:\Program Files (x86)')):
            if base:
                cands += [os.path.join(base, 'freerouting', 'freerouting.exe'),
                          os.path.join(base, 'Freerouting', 'freerouting.exe')]
    elif sys.platform == 'darwin':
        cands += ['/Applications/Freerouting.app/Contents/MacOS/Freerouting',
                  os.path.join(home, 'Applications', 'Freerouting.app', 'Contents', 'MacOS', 'Freerouting')]
    else:
        cands += [os.path.join(home, '.local', 'share', 'freerouting', 'bin', 'freerouting'),
                  '/opt/freerouting/bin/freerouting', '/usr/local/bin/freerouting',
                  '/usr/bin/freerouting']
    for c in cands:
        if _exists(c):
            return [c], 'install location'

    # 5. jar fallback - needs an external Java 21+
    jars = []
    roots = [os.path.join(home, 'AppData', 'Local', 'freerouting', 'app'),
             os.path.join(home, '.local', 'share', 'freerouting'),
             '/opt/freerouting', os.path.join(home, 'Downloads'), os.getcwd()]
    for r in roots:
        if os.path.isdir(r):
            jars += sorted(glob.glob(os.path.join(r, '**', 'freerouting*.jar'), recursive=True))
    if jars:
        java = shutil.which('java')
        if java:
            mj = java_major(java)
            if mj and mj >= 21:
                return [java, '-jar', jars[0]], 'java -jar (java %d)' % mj
            die('found %s but the only java on PATH is version %s; Freerouting 2.x needs Java 21+. '
                'Install the native Freerouting build or pass --fr-cmd.' % (jars[0], mj))
        die('found %s but no java on PATH. Install the native Freerouting build or pass --fr-cmd.' % jars[0])

    die('Freerouting not found. Searched PATH, the standard install locations for this OS, and for a '
        'freerouting*.jar. Install it, set FREEROUTING_CMD, or pass --fr-cmd "<command>".')


# ---------------------------------------------------------------- pcbnew

try:
    import pcbnew
except ImportError as e:
    die('cannot import pcbnew (%s).\nRun this with KiCad\'s own Python, e.g.\n'
        '  "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" %s <board>' % (e, os.path.basename(__file__)))

log('pcbnew %s' % pcbnew.GetBuildVersion())
log('board   %s' % BOARD)
log('outdir  %s' % OUTDIR)

PRO = os.path.splitext(BOARD)[0] + '.kicad_pro'
_clearance_restore = None


def apply_auto_clearance():
    """Raise every netclass clearance to the largest footprint-local override.

    The Specctra DSN has no per-footprint clearance field, so a footprint carrying
    (clearance X) is invisible to the router: it undercuts that part and every violation
    only appears after the import. The DSN takes its clearance from the NETCLASS, not from
    the min_clearance board rule - changing min_clearance does nothing.

    Returns the original classes list for restoration, or None when no change was needed.
    """
    import json
    # Read the overrides from the BOARD FILE, not via LoadBoard. pcbnew caches the project by
    # path, so probing with LoadBoard here would pin the old netclass clearances in memory and
    # the edit below would never reach the DSN.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import kicad_sexp as _K
    _locals = _K.footprint_local_clearances(BOARD)
    worst, who = 0, None
    for _ref, _mm in _locals:
        if int(round(_mm * 1e6)) > worst:
            worst, who = int(round(_mm * 1e6)), _ref
    forced = float(CLEARANCE) if CLEARANCE else 0.0
    if forced and int(round(forced * 1e6)) >= worst:
        worst, who = int(round(forced * 1e6)), '--clearance'
    elif worst:
        who = '%s (footprint-local override)' % who
    if not worst:
        log('auto-clearance: no footprint-local overrides; nothing to do')
        return None
    worst_mm = worst / 1e6
    if not os.path.isfile(PRO):
        log('auto-clearance: %s not found; cannot raise clearance' % os.path.basename(PRO))
        return None
    with io.open(PRO, encoding='utf-8') as f:
        proj = json.load(f)
    classes = proj.get('net_settings', {}).get('classes', [])
    original = json.loads(json.dumps(classes))
    raised = []
    for c in classes:
        cur = c.get('clearance')
        if cur is not None and cur < worst_mm:
            raised.append((c.get('name'), cur, worst_mm))
            c['clearance'] = worst_mm
    if not raised:
        log('auto-clearance: netclass clearance already >= %.3f mm (%s)' % (worst_mm, who))
        return None
    with io.open(PRO, 'w', encoding='utf-8') as f:
        f.write(json.dumps(proj, indent=2))
    log('auto-clearance: export clearance %.3f mm required by %s; raised %d netclass clearance(s):'
        % (worst_mm, who, len(raised)))
    for n, a, b_ in raised:
        log('    %-20s %.3f -> %.3f mm' % (n, a, b_))
    log('    (restored immediately after the DSN is written)')
    return original


def restore_clearance(original):
    import json
    if original is None:
        return
    with io.open(PRO, encoding='utf-8') as f:
        proj = json.load(f)
    proj.setdefault('net_settings', {})['classes'] = original
    with io.open(PRO, 'w', encoding='utf-8') as f:
        f.write(json.dumps(proj, indent=2))
    log('auto-clearance: netclass clearances restored')


def via_inventory(board):
    """diameter/drill census. KiCad 10 vias may carry a per-layer width and the arg-less
    PCB_VIA.GetWidth() trips an assertion that can pop a modal dialog and hang a headless
    run - always use the layer-aware accessor."""
    inv = {}
    for v in board.GetTracks():
        if v.GetClass() != 'PCB_VIA':
            continue
        d = v.GetFrontWidth() if hasattr(v, 'GetFrontWidth') else v.GetWidth(pcbnew.F_Cu)
        inv['%.3f/%.3f' % (d / 1e6, v.GetDrill() / 1e6)] = inv.get('%.3f/%.3f' % (d / 1e6, v.GetDrill() / 1e6), 0) + 1
    return inv


def bad_padstacks(board):
    out = []
    for v in board.GetTracks():
        if v.GetClass() != 'PCB_VIA':
            continue
        d = v.GetFrontWidth() if hasattr(v, 'GetFrontWidth') else v.GetWidth(pcbnew.F_Cu)
        if v.GetDrill() >= d:
            c = v.GetStart()
            out.append((v.GetNetname(), c.x / 1e6, c.y / 1e6, d / 1e6, v.GetDrill() / 1e6))
    return out

BACKUP = BOARD + '.bak_prerouting'
if not os.path.exists(BACKUP):
    shutil.copy2(BOARD, BACKUP)
    log('backup  %s' % BACKUP)
else:
    log('backup  %s (kept existing)' % BACKUP)


def fill_zones(board):
    filler = pcbnew.ZONE_FILLER(board)
    zones = board.Zones()
    ok = filler.Fill(zones)
    return ok, len(list(zones))


# ---------------------------------------------------------------- 1. export

if not IMPORT_ONLY:
    if AUTO_CLEARANCE or CLEARANCE:
        _clearance_restore = apply_auto_clearance()
    board = pcbnew.LoadBoard(BOARD)
    log('loaded: %d footprints, %d tracks, %d zones'
        % (len(board.GetFootprints()), len(board.GetTracks()), len(list(board.Zones()))))

    if not NO_FILL:
        ok, nz = fill_zones(board)
        log('zone fill before export: %s (%d zones)' % (ok, nz))

    if os.path.exists(DSN):
        os.remove(DSN)
    if not pcbnew.ExportSpecctraDSN(board, DSN):
        die('ExportSpecctraDSN returned False')
    if not os.path.exists(DSN) or os.path.getsize(DSN) == 0:
        die('DSN missing or empty after export')
    log('DSN written: %s (%.1f MB)' % (DSN, os.path.getsize(DSN) / 1e6))

    # rev P / improvements #7: a net with its own inner-layer plane must be via-only on F.Cu/B.Cu -
    # Freerouting will happily join its pads with surface tracks if given the chance. Filtering the
    # plane nets out of the DSN before routing prevents the link from ever being created; stitch_planes.py
    # then places the real vias. --no-plane-filter restores the pre-1.16.0 behaviour.
    if not NO_PLANE_FILTER:
        plane_nets = sorted({z.GetNetname() for z in board.Zones()
                              if not z.GetIsRuleArea() and pcbnew.IsCopperLayer(z.GetLayer())
                              and z.GetLayer() not in (pcbnew.F_Cu, pcbnew.B_Cu) and z.GetNetname()})
        if plane_nets:
            _filtered = DSN + '.planefiltered'
            _cmd = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dsn_filter.py'),
                    DSN, _filtered, '--nets', ','.join(plane_nets), '--invert', '--quiet']
            if subprocess.call(_cmd) == 0 and os.path.isfile(_filtered) and os.path.getsize(_filtered) > 0:
                shutil.move(_filtered, DSN)
                log('plane nets filtered out of the DSN (via-only, improvements #7): %s' % ', '.join(plane_nets))
            else:
                log('WARNING: plane-net DSN filter failed; routing with plane nets exposed to Freerouting')
        else:
            log('no inner-layer plane zones found - nothing to filter')

    # Autorouter costs (via cost, preferred direction, rip-up) are GUI state by default, so a
    # batch run inherits whatever the last person clicked. -dr reads them from a file instead.
    if AUTO_RULES and not RULES:
        _gen = os.path.splitext(DSN)[0] + '.rules'
        _pf = None
        for _c in (os.path.splitext(BOARD)[0] + '.golden.json',
                   os.path.join(os.path.dirname(BOARD), 'kicad_golden.project.json')):
            if os.path.isfile(_c):
                _pf = _c
                break
        _cmd = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                             'rules_writer.py'), DSN, _gen, '--quiet']
        if _pf:
            _cmd += ['--params', _pf]
        if subprocess.call(_cmd) == 0 and os.path.isfile(_gen):
            RULES = _gen
            log('auto-rules: wrote %s' % os.path.basename(_gen))
        else:
            log('auto-rules: rules_writer failed; continuing without -dr')
    restore_clearance(_clearance_restore)
    # Deliberately NOT cleared. pcbnew caches the project settings it read at LoadBoard time, so
    # the SaveBoard at the end of the import rewrites the .kicad_pro from that cache and silently
    # puts the RAISED clearance back - this restore alone does not survive. Re-asserted after the
    # save. Measured: a 3-candidate sweep left the netclasses at the last candidate's clearance
    # (0.100 -> 0.250) while logging "restored" three times.
    VIAS_BEFORE = via_inventory(board)

FR, how = discover_freerouting()
log('freerouting: %s   [found via %s]' % (' '.join(FR), how))

if EXPORT_ONLY:
    log('--export-only: stopping before the router runs.')
    sys.exit(0)

# ---------------------------------------------------------------- 2. route

if not IMPORT_ONLY:
    if os.path.exists(SES):
        os.remove(SES)
    cmd = FR + ['-de', DSN, '-do', SES, '-mp', str(PASSES), '-l', 'en']
    if RULES:
        if not os.path.isfile(RULES):
            die('no such rules file: ' + RULES, 2)
        cmd += ['-dr', RULES]
        log('rules: %s' % RULES)
    if THREADS:
        cmd += ['-mt', str(THREADS)]
    log('running: %s' % ' '.join(cmd))
    log('timeout: %d s (%.1f h)' % (TIMEOUT, TIMEOUT / 3600.0))
    t0 = time.time()
    # The native launcher spawns the JVM as a GRANDCHILD. subprocess timeout/kill only reaches the
    # direct child, which would orphan a multi-GB router running unsupervised. Kill the whole tree.
    kw = {}
    if os.name == 'nt':
        kw['creationflags'] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kw['start_new_session'] = True
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            cwd=OUTDIR, errors='replace', **kw)

    def kill_tree(p):
        if os.name == 'nt':
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(p.pid)],
                           capture_output=True, timeout=60)
        else:
            import signal
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGKILL)
            except Exception:
                p.kill()

    try:
        out, err = proc.communicate(timeout=TIMEOUT)
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        log('timeout reached - killing the Freerouting process tree')
        kill_tree(proc)
        try:
            out, err = proc.communicate(timeout=60)
        except Exception:
            out, err = '', ''
        rc = 'TIMEOUT'
    except KeyboardInterrupt:
        kill_tree(proc)
        raise
    out, err = out or '', err or ''
    dt = time.time() - t0
    # verify nothing survived
    if rc == 'TIMEOUT' and os.name == 'nt':
        chk = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq freerouting.exe'],
                             capture_output=True, text=True, timeout=60)
        if 'freerouting.exe' in (chk.stdout or ''):
            log('WARNING: a freerouting.exe survived the tree kill - stop it manually')
    with open(LOG, 'w', encoding='utf-8', errors='replace') as f:
        f.write('cmd: %s\nexit: %s\nelapsed: %.1f s\n\n--- stdout ---\n%s\n--- stderr ---\n%s\n'
                % (' '.join(cmd), rc, dt, out, err))
    log('freerouting exit=%s elapsed=%.1f s   log: %s' % (rc, dt, LOG))
    for line in (out or '').splitlines()[-25:]:
        log('  | ' + line)
    if err.strip():
        for line in err.splitlines()[-15:]:
            log('  ! ' + line)
    if rc == 'TIMEOUT':
        die('Freerouting exceeded the %d s cap; no .ses imported. Board left untouched.' % TIMEOUT)
    if not os.path.exists(SES) or os.path.getsize(SES) == 0:
        die('Freerouting produced no usable .ses (exit %s). Board left untouched.' % rc)
    log('SES written: %s (%.1f MB)' % (SES, os.path.getsize(SES) / 1e6))
    ses_path = SES
else:
    ses_path = os.path.abspath(IMPORT_ONLY)
    if not _exists(ses_path) or os.path.getsize(ses_path) == 0:
        die('no usable .ses at ' + ses_path)

# ---------------------------------------------------------------- 3. import

board = pcbnew.LoadBoard(BOARD)          # reload: export may have mutated in-memory state
before = len(board.GetTracks())
if not pcbnew.ImportSpecctraSES(board, ses_path):
    die('ImportSpecctraSES returned False; board not saved')
after = len(board.GetTracks())

if not NO_FILL:
    ok, nz = fill_zones(board)
    log('zone fill after import: %s (%d zones)' % (ok, nz))

# Padstack integrity gate: a DSN/SES round-trip can return a via whose drill is larger than
# its own pad (observed: 0.25 mm diameter against a 0.30 mm drill, annular -0.025 mm). KiCad
# will save it without complaint, so check before writing over a good board.
_bad = [] if NO_PADSTACK_GATE else bad_padstacks(board)
if _bad:
    log('')
    log('PADSTACK GATE: %d via(s) came back with a hole at least as large as the pad.' % len(_bad))
    for n, x, y, d, dr in _bad[:10]:
        log('    %-18s @ (%.3f, %.3f)  diameter %.3f  drill %.3f' % (n[:18], x, y, d, dr))
    log('The SES import corrupted these padstacks. The board on disk was NOT modified;')
    log('%s still holds the pre-routing state.' % os.path.basename(BACKUP))
    log('Re-run from a bare board, or route the remaining connection by hand.')
    die('aborted on corrupted via padstacks (use --no-padstack-gate to override)')

board_guard.check_board_writable(BOARD, script='route_freerouting.py')   # again: KiCad may have opened it meanwhile
if not pcbnew.SaveBoard(BOARD, board):
    die('SaveBoard returned False')

# SaveBoard rewrites the .kicad_pro from pcbnew's cached project settings, undoing the restore
# done before the router ran. Re-assert it against the file that is now on disk.
if _clearance_restore is not None:
    restore_clearance(_clearance_restore)
    _clearance_restore = None

log('imported: tracks %d -> %d' % (before, after))
log('saved: %s' % BOARD)
log('')
log('NEXT: the router does not obey the golden standard. Run the post-import repair')
log('(45 deg lattice, pad-entry snapping, neckdown removal, via flags) and then kicad_audit.js.')
