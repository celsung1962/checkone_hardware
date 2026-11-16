#!/usr/bin/env python
"""rail_zones.py - build inner-layer polygon zones for interleaved BGA power rails.

Bounding-box splits over interleaved rails are FORBIDDEN (SKILL.md, "Complex Power Plane Splits"):
they starve pads. This builds each rail's outline as a union of buffered via points plus corridors,
which follows the actual ball grouping, and verifies the incumbent plane survives.

  python rail_zones.py <board.kicad_pcb> --nets +1.2V,FPGA_2.5V --layer In2.Cu
                       [--plane-net +3.3V] [--dry-run] [--no-fill]

Requires shapely (optional dependency - install into KiCad's python). Without it the script reports
what it would need and exits 4 rather than guessing with hand-rolled geometry.

Two rules this encodes, both learned the hard way:
  * a zone OUTLINE must never have obstacles subtracted from it - the filler already clears them.
    Subtracting gives hole-riddled slivers (observed: 30x9 mm bbox, 814 vertices, 0.15 mm2 area).
  * the starvation check must test the INCUMBENT plane's connected components, not point containment.
"""
import io, os, re, sys, math, collections, uuid as uuidmod

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kicad_sexp as KS
import board_guard  # noqa: E402
import zone_fill_check  # noqa: E402

try:
    from shapely.geometry import Point, LineString, Polygon, MultiPolygon, box
    from shapely.ops import unary_union
    HAVE_SHAPELY = True
except ImportError:
    HAVE_SHAPELY = False

BUF = 0.95          # merges via points up to 1.9 mm apart
CORRIDOR = 0.5
SIMPLIFY = 0.03
MIN_AREA = 1.0      # mm2
MIN_FILL = 0.08     # area / bbox-area; below this it is a sliver, not a region


