#!/usr/bin/env python
"""via_relocate.py - move plane vias that break the pad rules, one candidate at a time (lessons L15, L38; ServiceOne
rev. 0.2 review issues 10 and 18, 2026-10-22).

MUST be run with KiCad's own Python (pcbnew; shapely is needed, as for layout_measure.py).

--mode web    audit `via` FAILs "ring ... from SMD pad" / "ring touches" (L15: >= 0.15 mm solder-mask web). A via is
              moved only when exactly one track ends in it and that track's other end is in the pad named in the
              finding (a plane stub). The via slides along the stub direction in 0.05 mm steps (up to 1.5 mm) to the
              first spot with: ring to every SMD pad >= 0.16 mm, copper to every other-net item >= 0.115 mm, drill
              edge to every other hole >= 0.26 mm, board-edge clearance. The stub end moves with it (angle kept).
--mode axis   audit `pad-entry` FAILs on SMD pads of plane nets (nets with a copper zone), whose via is joined to the
              pad by a single stub. The via goes onto one of the pad's axes at half the pad length + 0.5 mm + via
              radius + 0..0.6 mm; the long axis first for an elongated pad (the direction nearer the current via
              first). The new stub runs straight from the pad centre to the via, no wider than the pad. This clears
              the stub zone (pad edge + 0.5 mm) that refinish_gated.py cannot fix (L38).
A locked via or stub is never moved (L40): the candidate is skipped with "locked".

The tool has no gate of its own: drive it with gate_each.py (one candidate per run, every change gated):
    gate_each.py BOARD --count N -- KICAD_PY via_relocate.py {board} AUDIT.json --mode axis --apply --indices {i}
Without --apply it lists the candidates and what it would do. --indices a,b,c restricts the run (indices into this
tool's own candidate list, stable for one audit JSON). --box x0,y0,x1,y1 keeps candidates inside a rectangle,
--exclude-box skips them (L37: leave a region the designer is routing alone).

Usage: via_relocate.py BOARD AUDIT.json --mode web|axis [--apply] [--indices a,b] [--box ..] [--exclude-box ..]
Measured on ServiceOne rev. 0.2 (2026-10-22): axis mode over the 107 plane pads with pad-entry FAILs outside the ADC
region; most refusals were a blocked axis (another net's track) or no hole-to-hole room - those go to the
interactive router.
"""
import json, math, os, re, sys
import pcbnew
from shapely.geometry import Point, Polygon, LineString

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import board_guard  # noqa: E402

a = sys.argv[1:]
if len(a) < 2 or a[0].startswith('-') or '--mode' not in a or a[a.index('--mode') + 1] not in ('web', 'axis'):
    sys.stdout.write(__doc__)
    sys.exit(2)
BOARD, AUD = a[0], a[1]
MODE = a[a.index('--mode') + 1]
APPLY = '--apply' in a
ONLY = set(int(v) for v in a[a.index('--indices') + 1].split(',')) if '--indices' in a else None
_box = lambda n: tuple(map(float, a[a.index(n) + 1].split(','))) if n in a else None
BOX, XBOX = _box('--box'), _box('--exclude-box')
WEB, CLR, H2H, STEP, MAXS = 0.16, 0.115, 0.26, 0.05, 1.5
mm, nm = pcbnew.ToMM, pcbnew.FromMM
b = pcbnew.LoadBoard(BOARD)


def skip_xy(x, y):
    return bool((BOX and not (BOX[0] <= x <= BOX[2] and BOX[1] <= y <= BOX[3])) or
                (XBOX and XBOX[0] <= x <= XBOX[2] and XBOX[1] <= y <= XBOX[3]))


# obstacle geometry, once
tracks = [t for t in b.GetTracks() if t.GetClass() != 'PCB_VIA']
vias = [t for t in b.GetTracks() if t.GetClass() == 'PCB_VIA']
pads = [(fp, p) for fp in b.GetFootprints() for p in fp.Pads()]
padpoly = {}
for fp, p in pads:
    for L in (pcbnew.F_Cu, pcbnew.B_Cu):
        if p.IsOnLayer(L):
            o = p.GetEffectivePolygon(L).Outline(0)
            padpoly[(id(p), L)] = Polygon([(mm(o.CPoint(i).x), mm(o.CPoint(i).y)) for i in range(o.PointCount())])
ds = b.GetDesignSettings()
EDGE = mm(ds.m_CopperEdgeClearance)
outline = pcbnew.SHAPE_POLY_SET()
b.GetBoardPolygonOutlines(outline, False)
op = outline.Outline(0)
board_poly = Polygon([(mm(op.CPoint(i).x), mm(op.CPoint(i).y)) for i in range(op.PointCount())])
holes_cut = [Polygon([(mm(outline.Hole(0, h).CPoint(i).x), mm(outline.Hole(0, h).CPoint(i).y))
                      for i in range(outline.Hole(0, h).PointCount())]) for h in range(outline.HoleCount(0))]


