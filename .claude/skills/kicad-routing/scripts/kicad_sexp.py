"""Shared s-expression helpers for the kicad-routing python tools.

Dependency-free. Depth-tracking scanner that respects quoted strings and backslash escapes -
never edit a board with line-based regex alone (see SKILL.md, "S-expression editing").

Import with:  sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import kicad_sexp
"""
import io, os, re, math, shutil, collections

BS = chr(92)
NL = chr(10)


def read_board(path):
    s = io.open(path, encoding='utf-8', newline='').read()
    eol = '\r\n' if '\r\n' in s[:4000] else NL
    return s, eol


def kids(text, open_idx=None):
    """Direct child lists of the list opening at open_idx.
    Yields (block_text, head_token, start, end_exclusive)."""
    open_idx = text.index('(') if open_idx is None else open_idx
    i = open_idx + 1
    n = len(text)
    depth = 0
    in_str = False
    esc = False
    start = None
    out = []
    while i < n:
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == BS:
                esc = True
            elif c == '"':
                in_str = False
            i += 1
            continue
        if c == '"':
            in_str = True
        elif c == '(':
            if depth == 0:
                start = i
            depth += 1
        elif c == ')':
            if depth == 0:
                break
            depth -= 1
            if depth == 0:
                m = re.match(r'\(\s*([^\s()"]+)', text[start:i + 1])
                out.append((text[start:i + 1], m.group(1) if m else '', start, i + 1))
        i += 1
    return out


def balanced(text):
    """(depth, min_depth, unterminated_string) - all three must be (0, 0, False)."""
    d = mind = 0
    ins = esc = False
    for c in text:
        if ins:
            if esc:
                esc = False
            elif c == BS:
                esc = True
            elif c == '"':
                ins = False
            continue
        if c == '"':
            ins = True
        elif c == '(':
            d += 1
        elif c == ')':
            d -= 1
            mind = min(mind, d)
    return d, mind, ins


def line_start(text, i):
    j = text.rfind(NL, 0, i)
    return j + 1 if j != -1 else 0


def whole_lines(text, a, b):
    """Expand [a,b) to the full lines it occupies, only if the block is alone on them."""
    ls = line_start(text, a)
    if text[ls:a].strip() != '':
        return a, b
    le = text.find(NL, b)
    if le == -1:
        return ls, b
    if text[b:le].strip() != '':
        return a, b
    return ls, le + 1


def census(blocks):
    return collections.Counter(h for _, h, _, _ in blocks)


def verify_write(path, original, result, expect_delta=None, protect=(
        'footprint', 'gr_line', 'gr_text', 'dimension', 'group', 'setup', 'layers'), backup_suffix='.bak'):
    """Balance + census + byte-identity checks, then write. Raises AssertionError on any failure."""
    d, mind, ins = balanced(result)
    assert (d, mind, ins) == (0, 0, False), 'paren/string imbalance: %s' % ((d, mind, ins),)
    A, B = kids(original), kids(result)
    ca, cb = census(A), census(B)
    for k in set(ca) | set(cb):
        want = ca.get(k, 0) + (expect_delta or {}).get(k, 0)
        assert cb.get(k, 0) == want, '%s: expected %d, got %d' % (k, want, cb.get(k, 0))
    for key in protect:
        if (expect_delta or {}).get(key):
            continue
        assert [b for b, h, _, _ in A if h == key] == [b for b, h, _, _ in B if h == key], \
            '%s blocks modified' % key
    bad = [h for _, h, st, _ in B if result[line_start(result, st):st] != '\t']
    assert not bad, 'bad top-level indentation: %s' % set(bad)
    bak = path + backup_suffix
    if not os.path.exists(bak):
        shutil.copy2(path, bak)
    io.open(path, 'w', encoding='utf-8', newline='').write(result)
    return bak


# ------------------------------------------------------------------ geometry
def fp_transform(blk):
    """Footprint origin and rotation; returns (fx, fy, cos, sin) using KiCad's RotatePoint
    convention  X = fx + px*cos + py*sin ,  Y = fy - px*sin + py*cos."""
    at = re.search(r'\n\t\t\(at ([-0-9.]+) ([-0-9.]+)(?: ([-0-9.]+))?\)', blk)
    fx, fy = float(at.group(1)), float(at.group(2))
    rot = math.radians(float(at.group(3) or 0))
    return fx, fy, math.cos(rot), math.sin(rot)


def xf(fx, fy, ca, sa, px, py):
    return fx + px * ca + py * sa, fy - px * sa + py * ca


