#!/usr/bin/env python
"""layout_measure.py - measure a routed board against datasheet layout rules (kicad-routing 1.19.0).

MUST be run with KiCad's own Python (it imports pcbnew). Read-only: zones are filled in memory, nothing is saved.

    layout_measure.py path   <board> REF.PAD REF.PAD [--no-plane]
    layout_measure.py return <board> REF.PAD [REF.PAD ...]
    layout_measure.py kelvin <board> SENSE SHUNT LOAD [--oz 1]
    layout_measure.py gap    <board> --a NET,NET --b NET,NET [--exempt X,Y,R] [--max 1.0]
    layout_measure.py check  <board> [--params kicad_golden.project.json] [--json out.json] [--pre-route]

WHY THIS EXISTS. DRC proves clearances and connectivity; it says nothing about the layout sections of the
datasheets: "decoupling capacitor as close as possible", "Kelvin connection to the shunt", "route digital
traces away from the analog inputs". On ServiceOne (2026-10-05) a DRC-clean, audit-reviewed board still had:
  * both INA226 sense inputs tapping the power track 8 mm and 58 mm away from the shunt pads - an estimated
    +20 % and +47 % current error. Same net, so DRC cannot see it;
  * an 8.192 MHz ADC clock 0.11 mm from a 24-bit input over 10 mm;
  * output and decoupling capacitors reached only through the plane (2 vias) although 2 mm away.
Straight-line distance hides all three. This tool follows the copper.

WHAT IT MEASURES. A per-net graph of pads, track ends, vias and the inner-plane zones of that net. Tracks are
edges with their length; T-junctions, vias inside pads and vias / pads inside a filled zone of the net are
joined (a plane hop costs its straight-line distance and is reported as plane-<layer>).
  path     shortest routed path between two pads: length, vias, layers used (--no-plane: surface only)
  return   from a pad to its nearest via or plane connection (the return / stitching length)
  kelvin   SENSE = monitor input pad, SHUNT = shunt pad on that net, LOAD = a pad the load current reaches
           through the shunt pad. Reports the copper shared by SENSE->SHUNT and SHUNT->LOAD (it carries load
           current, so its resistance adds to the shunt) and whether SENSE reaches LOAD without the SHUNT pad
           (a parallel current path through the sense trace). PASS = 0 mm shared and no bypass.
  gap      smallest same-layer edge-to-edge gap between the tracks of two net groups, the parallel length
           closer than --max, and where. F.Cu and B.Cu do not couple through the inner planes; only same-layer
           pairs count. --exempt X,Y,R ignores the area around the IC's own pins.
  check    runs the project's `layout_checks` block (kicad_golden.project.json, written by init_project.py):
             "kelvin":     [{"sense": "U13.10", "shunt": "R57.1", "load": "D3.1"}]
             "decoupling": [{"pin": "U1.19", "cap": "C1.1", "max_mm": 3.0, "surface": true}]
             "separation": [{"a": ["/ADC_AIN1P"], "b": ["CLKIN"], "min_mm": 0.5, "exempt": [x, y, r]}]
           Exit 1 when any check fails. Every list starts empty - the entries are design decisions.
Resistance estimates use 0.49 mOhm per square for 1 oz (35 um) copper and ignore vias: they are lower bounds.
"""
import heapq
import json
import math
import os
import sys

try:
    import pcbnew
except ImportError:
    sys.stderr.write('layout_measure.py needs KiCad\'s Python (pcbnew)\n')
    sys.exit(2)

M = pcbnew.ToMM


def die(msg, code=2):
    sys.stderr.write(msg + '\n')
    sys.exit(code)


