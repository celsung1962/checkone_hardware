#!/usr/bin/env python
"""pad_row_keepouts.py - "no vias" rule areas over every IC pad-row band (lesson L16, ServiceOne review issue 16).

Vladimir's rule: no via inside an IC pad-row band - from the inner pad ends to 0.5 mm beyond the outer pad ends,
between the first and the last pin of the row. Vias go beyond the row, or under the body between the rows. The audit
checks it after routing (kicad_audit.js section 26); this script puts the rule into the board BEFORE routing, so
Freerouting (DSN via_keepout), the interactive router and KiCad's DRC all keep vias out of the bands.

The band geometry is the audit's: footprints whose reference matches --ref-pattern (default ^(U|IC)[0-9]) with
>= --min-pads copper pads; a row is >= 3 pads of equal size on one footprint-frame line at a uniform pitch
(0.1-2.6 mm), not through the footprint origin and not all with one pad number (an exposed pad split into a
grid). One rule area per row, on all copper layers, vias not allowed
(tracks, pads, pours and footprints allowed).

  pad_row_keepouts.py <board> --list [--json F]                read-only: rows, bands, vias already inside
  pad_row_keepouts.py <export-copy> --export-copy              KO_EXPORT_ROW_<ref>_<n> on a DSN export copy
  pad_row_keepouts.py <board> --write                          KO_ROW_<ref>_<n> on the real board (board_guard)
  options: --refs U1,U2 | --exclude U9 | --ref-pattern RE | --min-pads 6 | --margin 0.5 | --allow-no-pro
           --force-write

--write is idempotent: rule areas named KO_ROW_* are edited in place, stale ones removed; item nets are compared
from the saved file and the board is restored if one changed (see plane_plan.py). Vias already inside a band are
listed - KiCad's DRC reports them as rule-area violations from then on, as the audit does.
export_keepouts.py --pad-row-bands calls the same code for a Freerouting export copy.
"""
import json
import math
import os
import re
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

M = pcbnew.ToMM


def _size(p):
    try:
        s = p.GetSize(pcbnew.F_Cu)
    except TypeError:
        s = p.GetSize()
    return M(s.x), M(s.y)


def _frame(fp):
    """Footprint frame: (to_board(lx, ly) -> (x, y) mm, to_local(x, y) -> (lx, ly)), fitted on the pads so that
    rotation sense and the bottom-side mirror come out right whatever the API convention."""
    ox, oy = M(fp.GetPosition().x), M(fp.GetPosition().y)
    th = math.radians(fp.GetOrientationDegrees())
    pads = [(M(p.GetFPRelativePosition().x), M(p.GetFPRelativePosition().y), M(p.GetPosition().x),
             M(p.GetPosition().y)) for p in fp.Pads()]
    best = None
    for sgn in (1, -1):
        c, s = math.cos(sgn * th), math.sin(sgn * th)
        for mx in (1, -1):
            def tb(lx, ly, c=c, s=s, mx=mx):
                lx *= mx
                return ox + c * lx + s * ly, oy - s * lx + c * ly
            err = sum(math.hypot(tb(a, b_)[0] - x, tb(a, b_)[1] - y) for a, b_, x, y in pads)
            if best is None or err < best[0]:
                best = (err, tb, c, s, mx)
    _, tb, c, s, mx = best

    def tl(x, y):
        dx, dy = x - ox, y - oy
        return mx * (c * dx - s * dy), s * dx + c * dy
    return tb, tl


def _local_rot(fp, p):
    try:
        return p.GetFPRelativeOrientation().AsDegrees()
    except AttributeError:
        return p.GetOrientationDegrees() - fp.GetOrientationDegrees()


