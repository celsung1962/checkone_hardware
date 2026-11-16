#!/usr/bin/env python
"""route_finish.py - grid maze router for the last few connections an autorouter left behind.

MUST be run with KiCad's own Python (it imports pcbnew).

    route_finish.py <board.kicad_pcb> --net NAME (--from X,Y | --from-pad REF.PAD) (--to X,Y | --to-pad REF.PAD)
                    [--width MM] [--layer F.Cu] [--grid 0.1] [--clearance 0.1]
                    [--safety MM] [--via-cost N] [--max-expansions N] [--via-d MM] [--via-drill MM] [--dry-run]
                    [--exclusive [--allow REF.PAD,...]] [--block-courtyards [--courtyard-exempt REF,...]]
                    [--avoid NET,... [--avoid-margin MM] [--avoid-exempt X,Y,R[;X,Y,R]] [--avoid-layers F.Cu,B.Cu]]
                    [--edge MM] [--no-axial] [--allow-acute]
    route_finish.py <board.kicad_pcb> --refinish REF.PAD [--refinish-length 1.5] [--refinish-force] [--width MM] [...]

1.23.0 (board review rev. 0.2, L10 / L11): with --from-pad / --to-pad every pad end is an AXIAL STUB - from the
exact pad centre along the pad axis (elongated pad: long axis; square: either; IC pin: outer end first; passive:
the side facing the route) to pad edge + 0.5 mm, no wider than the pad's smallest dimension; the grid origin is
shifted so the stub axis passes through the exact centre. --no-axial gives the 1.19 behaviour. --refinish REF.PAD
realigns an existing entry: the track into the pad is cut back to a vertex >= --refinish-length of copper away
and re-routed from there with a stub (nothing saved without a route).

1.19.0 options (ServiceOne datasheet layout fixes, 2026-10-05):
  --from-pad / --to-pad  start and end at the exact pad centre. The grid is aligned to 0.05 mm, and an
                         off-grid centre is snapped to whenever the end segment stays on the lattice.
  --exclusive            every other copper item of the SAME net is an obstacle; only the two pads (and
                         --allow REF.PAD,...) are own copper. This draws a DEDICATED trace - a Kelvin sense
                         line from a shunt pad to a current monitor - instead of a route that merges with the
                         power track it is meant to measure. DRC cannot see that mistake (same net).
  --block-courtyards     other parts' F.Cu courtyards block tracks and vias: no track between a foreign
                         part's pins, under a part or into a crystal/inductor courtyard (audit FAILs
                         between-pads / crystal-inductor). --courtyard-exempt lifts it for named parts.
  --avoid NETS           keep --avoid-margin (default 0.5 mm) from these nets on the same layer, e.g. a
                         clock away from ADC inputs. --avoid-exempt X,Y,R lifts it within R of a point (the
                         IC's own pins); --avoid-layers limits it to some layers (planes shield F from B).
  Drilled pads and other-net vias keep the board's HOLE clearance, and the outline keeps the board's
  copper-to-edge clearance (both from the board design settings; --edge overrides). Before 1.19.0 only the
  copper clearance and a fixed 0.3 mm edge were kept (hole_clearance warnings, edge errors on a 0.5 mm
  board). New vias get remove_unused_layers / keep_end_layers, as the audit requires.
  Git Bash rewrites an argument that starts with "/" into a Windows path: net names like /ADC_AIN1P need
  MSYS_NO_PATHCONV=1 in the environment.

WHY THIS EXISTS: a second Freerouting pass over already-routed copper corrupts via padstacks (see
"Never top up an already-routed board"), so the remainder has to be finished some other way. This
routes ONE connection at a time, on the 45-degree lattice, so each result can be DRC-checked before
the next is attempted.

RULES IT KEEPS:
  * Only F.Cu and B.Cu are routable. Inner layers are planes; a track on one is an audit FAIL.
  * Every emitted segment is horizontal, vertical or exactly 45 degrees. The check is enforced, not
    hoped for: off-lattice output makes the script EXIT 3 without writing. Do not remove that check -
    it caught two real bugs during development.
  * No turn sharper than 90 degrees (1.27.0, ServiceOne D133 review): the search carries the direction it
    arrived in, the simplifier keeps it, and an acute joint left anyway makes the script EXIT 5 without
    writing. --allow-acute lifts both (the audit still FAILs the joint).
  * With --from X,Y / --to X,Y the endpoints are not dragged onto the exact pad centre: a track ending
    anywhere inside the target copper connects it, and moving the vertex would tilt the last segment off
    the lattice. Use --from-pad / --to-pad when the audit's pad-entry rule must hold (1.19.0).
  * Vias are never placed inside a pad, and rule areas (including footprint-internal keepouts) block
    both tracks and vias.
  * Board-level copper graphics are treated as obstacles. Freerouting never sees them - they are not
    in the DSN - which is exactly how a short gets built.

TWO THINGS THAT DECIDE THE OUTCOME:
  * --safety. Obstacles are dilated by (half-width + clearance + safety). Without the safety term a
    grid cell centre can sit up to GRID*sqrt(2)/2 from the true edge and DRC reports a near-miss;
    measured 0.0594 mm against a 0.1 mm rule at --grid 0.1. Too much safety seals narrow channels
    and the net stops routing at all. --grid 0.05 --safety 0.05 is the useful compromise.
  * ORDER. Routing one net changes what the next can do. MEASURED on one board, same 8 connections,
    three orderings: 3, 4 and 4 left unrouted. Route the congested area first, re-run, and keep the
    best result - there is no ordering that is right in general.

ALWAYS DRC AFTER EACH NET and revert any route that raises the violation count.

rev P (kicad-golden 1.16.0): this script still ends inside the target copper, not exactly on the pad
centre (see the NOTE above the endpoint code) - deliberately, so the last segment never risks going
off-lattice. Run `geometry_finish.py --pad-centre-entries` afterward: it snaps an entry exactly onto
its pad centre whenever the approach direction is already lattice-exact (improvements #8), which
covers the common case without touching this script's tested pathfinding.

Exit codes: 0 routed, 1 no path, 2 usage, 3 off-lattice geometry, 4 duplicate same-net copper, 5 acute joint
(nothing written).
"""
import sys
import math
import heapq
import numpy as np
import pcbnew
import os as _os
sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import board_guard  # noqa: E402
import zone_fill_check  # noqa: E402

MM = 1e6


def die(m, c=2):
    sys.stderr.write(str(m) + '\n')
    sys.exit(c)


args = sys.argv[1:]


def opt(name, default=None):
    if name in args:
        i = args.index(name)
        if i + 1 >= len(args):
            die(name + ' needs a value')
        return args[i + 1]
    return default


if not args or args[0].startswith('--'):
    die(__doc__)

BOARD = args[0]
REFIN = opt('--refinish')
NET = opt('--net') or ('' if REFIN else die('--net required'))
FROM = opt('--from') or ('' if '--from-pad' in args or REFIN else die('--from or --from-pad required'))
TO = opt('--to') or ('' if '--to-pad' in args or REFIN else die('--to or --to-pad required'))
WIDTH = float(opt('--width', '0.2'))
GRID = float(opt('--grid', '0.1'))
CLR = float(opt('--clearance', '0.1'))
VIA_COST = float(opt('--via-cost', '40'))
MAX_EXP = int(float(opt('--max-expansions', '4000000')))   # A* budget; raise it for long dedicated routes
VIA_D = float(opt('--via-d', '0.45'))
VIA_DRILL = float(opt('--via-drill', '0.2'))
START_LAYER = opt('--layer', 'F.Cu')
DRY = '--dry-run' in args
EXCL = '--exclusive' in args
FPAD = opt('--from-pad')
TPAD = opt('--to-pad')
ALLOWED = (set(x for x in (FPAD, TPAD) if x) | set((opt('--allow') or '').split(','))) - {''}

if not DRY:
    board_guard.check_board_writable(BOARD, script='route_finish.py')   # KiCad lock / .kicad_pro beside it
B = pcbnew.LoadBoard(BOARD)


def _pad(tag):
    r, n = tag.split('.', 1)
    f = B.FindFootprintByReference(r)
    if f is None:
        die('no footprint ' + r)
    for p in f.Pads():
        if p.GetNumber() == n:
            return p
    die('no pad ' + tag)


