#!/usr/bin/env python
"""plane_plan.py - plan the inner power planes before routing (lesson L23, ServiceOne review issue 13).

The power planes are planned, not taken as given. This tool proposes islands of a rail on an inner layer, measures
the trade-offs, writes the decided islands as zones, and checks them after the fill. The designer decides: the
`map` output is a proposal. Its JSON is pasted, edited or replaced by a hand-drawn outline in `plane_plan` of
kicad_golden.project.json.

  plane_plan.py map   <board> [--layer In2.Cu] [--rails A,B] [--cluster-mm 6] [--min-pads 3] [--out DIR]
  plane_plan.py apply <board> [--params FILE] [--dry-run]
  plane_plan.py check <board> [--params FILE] [--json FILE]

map (read-only): for each rail, its pads are clustered. Every cluster of >= --min-pads pads gives a candidate
island: the convex hull of the pads + 1 mm, inside the board less the edge clearance. Each candidate is measured:
  pads served         rail pads inside the outline, and how many still need their own via to the island
  voltage / gap       from the net name (or --voltage NET=V), gap from plane_plan.gap_by_voltage
  crossings           tracks of other nets on the ADJACENT signal layer that cross the island outline (a split under
                      a signal breaks its return path: route away or add a stitching capacitor)
  main plane          pieces of the main plane after cutting the island + gap, and the thin main-plane copper
                      (narrower than min_neck_mm, morphological opening) left within 3 mm of the island
  sense vias          vias of a Kelvin sense path of the same net (layout_checks.kelvin) inside the island: through
                      the island the sense line would share copper with the load - move those vias out
                      or notch the island around them
It writes <out>/plane_plan_<layer>.png, plane_plan_<layer>.md (trade-off table) and plane_plan_<layer>.json
(`islands` entries ready for kicad_golden.project.json -> plane_plan.islands).

apply (writes the board, board_guard + zone refill): for every plane_plan.islands entry, a zone named after the
island on its layer and net, priority above the layer's main plane, clearance = the island gap, other zone settings
copied from the main plane. A zone with the same name is edited in place (idempotent; zones are never removed
through the API - on KiCad 10.0 that saved a lone via under another net). Item nets are compared after the save
and the board is restored if one changed.

check (read-only, exit 1 on FAIL): after the fill, per island zone -
  FAIL the island fills to nothing, or a filled piece has no pad or via of its net (isolated copper)
  FAIL the main plane of the layer falls into more pieces than before the islands (the island splits it)
  FAIL a Kelvin check (layout_checks.kelvin) of the island's net fails (the island joined sense and load)
  WARN island copper, or main-plane copper within 3 mm of the island, narrower than plane_plan.min_neck_mm
  WARN tracks of other nets on the adjacent signal layer crossing the island outline
  WARN rail pads inside the island with no via of their own within 2 mm (the island does not reach them)

Rules (plane_plan block, defaults in brackets): never_split [GND] - map refuses to propose an island on a layer
whose main plane is listed; gap_by_voltage [<=5 V 0.3, <=30 V 0.5, <=60 V 1.0, else 2.0 mm]; min_neck_mm [1.0].
Needs KiCad's Python with shapely and matplotlib (map picture).
"""
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import pcbnew  # noqa: E402

try:
    from shapely.geometry import LineString, Point, Polygon, MultiPolygon
    from shapely.ops import unary_union
except ImportError:  # pragma: no cover
    sys.exit('plane_plan.py needs shapely in KiCad\'s Python (pip install shapely into it)')

M = pcbnew.ToMM
DEF_GAPS = [{"max_v": 5, "gap_mm": 0.3}, {"max_v": 30, "gap_mm": 0.5}, {"max_v": 60, "gap_mm": 1.0},
            {"max_v": 1000, "gap_mm": 2.0}]
RE_SUPPLY = re.compile(r'^[+-]?\d+(?:[.pv]\d+)?v\d*$|(?:^|[_/+-])(?:vcc|vdd|vbus|vsys|vin|vout|vbat|batt|bat|avdd|dvdd)'
                       r'(?:$|[_0-9])', re.I)


def opt(args, name, default=None):
    return args[args.index(name) + 1] if name in args else default