def main():
    args = sys.argv[1:]
    if not args or args[0].startswith('--'):
        sys.stderr.write(__doc__)
        return 2
    if not HAVE_SHAPELY:
        sys.stderr.write('shapely is required for this tool.\n'
                         '  "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" -m pip install shapely\n'
                         'Everything else in the skill works without it.\n')
        return 4
    board = os.path.abspath(args[0])
    dry = '--dry-run' in args

    def opt(n, d=None):
        return args[args.index(n) + 1] if n in args else d

    rails = [n.strip() for n in (opt('--nets') or '').split(',') if n.strip()]
    layer = opt('--layer', 'In2.Cu')
    if not rails:
        sys.stderr.write('--nets is required\n')
        return 2

    if not dry:
        board_guard.check_board_writable(board, script='rail_zones.py')   # KiCad lock / .kicad_pro beside it
    B = KS.collect(board)
    R = KS.rules_from_project(board)
    CLEAR, EDGE = R['min_clearance'], R['min_copper_edge_clearance']
    vias, pads, edges = B['vias'], B['pads'], B['edges']

    plane_net = opt('--plane-net')
    if not plane_net:
        cand = [z['net'] for z in B['zones']
                if not z['keepout'] and z['layer'] == layer and z['net'] not in rails]
        plane_net = cand[0] if cand else None
    print('rails: %s   layer: %s   incumbent plane: %s' % (', '.join(rails), layer, plane_net or '(none)'))

    xs = sorted({round(v, 4) for e in edges for v in (e[0], e[2])})
    ys = sorted({round(v, 4) for e in edges for v in (e[1], e[3])})
    interior = box(xs[0] + EDGE, ys[0] + EDGE, xs[-1] - EDGE, ys[-1] - EDGE)
    cut = [LineString([(e[0], e[1]), (e[2], e[3])]).buffer(EDGE) for e in edges
           if not (abs(e[0] - xs[0]) < 1e-3 or abs(e[0] - xs[-1]) < 1e-3
                   or abs(e[1] - ys[0]) < 1e-3 or abs(e[1] - ys[-1]) < 1e-3)]
    if cut:
        interior = interior.difference(unary_union(cut))
    print('usable %s area: %.0f mm2 (%d internal cutout lines)' % (layer, interior.area, len(cut)))

    railpts = {r: sorted({(round(v['x'], 4), round(v['y'], 4)) for v in vias if v['net'] == r})
               for r in rails}
    for r in rails:
        if not railpts[r]:
            print('  %s: no vias on this net - stitch it first (stitch_planes.py)' % r)

    def obstacles(net, half):
        g = [Point(v['x'], v['y']).buffer(v['r'] + CLEAR + half) for v in vias if v['net'] != net]
        g += [Point(p['x'], p['y']).buffer(p['r'] + CLEAR + half)
              for p in pads if p['net'] != net and not p['smd']]
        return unary_union(g) if g else Polygon()

    geoms = {}
    for r in rails:
        pts = railpts[r]
        if not pts:
            continue
        blob = unary_union([Point(p).buffer(BUF, quad_segs=8) for p in pts])
        parts = list(blob.geoms) if isinstance(blob, MultiPolygon) else [blob]
        obs = obstacles(r, CORRIDOR / 2.0)
        added, failed, progress = 0, set(), True
        while len(parts) > 1 and progress:
            progress = False
            cand = sorted((parts[i].distance(parts[j]), i, j)
                          for i in range(len(parts)) for j in range(i + 1, len(parts))
                          if (id(parts[i]), id(parts[j])) not in failed)
            for d, i, j in cand:
                A, Bq = parts[i], parts[j]
                corr = LineString([(A.centroid.x, A.centroid.y), (Bq.centroid.x, Bq.centroid.y)]) \
                    .buffer(CORRIDOR / 2.0, cap_style=2)
                if corr.intersects(obs):      # obstacles VETO a corridor, never cut one
                    failed.add((id(A), id(Bq)))
                    continue
                parts = [x for k, x in enumerate(parts) if k not in (i, j)] + [unary_union([A, Bq, corr])]
                added += 1
                progress = True
                break
        geoms[r] = (unary_union(parts).intersection(interior), added)

    order = sorted(geoms, key=lambda r: geoms[r][0].area)
    prio = {r: len(order) - i for i, r in enumerate(order)}
    final = {}
    print()
    print('rail outlines (exterior ring only; the filler clears foreign copper):')
    for r in order:
        g, added = geoms[r]
        keep = []
        for part in (g.geoms if isinstance(g, MultiPolygon) else [g]):
            p = Polygon(part.exterior).simplify(SIMPLIFY, preserve_topology=True)
            if not p.is_valid:
                p = p.buffer(0)
            if p.is_empty or p.geom_type != 'Polygon':
                continue
            bb = p.bounds
            bba = max((bb[2] - bb[0]) * (bb[3] - bb[1]), 1e-9)
            if p.area < MIN_AREA or p.area / bba < MIN_FILL:
                print('   %-11s piece rejected (sliver): %.2f mm2, fill %.2f' % (r, p.area, p.area / bba))
                continue
            keep.append(p)
        if keep:
            final[r] = keep
            for p in keep:
                bb = p.bounds
                print('   %-11s prio %d  %6.2f mm2  bbox %5.1f x %5.1f  fill %.2f  %3d vertices (%d corridors)'
                      % (r, prio[r], p.area, bb[2] - bb[0], bb[3] - bb[1],
                         p.area / max((bb[2] - bb[0]) * (bb[3] - bb[1]), 1e-9),
                         len(p.exterior.coords) - 1, added))
        else:
            print('   %-11s DROPPED - no usable piece' % r)

    print()
    for r in order:
        if r in final:
            cov = sum(1 for pt in railpts[r] if any(p.buffer(1e-6).contains(Point(pt)) for p in final[r]))
            print('   %-11s covers %d/%d of its vias' % (r, cov, len(railpts[r])))

    # ---- starvation check on the INCUMBENT plane: connected components, not containment ----
    if plane_net and final:
        allr = unary_union([p for r in final for p in final[r]])
        left = interior.difference(allr.buffer(CLEAR))
        pieces = sorted((list(left.geoms) if isinstance(left, MultiPolygon) else [left]),
                        key=lambda p: -p.area)
        pv = [(v['x'], v['y']) for v in vias if v['net'] == plane_net]
        in_main = sum(1 for p in pv if pieces[0].buffer(1e-6).contains(Point(p)))
        print()
        print('%s remainder %.0f mm2 in %d piece(s); %d/%d of its vias in the main piece'
              % (plane_net, left.area, len(pieces), in_main, len(pv)))
        if pv and in_main != len(pv):
            print('REFUSING: would strand %d %s vias' % (len(pv) - in_main, plane_net))
            return 3

    if dry or not final:
        print('[dry-run] nothing written' if dry else 'nothing to write')
        return 0

    s, eol = B['text'], B['eol']

    def zone_block(net, poly, p, idx):
        pts = ''
        for i in range(0, len(poly), 4):
            pts += '\t\t\t\t' + ' '.join('(xy %s %s)' % (round(x, 6), round(y, 6))
                                         for x, y in poly[i:i + 4]) + eol
        nm = re.sub(r'[^A-Za-z0-9_]', '', net.replace('+', '').replace('.', 'V'))
        return eol.join(['\t(zone', '\t\t(net "%s")' % net, '\t\t(layer "%s")' % layer,
                         '\t\t(uuid "%s")' % uuidmod.uuid4(), '\t\t(name "PWR_%s_%s_%d")' % (nm, layer.replace('.', ''), idx),
                         '\t\t(hatch edge 0.5)', '\t\t(priority %d)' % p,
                         '\t\t(connect_pads', '\t\t\t(clearance %s)' % CLEAR, '\t\t)',
                         '\t\t(min_thickness 0.1)', '\t\t(filled_areas_thickness no)',
                         '\t\t(fill yes', '\t\t\t(thermal_gap 0.5)', '\t\t\t(thermal_bridge_width 0.5)',
                         '\t\t\t(island_removal_mode 0)', '\t\t)', '\t\t(polygon', '\t\t\t(pts']) + eol \
            + pts + eol.join(['\t\t\t)', '\t\t)', '\t)']) + eol

    blocks, nz = '', 0
    for r in order:
        for i, p in enumerate(final.get(r, [])):
            ring = [(x, y) for x, y in p.exterior.coords[:-1]]
            if len(ring) < 3:
                continue
            blocks += zone_block(r, ring, prio[r], i)
            nz += 1

    anchor = next(a for _, h, a, _ in B['blocks'] if h == 'zone')
    ls = s.rfind(KS.NL, 0, anchor) + 1
    result = s[:ls] + blocks + s[ls:]
    bak = KS.verify_write(board, s, result, expect_delta={'zone': nz},
                          protect=('footprint', 'gr_line', 'gr_text', 'dimension', 'group', 'setup', 'layers'),
                          backup_suffix='.bak_prerailzones')
    print()
    print('wrote %d zones to %s  (backup %s)' % (nz, board, os.path.basename(bak)))
    if '--no-fill' not in args:
        zone_fill_check.refill_saved_board(board)     # new zones are written unfilled
    else:
        print('REMINDER: --no-fill - refill the zones (zone_fill_check.py --fix) before DRC / Gerbers / commit')
    print('NEXT: kicad-cli pcb drc, then RENDER THE LAYER AND LOOK AT IT.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