# --refinish REF.PAD (1.23.0, L10): realign an EXISTING entry. The track that ends in the pad is cut back along its
# chain (same layer, no via, no branch) to the first vertex at least --refinish-length (default 1.5 mm) of copper
# from the pad; those segments are taken out in memory and the connection is re-routed from the cut vertex to the
# pad with an axial stub. Nothing is saved unless the new route is found and passes the lattice check.
REFIN_CUT = None
BEND_MIN = 0.5
if REFIN:
    _rp = _pad(REFIN)
    NET = NET or _rp.GetNetname()
    if _rp.GetNetname() != NET:
        die('--refinish %s: the pad is on %s, not %s' % (REFIN, _rp.GetNetname(), NET))
    _tr = [t for t in B.GetTracks() if t.Type() == pcbnew.PCB_TRACE_T and t.GetNetname() == NET]
    _vi = [t.GetPosition() for t in B.GetTracks() if t.Type() == pcbnew.PCB_VIA_T and t.GetNetname() == NET]

    def _same(a_, b_):
        return abs(a_.x - b_.x) <= 1000 and abs(a_.y - b_.y) <= 1000
    _in = sorted([t for t in _tr if _rp.IsOnLayer(t.GetLayer()) and (_rp.HitTest(t.GetStart()) or _rp.HitTest(t.GetEnd()))],
                 key=lambda t: t.m_Uuid.AsString())
    if not _in:
        die('--refinish %s: no track ends in the pad' % REFIN, 1)
    _rc = _rp.GetPosition()
    try:
        _rw, _rh = _rp.GetSize(pcbnew.F_Cu).x, _rp.GetSize(pcbnew.F_Cu).y
    except TypeError:
        _rw, _rh = _rp.GetSize().x, _rp.GetSize().y
    _round = _rp.GetShape() == pcbnew.PAD_SHAPE_CIRCLE or (_rp.GetShape() == pcbnew.PAD_SHAPE_OVAL and _rw == _rh)

    def _entry_ok(t):
        """Axial already: ends exactly at the pad centre along an accepted axis (audit section 7)."""
        if not (_same(t.GetStart(), _rc) or _same(t.GetEnd(), _rc)):
            return False
        if _round:
            return True
        far = t.GetEnd() if _same(t.GetStart(), _rc) else t.GetStart()
        ang = math.degrees(math.atan2(-(far.y - _rc.y), far.x - _rc.x))
        long_ax = _rp.GetOrientationDegrees() + (0 if _rw >= _rh else 90)
        rel = (ang - long_ax) % 180
        along_long = min(rel, 180 - rel) < 0.01
        if max(_rw, _rh) >= 1.5 * min(_rw, _rh):
            if not along_long:
                return False
        elif min(rel % 90, 90 - rel % 90) >= 0.01:
            return False
        reach = (max(_rw, _rh) if along_long else min(_rw, _rh)) / 2 / MM
        if t.GetLength() / MM >= reach + BEND_MIN - 1e-6:
            return True
        # a shorter entry is fine only when its far end is a via or another pad (not a bend)
        return any(_same(v, far) for v in _vi) or any(q.HitTest(far) for f_ in B.GetFootprints() for q in f_.Pads()
                                                    if q is not _rp and q.GetNetname() == NET)
    if opt('--entry') is not None:
        _cur = _in[int(opt('--entry'))]
    else:
        _bad = list(_in) if '--refinish-force' in args else [t for t in _in if not _entry_ok(t)]   # force: fan-out alignment
        if not _bad:
            print('refinish %s: all %d entr%s already axial - nothing to do' % (REFIN, len(_in), 'y' if len(_in) == 1 else 'ies'))
            sys.exit(0)
        _cur = _bad[0]
        if len(_in) > 1:
            print('refinish %s: %d tracks end in the pad, %d non-axial - this run takes one (run again for the next)'
                  % (REFIN, len(_in), len(_bad)))
    _pt = _cur.GetEnd() if _rp.HitTest(_cur.GetStart()) else _cur.GetStart()
    _rm, _acc = [_cur], _cur.GetLength() / MM
    _want = float(opt('--refinish-length', '1.5'))
    _own_pads = [('%s.%s' % (f.GetReference(), q.GetNumber()), q) for f in B.GetFootprints() for q in f.Pads()
                 if q.GetNetname() == NET and q is not _rp]

    def _pad_at(pt, layer):
        return next((tg for tg, q in _own_pads if q.IsOnLayer(layer) and q.HitTest(pt)), None)
    _fpad = _pad_at(_pt, _cur.GetLayer())
    while _acc < _want and not _fpad:
        _nx = [t for t in _tr if t not in _rm and t.GetLayer() == _cur.GetLayer() and
               (_same(t.GetStart(), _pt) or _same(t.GetEnd(), _pt))]
        if len(_nx) != 1 or any(_same(v, _pt) for v in _vi):
            break
        _cur = _nx[0]
        _pt = _cur.GetEnd() if _same(_cur.GetStart(), _pt) else _cur.GetStart()
        _rm.append(_cur)
        _acc += _cur.GetLength() / MM
        _fpad = _pad_at(_pt, _cur.GetLayer())
    if opt('--width') is None:
        WIDTH = _rm[-1].GetWidth() / MM
    START_LAYER = B.GetLayerName(_cur.GetLayer())
    REFIN_CUT = (_pt.x / MM, _pt.y / MM)
    for _t in _rm:
        B.Remove(_t)
    print('refinish %s: %d segment(s), %.3f mm of %s taken out; re-route from (%.4f, %.4f) on %s, width %.3f mm' % (
        REFIN, len(_rm), _acc, NET, REFIN_CUT[0], REFIN_CUT[1], START_LAYER, WIDTH))
    FROM, TPAD = '%f,%f' % REFIN_CUT, REFIN
    if _fpad:                    # the chain runs pad to pad: re-route it whole, with a stub at both ends
        FPAD, REFIN_CUT = _fpad, None
        print('refinish %s: the chain starts in pad %s - re-routed pad to pad' % (REFIN, _fpad))
    ALLOWED |= {x for x in (REFIN, _fpad) if x}      # their own parts stay enterable with --block-courtyards

if FPAD:
    _q = _pad(FPAD).GetPosition()
    FROM = '%f,%f' % (_q.x / 1e6, _q.y / 1e6)
if TPAD:
    _q = _pad(TPAD).GetPosition()
    TO = '%f,%f' % (_q.x / 1e6, _q.y / 1e6)
fx, fy = [float(v) for v in FROM.split(',')]
tx, ty = [float(v) for v in TO.split(',')]
_ds = B.GetDesignSettings()
HOLE_CLR = _ds.m_HoleClearance / 1e6
LAYERS = [B.GetLayerID('F.Cu'), B.GetLayerID('B.Cu')]
LNAME = {LAYERS[0]: 'F.Cu', LAYERS[1]: 'B.Cu'}

AXIAL = '--no-axial' not in args
BEND_MIN = 0.5


def _padsize(p):
    try:
        q = p.GetSize(pcbnew.F_Cu)
    except TypeError:
        q = p.GetSize()
    return q.x / MM, q.y / MM


def _hit(p, x, y, acc=0):
    v = pcbnew.VECTOR2I(int(round(x * MM)), int(round(y * MM)))
    try:
        return p.HitTest(v, int(acc))
    except TypeError:
        return p.HitTest(v)


def pad_axial_dirs(tag, toward):
    """[(ux, uy, reach_mm)] lattice steps for an axial entry into pad TAG, best first. None: round pad (any
    direction is axial). []: the pad is not on the 45-degree lattice. An IC pin (part with >= 6 pads) is entered
    from its outer end first (L10); any other pad from the side facing TOWARD (the other end of the route)."""
    p = _pad(tag)
    w, h = _padsize(p)
    shp = p.GetShape()
    if shp == pcbnew.PAD_SHAPE_CIRCLE or (shp == pcbnew.PAD_SHAPE_OVAL and abs(w - h) < 1e-6):
        return None
    a = p.GetOrientationDegrees()
    if abs(a / 45.0 - round(a / 45.0)) > 1e-3:
        return []
    px, py = p.GetPosition().x / MM, p.GetPosition().y / MM
    out = []
    for k in range(4):
        r = math.radians(a + 90 * k)
        c, s_ = math.cos(r), -math.sin(r)
        ux, uy = (abs(c) > 0.3) * (1 if c > 0 else -1), (abs(s_) > 0.3) * (1 if s_ > 0 else -1)
        n = math.hypot(ux, uy)
        t = 0.0
        while t < 20 and _hit(p, px + ux / n * (t + 0.005), py + uy / n * (t + 0.005)):
            t += 0.005
        out.append((ux, uy, t))
    if max(w, h) / max(1e-9, min(w, h)) >= 1.5:
        out = sorted(out, key=lambda d: -d[2])[:2]
    f = p.GetParentFootprint()
    if f is not None and len(list(f.Pads())) >= 6:
        vx, vy = px - f.GetPosition().x / MM, py - f.GetPosition().y / MM
    else:
        vx, vy = toward[0] - px, toward[1] - py
    out.sort(key=lambda d: -(vx * d[0] + vy * d[1]) / math.hypot(d[0], d[1]))
    return out


