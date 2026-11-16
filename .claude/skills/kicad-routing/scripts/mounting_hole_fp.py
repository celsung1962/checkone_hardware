#!/usr/bin/env python
"""mounting_hole_fp.py - mounting-hole footprints that carry their own mechanical keep-out (lesson L24, ServiceOne
review issue 17, D116 / D124). MUST be run with KiCad's own Python (it imports pcbnew).

Every mounting hole and pillar contact gets a copper keep-out of radius = the largest contact diameter / 2 + 0.5 mm:
the pillar or standoff under the board, the screw head, nut or washer on top. On ServiceOne that radius was added
afterwards as board-level rule areas (add_spacer_keepouts.py); a footprint that carries it from the start puts the
rule in front of the placer, the router (KiCad's Specctra export writes footprint keep-outs), DRC and the audit,
and no later reroute is needed.

  mounting_hole_fp.py --lib DIR.pretty --hole 2.3 --contact-top 4.2 --contact-bottom 5.0
                      [--name NAME] [--margin 0.5] [--plated RING_MM] [--layers F.Cu,B.Cu | all]
                      [--pour-allowed] [--note "AK-H-79 post d 5.00, M2 screw head d 4.2"]

  --hole            drill diameter (mm). NPTH unless --plated RING_MM (PTH pad, copper ring width RING_MM, net-less;
                    give it a net on the schematic if the chassis is to be grounded)
  --contact-top / --contact-bottom   largest contact diameter on each side (screw head, washer, nut, standoff hex
                    across corners, enclosure post); the keep-out radius is max(top, bottom) / 2 + --margin
  --layers          keep-out layers (default F.Cu,B.Cu: where the parts touch; "all" adds the inner layers)
  --pour-allowed    let zone fills enter the keep-out (default: tracks, vias and pours are all forbidden)

Writes DIR.pretty/NAME.kicad_mod (default name MountingHole_<hole>mm_KO<radius>): the hole, a "no tracks / vias / pours"
rule area named KO_MECH on the chosen layers, the courtyard (the keep-out circle), the contact circles on F.Fab /
B.Fab and Cmts.User, and a description with the diameters. Excluded from BOM and position files. kicad_audit.js
section 27 counts a footprint with a KO_MECH rule area as covered, so it needs no mechanical_keepouts entry.
"""
import math
import os
import sys

import pcbnew

a = sys.argv[1:]


def opt(n, d=None):
    return a[a.index(n) + 1] if n in a else d


if '--lib' not in a or '--hole' not in a or not ({'--contact-top', '--contact-bottom'} & set(a)):
    print(__doc__)
    sys.exit(2)
LIB = opt('--lib')
HOLE = float(opt('--hole'))
CT = float(opt('--contact-top', '0'))
CB = float(opt('--contact-bottom', '0'))
MARGIN = float(opt('--margin', '0.5'))
RING = float(opt('--plated')) if opt('--plated') else None
R = max(CT, CB) / 2 + MARGIN
if R <= HOLE / 2 + (RING or 0):
    sys.exit('keep-out radius %.2f mm is not larger than the hole / ring - check the contact diameters' % R)
NAME = opt('--name') or 'MountingHole_%gmm_KO%.1f' % (HOLE, R)
mm = pcbnew.FromMM
V = lambda x, y: pcbnew.VECTOR2I(mm(x), mm(y))

fp = pcbnew.FOOTPRINT(None)
fp.SetFPID(pcbnew.LIB_ID('', NAME))
fp.SetReference('H**')
fp.SetValue(NAME)
fp.Reference().SetPosition(V(0, -R - 1.0))
fp.Value().SetPosition(V(0, R + 1.0))
fp.Value().SetLayer(pcbnew.F_Fab)
note = opt('--note', '')
fp.SetLibDescription('Mounting hole d %g mm with its mechanical keep-out r %g mm (largest contact d %g mm + %g mm): '
                     'contact top d %g, bottom d %g mm.%s (kicad-routing mounting_hole_fp.py, lesson L24)'
                     % (HOLE, R, max(CT, CB), MARGIN, CT, CB, (' ' + note) if note else ''))
fp.SetKeywords('mounting hole keep-out')
fp.SetAttributes(pcbnew.FP_EXCLUDE_FROM_BOM | pcbnew.FP_EXCLUDE_FROM_POS_FILES)

p = pcbnew.PAD(fp)
if RING:
    p.SetNumber('1')
    p.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    p.SetLayerSet(p.PTHMask())
    p.SetSize(V(HOLE + 2 * RING, HOLE + 2 * RING))
else:
    p.SetNumber('')
    p.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
    p.SetLayerSet(p.UnplatedHoleMask())
    p.SetSize(V(HOLE, HOLE))
p.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
p.SetDrillSize(V(HOLE, HOLE))
p.SetFPRelativePosition(V(0, 0))
fp.Add(p)


def circle(layer, r, width):
    c = pcbnew.PCB_SHAPE(fp)
    c.SetShape(pcbnew.SHAPE_T_CIRCLE)
    c.SetCenter(V(0, 0))
    c.SetEnd(V(r, 0))
    c.SetLayer(layer)
    c.SetWidth(mm(width))
    fp.Add(c)


circle(pcbnew.F_CrtYd, R, 0.05)
circle(pcbnew.B_CrtYd, R, 0.05)
if CT:
    circle(pcbnew.F_Fab, CT / 2, 0.1)
if CB:
    circle(pcbnew.B_Fab, CB / 2, 0.1)
circle(pcbnew.Cmts_User, R, 0.05)

z = pcbnew.ZONE(fp)
z.SetIsRuleArea(True)
z.SetZoneName('KO_MECH')
z.SetDoNotAllowTracks(True)
z.SetDoNotAllowVias(True)
z.SetDoNotAllowPads(False)
z.SetDoNotAllowFootprints(False)
z.SetDoNotAllowZoneFills('--pour-allowed' not in a)
ls = pcbnew.LSET()
if opt('--layers', 'F.Cu,B.Cu') == 'all':
    ls = pcbnew.LSET.AllCuMask()
else:
    for n in opt('--layers', 'F.Cu,B.Cu').split(','):
        ls.AddLayer({'F.Cu': pcbnew.F_Cu, 'B.Cu': pcbnew.B_Cu}.get(n) or getattr(pcbnew, n.replace('.', '_')))
z.SetLayerSet(ls)
o = z.Outline()
o.NewOutline()
for k in range(36):
    t = 2 * math.pi * k / 36
    rr = R / math.cos(math.pi / 36)         # the polygon circumscribes the circle: the keep-out is never smaller
    o.Append(mm(rr * math.cos(t)), mm(rr * math.sin(t)))
fp.Add(z)

os.makedirs(LIB, exist_ok=True)
pcbnew.PCB_IO_MGR.FindPlugin(pcbnew.PCB_IO_MGR.KICAD_SEXP).FootprintSave(LIB, fp)   # FootprintSave() guesses no plugin here
print('written %s/%s.kicad_mod: hole d %g mm %s, keep-out r %g mm on %s (tracks, vias%s not allowed)' % (
    LIB, NAME, HOLE, 'PTH ring %g mm' % RING if RING else 'NPTH', R, opt('--layers', 'F.Cu,B.Cu'),
    '' if '--pour-allowed' in a else ', pours'))