def params_for(board_path, args):
    p = opt(args, '--params') or os.path.join(os.path.dirname(os.path.abspath(board_path)), 'kicad_golden.project.json')
    return (json.load(open(p, encoding='utf-8')) if os.path.isfile(p) else {}), p


def voltage_of(net, overrides):
    if net in overrides:
        return overrides[net]
    m = re.search(r'(\d+)V(\d+)', net, re.I)            # 3V3
    if m:
        return float(m.group(1) + '.' + m.group(2))
    m = re.search(r'(\d+(?:[.,]\d+)?)V', net, re.I)      # +3.3V, -24V, +24V_SW
    return float(m.group(1).replace(',', '.')) if m else None


def gap_for(volts, plan):
    table = plan.get('gap_by_voltage') or DEF_GAPS
    if volts is None:
        return max(t['gap_mm'] for t in table if t['max_v'] <= 30) if table else 0.5
    for t in sorted(table, key=lambda t: t['max_v']):
        if volts <= t['max_v']:
            return t['gap_mm']
    return table[-1]['gap_mm']


# ------------------------------------------------------------------ board geometry
def poly_of(chain):
    pts = [(M(chain.CPoint(i).x), M(chain.CPoint(i).y)) for i in range(chain.PointCount())]
    return Polygon(pts) if len(pts) >= 3 else None


def polyset(ps):
    out = []
    for i in range(ps.OutlineCount()):
        o = poly_of(ps.Outline(i))
        if o is None:
            continue
        holes = [poly_of(ps.Hole(i, j)) for j in range(ps.HoleCount(i))]
        out.append(Polygon(o.exterior.coords, [h.exterior.coords for h in holes if h is not None]))
    return unary_union(out) if out else Polygon()


def board_area(b):
    ps = pcbnew.SHAPE_POLY_SET()
    b.GetBoardPolygonOutlines(ps, True)
    return polyset(ps).buffer(0)


def copper_layers(b):
    order = [pcbnew.F_Cu] + [getattr(pcbnew, 'In%d_Cu' % i) for i in range(1, 31)] + [pcbnew.B_Cu]
    return [l for l in order if b.IsLayerEnabled(l)]


def zones_on(b, L):
    return [z for z in b.Zones() if not z.GetIsRuleArea() and z.IsOnLayer(L) and z.GetNetname()]


def main_net(b, L, plan):
    name = b.GetLayerName(L)
    fixed = (plan.get('main_planes') or {}).get(name)
    if fixed:
        return fixed
    zs = zones_on(b, L)
    if not zs:
        return None
    return max(zs, key=lambda z: polyset(z.Outline()).area).GetNetname()


def plane_layers(b):
    return [L for L in copper_layers(b) if L not in (pcbnew.F_Cu, pcbnew.B_Cu) and zones_on(b, L)]


def adjacent_signal(b, L):
    cu = copper_layers(b)
    planes = set(plane_layers(b))
    i = cu.index(L)
    out = []
    for j in (i - 1, i + 1):
        if 0 <= j < len(cu) and cu[j] not in planes:
            out.append(cu[j])
    return out


def rail_pads(b, net):
    out = []
    for f in b.GetFootprints():
        for p in f.Pads():
            if p.GetNetname() == net:
                q = p.GetPosition()
                out.append(('%s.%s' % (f.GetReference(), p.GetNumber()), M(q.x), M(q.y), p))
    return out


def crossings(b, outline, layers, own_net):
    hits = []
    edge = outline.boundary
    for t in b.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T or t.GetLayer() not in layers or t.GetNetname() == own_net:
            continue
        s, e = t.GetStart(), t.GetEnd()
        ls = LineString([(M(s.x), M(s.y)), (M(e.x), M(e.y))])
        if ls.intersects(edge):
            hits.append(t.GetNetname())
    return hits


def slivers(region, near, min_w):
    """Copper of `region` narrower than min_w (morphological opening residue) within `near`: [(area, width)]."""
    if region.is_empty:
        return []
    opened = region.buffer(-min_w / 2).buffer(min_w / 2)
    out = []
    for p in pieces(region.difference(opened).intersection(near)):
        if p.area > 0.3 and p.length > 0:
            out.append((round(p.area, 2), round(2 * p.area / p.length, 2)))
    return out