# Axial stubs need the pad centre ON the stub's grid line. The grid origin is free: shift it (by less than one
# cell) so that the preferred stub axis of each end passes exactly through its pad centre. Two constraints on
# different coordinates are always met; when both fix the same one they must agree, else the next pair is tried.
def _origin_for(cands):
    """cands: [(x, y, (ux, uy))] -> (X0 mod GRID, Y0 mod GRID) or None."""
    fixX = fixY = None
    diag = []
    for x, y, (ux, uy) in cands:
        if uy == 0:
            v = y
            if fixY is not None and abs(((v - fixY + GRID / 2) % GRID) - GRID / 2) > 1e-6:
                return None
            fixY = v
        elif ux == 0:
            v = x
            if fixX is not None and abs(((v - fixX + GRID / 2) % GRID) - GRID / 2) > 1e-6:
                return None
            fixX = v
        else:
            diag.append((x, y, ux * uy))
    for x, y, sg in diag:            # sg 1: X0 - Y0 = x - y ; sg -1: X0 + Y0 = x + y (mod GRID)
        if fixX is None and fixY is None:
            fixX = x
        if fixX is not None and fixY is None:
            fixY = (fixX - (x - y)) if sg == 1 else ((x + y) - fixX)
        elif fixY is not None and fixX is None:
            fixX = (fixY + (x - y)) if sg == 1 else ((x + y) - fixY)
        else:
            r = (fixX - fixY) - (x - y) if sg == 1 else (fixX + fixY) - (x + y)
            if abs(((r + GRID / 2) % GRID) - GRID / 2) > 1e-6:
                return None
    return fixX, fixY


GRID_SHIFT = (None, None)
if AXIAL and (FPAD or TPAD):
    _fd = (pad_axial_dirs(FPAD, (tx, ty)) or [None]) if FPAD else [None]
    _td = (pad_axial_dirs(TPAD, (fx, fy)) or [None]) if TPAD else [None]
    for _a in _fd:
        for _b in _td:
            _c = ([(fx, fy, _a[:2])] if _a else []) + ([(tx, ty, _b[:2])] if _b else [])
            _o = None
            if REFIN_CUT and _c:     # the cut vertex on the grid too, when it fits
                _o = _origin_for(_c + [(fx, fy, (1, 0)), (fx, fy, (0, 1))])
            _o = _o or (_origin_for(_c) if _c else None)
            if _o:
                GRID_SHIFT = _o
                break
        if GRID_SHIFT != (None, None):
            break

# ---------------------------------------------------------------- grid frame
bb = B.GetBoardEdgesBoundingBox()
# grid aligned to 0.05 mm, so that most pad centres are grid points (exact pad entries)
X0 = math.floor(bb.GetLeft() / MM / 0.05) * 0.05 - 0.05
Y0 = math.floor(bb.GetTop() / MM / 0.05) * 0.05 - 0.05
if GRID_SHIFT[0] is not None:
    X0 -= GRID - ((GRID_SHIFT[0] - X0) % GRID)
if GRID_SHIFT[1] is not None:
    Y0 -= GRID - ((GRID_SHIFT[1] - Y0) % GRID)
W = int(math.ceil(bb.GetWidth() / MM / GRID)) + 3
H = int(math.ceil(bb.GetHeight() / MM / GRID)) + 3


def g2m(cx, cy):
    return X0 + cx * GRID, Y0 + cy * GRID


def m2g(x, y):
    return int(round((x - X0) / GRID)), int(round((y - Y0) / GRID))


occ = [np.zeros((W, H), dtype=bool) for _ in LAYERS]   # foreign copper
own = [np.zeros((W, H), dtype=bool) for _ in LAYERS]   # this net's copper
padmask = [np.zeros((W, H), dtype=bool) for _ in LAYERS]  # any pad (no via-in-pad)

YY, XX = np.meshgrid(np.arange(H), np.arange(W))


def stamp_disk(arr, x, y, r):
    cx, cy = m2g(x, y)
    rc = int(math.ceil(r / GRID))
    x0, x1 = max(0, cx - rc), min(W, cx + rc + 1)
    y0, y1 = max(0, cy - rc), min(H, cy + rc + 1)
    if x0 >= x1 or y0 >= y1:
        return
    sub_x = XX[x0:x1, y0:y1] - cx
    sub_y = YY[x0:x1, y0:y1] - cy
    arr[x0:x1, y0:y1] |= (sub_x * sub_x + sub_y * sub_y) <= rc * rc


def stamp_seg(arr, x1, y1, x2, y2, r):
    n = max(2, int(math.ceil(math.hypot(x2 - x1, y2 - y1) / (GRID * 0.5))))
    for i in range(n + 1):
        t = i / float(n)
        stamp_disk(arr, x1 + (x2 - x1) * t, y1 + (y2 - y1) * t, r)


def stamp_box(arr, bbox, pad=0.0):
    x0 = int(math.floor((bbox.GetLeft() / MM - pad - X0) / GRID))
    x1 = int(math.ceil((bbox.GetRight() / MM + pad - X0) / GRID))
    y0 = int(math.floor((bbox.GetTop() / MM - pad - Y0) / GRID))
    y1 = int(math.ceil((bbox.GetBottom() / MM + pad - Y0) / GRID))
    x0, x1 = max(0, x0), min(W, x1 + 1)
    y0, y1 = max(0, y0), min(H, y1 + 1)
    if x0 < x1 and y0 < y1:
        arr[x0:x1, y0:y1] = True


def stamp_polyset(arr, ps):
    """Rasterise a SHAPE_POLY_SET accurately. Bounding boxes merge neighbouring fine-pitch pads
    into one solid block and seal off the very pad we are trying to reach."""
    from matplotlib.path import Path
    for oi in range(ps.OutlineCount()):
        ch = ps.Outline(oi)
        verts = [(ch.CPoint(i).x / MM, ch.CPoint(i).y / MM) for i in range(ch.PointCount())]
        if len(verts) < 3:
            continue
        xs = [v[0] for v in verts]
        ys = [v[1] for v in verts]
        x0 = max(0, int(math.floor((min(xs) - X0) / GRID)) - 1)
        x1 = min(W, int(math.ceil((max(xs) - X0) / GRID)) + 2)
        y0 = max(0, int(math.floor((min(ys) - Y0) / GRID)) - 1)
        y1 = min(H, int(math.ceil((max(ys) - Y0) / GRID)) + 2)
        if x0 >= x1 or y0 >= y1:
            continue
        gx = X0 + np.arange(x0, x1) * GRID
        gy = Y0 + np.arange(y0, y1) * GRID
        PX, PY = np.meshgrid(gx, gy, indexing='ij')
        hit = Path(verts).contains_points(np.column_stack([PX.ravel(), PY.ravel()]))
        arr[x0:x1, y0:y1] |= hit.reshape(x1 - x0, y1 - y0)


def pad_polys(p, lay):
    ps = pcbnew.SHAPE_POLY_SET()
    try:
        p.TransformShapeToPolygon(ps, lay, 0, 5000, pcbnew.ERROR_INSIDE)
        if ps.OutlineCount():
            return ps
    except Exception:
        pass
    try:
        return p.GetEffectivePolygon(lay)
    except Exception:
        return None


