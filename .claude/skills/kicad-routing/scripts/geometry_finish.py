#!/usr/bin/env python
"""geometry_finish.py - post-routing geometric refinement (kicad-golden 1.16.0, improvements review).

MUST be run with KiCad's own Python (it imports pcbnew).

    geometry_finish.py <board.kicad_pcb> [--all] [--params kicad_golden.project.json]
        [--center-gaps] [--neck-pad-entries] [--pad-centre-entries] [--route-around] [--spread]
        [--fix-plane-links] [--report-shared-gaps] [--crystal-inductor-keepouts]
        [--clearance MM] [--via-d MM] [--via-drill MM] [--dry-run]

Implements improvements entries 3-11 (see CHANGELOG.md 1.16.0 and SKILL.md
Post-Routing Geometric Refinement). Order matters:

  --crystal-inductor-keepouts   PRE-ROUTING. Adds rule areas over crystal/inductor courtyards so
                                Freerouting avoids them (improvements #4 exception).
  everything else               POST-IMPORT, after the 45-degree/neckdown/via-stack repair in
                                repair_import.py, because they assume lattice-clean geometry.

WHAT IS FIXED AUTOMATICALLY, AND WHAT IS ONLY REPORTED. --center-gaps, --neck-pad-entries and
--pad-centre-entries rewrite the common, simple topology: an isolated straight segment between two
lattice joints (no branch), or a pad-entry run whose direction already lines up with the pad centre.
A segment that is part of a longer multi-branch run, or whose neighbours would need to move too (see
SKILL.md, "Any geometric snap must be scoped to what you are fixing"), is left alone and named in the
report. --route-around and --spread are harder still: the improvements review's own test found the
keepout approach to entry 10 stalls Freerouting outright, and a fix-afterward pass only rehomed 10 of
32 offending runs. Treat both as best-effort - read the report, do not assume either brought the
count to zero.

Exit codes: 0 ok, 2 usage.
"""
import sys
import os
import json
import math
import pcbnew
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board_guard  # noqa: E402
import zone_fill_check  # noqa: E402

MM = 1e6


def die(m, c=2):
    sys.stderr.write(str(m) + '\n')
    sys.exit(c)


args = sys.argv[1:]
if not args or args[0].startswith('--'):
    die(__doc__)
BOARD = args[0]
ALL = '--all' in args
FLAGS = {
    'center_gaps': ALL or '--center-gaps' in args,
    'neck_pad_entries': ALL or '--neck-pad-entries' in args,
    'pad_centre_entries': ALL or '--pad-centre-entries' in args,
    'route_around': ALL or '--route-around' in args,
    'spread': ALL or '--spread' in args,
    'fix_plane_links': ALL or '--fix-plane-links' in args,
    'report_shared_gaps': ALL or '--report-shared-gaps' in args,
    'crystal_inductor_keepouts': '--crystal-inductor-keepouts' in args,  # pre-routing; never in --all
}
if not any(FLAGS.values()):
    die('nothing to do - pass a flag (see --help text above) or --all')


def opt(name, default=None):
    if name in args:
        i = args.index(name)
        if i + 1 >= len(args):
            die(name + ' needs a value')
        return args[i + 1]
    return default


CLEARANCE = float(opt('--clearance', '0.1'))
VIA_D = float(opt('--via-d', '0.45'))
VIA_DRILL = float(opt('--via-drill', '0.2'))
DRY = '--dry-run' in args

PARAMS_PATH = opt('--params')
if not PARAMS_PATH:
    for cand in (os.path.splitext(BOARD)[0] + '.golden.json',
                 os.path.join(os.path.dirname(os.path.abspath(BOARD)), 'kicad_golden.project.json')):
        if os.path.exists(cand):
            PARAMS_PATH = cand
            break
PARAMS = {}
if PARAMS_PATH and os.path.exists(PARAMS_PATH):
    with open(PARAMS_PATH, encoding='utf-8') as f:
        PARAMS = json.load(f)
