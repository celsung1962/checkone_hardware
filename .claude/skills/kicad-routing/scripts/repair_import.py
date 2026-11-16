#!/usr/bin/env python
"""repair_import.py - post-import repair of an external router's output.

Freerouting does not obey this standard. After a Specctra SES import, this fixes what it emits:

  * every via gets  (remove_unused_layers yes) (keep_end_layers yes)   [Q-06, FAIL if missing]
  * segments below min_track_width are raised to it
  * optionally deletes items named in a kicad-cli DRC report, then iteratively removes the dangling
    stubs that deletion creates, re-running DRC until nothing dangles

  python repair_import.py <board.kicad_pcb> [--drc report.json --delete TYPE[,TYPE...]]
                                            [--declang] [--kicad-cli PATH] [--dry-run] [--no-fill]

The board must have its .kicad_pro beside it and no KiCad lock (board_guard.py). After any write the zones
are refilled and the board saved through KiCad's Python (zone_fill_check.py --fix; --no-fill skips it).

--delete takes DRC violation types (e.g. copper_edge_clearance). Only Track/Via items are removed,
never pads or graphics. Deleting copper breaks connections that were good: the summary reports it.
"""
import io, os, re, sys, json, glob, shutil, subprocess, collections

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kicad_sexp as KS
import board_guard  # noqa: E402
import zone_fill_check  # noqa: E402

WROTE = []          # set when any pass wrote the board: refill the zones once at the end

UUID_RE = re.compile(r'\(uuid "([0-9a-fA-F-]+)"\)')


def find_cli(explicit=None):
    if explicit:
        return explicit
    for c in ('kicad-cli', 'kicad-cli.exe'):
        p = shutil.which(c)
        if p:
            return p
    pats = [r'C:\Program Files\KiCad\*\bin\kicad-cli.exe',
            '/usr/bin/kicad-cli', '/usr/local/bin/kicad-cli',
            '/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli']
    for pat in pats:
        hit = sorted(glob.glob(pat))
        if hit:
            return hit[-1]
    return None


def run_drc(cli, board, out):
    r = subprocess.run([cli, 'pcb', 'drc', '--format', 'json', '--output', out, board],
                       capture_output=True, text=True, timeout=900)
    if not os.path.exists(out):
        raise SystemExit('DRC failed: ' + ((r.stderr or r.stdout) or '')[:400])
    return json.load(io.open(out, encoding='utf-8'))


def targets_from(drc, types):
    tgt = {}
    for v in drc.get('violations', []):
        if v.get('type') not in types:
            continue
        for it in v.get('items', []):
            d = it.get('description', '')
            if d.startswith('Track') or d.startswith('Via'):
                tgt[it['uuid']] = d
    return tgt


def drop_uuids(board, uuids):
    """Remove top-level segment/via blocks whose uuid is listed. Returns (result, counter)."""
    s, eol = KS.read_board(board)
    K = KS.kids(s)
    out, cursor, rem = [], 0, collections.Counter()
    for blk, h, a, b in K:
        if h in ('segment', 'via'):
            m = UUID_RE.search(blk)
            if m and m.group(1) in uuids:
                da, db = KS.whole_lines(s, a, b)
                out.append(s[cursor:da])
                cursor = db
                rem[h] += 1
                continue
        out.append(s[cursor:b])
        cursor = b
    out.append(s[cursor:])
    return s, ''.join(out), rem


def netcount(drc):
    c = collections.Counter()
    for u in drc.get('unconnected_items', []):
        for i in u.get('items', []):
            m = re.search(r'\[([^\]]+)\]', i.get('description', ''))
            if m:
                c[m.group(1)] += 1
                break
    return c


