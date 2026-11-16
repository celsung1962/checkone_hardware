#!/usr/bin/env python
"""fab_layer_fix.py - Fab-layer hygiene: hide Value text, centre/shrink the Fab reference, add one
where missing.

MUST be run with KiCad's own Python (it imports pcbnew). improvements #1, #2 (kicad-golden 1.16.0).

    fab_layer_fix.py <board.kicad_pcb> [--hide-values] [--center-refs] [--add-missing-refs] [--all]
                     [--min-height MM] [--dry-run]

WHAT EACH FLAG DOES
  --hide-values       Hide (never delete) the Value field, and any ${VALUE} user text, wherever it
                       sits on F.Fab/B.Fab. KiCad's BOM and "Update PCB from Schematic" both read the
                       Value field, so it must survive - only stop it being drawn.
  --center-refs        Move the Fab reference text (the Reference field if it already lives on Fab,
                       else a ${REFERENCE} user text) to the centre of the Fab outline's bounding box
                       (fallback: courtyard centre, then the footprint origin), rotated to the
                       footprint's own orientation, shrunk to fit down to --min-height (default
                       0.3 mm, width kept equal to height, thickness 15% of height). Never enlarged.
  --add-missing-refs   Add a ${REFERENCE} user text on the Fab layer to a footprint that has neither
                       a Fab-layer Reference field nor a ${REFERENCE} user text there, then centre it
                       like any other.
  --all                All three.

Only Fab-layer content is touched. Silkscreen, courtyard and copper are never modified, and the
Value field itself is never deleted - only hidden.

SCOPE NOTE: fitting uses an approximate stroke-font character width (0.8 x height) rather than
exact glyph metrics (pcbnew's own EDA_TEXT.GetTextBox() needs a live rendering-settings object this
script does not construct). It shrinks generously rather than precisely; verify visually on a
crowded board. Long-axis alignment assumes the footprint sits at a multiple of 90 degrees, which is
the overwhelming common case; an arbitrarily rotated footprint gets an axis-aligned bounding box
that is looser than its true local bbox, which only ever makes the fit check more conservative.

Exit codes: 0 ok, 2 usage.
"""
import os
import sys
import pcbnew
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board_guard  # noqa: E402

MM = 1e6


def die(m, c=2):
    sys.stderr.write(str(m) + '\n')
    sys.exit(c)


args = sys.argv[1:]
if not args or args[0].startswith('--'):
    die(__doc__)
BOARD = args[0]
ALL = '--all' in args
DO_HIDE = ALL or '--hide-values' in args
DO_CENTER = ALL or '--center-refs' in args
DO_ADD = ALL or '--add-missing-refs' in args
if not (DO_HIDE or DO_CENTER or DO_ADD):
    die('nothing to do - pass --hide-values, --center-refs, --add-missing-refs or --all')


def opt(name, default=None):
    if name in args:
        i = args.index(name)
        if i + 1 >= len(args):
            die(name + ' needs a value')
        return args[i + 1]
    return default


MIN_H = float(opt('--min-height', '0.3'))
DRY = '--dry-run' in args

if not DRY:
    board_guard.check_board_writable(BOARD, script='fab_layer_fix.py')   # KiCad lock / .kicad_pro beside it
B = pcbnew.LoadBoard(BOARD)

hidden = 0
centered = 0
added = 0
still_too_small = []


def fab_layer_of(fp):
    return pcbnew.F_Fab if fp.GetLayer() == pcbnew.F_Cu else pcbnew.B_Fab


def is_fab(layer, fab_layer):
    return layer == fab_layer


# ---------------------------------------------------------------- entry 1: hide Value + ${VALUE}
if DO_HIDE:
    for fp in B.GetFootprints():
        fab = fab_layer_of(fp)
        v = fp.Value()
        if v.GetLayer() == fab and v.IsVisible():
            v.SetVisible(False)
            hidden += 1
        for it in fp.GraphicalItems():
            if it.GetClass() != 'PCB_TEXT':
                continue
            try:
                txt = it.GetText()
            except Exception:
                continue
            if '${VALUE}' in txt and it.GetLayer() == fab and it.IsVisible():
                it.SetVisible(False)
                hidden += 1

print('Fab values hidden: %d' % hidden)

# ---------------------------------------------------------------- entries 1/2 shared: find the Fab reference text
def find_fab_ref(fp, fab):
    r = fp.Reference()
    if r.GetLayer() == fab:
        return r, 'Reference field'
    for it in fp.GraphicalItems():
        if it.GetClass() != 'PCB_TEXT' or it.GetLayer() != fab:
            continue
        try:
            txt = it.GetText()
        except Exception:
            continue
        if '${REFERENCE}' in txt:
            return it, '${REFERENCE} text'
    return None, None


def outline_bbox(fp, fab):
    box = None
    for it in fp.GraphicalItems():
        if it.GetClass() != 'PCB_SHAPE' or it.GetLayer() != fab:
            continue
        bb = it.GetBoundingBox()
        box = bb if box is None else (box.Merge(bb) or box)
    return box