def ok_spot(v, x, y, net, skip_tracks):
    r = mm(v.GetWidth(pcbnew.F_Cu)) / 2
    dr = mm(v.GetDrillValue()) / 2
    c = Point(x, y)
    ring = c.buffer(r)
    if board_poly.exterior.distance(c) < r + EDGE or not board_poly.contains(c):
        return 'edge'
    for hp in holes_cut:
        if hp.exterior.distance(c) < r + EDGE:
            return 'edge'
    for (fp, p) in pads:
        pc = p.GetPosition()
        if abs(mm(pc.x) - x) > 6 or abs(mm(pc.y) - y) > 6:
            continue
        for L in (pcbnew.F_Cu, pcbnew.B_Cu):
            g = padpoly.get((id(p), L))
            if g is None:
                continue
            dd = g.distance(ring)
            if p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD and dd < WEB:
                return 'web %s.%s' % (fp.GetReference(), p.GetNumber())
            if p.GetNetname() != net and dd < CLR:
                return 'clr %s.%s' % (fp.GetReference(), p.GetNumber())
        if p.GetDrillSizeX() > 0 and c.distance(Point(mm(pc.x), mm(pc.y))) - mm(p.GetDrillSizeX()) / 2 - dr < H2H:
            return 'h2h pad'
    for t in tracks:
        if t.GetNetname() == net or id(t) in skip_tracks:
            continue
        s, e = t.GetStart(), t.GetEnd()
        if min(mm(s.x), mm(e.x)) - 3 > x or max(mm(s.x), mm(e.x)) + 3 < x or \
           min(mm(s.y), mm(e.y)) - 3 > y or max(mm(s.y), mm(e.y)) + 3 < y:
            continue
        if LineString([(mm(s.x), mm(s.y)), (mm(e.x), mm(e.y))]).distance(c) - mm(t.GetWidth()) / 2 - r < CLR:
            return 'clr track %s' % t.GetNetname()
    for o in vias:
        if o is v or o.m_Uuid.AsString() == v.m_Uuid.AsString():
            continue
        q = o.GetPosition()
        dd = c.distance(Point(mm(q.x), mm(q.y)))
        if dd - mm(o.GetDrillValue()) / 2 - dr < H2H:
            return 'h2h via'
        if o.GetNetname() != net and dd - mm(o.GetWidth(pcbnew.F_Cu)) / 2 - r < CLR:
            return 'clr via'
    return None


RX = re.compile(r'^via (\S+) [\d.]+/[\d.]+ @ (-?[\d.]+),(-?[\d.]+): ring (?:touches / merges with|[\d.]+ mm from) '
                r'SMD pad (\S+)-(\S+) \(')


def web_candidates():
    todo = []
    for f in json.load(open(AUD, encoding='utf-8'))['findings']:
        if f['level'] != 'FAIL' or f['check'] != 'via':
            continue
        m = RX.match(f['msg'])
        if not m:
            continue
        x, y = float(m.group(2)), float(m.group(3))
        if skip_xy(x, y):
            continue
        todo.append((m.group(1), x, y, m.group(4), m.group(5)))
    return todo


# ---- via_axis: relocate a plane pad's via onto the pad axis, past pad edge + 0.5 mm (review issue 18, L10/L11) ----
# Candidates: pads named in audit pad-entry FAILs, on PLANE nets, outside --box, whose via is joined to the pad by a
# single stub (one track ends in the via; its other end is in the pad). The new via goes on one of the pad's axes, at
# half the pad length along that axis + 0.5 mm + via radius + extra (0..0.6 mm in 0.05 steps); axes tried: the long
# axis first for an elongated pad (both directions, the one nearer the current via first), both axes otherwise.
# The new stub runs straight from the pad centre to the via, at min(old stub width, pad's smaller side).
# Top-side pads only (the stub is looked for on F.Cu).
PRX = re.compile(r'pad (\S+?)-(\S+?)[ )]')
PLANE = {z.GetNetname() for z in b.Zones() if not z.GetIsRuleArea() and z.GetNetname()}


