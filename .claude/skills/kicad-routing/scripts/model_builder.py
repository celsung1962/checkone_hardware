#!/usr/bin/env python
"""model_builder.py - approximate 3D models made of boxes, as STEP (AP214) and VRML (lesson L26, ServiceOne review
issue 20). Plain Python, no KiCad needed.

Search first: KiCad's library, EasyEDA by LCSC code, the manufacturer. For a part still without a model, the designer
either finds one or lets Claude build an approximate one from the datasheet drawing. The file name ends in `_approx`.
The audit's section 28 lists every `*_approx` model as INFO, so it goes into the release note. Prototype: ServiceOne
hardware/routing/model_tools/box_model.py (SW1, 2026-10-20).

  model_builder.py spec <spec.json> --out DIR [--assign FOOTPRINT.kicad_mod --model-path PATH]
      spec.json: {"name": "SW_X", "boxes": [{"name": "housing", "color": [0.1, 0.1, 0.1],
                  "x": [-4.7, 4.7], "y": [-14.7, -1.7], "z": [0, 17.0]}, ...]}
      Box coordinates are in the footprint frame, in mm: x to the right, y down (as KiCad footprints), z up from the
      board surface (negative z is below the board: THT tails). Take them from the datasheet drawing and note the
      source of each height in the spec's "note" fields.
  model_builder.py footprint <FOOTPRINT.kicad_mod> --height H --out DIR [--body fab|courtyard|pads] [--standoff Z]
                  [--inset MM] [--pin-length 3.0] [--body-color r,g,b] [--assign] [--model-path PATH]
      A body box over the footprint's F.Fab outline (default; --body courtyard uses the courtyard less --inset
      0.25 mm, --body pads the pad extent), from --standoff to H, plus one box per pad: an SMD pad becomes a 0.1 mm
      lead on the board, a THT pad becomes a pin of drill size from -pin-length to the body base. Rotated pads use
      their bounding box. Good for a 3D clearance view and the mechanical checks, never for a drawing.

Output: DIR/<name>_approx.step and .wrl (VRML in KiCad's 0.1-inch unit). --assign writes or replaces the footprint's
(model ...) block for that file name (path: --model-path, default ${KIPRJMOD}/<DIR name>/<name>_approx.step); the
footprint file is rewritten as text and nothing else in it changes.
"""
import datetime
import json
import math
import os
import re
import sys

# ------------------------------------------------------------------ geometry -> STEP / VRML (from box_model.py)
FACES = [((0, 3, 2, 1), (0, 0, -1)), ((4, 5, 6, 7), (0, 0, 1)),
         ((0, 1, 5, 4), (0, -1, 0)), ((2, 3, 7, 6), (0, 1, 0)),
         ((1, 2, 6, 5), (1, 0, 0)), ((3, 0, 4, 7), (-1, 0, 0))]


def corners(b):
    x0, x1 = sorted(b['x'])
    y0, y1 = sorted(b['y'])
    z0, z1 = sorted(b['z'])
    ya, yb = -y1, -y0                       # footprint y down -> model y up
    return [(x0, ya, z0), (x1, ya, z0), (x1, yb, z0), (x0, yb, z0),
            (x0, ya, z1), (x1, ya, z1), (x1, yb, z1), (x0, yb, z1)]


def num(v):
    return f"{v:.6f}" if abs(v) >= 1e-12 else "0."