# ---------------------------------------------------------------- copper islands of the net (1.26.4)
# A route that starts at a coordinate (an open end reported by DRC, a --refinish cut vertex) belongs to one island of
# the net's copper and must reach ANOTHER island. Own copper used to be passable everywhere, so a route could run
# back along its own island and stop near the requested point - duplicate copper (exit 4). In island mode the start
# island is an obstacle (except around the start point) and every other island of the net is a goal: the route ends
# where it first touches it. Off for plane nets (a zone joins everything), --exclusive, a pad start, --no-islands.
def _islands(net):
    trk = [t for t in B.GetTracks() if t.GetNetname() == net]
    pds = [pd for f in B.GetFootprints() for pd in f.Pads() if pd.GetNetname() == net]
    items = [('t', t) for t in trk] + [('p', pd) for pd in pds]
    par = list(range(len(items)))

    def find(i):
        while par[i] != i:
            par[i] = par[par[i]]
            i = par[i]
        return i

    def touch(a, b):
        (ka, A), (kb, Bb) = a, b
        if ka == 'p' and kb == 'p':
            return False
        if ka == 'p':
            (ka, A), (kb, Bb) = b, a
        if kb == 'p':
            pts = [A.GetPosition()] if A.GetClass() == 'PCB_VIA' else [A.GetStart(), A.GetEnd()]
            return any(Bb.HitTest(q) and (A.GetClass() == 'PCB_VIA' or Bb.IsOnLayer(A.GetLayer())) for q in pts)
        va, vb = A.GetClass() == 'PCB_VIA', Bb.GetClass() == 'PCB_VIA'
        if va and vb:
            return False
        if va or vb:
            v, t = (A, Bb) if va else (Bb, A)
            return t.HitTest(v.GetPosition(), int(v.GetWidth(pcbnew.F_Cu) / 2))
        if A.GetLayer() != Bb.GetLayer():
            return False
        return any(Bb.HitTest(q, 1000) for q in (A.GetStart(), A.GetEnd())) or \
            any(A.HitTest(q, 1000) for q in (Bb.GetStart(), Bb.GetEnd()))
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if find(i) != find(j) and touch(items[i], items[j]):
                par[find(i)] = find(j)
    return {it[1].m_Uuid.AsString(): find(k) for k, it in enumerate(items)}, items


ISL_MAP, START_ISL, START_R = {}, None, 0.0
_plane_net = any(z.GetNetname() == NET and not z.GetIsRuleArea() for z in B.Zones())
if not FPAD and not EXCL and not _plane_net and '--no-islands' not in args:
    ISL_MAP, _items = _islands(NET)
    _fp = pcbnew.VECTOR2I(int(round(fx * MM)), int(round(fy * MM)))
    _best = None
    for _k, _it in _items:
        _d = 0 if _it.HitTest(_fp, 50000) else None
        if _d is None:
            _q = _it.GetPosition()
            _d = math.hypot(_q.x - _fp.x, _q.y - _fp.y)
        if _best is None or _d < _best[0]:
            _best = (_d, ISL_MAP[_it.m_Uuid.AsString()], _it)
    START_ISL = _best[1] if _best else None
    if _best and _best[0] == 0:          # the start lies on a via or a track: the free circle must clear it (1.26.4)
        _si = _best[2]
        if _si.GetClass() == 'PCB_VIA':
            START_R = _si.GetWidth(pcbnew.F_Cu) / MM / 2.0
        elif _si.GetClass() == 'PAD':          # a pad of the start island: clear its half-diagonal
            START_R = math.hypot(_si.GetSize().x, _si.GetSize().y) / MM / 2.0
        else:
            START_R = _si.GetWidth() / MM / 2.0
    if START_ISL is not None and len(set(ISL_MAP.values())) < 2:
        START_ISL = None                 # one island only: nothing to tell apart
    if START_ISL is not None:
        print('islands: %d copper island(s) of %s; the start island is an obstacle, the others are goals'
              % (len(set(ISL_MAP.values())), NET))
start_isl = [np.zeros((W, H), dtype=bool) for _ in LAYERS]


def _is_start_isl(item):
    return START_ISL is not None and ISL_MAP.get(item.m_Uuid.AsString()) == START_ISL


# ---------------------------------------------------------------- rasterise copper
for t in B.GetTracks():
    isvia = (t.GetClass() == 'PCB_VIA')
    mine = (t.GetNetname() == NET) and not EXCL
    s, e = t.GetStart(), t.GetEnd()
    sisl = mine and _is_start_isl(t)
    if isvia:
        r = t.GetFrontWidth() / MM / 2.0
        for li, lay in enumerate(LAYERS):
            tgt = (start_isl[li] if sisl else own[li]) if mine else occ[li]
            stamp_disk(tgt, s.x / MM, s.y / MM, r)
            if not mine:
                stamp_disk(padmask[li], s.x / MM, s.y / MM, r)
    else:
        lay = t.GetLayer()
        if lay not in LAYERS:
            continue
        li = LAYERS.index(lay)
        r = t.GetWidth() / MM / 2.0
        tgt = (start_isl[li] if sisl else own[li]) if mine else occ[li]
        stamp_seg(tgt, s.x / MM, s.y / MM, e.x / MM, e.y / MM, r)

# 6+ layer boards (GapOne CON, 2026-11-07): only F.Cu/B.Cu are routed here, but a new via also crosses the inner
# SIGNAL layers - other-net tracks there block via positions (copper and hole clearance), or the via shorts them.
INNER_OCC = np.zeros_like(occ[0])
for t in B.GetTracks():
    if t.GetClass() == 'PCB_TRACK' and t.GetLayer() not in LAYERS and t.GetNetname() != NET:
        s_, e_ = t.GetStart(), t.GetEnd()
        stamp_seg(INNER_OCC, s_.x / MM, s_.y / MM, e_.x / MM, e_.y / MM, t.GetWidth() / MM / 2.0)

# hole clearance: other-net vias and every drilled pad (NPTH mounting holes included) keep the board's
# hole clearance; the copper dilation below only gives the copper clearance (hole_clearance warnings).
for t in B.GetTracks():
    if t.GetClass() == 'PCB_VIA' and not (t.GetNetname() == NET and not EXCL):
        q = t.GetStart()
        for li in range(len(LAYERS)):
            stamp_disk(occ[li], q.x / MM, q.y / MM, t.GetDrillValue() / MM / 2.0 + HOLE_CLR - CLR + 0.01)
for f in B.GetFootprints():
    for p in f.Pads():
        if p.GetDrillSizeX() > 0 and not (p.GetNetname() == NET and not EXCL):
            q = p.GetPosition()
            for li in range(len(LAYERS)):
                stamp_disk(occ[li], q.x / MM, q.y / MM,
                           max(p.GetDrillSizeX(), p.GetDrillSizeY()) / MM / 2.0 + HOLE_CLR - CLR)
for f in B.GetFootprints():
    for p in f.Pads():
        mine = (p.GetNetname() == NET) and (not EXCL or ('%s.%s' % (f.GetReference(), p.GetNumber())) in ALLOWED)
        ls = p.GetLayerSet()
        bbox = p.GetBoundingBox()
        for li, lay in enumerate(LAYERS):
            if not ls.Contains(lay):
                continue
            ps = pad_polys(p, lay)
            tgt = (start_isl[li] if _is_start_isl(p) else own[li]) if mine else occ[li]
            if ps is not None and ps.OutlineCount():
                stamp_polyset(padmask[li], ps)
                stamp_polyset(tgt, ps)
            else:
                stamp_box(padmask[li], bbox)
                stamp_box(tgt, bbox)

# --avoid NET,NET [--avoid-margin MM] [--avoid-exempt X,Y,R] [--avoid-layers F.Cu,B.Cu]
AVOID = set((opt('--avoid') or '').split(',')) - {''}
if AVOID:
    AVM = float(opt('--avoid-margin', '0.5'))
    avm = [np.zeros((W, H), dtype=bool) for _ in LAYERS]
    for t in B.GetTracks():
        if t.GetNetname() in AVOID and t.GetClass() != 'PCB_VIA' and t.GetLayer() in LAYERS:
            s, e = t.GetStart(), t.GetEnd()
            stamp_seg(avm[LAYERS.index(t.GetLayer())], s.x / MM, s.y / MM, e.x / MM, e.y / MM,
                      t.GetWidth() / MM / 2.0 + AVM)
    for f in B.GetFootprints():
        for p in f.Pads():
            if p.GetNetname() in AVOID:
                for li, lay in enumerate(LAYERS):
                    if p.GetLayerSet().Contains(lay):
                        stamp_box(avm[li], p.GetBoundingBox(), pad=AVM)
    if opt('--avoid-exempt'):              # X,Y,R[;X,Y,R...] (1.26.6: several circles, e.g. the IC and a test pad)
        PX, PY = np.meshgrid(X0 + np.arange(W) * GRID, Y0 + np.arange(H) * GRID, indexing='ij')
        for spec in opt('--avoid-exempt').split(';'):
            ex, ey, er_ = [float(v) for v in spec.split(',')]
            near = (PX - ex) ** 2 + (PY - ey) ** 2 <= er_ * er_
            for li in range(len(LAYERS)):
                avm[li] &= ~near
    AVL = opt('--avoid-layers')
    for li in range(len(LAYERS)):
        if not AVL or LNAME[LAYERS[li]] in AVL.split(','):
            occ[li] |= avm[li]