def plane_region(b, L, main, inner, skip_names=()):
    """Where the main plane can pour on L: its zone outlines inside the board, less the other zones on L (with their
    clearance), except zones named in skip_names (the islands being judged)."""
    mains = [z for z in zones_on(b, L) if z.GetNetname() == main]
    reg = unary_union([polyset(z.Outline()) for z in mains]).intersection(inner) if mains else inner
    others = [z for z in zones_on(b, L) if z.GetNetname() != main and z.GetZoneName() not in skip_names]
    if others:
        reg = reg.difference(unary_union([polyset(z.Outline()).buffer(M(z.GetLocalClearance() or 0))
                                          for z in others]))
    return reg


def island_name(rail, n):
    tag = re.sub(r'[^A-Za-z0-9]+', '', rail.replace('+', 'P').replace('-', 'N', 1) if rail[:1] in '+-' else rail)
    return 'PP_%s_%d' % (tag or 'NET', n)


def pieces(geom):
    return [] if geom.is_empty else list(getattr(geom, 'geoms', [geom]))


def sense_vias(board_path, net, kelvin, LM=None):
    """Vias on the sense path of every Kelvin check of this net: [(check, x, y)]."""
    out = []
    checks = [k for k in kelvin if k.get('sense')]
    if not checks:
        return out
    import layout_measure
    LM = LM or layout_measure.Board(board_path)
    for k in checks:
        try:
            if LM.pad(k['sense']).GetNetname() != net:
                continue
        except SystemExit:
            continue
        r = LM.shortest(net, k['sense'], k['shunt'])
        if r is None:
            continue
        nodes, _ = LM.graph(net)
        for key in r[3]:
            if nodes[key][2] == 'via':
                out.append(('%s-%s' % (k['sense'], k['shunt']), nodes[key][0], nodes[key][1]))
    return out


