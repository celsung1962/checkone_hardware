#!/usr/bin/env python
"""stitch_planes.py - connect SMD pads to their inner-layer plane with stitching vias.

Freerouting places ZERO vias on plane nets (SKILL.md, "After the Router: Plane Stitching"), so every
surface-mount GND/power pad comes back with no path to its plane. This places one via just outside each
such pad, joined by a short same-layer stub.

Plane nets are DISCOVERED from the board's own non-keepout zones on inner layers - nothing hard-coded.

  python stitch_planes.py <board.kicad_pcb> [--nets GND,+3.3V] [--dry-run] [--report] [--no-fill]

Runs on the system python (no pcbnew needed). After writing, the zones are refilled and the board saved
through KiCad's Python (zone_fill_check.py --fix; --no-fill skips it), then run kicad-cli pcb drc.
The board must have its .kicad_pro beside it and no KiCad lock (board_guard.py).
Via sizes with a drill below fabricator.economical_via_drill_mm (kicad_golden.project.json) are not used
unless fabricator.fine_vias_approved is true (board review rev. 0.2, issue 11).
"""
import io, os, re, sys, math, collections, uuid as uuidmod

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kicad_sexp as KS
import board_guard  # noqa: E402
import zone_fill_check  # noqa: E402

VIA_SIZES = [(0.6, 0.3), (0.45, 0.2), (0.25, 0.15)]      # widest that fits wins; all predefined
DIAG_FIRST = (45, 135, 225, 315, 0, 90, 180, 270)        # diagonal fits fine pitch, orthogonal may not


def economical_sizes(board, sizes):
    """Drop the via sizes whose drill is below the fabricator's economical tier (JLCPCB 4L/6L: 0.2 mm; 0.15 mm
    costs extra), unless the project approved fine vias. No key in the project parameters: unchanged."""
    import json
    pj = os.path.join(os.path.dirname(board), 'kicad_golden.project.json')
    try:
        fab = (json.load(io.open(pj, encoding='utf-8')) or {}).get('fabricator') or {}
    except (OSError, ValueError):
        return list(sizes)
    eco = fab.get('economical_via_drill_mm')
    if not eco or fab.get('fine_vias_approved'):
        return list(sizes)
    keep = [s for s in sizes if s[1] >= float(eco) - 1e-9]
    if len(keep) < len(sizes):
        print('economical via tier: drill >= %.2f mm, not using %s' % (float(eco), [s for s in sizes if s not in keep]))
    return keep or list(sizes)