def write_step(path, name, boxes, note):
    ents = []

    def e(s):
        ents.append(s)
        return f"#{len(ents)}"
    unit_len = e("( LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.) )")
    unit_ang = e("( NAMED_UNIT(*) PLANE_ANGLE_UNIT() SI_UNIT($,.RADIAN.) )")
    unit_sol = e("( NAMED_UNIT(*) SI_UNIT($,.STERADIAN.) SOLID_ANGLE_UNIT() )")
    unc = e(f"UNCERTAINTY_MEASURE_WITH_UNIT(LENGTH_MEASURE(1.E-07),{unit_len},'distance_accuracy_value','confusion accuracy')")
    ctx = e(f"( GEOMETRIC_REPRESENTATION_CONTEXT(3) GLOBAL_UNCERTAINTY_ASSIGNED_CONTEXT(({unc})) GLOBAL_UNIT_ASSIGNED_CONTEXT(({unit_len},{unit_ang},{unit_sol})) REPRESENTATION_CONTEXT('Context #1','3D Context with UNIT and UNCERTAINTY') )")
    origin = e("CARTESIAN_POINT('',(0.,0.,0.))")
    dz = e("DIRECTION('',(0.,0.,1.))")
    dx = e("DIRECTION('',(1.,0.,0.))")
    world = e(f"AXIS2_PLACEMENT_3D('',{origin},{dz},{dx})")
    solids = []
    for b in boxes:
        P = corners(b)
        vp = [e(f"CARTESIAN_POINT('',({num(p[0])},{num(p[1])},{num(p[2])}))") for p in P]
        vv = [e(f"VERTEX_POINT('',{p})") for p in vp]
        edges = {}

        def edge(i, j):
            key = (min(i, j), max(i, j))
            if key not in edges:
                a, c = P[key[0]], P[key[1]]
                d = tuple(c[k] - a[k] for k in range(3))
                L = sum(t * t for t in d) ** 0.5
                dirr = e(f"DIRECTION('',({num(d[0] / L)},{num(d[1] / L)},{num(d[2] / L)}))")
                vec = e(f"VECTOR('',{dirr},1.)")
                line = e(f"LINE('',{vp[key[0]]},{vec})")
                edges[key] = e(f"EDGE_CURVE('',{vv[key[0]]},{vv[key[1]]},{line},.T.)")
            return edges[key], (i, j) == key
        faces = []
        for idx, n in FACES:
            oes = []
            for k in range(4):
                ec, same = edge(idx[k], idx[(k + 1) % 4])
                oes.append(e(f"ORIENTED_EDGE('',*,*,{ec},{'.T.' if same else '.F.'})"))
            loop = e(f"EDGE_LOOP('',({','.join(oes)}))")
            bound = e(f"FACE_OUTER_BOUND('',{loop},.T.)")
            nd = e(f"DIRECTION('',({num(n[0])},{num(n[1])},{num(n[2])}))")
            ref = (1, 0, 0) if n[0] == 0 else (0, 1, 0)
            rd = e(f"DIRECTION('',({num(ref[0])},{num(ref[1])},{num(ref[2])}))")
            ax = e(f"AXIS2_PLACEMENT_3D('',{vp[idx[0]]},{nd},{rd})")
            pl = e(f"PLANE('',{ax})")
            faces.append(e(f"ADVANCED_FACE('',({bound}),{pl},.T.)"))
        shell = e(f"CLOSED_SHELL('',({','.join(faces)}))")
        solid = e(f"MANIFOLD_SOLID_BREP('{b.get('name', 'box')}',{shell})")
        r, g, bl = b.get('color', (0.2, 0.2, 0.2))
        col = e(f"COLOUR_RGB('',{num(r)},{num(g)},{num(bl)})")
        fsty = e(f"FILL_AREA_STYLE_COLOUR('',{col})")
        fa = e(f"FILL_AREA_STYLE('',({fsty}))")
        sfa = e(f"SURFACE_STYLE_FILL_AREA({fa})")
        ssu = e(f"SURFACE_SIDE_STYLE('',({sfa}))")
        su = e(f"SURFACE_STYLE_USAGE(.BOTH.,{ssu})")
        psa = e(f"PRESENTATION_STYLE_ASSIGNMENT(({su}))")
        e(f"STYLED_ITEM('color',({psa}),{solid})")
        solids.append(solid)
    rep = e(f"ADVANCED_BREP_SHAPE_REPRESENTATION('{name}',({world},{','.join(solids)}),{ctx})")
    appctx = e("APPLICATION_CONTEXT('core data for automotive mechanical design processes')")
    e(f"APPLICATION_PROTOCOL_DEFINITION('international standard','automotive_design',2000,{appctx})")
    pctx = e(f"PRODUCT_CONTEXT('',{appctx},'mechanical')")
    prod = e(f"PRODUCT('{name}','{name}','approximate model',({pctx}))")
    pdf = e(f"PRODUCT_DEFINITION_FORMATION('','',{prod})")
    pdctx = e(f"PRODUCT_DEFINITION_CONTEXT('part definition',{appctx},'design')")
    pd = e(f"PRODUCT_DEFINITION('design','',{pdf},{pdctx})")
    pds = e(f"PRODUCT_DEFINITION_SHAPE('','',{pd})")
    e(f"SHAPE_DEFINITION_REPRESENTATION({pds},{rep})")
    now = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
    safe = re.sub(r"[^ -~]", "?", note).replace("'", " ")[:200]
    with open(path, 'w', encoding='ascii', newline='\n') as fh:
        fh.write("ISO-10303-21;\nHEADER;\n")
        fh.write(f"FILE_DESCRIPTION(('{name} approximate model: {safe}'),'2;1');\n")
        fh.write(f"FILE_NAME('{name}.step','{now}',(''),(''),'model_builder.py','model_builder.py','');\n")
        fh.write("FILE_SCHEMA(('AUTOMOTIVE_DESIGN { 1 0 10303 214 1 1 1 1 }'));\nENDSEC;\nDATA;\n")
        for i, s in enumerate(ents, 1):
            fh.write(f"#{i}={s};\n")
        fh.write("ENDSEC;\nEND-ISO-10303-21;\n")