# ------------------------------------------------------------------ map
def cmd_map(path, args):
    params, ppath = params_for(path, args)
    plan = params.get('plane_plan') or {}
    b = pcbnew.LoadBoard(path)
    layer_name = opt(args, '--layer', 'In2.Cu')
    L = b.GetLayerID(layer_name)
    if L < 0 or not b.IsLayerEnabled(L):
        sys.exit('layer %s not on the board' % layer_name)
    main = main_net(b, L, plan)
    never = plan.get('never_split') or ['GND']
    if main in never:
        sys.exit('%s carries the %s plane, listed in never_split: no islands are proposed there' % (layer_name, main))
    overrides = {}
    for v in [a for i, a in enumerate(args) if i and args[i - 1] == '--voltage']:
        n, val = v.rsplit('=', 1)
        overrides[n] = float(val)
    cluster = float(opt(args, '--cluster-mm', '6'))
    minp = int(opt(args, '--min-pads', '3'))
    edge_cl = max(0.5, M(b.GetDesignSettings().m_CopperEdgeClearance))
    area = board_area(b)
    inner = area.buffer(-(edge_cl + 0.1))
    main_region = plane_region(b, L, main, inner)
    min_w = float(plan.get('min_neck_mm', 1.0))
    planes_of = {main_net(b, l, plan) for l in plane_layers(b)}
    if opt(args, '--rails'):
        rails = [r for r in opt(args, '--rails').split(',') if r]
    else:
        rails = []
        for n in sorted({p.GetNetname() for f in b.GetFootprints() for p in f.Pads()}):
            if not n or n in planes_of or n in never or n.startswith(('unconnected-', 'Net-(')):
                continue
            ni = b.FindNet(n)
            cls = ni.GetNetClassName() if ni and hasattr(ni, 'GetNetClassName') else ''
            if cls.upper().startswith('POWER') or RE_SUPPLY.search(n):
                rails.append(n)
    adj = adjacent_signal(b, L)
    kelvin = (params.get('layout_checks') or {}).get('kelvin') or []
    LM = None
    if kelvin:
        import layout_measure
        LM = layout_measure.Board(path)
    vias_by_net = {}
    for t in b.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            q = t.GetPosition()
            vias_by_net.setdefault(t.GetNetname(), []).append((M(q.x), M(q.y)))
    cands = []
    for rail in rails:
        pads = rail_pads(b, rail)
        if len(pads) < minp:
            continue
        # single-linkage clusters
        groups, seen = [], set()
        for i, p in enumerate(pads):
            if i in seen:
                continue
            stack, g = [i], []
            seen.add(i)
            while stack:
                k = stack.pop()
                g.append(k)
                for j, q in enumerate(pads):
                    if j not in seen and math.hypot(q[1] - pads[k][1], q[2] - pads[k][2]) <= cluster:
                        seen.add(j)
                        stack.append(j)
            groups.append([pads[k] for k in g])
        sv_all = sense_vias(path, rail, kelvin, LM) if kelvin else []
        volts = voltage_of(rail, overrides)
        gap = gap_for(volts, plan)
        n = 0
        for g in groups:
            if len(g) < minp:
                continue
            hull = unary_union([Point(x, y).buffer(1.0) for _, x, y, _ in g]).convex_hull.buffer(0.5)
            outline = hull.intersection(main_region).buffer(0).simplify(0.05)
            if outline.is_empty or outline.area < 4:
                continue
            if isinstance(outline, MultiPolygon):
                outline = max(outline.geoms, key=lambda p: p.area)
            n += 1
            name = island_name(rail, n)
            served = [t for t, x, y, _ in pads if outline.contains(Point(x, y))]
            own_vias = vias_by_net.get(rail, [])
            no_via = [t for t, x, y, p in pads if outline.contains(Point(x, y)) and
                      not any(math.hypot(vx - x, vy - y) <= 2.0 for vx, vy in own_vias)]
            cut = main_region.difference(outline.buffer(gap))
            main_pieces = len(pieces(cut))
            sv = [s for s in sv_all if outline.buffer(gap).contains(Point(s[1], s[2]))]
            thin = slivers(cut, outline.buffer(gap + 3), min_w)
            cr = crossings(b, outline, adj, rail)
            cands.append({
                'name': name, 'rail': rail, 'layer': layer_name, 'voltage_v': volts, 'gap_mm': gap,
                'area_mm2': round(outline.area, 1), 'pads_served': served, 'pads_without_own_via': no_via,
                'crossings_adjacent': len(cr), 'crossing_nets': sorted(set(cr)),
                'main_plane_pieces': main_pieces, 'main_plane_slivers': [{'area_mm2': a, 'width_mm': w} for a, w in thin],
                'sense_vias_inside': [{'check': c, 'x': round(x, 3), 'y': round(y, 3)} for c, x, y in sv],
                'outline': [[round(x, 3), round(y, 3)] for x, y in list(outline.exterior.coords)[:-1]],
            })
    out = opt(args, '--out') or os.path.join(os.path.dirname(os.path.abspath(path)), 'plane_plan')
    os.makedirs(out, exist_ok=True)
    stem = os.path.join(out, 'plane_plan_' + layer_name.replace('.', '_'))
    base_pieces = len(pieces(main_region))
    json.dump({'layer': layer_name, 'main_plane': main, 'adjacent_signal_layers': [b.GetLayerName(l) for l in adj],
               'main_plane_pieces_before': base_pieces, 'min_neck_mm': min_w,
               'islands': cands}, open(stem + '.json', 'w', encoding='utf-8'), indent=1)
    rows = ['# Plane plan proposal - %s (main plane %s, adjacent signal layer %s)' %
            (layer_name, main, ', '.join(b.GetLayerName(l) for l in adj) or '-'), '',
            'Proposal only: the designer decides, edits or draws each outline, then records it in '
            '`plane_plan.islands` (kicad_golden.project.json). Main plane before: %d piece(s); thin copper = main plane '
            'narrower than %s mm left beside the island.' % (base_pieces, min_w), '',
            '| Island | Rail | V | Gap | Area mm2 | Pads served | Pads without own via | Adjacent crossings | '
            'Main plane pieces | Thin main copper | Sense vias inside |', '|' + '---|' * 11]
    for c in cands:
        rows.append('| %s | %s | %s | %s | %s | %d (%s) | %d | %d %s | %d | %s | %d |' % (
            c['name'], c['rail'], c['voltage_v'], c['gap_mm'], c['area_mm2'], len(c['pads_served']),
            ', '.join(c['pads_served'][:8]) + (' ...' if len(c['pads_served']) > 8 else ''),
            len(c['pads_without_own_via']), c['crossings_adjacent'],
            ('(' + ', '.join(c['crossing_nets'][:5]) + ')') if c['crossing_nets'] else '',
            c['main_plane_pieces'], _thin(c), len(c['sense_vias_inside'])))
    if not cands:
        rows.append('| - | no rail with %d+ clustered pads on this layer | | | | | | | | | |' % minp)
    rows += ['', 'Reading the table: more than one main-plane piece means the island splits the main plane; '
             'crossings are signals on the adjacent layer that lose their return path at the split; a sense via '
             'inside the island joins the sense line to the load copper through the island (move it out or notch '
             'the island around it).']
    open(stem + '.md', 'w', encoding='utf-8').write('\n'.join(rows) + '\n')
    try:
        _picture(b, area, main_region, cands, adj, stem + '.png', layer_name, main)
    except Exception as e:  # picture is a convenience
        print('picture skipped: %s' % e)
    print('%s: main plane %s, %d candidate island(s) -> %s.{md,json,png}' % (layer_name, main, len(cands), stem))
    for c in cands:
        print('  %-14s %-10s pads %2d  no-via %2d  crossings %2d  main pieces %d  thin %s  sense vias %d' % (
            c['name'], c['rail'], len(c['pads_served']), len(c['pads_without_own_via']), c['crossings_adjacent'],
            c['main_plane_pieces'], _thin(c), len(c['sense_vias_inside'])))
    return 0


