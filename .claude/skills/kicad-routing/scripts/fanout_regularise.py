#!/usr/bin/env python
"""fanout_regularise.py - align the first bends of an IC fan-out on one line per side (lesson L22, ServiceOne review
issue 19). MUST be run with KiCad's own Python (it imports pcbnew).

Vladimir's corrected U1: every pin leaves straight along its axis, the tracks of one side bend on one line, and the
parallel runs after the bend are equally spaced. With equal pin pitch and the same bend angle the spacing follows from
the alignment, so the tool moves only the first bend.

Groups are the audit's (kicad_audit.js section 31): per pad row of a U*/IC* part (as section 26), the tracks that
leave a pin straight along the outward axis and then bend the same way, on the same layer. For a group the target bend
distance D (from the pad centres) is the largest current one, never less than pad edge + 0.5 mm (L11). Each track is
edited in place:
    pad centre -> v1 (axial)  ->  v2 (bend run, direction d)  ->  v3 (next run, direction e)
    v1' = pad centre + D along the axis; v2' = where the line from v1' along d meets the line v2-v3.
So every segment keeps its direction (the 45-degree lattice holds) and the far vertex v3 does not move. A track whose
v1 or v2 joins anything else (a via, a pad, a branch), or whose v2' would reverse a segment or leave it shorter than
0.1 mm, cannot slide. Smaller target D values are tried when the largest one fails. When no slide works, the group's
pins are re-routed with route_finish.py --refinish --refinish-force: every new entry is an axial stub to pad edge
+ 0.5 mm, so the first bends align there.

Every group is GATED: the board is saved; KiCad DRC (error + unconnected count), the audit's FAIL count and its
fan-out WARN count must not rise, and the FAIL or the WARN count must fall; otherwise the board bytes are restored.

  fanout_regularise.py <board> --list [--refs U1,U4]          read-only: groups, bend distances, spread
  fanout_regularise.py <board> --apply [--refs U1,U4] [--params F] [--force-write]
The board needs its .kicad_pro beside it and no KiCad lock (board_guard). Locked tracks are not moved.
"""
import json
import math
import os
import re
import subprocess
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import kicad_sexp as KS  # noqa: E402

M = pcbnew.ToMM
FM = lambda v: int(round(v * 1e6))
args = sys.argv[1:]
if not args or args[0].startswith('-') or not ({'--list', '--apply'} & set(args)):
    print(__doc__)
    sys.exit(2)


def opt(n, d=None):
    return args[args.index(n) + 1] if n in args else d


PCB = os.path.abspath(args[0])
APPLY = '--apply' in args
REFS = set(opt('--refs').split(',')) if opt('--refs') else None
if APPLY:
    import board_guard
    board_guard.check_board_writable(PCB, argv=args[1:], script='fanout_regularise.py')


def same(a, b):
    return abs(a.x - b.x) <= 1000 and abs(a.y - b.y) <= 1000


def size(p):
    try:
        s = p.GetSize(pcbnew.F_Cu)
    except TypeError:
        s = p.GetSize()
    return M(s.x), M(s.y)