def axis_candidates():
    seen, todo = set(), []
    for f in json.load(open(AUD, encoding='utf-8'))['findings']:
        if f['level'] != 'FAIL' or f['check'] != 'pad-entry':
            continue
        m = re.search(r'@ ?(-?[\d.]+),(-?[\d.]+)', f['msg'])
        p = PRX.search(f['msg'])
        if not (m and p):
            continue
        x, y = float(m.group(1)), float(m.group(2))
        if skip_xy(x, y):
            continue
        k = (p.group(1), p.group(2))
        if k in seen:
            continue
        seen.add(k)
        fp = b.FindFootprintByReference(k[0])
        pad = [q for q in fp.Pads() if q.GetNumber() == k[1]] if fp else []
        if pad and pad[0].GetNetname() in PLANE and pad[0].GetAttribute() == pcbnew.PAD_ATTRIB_SMD:
            todo.append((pad[0].GetNetname(), mm(pad[0].GetPosition().x), mm(pad[0].GetPosition().y), k[0], k[1]))
    return todo


def stub_clear(x0, y0, x1, y1, w, net, skip):
    seg = LineString([(x0, y0), (x1, y1)]).buffer(w / 2)
    for (fp, p) in pads:
        if p.GetNetname() == net:
            continue
        pc = p.GetPosition()
        if abs(mm(pc.x) - x1) > 5 or abs(mm(pc.y) - y1) > 5:
            continue
        g = padpoly.get((id(p), pcbnew.F_Cu))
        if g is not None and g.distance(seg) < CLR:
            return 'stub clr %s.%s' % (fp.GetReference(), p.GetNumber())
    for t in tracks:
        if t.GetNetname() == net or t.GetLayer() != pcbnew.F_Cu or id(t) in skip:
            continue
        s, e = t.GetStart(), t.GetEnd()
        if min(mm(s.x), mm(e.x)) - 4 > max(x0, x1) or max(mm(s.x), mm(e.x)) + 4 < min(x0, x1) or \
           min(mm(s.y), mm(e.y)) - 4 > max(y0, y1) or max(mm(s.y), mm(e.y)) + 4 < min(y0, y1):
            continue
        if LineString([(mm(s.x), mm(s.y)), (mm(e.x), mm(e.y))]).buffer(mm(t.GetWidth()) / 2).distance(seg) < CLR:
            return 'stub clr track %s' % t.GetNetname()
    for o in vias:
        if o.GetNetname() == net:
            continue
        q = o.GetPosition()
        if Point(mm(q.x), mm(q.y)).buffer(mm(o.GetWidth(pcbnew.F_Cu)) / 2).distance(seg) < CLR:
            return 'stub clr via'
    return None


def run_web(todo):
    moved = 0
    for idx, (net, x, y, ref, num) in enumerate(todo):
        if ONLY is not None and idx not in ONLY:
            continue
        P0 = pcbnew.VECTOR2I(nm(x), nm(y))
        v = min(vias, key=lambda o: (o.GetPosition() - P0).EuclideanNorm())
        if (v.GetPosition() - P0).EuclideanNorm() > 2000 or v.GetNetname() != net:
            print('  skip [%d] %s @%.4f,%.4f: via not found' % (idx, net, x, y)); continue
        fp = b.FindFootprintByReference(ref)
        pad = [p for p in fp.Pads() if p.GetNumber() == num] if fp else []
        if not pad:
            print('  skip [%d] %s @%.4f,%.4f: pad %s-%s not found' % (idx, net, x, y, ref, num)); continue
        pad = pad[0]
        vp = v.GetPosition()
        ends = [(t, end) for t in tracks if t.GetNetname() == net for end in ('s', 'e')
                if ((t.GetStart() if end == 's' else t.GetEnd()) - vp).EuclideanNorm() <= 1000]
        if len(ends) != 1:
            print('  skip [%d] %s @%.4f,%.4f: %d tracks end in the via' % (idx, net, x, y, len(ends))); continue
        t, end = ends[0]
        if v.IsLocked() or t.IsLocked():
            print('  skip [%d] %s @%.4f,%.4f: locked' % (idx, net, x, y)); continue
        other = t.GetEnd() if end == 's' else t.GetStart()
        if not pad.HitTest(other) or pad.GetNetname() != net:
            print('  skip [%d] %s @%.4f,%.4f: stub does not start in %s-%s' % (idx, net, x, y, ref, num)); continue
        dx, dy = mm(vp.x - other.x), mm(vp.y - other.y)
        L = math.hypot(dx, dy)
        if L < 1e-6:
            print('  skip [%d] %s @%.4f,%.4f: via at the stub start' % (idx, net, x, y)); continue
        ux, uy = dx / L, dy / L
        spot, why = None, ''
        k = 1
        while k * STEP <= MAXS + 1e-9:
            nx, ny = mm(vp.x) + ux * k * STEP, mm(vp.y) + uy * k * STEP
            why = ok_spot(v, nx, ny, net, {id(t)})
            if why is None:
                spot = (nx, ny); break
            if why.startswith('clr') or why.startswith('h2h') or why == 'edge':
                break                                  # a hard obstacle on the stub line: going further only crosses it
            k += 1
        if not spot:
            print('  skip [%d] %s @%.4f,%.4f: no spot (%s)' % (idx, net, x, y, why)); continue
        moved += 1
        print('  nudged [%d] %-18s @%.4f,%.4f -> %.4f,%.4f (%.2f mm)' % (idx, net[:18], x, y, spot[0], spot[1], k * STEP))
        if APPLY:
            np_ = pcbnew.VECTOR2I(nm(spot[0]), nm(spot[1]))
            v.SetPosition(np_)
            if end == 's':
                t.SetStart(np_)
            else:
                t.SetEnd(np_)
    return moved