# --block-courtyards [--courtyard-exempt REF,...]: foreign F.Cu courtyards block tracks and vias
if '--block-courtyards' in args:
    exempt = set(x.split('.')[0] for x in ALLOWED) | set((opt('--courtyard-exempt') or '').split(','))
    for f in B.GetFootprints():
        if f.GetReference() in exempt or f.IsFlipped():
            continue
        cy = f.GetCourtyard(pcbnew.F_CrtYd)
        if cy.OutlineCount():
            stamp_box(occ[0], cy.BBox(), pad=-CLR)
            stamp_box(padmask[0], cy.BBox(), pad=0.0)

# board-level copper graphics (invisible to Freerouting - they are why this script exists)
for d in B.GetDrawings():
    if d.GetClass() != 'PCB_SHAPE' or d.GetLayer() not in LAYERS:
        continue
    li = LAYERS.index(d.GetLayer())
    try:
        mine = (d.GetNetname() == NET)
    except Exception:
        mine = False
    s, e = d.GetStart(), d.GetEnd()
    stamp_seg(own[li] if mine else occ[li], s.x / MM, s.y / MM, e.x / MM, e.y / MM,
              max(d.GetWidth() / MM / 2.0, 0.05))

# rule areas (keepouts), including footprint-internal ones
ruleareas = []
for i in range(B.GetAreaCount()):
    z = B.GetArea(i)
    if z.GetIsRuleArea():
        ruleareas.append(z)
for f in B.GetFootprints():
    for z in f.Zones():
        if z.GetIsRuleArea():
            ruleareas.append(z)
KEEP_TRACK = np.zeros((W, H), dtype=bool)
KEEP_VIA = np.zeros((W, H), dtype=bool)
for z in ruleareas:
    # the real outline, not its bounding box (a circle's box leaves the tangent points open to a track
    # that hugs the square: ServiceOne D116, 2026-10-20)
    if z.GetDoNotAllowTracks():
        stamp_polyset(KEEP_TRACK, z.Outline())
    if z.GetDoNotAllowVias():
        stamp_polyset(KEEP_VIA, z.Outline())
print('rule areas: %d  (tracks blocked %s, vias blocked %s)'
      % (len(ruleareas), int(KEEP_TRACK.sum()), int(KEEP_VIA.sum())))

# ---------------------------------------------------------------- inside-board mask
inside = np.zeros((W, H), dtype=bool)
poly = pcbnew.SHAPE_POLY_SET()
if B.GetBoardPolygonOutlines(poly, True) and poly.OutlineCount() > 0:
    # vectorised point-in-polygon; a per-cell Contains() call is ~1.7M round trips and crawls
    from matplotlib.path import Path
    gxs = X0 + np.arange(W) * GRID
    gys = Y0 + np.arange(H) * GRID
    PX, PY = np.meshgrid(gxs, gys, indexing='ij')
    pts_all = np.column_stack([PX.ravel(), PY.ravel()])
    acc = np.zeros(pts_all.shape[0], dtype=bool)
    for oi in range(poly.OutlineCount()):
        ch = poly.Outline(oi)
        verts = [(ch.CPoint(i).x / MM, ch.CPoint(i).y / MM) for i in range(ch.PointCount())]
        if len(verts) < 3:
            continue
        acc |= Path(verts).contains_points(pts_all)
        for hi in range(poly.HoleCount(oi)):
            hc = poly.Hole(oi, hi)
            hv = [(hc.CPoint(i).x / MM, hc.CPoint(i).y / MM) for i in range(hc.PointCount())]
            if len(hv) >= 3:
                acc &= ~Path(hv).contains_points(pts_all)
    inside = acc.reshape(W, H)
else:
    inside[:, :] = True
    print('WARNING: no board outline polygon; edge clearance not enforced')

# edge clearance: erode the inside mask
EDGE = float(opt('--edge', '%.4f' % max(0.3, _ds.m_CopperEdgeClearance / 1e6 + float(opt('--safety', str(GRID))))))
er = int(math.ceil((EDGE + WIDTH / 2.0) / GRID))
eroded = inside.copy()
for dx in range(-er, er + 1):
    for dy in range(-er, er + 1):
        if dx * dx + dy * dy > er * er:
            continue
        eroded &= np.roll(np.roll(inside, dx, axis=0), dy, axis=1)
inside = eroded


def dilate(mask, r_mm):
    r = int(math.ceil(r_mm / GRID))
    if r <= 0:
        return mask.copy()
    out = mask.copy()
    for dx in range(-r, r + 1):
        for dy in range(-r, r + 1):
            if dx * dx + dy * dy > r * r:
                continue
            out |= np.roll(np.roll(mask, dx, axis=0), dy, axis=1)
    return out


# A grid cell centre can sit up to GRID*sqrt(2)/2 from the true edge, so a dilation of exactly
# (half-width + clearance) under-delivers and DRC reports a near-miss. Measured: a route at 0.1 mm
# grid came out at 0.0594 mm against a 0.1 mm rule. Pad the dilation by a whole cell.
SAFETY = float(opt('--safety', str(GRID)))
MARGIN = WIDTH / 2.0 + CLR + SAFETY
blocked = []
for li in range(len(LAYERS)):
    b = dilate(occ[li], MARGIN)
    b &= ~own[li]            # own copper is always passable - but never inside a keepout
    b |= dilate(KEEP_TRACK, WIDTH / 2.0 + SAFETY)   # the track edge, not its centre, must stay out
    b |= ~inside
    if START_ISL is not None:
        sb = dilate(start_isl[li], MARGIN)
        PXs, PYs = np.meshgrid(X0 + np.arange(W) * GRID, Y0 + np.arange(H) * GRID, indexing='ij')
        sb &= (PXs - fx) ** 2 + (PYs - fy) ** 2 > (MARGIN + 2 * GRID + START_R) ** 2
        b |= sb
        own[li] |= start_isl[li] & ((PXs - fx) ** 2 + (PYs - fy) ** 2 <= (MARGIN + 2 * GRID + START_R) ** 2)
    blocked.append(b)
    print('%s: %.1f%% blocked' % (LNAME[LAYERS[li]], 100.0 * b.sum() / b.size))

via_block = dilate(np.logical_or(occ[0], occ[1]), VIA_D / 2.0 + CLR + SAFETY)
via_block |= dilate(np.logical_or(padmask[0], padmask[1]), 0.0)   # no via-in-pad
via_block |= dilate(INNER_OCC, max(VIA_D / 2.0 + CLR, VIA_DRILL / 2.0 + HOLE_CLR) + SAFETY)   # inner signal tracks
via_block |= dilate(KEEP_VIA, VIA_D / 2.0 + SAFETY)
via_block |= ~inside

# ---------------------------------------------------------------- endpoints
sx, sy = m2g(fx, fy)
gx, gy = m2g(tx, ty)
sl = LAYERS.index(B.GetLayerID(START_LAYER))


def nearest_free(cx, cy, li, radius=25):
    if not blocked[li][cx, cy]:
        return cx, cy
    for r in range(1, radius):
        for dx in range(-r, r + 1):
            for dy in (-r, r):
                for (ax, ay) in ((cx + dx, cy + dy), (cx + dy, cy + dx)):
                    if 0 <= ax < W and 0 <= ay < H and not blocked[li][ax, ay]:
                        return ax, ay
    return None


def nearest_own(cx, cy, radius=40):
    """Nearest cell that is inside THIS net's copper, on either layer."""
    hits = []
    for li in range(len(LAYERS)):
        if own[li][cx, cy]:
            hits.append((cx, cy, li))
    if hits:
        return hits
    for r in range(1, radius):
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                if max(abs(dx), abs(dy)) != r:
                    continue
                ax, ay = cx + dx, cy + dy
                if not (0 <= ax < W and 0 <= ay < H):
                    continue
                for li in range(len(LAYERS)):
                    if own[li][ax, ay]:
                        hits.append((ax, ay, li))
        if hits:
            return hits
    return []


