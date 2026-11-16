#!/usr/bin/env python
"""center_gaps_safe.py - per-move centring of the audit's `between-pads` FAILs (playbook E6).
Origin: BladeOne routing trial tool (Vladimir Duk, 2026-09-28), brought into kicad-routing 1.18.0 with a batch
option --indices a,b,c used by centre_gated.py. Never run it unattended on the real board: its own clearance
model is not the judge (playbook G4) - centre_gated.py gates every batch with KiCad DRC and the audit.

center_gaps_safe.py <board> <audit.json> [--apply] - re-centre the segments kicad_audit.js reports as off-centre
(`between-pads`), SAFELY (decision of 2026-09-28, replacing geometry_finish.py --center-gaps):
  * the list of segments and the required correction come from the audit's own JSON, so the gap definition is
    the audit's by construction (own-pad flanks, 1.5 mm limit, via flanks, facing test);
  * only UNLOCKED segments are moved;
  * topology handled: a segment whose two ends each meet exactly ONE other segment (same net, same layer), no
    pad and no via there. The segment is shifted sideways by (c1 - c2) / 2; each neighbour keeps its direction
    and its far end, its shared end sliding along its own line to the shifted line - so every segment stays on
    the 45-degree lattice. A neighbour collinear with the segment, or that would shrink below 0.1 mm, is refused;
  * before a move is kept, the moved segment and both neighbours are checked with their true shapes against
    every other-net item near them (copper clearance, and hole clearance to other-net drills); proximity is
    judged by bounding box, never by an item's position (a long track's position is its start point).
Anything not handled is reported, never guessed. Dry run unless --apply."""
import pcbnew, sys, json, re, math, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board_guard, zone_fill_check  # noqa: E401,E402
args = sys.argv[1:]; APPLY = '--apply' in args
if APPLY:
    board_guard.check_board_writable(args[0], script='center_gaps_safe.py')