def write_wrl(path, boxes):
    k = 1 / 2.54                              # KiCad VRML unit = 0.1 inch
    with open(path, 'w', encoding='ascii', newline='\n') as fh:
        fh.write("#VRML V2.0 utf8\n")
        for b in boxes:
            P = corners(b)
            r, g, bl = b.get('color', (0.2, 0.2, 0.2))
            pts = ", ".join(f"{p[0] * k:.5f} {p[1] * k:.5f} {p[2] * k:.5f}" for p in P)
            idx = ", ".join(" ".join(str(i) for i in face) + " -1" for face, _ in FACES)
            fh.write(f"Shape {{ appearance Appearance {{ material Material {{ diffuseColor {r} {g} {bl} }} }}\n")
            fh.write(f"  geometry IndexedFaceSet {{ solid TRUE coord Coordinate {{ point [ {pts} ] }} coordIndex [ {idx} ] }} }}\n")


# ------------------------------------------------------------------ footprint reading (minimal s-expression parser)
def parse(text):
    tok = re.findall(r'"(?:[^"\\]|\\.)*"|\(|\)|[^\s()"]+', text)
    stack, cur = [], []
    for t in tok:
        if t == '(':
            stack.append(cur)
            cur = []
        elif t == ')':
            done = cur
            cur = stack.pop()
            cur.append(done)
        else:
            cur.append(t[1:-1] if t.startswith('"') else t)
    return cur[0]


def kid(n, k):
    return next((c for c in n[1:] if isinstance(c, list) and c and c[0] == k), None)


def kidsof(n, k):
    return [c for c in n[1:] if isinstance(c, list) and c and c[0] == k]


def fnum(v):
    return float(v)


def outline_pts(fp, layer):
    pts = []
    for g in kidsof(fp, 'fp_line') + kidsof(fp, 'fp_rect') + kidsof(fp, 'fp_poly') + kidsof(fp, 'fp_circle') + kidsof(fp, 'fp_arc'):
        lay = kid(g, 'layer')
        if not lay or lay[1] != layer:
            continue
        for key in ('start', 'end', 'mid', 'center'):
            q = kid(g, key)
            if q:
                pts.append((fnum(q[1]), fnum(q[2])))
        if g[0] == 'fp_circle' and kid(g, 'center') and kid(g, 'end'):
            c, e = kid(g, 'center'), kid(g, 'end')
            r = math.hypot(fnum(e[1]) - fnum(c[1]), fnum(e[2]) - fnum(c[2]))
            pts += [(fnum(c[1]) - r, fnum(c[2]) - r), (fnum(c[1]) + r, fnum(c[2]) + r)]
        ps = kid(g, 'pts')
        if ps:
            pts += [(fnum(p[1]), fnum(p[2])) for p in ps[1:] if isinstance(p, list) and p[0] == 'xy']
    return pts


def pad_boxes(fp, z_base, pin_len, color=(0.78, 0.78, 0.80)):
    out = []
    for p in kidsof(fp, 'pad'):
        kind = p[2]
        at = kid(p, 'at')
        x, y = fnum(at[1]), fnum(at[2])
        rot = fnum(at[3]) if len(at) > 3 else 0.0
        sz = kid(p, 'size')
        w, h = fnum(sz[1]), fnum(sz[2])
        c, s = abs(math.cos(math.radians(rot))), abs(math.sin(math.radians(rot)))
        bw, bh = w * c + h * s, w * s + h * c
        if kind in ('thru_hole', 'np_thru_hole'):
            if kind == 'np_thru_hole':
                continue
            dr = kid(p, 'drill')
            d = fnum([v for v in dr[1:] if not isinstance(v, list) and v != 'oval'][0]) if dr else min(w, h) * 0.6
            d *= 0.8
            out.append({'name': 'pin' + str(p[1]), 'color': color, 'x': [x - d / 2, x + d / 2], 'y': [y - d / 2, y + d / 2],
                        'z': [-pin_len, max(z_base, 0.5)]})
        else:
            out.append({'name': 'lead' + str(p[1]), 'color': color, 'x': [x - bw / 2, x + bw / 2],
                        'y': [y - bh / 2, y + bh / 2], 'z': [0.0, 0.1]})
    return out