def pt_seg_dist(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


_NUM = r'([-0-9.]+)'


def _pt(blk, key):
    m = re.search(r'\(%s %s %s\)' % (key, _NUM, _NUM), blk)
    return (float(m.group(1)), float(m.group(2))) if m else None


def shape_segments(blk, head):
    """Edge.Cuts graphic -> list of straight segments ((x1, y1), (x2, y2)) in the item's own coordinates.
    1.18.0: lines only were read before, so an outline drawn as gr_poly / gr_rect / gr_circle / gr_arc (the
    ServiceOne board: one polygon + six circular cut-outs) gave the stitcher no board edge at all."""
    kind = head[3:]                                              # gr_line -> line, fp_poly -> poly
    if kind == 'line':
        a, b = _pt(blk, 'start'), _pt(blk, 'end')
        return [(a, b)] if a and b else []
    if kind == 'rect':
        a, b = _pt(blk, 'start'), _pt(blk, 'end')
        if not (a and b):
            return []
        c = [a, (b[0], a[1]), b, (a[0], b[1])]
        return list(zip(c, c[1:] + c[:1]))
    if kind == 'poly':
        p = [(float(x), float(y)) for x, y in re.findall(r'\(xy %s %s\)' % (_NUM, _NUM), blk)]
        return list(zip(p, p[1:] + p[:1])) if len(p) > 1 else []
    if kind == 'circle':
        c, e = _pt(blk, 'center'), _pt(blk, 'end')
        if not (c and e):
            return []
        r = math.hypot(e[0] - c[0], e[1] - c[1])
        p = [(c[0] + r * math.cos(2 * math.pi * k / 48), c[1] + r * math.sin(2 * math.pi * k / 48)) for k in range(48)]
        return list(zip(p, p[1:] + p[:1]))
    if kind == 'arc':
        a, m, b = _pt(blk, 'start'), _pt(blk, 'mid'), _pt(blk, 'end')
        if not (a and m and b):
            return [(a, b)] if a and b else []
        d = 2 * (a[0] * (m[1] - b[1]) + m[0] * (b[1] - a[1]) + b[0] * (a[1] - m[1]))
        if abs(d) < 1e-12:
            return [(a, m), (m, b)]
        ux = ((a[0] ** 2 + a[1] ** 2) * (m[1] - b[1]) + (m[0] ** 2 + m[1] ** 2) * (b[1] - a[1]) + (b[0] ** 2 + b[1] ** 2) * (a[1] - m[1])) / d
        uy = ((a[0] ** 2 + a[1] ** 2) * (b[0] - m[0]) + (m[0] ** 2 + m[1] ** 2) * (a[0] - b[0]) + (b[0] ** 2 + b[1] ** 2) * (m[0] - a[0])) / d
        r = math.hypot(a[0] - ux, a[1] - uy)
        t0, tm, t1 = (math.atan2(q[1] - uy, q[0] - ux) for q in (a, m, b))
        sweep = (t1 - t0) % (2 * math.pi)
        if not (0 < (tm - t0) % (2 * math.pi) < sweep):
            sweep -= 2 * math.pi                                  # the arc runs the other way round
        n = max(4, int(abs(sweep) / (math.pi / 24)))
        p = [(ux + r * math.cos(t0 + sweep * k / n), uy + r * math.sin(t0 + sweep * k / n)) for k in range(n + 1)]
        return list(zip(p, p[1:]))
    return []


def rule_area(blk):
    """A zone block -> rule-area dict, or None when it is not a rule area. Footprint-internal rule areas carry
    absolute board coordinates (SKILL.md, Keepout Enumeration), so no transform is applied."""
    if '(keepout' not in blk:
        return None
    body = blk                                                   # the not_allowed flags occur only in (keepout ...)
    lm = re.search(r'\(layers? ([^)]*)\)', blk)
    layers = lm.group(1).replace('"', '').split() if lm else []
    pts = [(float(x), float(y)) for x, y in re.findall(r'\(xy %s %s\)' % (_NUM, _NUM), blk.split('(polygon', 1)[-1])]
    return {'layers': layers, 'poly': pts,
            'tracks': '(tracks not_allowed)' in body, 'vias': '(vias not_allowed)' in body}


def on_layer(layers, layer):
    """True when a rule area listed with `layers` applies to copper `layer` (handles *.Cu and F&B.Cu)."""
    for l in layers:
        if l == layer or l == '*.Cu' or (l == 'F&B.Cu' and layer in ('F.Cu', 'B.Cu')):
            return True
    return False


def pt_poly_dist(px, py, poly):
    """0 when (px, py) lies inside the polygon, else the distance to its boundary."""
    inside = False
    n = len(poly)
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        if (y1 > py) != (y2 > py) and px < (x2 - x1) * (py - y1) / (y2 - y1) + x1:
            inside = not inside
    if inside:
        return 0.0
    return min(pt_seg_dist(px, py, poly[i][0], poly[i][1], poly[(i + 1) % n][0], poly[(i + 1) % n][1]) for i in range(n)) if n else float('inf')


def collect(path):
    """Parse a board into pads / vias / segments / edge lines / zones / rule areas, all in absolute mm."""
    s, eol = read_board(path)
    K = kids(s)
    pads, vias, segs, edges, zones, rules = [], [], [], [], [], []
    for blk, h, _, _ in K:
        if h == 'footprint':
            fx, fy, ca, sa = fp_transform(blk)
            ref = re.search(r'\(property "Reference" "([^"]*)"', blk)
            ref = ref.group(1) if ref else '?'
            for pb, k, _, _ in kids(blk, 0):
                if k == 'pad':
                    toks = pb.split()
                    m = re.search(r'\(at ([-0-9.]+) ([-0-9.]+)', pb)
                    sz = re.search(r'\(size ([0-9.]+) ([0-9.]+)\)', pb)
                    w, hh = (float(sz.group(1)), float(sz.group(2))) if sz else (0.5, 0.5)
                    # 1.18.0: the circle must CONTAIN the pad: half the diagonal for anything but a round pad
                    # (half the larger side left the corners out - a stitching via shorted a side-LED pad)
                    r = max(w, hh) / 2.0 if (len(toks) > 3 and toks[3] == 'circle') else math.hypot(w, hh) / 2.0
                    # 1.18.0: a custom pad's copper is its primitives, not the anchor size (a side-view LED pad
                    # modelled by its 0.4 mm anchor was shorted by a stitching stub on ServiceOne)
                    if '(primitives' in pb:
                        prim = pb.split('(primitives', 1)[1]
                        wid = max([float(v) for v in re.findall(r'\(width ([0-9.]+)\)', prim)] or [0.0])
                        for x, y in re.findall(r'\((?:xy|start|end|mid|center) %s %s\)' % (_NUM, _NUM), prim):
                            r = max(r, math.hypot(float(x), float(y)) + wid / 2.0)
                    nm = re.search(r'\(net "([^"]*)"\)', pb)
                    lay = re.search(r'\(layers ([^)]*)\)', pb)
                    X, Y = xf(fx, fy, ca, sa, float(m.group(1)), float(m.group(2)))
                    pads.append({'x': X, 'y': Y, 'r': r,
                                 'net': nm.group(1) if nm else None,
                                 'smd': (toks[2] if len(toks) > 2 else '') == 'smd',
                                 'lays': lay.group(1).replace('"', '').split() if lay else [],
                                 'ref': ref, 'pad': toks[1].strip('"') if len(toks) > 1 else '?'})
                elif k.startswith('fp_') and 'Edge.Cuts' in pb:
                    for (x1, y1), (x2, y2) in shape_segments(pb, k):
                        X1, Y1 = xf(fx, fy, ca, sa, x1, y1)
                        X2, Y2 = xf(fx, fy, ca, sa, x2, y2)
                        edges.append((X1, Y1, X2, Y2))
                elif k == 'zone':
                    ra = rule_area(pb)
                    if ra:
                        ra['ref'] = ref
                        rules.append(ra)
        elif h == 'via':
            m = re.search(r'\(at ([-0-9.]+) ([-0-9.]+)\)', blk)
            sz = re.search(r'\(size ([0-9.]+)\)', blk)
            dr = re.search(r'\(drill ([0-9.]+)\)', blk)
            nm = re.search(r'\(net "([^"]*)"\)', blk)
            vias.append({'x': float(m.group(1)), 'y': float(m.group(2)),
                         'r': float(sz.group(1)) / 2.0, 'dr': float(dr.group(1)) / 2.0,
                         'net': nm.group(1) if nm else None})
        elif h == 'segment':
            a = re.search(r'\(start ([-0-9.]+) ([-0-9.]+)\)', blk)
            b = re.search(r'\(end ([-0-9.]+) ([-0-9.]+)\)', blk)
            w = re.search(r'\(width ([0-9.]+)\)', blk)
            nm = re.search(r'\(net "([^"]*)"\)', blk)
            ly = re.search(r'\(layer "([^"]+)"\)', blk)
            segs.append({'x1': float(a.group(1)), 'y1': float(a.group(2)),
                         'x2': float(b.group(1)), 'y2': float(b.group(2)),
                         'r': float(w.group(1)) / 2.0, 'net': nm.group(1) if nm else None,
                         'layer': ly.group(1) if ly else ''})
        elif h.startswith('gr_') and 'Edge.Cuts' in blk:
            for (x1, y1), (x2, y2) in shape_segments(blk, h):
                edges.append((x1, y1, x2, y2))
        elif h == 'zone':
            nm = re.search(r'\(net "([^"]*)"\)', blk)
            ly = re.search(r'\(layers? "?([^)"]+)"?\)', blk)
            zones.append({'net': nm.group(1) if nm else None,
                          'layer': (ly.group(1).strip() if ly else ''),
                          'keepout': '(keepout' in blk})
            ra = rule_area(blk)
            if ra:
                ra['ref'] = None
                rules.append(ra)
    return {'text': s, 'eol': eol, 'blocks': K, 'pads': pads, 'vias': vias,
            'segs': segs, 'edges': edges, 'zones': zones, 'rule_areas': rules}


def footprint_local_clearances(path_or_text):
    """[(reference, clearance_mm), ...] for footprints carrying a local (clearance N) override.

    These are invisible to the Specctra DSN, which has no per-footprint clearance field, so a
    router given only the board-global value will undercut the part and every violation shows up
    only after the import. rev J.

    Read from the FILE, never via pcbnew.LoadBoard: pcbnew caches the project by path, so probing
    with LoadBoard before editing the .kicad_pro pins the stale netclass clearances in memory.
    """
    # a board file always begins with "(kicad_pcb"; anything else is treated as a path
    if path_or_text.lstrip().startswith('('):
        src = path_or_text
    else:
        src, _eol = read_board(path_or_text)
    out = []
    for blk, head, _s, _e in kids(src):
        if head != 'footprint':
            continue
        ref = None
        for b2, h2, _a, _b in kids(blk):
            if h2 == 'property' and '"Reference"' in b2:
                m = re.search(r'"Reference"\s+"([^"]*)"', b2)
                if m:
                    ref = m.group(1)
        for b2, h2, _a, _b in kids(blk):
            if h2 == 'clearance':
                m = re.match(r'\(clearance\s+([0-9.]+)\s*\)', b2.strip())
                if m:
                    out.append((ref or '?', float(m.group(1))))
    return out


def clearance_floor(path_or_text):
    """Largest footprint-local clearance override in mm, or 0.0 when there is none."""
    vals = footprint_local_clearances(path_or_text)
    return max([v for _r, v in vals], default=0.0)


def sweep_candidates(floor, steps=(0.0, 0.05, 0.10)):
    """Clearance candidates for route_sweep.py. Never starts below the local-override floor."""
    base = floor if floor else 0.10
    return [round(base + s, 3) for s in steps]


def rules_from_project(board_path, defaults=None):
    """Read the design rules that these tools need out of <board>.kicad_pro."""
    import json
    # min_hole_clearance (drill edge to other-net copper; JLCPCB 0.254) defaults to 0 so that callers which
    # never used it behave exactly as before; stitch_planes.py enforces it (local fix after 1.16.0).
    out = {'min_clearance': 0.1, 'min_copper_edge_clearance': 0.5, 'min_hole_to_hole': 0.254,
           'min_track_width': 0.1, 'min_via_diameter': 0.45, 'min_through_hole_diameter': 0.2,
           'min_hole_clearance': 0.0}
    out.update(defaults or {})
    pro = os.path.splitext(board_path)[0] + '.kicad_pro'
    if os.path.exists(pro):
        try:
            r = json.load(io.open(pro, encoding='utf-8'))['board']['design_settings']['rules']
            for k in list(out):
                if k in r and isinstance(r[k], (int, float)):
                    out[k] = r[k]
        except Exception:
            pass
    return out


def find_kicad_cli(explicit=None):
    """kicad-cli: explicit path, PATH, then the usual install locations (newest first)."""
    import glob, shutil
    if explicit:
        return explicit
    for c in ('kicad-cli', 'kicad-cli.exe'):
        p = shutil.which(c)
        if p:
            return p
    for pat in (r'C:\Program Files\KiCad\*\bin\kicad-cli.exe', '/usr/bin/kicad-cli', '/usr/local/bin/kicad-cli',
                '/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'):
        hit = sorted(glob.glob(pat))
        if hit:
            return hit[-1]
    return None


def find_kicad_python(explicit=None):
    """The interpreter that has pcbnew: explicit path, KICAD_PYTHON env, the usual install locations."""
    import glob
    if explicit:
        return explicit
    if os.environ.get('KICAD_PYTHON'):
        return os.environ['KICAD_PYTHON']
    for pat in (r'C:\Program Files\KiCad\*\bin\python.exe',
                '/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3',
                '/usr/lib/kicad/bin/python', '/usr/bin/python3'):
        hit = sorted(glob.glob(pat))
        if hit:
            return hit[-1]
    return None
