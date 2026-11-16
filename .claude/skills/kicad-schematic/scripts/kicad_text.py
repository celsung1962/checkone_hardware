#!/usr/bin/env python3
"""
Text metrics of KiCad's stroke font (KiCad 8-10 default "KiCad Font"), for scripts that place or check text.

The font is proportional: "I" advances 0.61 mm and "M" 1.45 mm at 1.27 mm. Estimating a width as
characters x constant puts the inner end of a long label more than 1 mm off, which is enough to misalign a column
of labels or to let a value touch the next part.

CHAR_W: advance of each character at 1.27 mm (mm), fitted by least squares on 1801 plotted texts of a real
project (max error 0.03 mm, no constant term: width = sum of advances); the space (0.969 mm) is the median gap
between 2110 pairs of plotted words. Characters not in the table use 1.21 mm.

    from kicad_text import text_width, label_wire_length, aligned_label_anchor
    text_width("CH1_RANGE")            # 10.88 mm at 1.27 mm
    label_wire_length("CH1_RANGE")     # 12.70 mm: grid multiple covering the text + 0.6 mm
    aligned_label_anchor(132.08, "CH1_RANGE")   # far-end anchor so the text starts 0.635 mm after x = 132.08
"""
import math

CHAR_W = {"%": 1.450, "'": 0.605, "(": 0.846, ")": 0.846, "*": 0.966, "+": 1.572, ",": 0.605, "-": 1.572, ".": 0.605,
          "/": 1.330, ":": 0.605, ";": 0.605, "<": 1.572, "=": 1.572, ">": 1.572, "@": 1.632, "A": 1.088, "B": 1.270,
          "C": 1.270, "D": 1.270, "E": 1.148, "F": 1.088, "G": 1.270, "H": 1.330, "I": 0.605, "J": 0.967, "K": 1.270,
          "L": 1.027, "M": 1.450, "N": 1.330, "O": 1.330, "P": 1.270, "Q": 1.330, "R": 1.270, "S": 1.209, "T": 0.967,
          "U": 1.330, "V": 1.088, "W": 1.450, "X": 1.209, "Y": 1.089, "Z": 1.209, "[": 0.846, "]": 0.846, "_": 0.967,
          "a": 1.148, "b": 1.148, "c": 1.088, "d": 1.148, "e": 1.088, "f": 0.725, "g": 1.148, "h": 1.148, "i": 0.605,
          "k": 1.027, "l": 0.664, "m": 1.693, "n": 1.148, "o": 1.148, "p": 1.148, "q": 1.148, "r": 0.786, "s": 1.027,
          "t": 0.725, "u": 1.148, "v": 0.966, "w": 1.330, "x": 1.027, "y": 0.966, "z": 1.027, "~": 0.907, " ": 0.969}
CHAR_W.update({str(d): 1.209 for d in range(10)})
DEFAULT_W = 1.21
HEIGHT = 1.15          # text box height / font size (cap height plus stroke)


def text_width(s, size=1.27):
    """Plotted width (mm) of a single-line text at font size `size` (mm)."""
    return sum(CHAR_W.get(c, DEFAULT_W) for c in s) * size / 1.27


LABEL_OFFSET = 0.23   # KiCad draws a local label's text this far inside its anchor (0.228-0.235 mm measured)


def label_wire_length(net, size=1.27, margin=0.6, grid=1.27):
    """Length of the wire that runs under the whole text of a label, rounded UP to the connection grid."""
    return round(math.ceil((text_width(net, size) + margin) / grid - 1e-9) * grid, 4)


def aligned_label_anchor(start, net, direction=1, gap=0.635, grid=0.635, size=1.27):
    """Far-end anchor (one coordinate, mm) of a label whose text must START `gap` mm from `start` (the point
    where the label wire leaves the pin or lane), with the label anchored at the far end and its text running back
    toward `start` (wire under the whole text). direction = +1 if the wire runs toward +x/+y, -1 otherwise.
    The anchor is snapped to the connection grid: with KiCad's minimum connection grid of 25 mil (0.635 mm) the
    text starts of a column line up within +/-0.32 mm."""
    raw = start + direction * (gap + text_width(net, size) + LABEL_OFFSET)
    return round(round(raw / grid) * grid, 4)


if __name__ == "__main__":
    import sys
    for s in sys.argv[1:] or ["CH1_RANGE", "EN24", "ADC_SYNC_RESET", "100K", "4.7uF 50V"]:
        print(f"{s:20s} {text_width(s):6.2f} mm   label wire {label_wire_length(s):6.2f} mm")