SHARED_GAPS_ALLOWED = bool((PARAMS.get('shared_pad_gaps') or {}).get('allowed'))
PLANE_EXCEPTIONS = {(e.get('ref'), e.get('pad')) for e in (PARAMS.get('plane_net_exceptions') or {}).get('allowed', [])}
DETOUR = PARAMS.get('detour_limits') or {}
DETOUR_PCT = DETOUR.get('max_length_increase_pct', 50) / 100.0
DETOUR_MM = DETOUR.get('max_length_increase_mm', 10)

if not DRY and any(v for k, v in FLAGS.items() if k != 'report_shared_gaps'):     # a report alone writes nothing
    board_guard.check_board_writable(BOARD, script='geometry_finish.py')   # KiCad lock / .kicad_pro beside it
B = pcbnew.LoadBoard(BOARD)
COPPER_LAYERS = {pcbnew.F_Cu, pcbnew.B_Cu}


def is_copper_track(t):
    return t.GetClass() == 'PCB_TRACK' and t.GetLayer() in COPPER_LAYERS


def all_pads():
    for fp in B.GetFootprints():
        for p in fp.Pads():
            yield p


PADS = list(all_pads())


def pad_reach(pad, ux, uy):
    """Half-extent of a (possibly rotated) rectangular pad projected onto direction (ux,uy)."""
    th = -pad.GetOrientation().AsDegrees() * math.pi / 180.0
    lx = ux * math.cos(th) - uy * math.sin(th)
    ly = ux * math.sin(th) + uy * math.cos(th)
    w, h = pad.GetSize().x / MM, pad.GetSize().y / MM
    return abs(lx) * w / 2.0 + abs(ly) * h / 2.0


def pad_min_dim(pad):
    return min(pad.GetSize().x, pad.GetSize().y) / MM


class PadBucket:
    """Coarse spatial index over PADS, cell size in mm."""

    def __init__(self, pads, cell=2.0):
        self.cell = cell
        self.map = {}
        for p in pads:
            k = self._key(p.GetPosition().x / MM, p.GetPosition().y / MM)
            self.map.setdefault(k, []).append(p)

    def _key(self, x, y):
        return (int(math.floor(x / self.cell)), int(math.floor(y / self.cell)))

    def near(self, x0, y0, x1, y1, pad=3.0):
        out = []
        bx0, bx1 = int(math.floor((min(x0, x1) - pad) / self.cell)), int(math.floor((max(x0, x1) + pad) / self.cell))
        by0, by1 = int(math.floor((min(y0, y1) - pad) / self.cell)), int(math.floor((max(y0, y1) + pad) / self.cell))
        for bx in range(bx0, bx1 + 1):
            for by in range(by0, by1 + 1):
                out.extend(self.map.get((bx, by), []))
        return out


BUCKET = PadBucket(PADS)