def bands(b, ref_pattern=r'^(U|IC)\d', min_pads=6, margin=0.5, refs=None, exclude=()):
    """[{ref, n, pins: [..], poly: [(x, y) x4] mm, axis, pitch}] - one band per pad row, as kicad_audit.js §26."""
    out = []
    for fp in sorted(b.GetFootprints(), key=lambda f: f.GetReference()):
        ref = fp.GetReference()
        if refs is not None and ref not in refs or ref in exclude:
            continue
        if refs is None and not re.search(ref_pattern, ref):
            continue
        cu = [p for p in fp.Pads() if p.IsOnCopperLayer() and p.GetAttribute() != pcbnew.PAD_ATTRIB_NPTH]
        if len(cu) < min_pads:
            continue
        tb, _ = _frame(fp)
        rows_pads = []
        for p in cu:
            w, h = _size(p)
            if round(_local_rot(fp, p)) % 180 == 90:
                w, h = h, w
            q = p.GetFPRelativePosition()
            rows_pads.append(dict(num=p.GetNumber(), lx=M(q.x), ly=M(q.y), ex=w, ey=h))
        n = 0
        for axis in ('x', 'y'):
            groups = {}
            for d in rows_pads:
                c = d['lx'] if axis == 'x' else d['ly']
                groups.setdefault((round(c * 100), round(d['ex'] * 1000), round(d['ey'] * 1000)), []).append(d)
            for g in groups.values():
                if len(g) < 3 or len({d['num'] for d in g}) == 1:     # one number = exposed-pad grid
                    continue
                al = (lambda d: d['ly']) if axis == 'x' else (lambda d: d['lx'])
                g.sort(key=al)
                gaps = [al(g[i + 1]) - al(g[i]) for i in range(len(g) - 1)]
                if any(abs(x - gaps[0]) > 0.02 for x in gaps) or not 0.1 <= gaps[0] <= 2.6:
                    continue
                c = g[0]['lx'] if axis == 'x' else g[0]['ly']
                half = (g[0]['ex'] if axis == 'x' else g[0]['ey']) / 2
                if abs(c) <= half + 1e-6:
                    continue
                sg = 1 if c > 0 else -1
                a0, a1 = sg * (abs(c) - half), sg * (abs(c) + half + margin)
                s0, s1 = al(g[0]), al(g[-1])
                corners = [(a0, s0), (a1, s0), (a1, s1), (a0, s1)]
                pts = [tb(a, s) if axis == 'x' else tb(s, a) for a, s in corners]
                n += 1
                out.append(dict(ref=ref, n=n, pins=[d['num'] for d in g], axis=axis, pitch=round(gaps[0], 3),
                                poly=[(round(x, 4), round(y, 4)) for x, y in pts]))
    return out


def _inside(poly, x, y):
    ins = False
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i], poly[i - 1]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            ins = not ins
    return ins


def _dist_edges(poly, x, y):
    d = None
    for i in range(len(poly)):
        (x1, y1), (x2, y2) = poly[i - 1], poly[i]
        L2 = (x2 - x1) ** 2 + (y2 - y1) ** 2
        t = 0 if L2 == 0 else max(0, min(1, ((x - x1) * (x2 - x1) + (y - y1) * (y2 - y1)) / L2))
        e = math.hypot(x - x1 - t * (x2 - x1), y - y1 - t * (y2 - y1))
        d = e if d is None else min(d, e)
    return d


def vias_inside(b, bd):
    """Vias whose copper reaches the band (as KiCad's DRC and the router's via keep-out see it), except vias with the
    centre inside a pad of the band's footprint (via-in-pad is the audit's section 6)."""
    fp = b.FindFootprintByReference(bd['ref'])
    hits = []
    for t in b.GetTracks():
        if t.Type() != pcbnew.PCB_VIA_T:
            continue
        q = t.GetPosition()
        x, y = M(q.x), M(q.y)
        r = M(t.GetWidth(pcbnew.F_Cu)) / 2
        reach = _inside(bd['poly'], x, y) or _dist_edges(bd['poly'], x, y) < r - 0.0005
        if reach and not any(p.HitTest(q) for p in fp.Pads()):
            hits.append((t.GetNetname(), round(x, 3), round(y, 3)))
    return hits


def add_rule_area(b, poly, name):
    z = pcbnew.ZONE(b)
    b.Add(z)
    set_rule_area(z, poly, name)
    return z


