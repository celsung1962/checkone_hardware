#!/usr/bin/env python
"""route_report.py - the "am I done?" metric for the kicad-routing routing workflow.

MUST be run with KiCad's own Python (it imports pcbnew):

    "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" route_report.py <board.kicad_pcb> [opts]

Answers three questions the rest of the toolchain never answered:

  1. How complete is the routing?  Connections are counted as `pads - 1` per net (the honest
     ratsnest denominator, SKILL.md), against KiCad's own unconnected count.
  2. What will fight the router before it is run?  Footprint-local clearance overrides, which
     the Specctra DSN cannot express, and long-haul nets, which autorouters starve of channels.
  3. What did the round-trip damage?  A via padstack inventory, so a diameter/drill mismatch
     is visible instead of silent.

Run it BEFORE routing (as pre-flight) and AFTER every stage.

Options:
  --json PATH        write the full report as JSON
  --span-mm N        long-haul threshold in mm (default 50)
  --stitch-mm N      a plane-net SMD pad counts as stitched if a same-net via is within N mm
                     (default 1.5)
  --quiet            machine-readable summary line only
  --fail-on-gap      exit 1 when anything blocks completion (unrouted, or a bad padstack)

Exit codes: 0 ok, 1 gap found (with --fail-on-gap) or failure, 2 usage.
"""
import os
import sys
import json
import math
from collections import defaultdict, Counter

NM = 1e6


def die(msg, code=1):
    sys.stderr.write(str(msg).rstrip() + '\n')
    sys.exit(code)


args = sys.argv[1:]
if not args or args[0].startswith('--'):
    die(__doc__, 2)
BOARD = os.path.abspath(args[0])
if not os.path.isfile(BOARD):
    die('no such board: ' + BOARD, 2)


def opt(name, default=None):
    if name in args:
        i = args.index(name)
        if i + 1 >= len(args):
            die(name + ' needs a value', 2)
        return args[i + 1]
    return default


JSON_OUT = opt('--json')
SPAN_MM = float(opt('--span-mm', '50'))
STITCH_MM = float(opt('--stitch-mm', '1.5'))
QUIET = '--quiet' in args
FAIL_ON_GAP = '--fail-on-gap' in args

try:
    import pcbnew
except ImportError as e:
    die('cannot import pcbnew (%s).\nRun this with KiCad\'s own Python, e.g.\n'
        '  "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" %s <board>'
        % (e, os.path.basename(__file__)))

b = pcbnew.LoadBoard(BOARD)
out = []


def log(s=''):
    out.append(s)


# ------------------------------------------------------------------ 1. completion
pads = defaultdict(list)
for fp in b.GetFootprints():
    for p in fp.Pads():
        n = p.GetNetname()
        if n:
            c = p.GetCenter()
            pads[n].append((c.x, c.y))

total_conn = sum(max(0, len(v) - 1) for v in pads.values())
try:
    unrouted = b.GetConnectivity().GetUnconnectedCount(True)
except Exception:
    unrouted = None

routed = (total_conn - unrouted) if unrouted is not None else None
pct = (100.0 * routed / total_conn) if (routed is not None and total_conn) else None

# per-netclass rollup
cls_of = {}
for n in pads:
    net = b.FindNet(n)
    cls_of[n] = (net.GetNetClassName() if net is not None else '') or '(none)'
cls_conn = Counter()
for n, v in pads.items():
    cls_conn[cls_of[n]] += max(0, len(v) - 1)

log('=' * 72)
log('ROUTING COMPLETION  -  %s' % os.path.basename(BOARD))
log('=' * 72)
log('  nets with pads          : %d' % len(pads))
log('  connections (pads - 1)  : %d' % total_conn)
if unrouted is None:
    log('  unrouted                : unavailable (no connectivity API)')
else:
    log('  routed                  : %d' % routed)
    log('  unrouted                : %d' % unrouted)
    log('  COMPLETION              : %.2f %%' % pct)