def flanking_pair(t):
    """For a copper track, find the pad pair (if any) it passes between: nearest foreign-net pad on
    each perpendicular side, within a tight-enough gap. Mirrors kicad_audit.js check 16."""
    s, e = t.GetStart(), t.GetEnd()
    x1, y1, x2, y2 = s.x / MM, s.y / MM, e.x / MM, e.y / MM
    length = math.hypot(x2 - x1, y2 - y1)
    if length < 0.3:
        return None
    ux, uy = (x2 - x1) / length, (y2 - y1) / length
    nx, ny = -uy, ux
    net = t.GetNetname()
    layer = t.GetLayer()
    best_pos, best_neg = None, None
    for p in BUCKET.near(x1, y1, x2, y2, 3.0):
        if p.GetNetname() == net or not p.IsOnLayer(layer):
            continue
        px, py = p.GetPosition().x / MM, p.GetPosition().y / MM
        tt = (px - x1) * ux + (py - y1) * uy
        if tt < -0.5 or tt > length + 0.5:
            continue
        d = (px - x1) * nx + (py - y1) * ny
        if d >= 0 and (best_pos is None or d < best_pos[1]):
            best_pos = (p, d)
        if d < 0 and (best_neg is None or d > best_neg[1]):
            best_neg = (p, d)
    if not best_pos or not best_neg:
        return None
    if abs(best_pos[1]) + abs(best_neg[1]) > 6:
        return None
    p1, d1 = best_pos
    p2, d2 = best_neg
    half_w = t.GetWidth() / MM / 2.0
    c1 = abs(d1) - half_w - pad_reach(p1, nx, ny)
    c2 = abs(d2) - half_w - pad_reach(p2, nx, ny)
    return {'p1': p1, 'p2': p2, 'c1': c1, 'c2': c2, 'ux': ux, 'uy': uy, 'nx': nx, 'ny': ny,
            'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2, 'length': length}


def endpoint_free(t, which):
    """True if the given end (0=start,1=end) touches no pad and no via - a plain lattice joint that
    only continues to another track, safe to nudge without disturbing a connection point."""
    pt = t.GetStart() if which == 0 else t.GetEnd()
    for p in BUCKET.near(pt.x / MM, pt.y / MM, pt.x / MM, pt.y / MM, 0.01):
        if (p.GetPosition() - pt).EuclideanNorm() < 1000:  # 1 um
            return False
    for o in B.GetTracks():
        if o.GetClass() != 'PCB_VIA':
            continue
        if (o.GetPosition() - pt).EuclideanNorm() < 1000:
            return False
    return True


def add_track(x1, y1, x2, y2, width_mm, layer, netcode):
    nt = pcbnew.PCB_TRACK(B)
    nt.SetStart(pcbnew.VECTOR2I(int(round(x1 * MM)), int(round(y1 * MM))))
    nt.SetEnd(pcbnew.VECTOR2I(int(round(x2 * MM)), int(round(y2 * MM))))
    nt.SetWidth(int(round(width_mm * MM)))
    nt.SetLayer(layer)
    nt.SetNetCode(netcode)
    B.Add(nt)
    return nt


def add_via(x, y, netcode, size_mm=None, drill_mm=None):
    v = pcbnew.PCB_VIA(B)
    v.SetPosition(pcbnew.VECTOR2I(int(round(x * MM)), int(round(y * MM))))
    v.SetWidth(int(round((size_mm or VIA_D) * MM)))
    v.SetDrill(int(round((drill_mm or VIA_DRILL) * MM)))
    v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    v.SetNetCode(netcode)
    B.Add(v)
    return v


MIN_SEG_MM = 0.01  # below this, a "segment" is numerically zero-length, not a real one


def _on_lattice(x1, y1, x2, y2, tol_deg=0.02):
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length < MIN_SEG_MM:
        return False
    a = math.degrees(math.atan2(dy, dx)) % 45.0
    return min(a, 45.0 - a) < tol_deg


def shift_isolated_segment(t, delta_perp, nx, ny, max_jog_frac=0.4):
    """Shift the middle of an isolated segment sideways by delta_perp (mm, along (nx,ny)), keeping
    both original endpoints fixed by inserting a 45-degree jog at each end. Returns True if applied,
    False if the segment is not free at both ends, too short for the jog to fit, or the result would
    not be three genuine (non-zero-length, lattice-exact) segments - checked BEFORE anything is
    removed from the board, so a rejected shift never touches the original track."""
    if not (endpoint_free(t, 0) and endpoint_free(t, 1)):
        return False
    s, e = t.GetStart(), t.GetEnd()
    x1, y1, x2, y2 = s.x / MM, s.y / MM, e.x / MM, e.y / MM
    length = math.hypot(x2 - x1, y2 - y1)
    jog = abs(delta_perp)
    if jog < 1e-4 or jog > length * max_jog_frac:
        return False
    ux, uy = (x2 - x1) / length, (y2 - y1) / length
    # jog point A: move 'jog' further along the track AND 'delta_perp' sideways (45 degrees)
    ax, ay = x1 + ux * jog + nx * delta_perp, y1 + uy * jog + ny * delta_perp
    bx, by = x2 - ux * jog + nx * delta_perp, y2 - uy * jog + ny * delta_perp
    for (px1, py1, px2, py2) in ((x1, y1, ax, ay), (ax, ay, bx, by), (bx, by, x2, y2)):
        if not _on_lattice(px1, py1, px2, py2):
            return False
    width_mm = t.GetWidth() / MM
    layer, netcode = t.GetLayer(), t.GetNetCode()
    B.Remove(t)
    add_track(x1, y1, ax, ay, width_mm, layer, netcode)
    add_track(ax, ay, bx, by, width_mm, layer, netcode)
    add_track(bx, by, x2, y2, width_mm, layer, netcode)
    return True


report = {k: 0 for k in FLAGS}
report['still_off_centre'] = []
report['still_wide'] = []
report['shared_gaps'] = []
report['plane_net_still_linked'] = []
report['route_around_left'] = []
report['crystal_inductor_keepouts_added'] = 0

# ---------------------------------------------------------------- --crystal-inductor-keepouts (pre-routing)
if FLAGS['crystal_inductor_keepouts']:
    def is_crystal_inductor(fp):
        libname = fp.GetFPIDAsString()
        ref = fp.GetReference()
        low = libname.lower()
        return ('crystal' in low or 'oscillator' in low or 'resonator' in low
                or 'inductor' in low or 'choke' in low or 'ferrite' in low
                or (len(ref) >= 2 and ref[0] in 'YXL' and ref[1:].isdigit()))

    existing_ko = {z.GetZoneName() for z in B.Zones() if z.GetIsRuleArea()}
    skipped_invalid = []
    for fp in B.GetFootprints():
        if not is_crystal_inductor(fp):
            continue
        zname = 'KO_%s_courtyard' % fp.GetReference()
        if zname in existing_ko:
            continue  # already has one - safe to re-run this flag
        mount = fp.GetLayer()
        crt_layer = pcbnew.F_CrtYd if mount == pcbnew.F_Cu else pcbnew.B_CrtYd
        box = None
        for it in fp.GraphicalItems():
            if it.GetClass() != 'PCB_SHAPE' or it.GetLayer() != crt_layer:
                continue
            bb = it.GetBoundingBox()
            box = bb if box is None else (box.Merge(bb) or box)
        if box is None:
            continue
        # Sanity gate: a real courtyard is at most a few hundred mm across and sits on the board.
        # A KiCad-internal bounding-box int32 overflow (seen on this board's inductor footprints)
        # produces a numerically "valid" but physically absurd box - reject it rather than write a
        # corrupted rule area (observed once: width/height wrapped to -497 / 2147483 mm, the
        # int32-nm overflow signature).
        w_mm, h_mm = box.GetWidth() / MM, box.GetHeight() / MM
        fpos = fp.GetPosition()
        offset_mm = ((box.GetCenter().x - fpos.x) ** 2 + (box.GetCenter().y - fpos.y) ** 2) ** 0.5 / MM
        if w_mm <= 0 or h_mm <= 0 or w_mm > 500 or h_mm > 500 or offset_mm > 100:
            skipped_invalid.append('%s (courtyard bbox looked invalid: %.1fx%.1f mm, %.1f mm from origin)' % (fp.GetReference(), w_mm, h_mm, offset_mm))
            continue
        z = pcbnew.ZONE(B)
        z.SetIsRuleArea(True)
        z.SetDoNotAllowTracks(True)
        z.SetDoNotAllowVias(True)
        z.SetDoNotAllowPads(False)
        z.SetDoNotAllowZoneFills(False)
        z.SetDoNotAllowFootprints(False)
        z.SetLayer(mount)
        z.SetZoneName(zname)
        outline = z.Outline()
        outline.NewOutline()
        x0, y0, x1, y1 = box.GetLeft(), box.GetTop(), box.GetRight(), box.GetBottom()
        for (x, y) in [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]:
            outline.Append(x, y)
        B.Add(z)
        report['crystal_inductor_keepouts_added'] += 1
    print('crystal/inductor keepouts added: %d' % report['crystal_inductor_keepouts_added'])
    if skipped_invalid:
        print('skipped (bad bounding-box computation, needs a hand-drawn keepout instead): %s' % '; '.join(skipped_invalid))

# ---------------------------------------------------------------- --report-shared-gaps / FAIL enforcement (Q-16)
if FLAGS['report_shared_gaps']:
    gaps = {}
    for t in B.GetTracks():
        if not is_copper_track(t):
            continue
        pair = flanking_pair(t)
        if not pair:
            continue
        key = tuple(sorted(['%s-%s' % (pair['p1'].GetParentFootprint().GetReference(), pair['p1'].GetNumber()),
                            '%s-%s' % (pair['p2'].GetParentFootprint().GetReference(), pair['p2'].GetNumber())]))
        gaps.setdefault(key, set()).add(t.GetNetname())
    for key, nets in gaps.items():
        if len(nets) >= 2:
            report['shared_gaps'].append({'pads': list(key), 'nets': sorted(nets)})
    print('pad gaps carrying 2+ tracks: %d%s' % (len(report['shared_gaps']),
          ' (allowed by project params, WARN only)' if SHARED_GAPS_ALLOWED else ' (not allowed - FAIL, see Q-16)'))
    for g in report['shared_gaps']:
        print('   %s: %s' % (' / '.join(g['pads']), ', '.join(g['nets'])))

# ---------------------------------------------------------------- --center-gaps (entries 3, 4) + --route-around (10)
if FLAGS['center_gaps'] or FLAGS['route_around']:
    for t in list(B.GetTracks()):
        if not is_copper_track(t):
            continue
        pair = flanking_pair(t)
        if not pair:
            continue
        same_fp = pair['p1'].GetParentFootprint() is pair['p2'].GetParentFootprint()
        mismatch = pair['c1'] - pair['c2']
        if FLAGS['center_gaps'] and abs(mismatch) > 0.01:
            delta = mismatch / 2.0  # move the segment toward the midpoint clearance
            applied = shift_isolated_segment(t, -delta, pair['nx'], pair['ny'])
            if applied:
                report['center_gaps'] += 1
            else:
                ref1 = '%s-%s' % (pair['p1'].GetParentFootprint().GetReference(), pair['p1'].GetNumber())
                ref2 = '%s-%s' % (pair['p2'].GetParentFootprint().GetReference(), pair['p2'].GetNumber())
                report['still_off_centre'].append('%s: %s / %s' % (t.GetNetname(), ref1, ref2))
        elif same_fp and FLAGS['route_around']:
            report['route_around_left'].append('%s under %s' % (t.GetNetname(), pair['p1'].GetParentFootprint().GetReference()))

if FLAGS['center_gaps']:
    print('gaps re-centred: %d' % report['center_gaps'])
    if report['still_off_centre']:
        print('still off-centre (multi-branch or pad-touching, needs manual attention): %d' % len(report['still_off_centre']))
        for m in report['still_off_centre'][:20]:
            print('   %s' % m)

if FLAGS['route_around']:
    # NOT an automated reroute: the improvements review's own test found a pre-routing keepout
    # stalls Freerouting outright, and this is exactly the geometry a bounding-box detour would have
    # to thread through the SAME footprint's other copper without new tooling to prove it is safe.
    # This flag only reports candidates, for a human (or route_finish.py, by hand) to act on.
    print('tracks passing under a part, candidates for a manual detour: %d' % len(report['route_around_left']))
    for m in report['route_around_left'][:20]:
        print('   %s' % m)

# ---------------------------------------------------------------- --neck-pad-entries (entry 5)
if FLAGS['neck_pad_entries']:
    necked = 0
    for t in list(B.GetTracks()):
        if not is_copper_track(t):
            continue
        s, e = t.GetStart(), t.GetEnd()
        width_mm = t.GetWidth() / MM
        for end, other in ((s, e), (e, s)):
            hit = None
            for p in BUCKET.near(end.x / MM, end.y / MM, end.x / MM, end.y / MM, 0.01):
                if p.GetNetname() != t.GetNetname():
                    continue
                if (p.GetPosition() - end).EuclideanNorm() < 1000:  # 1 um: exact pad-centre entry
                    hit = p
                    break
            if hit is None:
                continue
            min_dim = pad_min_dim(hit)
            if width_mm <= min_dim + 1e-6:
                continue
            x1, y1 = end.x / MM, end.y / MM
            x2, y2 = other.x / MM, other.y / MM
            length = math.hypot(x2 - x1, y2 - y1)
            ux, uy = (x2 - x1) / length, (y2 - y1) / length
            boundary = pad_reach(hit, ux, uy) + CLEARANCE
            if boundary >= length - MIN_SEG_MM:
                continue  # the whole segment is inside the clearance area; nothing to keep at full width
            bx, by = x1 + ux * boundary, y1 + uy * boundary
            layer, netcode = t.GetLayer(), t.GetNetCode()
            B.Remove(t)
            add_track(x1, y1, bx, by, min_dim, layer, netcode)
            add_track(bx, by, x2, y2, width_mm, layer, netcode)
            necked += 1
            break
    report['neck_pad_entries'] = necked
    print('pad entries necked to the pad\'s smallest dimension: %d' % necked)

# ---------------------------------------------------------------- --pad-centre-entries (entries 8, 9 partial)
if FLAGS['pad_centre_entries']:
    snapped = 0
    for t in list(B.GetTracks()):
        if not is_copper_track(t):
            continue
        s, e = t.GetStart(), t.GetEnd()
        for end, other in ((s, e), (e, s)):
            exact = False
            near_pad = None
            for p in BUCKET.near(end.x / MM, end.y / MM, end.x / MM, end.y / MM, 1.0):
                if p.GetNetname() != t.GetNetname() or not p.IsOnLayer(t.GetLayer()):
                    continue
                d = (p.GetPosition() - end).EuclideanNorm()
                if d < 1000:
                    exact = True
                    break
                if d < max(p.GetSize().x, p.GetSize().y) / 2.0:
                    near_pad = p
            if exact or near_pad is None:
                continue
            c = near_pad.GetPosition()
            ox, oy = other.x / MM, other.y / MM
            cx, cy = c.x / MM, c.y / MM
            ang = math.degrees(math.atan2(cy - oy, cx - ox)) % 45.0
            on_lattice = min(ang, 45.0 - ang) < 0.05 and math.hypot(cx - ox, cy - oy) >= MIN_SEG_MM
            if on_lattice:
                if end == s:
                    t.SetStart(c)
                else:
                    t.SetEnd(c)
                snapped += 1
            else:
                report['still_off_centre'].append('%s @ %s-%s (direction not on the 45-degree lattice - needs a reroute, not a snap)' % (
                    t.GetNetname(), near_pad.GetParentFootprint().GetReference(), near_pad.GetNumber()))
    report['pad_centre_entries'] = snapped
    print('pad entries snapped exactly onto the pad centre: %d' % snapped)

# ---------------------------------------------------------------- --spread (entry 11, best-effort, component outlines only)
if FLAGS['spread']:
    spread = 0
    for t in list(B.GetTracks()):
        if not is_copper_track(t):
            continue
        s, e = t.GetStart(), t.GetEnd()
        length = t.GetLength() / MM
        if length < 2:
            continue
        x1, y1, x2, y2 = s.x / MM, s.y / MM, e.x / MM, e.y / MM
        mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        ux, uy = (x2 - x1) / length, (y2 - y1) / length
        nx, ny = -uy, ux
        pos_gap, neg_gap, pos_p, neg_p = None, None, None, None
        for p in BUCKET.near(mx, my, mx, my, 6.0):
            if p.GetNetname() == t.GetNetname() or not p.IsOnLayer(t.GetLayer()):
                continue
            px, py = p.GetPosition().x / MM, p.GetPosition().y / MM
            dx, dy = px - mx, py - my
            along = abs(dx * ux + dy * uy)
            if along > length / 2.0 + 1:
                continue
            d = dx * nx + dy * ny
            gap = abs(d) - t.GetWidth() / MM / 2.0 - max(p.GetSize().x, p.GetSize().y) / MM / 2.0
            if d >= 0 and (pos_gap is None or gap < pos_gap):
                pos_gap, pos_p = gap, p
            elif d < 0 and (neg_gap is None or gap < neg_gap):
                neg_gap, neg_p = gap, p
        if pos_gap is None or neg_gap is None:
            continue
        near, far = (pos_gap, neg_gap) if pos_gap < neg_gap else (neg_gap, pos_gap)
        if near < 2 * CLEARANCE and far >= 3 * near and far - near > 0.2:
            target_gap = (near + far) / 2.0
            move = target_gap - near
            move = max(-1.0, min(1.0, move if pos_gap < neg_gap else -move))
            if shift_isolated_segment(t, move, nx, ny):
                spread += 1
    report['spread'] = spread
    print('tracks spread away from a tight component outline: %d' % spread)

# ---------------------------------------------------------------- --fix-plane-links (entry 7)
if FLAGS['fix_plane_links']:
    plane_nets = set()
    for z in B.Zones():
        if z.GetIsRuleArea():
            continue
        if pcbnew.IsCopperLayer(z.GetLayer()) and z.GetLayer() not in (pcbnew.F_Cu, pcbnew.B_Cu):
            plane_nets.add(z.GetNetname())
    fixed_links = 0
    for net in plane_nets:
        segs = [t for t in B.GetTracks() if is_copper_track(t) and t.GetNetname() == net]
        if not segs:
            continue
        parent = {}

        def find(k):
            while parent.setdefault(k, k) != k:
                parent[k] = parent.get(parent[k], parent[k])
                k = parent[k]
            return k

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        def keyof(pt):
            return (pt.x, pt.y)

        for t in segs:
            union(keyof(t.GetStart()), keyof(t.GetEnd()))
        groups = {}
        pads_of_net = [p for p in PADS if p.GetNetname() == net]
        for p in pads_of_net:
            k = keyof(p.GetPosition())
            if k not in parent:
                continue  # no surface track touches this pad at all - fine
            groups.setdefault(find(k), []).append(p)
        for root, padsHere in groups.items():
            if len(padsHere) < 2:
                continue
            flagged = [p for p in padsHere if (p.GetParentFootprint().GetReference(), p.GetNumber()) not in PLANE_EXCEPTIONS]
            if len(flagged) < 2:
                continue
            # delete every surface track segment in this component, then give each flagged pad its own via
            comp_tracks = [t for t in segs if find(keyof(t.GetStart())) == root]
            for t in comp_tracks:
                B.Remove(t)
            for p in flagged:
                c = p.GetPosition()
                th = -p.GetOrientation().AsDegrees() * math.pi / 180.0
                w, h = p.GetSize().x / MM, p.GetSize().y / MM
                off = max(w, h) / 2.0 + VIA_D / 2.0 + CLEARANCE
                placed = False
                for (dx, dy) in ((1, 0), (0, 1), (-1, 0), (0, -1)):
                    vx, vy = c.x / MM + dx * off, c.y / MM + dy * off
                    if any((q.GetPosition() - pcbnew.VECTOR2I(int(vx * MM), int(vy * MM))).EuclideanNorm() < (VIA_D + 0.1) * MM
                           for q in PADS if q is not p):
                        continue
                    add_via(vx, vy, p.GetNetCode())
                    add_track(c.x / MM, c.y / MM, vx, vy, min(w, h), p.GetLayerSet().Seq()[0] if p.GetLayerSet().Seq() else pcbnew.F_Cu, p.GetNetCode())
                    placed = True
                    break
                if placed:
                    fixed_links += 1
                else:
                    report['plane_net_still_linked'].append('%s-%s (no clear spot for its own via)' % (
                        p.GetParentFootprint().GetReference(), p.GetNumber()))
    report['fix_plane_links'] = fixed_links
    print('plane-net pads given their own via (surface link removed): %d' % fixed_links)
    if report['plane_net_still_linked']:
        print('could not place a via for: %s' % ', '.join(report['plane_net_still_linked']))

if DRY:
    print('[dry-run] not written')
    sys.exit(0)

changed = any(report.get(k) for k in ('center_gaps', 'neck_pad_entries', 'pad_centre_entries', 'spread', 'fix_plane_links')) \
    or report['crystal_inductor_keepouts_added']
if changed:
    zone_fill_check.refill(B)      # the SAVED fill must be current (board review rev. 0.2, issue 1)
    B.Save(BOARD)
    print('saved')
else:
    print('nothing to change')