def from_footprint(fp, height, body='fab', standoff=0.0, inset=0.25, pin_len=3.0, color=(0.15, 0.15, 0.15)):
    if body == 'pads':
        pts = []
        for b in pad_boxes(fp, 0, 0):
            pts += [(b['x'][0], b['y'][0]), (b['x'][1], b['y'][1])]
        ins = 0.0
    else:
        layer = 'F.Fab' if body == 'fab' else 'F.CrtYd'
        pts = outline_pts(fp, layer)
        ins = 0.0 if body == 'fab' else inset
        if not pts:
            raise SystemExit('the footprint has no %s outline - use --body pads or another --body' % layer)
    x0, x1 = min(p[0] for p in pts) + ins, max(p[0] for p in pts) - ins
    y0, y1 = min(p[1] for p in pts) + ins, max(p[1] for p in pts) - ins
    boxes = [{'name': 'body', 'color': color, 'x': [x0, x1], 'y': [y0, y1], 'z': [standoff, height]}]
    return boxes + pad_boxes(fp, standoff, pin_len)


# ------------------------------------------------------------------ footprint model assignment (text edit)
def assign(fp_path, model_path):
    txt = open(fp_path, encoding='utf-8').read()
    base = os.path.basename(model_path)
    blocks = []
    i = 0
    while True:
        j = txt.find('(model ', i)
        if j < 0:
            break
        depth, k = 0, j
        while True:
            if txt[k] == '(':
                depth += 1
            elif txt[k] == ')':
                depth -= 1
                if depth == 0:
                    break
            k += 1
        blocks.append((j, k + 1))
        i = k + 1
    new = ('(model "%s"\n\t\t(offset\n\t\t\t(xyz 0 0 0)\n\t\t)\n\t\t(scale\n\t\t\t(xyz 1 1 1)\n\t\t)\n'
           '\t\t(rotate\n\t\t\t(xyz 0 0 0)\n\t\t)\n\t)' % model_path)
    stem = re.sub(r'\.(step|stp|wrl)$', '', base, flags=re.I)
    same = [(a, b) for a, b in blocks if stem in txt[a:b]]
    if same:
        a, b = same[0]
        txt = txt[:a] + new + txt[b:]
        what = 'replaced'
    else:
        end = txt.rstrip().rfind(')')
        ef = txt.rfind('(embedded_fonts', 0, end)
        at = ef if ef > 0 else end
        ls = txt.rfind('\n', 0, at) + 1
        txt = txt[:ls] + '\t' + new + '\n' + txt[ls:]
        what = 'added'
    open(fp_path, 'w', encoding='utf-8', newline='\n').write(txt)
    return what


def opt(a, n, d=None):
    return a[a.index(n) + 1] if n in a else d


def main():
    a = sys.argv[1:]
    if len(a) < 2 or a[0] not in ('spec', 'footprint'):
        print(__doc__)
        return 2
    out = opt(a, '--out') or '.'
    os.makedirs(out, exist_ok=True)
    note = ''
    if a[0] == 'spec':
        spec = json.load(open(a[1], encoding='utf-8'))
        name, boxes = spec['name'], spec['boxes']
        note = spec.get('note', 'boxes from the datasheet drawing')
        fp_file = opt(a, '--assign')
    else:
        fp_file = a[1]
        fp = parse(open(fp_file, encoding='utf-8').read())
        if opt(a, '--height') is None:
            raise SystemExit('--height H (mm, from the datasheet) is required')
        col = tuple(float(v) for v in opt(a, '--body-color', '0.15,0.15,0.15').split(','))
        boxes = from_footprint(fp, float(opt(a, '--height')), opt(a, '--body', 'fab'), float(opt(a, '--standoff', '0')),
                               float(opt(a, '--inset', '0.25')), float(opt(a, '--pin-length', '3.0')), col)
        name = fp[1]
        note = 'body %s outline, height %s mm; pins from the pads' % (opt(a, '--body', 'fab'), opt(a, '--height'))
    for b in boxes:
        for k in ('x', 'y', 'z'):
            if abs(b[k][1] - b[k][0]) < 1e-6:
                raise SystemExit('box %s has zero %s extent' % (b.get('name'), k))
    stem = name if name.endswith('_approx') else name + '_approx'
    base = os.path.join(out, stem)
    write_step(base + '.step', stem, boxes, note)
    write_wrl(base + '.wrl', boxes)
    zs = [z for b in boxes for z in b['z']]
    print('written %s.step / .wrl: %d boxes, z %.2f .. %.2f mm' % (base, len(boxes), min(zs), max(zs)))
    if fp_file and ('--assign' in a):
        mp = opt(a, '--model-path') or '${KIPRJMOD}/%s/%s.step' % (os.path.basename(os.path.abspath(out)), stem)
        print('%s: model %s (%s)' % (fp_file, mp, assign(fp_file, mp)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