def groups(b):
    """[{ref, row, layer, items: [{pad, segs: (s0, s1, s2), u, c, D, reach}]}] as audit section 31."""
    import pad_row_keepouts as PRK
    tr = [t for t in b.GetTracks() if t.Type() == pcbnew.PCB_TRACE_T]
    vias = [t.GetPosition() for t in b.GetTracks() if t.Type() == pcbnew.PCB_VIA_T]
    allpads = [p for f in b.GetFootprints() for p in f.Pads()]
    at = {}
    for t in tr:
        for e in (t.GetStart(), t.GetEnd()):
            at.setdefault((e.x // 1000, e.y // 1000), []).append(t)

    def touching(pt, layer, exclude):
        out = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for t in at.get((pt.x // 1000 + dx, pt.y // 1000 + dy), []):
                    if t not in exclude and t.GetLayer() == layer and (same(t.GetStart(), pt) or same(t.GetEnd(), pt)) \
                            and t not in out:
                        out.append(t)
        return out

    def far(t, pt):            # a COPY: GetStart / GetEnd are live references that follow later edits
        q = t.GetEnd() if same(t.GetStart(), pt) else t.GetStart()
        return pcbnew.VECTOR2I(q.x, q.y)

    def blocked(pt, own=None):
        ou = own.m_Uuid.AsString() if own is not None else None      # SWIG proxies are not identical objects
        return any(same(v, pt) for v in vias) or any(q.HitTest(pt) for q in allpads if q.m_Uuid.AsString() != ou)
    out = []
    for bd in PRK.bands(b, refs=REFS):
        fp = b.FindFootprintByReference(bd['ref'])
        pads = {p.GetNumber(): p for p in fp.Pads()}
        # outward unit vector of the row, board frame: from the inner band edge to the outer one
        (x0, y0), (x1, y1) = bd['poly'][0], bd['poly'][1]
        L = math.hypot(x1 - x0, y1 - y0)
        u = ((x1 - x0) / L, (y1 - y0) / L)
        grp = {}
        for num in bd['pins']:
            p = pads[num]
            c = pcbnew.VECTOR2I(p.GetPosition().x, p.GetPosition().y)
            w, h = size(p)
            for s0 in touching(c, p.GetLayer() if p.GetAttribute() == pcbnew.PAD_ATTRIB_SMD else p.GetLayer(), []):
                if s0.GetNetname() != p.GetNetname() or s0.IsLocked():
                    continue
                v1 = far(s0, c)
                dx, dy = M(v1.x - c.x), M(v1.y - c.y)
                D = dx * u[0] + dy * u[1]
                if D <= 0 or abs(dx * u[1] - dy * u[0]) > 1e-3 or blocked(v1, p):
                    continue
                n1 = touching(v1, s0.GetLayer(), [s0])
                if len(n1) != 1 or n1[0].IsLocked():
                    continue
                s1 = n1[0]
                v2 = far(s1, v1)
                d = (M(v2.x - v1.x), M(v2.y - v1.y))
                ld = math.hypot(*d)
                if ld < 1e-6 or abs(d[0] * u[1] - d[1] * u[0]) < 1e-6:
                    continue                                     # no bend
                dn = (d[0] / ld, d[1] / ld)
                key = (s0.GetLayer(), round(dn[0], 3), round(dn[1], 3))
                n2 = [] if blocked(v2) else touching(v2, s0.GetLayer(), [s1])
                s2 = n2[0] if len(n2) == 1 and not n2[0].IsLocked() else None
                reach = (abs(u[0]) * w / 2 + abs(u[1]) * h / 2) if round(p.GetOrientationDegrees()) % 180 == 0 \
                    else (abs(u[0]) * h / 2 + abs(u[1]) * w / 2)
                grp.setdefault(key, []).append(dict(pad=p, num=num, segs=(s0, s1, s2), u=u, c=c, D=D, reach=reach,
                                                    v1=v1, v2=v2, d=dn))
        for (layer, _, _), items in grp.items():
            if len(items) >= 2:
                out.append(dict(ref=bd['ref'], row=bd['n'], layer=b.GetLayerName(layer), items=items))
    return out


def plan(g, D):
    """New (v1', v2') for each track of group g at bend distance D, or a reason string."""
    moves = []
    for it in g['items']:
        s0, s1, s2 = it['segs']
        c, u, d = it['c'], it['u'], it['d']
        if abs(it['D'] - D) < 1e-4:
            moves.append(None)
            continue
        if s2 is None:
            return 'pin %s: the bend run ends at a via, a pad or a branch' % it['num']
        nv1 = (M(c.x) + u[0] * D, M(c.y) + u[1] * D)
        v2 = it['v2']
        v3 = s2.GetEnd() if same(s2.GetStart(), v2) else s2.GetStart()
        v3 = pcbnew.VECTOR2I(v3.x, v3.y)
        e = (M(v3.x - v2.x), M(v3.y - v2.y))
        den = d[0] * e[1] - d[1] * e[0]
        if abs(den) < 1e-9:
            return 'pin %s: the run after the bend is parallel to it' % it['num']
        # nv1 + t d = v2 + k e
        rx, ry = M(v2.x) - nv1[0], M(v2.y) - nv1[1]
        t = (rx * e[1] - ry * e[0]) / den
        k = (rx * d[1] - ry * d[0]) / den
        nv2 = (nv1[0] + t * d[0], nv1[1] + t * d[1])
        len3 = math.hypot(M(v3.x) - nv2[0], M(v3.y) - nv2[1])
        if t < 0.1 or len3 < 0.1 or ((M(v3.x) - nv2[0]) * e[0] + (M(v3.y) - nv2[1]) * e[1]) <= 0:
            return 'pin %s: moving the bend would reverse or shrink a segment' % it['num']
        moves.append((nv1, nv2))
    return moves


def apply_moves(g, moves):
    for it, mv in zip(g['items'], moves):
        if mv is None:
            continue
        s0, s1, s2 = it['segs']
        (a1, b1), (a2, b2) = mv
        P1, P2 = pcbnew.VECTOR2I(FM(a1), FM(b1)), pcbnew.VECTOR2I(FM(a2), FM(b2))
        v1, v2 = it['v1'], it['v2']
        e0 = same(s0.GetEnd(), v1)                  # decide every end before moving any of them
        st1 = same(s1.GetStart(), v1)
        st2 = same(s2.GetStart(), v2)
        (s0.SetEnd if e0 else s0.SetStart)(P1)
        if st1:
            s1.SetStart(P1)
            s1.SetEnd(P2)
        else:
            s1.SetEnd(P1)
            s1.SetStart(P2)
        (s2.SetStart if st2 else s2.SetEnd)(P2)


def worse(now, base):
    """Gate: nothing may rise (DRC errors + unconnected, audit FAIL, fan-out WARN) and FAIL or the WARN must fall."""
    return now[0] > base[0] or now[1] > base[1] or now[2] > base[2] or (now[1] == base[1] and now[2] == base[2])


def counts():
    KP_CLI = KS.find_kicad_cli()
    j = PCB + '.fo_drc.json'
    subprocess.run([KP_CLI, 'pcb', 'drc', '--format', 'json', '-o', j, PCB], capture_output=True)
    d = json.load(open(j, encoding='utf-8'))
    drc = sum(1 for v in d['violations'] if v['severity'] == 'error') + len(d.get('unconnected_items', []))
    ja = PCB + '.fo_audit.json'
    params = opt('--params') or os.path.join(os.path.dirname(PCB), 'kicad_golden.project.json')
    cmd = ['node', os.path.join(HERE, 'kicad_audit.js'), PCB, '--no-sch', '--quiet', '--json', ja]
    if os.path.isfile(params):
        cmd[3:3] = ['--params', params]
    subprocess.run(cmd, capture_output=True)
    a = json.load(open(ja, encoding='utf-8'))
    for f in (j, ja):
        os.remove(f)
    return drc, a['summary'].get('FAIL', 0), sum(1 for f in a['findings'] if f['check'] == 'fan-out')


b = pcbnew.LoadBoard(PCB)
gs = groups(b)
for g in gs:
    Ds = [it['D'] for it in g['items']]
    print('  %-6s row %d %s: pins %s, bends %.3f..%.3f mm (spread %.3f)' % (
        g['ref'], g['row'], g['layer'], ','.join(it['num'] for it in g['items']), min(Ds), max(Ds), max(Ds) - min(Ds)))
todo = [g for g in gs if max(it['D'] for it in g['items']) - min(it['D'] for it in g['items']) > 0.1 + 1e-6]
_pp = opt('--params') or os.path.join(os.path.dirname(PCB), 'kicad_golden.project.json')
_kel = set()
if os.path.isfile(_pp):            # Kelvin sense / shunt pads (layout_checks.kelvin) are never re-laid by this tool
    for k in (json.load(open(_pp, encoding='utf-8')).get('layout_checks') or {}).get('kelvin') or []:
        _kel |= {k.get('sense'), k.get('shunt')}
for g in [g for g in todo if any('%s.%s' % (g['ref'], it['num']) in _kel for it in g['items'])]:
    print('  %s row %d %s: holds a Kelvin pad - left' % (g['ref'], g['row'], g['layer']))
    todo.remove(g)
print('%d fan-out group(s), %d with bends more than 0.1 mm apart' % (len(gs), len(todo)))
if not APPLY:
    sys.exit(0)
base = counts()
print('start: DRC errors + unconnected %d, audit FAIL %d, fan-out WARN %d' % base)
kept = 0
for g0 in todo:
    tag = '%s row %d %s' % (g0['ref'], g0['row'], g0['layer'])
    Ds = sorted({round(it['D'], 4) for it in g0['items']}, reverse=True)
    floor = max(it['reach'] + 0.5 for it in g0['items'])
    done = False
    for D in [x for x in Ds if x >= floor - 1e-6] or [floor]:
        b = pcbnew.LoadBoard(PCB)
        g = next((x for x in groups(b) if (x['ref'], x['row'], x['layer']) == (g0['ref'], g0['row'], g0['layer'])
                  and len(x['items']) == len(g0['items'])), None)
        if g is None:
            break
        mv = plan(g, D)
        if isinstance(mv, str):
            print('  %-22s D %.3f: left (%s)' % (tag, D, mv))
            continue
        bak = open(PCB, 'rb').read()
        apply_moves(g, mv)
        b.Save(PCB)
        now = counts()
        if worse(now, base):
            open(PCB, 'wb').write(bak)
            print('  %-22s D %.3f: REVERTED (DRC %d, FAIL %d, fan-out WARN %d)' % ((tag, D) + now))
            continue
        base = now
        kept += 1
        done = True
        print('  %-22s D %.3f: kept (DRC %d, FAIL %d, fan-out WARN %d)' % ((tag, D) + now))
        break
    if not done:                      # fallback: re-route every pin of the group with an axial stub (route_finish.py
        b = pcbnew.LoadBoard(PCB)       # --refinish --refinish-force): all first bends land at pad edge + 0.5 mm
        g = next((x for x in groups(b) if (x['ref'], x['row'], x['layer']) == (g0['ref'], g0['row'], g0['layer'])), None)
        bak = open(PCB, 'rb').read()
        why = None
        for it in (g['items'] if g else []):
            if abs(it['D'] - (it['reach'] + 0.5)) < 0.01:
                continue
            r = subprocess.run([sys.executable, os.path.join(HERE, 'route_finish.py'), PCB, '--refinish',
                                '%s.%s' % (g0['ref'], it['num']), '--refinish-force', '--grid', '0.05', '--safety', '0.05']
                               + (['--force-write'] if '--force-write' in args else []),
                               capture_output=True, text=True, encoding='utf-8', errors='replace',
                               env=dict(os.environ, MSYS_NO_PATHCONV='1'))
            if r.returncode:
                why = 'pin %s: %s' % (it['num'], ([l for l in r.stderr.splitlines() if l.strip() and 'leak' not in l] or ['?'])[-1][:110])
                break
        if g is None or why:
            open(PCB, 'wb').write(bak)
            print('  %-22s re-route: left (%s)' % (tag, why or 'group not found'))
        else:
            now = counts()
            if worse(now, base):
                open(PCB, 'wb').write(bak)
                print('  %-22s re-route: REVERTED (DRC %d, FAIL %d, fan-out WARN %d)' % ((tag,) + now))
            else:
                base = now
                kept += 1
                done = True
                print('  %-22s re-route with axial stubs: kept (DRC %d, FAIL %d, fan-out WARN %d)' % ((tag,) + now))
    if not done:
        print('  %-22s not aligned' % tag)
if kept:
    import zone_fill_check
    b = pcbnew.LoadBoard(PCB)
    zone_fill_check.refill(b)
    b.Save(PCB)
print('end: %d of %d group(s) improved; DRC %d, audit FAIL %d, fan-out WARN %d' % ((kept, len(todo)) + base))
