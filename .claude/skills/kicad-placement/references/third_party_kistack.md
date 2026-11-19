# Third-party notice: KiStack layout-placement

`scripts/local_reach.py` and the "Local reachability" rules in `placement_rules.md` are adapted from the
layout-placement skill of KiStack (https://github.com/BackplaneWorks/kistack, commit of 2026-11-17): the scripts
`route_check.py`, `grid_router.py`, `placement_audit.py`, `local_search.py` and `rules.py`, and its SKILL.md.

What changed in the adaptation (2026-11-19, kicad-placement 1.5.0):

- pcbnew instead of KiCad's IPC API (kipy) and Backplane's API server: the board is read from the file, nothing is
  written;
- per-net rules from the `.kicad_pro` net classes and the pads' resolved clearance, with a neck-down to the
  Default width near the IC, instead of one strictest value for the whole board;
- a window around each IC and cached obstacle masks (speed on 300+ part boards);
- escapes to a ring around the IC instead of the board edge;
- local parts chosen by net (a pad on an IC net near that pin, then their RC / divider partners) instead of
  every part of four pads or fewer near the IC; on supply rails only each part's link to the IC pin, since a
  multi-layer board joins rail capacitors through planes;
- re-ordering passes and a routed-alone test, so a link the greedy router cannot fit with the others is a WARN and
  only a link with no corridor even alone fails;
- new reports: the parts holding the strip in front of a far pin, crowded neighbouring pins, an IC rotation score;
- the RF matching-chain checks are not ported (AQTech boards are analog / low frequency).

Licence of the original:

```
Copyright 2026 American Embedded, LLC

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
documentation files (the "Software"), to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of
the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE
WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR
OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
```