def set_rule_area(z, poly, name):
    z.SetIsRuleArea(True)
    z.SetDoNotAllowVias(True)
    z.SetDoNotAllowTracks(False)
    z.SetDoNotAllowPads(False)
    z.SetDoNotAllowFootprints(False)
    if hasattr(z, 'SetDoNotAllowZoneFills'):
        z.SetDoNotAllowZoneFills(False)
    z.SetLayerSet(pcbnew.LSET.AllCuMask())
    z.SetZoneName(name)
    o = z.Outline()
    o.RemoveAllContours()
    o.NewOutline()
    for x, y in poly:
        o.Append(pcbnew.FromMM(x), pcbnew.FromMM(y))


def main():
    a = sys.argv[1:]
    if not a or a[0].startswith('-'):
        print(__doc__)
        return 2

    def opt(n, d=None):
        return a[a.index(n) + 1] if n in a else d
    path = a[0]
    modes = [m for m in ('--list', '--export-copy', '--write') if m in a]
    if len(modes) != 1:
        sys.exit('pass exactly one of --list, --export-copy, --write')
    mode = modes[0]
    if mode != '--list':
        import board_guard
        board_guard.check_board_writable(path, argv=a[1:], script='pad_row_keepouts.py')
    b = pcbnew.LoadBoard(path)
    refs = set(opt('--refs').split(',')) if opt('--refs') else None
    bl = bands(b, opt('--ref-pattern', r'^(U|IC)\d'), int(opt('--min-pads', '6')), float(opt('--margin', '0.5')),
               refs, set((opt('--exclude') or '').split(',')) - {''})
    report = []
    for bd in bl:
        hits = vias_inside(b, bd)
        report.append(dict(bd, vias_inside=hits))
        print('  %-6s row %d: pins %s..%s (%d, pitch %.2f mm)%s' % (
            bd['ref'], bd['n'], bd['pins'][0], bd['pins'][-1], len(bd['pins']), bd['pitch'],
            ('  - %d via(s) already inside: %s' % (len(hits), ', '.join('%s@%s,%s' % h for h in hits[:4]))
             if hits else '')))
    nv = sum(len(r['vias_inside']) for r in report)
    print('%d pad-row band(s) on %d footprint(s); %d via(s) already inside a band'
          % (len(bl), len({x['ref'] for x in bl}), nv))
    if opt('--json'):
        json.dump(report, open(opt('--json'), 'w', encoding='utf-8'), indent=1)
    if mode == '--list':
        return 0
    if mode == '--export-copy':
        for bd in bl:
            add_rule_area(b, bd['poly'], 'KO_EXPORT_ROW_%s_%d' % (bd['ref'], bd['n']))
        b.Save(path)
        print('added %d export-only "no vias" rule areas; saved %s' % (len(bl), path))
        return 0
    # --write: real board, idempotent, nets verified from the saved file
    import zone_fill_check
    nets_before = {t.m_Uuid.AsString(): t.GetNetname() for t in b.GetTracks()}
    have = {z.GetZoneName(): z for z in b.Zones() if z.GetIsRuleArea() and z.GetZoneName().startswith('KO_ROW_')}
    want = {'KO_ROW_%s_%d' % (bd['ref'], bd['n']): bd for bd in bl}
    edited = 0
    for name, bd in want.items():
        if name in have:
            set_rule_area(have[name], bd['poly'], name)
            edited += 1
        else:
            add_rule_area(b, bd['poly'], name)
    stale = [z for n, z in have.items() if n not in want]
    for z in stale:
        b.Remove(z)
    backup = open(path, 'rb').read()
    zone_fill_check.refill(b)
    b.Save(path)
    b2 = pcbnew.LoadBoard(path)
    changed = [t for t in b2.GetTracks() if nets_before.get(t.m_Uuid.AsString(), t.GetNetname()) != t.GetNetname()]
    if changed:
        open(path, 'wb').write(backup)
        sys.exit('pad_row_keepouts.py: %d item net(s) changed on save - board restored, nothing written' % len(changed))
    print('KO_ROW_* rule areas: %d edited, %d new, %d stale removed; zones refilled and saved; item nets unchanged'
          % (edited, len(want) - edited, len(stale)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
