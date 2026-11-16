#!/usr/bin/env python
"""zone_fill_check.py - find stale zone fills in a SAVED board, and optionally refill and save it.

MUST be run with KiCad's own Python (it imports pcbnew).

Board review rev. 0.2 (2026-10-20), issue 1: after scripted copper edits the In1.Cu GND and In2.Cu +3.3V fills
in the board file still showed the clearances of vias that had been moved or removed. Nothing caught it:
`kicad-cli pcb drc --refill-zones` and the Gerber export refill in memory, so DRC and the order files were right
while the saved board stayed stale. This script compares, for every copper zone and layer, the fill saved in the
file with a fresh ZONE_FILLER fill: the area of the symmetric difference (XOR) above the tolerance marks the zone
stale. A moved via inside a plane changes no area, only the position of its clearance hole - the XOR sees it.

Usage:
    zone_fill_check.py <board.kicad_pcb> [--fix] [--tol MM2] [--json FILE] [--force-write] [--allow-no-pro]
      --fix       refill every zone and save the board in place (only when a stale zone was found);
                  goes through board_guard (no KiCad lock, .kicad_pro beside the board)
      --tol MM2   XOR area per zone and layer counted as noise (default 0.01 mm2)
      --json F    write the per-zone result
Exit: 0 every saved fill is current (or --fix refilled and saved), 1 stale fill found (check mode), 2 usage,
      3 refused by board_guard.

Importable: snapshot(board), refill(board), compare(board, before, tol) -> rows, check_and_fix(path, fix).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import board_guard  # noqa: E402

NM2_PER_MM2 = 1e12


def _pcbnew():
    try:
        import pcbnew
        return pcbnew
    except ImportError as e:
        sys.stderr.write("cannot import pcbnew (%s). Run this with KiCad's own Python.\n" % e)
        sys.exit(2)


def copper_zones(board):
    out = []
    for i in range(board.GetAreaCount()):
        z = board.GetArea(i)
        if z.GetIsRuleArea():
            continue
        out.append(z)
    return out


def _layers(board, z):
    pcbnew = _pcbnew()
    return [L for L in z.GetLayerSet().Seq() if pcbnew.IsCopperLayer(L)]


def snapshot(board):
    """{(zone index, layer): copy of the filled polygon set} for every copper zone."""
    pcbnew = _pcbnew()
    snap = {}
    for i, z in enumerate(copper_zones(board)):
        for L in _layers(board, z):
            snap[(i, L)] = pcbnew.SHAPE_POLY_SET(z.GetFilledPolysList(L)) if z.HasFilledPolysForLayer(L) \
                else pcbnew.SHAPE_POLY_SET()
    return snap


def refill(board):
    pcbnew = _pcbnew()
    board.BuildConnectivity()
    zs = pcbnew.ZONES()
    for z in copper_zones(board):
        zs.append(z)
    return pcbnew.ZONE_FILLER(board).Fill(zs)


def compare(board, before, tol_mm2=0.01):
    """Rows for every zone and layer: saved area, fresh area, XOR area (mm2), stale flag."""
    pcbnew = _pcbnew()
    after = snapshot(board)
    zones = copper_zones(board)
    rows = []
    for key in sorted(set(before) | set(after)):
        i, L = key
        a = before.get(key, pcbnew.SHAPE_POLY_SET())
        b = after.get(key, pcbnew.SHAPE_POLY_SET())
        x = a.CloneDropTriangulation() if hasattr(a, 'CloneDropTriangulation') else pcbnew.SHAPE_POLY_SET(a)
        x.BooleanXor(b)
        xa = x.Area() / NM2_PER_MM2
        z = zones[i]
        bb = z.GetBoundingBox()
        rows.append({
            'zone': z.GetZoneName() or '', 'net': z.GetNetname(), 'layer': board.GetLayerName(L),
            'priority': z.GetAssignedPriority(),
            'bbox_mm': [round(pcbnew.ToMM(v), 3) for v in (bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom())],
            'saved_mm2': round(a.Area() / NM2_PER_MM2, 4), 'fresh_mm2': round(b.Area() / NM2_PER_MM2, 4),
            'xor_mm2': round(xa, 4), 'stale': xa > tol_mm2,
        })
    return rows


def check_and_fix(path, fix=False, tol_mm2=0.01, argv=None, quiet=False):
    """Load, compare, optionally save. Returns (rows, saved: bool)."""
    pcbnew = _pcbnew()
    if fix:
        board_guard.check_board_writable(path, argv=argv, script='zone_fill_check.py')
    board = pcbnew.LoadBoard(path)
    before = snapshot(board)
    ok = refill(board)
    rows = compare(board, before, tol_mm2)
    stale = [r for r in rows if r['stale']]
    if not quiet:
        for r in rows:
            print('%-6s %-12s %-18s %-8s saved %10.3f  fresh %10.3f  xor %8.4f mm2' % (
                'STALE' if r['stale'] else 'ok', r['net'][:12], (r['zone'] or '-')[:18], r['layer'],
                r['saved_mm2'], r['fresh_mm2'], r['xor_mm2']))
        print('%d zone layer(s) checked, %d stale (tolerance %.4f mm2)%s'
              % (len(rows), len(stale), tol_mm2, '' if ok else '; ZONE_FILLER reported a failure'))
    saved = False
    if fix and stale:
        board.Save(path)
        saved = True
        if not quiet:
            print('refilled and saved: %s' % path)
    elif fix and not quiet:
        print('nothing to fix')
    return rows, saved


def refill_saved_board(path, kicad_python=None, label='zones'):
    """For the scripts that write the board as TEXT on the system Python (stitch_planes, repair_import,
    rail_zones): refill and save through KiCad's Python. Prints a reminder when KiCad's Python is not found.
    Returns True when the saved fill is current afterwards."""
    import subprocess
    import kicad_sexp as KS
    kp = KS.find_kicad_python(kicad_python)
    if not kp:
        print('REMINDER: KiCad\'s Python not found - refill the %s and save (zone_fill_check.py %s --fix) '
              'before DRC, Gerbers or a commit' % (label, path))
        return False
    r = subprocess.run([kp, os.path.abspath(__file__), path, '--fix'], capture_output=True, text=True)
    tail = [l for l in (r.stdout or '').splitlines() if l.strip()][-1:]
    if r.returncode == 0:
        print('zone refill: %s' % (tail[0] if tail else 'ok'))
        return True
    print('REMINDER: zone refill failed (exit %d): %s - run zone_fill_check.py %s --fix'
          % (r.returncode, ((r.stderr or '') + ' '.join(tail)).strip()[-300:], path))
    return False


def main():
    a = sys.argv[1:]
    if not a or a[0].startswith('--'):
        sys.stderr.write(__doc__)
        return 2
    path = os.path.abspath(a[0])
    if not os.path.isfile(path):
        sys.stderr.write('no such board: %s\n' % path)
        return 2
    tol = float(a[a.index('--tol') + 1]) if '--tol' in a else 0.01
    fix = '--fix' in a
    rows, saved = check_and_fix(path, fix=fix, tol_mm2=tol, argv=a[1:])
    if '--json' in a:
        with open(a[a.index('--json') + 1], 'w', encoding='utf-8') as f:
            json.dump({'board': path, 'tolerance_mm2': tol, 'fixed': saved, 'zones': rows}, f, indent=1)
    stale = any(r['stale'] for r in rows)
    return 0 if (not stale or saved) else 1


if __name__ == '__main__':
    sys.exit(main())