B = pcbnew.LoadBoard(args[0]); audit = json.load(open(args[1], encoding='utf-8'))
MM = 1e6
ds = B.GetDesignSettings(); CLR = ds.m_MinClearance; HCLR = ds.m_HoleClearance
RX = re.compile(r'^(.*) runs (?:between pads .+?|under two-pad part \S+) off-centre: ([-\d.]+) mm vs ([-\d.]+) mm .*@ ([-\d.]+),([-\d.]+) \((\S+)\)')
tracks = [t for t in B.GetTracks()]
segs = [t for t in tracks if t.GetClass() == 'PCB_TRACK']
vias = [t for t in tracks if t.GetClass() == 'PCB_VIA']
pads = [p for f in B.GetFootprints() for p in f.Pads()]
holes = [(v.GetPosition(), v.GetDrill() // 2, v.GetNetCode()) for v in vias]
holes += [(p.GetPosition(), max(p.GetDrillSize().x, p.GetDrillSize().y) // 2, p.GetNetCode()) for p in pads if p.GetDrillSize().x > 0]


def bb_near(item, box, r=1 * MM):
    b = item.GetBoundingBox()
    return not (b.GetRight() < box[0] - r or b.GetLeft() > box[2] + r or b.GetBottom() < box[1] - r or b.GetTop() > box[3] + r)


def clear(shape_items, net, layer):
    xs = [q for t in shape_items for q in (t.GetStart().x, t.GetEnd().x)]; ys = [q for t in shape_items for q in (t.GetStart().y, t.GetEnd().y)]
    box = (min(xs), min(ys), max(xs), max(ys))
    for t in shape_items:
        st = t.GetEffectiveShape(layer)
        for o in tracks:
            if o in shape_items or o.GetNetCode() == net or not o.IsOnLayer(layer) or not bb_near(o, box):
                continue
            if st.Collide(o.GetEffectiveShape(layer), CLR - 1):
                return 'copper %s' % o.GetNetname()
        for p in pads:
            if p.GetNetCode() == net or not p.IsOnLayer(layer) or not bb_near(p, box):
                continue
            if st.Collide(p.GetEffectiveShape(layer), CLR - 1):
                return 'pad %s-%s' % (p.GetParentFootprint().GetReference(), p.GetNumber())
        for c, r, n in holes:
            if n == net or r <= 0 or c.x < box[0] - 2 * MM or c.x > box[2] + 2 * MM or c.y < box[1] - 2 * MM or c.y > box[3] + 2 * MM:
                continue
            if st.Collide(pcbnew.SHAPE_SEGMENT(c, c, 2 * r), HCLR - 1):
                return 'hole of %s' % (B.FindNet(n).GetNetname() if B.FindNet(n) else '?')
    return None


def cp(p):
    return pcbnew.VECTOR2I(p.x, p.y)


def at(p, q):
    return p.x == q.x and p.y == q.y


def others_at(pt, seg):
    return [t for t in segs if t is not seg and t.GetNetCode() == seg.GetNetCode() and t.GetLayer() == seg.GetLayer()
            and (at(t.GetStart(), pt) or at(t.GetEnd(), pt))]


def blocked_at(pt, net, layer):
    if any(v.GetNetCode() == net and at(v.GetPosition(), pt) for v in vias):
        return 'via'
    for p in pads:
        if p.GetNetCode() == net and p.IsOnLayer(layer) and p.HitTest(pt):
            return 'pad %s-%s' % (p.GetParentFootprint().GetReference(), p.GetNumber())
    return None


def intersect(p, d, q, e):
    # line p + s*d  with  line q + t*e ; returns point or None when parallel
    den = d[0] * e[1] - d[1] * e[0]
    if abs(den) < 1e-12:
        return None
    s = ((q[0] - p[0]) * e[1] - (q[1] - p[1]) * e[0]) / den
    return (p[0] + s * d[0], p[1] + s * d[1])


todo = []
for f in audit['findings']:
    if f['level'] != 'FAIL' or not (f['check'] == 'between-pads' or (f['check'] == 'pin-array' and ' off-centre: ' in f['msg'])):
        continue                                   # 1.24.0: pin-array channel centreline findings have the same form
    m = RX.match(f['msg'])
    if not m:
        print('  ?? unparsed: %s' % f['msg'][:120]); continue
    fl = re.match(r'^.* runs (?:between pads (.+?)|under two-pad part (\S+)) off-centre', f['msg'])
    todo.append((m.group(1), float(m.group(2)), float(m.group(3)), float(m.group(4)), float(m.group(5)), m.group(6),
                 (fl.group(1) or fl.group(2)) if fl else None))


def flank_items(spec):
    """Positions and reach of the two flanks named in an audit message: 'REF-NUM / REF-NUM', 'via@x,y-V',
    or a two-pad part reference (both of its pads)."""
    out = []
    if spec is None:
        return out
    if ' / ' not in spec:
        fp = B.FindFootprintByReference(spec)
        return [('pad', p) for p in fp.Pads()] if fp else []
    for k in spec.split(' / '):
        k = k.strip()
        if k.startswith('via@'):
            xy = k[4:].rsplit('-', 1)[0].split(',')
            q = (float(xy[0]) * MM, float(xy[1]) * MM)
            v = min(vias, key=lambda o: math.hypot(o.GetPosition().x - q[0], o.GetPosition().y - q[1]))
            out.append(('via', v))
        else:
            ref, num = k.split('-', 1)
            fp = B.FindFootprintByReference(ref)
            ps = [p for p in fp.Pads() if p.GetNumber() == num] if fp else []
            if ps:
                out.append(('pad', ps[0]))
    return out


def detour(s, a, b, u, n, delta, flanks, code, L):
    """Local detour (2026-09-29): leave the segment on its line except across the window where its two flanks
    face it; there, 45-degree jogs take it to the centred line. Returns the new tracks or a reason string."""
    Ls = math.hypot(b.x - a.x, b.y - a.y); ad = abs(delta)
    ts = []
    for kind, o in flanks:
        c = o.GetPosition(); t = (c.x - a.x) * u[0] + (c.y - a.y) * u[1]
        if kind == 'via':
            r = o.GetWidth(pcbnew.F_Cu) / 2
        else:
            bb = o.GetBoundingBox(); r = abs(u[0]) * bb.GetWidth() / 2 + abs(u[1]) * bb.GetHeight() / 2
        ts += [t - r, t + r]
    if len(ts) < 4:
        return 'flanks not found'
    m = CLR + s.GetWidth() / 2 + ad            # the jogs start clear of the facing window
    t_lo, t_hi = min(ts) - m, max(ts) + m
    if t_lo < ad + 0.05 * MM or t_hi > Ls - ad - 0.05 * MM:
        return 'facing window reaches the segment ends'
    P = lambda t, off: pcbnew.VECTOR2I(int(round(a.x + u[0] * t + n[0] * off)), int(round(a.y + u[1] * t + n[1] * off)))
    pts = [P(t_lo - ad, 0), P(t_lo, delta), P(t_hi, delta), P(t_hi + ad, 0), cp(b)]
    s.SetEnd(pts[0]); new = []
    for p0, p1 in zip(pts, pts[1:]):
        j = pcbnew.PCB_TRACK(B); j.SetStart(p0); j.SetEnd(p1); j.SetWidth(s.GetWidth()); j.SetLayer(L)
        j.SetNet(s.GetNet()); j.SetLocked(s.IsLocked()); B.Add(j); new.append(j)
    bad = clear([s] + new, code, L)
    if bad:
        s.SetEnd(cp(b))
        for j in new:
            B.Remove(j)
        return 'detour would violate: %s' % bad
    return new

ONLY = int(args[args.index('--index') + 1]) if '--index' in args else None   # apply exactly one entry
ONLYSET = set(int(v) for v in args[args.index('--indices') + 1].split(',')) if '--indices' in args else None  # batch (bisection driver)
# --allow-locked-nets A,B: locked copper of THESE nets may move (hand-laid copper being corrected on purpose;
# re-lock and re-fingerprint afterwards). Locked copper of every other net is still never touched.
ALLOW = set(args[args.index('--allow-locked-nets') + 1].split(',')) if '--allow-locked-nets' in args else set()
moved, report = 0, []
for idx, (net, c1, c2, x, y, layer_name, flank_spec) in enumerate(todo):
    if ONLY is not None and idx != ONLY:
        continue
    if ONLYSET is not None and idx not in ONLYSET:
        continue
    L = B.GetLayerID(layer_name); P0 = pcbnew.VECTOR2I(int(round(x * MM)), int(round(y * MM)))
    cand = [t for t in segs if t.GetNetname() == net and t.GetLayer() == L and at(t.GetStart(), P0)]
    tag = '%-22s @%.4f,%.4f' % (net[:22], x, y)
    if len(cand) != 1:
        report.append(tag + '  segment not found uniquely (%d)' % len(cand)); continue
    s = cand[0]
    if s.IsLocked() and net not in ALLOW:
        report.append(tag + '  locked - left'); continue
    a, b = cp(s.GetStart()), cp(s.GetEnd()); code = s.GetNetCode()    # copies: GetStart/GetEnd are live references
    Ls = math.hypot(b.x - a.x, b.y - a.y); u = ((b.x - a.x) / Ls, (b.y - a.y) / Ls); n = (-u[1], u[0])
    delta = (c1 - c2) / 2.0 * MM                      # + moves toward the side of bestPos (c1)
    ends, why = [], None
    for k_end, pt in enumerate((a, b)):
        blk = blocked_at(pt, code, L)
        nb = others_at(pt, s)
        if blk:
            # fixed end (pad or via): keep it, and reach the shifted line with a 45-degree jog of |delta|*sqrt(2)
            # (2026-09-29). The jog direction is n*delta + inward*|delta|, which stays on the lattice.
            inward = u if k_end == 0 else (-u[0], -u[1])
            J = (pt.x + n[0] * delta + inward[0] * abs(delta), pt.y + n[1] * delta + inward[1] * abs(delta))
            ends.append((pt, None, None, J)); continue
        if len(nb) != 1:
            why = 'end joins %d segments' % len(nb); break
        t = nb[0]
        if t.IsLocked() and t.GetNetname() not in ALLOW:
            why = 'neighbour locked'; break
        far = t.GetEnd() if at(t.GetStart(), pt) else t.GetStart()
        e = (far.x - pt.x, far.y - pt.y); le = math.hypot(*e)
        if le == 0:
            why = 'zero-length neighbour'; break
        e = (e[0] / le, e[1] / le)
        if abs(e[0] * u[1] - e[1] * u[0]) < 1e-9:
            why = 'neighbour collinear'; break
        newpt = intersect((a.x + n[0] * delta, a.y + n[1] * delta), u, (far.x, far.y), e)
        if newpt is None or math.hypot(newpt[0] - far.x, newpt[1] - far.y) < 0.1 * MM:
            why = 'neighbour would vanish'; break
        # the neighbour must keep its direction (slide along its own line, same side of its far end)
        if (newpt[0] - far.x) * e[0] + (newpt[1] - far.y) * e[1] >= 0:
            why = 'neighbour would reverse'; break
        ends.append((pt, t, far, newpt))
    if why:
        r_ = detour(s, a, b, u, n, delta, flank_items(flank_spec), code, L) if abs(delta) > 0.002 * MM else 'shift below 2 um'
        if isinstance(r_, str):
            report.append(tag + '  left (%s; %s)' % (why, r_)); continue
        moved += 1; print('  centred [%d] %s by %+.4f mm (local detour)' % (idx, tag, delta / MM)); continue
    # apply tentatively
    (pa, ta, fa, na), (pb, tb, fb, nb_) = ends
    NA = pcbnew.VECTOR2I(int(round(na[0])), int(round(na[1]))); NB = pcbnew.VECTOR2I(int(round(nb_[0])), int(round(nb_[1])))
    if (ta is None or tb is None) and math.hypot(NB.x - NA.x, NB.y - NA.y) < 0.05 * MM or \
            ((NB.x - NA.x) * u[0] + (NB.y - NA.y) * u[1]) <= 0:
        r_ = detour(s, a, b, u, n, delta, flank_items(flank_spec), code, L)
        if isinstance(r_, str):
            report.append(tag + '  left (segment too short for the jog; %s)' % r_); continue
        moved += 1; print('  centred [%d] %s by %+.4f mm (local detour)' % (idx, tag, delta / MM)); continue
    nbrs = [t for t in (ta, tb) if t is not None]
    saved = [(t, cp(t.GetStart()), cp(t.GetEnd())) for t in nbrs + [s]]
    for t, pt, newp in ((ta, pa, NA), (tb, pb, NB)):
        if t is not None:
            (t.SetStart if at(t.GetStart(), pt) else t.SetEnd)(newp)
    s.SetStart(NA); s.SetEnd(NB)
    jogs = []
    for t, pt, newp in ((ta, pa, NA), (tb, pb, NB)):
        if t is None:
            j = pcbnew.PCB_TRACK(B); j.SetStart(pt); j.SetEnd(newp); j.SetWidth(s.GetWidth()); j.SetLayer(L)
            j.SetNet(s.GetNet()); j.SetLocked(s.IsLocked()); B.Add(j); jogs.append(j)
    bad = clear([s] + nbrs + jogs, code, L)
    if bad:
        for t, st_, en_ in saved:
            t.SetStart(st_); t.SetEnd(en_)
        for j in jogs:
            B.Remove(j)
        r_ = detour(s, a, b, u, n, delta, flank_items(flank_spec), code, L)
        if isinstance(r_, str):
            report.append(tag + '  left (would violate: %s; %s)' % (bad, r_)); continue
        moved += 1; print('  centred [%d] %s by %+.4f mm (local detour)' % (idx, tag, delta / MM)); continue
    moved += 1
    print('  centred [%d] %s by %+.4f mm' % (idx, tag, delta / MM))
for r in report:
    print('  ' + r)
print('re-centred %d of %d; left %d' % (moved, len(todo), len(report)))
if APPLY and moved:
    print('fill:', zone_fill_check.refill(B)); B.Save(args[0]); print('saved')
elif not APPLY:
    print('dry run - not saved')