def _thin(c):
    t = c['main_plane_slivers']
    return '-' if not t else '%d (%.1f mm2, min ~%.2f mm)' % (len(t), sum(x['area_mm2'] for x in t),
                                                             min(x['width_mm'] for x in t))


def _picture(b, area, main_region, cands, adj, png, layer_name, main):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(14, 7.5))

    def draw(g, **kw):
        for p in pieces(g):
            if isinstance(p, Polygon):
                x, y = p.exterior.xy
                ax.fill(x, y, **kw)
    draw(area, color='#eeeeee')
    draw(main_region, color='#cfe3f7', label='main plane ' + main)
    colours = ['#f4a259', '#8cb369', '#bc4b51', '#5b8e7d', '#9b5de5']
    for i, c in enumerate(cands):
        poly = Polygon(c['outline'])
        draw(poly, color=colours[i % len(colours)], alpha=0.6)
        ax.text(poly.centroid.x, poly.centroid.y, '%s\n%s' % (c['name'], c['rail']), ha='center', va='center',
                fontsize=8)
        for s in c['sense_vias_inside']:
            ax.plot(s['x'], s['y'], 'kx', ms=9, mew=2)
    for t in b.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T or t.GetLayer() not in adj:
            continue
        s, e = t.GetStart(), t.GetEnd()
        ax.plot([M(s.x), M(e.x)], [M(s.y), M(e.y)], color='#777777', lw=0.4)
    ax.set_aspect('equal')
    ax.invert_yaxis()
    ax.set_title('Plane plan proposal %s (grey lines: tracks on the adjacent signal layer; x: sense vias inside)'
                 % layer_name)
    fig.tight_layout()
    fig.savefig(png, dpi=110)