class Board:
    def __init__(self, path):
        self.b = pcbnew.LoadBoard(path)
        pcbnew.ZONE_FILLER(self.b).Fill(self.b.Zones())
        self.cu = [l for l in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.In3_Cu, pcbnew.In4_Cu, pcbnew.B_Cu)
                   if self.b.IsLayerEnabled(l)]
        self.ln = {l: self.b.GetLayerName(l) for l in self.cu}
        self._g = {}

    def pad(self, tag):
        ref, num = tag.split('.', 1)
        fp = self.b.FindFootprintByReference(ref)
        if fp is None:
            die('no footprint ' + ref)
        for p in fp.Pads():
            if p.GetNumber() == num:
                return p
        die('no pad ' + tag)

    def tracks(self, net=None):
        return [t.Cast() for t in list(self.b.GetTracks()) if net is None or t.GetNetname() == net]

    # ------------------------------------------------------------ connectivity graph of one net
    def graph(self, net):
        if net in self._g:
            return self._g[net]
        nodes, adj = {}, {}

        def node(k, x, y, kind, label=''):
            if k not in nodes:
                nodes[k] = (x, y, kind, label)
                adj[k] = []
            return k

        def edge(a, c, w, kind):
            adj[a].append((c, w, kind))
            adj[c].append((a, w, kind))

        pads = [(f, p) for f in self.b.GetFootprints() for p in f.Pads() if p.GetNetname() == net]
        items = self.tracks(net)
        vias = [t for t in items if t.Type() == pcbnew.PCB_VIA_T]
        segs = [t for t in items if t.Type() != pcbnew.PCB_VIA_T]
        for f, p in pads:
            q = p.GetPosition()
            node(('P', f.GetReference(), p.GetNumber()), M(q.x), M(q.y), 'pad', '%s.%s' % (f.GetReference(), p.GetNumber()))
        for v in vias:
            q = v.GetPosition()
            node(('V', q.x, q.y), M(q.x), M(q.y), 'via')
        # every segment is split at the points where another segment end or a via lands on it, so that two
        # paths running along the same copper share the same graph edges (needed by the kelvin check)
        for t in segs:
            L = t.GetLayer()
            a, c = t.GetStart(), t.GetEnd()
            pts = [(a.x, a.y), (c.x, c.y)]
            for u in segs:
                if u is t or u.GetLayer() != L:
                    continue
                for e in (u.GetStart(), u.GetEnd()):
                    if t.HitTest(e, 0):
                        pts.append((e.x, e.y))
            for v in vias:
                q = v.GetPosition()
                if t.HitTest(q, 0):
                    pts.append((q.x, q.y))
            dx, dy = c.x - a.x, c.y - a.y
            pts = sorted(set(pts), key=lambda q: (q[0] - a.x) * dx + (q[1] - a.y) * dy)
            for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
                k1 = node(('T', x1, y1, L), M(x1), M(y1), 'pt')
                k2 = node(('T', x2, y2, L), M(x2), M(y2), 'pt')
                edge(k1, k2, M(math.hypot(x2 - x1, y2 - y1)), self.ln[L])
        for t in segs:
            L = t.GetLayer()
            for e in (t.GetStart(), t.GetEnd()):
                ke = ('T', e.x, e.y, L)
                for f, p in pads:
                    if p.IsOnLayer(L) and p.HitTest(e):
                        q = p.GetPosition()
                        edge(ke, ('P', f.GetReference(), p.GetNumber()), M(math.hypot(q.x - e.x, q.y - e.y)), 'pad')
                for v in vias:
                    q = v.GetPosition()
                    if math.hypot(q.x - e.x, q.y - e.y) <= v.GetWidth(pcbnew.F_Cu) / 2:
                        edge(ke, ('V', q.x, q.y), M(math.hypot(q.x - e.x, q.y - e.y)), 'via')
        for f, p in pads:   # vias inside pads (thermal vias, via-in-pad)
            for v in vias:
                q = v.GetPosition()
                if p.HitTest(q):
                    pq = p.GetPosition()
                    edge(('P', f.GetReference(), p.GetNumber()), ('V', q.x, q.y), M(math.hypot(pq.x - q.x, pq.y - q.y)), 'via-in-pad')
        for z in self.b.Zones():   # planes / pours of this net
            if z.GetIsRuleArea() or z.GetNetname() != net:
                continue
            for L in self.cu:
                if not z.IsOnLayer(L):
                    continue
                mem = [('V', v.GetPosition().x, v.GetPosition().y) for v in vias if z.HitTestFilledArea(L, v.GetPosition())]
                mem += [('P', f.GetReference(), p.GetNumber()) for f, p in pads
                        if p.IsOnLayer(L) and z.HitTestFilledArea(L, p.GetPosition())]
                for i in range(len(mem)):
                    for j in range(i + 1, len(mem)):
                        a, c = nodes[mem[i]], nodes[mem[j]]
                        edge(mem[i], mem[j], math.hypot(a[0] - c[0], a[1] - c[1]), 'plane-' + self.ln[L])
        self._g[net] = (nodes, adj)
        return nodes, adj

    def shortest(self, net, src, dst=None, to_plane=False, no_plane=False, avoid=()):
        """Dijkstra from pad src (REF.PAD); returns (length, vias, kinds, node list) or None."""
        nodes, adj = self.graph(net)
        s = ('P',) + tuple(src.split('.', 1))
        t = ('P',) + tuple(dst.split('.', 1)) if dst else None
        if s not in nodes:
            return None
        dist, prev, h = {s: 0.0}, {}, [(0.0, s)]
        while h:
            d, u = heapq.heappop(h)
            if d > dist.get(u, 1e18):
                continue
            hit = (t is not None and u == t) or (to_plane and u != s and (
                nodes[u][2] == 'via' or any(k.startswith('plane') for _, _, k in adj[u])))
            if hit:
                seq, k = [u], u
                while k in prev:
                    k = prev[k][0]
                    seq.append(k)
                seq.reverse()
                kinds = sorted({prev[x][1] for x in seq if x in prev} - {'pad', 'via'})
                return round(d, 3), sum(1 for x in seq if nodes[x][2] == 'via'), kinds, seq
            for v, w, kind in adj[u]:
                if no_plane and kind.startswith('plane'):
                    continue
                if v in avoid:
                    continue
                if d + w < dist.get(v, 1e18):
                    dist[v] = d + w
                    prev[v] = (u, kind)
                    heapq.heappush(h, (d + w, v))
        return None

    # ------------------------------------------------------------ checks
    def kelvin(self, sense, shunt, load, oz=1.0):
        net = self.pad(sense).GetNetname()
        for tag in (shunt, load):
            if self.pad(tag).GetNetname() != net:
                die('%s is not on %s (net of %s)' % (tag, net, sense))
        ps = self.shortest(net, sense, shunt)
        pl = self.shortest(net, shunt, load)
        if ps is None or pl is None:
            return {'check': 'kelvin', 'sense': sense, 'shunt': shunt, 'load': load, 'net': net, 'pass': False,
                    'error': 'no copper path sense->shunt or shunt->load (open connection)'}
        nodes, adj = self.graph(net)

        def edges(seq):
            return {frozenset((seq[i], seq[i + 1])) for i in range(len(seq) - 1)}
        shared = edges(ps[3]) & edges(pl[3])
        length, sq = 0.0, 0.0
        segs = [t for t in self.tracks(net) if t.Type() != pcbnew.PCB_VIA_T]
        for e in shared:
            a, c = tuple(e)
            w = min((x[1] for x in adj[a] if x[0] == c), default=0.0)
            kind = [x[2] for x in adj[a] if x[0] == c][0]
            if kind in ('pad', 'via', 'via-in-pad') or kind.startswith('plane'):
                continue
            mid = pcbnew.VECTOR2I(pcbnew.FromMM((nodes[a][0] + nodes[c][0]) / 2), pcbnew.FromMM((nodes[a][1] + nodes[c][1]) / 2))
            tw = [M(t.GetWidth()) for t in segs if t.HitTest(mid, 1000)]
            length += w
            sq += w / (max(tw) if tw else 0.2)
        # the shunt pad is every node inside its copper: tracks that meet inside the pad meet AT the shunt
        sp = self.pad(shunt)
        inpad = {k for k, v in nodes.items() if (v[2] == 'pad' and v[3] == shunt) or
                 (k[0] == 'T' and sp.IsOnLayer(k[3]) and sp.HitTest(pcbnew.VECTOR2I(k[1], k[2])))}
        bypass = self.shortest(net, sense, load, avoid=inpad)
        mohm = sq * 0.49 / oz
        return {'check': 'kelvin', 'sense': sense, 'shunt': shunt, 'load': load, 'net': net,
                'sense_path_mm': ps[0], 'sense_vias': ps[1], 'shared_mm': round(length, 2),
                'shared_mohm_min': round(mohm, 2), 'bypass': bypass is not None,
                'pass': length < 0.05 and bypass is None}

    def ret(self, tag):
        net = self.pad(tag).GetNetname()
        r = self.shortest(net, tag, to_plane=True)
        return {'check': 'return', 'pad': tag, 'net': net,
                'mm': None if r is None else r[0], 'kinds': None if r is None else r[2]}

    def path(self, a, c, no_plane=False):
        net = self.pad(a).GetNetname()
        if self.pad(c).GetNetname() != net:
            die('%s and %s are on different nets' % (a, c))
        r = self.shortest(net, a, c, no_plane=no_plane)
        return {'check': 'path', 'a': a, 'b': c, 'net': net, 'surface_only': no_plane,
                'mm': None if r is None else r[0], 'vias': None if r is None else r[1],
                'kinds': None if r is None else r[2]}

    def gap(self, na, nb, exempt=None, maxd=1.0):
        A = [t for n in na for t in self.tracks(n) if t.Type() != pcbnew.PCB_VIA_T]
        Bt = [t for n in nb for t in self.tracks(n) if t.Type() != pcbnew.PCB_VIA_T]
        best, run = None, {}
        for x in A:
            s, e = x.GetStart(), x.GetEnd()
            n = max(1, int(M(x.GetLength()) / 0.1))
            for i in range(n + 1):
                px, py = s.x + (e.x - s.x) * i / n, s.y + (e.y - s.y) * i / n
                if exempt and math.hypot(M(px) - exempt[0], M(py) - exempt[1]) <= exempt[2]:
                    continue
                for y in Bt:
                    if y.GetLayer() != x.GetLayer():
                        continue
                    a, c = y.GetStart(), y.GetEnd()
                    dx, dy = c.x - a.x, c.y - a.y
                    den = dx * dx + dy * dy
                    u = 0.0 if den == 0 else max(0.0, min(1.0, ((px - a.x) * dx + (py - a.y) * dy) / den))
                    g = M(math.hypot(px - a.x - u * dx, py - a.y - u * dy)) - M(x.GetWidth() + y.GetWidth()) / 2
                    if best is None or g < best[0]:
                        best = (g, M(px), M(py), self.ln[x.GetLayer()], x.GetNetname(), y.GetNetname())
                    if g < maxd:
                        k = (x.GetNetname(), y.GetNetname())
                        run[k] = run.get(k, 0.0) + M(x.GetLength()) / n
                        break
        pairs = [{'a': k[0], 'b': k[1], 'parallel_mm': round(v, 1)} for k, v in sorted(run.items(), key=lambda kv: -kv[1])]
        return {'check': 'gap', 'min_gap_mm': None if best is None else round(best[0], 3),
                'at': None if best is None else [round(best[1], 2), round(best[2], 2), best[3], best[4], best[5]],
                'within_max': pairs}


