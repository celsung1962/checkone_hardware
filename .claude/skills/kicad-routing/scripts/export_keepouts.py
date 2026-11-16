#!/usr/bin/env python
"""export_keepouts.py - export-time rule areas for a Freerouting run. EXPORT COPY ONLY, never the real board.

Freerouting sees only what the Specctra DSN carries. Three things the board relies on are not in it:

  --corridors REF,REF | auto
        Crystal / inductor courtyards (audit check "crystal-inductor": no other net's track under them on their
        mounted layer). A rule area over the whole courtyard also blocks the part's OWN nets, which only works
        when those are hand-routed and locked first (playbook D2). This variant subtracts one entry corridor per
        pad - the pad box widened by --corridor-margin, extended to the courtyard edge nearest the pad, or to the
        side given as REF:left|right|top|bottom - so a single routing pass can reach the pads while other nets
        stay off the body. "auto" = every footprint whose reference matches ^[YXL][0-9]+$ (as the audit).
  --edge-band MM
        Freerouting keeps only its own clearance to the board boundary, not the board's copper-to-edge rule
        (ServiceOne, 2026-10-04: 22 copper_edge_clearance errors after the first import). Adds a band of MM
        (use the rule + 0.05) along the outline and around every cut-out, on F.Cu and B.Cu, ONE ZONE PER RING:
        pcbnew saves only the first outline of a zone (KiCad 10.0.6), so a multi-ring zone loses its rings.
  --fiducials
        Pad-local clearance is not in the DSN either: a keepout of pad radius + local clearance + 0.05 mm over
        every FID* pad.
  --pad-row-bands
        "No vias" rule areas over every IC pad-row band (lesson L16, audit section 26), as pad_row_keepouts.py: the
        DSN carries them as via keep-outs, so the router places no via between the pins of a row.

Usage (KiCad's Python):
    export_keepouts.py <export-copy.kicad_pcb> --export-copy [--corridors auto] [--edge-band 0.55] [--fiducials]
                       [--pad-row-bands]
                       [--corridor-margin 0.15] [--allow-no-pro] [--force-write]
The copy needs its .kicad_pro beside it (board_guard; --allow-no-pro skips only that check) and no KiCad lock.
"""
import math
import os
import re
import sys

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board_guard  # noqa: E402

a = sys.argv[1:]
if not a or a[0].startswith('--'):
    sys.stderr.write(__doc__)
    sys.exit(2)
if '--export-copy' not in a:
    sys.stderr.write('refusing: pass --export-copy to confirm %s is a COPY made for the DSN export\n' % a[0])
    sys.exit(2)


def opt(name, default=None):
    return a[a.index(name) + 1] if name in a else default


MM = pcbnew.ToMM
FM = lambda v: pcbnew.FromMM(float(v))     # numpy / int safe
# The export copy is a copy by design, but pcbnew still rewrites the .kicad_pro beside it on save: copy the
# project next to it (the DSN export reads its netclasses), or pass --allow-no-pro to skip only that check.
board_guard.check_board_writable(a[0], argv=a[1:], script='export_keepouts.py')
b = pcbnew.LoadBoard(a[0])
MARGIN = FM(opt('--corridor-margin', '0.15'))
added = []


def rect(x0, y0, x1, y1):
    s = pcbnew.SHAPE_POLY_SET(); s.NewOutline()
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        s.Append(int(x), int(y))
    return s


def rule(poly, name, layers):
    z = pcbnew.ZONE(b); z.SetIsRuleArea(True)
    z.SetDoNotAllowTracks(True); z.SetDoNotAllowVias(True); z.SetDoNotAllowPads(False)
    z.SetDoNotAllowFootprints(False)
    if hasattr(z, 'SetDoNotAllowZoneFills'):
        z.SetDoNotAllowZoneFills(False)
    ls = pcbnew.LSET()
    for l in layers:
        ls.AddLayer(l)
    z.SetLayerSet(ls); z.SetZoneName(name); z.Outline().Append(poly); b.Add(z)
    added.append(name)