log('')
log('  connections per netclass:')
for k, v in sorted(cls_conn.items(), key=lambda kv: -kv[1]):
    log('     %-28s %d' % (k[:28], v))

# ------------------------------------------------------------------ 2. pre-flight hazards
log('')
log('-' * 72)
log('PRE-FLIGHT HAZARDS (these fight the router before it starts)')
log('-' * 72)

# 2a. footprint-local clearance overrides - the Specctra DSN cannot express them
overrides = []
for fp in b.GetFootprints():
    lc = fp.GetLocalClearance()
    if lc:
        overrides.append({'ref': fp.GetReference(), 'fpid': fp.GetFPIDAsString(),
                          'clearance_mm': round(lc / NM, 4), 'pads': len(list(fp.Pads()))})
overrides.sort(key=lambda d: -d['clearance_mm'])
max_local = max([d['clearance_mm'] for d in overrides], default=0.0)

log('  footprint-local clearance overrides : %d' % len(overrides))
if overrides:
    for d in overrides:
        log('     %-6s %-44s %.3f mm  (%d pads)'
            % (d['ref'], d['fpid'][:44], d['clearance_mm'], d['pads']))
    log('     >> Specctra DSN has NO per-footprint clearance field. Unless the EXPORT clearance is')
    log('        raised to at least %.3f mm, the router will undercut these footprints and every' % max_local)
    log('        violation will appear only after the import. route_freerouting.py --auto-clearance')
    log('        does this automatically.')
else:
    log('     none - the board-global clearance is the whole story')

# 2b. long-haul nets - autorouters serve short nets first and starve long ones
spans = []
for n, pts in pads.items():
    if len(pts) < 2:
        continue
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    # bbox diagonal is an adequate proxy and is O(n) rather than O(n^2)
    d = math.hypot(max(xs) - min(xs), max(ys) - min(ys)) / NM
    if d >= SPAN_MM:
        spans.append({'net': n, 'span_mm': round(d, 1), 'pads': len(pts), 'netclass': cls_of[n]})
spans.sort(key=lambda d: -d['span_mm'])
log('')
log('  long-haul nets (pad span >= %.0f mm)  : %d' % (SPAN_MM, len(spans)))
for d in spans[:15]:
    log('     %-28s %6.1f mm  %3d pads  [%s]' % (d['net'][:28], d['span_mm'], d['pads'], d['netclass'][:18]))
if spans:
    log('     >> Route these FIRST, on a bare board or by hand, so they claim their channels while')
    log('        the board is still empty. Left to the end they are the ones that stay unrouted.')

# 2c. plane stitching coverage
plane_nets = set()
for i in range(b.GetAreaCount()):
    z = b.GetArea(i)
    ls = z.GetLayerSet()
    if not z.GetIsRuleArea() and (ls.Contains(pcbnew.In1_Cu) or ls.Contains(pcbnew.In2_Cu)):
        if z.GetNetname():
            plane_nets.add(z.GetNetname())
vias = [(v.GetStart().x, v.GetStart().y, v.GetNetname())
        for v in b.GetTracks() if v.GetClass() == 'PCB_VIA']
stitch_gap = Counter()
stitch_tot = Counter()
for fp in b.GetFootprints():
    for p in fp.Pads():
        n = p.GetNetname()
        if n not in plane_nets or p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
            continue
        stitch_tot[n] += 1
        c = p.GetCenter()
        if not any(vn == n and math.hypot(vx - c.x, vy - c.y) < STITCH_MM * NM
                   for vx, vy, vn in vias):
            stitch_gap[n] += 1
log('')
log('  plane nets (inner-layer zones)      : %s' % (', '.join(sorted(plane_nets)) or 'none'))
if plane_nets:
    for n in sorted(plane_nets):
        log('     %-10s %3d SMD pads, %3d with no via within %.1f mm'
            % (n, stitch_tot[n], stitch_gap[n], STITCH_MM))
    if sum(stitch_gap.values()):
        log('     >> %d unstitched plane pads. Each is a latent unconnected item; re-run'
            % sum(stitch_gap.values()))
        log('        stitch_planes.py, and widen its search before accepting "no clear position".')