def main():
    args = sys.argv[1:]
    if not args or args[0].startswith('--'):
        sys.stderr.write(__doc__)
        return 2
    board = os.path.abspath(args[0])
    dry = '--dry-run' in args

    def opt(n, d=None):
        return args[args.index(n) + 1] if n in args else d

    if not dry:
        board_guard.check_board_writable(board, script='repair_import.py')
    R = KS.rules_from_project(board)
    MINW = R['min_track_width']

    # ---------------- pass 1: via flags + widths ----------------
    s, eol = KS.read_board(board)
    K = KS.kids(s)
    out, cursor = [], 0
    vfix = wfix = vok = 0
    widths = collections.Counter()
    for blk, h, a, b in K:
        if h == 'via':
            ok = ('(remove_unused_layers yes)' in blk) and ('(keep_end_layers yes)' in blk)
            if ok:
                vok += 1
            else:
                new = blk.replace('(remove_unused_layers no)', '(remove_unused_layers yes)') \
                         .replace('(keep_end_layers no)', '(keep_end_layers yes)')
                add = []
                if '(remove_unused_layers' not in new:
                    add.append('\t\t(remove_unused_layers yes)')
                if '(keep_end_layers' not in new:
                    add.append('\t\t(keep_end_layers yes)')
                if add:
                    m = re.search(r'\n\t\t\(layers[^\n]*\)', new)
                    assert m, 'via without a (layers ...) line'
                    new = new[:m.end()] + eol + eol.join(add) + new[m.end():]
                out.append(s[cursor:a]); out.append(new); cursor = b
                vfix += 1
                continue
        elif h == 'segment':
            m = re.search(r'\(width ([0-9.]+)\)', blk)
            if m:
                w = float(m.group(1))
                widths[w] += 1
                if w < MINW - 1e-9:
                    new = blk[:m.start()] + '(width %s)' % MINW + blk[m.end():]
                    out.append(s[cursor:a]); out.append(new); cursor = b
                    wfix += 1
                    continue
        out.append(s[cursor:b]); cursor = b
    out.append(s[cursor:])
    result = ''.join(out)

    print('via flags: %d already compliant, %d fixed (Q-06)' % (vok, vfix))
    print('segments below min_track_width %.3f raised: %d' % (MINW, wfix))
    print('width histogram before: %s' % dict(sorted(widths.items())))
    if not dry and (vfix or wfix):
        KS.verify_write(board, s, result, backup_suffix='.bak_prerepair')
        WROTE.append(board)
        print('written (backup .bak_prerepair)')
    elif dry:
        print('[dry-run] not written')

    # ---------------- pass 2: optional deletion + dangling convergence ----------------
    types = {t.strip() for t in (opt('--delete') or '').split(',') if t.strip()}
    if not types and '--declang' not in args:
        return 0
    cli = find_cli(opt('--kicad-cli'))
    if not cli:
        sys.stderr.write('kicad-cli not found; pass --kicad-cli PATH\n')
        return 1
    work = os.path.join(os.path.dirname(board), '_drc_tmp.json')
    before = run_drc(cli, board, work)
    n0 = netcount(before)

    if types:
        tgt = targets_from(before, types)
        print()
        print('deleting %d routing items implicated in %s' % (len(tgt), ', '.join(sorted(types))))
        if tgt and not dry:
            orig, res, rem = drop_uuids(board, set(tgt))
            KS.verify_write(board, orig, res,
                            expect_delta={'segment': -rem['segment'], 'via': -rem['via']},
                            backup_suffix='.bak_predelete')
            WROTE.append(board)
            print('  removed %s' % dict(rem))

    if '--declang' in args or types:
        print()
        total = collections.Counter()
        for it in range(1, 13):
            d = run_drc(cli, board, work)
            tgt = targets_from(d, {'track_dangling', 'via_dangling'})
            errs = sum(1 for v in d['violations'] if v.get('severity') == 'error')
            print('  iter %d: %d violations (%d errors), %d dangling' % (it, len(d['violations']), errs, len(tgt)))
            if not tgt:
                print('  -> stable')
                break
            if dry:
                print('  [dry-run] stopping')
                break
            orig, res, rem = drop_uuids(board, set(tgt))
            KS.verify_write(board, orig, res,
                            expect_delta={'segment': -rem['segment'], 'via': -rem['via']},
                            backup_suffix='.bak_predeclang')
            WROTE.append(board)
            total.update(rem)
        print('  total removed: %s' % dict(total))

    after = run_drc(cli, board, work)
    n1 = netcount(after)
    regressed = sorted(n for n in set(n0) | set(n1) if n1.get(n, 0) > n0.get(n, 0))
    print()
    print('unconnected items %d -> %d' % (len(before.get('unconnected_items', [])),
                                          len(after.get('unconnected_items', []))))
    if regressed:
        print('NETS MADE WORSE by copper removal (%d):' % len(regressed))
        for n in regressed[:15]:
            print('   %-30s %d -> %d' % (n, n0.get(n, 0), n1.get(n, 0)))
    else:
        print('no net regressed')
    try:
        os.remove(work)
    except OSError:
        pass
    return 0


def _main():
    rc = main()
    if WROTE and '--no-fill' not in sys.argv[1:]:
        zone_fill_check.refill_saved_board(WROTE[0])   # the SAVED fill must be current (board review rev. 0.2, issue 1)
    elif WROTE:
        print('REMINDER: --no-fill - refill the zones (zone_fill_check.py --fix) before DRC / Gerbers / commit')
    return rc


if __name__ == '__main__':
    sys.exit(_main())