# ---------------------------------------------------------------- crystal / inductor corridors
spec = opt('--corridors')
if spec:
    if spec == 'auto':
        items = [(f.GetReference(), None) for f in b.GetFootprints() if re.match(r'^[YXL]\d+$', f.GetReference())]
    else:
        items = [(t.split(':')[0], t.split(':')[1] if ':' in t else None) for t in spec.split(',') if t]
    for ref, forced in items:
        fp = b.FindFootprintByReference(ref)
        if fp is None:
            print('  %s: not on the board - skipped' % ref); continue
        side = pcbnew.F_CrtYd if fp.GetLayer() == pcbnew.F_Cu else pcbnew.B_CrtYd
        cy = fp.GetCourtyard(side)
        if not cy.OutlineCount():
            print('  %s: no courtyard - skipped' % ref); continue
        bb = cy.BBox(); X0, Y0, X1, Y1 = bb.GetLeft(), bb.GetTop(), bb.GetRight(), bb.GetBottom()
        ko = rect(X0, Y0, X1, Y1)
        for p in fp.Pads():
            q = p.GetBoundingBox(); l, t, r, d = q.GetLeft(), q.GetTop(), q.GetRight(), q.GetBottom()
            gaps = {'left': l - X0, 'right': X1 - r, 'top': t - Y0, 'bottom': Y1 - d}
            s = forced or min(gaps, key=gaps.get)
            c = {'left': (X0 - MARGIN, t - MARGIN, r + MARGIN, d + MARGIN), 'right': (l - MARGIN, t - MARGIN, X1 + MARGIN, d + MARGIN),
                 'top': (l - MARGIN, Y0 - MARGIN, r + MARGIN, d + MARGIN), 'bottom': (l - MARGIN, t - MARGIN, r + MARGIN, Y1 + MARGIN)}[s]
            ko.BooleanSubtract(rect(*c))
        if ko.OutlineCount() > 1:
            for i in range(ko.OutlineCount()):
                one = pcbnew.SHAPE_POLY_SET(); one.AddOutline(ko.Outline(i))
                rule(one, 'KO_EXPORT_%s_%d' % (ref, i), [fp.GetLayer()])
        elif ko.OutlineCount():
            rule(ko, 'KO_EXPORT_%s' % ref, [fp.GetLayer()])
        print('  %s: courtyard %.2f x %.2f mm, %d corridor(s)%s, keepout %.2f mm2'
              % (ref, MM(X1 - X0), MM(Y1 - Y0), len(list(fp.Pads())), ' toward %s' % forced if forced else '', ko.Area() / 1e12))

# ---------------------------------------------------------------- edge band
band_mm = opt('--edge-band')
if band_mm:
    outline = pcbnew.SHAPE_POLY_SET(); b.GetBoardPolygonOutlines(outline, False)
    inner = pcbnew.SHAPE_POLY_SET(outline)
    inner.Inflate(-FM(band_mm), pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, FM(0.01))
    band = pcbnew.SHAPE_POLY_SET(outline); band.BooleanSubtract(inner)
    for i in range(band.OutlineCount()):
        one = pcbnew.SHAPE_POLY_SET(); one.AddOutline(band.Outline(i))
        for h in range(band.HoleCount(i)):
            one.AddHole(band.CHole(i, h))
        rule(one, 'KO_EXPORT_EDGE_%d' % i, [pcbnew.F_Cu, pcbnew.B_Cu])
    hit = []
    for f in b.GetFootprints():
        for p in f.Pads():
            n = p.GetNetname()
            if n and not n.startswith('unconnected') and band.Collide(p.GetPosition()):
                hit.append('%s-%s' % (f.GetReference(), p.GetNumber()))
    print('  edge band %s mm: %d ring(s); routed pads with their centre in the band: %s'
          % (band_mm, band.OutlineCount(), ', '.join(hit) or 'none'))

# ---------------------------------------------------------------- fiducials
if '--fiducials' in a:
    for f in b.GetFootprints():
        if not f.GetReference().startswith('FID'):
            continue
        for p in f.Pads():
            r = max(p.GetSize(pcbnew.F_Cu).x, p.GetSize(pcbnew.F_Cu).y) / 2 + (p.GetLocalClearance() or 0) + FM(0.05)
            c = pcbnew.SHAPE_POLY_SET(); c.NewOutline()
            for k in range(32):
                c.Append(int(p.GetPosition().x + r * math.cos(2 * math.pi * k / 32)),
                         int(p.GetPosition().y + r * math.sin(2 * math.pi * k / 32)))
            rule(c, 'KO_EXPORT_%s' % f.GetReference(), [pcbnew.F_Cu, pcbnew.B_Cu])
            print('  %s: keepout radius %.3f mm' % (f.GetReference(), MM(r)))

# ---------------------------------------------------------------- pad-row bands (L16)
if '--pad-row-bands' in a:
    import pad_row_keepouts as PRK
    for bd in PRK.bands(b):
        PRK.add_rule_area(b, bd['poly'], 'KO_EXPORT_ROW_%s_%d' % (bd['ref'], bd['n']))
        added.append('KO_EXPORT_ROW_%s_%d' % (bd['ref'], bd['n']))
    print('  pad-row bands: %d "no vias" rule areas' % sum(1 for n in added if n.startswith('KO_EXPORT_ROW_')))

b.Save(a[0])
print('added %d export-only rule areas; saved %s' % (len(added), a[0]))