# ---------------------------------------------------------------- axial pad entries (1.23.0, L10 / L11)
# With --from-pad / --to-pad the route ends in an AXIAL STUB: one straight segment from the exact pad centre along
# the pad axis (the long axis of an elongated pad, either axis of a square one, preferring the outer end) to
# pad edge + 0.5 mm, no wider than the pad's smallest dimension. The search starts and ends at the stub ends, and
# the stub cells and the pad area are closed to it, so the last bend lies >= 0.5 mm beyond the pad edge (audit
# section 7, review issues 6 and 18). A round pad needs no stub. --no-axial restores the 1.19 behaviour.
def stubs_for(tag, layers, toward):
    """Clear axial stubs into pad TAG: [dict(li, cells, end, width, avoid)], best first; [None] for a round pad."""
    dirs = pad_axial_dirs(tag, toward)
    if dirs is None:
        return [None]
    p = _pad(tag)
    px, py = p.GetPosition().x / MM, p.GetPosition().y / MM
    w, h = _padsize(p)
    sw = min(WIDTH, min(w, h))
    c0 = m2g(px, py)
    bbr = int(math.ceil((max(w, h) / 2 + WIDTH / 2 + CLR) / GRID)) + 2
    area = set()
    for cx in range(c0[0] - bbr, c0[0] + bbr + 1):
        for cy in range(c0[1] - bbr, c0[1] + bbr + 1):
            if 0 <= cx < W and 0 <= cy < H and _hit(p, *g2m(cx, cy), acc=(WIDTH / 2 + CLR) * MM):
                area.add((cx, cy))
    out = []
    cmx, cmy = g2m(*c0)
    own_tr = [t for t in B.GetTracks() if t.Type() == pcbnew.PCB_TRACE_T and t.GetNetname() == NET]
    for li in layers:
        for ux, uy, reach in dirs:           # an existing axial stub along this direction is shared, not doubled
            un = math.hypot(ux, uy)
            for t in own_tr:
                if t.GetLayer() != LAYERS[li]:
                    continue
                a_, b_ = (t.GetStart(), t.GetEnd())
                for q0, q1 in ((a_, b_), (b_, a_)):
                    if abs(q0.x / MM - px) > 1e-3 or abs(q0.y / MM - py) > 1e-3:
                        continue
                    dx, dy = q1.x / MM - px, q1.y / MM - py
                    ln = math.hypot(dx, dy)
                    if ln >= reach + BEND_MIN - 1e-6 and abs(dx * uy - dy * ux) / un < 1e-4 * max(1, ln) and dx * ux + dy * uy > 0:
                        e = (q1.x / MM, q1.y / MM)
                        ce = m2g(*e)
                        k = int(round(ln / (GRID * un)))
                        line = {(c0[0] + ux * j, c0[1] + uy * j) for j in range(max(0, k))}
                        av = {(cx, cy, l2) for cx, cy in (area | line) - {ce} for l2 in range(len(LAYERS))}
                        out.append(dict(tag=tag, li=li, cells=[], end=ce + (li,), width=sw, avoid=av, dir=(ux, uy),
                                        reach=reach, exact=True, shared=e))
    for li in layers:
        for ux, uy, reach in dirs:
            un = math.hypot(ux, uy)
            off = ((cmx - px) * ux + (cmy - py) * uy) / un            # cell 0 ahead of the exact centre (mm)
            exact = abs((cmx - px) * uy - (cmy - py) * ux) / un < 1e-6
            n = max(1, int(math.ceil((reach + BEND_MIN - off) / (GRID * un) - 1e-9)))
            cells = [(c0[0] + ux * k, c0[1] + uy * k) for k in range(n + 1)]
            if not all(0 <= cx < W and 0 <= cy < H and (own[li][cx, cy] or not blocked[li][cx, cy])
                       for cx, cy in cells):
                continue
            av = {(cx, cy, l2) for cx, cy in (area | set(cells[:-1])) - {cells[-1]} for l2 in range(len(LAYERS))}
            out.append(dict(tag=tag, li=li, cells=cells, end=cells[-1] + (li,), width=sw, avoid=av,
                            dir=(ux, uy), reach=reach, exact=exact))
    out.sort(key=lambda d: (not d.get('shared'), not d['exact']))   # stable: preference order kept within groups
    return out


def _pad_layers(tag):
    ls = _pad(tag).GetLayerSet()
    return [i for i, lay in enumerate(LAYERS) if ls.Contains(lay)] or [0]


if FPAD:
    _fl = _pad_layers(FPAD)
    srcs = [(sx, sy, sl if sl in _fl else _fl[0])]
else:
    srcs = nearest_own(sx, sy)
if not srcs:
    die('no own-net copper found near --from')
start0 = srcs[0]
goal0 = {(gx, gy, li) for li in _pad_layers(TPAD)} if TPAD else set(nearest_own(gx, gy))
GOAL_ANY = START_ISL is not None and not TPAD          # island mode: touching any other island ends the route
if not goal0:
    die('no own-net copper found near --to')