def main():
    a = sys.argv[1:]
    if len(a) < 2 or a[0] not in ('path', 'return', 'kelvin', 'gap', 'check'):
        die(__doc__)
    cmd, brd = a[0], a[1]
    rest = a[2:]

    def opt(name, default=None):
        return rest[rest.index(name) + 1] if name in rest else default
    pos = [x for i, x in enumerate(rest) if not x.startswith('--') and (i == 0 or not rest[i - 1].startswith('--'))]
    B = Board(brd)
    out = []
    if cmd == 'path':
        out.append(B.path(pos[0], pos[1], '--no-plane' in rest))
    elif cmd == 'return':
        out += [B.ret(t) for t in pos]
    elif cmd == 'kelvin':
        out.append(B.kelvin(pos[0], pos[1], pos[2], float(opt('--oz', '1'))))
    elif cmd == 'gap':
        ex = [float(v) for v in opt('--exempt').split(',')] if opt('--exempt') else None
        out.append(B.gap(opt('--a', '').split(','), opt('--b', '').split(','), ex, float(opt('--max', '1.0'))))
    else:
        pp = opt('--params') or os.path.join(os.path.dirname(os.path.abspath(brd)), 'kicad_golden.project.json')
        lc = (json.load(open(pp, encoding='utf-8')) if os.path.isfile(pp) else {}).get('layout_checks', {})
        if '--pre-route' in rest:
            # 1.26.0 (playbook B0): before routing only the placement can be judged - the straight distance from
            # each pin to its capacitor pad must already be within max_mm (the routed length can only be longer).
            for d in lc.get('decoupling', []):
                a_, c_ = B.pad(d['pin']).GetPosition(), B.pad(d['cap']).GetPosition()
                mm_ = round(M(math.hypot(a_.x - c_.x, a_.y - c_.y)), 3)
                out.append({'check': 'decoupling-placement', 'pin': d['pin'], 'cap': d['cap'], 'straight_mm': mm_,
                            'max_mm': d['max_mm'], 'pass': mm_ <= d['max_mm'], 'why': d.get('why', '')})
            n_skip = len(lc.get('kelvin', [])) + len(lc.get('separation', []))
            if n_skip:
                print('pre-route: %d kelvin / separation check(s) need copper - they run after routing' % n_skip)
            lc = {}
        for k in lc.get('kelvin', []):
            out.append(B.kelvin(k['sense'], k['shunt'], k['load'], float(k.get('oz', 1))))
        for d in lc.get('decoupling', []):
            r = B.path(d['pin'], d['cap'], no_plane=d.get('surface', False))
            r['check'] = 'decoupling'
            r['max_mm'] = d['max_mm']
            r['pass'] = r['mm'] is not None and r['mm'] <= d['max_mm']
            out.append(r)
        for s in lc.get('separation', []):
            r = B.gap(s['a'], s['b'], s.get('exempt'), s['min_mm'])
            r['min_mm'] = s['min_mm']
            r['pass'] = r['min_gap_mm'] is None or r['min_gap_mm'] >= s['min_mm']
            out.append(r)
        if not out:
            print('layout_checks is empty in %s - nothing to check (the entries are design decisions)' % pp)
    for r in out:
        flag = '' if 'pass' not in r else ('PASS  ' if r['pass'] else 'FAIL  ')
        print(flag + json.dumps(r))
    if opt('--json'):
        json.dump(out, open(opt('--json'), 'w', encoding='utf-8'), indent=1)
    sys.exit(1 if any(r.get('pass') is False for r in out) else 0)


if __name__ == '__main__':
    main()