# ------------------------------------------------------------------ apply
def cmd_apply(path, args):
    import board_guard
    import zone_fill_check
    params, ppath = params_for(path, args)
    plan = params.get('plane_plan') or {}
    islands = plan.get('islands') or []
    if not islands:
        sys.exit('no plane_plan.islands in %s' % ppath)
    dry = '--dry-run' in args
    if not dry:
        board_guard.check_board_writable(path, script='plane_plan.py apply')
    b = pcbnew.LoadBoard(path)
    # An island zone already on the board is edited in place, never removed: removing a zone through the Python
    # API saved a lone via of that net under another net (seen on KiCad 10.0). Item nets are compared after the
    # save, from the file, and the board is restored when one changed.
    nets_before = {t.m_Uuid.AsString(): t.GetNetname() for t in b.GetTracks()}
    existing = {}
    for zz in b.Zones():
        if not zz.GetIsRuleArea() and zz.GetZoneName():
            existing.setdefault(zz.GetZoneName(), zz)
    made, reused = [], 0
    for isl in islands:
        L = b.GetLayerID(isl['layer'])
        net = b.FindNet(isl['rail'])
        if L < 0 or net is None:
            sys.exit('island %s: layer %s or net %s not on the board' % (isl['name'], isl['layer'], isl['rail']))
        main = main_net(b, L, plan)
        ref = next((zz for zz in zones_on(b, L) if zz.GetNetname() == main), None)
        gap = isl.get('gap_mm') or gap_for(isl.get('voltage_v') or voltage_of(isl['rail'], {}), plan)
        made.append((isl['name'], isl['layer'], isl['rail'], gap, len(isl['outline'])))
        if dry:
            continue
        z = existing.get(isl['name'])
        if z is None:
            z = pcbnew.ZONE(b)
            b.Add(z)
        else:
            reused += 1
        z.SetLayer(L)
        z.SetNetCode(net.GetNetCode())
        z.SetZoneName(isl['name'])
        o = z.Outline()
        o.RemoveAllContours()
        o.NewOutline()
        for x, y in isl['outline']:
            o.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
        z.SetLocalClearance(pcbnew.FromMM(gap))
        if ref is not None:
            z.SetAssignedPriority(ref.GetAssignedPriority() + 1)
            z.SetMinThickness(ref.GetMinThickness())
            z.SetThermalReliefGap(ref.GetThermalReliefGap())
            z.SetThermalReliefSpokeWidth(ref.GetThermalReliefSpokeWidth())
            z.SetPadConnection(ref.GetPadConnection())
    if dry:
        for m in made:
            print('would write zone %s on %s, net %s, gap %s mm, %d vertices' % m)
        return 0
    backup = open(path, 'rb').read()
    zone_fill_check.refill(b)
    b.Save(path)
    b2 = pcbnew.LoadBoard(path)
    changed = [(nets_before[t.m_Uuid.AsString()], t.GetNetname(), M(t.GetPosition().x), M(t.GetPosition().y))
               for t in b2.GetTracks() if nets_before.get(t.m_Uuid.AsString(), t.GetNetname()) != t.GetNetname()]
    if changed:
        open(path, 'wb').write(backup)
        for c in changed[:10]:
            print('  net changed %s -> %s at (%.3f, %.3f)' % c)
        sys.exit('plane_plan.py apply: %d item net(s) changed on save - board restored, nothing written' % len(changed))
    for m in made:
        print('zone %s on %s, net %s, gap %s mm, %d vertices' % m)
    print('%d island zone(s) edited in place, %d new; zones refilled and saved; item nets unchanged' %
          (reused, len(made) - reused))
    return 0