def courtyard_bbox(fp):
    crt = pcbnew.F_CrtYd if fp.GetLayer() == pcbnew.F_Cu else pcbnew.B_CrtYd
    box = None
    for it in fp.GraphicalItems():
        if it.GetClass() != 'PCB_SHAPE' or it.GetLayer() != crt:
            continue
        bb = it.GetBoundingBox()
        box = bb if box is None else (box.Merge(bb) or box)
    return box


# ---------------------------------------------------------------- entry 2 (part 1): add a missing Fab reference
if DO_ADD:
    for fp in B.GetFootprints():
        fab = fab_layer_of(fp)
        existing, _ = find_fab_ref(fp, fab)
        if existing is not None:
            continue
        t = pcbnew.PCB_TEXT(fp)
        t.SetText('${REFERENCE}')
        t.SetLayer(fab)
        t.SetPosition(fp.GetPosition())
        try:
            t.SetKeepUpright(False)
        except Exception:
            pass
        fp.Add(t)
        added += 1

print('Fab reference texts added: %d' % added)

# A PCB_TEXT added via fp.Add() in this same process is not fully wired for text-variable
# resolution (GetShownText) or bounding-box maths: on a real board this produced KiCad-internal
# "Overflow converting value ... to int" asserts and, on the affected footprints, a Fab reference
# saved at a position hundreds to thousands of mm off the footprint - a real corruption, not a
# cosmetic warning. Saving and reloading before touching any newly-added text avoids it.
if DO_ADD and added and DO_CENTER:
    if DRY:
        sys.stderr.write('NOTE: --dry-run with --add-missing-refs + --center-refs together cannot '
                          'preview centring of the newly-added text (it needs a save+reload first); '
                          'run --add-missing-refs alone, then --center-refs, to preview both steps.\n')
    else:
        B.Save(BOARD)
        B = pcbnew.LoadBoard(BOARD)

# ---------------------------------------------------------------- entry 2 (part 2): centre + shrink to fit
if DO_CENTER:
    for fp in B.GetFootprints():
        fab = fab_layer_of(fp)
        ref, tag = find_fab_ref(fp, fab)
        if ref is None:
            continue  # nothing to centre (and --add-missing-refs was not requested)
        box = outline_bbox(fp, fab) or courtyard_bbox(fp)
        if box is not None:
            centre = box.GetCenter()
            w, h = box.GetWidth() / MM, box.GetHeight() / MM
            # Sanity gate: a real Fab/courtyard outline never sits tens of mm from the footprint's
            # own origin, and never spans more than a few hundred mm. A KiCad-internal bounding-box
            # overflow (seen once, on a freshly-added text - see the reload note above) produces a
            # geometrically absurd but numerically finite box that would otherwise pass silently.
            fpos = fp.GetPosition()
            offset_mm = ((centre.x - fpos.x) ** 2 + (centre.y - fpos.y) ** 2) ** 0.5 / MM
            if w > 500 or h > 500 or offset_mm > 100:
                still_too_small.append('%s (outline computation looked invalid: %.1fx%.1f mm, %.1f mm from origin - left unmoved)' % (fp.GetReference(), w, h, offset_mm))
                box = None
                centre = fp.GetPosition()
                w = h = None
        else:
            centre = fp.GetPosition()
            w = h = None
        moved = box is not None and (ref.GetPosition().x, ref.GetPosition().y) != (centre.x, centre.y)
        if moved:
            ref.SetPosition(centre)
        try:
            ref.SetTextAngle(pcbnew.EDA_ANGLE(fp.GetOrientationDegrees(), pcbnew.DEGREES_T))
        except Exception:
            pass
        try:
            ref.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER)
            ref.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
        except Exception:
            pass
        try:
            shown = ref.GetShownText(True)  # resolves ${REFERENCE}/${VALUE} to the real designator
        except Exception:
            shown = ref.GetText()
        cur_h = ref.GetTextHeight() / MM
        if w and h:
            long_axis_mm = max(w, h)
            short_axis_mm = min(w, h)
            content_len = max(1, len(shown))
            fit_by_width = (long_axis_mm * 0.9) / (content_len * 0.8)
            target_h = min(cur_h, short_axis_mm * 0.9, fit_by_width)
        else:
            target_h = cur_h
        target_h = max(target_h, MIN_H)
        target_h = min(target_h, cur_h)  # never enlarge
        resized = abs(target_h - cur_h) > 1e-4
        if resized:
            ref.SetTextHeight(int(round(target_h * MM)))
            ref.SetTextWidth(int(round(target_h * MM)))
            ref.SetTextThickness(int(round(target_h * 0.15 * MM)))
        if moved or resized:
            centered += 1
        if w and h and target_h <= MIN_H + 1e-6 and (target_h < cur_h - 1e-4 or cur_h <= MIN_H + 1e-4):
            fit_w = target_h * 0.8 * max(1, len(shown))
            if fit_w > long_axis_mm * 0.9 + 1e-6:
                still_too_small.append(fp.GetReference())

print('Fab references centred/resized: %d' % centered)
if still_too_small:
    print('still does not fit at the %.2f mm floor: %s' % (MIN_H, ', '.join(sorted(set(still_too_small)))))

if DRY:
    print('[dry-run] not written')
    sys.exit(0)

if hidden or centered or added:
    B.Save(BOARD)
    print('saved')
else:
    print('nothing to change')