# ---------------------------------------------------------------- A*
DIRS = [(1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
        (1, 1, 1.4142), (1, -1, 1.4142), (-1, 1, 1.4142), (-1, -1, 1.4142)]
# 1.27.0 (ServiceOne D133 review): no turn sharper than 90 degrees. The search state carries the direction it
# arrived in (-1: none, at the start or after a via) and a step whose direction is more than 90 degrees from it is
# not taken. --allow-acute restores the 1.26 search (the final check below still refuses to write an acute joint).
NO_ACUTE = '--allow-acute' not in args


def _sgn(v):
    return (v > 0) - (v < 0)


def _dir_index(v):
    """Index in DIRS of the lattice direction of vector v (signs only); -1 for None / zero."""
    if not v:
        return -1
    s = (_sgn(v[0]), _sgn(v[1]))
    return next((k for k, d in enumerate(DIRS) if (d[0], d[1]) == s), -1)


def _turn_ok(d0, d1):
    """d0 -> d1 (DIRS indices, -1 = free) turns by 90 degrees or less."""
    return d0 < 0 or d1 < 0 or DIRS[d0][0] * DIRS[d1][0] + DIRS[d0][1] * DIRS[d1][1] >= 0


def astar(start, goalset, avoid, din=-1, dout=-1):
    """Cells start -> goalset. din: direction arriving at start (a stub); dout: direction leaving the goal cell."""
    def h(n):
        if GOAL_ANY:
            return 0.5 * math.hypot(n[0] - gx, n[1] - gy)
        return min(math.hypot(n[0] - q[0], n[1] - q[1]) for q in goalset)
    s0 = start + (din if NO_ACUTE else -1,)
    openh = [(h(start), 0.0, s0)]
    came, gsc, seen, pop = {}, {s0: 0.0}, set(), 0
    while openh:
        f, gc, st = heapq.heappop(openh)
        if st in seen:
            continue
        seen.add(st)
        pop += 1
        if pop > MAX_EXP:
            print('A*: giving up after %d expansions' % pop)
            break
        cur, cd = st[:3], st[3]
        if (cur in goalset and (not NO_ACUTE or _turn_ok(cd, dout))) or (
                GOAL_ANY and cur != start and own[cur[2]][cur[0], cur[1]] and
                math.hypot(cur[0] - start[0], cur[1] - start[1]) * GRID > MARGIN + 2 * GRID + START_R):
            path = [st]
            while path[-1] in came:
                path.append(came[path[-1]])
            return [p[:3] for p in path[::-1]], pop
        cx, cy, cl = cur
        for k, (dx, dy, cost) in enumerate(DIRS):
            if NO_ACUTE and not _turn_ok(cd, k):
                continue
            nx, ny = cx + dx, cy + dy
            if not (0 <= nx < W and 0 <= ny < H):
                continue
            if blocked[cl][nx, ny] and not own[cl][nx, ny]:
                continue
            if (nx, ny, cl) in avoid:
                continue
            if dx and dy:   # diagonal: do not cut a corner through blocked orthogonals
                if blocked[cl][cx + dx, cy] and blocked[cl][cx, cy + dy]:
                    continue
            nn = (nx, ny, cl, k if NO_ACUTE else -1)
            ng = gc + cost
            if ng < gsc.get(nn, 1e18):
                gsc[nn] = ng
                came[nn] = st
                heapq.heappush(openh, (ng + h(nn), ng, nn))
        ol = 1 - cl
        if not via_block[cx, cy] and not blocked[ol][cx, cy] and (cx, cy, ol) not in avoid:
            nn = (cx, cy, ol, -1)
            ng = gc + VIA_COST
            if ng < gsc.get(nn, 1e18):
                gsc[nn] = ng
                came[nn] = st
                heapq.heappush(openh, (ng + h(nn), ng, nn))
    return None, pop


fst = stubs_for(FPAD, [start0[2]] + [l for l in _pad_layers(FPAD) if l != start0[2]], (tx, ty)) if FPAD and AXIAL else [None]
tst = stubs_for(TPAD, _pad_layers(TPAD), (fx, fy)) if TPAD and AXIAL else [None]
for tag, lst in ((FPAD, fst), (TPAD, tst)):
    if tag and AXIAL and not lst:
        die('no clear axial entry into %s (pad off the 45-degree lattice, or the stub to pad edge + %.1f mm is '
            'blocked) - free the pad axis, or route with --no-axial and finish the entry by hand' % (tag, BEND_MIN), 1)
FSTUB = TSTUB = None
AVOID = set()
path, POP = None, 0
for fs in fst[:2]:
    for ts in tst[:2]:
        start = fs['end'] if fs else start0
        goalset = {ts['end']} if ts else goal0
        avoid = (fs['avoid'] if fs else set()) | (ts['avoid'] if ts else set())
        if REFIN_CUT and start0 in avoid and not fs:
            die('--refinish %s: the cut point (%.3f, %.3f) is %.3f mm from the pad centre, inside the stub zone (pad edge '
                '+ %.1f mm) - usually a via right next to the pad: move it out first (or --refinish-length longer when '
                'the chain continues)' % (REFIN, fx, fy, math.hypot(fx - tx, fy - ty), BEND_MIN), 1)
        avoid -= {start} | goalset
        for stub in (fs, ts):
            if stub and stub.get('shared'):
                print('axial stub into %s on %s: dir %s - shares the existing stub ending at (%.4f, %.4f)' % (
                    stub['tag'], LNAME[LAYERS[stub['li']]], stub['dir'], stub['shared'][0], stub['shared'][1]))
            elif stub:
                print('axial stub into %s on %s: dir %s, pad reach %.3f mm, %d cells, width %.3f mm' % (
                    stub['tag'], LNAME[LAYERS[stub['li']]], stub['dir'], stub['reach'], len(stub['cells']) - 1,
                    stub['width']))
        print('start %s -> goal %s' % (start, sorted(goalset)))
        # a stub runs out of its pad along dir: the route continues from its end in that direction, and enters the
        # goal stub against it (toward the pad)
        DIN = _dir_index(fs['dir']) if fs else -1
        DOUT = _dir_index((-ts['dir'][0], -ts['dir'][1])) if ts else -1
        path, n = astar(start, goalset, avoid, DIN, DOUT)
        POP += n
        if path:
            FSTUB, TSTUB, AVOID = fs, ts, avoid
            break
    if path:
        break
if not path:
    die('NO PATH found for %s (expanded %d cells)%s' % (NET, POP, ' with axial entries - --no-axial routes without'
                                                         if (fst[0] or tst[0]) else ''), 1)
print('path: %d cells, %d expansions' % (len(path), POP))


# ---------------------------------------------------------------- simplify to 45-degree runs
# A* returns a staircase. The standard requires clean 45/90 runs, so re-fit the cell path with
# the fewest straight segments that stay collision-free.
def passable(cx, cy, li):
    if not (0 <= cx < W and 0 <= cy < H):
        return False
    return (own[li][cx, cy] or not blocked[li][cx, cy]) and (cx, cy, li) not in AVOID


def seg_clear(a, b, li):
    """a->b must be horizontal, vertical or exactly 45; every cell along it must be passable."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    if dx == 0 and dy == 0:
        return True
    if not (dx == 0 or dy == 0 or abs(dx) == abs(dy)):
        return False
    n = max(abs(dx), abs(dy))
    sx = (dx > 0) - (dx < 0)
    sy = (dy > 0) - (dy < 0)
    for k in range(n + 1):
        if not passable(a[0] + sx * k, a[1] + sy * k, li):
            return False
    return True


def corners(a, b):
    """The two 45-degree L routes from a to b: diagonal-then-straight, straight-then-diagonal."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    sx = (dx > 0) - (dx < 0)
    sy = (dy > 0) - (dy < 0)
    m = min(abs(dx), abs(dy))
    out = []
    out.append((a[0] + sx * m, a[1] + sy * m))          # diagonal first
    if abs(dx) > abs(dy):
        out.append((b[0] - sx * m, b[1] - sy * m))      # straight first
    else:
        out.append((b[0] - sx * m, b[1] - sy * m))
    return out


def simplify_run(cells, li, din=-1, dout=-1):
    """Greedy: from i, reach the furthest j joinable by 1 or 2 clean segments. With NO_ACUTE (1.27.0) a shortcut
    is taken only if it turns by 90 degrees or less from the segment before it (din at the start) and, at the end
    of the run, from dout."""
    out = [cells[0]]
    i = 0

    def fits(a, c, b, j):
        if not NO_ACUTE:
            return True
        prev = _dir_index((out[-1][0] - out[-2][0], out[-1][1] - out[-2][1])) if len(out) > 1 else din
        d1 = _dir_index((c[0] - a[0], c[1] - a[1]))
        d2 = _dir_index((b[0] - c[0], b[1] - c[1]))
        first = d1 if d1 >= 0 else d2          # a corner on a or on b leaves one leg
        last = d2 if d2 >= 0 else d1
        return _turn_ok(prev, first) and _turn_ok(d1, d2) and (j < len(cells) - 1 or _turn_ok(last, dout))

    while i < len(cells) - 1:
        best_j, best_mid = i + 1, None
        for j in range(len(cells) - 1, i, -1):
            a, b = cells[i], cells[j]
            if seg_clear(a, b, li) and fits(a, b, b, j):
                best_j, best_mid = j, None
                break
            hit = None
            for c in corners(a, b):
                if seg_clear(a, c, li) and seg_clear(c, b, li) and fits(a, c, b, j):
                    hit = c
                    break
            if hit is not None:
                best_j, best_mid = j, hit
                break
        if best_mid is not None:
            out.append(best_mid)
        out.append(cells[best_j])
        i = best_j
    return out


runs = []
cur_layer = path[0][2]
cur = [(path[0][0], path[0][1])]
for (cx, cy, cl) in path[1:]:
    if cl != cur_layer:
        runs.append((cur_layer, cur, (cx, cy)))
        cur_layer = cl
        cur = [(cx, cy)]
    else:
        cur.append((cx, cy))
runs.append((cur_layer, cur, None))

simple = []
for ri, (li, cells, viapt) in enumerate(runs):
    sc = simplify_run(cells, li, DIN if ri == 0 else -1, DOUT if ri == len(runs) - 1 else -1) if len(cells) > 1 else cells
    simple.append((li, sc, viapt))
print('simplified: %d cells -> %d vertices'
      % (len(path), sum(len(x[1]) for x in simple)))

path = []
for (li, cells, viapt) in simple:
    for (cx, cy) in cells:
        path.append((cx, cy, li))
    if viapt is not None:
        path.append((viapt[0], viapt[1], 1 - li))

# ---------------------------------------------------------------- path -> segments
pts = []
for (cx, cy, cl) in path:
    mx, my = g2m(cx, cy)
    pts.append((mx, my, cl))
# NOTE: endpoints are deliberately NOT moved onto the exact pad centre. A track that ends
# anywhere inside the target copper connects it, and forcing the vertex to an arbitrary centre
# would put that last segment off the 45-degree lattice, which is an audit FAIL.

# Drop consecutive duplicate points. A layer change produces the same (x,y) twice, and a
# zero-length step makes the collinearity cross-product below identically zero, which merges the
# entire remaining run into one off-lattice segment.
ded = [pts[0]]
for q in pts[1:]:
    px, py, pl = ded[-1]
    if abs(q[0] - px) < 1e-9 and abs(q[1] - py) < 1e-9 and q[2] == pl:
        continue
    ded.append(q)
pts = ded

segs, vias = [], []
i = 0
while i < len(pts) - 1:
    x1, y1, l1 = pts[i]
    x2, y2, l2 = pts[i + 1]
    if l1 != l2:
        vias.append((x1, y1))
        i += 1
        continue
    # extend while direction is unchanged
    j = i + 1
    dx, dy = x2 - x1, y2 - y1
    while (abs(dx) > 1e-9 or abs(dy) > 1e-9) and j + 1 < len(pts):
        x3, y3, l3 = pts[j + 1]
        if l3 != l1:
            break
        ex, ey = x3 - pts[j][0], y3 - pts[j][1]
        if abs(ex * dy - ey * dx) > 1e-9:
            break
        j += 1
    segs.append((x1, y1, pts[j][0], pts[j][1], l1))
    i = j

def _onlat(x1, y1, x2, y2):
    dx, dy = abs(x2 - x1), abs(y2 - y1)
    return dx < 1e-6 or dy < 1e-6 or abs(dx - dy) < 1e-6


# --from-pad / --to-pad: put the end vertex exactly on an off-grid pad centre when the segment stays on the lattice
if (FPAD or REFIN_CUT) and not FSTUB and segs and math.hypot(segs[0][0] - fx, segs[0][1] - fy) < GRID and _onlat(fx, fy, segs[0][2], segs[0][3]):
    segs[0] = (fx, fy) + tuple(segs[0][2:])
elif REFIN_CUT and segs and math.hypot(segs[0][0] - fx, segs[0][1] - fy) > 1e-6:
    print('  WARN: the re-route starts %.3f mm from the cut vertex (off the grid) - the copper overlaps; join it by '
          'hand if the audit reports a dangling end' % math.hypot(segs[0][0] - fx, segs[0][1] - fy))
if TPAD and not TSTUB and segs and math.hypot(segs[-1][2] - tx, segs[-1][3] - ty) < GRID and _onlat(segs[-1][0], segs[-1][1], tx, ty):
    segs[-1] = tuple(segs[-1][:2]) + (tx, ty, segs[-1][4])
segs = [s_ + (WIDTH,) for s_ in segs]


def _stub_seg(stub, cx, cy):
    """Stub from the exact pad centre (cx, cy) to the stub end; the grid centre when the exact one is off the axis."""
    ex, ey = g2m(*stub['cells'][-1])
    if not _onlat(cx, cy, ex, ey):
        print('  WARN: the centre of %s is off the grid axis - the stub starts at the nearest grid point' % stub['tag'])
        cx, cy = g2m(*stub['cells'][0])
    return cx, cy, ex, ey


for stub, first in ((FSTUB, True), (TSTUB, False)):
    if not stub or not segs:
        continue
    if stub.get('shared'):              # join the existing stub's end exactly when the lattice allows
        ex, ey = stub['shared']
        s0 = segs[0] if first else segs[-1]
        near = (s0[0], s0[1]) if first else (s0[2], s0[3])
        other = (s0[2], s0[3]) if first else (s0[0], s0[1])
        if math.hypot(near[0] - ex, near[1] - ey) < 2 * GRID and _onlat(ex, ey, *other):
            segs[0 if first else -1] = ((ex, ey) + other if first else other + (ex, ey)) + s0[4:]
        elif math.hypot(near[0] - ex, near[1] - ey) > 1e-6:
            print('  WARN: the route meets the shared stub of %s %.3f mm from its end - join it by hand' % (
                stub['tag'], math.hypot(near[0] - ex, near[1] - ey)))
        continue
    cx_, cy_ = (fx, fy) if first else (tx, ty)
    x1, y1, x2, y2 = _stub_seg(stub, cx_, cy_)
    if first:
        segs.insert(0, (x1, y1, x2, y2, stub['li'], stub['width']))
    else:
        segs.append((x2, y2, x1, y1, stub['li'], stub['width']))
bad = []
for (x1, y1, x2, y2, li, _w) in segs:
    dx, dy = abs(x2 - x1), abs(y2 - y1)
    if dx < 1e-9 and dy < 1e-9:
        continue
    if not (dx < 1e-9 or dy < 1e-9 or abs(dx - dy) < 1e-6):
        bad.append((x1, y1, x2, y2, LNAME[LAYERS[li]]))
if bad:
    for b_ in bad:
        sys.stderr.write('  OFF-LATTICE %s (%.3f,%.3f)->(%.3f,%.3f)' % (b_[4], b_[0], b_[1], b_[2], b_[3]) + chr(10))
    die('%d segment(s) are not horizontal / vertical / 45 - refusing to write' % len(bad), 3)

segs = [s_ for s_ in segs if abs(s_[2] - s_[0]) > 1e-9 or abs(s_[3] - s_[1]) > 1e-9]

# Acute joints (1.27.0): two consecutive segments of the route on one layer may turn by 90 degrees at most (the audit's
# `acute` FAIL, Vladimir's rule). The search and the simplifier avoid them; this is the final check before writing.
_acute = []
for s1, s2 in zip(segs, segs[1:]):
    if s1[4] != s2[4] or abs(s1[2] - s2[0]) > 1e-6 or abs(s1[3] - s2[1]) > 1e-6:
        continue
    if (s1[2] - s1[0]) * (s2[2] - s2[0]) + (s1[3] - s1[1]) * (s2[3] - s2[1]) < -1e-9:
        _acute.append((LNAME[LAYERS[s1[4]]], s1[2], s1[3]))
if _acute and '--allow-acute' not in args:
    for lay, x, y in _acute:
        sys.stderr.write('  ACUTE joint %s (%.3f,%.3f)\n' % (lay, x, y))
    die('%d acute joint(s) (a turn sharper than 90 degrees) - refusing to write' % len(_acute), 5)

# Duplicate copper (1.23.0): own copper is passable, so a route can run along a track of its own net - the audit's
# loop check FAILs that (parallel same-net copper < 0.3 mm apart over > 0.5 mm, review issue 14). Refuse to write it.
def _dup(seg, t):
    x1, y1, x2, y2 = seg[:4]
    a_, b_ = t.GetStart(), t.GetEnd()
    u1, v1, u2, v2 = a_.x / MM, a_.y / MM, b_.x / MM, b_.y / MM
    dx, dy = x2 - x1, y2 - y1
    ln = math.hypot(dx, dy)
    ex, ey = u2 - u1, v2 - v1
    lt = math.hypot(ex, ey)
    if ln < 1e-9 or lt < 1e-9 or abs(dx * ey - dy * ex) / (ln * lt) > 0.02:
        return 0.0
    ux, uy = dx / ln, dy / ln
    if abs((u1 - x1) * uy - (v1 - y1) * ux) >= 0.3:
        return 0.0
    p1, p2 = sorted(((u1 - x1) * ux + (v1 - y1) * uy, (u2 - x1) * ux + (v2 - y1) * uy))
    return max(0.0, min(ln, p2) - max(0.0, p1))


_own_now = [t for t in B.GetTracks() if t.Type() == pcbnew.PCB_TRACE_T and t.GetNetname() == NET]
_dups = [(s_, t) for s_ in segs for t in _own_now if t.GetLayer() == LAYERS[s_[4]] and _dup(s_, t) > 0.5]
if _dups and '--allow-overlap' not in args:
    for s_, t in _dups[:4]:
        sys.stderr.write('  DUPLICATE: new (%.3f,%.3f)->(%.3f,%.3f) runs along %s track (%.3f,%.3f)->(%.3f,%.3f)\n' % (
            s_[0], s_[1], s_[2], s_[3], NET, t.GetStart().x / MM, t.GetStart().y / MM, t.GetEnd().x / MM, t.GetEnd().y / MM))
    die('%d new segment(s) would duplicate copper of %s (audit loop FAIL) - nothing written (--allow-overlap overrides)'
        % (len(_dups), NET), 4)
print('result: %d segment(s), %d via(s)  [all on the 45 lattice]' % (len(segs), len(vias)))
for s in segs:
    print('   %s (%.3f,%.3f)->(%.3f,%.3f) w %.3f' % (LNAME[LAYERS[s[4]]], s[0], s[1], s[2], s[3], s[5]))
for v in vias:
    print('   VIA @ (%.3f,%.3f)' % v)

if DRY:
    sys.exit(0)

nm = B.GetNetsByName()
netcode = None
for k in nm.keys():
    if str(k) == NET:
        netcode = nm[k].GetNetCode()
        break
if netcode is None:
    die('net not found: ' + NET)

for (x1, y1, x2, y2, li, sw) in segs:
    t = pcbnew.PCB_TRACK(B)
    t.SetStart(pcbnew.VECTOR2I(int(round(x1 * MM)), int(round(y1 * MM))))
    t.SetEnd(pcbnew.VECTOR2I(int(round(x2 * MM)), int(round(y2 * MM))))
    t.SetWidth(int(round(sw * MM)))
    t.SetLayer(LAYERS[li])
    t.SetNetCode(netcode)
    B.Add(t)
for (x, y) in vias:
    v = pcbnew.PCB_VIA(B)
    v.SetPosition(pcbnew.VECTOR2I(int(round(x * MM)), int(round(y * MM))))
    v.SetWidth(int(round(VIA_D * MM)))
    v.SetDrill(int(round(VIA_DRILL * MM)))
    v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetLayerPair(LAYERS[0], LAYERS[1])
    v.SetRemoveUnconnected(True)
    v.SetKeepStartEnd(True)
    v.SetNetCode(netcode)
    B.Add(v)

zone_fill_check.refill(B)          # the SAVED fill must be current (board review rev. 0.2, issue 1)
B.Save(BOARD)
print('saved')
