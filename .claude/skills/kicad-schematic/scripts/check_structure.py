#!/usr/bin/env python3
"""check_structure.py - structural drawing rules of references/schematic_drawing.md sections 5 and 8a, checked on
the .kicad_sch files (no PDF, no KiCad needed). Pairs with check_drawing.py (text collisions on the plot) and
fix_passive_text.py (R/C text sweep).

    python3 check_structure.py <root.kicad_sch> [--max-value 12] [--json OUT] [--no-warn]

Checks (FAIL fails the run, WARN is reported):
  sheet-no-pins      FAIL  a sheet symbol with no pins and no "in: ... / out: ..." rails text inside its outline
  ports-text-only    FAIL  a "SHEET PORTS" text box that contains no hierarchical label and no power symbol
  pin-no-connect     FAIL  a sheet pin that ends on a no-connect flag
  label-on-pin       FAIL  a net / global / hierarchical label anchored on a symbol pin (no wire stub)
  power-on-pin       FAIL  a power symbol (or PWR_FLAG) whose pin sits directly on another part's pin
  power-sideways     FAIL  a power symbol pointing left or right
  power-inverted     WARN  a ground / negative rail pointing up, or a positive rail pointing down
                           (allowed only for the inverted ground above a part, section 3)
  pwr-flag-count     FAIL  more than one PWR_FLAG on one net
  long-value         WARN  a visible Value longer than --max-value characters, or equal to the part's MPN field
                           (ICs whose value fits inside the body width are exempt)
  ref-order          WARN  references of one prefix running right to left / bottom to top inside a row / column
  long-note          WARN  a note (text / text box) with more than 6 lines or 400 characters (ports block exempt)
  title-process      WARN  a title-block comment with a process remark ("generated", "do not edit")
  paper-size         FAIL  a sheet not on A3 landscape (A2 / A1 / A0 landscape: WARN, a recorded deviation)
Exit code: 0 no FAIL, 1 FAIL, 2 usage error.
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from fix_passive_text import Sheet, kid, kids, head, num  # noqa: E402
from kicad_text import text_width  # noqa: E402

TOL = 0.02
GROUND = re.compile(r'(^-|GND|VSS|VEE|^0V$|EARTH|CHASSIS)', re.I)
MPN_FIELDS = ('MPN', 'Manufacturer_Part_Number', 'MFR_PN', 'Mfr. Part #', 'PartNumber', 'Part Number')


def key(p):
    return (round(p[0] / TOL) * TOL, round(p[1] / TOL) * TOL)


def same(a, b):
    return abs(a[0] - b[0]) <= TOL and abs(a[1] - b[1]) <= TOL


def on_segment(p, a, b):
    (x, y), (x0, y0), (x1, y1) = p, a, b
    if abs((x1 - x0) * (y - y0) - (y1 - y0) * (x - x0)) > TOL * max(1.0, abs(x1 - x0) + abs(y1 - y0)):
        return False
    return min(x0, x1) - TOL <= x <= max(x0, x1) + TOL and min(y0, y1) - TOL <= y <= max(y0, y1) + TOL


def prop(node, name):
    for p in kids(node, 'property'):
        if p[1] == name:
            return p[2]
    return None


def is_power(sym):
    return sym['ref'].startswith('#') or (prop(sym['node'], 'Reference') or '').startswith('#')


class Finding(dict):
    pass


def sheet_files(root_path):
    """(sheet file, parent Sheet, sheet node) for every sub-sheet, depth first; the root itself first."""
    seen, out = set(), []

    def walk(path, parent, node):
        path = os.path.normpath(path)
        s = Sheet(path)
        out.append((s, parent, node))
        if path in seen:
            return
        seen.add(path)
        for sh in kids(s.root, 'sheet'):
            f = prop(sh, 'Sheetfile') or prop(sh, 'Sheet file')
            if f:
                walk(os.path.join(os.path.dirname(path), f), s, sh)
    walk(root_path, None, None)
    return out


def points_of_labels(s, kinds=('label', 'global_label', 'hierarchical_label')):
    out = []
    for k in kinds:
        for l in kids(s.root, k):
            at = kid(l, 'at')
            out.append((k, l[1], (num(at[1]), num(at[2]))))
    return out


def nets_of_sheet(s):
    """Union-find over wire ends, pin points and label anchors; returns {point_key: group} and group names."""
    parent = {}

    def find(a):
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    segs = []
    for w in kids(s.root, 'wire'):
        pts = [(num(q[1]), num(q[2])) for q in kid(w, 'pts') if head(q) == 'xy']
        segs += list(zip(pts, pts[1:]))
    nodes = []
    for a, b in segs:
        nodes += [a, b]
    for sym in s.syms:
        for p in sym['pins']:
            nodes.append(p[0])
    for _, _, p in points_of_labels(s):
        nodes.append(p)
    for n in nodes:
        find(key(n))
    for a, b in segs:
        union(key(a), key(b))
        for n in nodes:
            if on_segment(n, a, b):
                union(key(n), key(a))
    # pins / labels on the same point are connected
    names = {}
    for k, name, p in points_of_labels(s):
        names.setdefault(find(key(p)), set()).add(name)
    for sym in s.syms:
        if is_power(sym) and sym['pins']:
            v = prop(sym['node'], 'Value') or ''
            if v and v != 'PWR_FLAG':
                names.setdefault(find(key(sym['pins'][0][0])), set()).add(v)
    return find, names


def check(root_path, max_value=12):
    fs = []

    def add(level, check_, sheet, msg, at=None):
        fs.append(Finding(level=level, check=check_, sheet=os.path.basename(sheet.path), msg=msg,
                          at=None if at is None else [round(at[0], 2), round(at[1], 2)]))
    flags = {}
    for s, parent, shnode in sheet_files(root_path):
        # ---- sheet symbols drawn on this sheet
        ncs = [(num(kid(n, 'at')[1]), num(kid(n, 'at')[2])) for n in kids(s.root, 'no_connect')]
        texts = [(t[1], (num(kid(t, 'at')[1]), num(kid(t, 'at')[2]))) for t in kids(s.root, 'text')]
        texts += [(t[1], (num(kid(t, 'at')[1]), num(kid(t, 'at')[2]))) for t in kids(s.root, 'text_box')]
        for sh in kids(s.root, 'sheet'):
            at, sz = kid(sh, 'at'), kid(sh, 'size')
            x0, y0 = num(at[1]), num(at[2]); x1, y1 = x0 + num(sz[1]), y0 + num(sz[2])
            name = prop(sh, 'Sheetname') or prop(sh, 'Sheet name') or '?'
            pins = kids(sh, 'pin')
            if not pins:
                rails = any(x0 - 1 <= p[0] <= x1 + 1 and y0 - 1 <= p[1] <= y1 + 6 and re.search(r'\b(in|out)\s*:', t, re.I)
                            for t, p in texts)
                if not rails:
                    add('FAIL', 'sheet-no-pins', s, f"sheet '{name}' has no pins and no 'in: ... / out: ...' rails "
                        "text: its interface is invisible on this sheet (section 5)", (x0, y0))
            for p in pins:
                pa = kid(p, 'at'); pp = (num(pa[1]), num(pa[2]))
                if any(same(pp, n) for n in ncs):
                    add('FAIL', 'pin-no-connect', s, f"sheet '{name}' pin {p[1]} ends on a no-connect: draw the "
                        "destination sheet (empty, with its ports, 'TBD') and wire the pin to it (section 5)", pp)
        # ---- ports block made of real objects
        hl = [p for k, _, p in points_of_labels(s, ('hierarchical_label',))]
        pw = [sym['pins'][0][0] for sym in s.syms if is_power(sym) and sym['pins']]
        for t in kids(s.root, 'text_box') + kids(s.root, 'text'):
            if not t[1].strip().upper().startswith('SHEET PORTS'):
                continue
            at = kid(t, 'at'); x0, y0 = num(at[1]), num(at[2])
            sz = kid(t, 'size')
            if sz is not None:
                x1, y1 = x0 + num(sz[1]), y0 + num(sz[2])
            else:
                lines = t[1].split('\n')
                x1, y1 = x0 + max(text_width(l, 1.27) for l in lines) + 2, y0 + 1.27 * 1.6 * len(lines) + 2
            listing = [l for l in t[1].split('\n')[1:] if l.strip()]
            # a title-only box heads a column of real labels below it; a box with more lines lists the ports
            inside = [p for p in hl + pw if x0 - 2 <= p[0] <= x1 + 25 and y0 - 2 <= p[1] <= y1 + 80]
            if listing or not inside:
                add('FAIL', 'ports-text-only', s, "the SHEET PORTS block only lists the ports in text: put the "
                    "hierarchical labels (signals) and power symbols (rails) in it (section 5)", (x0, y0))
        # ---- labels and power symbols on pins
        libs = kid(s.root, 'lib_symbols') or []
        hidden_num = {n[1] for n in libs if head(n) == 'symbol' and kid(n, 'pin_numbers') is not None
                      and 'hide' in str(kid(n, 'pin_numbers'))}
        # pins whose numbers are shown (ICs, connectors): a label or power symbol on them hides the number
        part_pins = [(sym['ref'], p[0]) for sym in s.syms if not is_power(sym)
                     and kid(sym['node'], 'lib_id')[1] not in hidden_num for p in sym['pins']]
        for k, name, p in points_of_labels(s):
            for ref, q in part_pins:
                if same(p, q):
                    add('FAIL', 'label-on-pin', s, f"{k.replace('_', ' ')} '{name}' sits on pin of {ref}: start "
                        "it at the end of a wire stub (section 8a.8)", p)
                    break
        for sym in s.syms:
            if not is_power(sym) or not sym['pins']:
                continue
            v = prop(sym['node'], 'Value') or ''
            pp = sym['pins'][0][0]
            for ref, q in part_pins:
                if same(pp, q):
                    add('FAIL', 'power-on-pin', s, f"power symbol '{v}' sits directly on pin of {ref}: wire it "
                        "through a stub (section 8a.8)", pp)
                    break
            if v == 'PWR_FLAG':
                flags.setdefault(s.path, []).append(sym)
                continue
            if sym['body'] is None:
                continue
            bx = ((sym['body'][0] + sym['body'][2]) / 2, (sym['body'][1] + sym['body'][3]) / 2)
            dx, dy = bx[0] - pp[0], bx[1] - pp[1]
            if abs(dx) > abs(dy) + 0.2:
                add('FAIL', 'power-sideways', s, f"power symbol '{v}' points {'right' if dx > 0 else 'left'}: "
                    "grounds point down, rails up (section 8a.6)", pp)
            else:
                down = dy > 0
                if GROUND.search(v) and not down:
                    add('WARN', 'power-inverted', s, f"'{v}' points up: allowed only for a ground above a part "
                        "(section 3)", pp)
                elif not GROUND.search(v) and down:
                    add('WARN', 'power-inverted', s, f"rail '{v}' points down (section 8a.6)", pp)
        # ---- values
        for sym in s.syms:
            if is_power(sym):
                continue
            val = next((f for f in sym['fields'] if f['name'] == 'Value'), None)
            if val is None:
                continue
            mpn = next((prop(sym['node'], f) for f in MPN_FIELDS if prop(sym['node'], f)), None)
            body_w = (sym['body'][2] - sym['body'][0]) if sym['body'] else 0
            fits = sym['ref'][:1] == 'U' and text_width(val['text'], val['size']) <= body_w
            if fits:
                continue
            if len(val['text']) > max_value:
                add('WARN', 'long-value', s, f"{sym['ref']} value '{val['text']}' is {len(val['text'])} characters: "
                    "show a short value, keep the part number in the MPN / LCSC field (section 8a.4)",
                    (val['x'], val['y']))
            elif mpn and val['text'].strip() == mpn.strip() and len(mpn) > 8:
                add('WARN', 'long-value', s, f"{sym['ref']} value equals its MPN '{mpn}' (section 8a.4)",
                    (val['x'], val['y']))
        # ---- reference order
        byp = {}
        for sym in s.syms:
            m = re.match(r'^([A-Z]+)(\d+)$', sym['ref'])
            if m and not is_power(sym):
                byp.setdefault(m.group(1), {})[int(m.group(2))] = (sym['x'], sym['y'])
        for pre, d in byp.items():
            bad = []
            for n in sorted(d):
                if n + 1 not in d:
                    continue
                (xa, ya), (xb, yb) = d[n], d[n + 1]
                if abs(ya - yb) < 1.3 and abs(xa - xb) < 25 and xb < xa - 1:
                    bad.append(f'{pre}{n}->{pre}{n + 1}')
                elif abs(xa - xb) < 1.3 and abs(ya - yb) < 25 and yb < ya - 1:
                    bad.append(f'{pre}{n}->{pre}{n + 1}')
            if bad:
                add('WARN', 'ref-order', s, f"{len(bad)} {pre} pair(s) numbered right to left or bottom to top: "
                    f"{', '.join(bad[:6])}{' ...' if len(bad) > 6 else ''} (section 8a.11)")
        # ---- notes and title block
        for t in kids(s.root, 'text_box') + kids(s.root, 'text'):
            body = t[1]
            if body.strip().upper().startswith('SHEET PORTS'):
                continue
            if body.count('\n') + 1 > 6 or len(body) > 400:
                at = kid(t, 'at')
                add('WARN', 'long-note', s, f"note of {body.count(chr(10)) + 1} lines / {len(body)} characters: keep "
                    "what the reader needs here, move calculations and histories to the report (section 8a.12)",
                    (num(at[1]), num(at[2])))
        paper = kid(s.root, 'paper')
        size = paper[1] if paper is not None and len(paper) > 1 else 'A4'
        portrait = paper is not None and 'portrait' in paper[2:]
        if size != 'A3' or portrait:
            big = size in ('A2', 'A1', 'A0') and not portrait
            add('WARN' if big else 'FAIL', 'paper-size', s, f"sheet on {size}{' portrait' if portrait else ''}: draw "
                "every sheet on A3 landscape" + (" (a larger size only as a recorded deviation)" if big else "") +
                " (section 6)")
        tb = kid(s.root, 'title_block')
        if tb is not None:
            for c in kids(tb, 'comment'):
                if re.search(r'generated|do not edit', c[2] if len(c) > 2 else '', re.I):
                    add('WARN', 'title-process', s, f"title-block comment '{c[2]}' is a process remark: move it to "
                        "the README (section 8a.13)")
    # ---- PWR_FLAG count per net, project wide (power symbols are global; local labels per sheet)
    seen_paths = {}
    per_net = {}
    for s, _, _ in sheet_files(root_path):
        if s.path in seen_paths or s.path not in flags:
            continue
        seen_paths[s.path] = True
        find, names = nets_of_sheet(s)
        for sym in flags[s.path]:
            g = find(key(sym['pins'][0][0]))
            nm = sorted(names.get(g, {f'{os.path.basename(s.path)}:unnamed@{g}'}))
            per_net.setdefault(nm[0], []).append((s, sym))
    for net, lst in per_net.items():
        if len(lst) > 1:
            where = ', '.join(f"{os.path.basename(s.path)} ({sym['x']:.1f}, {sym['y']:.1f})" for s, sym in lst)
            add('FAIL', 'pwr-flag-count', lst[0][0], f"{len(lst)} PWR_FLAG on net '{net}': keep one, at the rail's "
                f"source (section 8a.7) - {where}")
    return fs


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('root')
    ap.add_argument('--max-value', type=int, default=12)
    ap.add_argument('--json')
    ap.add_argument('--no-warn', action='store_true')
    a = ap.parse_args()
    if not os.path.exists(a.root):
        print('no such file:', a.root); return 2
    fs = check(a.root, a.max_value)
    for f in fs:
        if a.no_warn and f['level'] == 'WARN':
            continue
        print(f"{f['level']:4} {f['check']:15} {f['sheet']}: {f['msg']}" + (f" @ {f['at'][0]}, {f['at'][1]}" if f['at'] else ''))
    n_fail = sum(f['level'] == 'FAIL' for f in fs)
    n_warn = sum(f['level'] == 'WARN' for f in fs)
    print(f'{n_fail} FAIL, {n_warn} WARN')
    if a.json:
        json.dump(fs, open(a.json, 'w', encoding='utf-8'), indent=1)
    return 1 if n_fail else 0


if __name__ == '__main__':
    sys.exit(main())
