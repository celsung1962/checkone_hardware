#!/usr/bin/env python
"""dangling_classify.py - classify dangling copper before removing it (lesson L33; ServiceOne D133 clean-up, 2026-10-22).

MUST be run with KiCad's own Python (pcbnew).

Deleting DRC track_dangling stubs until none is left peels an unfinished net back to its pads: on ServiceOne that
removed 112 segments and left 30-46 mm gaps. A stub is the chain of segments from a free track end back to the first
junction (a pad, a via, or a point where three or more track ends meet). It is:
  - a LEAD-IN when its free end is a candidate end of an open connection of its net (open_ends.py pairs): kept, and
    listed with its end in the hand-off (L29);
  - locked: kept (L40);
  - otherwise unused: removed whole.
A dangling via (DRC via_dangling) is removed unless it is a candidate end or locked. An OVERHANG (a track that runs
past the pad it connects) is not a dangling stub in DRC's sense: trim it, never delete it (removing them broke 4
nets on ServiceOne).

Never iterate this to convergence on a board with open connections: run it once, after open_ends.py.

Usage: dangling_classify.py BOARD ENDS.json DRC.json OUT.json [--apply]
    ENDS.json from open_ends.py, DRC.json from kicad-cli pcb drc --format json --severity-all
--apply removes the unused stubs and vias and saves in place (board_guard: KiCad closed, .kicad_pro beside the
board); without it the tool only reports. Gate the result (stage_gate.py) like any other change.
"""
import json, math, os, sys
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import board_guard  # noqa: E402

if len(sys.argv) < 5 or sys.argv[1].startswith('-'):
    sys.stdout.write(__doc__)
    sys.exit(2)
BOARD, ENDJ, DRCJ, OUT = sys.argv[1:5]
APPLY = '--apply' in sys.argv
mm, nm = pcbnew.ToMM, pcbnew.FromMM
b = pcbnew.LoadBoard(BOARD)
uid = lambda x: x.m_Uuid.AsString()
lead = {}
for r in json.load(open(ENDJ)):
    for p in r['pairs']:
        for s in (p['a'], p['b']):
            if s['kind'] in ('free', 'via'):
                lead.setdefault(r['net'], []).append(tuple(s['xy']))
is_lead = lambda net, x, y: any(math.hypot(x - a, y - c) < 0.002 for a, c in lead.get(net, []))
d = json.load(open(DRCJ, encoding='utf-8'))
dang_tr = {i['uuid'] for v in d['violations'] if v['type'] == 'track_dangling' for i in v['items']}
dang_via = {i['uuid'] for v in d['violations'] if v['type'] == 'via_dangling' for i in v['items']}
tracks = [t for t in b.GetTracks() if t.GetClass() != 'PCB_VIA']
vias = [t for t in b.GetTracks() if t.GetClass() == 'PCB_VIA']
pads = [p for fp in b.GetFootprints() for p in fp.Pads()]
byuid = {uid(t): t for t in b.GetTracks()}


def node_items(pt, net, layer, exclude):
    """Track ends meeting at pt (same net, layer), and whether a pad / via is there."""
    ends, hard = [], False
    for o in tracks:
        if uid(o) in exclude or o.GetNetname() != net or o.GetLayer() != layer:
            continue
        for e in (o.GetStart(), o.GetEnd()):
            if (e - pt).EuclideanNorm() <= 1000:
                ends.append((o, e))
    for v in vias:
        if v.GetNetname() == net and (v.GetPosition() - pt).EuclideanNorm() <= v.GetWidth(pcbnew.F_Cu) / 2:
            hard = True
    for p in pads:
        if p.GetNetname() == net and p.IsOnLayer(layer) and p.HitTest(pt):
            hard = True
    return ends, hard


def free_end(t):
    for e in (t.GetStart(), t.GetEnd()):
        ends, hard = node_items(e, t.GetNetname(), t.GetLayer(), {uid(t)})
        if not ends and not hard:
            # also not inside another same-net track's copper
            if not any(o.GetNetname() == t.GetNetname() and o.GetLayer() == t.GetLayer() and uid(o) != uid(t)
                       and o.HitTest(e, 0) for o in tracks):
                return e
    return None


removed, kept = [], []
for u in sorted(dang_tr):
    t = byuid.get(u)
    if t is None or uid(t) in {x['uuid'] for x in removed}:
        continue
    fe = free_end(t)
    if fe is None:
        continue
    net = t.GetNetname()
    chain, cur, pt = [t], t, (t.GetEnd() if (t.GetStart() - fe).EuclideanNorm() <= 1000 else t.GetStart())
    while True:
        ends, hard = node_items(pt, net, cur.GetLayer(), {uid(c) for c in chain})
        if hard or len(ends) != 1:
            break
        nxt, e = ends[0]
        chain.append(nxt)
        cur = nxt
        pt = nxt.GetEnd() if (nxt.GetStart() - e).EuclideanNorm() <= 1000 else nxt.GetStart()
    rec = {'net': net, 'free': [round(mm(fe.x), 4), round(mm(fe.y), 4)], 'segments': len(chain),
           'length': round(sum(mm(c.GetLength()) for c in chain), 3), 'layer': b.GetLayerName(t.GetLayer()),
           'uuid': u}
    if is_lead(net, mm(fe.x), mm(fe.y)) or any(c.IsLocked() for c in chain):
        kept.append(dict(rec, locked=any(c.IsLocked() for c in chain)))
    else:
        removed.append(dict(rec, uuids=[uid(c) for c in chain]))
via_rm, via_keep = [], []
for u in dang_via:
    v = byuid.get(u)
    if v is None:
        continue
    p = v.GetPosition()
    rec = {'net': v.GetNetname(), 'xy': [round(mm(p.x), 4), round(mm(p.y), 4)], 'uuid': u}
    (via_keep if is_lead(v.GetNetname(), mm(p.x), mm(p.y)) or v.IsLocked() else via_rm).append(rec)
json.dump({'removed': removed, 'kept': kept, 'via_removed': via_rm, 'via_kept': via_keep}, open(OUT, 'w'), indent=1)
print('stubs: remove %d (%d segments, %.1f mm), keep %d lead-ins; dangling vias: remove %d, keep %d' % (
    len(removed), sum(r['segments'] for r in removed), sum(r['length'] for r in removed), len(kept), len(via_rm),
    len(via_keep)))
for r in kept:
    print('  keep  %-26s %s %s  %d seg %.2f mm' % (r['net'][:26], r['layer'], r['free'], r['segments'], r['length']))
for r in removed:
    print('  drop  %-26s %s %s  %d seg %.2f mm' % (r['net'][:26], r['layer'], r['free'], r['segments'], r['length']))
for r in via_rm:
    print('  drop via %-23s %s' % (r['net'][:23], r['xy']))
if APPLY:
    board_guard.check_board_writable(BOARD, argv=[], script='dangling_classify.py')
    gone = {x for r in removed for x in r['uuids']} | {r['uuid'] for r in via_rm}
    for t in list(b.GetTracks()):
        if uid(t) in gone:
            b.Remove(t)
    pcbnew.SaveBoard(BOARD, b)
    print('saved; removed %d items' % len(gone))