# ------------------------------------------------------------------ check
def cmd_check(path, args):
    params, ppath = params_for(path, args)
    plan = params.get('plane_plan') or {}
    islands = plan.get('islands') or []
    minneck = float(plan.get('min_neck_mm', 1.0))
    import layout_measure
    LM = layout_measure.Board(path)        # loads and fills the zones in memory
    b = LM.b
    res, fails = [], 0

    def add(level, msg, **kw):
        nonlocal fails
        fails += level == 'FAIL'
        res.append(dict(level=level, msg=msg, **kw))
        print('%-4s %s' % (level, msg))
    kelvin = (params.get('layout_checks') or {}).get('kelvin') or []
    inner = board_area(b).buffer(-(max(0.5, M(b.GetDesignSettings().m_CopperEdgeClearance)) + 0.1))
    for isl in islands:
        L = b.GetLayerID(isl['layer'])
        zs = [z for z in zones_on(b, L) if z.GetZoneName() == isl['name']] or \
             [z for z in zones_on(b, L) if z.GetNetname() == isl['rail'] and z.GetNetname() != main_net(b, L, plan)]
        if not zs:
            add('WARN', '%s: no zone on the board (run plane_plan.py apply)' % isl['name'])
            continue
        fill = unary_union([polyset(z.GetFilledPolysList(L)) for z in zs])
        own = [(x, y) for t, x, y, p in rail_pads(b, isl['rail']) if p.IsOnLayer(L)]
        vias = [(M(t.GetPosition().x), M(t.GetPosition().y)) for t in b.GetTracks()
                if t.Type() == pcbnew.PCB_VIA_T and t.GetNetname() == isl['rail']]
        if fill.is_empty:
            add('FAIL', '%s: the island fills to nothing - no pad or via of %s reaches %s inside it' %
                (isl['name'], isl['rail'], isl['layer']))
        for pc in pieces(fill):
            if not any(pc.buffer(0.05).contains(Point(x, y)) for x, y in own + vias):
                add('FAIL', '%s: isolated island copper (%.1f mm2) with no pad or via of %s' %
                    (isl['name'], pc.area, isl['rail']))
        outline = unary_union([polyset(z.Outline()) for z in zs])
        gap = isl.get('gap_mm') or gap_for(isl.get('voltage_v') or voltage_of(isl['rail'], {}), plan)
        thin = slivers(outline.intersection(inner), outline, minneck)
        if thin:
            add('WARN', '%s: island copper narrower than %.2f mm (%d place(s), min ~%.2f mm)' %
                (isl['name'], minneck, len(thin), min(w for _, w in thin)))
        main = main_net(b, L, plan)
        names_here = {i['name'] for i in islands if i['layer'] == isl['layer']}
        before = len(pieces(plane_region(b, L, main, inner, skip_names=names_here)))
        reg = plane_region(b, L, main, inner)
        after = len(pieces(reg))
        if after > before:
            add('FAIL', '%s: the %s plane on %s is in %d pieces (%d without the islands) - the island splits it' %
                (isl['name'], main, isl['layer'], after, before))
        thin = slivers(reg, outline.buffer(gap + 3), minneck)
        if thin:
            add('WARN', '%s: %s plane narrower than %.2f mm beside the island (%d place(s), min ~%.2f mm)' %
                (isl['name'], main, minneck, len(thin), min(w for _, w in thin)))
        cr = crossings(b, outline, adjacent_signal(b, L), isl['rail'])
        if cr:
            add('WARN', '%s: %d track(s) on the adjacent signal layer cross the island outline (%s) - route away or '
                'add a stitching capacitor' % (isl['name'], len(cr), ', '.join(sorted(set(cr))[:6])))
        far = [t for t, x, y, p in rail_pads(b, isl['rail']) if outline.contains(Point(x, y)) and
               not any(math.hypot(vx - x, vy - y) <= 2.0 for vx, vy in vias)]
        if far:
            add('WARN', '%s: %d pad(s) inside the island without their own via within 2 mm: %s' %
                (isl['name'], len(far), ', '.join(far[:8])))
        for k in kelvin:
            try:
                if LM.pad(k['sense']).GetNetname() != isl['rail']:
                    continue
            except SystemExit:
                continue
            r = LM.kelvin(k['sense'], k['shunt'], k['load'])
            if not r.get('pass'):
                add('FAIL', '%s: Kelvin %s/%s fails with the island (shared %s mm, bypass %s) - '
                    'move the sense vias out of %s or notch the island around them' % (isl['name'], k['sense'], k['shunt'], r.get('shared_mm'),
                                                   r.get('bypass'), isl['layer']))
    if not islands:
        print('no plane_plan.islands in %s - nothing to check' % ppath)
    if opt(args, '--json'):
        json.dump(res, open(opt(args, '--json'), 'w', encoding='utf-8'), indent=1)
    print('plane plan check: %d FAIL, %d WARN' % (fails, sum(1 for r in res if r['level'] == 'WARN')))
    return 1 if fails else 0


def main():
    a = sys.argv[1:]
    if len(a) < 2 or a[0] not in ('map', 'apply', 'check') or a[0] in ('-h', '--help'):
        print(__doc__)
        return 0 if a and a[0] in ('-h', '--help') else 2
    return {'map': cmd_map, 'apply': cmd_apply, 'check': cmd_check}[a[0]](a[1], a[2:])


if __name__ == '__main__':
    sys.exit(main())