# ------------------------------------------------------------------ 3. padstack integrity
log('')
log('-' * 72)
log('VIA PADSTACK INVENTORY (a DSN/SES round-trip can scramble diameter vs drill)')
log('-' * 72)
inv = Counter()
bad = []
for v in b.GetTracks():
    if v.GetClass() != 'PCB_VIA':
        continue
    # KiCad 10 vias may carry a per-layer width. The arg-less PCB_VIA.GetWidth() trips a
    # wxWidgets assertion ("called without a layer argument") that can pop a MODAL dialog and
    # hang a headless script. Always use the layer-aware accessor.
    d = v.GetFrontWidth() if hasattr(v, 'GetFrontWidth') else v.GetWidth(pcbnew.F_Cu)
    dr = v.GetDrill()
    ann = (d - dr) / 2.0
    inv['%.3f/%.3f' % (d / NM, dr / NM)] += 1
    if ann <= 0:
        c = v.GetStart()
        bad.append({'at': [round(c.x / NM, 4), round(c.y / NM, 4)], 'net': v.GetNetname(),
                    'diameter_mm': round(d / NM, 4), 'drill_mm': round(dr / NM, 4),
                    'annular_mm': round(ann / NM, 4)})
for k, n in sorted(inv.items()):
    dia, dr = (float(x) for x in k.split('/'))
    log('     %-14s x%-4d annular %+.4f mm %s' % (k, n, (dia - dr) / 2, '<< INVALID' if dia <= dr else ''))
if bad:
    log('')
    log('  !! %d via(s) have a hole at least as large as their own pad. This is the signature of a' % len(bad))
    log('     corrupted SES import - do not ship this board; restore the pre-import backup.')
    for d in bad[:8]:
        log('     %s %s dia %.3f drill %.3f' % (d['net'][:18], d['at'], d['diameter_mm'], d['drill_mm']))

# ------------------------------------------------------------------ verdict
blockers = []
if unrouted:
    blockers.append('%d unrouted connection(s)' % unrouted)
if bad:
    blockers.append('%d invalid via padstack(s)' % len(bad))
if sum(stitch_gap.values()):
    blockers.append('%d unstitched plane pad(s)' % sum(stitch_gap.values()))

log('')
log('=' * 72)
if blockers:
    log('NOT COMPLETE: ' + '; '.join(blockers))
else:
    log('COMPLETE: every connection routed, every plane pad stitched, all padstacks valid')
log('=' * 72)

report = {
    'board': os.path.basename(BOARD),
    'connections_total': total_conn,
    'connections_routed': routed,
    'unrouted': unrouted,
    'completion_pct': round(pct, 2) if pct is not None else None,
    'connections_per_netclass': dict(cls_conn),
    'local_clearance_overrides': overrides,
    'max_local_clearance_mm': max_local,
    'long_haul_nets': spans,
    'plane_nets': sorted(plane_nets),
    'plane_pads_total': dict(stitch_tot),
    'plane_pads_unstitched': dict(stitch_gap),
    'via_inventory': dict(inv),
    'invalid_padstacks': bad,
    'blockers': blockers,
}
if JSON_OUT:
    with open(JSON_OUT, 'w') as f:
        json.dump(report, f, indent=1)

if QUIET:
    print('completion=%s%% unrouted=%s unstitched=%d invalid_vias=%d'
          % (report['completion_pct'], unrouted, sum(stitch_gap.values()), len(bad)))
else:
    print('\n'.join(out))
    if JSON_OUT:
        print('\njson: %s' % JSON_OUT)

sys.exit(1 if (FAIL_ON_GAP and blockers) else 0)
