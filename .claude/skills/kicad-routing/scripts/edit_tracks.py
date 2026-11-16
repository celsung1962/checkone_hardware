#!/usr/bin/env python
"""edit_tracks.py - a scoped, exact copper edit from a JSON spec: delete segments and vias matched by their exact end
points, add new ones; aborts when a match is missing or ambiguous (ServiceOne rev. 0.2 review fixes, 2026-10-22/23).

MUST be run with KiCad's own Python (pcbnew).

Use it for a fix designed by hand (a pad entry re-laid on the axis, a stub restored to a pad centre, a via moved onto
a pin axis), then gate the result with stage_gate.py. Nothing outside the spec changes.

SPEC: one block or a list of blocks
    {"net": "GND", "layer": "F.Cu", "width": 0.2,
     "delete": [[x1, y1, x2, y2], ...],          segments, end points within 2 um, in either order
     "add": [[x1, y1, x2, y2], [x1, y1, x2, y2, w], ...],   optional 5th value: this segment's width
     "del_via": [[x, y], ...], "add_via": [[x, y], ...], "via_d": 0.45, "via_drill": 0.2}
A locked segment or via is not deleted unless --allow-locked (L40).

Usage: edit_tracks.py BOARD SPEC.json [--allow-locked]
board_guard first (KiCad closed, .kicad_pro beside the board); saved in place.
"""
import json, os, sys
import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import board_guard  # noqa: E402

if len(sys.argv) < 3 or sys.argv[1].startswith('-'):
    sys.stdout.write(__doc__)
    sys.exit(2)
BOARD, SPEC = sys.argv[1], sys.argv[2]
ALLOW_LOCKED = '--allow-locked' in sys.argv
board_guard.check_board_writable(BOARD, argv=[], script='edit_tracks.py')
b = pcbnew.LoadBoard(BOARD)
nm = pcbnew.FromMM
spec = json.load(open(SPEC))
spec = spec if isinstance(spec, list) else [spec]
ALL = [t for t in b.GetTracks() if t.GetClass() != 'PCB_VIA']
near = lambda p, x, y: abs(p.x - nm(x)) <= 2000 and abs(p.y - nm(y)) <= 2000
todel, toadd = [], []
for blk in spec:
    net, layer = blk['net'], b.GetLayerID(blk.get('layer', 'F.Cu'))
    for x1, y1, x2, y2 in blk.get('delete', []):
        hit = [t for t in ALL if t.GetNetname() == net and t.GetLayer() == layer and (
            (near(t.GetStart(), x1, y1) and near(t.GetEnd(), x2, y2)) or
            (near(t.GetStart(), x2, y2) and near(t.GetEnd(), x1, y1)))]
        if len(hit) != 1:
            sys.exit('ABORT: %d matches for %s %s' % (len(hit), net, (x1, y1, x2, y2)))
        todel.append(hit[0])
    ni = b.FindNet(net)
    for seg in blk.get('add', []):
        x1, y1, x2, y2 = seg[:4]
        t = pcbnew.PCB_TRACK(b)
        t.SetStart(pcbnew.VECTOR2I(nm(x1), nm(y1)))
        t.SetEnd(pcbnew.VECTOR2I(nm(x2), nm(y2)))
        t.SetWidth(nm(seg[4] if len(seg) > 4 else blk.get('width', 0.2)))
        t.SetLayer(layer)
        t.SetNet(ni)
        toadd.append(t)
VIAS = [t for t in b.GetTracks() if t.GetClass() == 'PCB_VIA']
for blk in spec:
    for x, y in blk.get('del_via', []):
        hit = [v for v in VIAS if v.GetNetname() == blk['net'] and near(v.GetPosition(), x, y)]
        if len(hit) != 1:
            sys.exit('ABORT: %d via matches for %s %s' % (len(hit), blk['net'], (x, y)))
        todel.append(hit[0])
    for x, y in blk.get('add_via', []):
        v = pcbnew.PCB_VIA(b)
        v.SetPosition(pcbnew.VECTOR2I(nm(x), nm(y)))
        v.SetWidth(pcbnew.F_Cu, nm(blk.get('via_d', 0.45)))
        v.SetDrill(nm(blk.get('via_drill', 0.2)))
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        v.SetRemoveUnconnected(True)
        v.SetKeepStartEnd(True)
        v.SetNet(b.FindNet(blk['net']))
        toadd.append(v)
locked = [t for t in todel if t.IsLocked()]
if locked and not ALLOW_LOCKED:
    sys.exit('ABORT: %d locked item(s) would be deleted (first: %s); unlock them in KiCad or pass --allow-locked'
             % (len(locked), locked[0].GetNetname()))
for t in todel:
    b.Remove(t)
for t in toadd:
    b.Add(t)
pcbnew.SaveBoard(BOARD, b)
print('deleted %d, added %d' % (len(todel), len(toadd)))