def run_axis(todo):
    moved = 0
    for idx, (net, px, py, ref, num) in enumerate(todo):
        if ONLY is not None and idx not in ONLY:
            continue
        pad = [q for q in b.FindFootprintByReference(ref).Pads() if q.GetNumber() == num][0]
        pc = pad.GetPosition()
        stubs = [(t, 's' if pad.HitTest(t.GetEnd()) else 'e') for t in tracks
                 if t.GetNetname() == net and t.GetLayer() == pcbnew.F_Cu and (pad.HitTest(t.GetStart()) or pad.HitTest(t.GetEnd()))]
        found = None
        for t, far in stubs:                       # far = the end away from the pad
            fpnt = t.GetStart() if far == 's' else t.GetEnd()
            vs = [v for v in vias if v.GetNetname() == net and (v.GetPosition() - fpnt).EuclideanNorm() <= 1000]
            if len(vs) != 1:
                continue
            others = [o for o in tracks if o.GetNetname() == net and o is not t and
                      ((o.GetStart() - fpnt).EuclideanNorm() <= 1000 or (o.GetEnd() - fpnt).EuclideanNorm() <= 1000)]
            if not others:
                found = (t, far, vs[0]); break
        if not found or len(stubs) != 1:
            print('  skip [%d] %s.%s: not a single stub to a via (%d tracks at the pad)' % (idx, ref, num, len(stubs))); continue
        t, far, v = found
        if v.IsLocked() or t.IsLocked():
            print('  skip [%d] %s.%s: locked' % (idx, ref, num)); continue
        ang = math.radians(pad.GetOrientation().AsDegrees())
        sx, sy = mm(pad.GetSize().x), mm(pad.GetSize().y)
        ax = [((math.cos(ang), -math.sin(ang)), sx / 2), ((math.sin(ang), math.cos(ang)), sy / 2)]
        if max(sx, sy) >= 1.5 * min(sx, sy):
            ax = [a_ for a_ in ax if a_[1] == max(sx, sy) / 2]
        vp = v.GetPosition()
        cur = (mm(vp.x) - px, mm(vp.y) - py)
        dirs = []
        for (ux, uy), half in ax:
            for sgn in (1, -1):
                dirs.append((-(cur[0] * ux * sgn + cur[1] * uy * sgn), ux * sgn, uy * sgn, half))
        dirs.sort()
        r = mm(v.GetWidth(pcbnew.F_Cu)) / 2
        w = min(mm(t.GetWidth()), min(sx, sy))
        spot, why = None, ''
        for _, ux, uy, half in dirs:
            for k in range(0, 13):
                d = half + 0.55 + r + 0.05 * k
                nx, ny = px + ux * d, py + uy * d
                why = ok_spot(v, nx, ny, net, {id(t)}) or stub_clear(px, py, nx, ny, w, net, {id(t)})
                if why is None:
                    spot = (nx, ny, d); break
            if spot:
                break
        if not spot:
            print('  skip [%d] %s.%s: no axial spot (%s)' % (idx, ref, num, why)); continue
        moved += 1
        print('  nudged [%d] %-18s @%.4f,%.4f -> %.4f,%.4f (%s.%s, %.2f mm)' % (idx, net[:18], px, py, spot[0], spot[1],
                                                                              ref, num, spot[2]))
        if APPLY:
            np_ = pcbnew.VECTOR2I(nm(spot[0]), nm(spot[1]))
            v.SetPosition(np_)
            t.SetStart(pcbnew.VECTOR2I(pc.x, pc.y))
            t.SetEnd(np_)
            t.SetWidth(nm(w))
    return moved


todo = web_candidates() if MODE == 'web' else axis_candidates()
moved = run_web(todo) if MODE == 'web' else run_axis(todo)
print('candidates %d, moved %d' % (len(todo), moved))
if APPLY and moved:
    board_guard.check_board_writable(BOARD, argv=a[2:], script='via_relocate.py')
    pcbnew.SaveBoard(BOARD, b)
    print('saved')
