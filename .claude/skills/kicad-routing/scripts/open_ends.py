#!/usr/bin/env python
"""open_ends.py - the real copper ends of every open connection, for routing or a hand-off list (lesson L31; ServiceOne
D133 finishing, 2026-10-22).

MUST be run with KiCad's own Python (pcbnew).

A DRC unconnected item gives two item positions, and for a track that position is not on the track: a route to it
ends on nothing (ServiceOne: 23 of 41 finishing attempts were reverted with no connection gained). This tool builds,
for every unconnected item of a DRC report, the two copper islands of the connection from the real geometry of the
net - a track end joins an item whose copper contains it, a via joins the tracks ending in it and the pads it sits in,
and on a plane net (a net with a filled zone) every via is one island with the plane - and lists the best end pairs
to route between: pads (route pad-to-pad, axial entry), free track ends (touching nothing else) and vias, ranked by
distance (pads and free ends first on ties).

Usage: open_ends.py BOARD DRC.json OUT.json [--pairs 3]
    DRC.json from kicad-cli pcb drc --format json --severity-all
OUT.json: [{"net", "k", "pairs": [{"dist", "a": {"kind": pad|free|via, "pad": "R1.2"|null, "xy": [x, y]}, "b": ...}]}]
Feed a pair to route_finish.py (--from-pad / --to-pad for pads, --from / --to for coordinates), or hand the list to
the interactive router with the board (L29: a hand-off lists every open connection with its ends).
Read-only.
"""
import json, math, sys
import pcbnew

mm, nm = pcbnew.ToMM, pcbnew.FromMM
if len(sys.argv) < 4 or sys.argv[1].startswith('-'):
    sys.stdout.write(__doc__)
    sys.exit(2)
BOARD, DRCJ, OUT = sys.argv[1:4]
NP = int(sys.argv[sys.argv.index('--pairs') + 1]) if '--pairs' in sys.argv else 3
b = pcbnew.LoadBoard(BOARD)
PLANE = {b.GetArea(i).GetNetname() for i in range(b.GetAreaCount()) if not b.GetArea(i).GetIsRuleArea()}
uuid_of = lambda x: x.m_Uuid.AsString()


def net_items(net):
    tr, vi, pa = [], [], []
    for t in b.GetTracks():
        if t.GetNetname() != net:
            continue
        (vi if t.GetClass() == 'PCB_VIA' else tr).append(t)
    for fp in b.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() == net:
                pa.append(p)
    return tr, vi, pa


def seg_dist(p, a, c):
    ax, ay, bx, by, px, py = a.x, a.y, c.x, c.y, p.x, p.y
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def islands(net):
    tr, vi, pa = net_items(net)
    items = tr + vi + pa
    idx = {uuid_of(x): i for i, x in enumerate(items)}
    par = list(range(len(items)))

    def f(i):
        while par[i] != i:
            par[i] = par[par[i]]
            i = par[i]
        return i

    def u(i, j):
        par[f(i)] = f(j)

    free = {}
    for t in tr:
        L = t.GetLayer()
        for end in (t.GetStart(), t.GetEnd()):
            touch = 0
            for o in tr:
                if o is t or uuid_of(o) == uuid_of(t) or o.GetLayer() != L:
                    continue
                if seg_dist(end, o.GetStart(), o.GetEnd()) <= o.GetWidth() / 2:
                    u(idx[uuid_of(t)], idx[uuid_of(o)]); touch += 1
            for v in vi:
                if (end - v.GetPosition()).EuclideanNorm() <= v.GetWidth(pcbnew.F_Cu) / 2:
                    u(idx[uuid_of(t)], idx[uuid_of(v)]); touch += 1
            for p in pa:
                if p.IsOnLayer(L) and p.HitTest(end):
                    u(idx[uuid_of(t)], idx[uuid_of(p)]); touch += 1
            if not touch:
                free[(uuid_of(t), end.x, end.y)] = (t, end)
    for v in vi:
        for p in pa:
            if p.HitTest(v.GetPosition()):
                u(idx[uuid_of(v)], idx[uuid_of(p)])
    if net in PLANE and vi:
        for v in vi[1:]:
            u(idx[uuid_of(v)], idx[uuid_of(vi[0])])
        for p in pa:
            if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
                u(idx[uuid_of(p)], idx[uuid_of(vi[0])])
    groups = {}
    for i, x in enumerate(items):
        groups.setdefault(f(i), []).append(x)
    return idx, f, groups, free


def cands(group, free):
    out = []
    for x in group:
        if isinstance(x, pcbnew.PAD):
            c = x.GetPosition()
            out.append(('pad', '%s.%s' % (x.GetParentFootprint().GetReference(), x.GetNumber()), c, 0))
        elif x.GetClass() == 'PCB_VIA':
            out.append(('via', None, x.GetPosition(), 2))
    for (uu, _, _), (t, end) in free.items():
        if any(uuid_of(t) == uuid_of(x) for x in group):
            out.append(('free', None, end, 1))
    return out


res = []
d = json.load(open(DRCJ, encoding='utf-8'))
for k, un in enumerate(d['unconnected_items']):
    A, B = un['items'][0], un['items'][1]
    net = A['description'].split('[')[1].split(']')[0]
    idx, f, groups, free = islands(net)
    ga, gb = idx.get(A['uuid']), idx.get(B['uuid'])
    if ga is None or gb is None or f(ga) == f(gb):
        res.append({'net': net, 'k': k, 'pairs': [], 'note': 'items not found or same island'})
        continue
    ca, cb = cands(groups[f(ga)], free), cands(groups[f(gb)], free)
    pairs = []
    for a in ca:
        for c in cb:
            dist = mm((a[2] - c[2]).EuclideanNorm())
            pairs.append((dist + 0.3 * (a[3] + c[3]), dist, a, c))
    pairs.sort(key=lambda z: z[0])
    seen, sel = set(), []
    for _, dist, a, c in pairs:
        kk = (a[1] or (a[2].x, a[2].y), c[1] or (c[2].x, c[2].y))
        if kk in seen:
            continue
        seen.add(kk)
        sel.append({'dist': round(dist, 3),
                    'a': {'kind': a[0], 'pad': a[1], 'xy': [round(mm(a[2].x), 4), round(mm(a[2].y), 4)]},
                    'b': {'kind': c[0], 'pad': c[1], 'xy': [round(mm(c[2].x), 4), round(mm(c[2].y), 4)]}})
        if len(sel) >= NP:
            break
    res.append({'net': net, 'k': k, 'pairs': sel, 'sizes': [len(groups[f(ga)]), len(groups[f(gb)])]})
json.dump(res, open(OUT, 'w'), indent=1)
for r in res:
    p = r['pairs'][0] if r['pairs'] else None
    print('%-26s %s' % (r['net'][:26], ('%.2f mm  %s %s -> %s %s' % (p['dist'], p['a']['kind'], p['a']['pad'] or p['a']['xy'],
                                                                   p['b']['kind'], p['b']['pad'] or p['b']['xy'])) if p else r.get('note')))