def main():
    args = sys.argv[1:]
    if not args or args[0].startswith('--'):
        sys.stderr.write(__doc__)
        return 2
    board = os.path.abspath(args[0])
    dry = '--dry-run' in args
    report_only = '--report' in args
    # --wide-search (local fix after 1.16.0): SKILL.md says "widen its search before accepting no clear
    # position". Beyond the default 0.05-0.50 mm past the pad edge, also try 0.75 / 1.0 / 1.5 mm with a
    # longer straight stub from the pad centre; every clearance check still applies to via and stub.
    EXTRAS = (0.05, 0.15, 0.30, 0.50) + ((0.75, 1.0, 1.5) if '--wide-search' in args else ())
    want = None
    if '--nets' in args:
        want = {n.strip() for n in args[args.index('--nets') + 1].split(',') if n.strip()}

    if not dry and not report_only:
        board_guard.check_board_writable(board, script='stitch_planes.py')
    via_sizes = economical_sizes(board, VIA_SIZES)
    B = KS.collect(board)
    R = KS.rules_from_project(board)
    CLEAR = R['min_clearance']
    EDGE = R['min_copper_edge_clearance']
    H2H = R['min_hole_to_hole']
    # drill edge to other-net copper (JLCPCB 0.254). Without it a thin-ring fallback via (0.25/0.15: 0.05 mm
    # ring) placed at copper clearance sits only 0.15 mm from a neighbour's copper - measured on BladeOne,
    # 5 hole_clearance DRC items (local fix after 1.16.0).
    HCLR = R.get('min_hole_clearance', 0.0)
    pads, vias, segs, edges = B['pads'], B['vias'], B['segs'], B['edges']
    # 1.18.0: rule areas (board-level and footprint-internal) that forbid vias or tracks are obstacles; before,
    # a via landed inside a push-button's keepout on ServiceOne
    rules = B.get('rule_areas', [])

    inner = [z for z in B['zones'] if not z['keepout'] and z['layer'].startswith('In')]
    plane_nets = sorted({z['net'] for z in inner if z['net']})
    if want:
        plane_nets = [n for n in plane_nets if n in want]
    if not plane_nets:
        print('no inner-layer plane zones found - nothing to stitch')
        return 0
    print('plane nets discovered from inner-layer zones: %s' % ', '.join(plane_nets))
    print('rules: clearance %.3f  edge %.3f  hole-to-hole %.3f  hole-to-copper %.3f' % (CLEAR, EDGE, H2H, HCLR))

    have = collections.Counter(v['net'] for v in vias)
    tgt = [p for p in pads if p['smd'] and p['net'] in plane_nets]
    print()
    print('%-14s %6s %6s' % ('net', 'SMDs', 'vias'))
    for n in plane_nets:
        print('%-14s %6d %6d' % (n, sum(1 for p in tgt if p['net'] == n), have.get(n, 0)))
    if report_only:
        return 0

    # ---- spatial index ----
    CELL = 2.0

    def cells(x0, y0, x1, y1):
        for cx in range(int(math.floor(min(x0, x1) / CELL)), int(math.floor(max(x0, x1) / CELL)) + 1):
            for cy in range(int(math.floor(min(y0, y1) / CELL)), int(math.floor(max(y0, y1) / CELL)) + 1):
                yield (cx, cy)

    gp, gv, gs, ge = (collections.defaultdict(list) for _ in range(4))
    for i, p in enumerate(pads):
        for c in cells(p['x'] - p['r'], p['y'] - p['r'], p['x'] + p['r'], p['y'] + p['r']):
            gp[c].append(i)
    for i, v in enumerate(vias):
        for c in cells(v['x'] - v['r'], v['y'] - v['r'], v['x'] + v['r'], v['y'] + v['r']):
            gv[c].append(i)
    for i, g in enumerate(segs):
        for c in cells(g['x1'], g['y1'], g['x2'], g['y2']):
            gs[c].append(i)
    for i, e in enumerate(edges):
        for c in cells(e[0], e[1], e[2], e[3]):
            ge[c].append(i)

    def near(grid, x, y, rad):
        out = set()
        for c in cells(x - rad, y - rad, x + rad, y + rad):
            out.update(grid.get(c, ()))
        return out

    def via_ok(x, y, vr, vdrr, net):
        rad = vr + 1.5
        for i in near(gp, x, y, rad):
            p = pads[i]
            need = vr + p['r'] + (0.0 if p['net'] == net else CLEAR)
            if p['net'] != net:
                need = max(need, vdrr + p['r'] + HCLR)          # our drill vs their copper
            if math.hypot(x - p['x'], y - p['y']) < need - 1e-9:
                return False
        for i in near(gv, x, y, rad):
            v = vias[i]
            d = math.hypot(x - v['x'], y - v['y'])
            # hole-to-hole is measured between DRILL EDGES, not centres
            if d - (vdrr + v['dr']) < H2H - 1e-9:
                return False
            if v['net'] != net and d < max(vr + v['r'] + CLEAR, vdrr + v['r'] + HCLR, vr + v['dr'] + HCLR) - 1e-9:
                return False
        for i in near(gs, x, y, rad):
            g = segs[i]
            if g['net'] == net:
                continue
            if KS.pt_seg_dist(x, y, g['x1'], g['y1'], g['x2'], g['y2']) < max(vr + g['r'] + CLEAR, vdrr + g['r'] + HCLR) - 1e-9:
                return False
        for i in near(ge, x, y, vr + EDGE + 1.0):
            e = edges[i]
            if KS.pt_seg_dist(x, y, e[0], e[1], e[2], e[3]) < vr + EDGE - 1e-9:
                return False
        for ra in rules:                                   # a through via is on every copper layer
            if ra['vias'] and ra['poly'] and KS.pt_poly_dist(x, y, ra['poly']) < vr - 1e-9:
                return False
        return True

    def stub_ok(x1, y1, x2, y2, hw, net, layer='F.Cu'):
        L = math.hypot(x2 - x1, y2 - y1)
        n = max(2, int(L / 0.05))
        for j in range(n + 1):
            t = j / float(n)
            px, py = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
            rad = hw + 1.0
            for i in near(gp, px, py, rad):
                p = pads[i]
                if p['net'] != net and math.hypot(px - p['x'], py - p['y']) < hw + p['r'] + CLEAR - 1e-9:
                    return False
            for i in near(gv, px, py, rad):
                v = vias[i]
                if v['net'] != net and math.hypot(px - v['x'], py - v['y']) < max(hw + v['r'] + CLEAR, hw + v['dr'] + HCLR) - 1e-9:
                    return False
            for i in near(gs, px, py, rad):
                g = segs[i]
                if g['net'] != net and KS.pt_seg_dist(px, py, g['x1'], g['y1'], g['x2'], g['y2']) < hw + g['r'] + CLEAR - 1e-9:
                    return False
            for i in near(ge, px, py, hw + EDGE + 1.0):
                e = edges[i]
                if KS.pt_seg_dist(px, py, e[0], e[1], e[2], e[3]) < hw + EDGE - 1e-9:
                    return False
            for ra in rules:
                if ra['tracks'] and ra['poly'] and KS.on_layer(ra['layers'], layer) and KS.pt_poly_dist(px, py, ra['poly']) < hw - 1e-9:
                    return False
        return True

    DIRS = [(math.cos(math.radians(a)), -math.sin(math.radians(a))) for a in DIAG_FIRST]
    new_v, new_s = [], []
    placed, skipped, sizes = collections.Counter(), collections.Counter(), collections.Counter()

    # Idempotency (local fix after 1.16.0): a pad that already has a surface stub from its centre to a same-net
    # via is stitched. Without this a second run - e.g. with --wide-search for the pads the first run skipped -
    # places a second via on every pad (measured on BladeOne: 105 duplicates).
    via_at = {(round(v['x'], 4), round(v['y'], 4), v['net']) for v in vias}

    def stitched(p):
        c = (round(p['x'], 4), round(p['y'], 4))
        for g in segs:
            if g['net'] != p['net']:
                continue
            for a, b in (((g['x1'], g['y1']), (g['x2'], g['y2'])), ((g['x2'], g['y2']), (g['x1'], g['y1']))):
                if (round(a[0], 4), round(a[1], 4)) == c and (round(b[0], 4), round(b[1], 4), p['net']) in via_at:
                    return True
        return False

    already = 0
    for p in tgt:
        net = p['net']
        if stitched(p):
            already += 1
            continue
        lay = p['lays'][0] if p['lays'] and p['lays'][0] in ('F.Cu', 'B.Cu') else 'F.Cu'
        done = False
        for vd, vdr in via_sizes:
            vr, hw = vd / 2.0, min(0.6, vd) / 2.0
            for dx, dy in DIRS:
                for extra in EXTRAS:
                    x = round(p['x'] + dx * (p['r'] + vr + extra), 6)
                    y = round(p['y'] + dy * (p['r'] + vr + extra), 6)
                    if not via_ok(x, y, vr, vdr / 2.0, net):
                        continue
                    if not stub_ok(p['x'], p['y'], x, y, hw, net, lay):
                        continue
                    new_v.append({'x': x, 'y': y, 'd': vd, 'dr': vdr, 'net': net})
                    new_s.append({'x1': p['x'], 'y1': p['y'], 'x2': x, 'y2': y,
                                  'w': hw * 2, 'net': net, 'layer': lay})
                    vias.append({'x': x, 'y': y, 'r': vr, 'dr': vdr / 2.0, 'net': net})
                    for c in cells(x - vr, y - vr, x + vr, y + vr):
                        gv[c].append(len(vias) - 1)
                    segs.append({'x1': p['x'], 'y1': p['y'], 'x2': x, 'y2': y,
                                 'r': hw, 'net': net, 'layer': lay})
                    for c in cells(p['x'], p['y'], x, y):
                        gs[c].append(len(segs) - 1)
                    placed[net] += 1
                    sizes['%.2f/%.2f' % (vd, vdr)] += 1
                    done = True
                    break
                if done:
                    break
            if done:
                break
        if not done:
            skipped[net] += 1

    print()
    print('already stitched (skipped): %d' % already)
    print('placed : %s  (total %d)' % (dict(placed), sum(placed.values())))
    print('skipped: %s  (total %d)  - no clear position around the pad' % (dict(skipped), sum(skipped.values())))
    print('via sizes used: %s' % dict(sizes))
    if dry or not new_v:
        print('[dry-run] nothing written' if dry else 'nothing to write')
        return 0

    s, eol = B['text'], B['eol']

    def seg_block(g):
        return eol.join(['\t(segment', '\t\t(start %s %s)' % (round(g['x1'], 6), round(g['y1'], 6)),
                         '\t\t(end %s %s)' % (round(g['x2'], 6), round(g['y2'], 6)),
                         '\t\t(width %s)' % g['w'], '\t\t(layer "%s")' % g['layer'],
                         '\t\t(net "%s")' % g['net'], '\t\t(uuid "%s")' % uuidmod.uuid4(), '\t)']) + eol

    def via_block(v):
        return eol.join(['\t(via', '\t\t(at %s %s)' % (v['x'], v['y']), '\t\t(size %s)' % v['d'],
                         '\t\t(drill %s)' % v['dr'], '\t\t(layers "F.Cu" "B.Cu")',
                         '\t\t(remove_unused_layers yes)', '\t\t(keep_end_layers yes)',
                         '\t\t(net "%s")' % v['net'], '\t\t(uuid "%s")' % uuidmod.uuid4(), '\t)']) + eol

    anchor = next((a for _, h, a, _ in B['blocks'] if h in ('zone', 'group')), None)
    assert anchor is not None, 'no zone/group block to insert before'
    ls = s.rfind(KS.NL, 0, anchor) + 1
    result = s[:ls] + ''.join(seg_block(g) for g in new_s) + ''.join(via_block(v) for v in new_v) + s[ls:]

    bak = KS.verify_write(board, s, result,
                          expect_delta={'segment': len(new_s), 'via': len(new_v)},
                          backup_suffix='.bak_prestitch')
    print()
    print('written: %s  (backup %s)' % (board, os.path.basename(bak)))
    if '--no-fill' not in args:
        zone_fill_check.refill_saved_board(board)     # the SAVED fill must be current (board review rev. 0.2, issue 1)
    else:
        print('REMINDER: --no-fill - refill the zones (zone_fill_check.py --fix) before DRC / Gerbers / commit')
    print('NEXT: kicad-cli pcb drc.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
