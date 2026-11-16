#!/usr/bin/env python
"""netclass_propose.py - derive netclasses from THIS board's netlist.

MUST be run with KiCad's own Python (it imports pcbnew):

    "<kicad>/bin/python" netclass_propose.py <board.kicad_pcb> [--apply] [--json F]

Why this exists: a settings template carries the netclass patterns of the board it was
captured from. Applied to a different design those patterns match nothing, while the new
board's own power rails silently resolve to Default and route at signal width. Nothing
fails - the board is simply manufactured with under-sized power copper.

This proposes patterns from the pads that are actually on the board:

  * POWER_DC   - current-carrying rails: a name that looks like a supply or a ground,
                 carrying at least --min-pads pads.
  * (reported) - rails that look like supplies but are clearly sense/feedback taps. These
                 carry no current and must stay on Default; they are listed, never assigned.
  * (reported) - candidate bus groups (shared prefix, >= --bus-min members), listed for a
                 human to name. Buses are a routing decision, not a naming one, so they are
                 never auto-assigned.

Nothing is written without --apply. With --apply the patterns are merged into the
.kicad_pro, existing patterns are kept, and duplicates are skipped.

Options:
  --apply         write the proposed patterns into <board>.kicad_pro
  --min-pads N    minimum pads for a rail to count as POWER_DC (default 3)
  --bus-min N     minimum members for a bus group to be reported (default 4)
  --json PATH     write the proposal as JSON
  --quiet         summary line only

Exit codes: 0 ok, 1 unclassed power rails remain (without --apply), 2 usage.
"""
import io
import os
import re
import sys
import json
from collections import defaultdict, Counter


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


APPLY = '--apply' in args
MIN_PADS = int(opt('--min-pads', '3'))
BUS_MIN = int(opt('--bus-min', '4'))
JSON_OUT = opt('--json')
QUIET = '--quiet' in args

try:
    import pcbnew
except ImportError as e:
    die("cannot import pcbnew (%s). Run this with KiCad's own Python." % e)

# ---------------------------------------------------------------- heuristics
# A supply rail: +3V3, 3.3V, VCC, VDD, VBAT, VBUS, VSYS, VIN, AVDD ... or a ground.
# The separator class must include + and - : rails are very often written "+VSYS", "+BATT",
# "-12V". Requiring ^ or _ alone silently misses them, and a missed rail is the exact failure
# this script exists to prevent.
SEP = r'(?: ^ | [_/+-] )'
END = r'(?: $ | [_0-9] )'
SUPPLY = re.compile(r'''(?ix)
    ^ [+-]? \d+ (?: [.pv] \d+ )? v \d* $      # +3.3V  3V3  5V  +24V  1V8
  | ''' + SEP + r'''
    (?: vcc | vdd | vss | vee | vbus | vsys | vin | vout | vref
      | vbat | batt | bat | vbatt
      | avdd | dvdd | avcc | dvcc | vdda | vddd | vddio | vcore | vpp )
    ''' + END + '''
''')
GROUND = re.compile(r'(?ix) ' + SEP + r' (?: gnd | agnd | dgnd | pgnd | vss | earth ) ' + END)

# Looks like a rail but carries no current: a divider tap, a feedback pin, a monitor line.
# On the reference board 24V_SENSE and SOLAR_SENSE matched the supply pattern and would have
# been widened to 0.6 mm for no reason; they are measurement taps.
SENSE = re.compile(r'''(?ix)
    (?:^|[_/]) (?: sense | sns | fb | feedback | adj | div | mon | monitor
                 | meas | detect | det | ok | pg | pgood | por | test | tp ) (?: $ | [_0-9] )
''')


def classify(name):
    """-> 'power' | 'sense' | None"""
    if not name:
        return None
    if SENSE.search(name):
        return 'sense'
    if GROUND.search(name) or SUPPLY.search(name):
        return 'power'
    return None


def bus_key(name):
    """Strip a trailing index so D0..D7 group as D. Returns None when there is no index."""
    m = re.match(r'^(.*?[A-Za-z_])(\d{1,2})$', name)
    return m.group(1) if m else None


# ---------------------------------------------------------------- gather
board = pcbnew.LoadBoard(BOARD)
pads = Counter()
for fp in board.GetFootprints():
    for p in fp.Pads():
        n = p.GetNetname()
        if n:
            pads[n] += 1

cls_of = {}
for n in pads:
    net = board.FindNet(n)
    cls_of[n] = (net.GetNetClassName() if net is not None else '') or '(none)'


def on_default(name):
    """A net is unclassed when every class it resolves to is Default/none."""
    parts = [p.strip() for p in cls_of.get(name, '').split(',')]
    return all(p in ('Default', '(none)', '') for p in parts)


power, sense, skipped_small = [], [], []
for n, c in sorted(pads.items(), key=lambda kv: -kv[1]):
    kind = classify(n)
    if kind == 'sense':
        sense.append((n, c))
    elif kind == 'power':
        (power if c >= MIN_PADS else skipped_small).append((n, c))

buses = defaultdict(list)
for n in pads:
    if classify(n):
        continue
    k = bus_key(n)
    if k:
        buses[k].append(n)
buses = {k: sorted(v) for k, v in buses.items() if len(v) >= BUS_MIN}

unclassed_power = [(n, c) for n, c in power if on_default(n)]

# ---------------------------------------------------------------- report
out = []
out.append('=' * 72)
out.append('NETCLASS PROPOSAL  -  %s' % os.path.basename(BOARD))
out.append('=' * 72)
out.append('  nets with pads: %d' % len(pads))
out.append('')
out.append('  POWER_DC candidates (>= %d pads):' % MIN_PADS)
if power:
    for n, c in power:
        out.append('     %-28s %4d pads   currently: %-22s %s'
                   % (n[:28], c, cls_of.get(n, '?')[:22], '<< UNCLASSED' if on_default(n) else ''))
else:
    out.append('     none found')
if skipped_small:
    out.append('')
    out.append('  supply-like but under %d pads (left on Default):' % MIN_PADS)
    for n, c in skipped_small:
        out.append('     %-28s %4d pads' % (n[:28], c))
if sense:
    out.append('')
    out.append('  sense / feedback taps - NOT assigned, they carry no current:')
    for n, c in sense:
        out.append('     %-28s %4d pads' % (n[:28], c))
if buses:
    out.append('')
    out.append('  candidate bus groups (>= %d members) - name and assign these yourself:' % BUS_MIN)
    for k, v in sorted(buses.items(), key=lambda kv: -len(kv[1])):
        out.append('     %-24s %2d nets   e.g. %s' % (k + '*', len(v), ', '.join(v[:4])))

out.append('')
if unclassed_power:
    out.append('  !! %d current-carrying rail(s) resolve to Default and would route at signal'
               % len(unclassed_power))
    out.append('     width. This is the failure the netclass template cannot catch for you.')
else:
    out.append('  every current-carrying rail already resolves to a power netclass')

proposal = [{'pattern': n, 'netclass': 'POWER_DC'} for n, _c in power]

# ---------------------------------------------------------------- apply
written = 0
if APPLY:
    pro = os.path.splitext(BOARD)[0] + '.kicad_pro'
    if not os.path.isfile(pro):
        die('no .kicad_pro next to the board; cannot apply')
    with io.open(pro, encoding='utf-8') as f:
        proj = json.load(f)
    ns = proj.setdefault('net_settings', {})
    pats = ns.setdefault('netclass_patterns', [])
    have = {(p.get('pattern'), p.get('netclass')) for p in pats}
    names = {c.get('name') for c in ns.get('classes', [])}
    if 'POWER_DC' not in names:
        die('the project has no POWER_DC netclass; run apply_settings.js first')
    for p in proposal:
        if (p['pattern'], p['netclass']) not in have:
            pats.append(dict(p))
            written += 1
    with io.open(pro, 'w', encoding='utf-8') as f:
        f.write(json.dumps(proj, indent=2))
    out.append('')
    out.append('  APPLIED: %d pattern(s) added to %s' % (written, os.path.basename(pro)))
    out.append('  (existing patterns kept; re-run the audit to confirm)')

report = {
    'board': os.path.basename(BOARD),
    'power_rails': [{'net': n, 'pads': c, 'unclassed': on_default(n)} for n, c in power],
    'sense_taps': [{'net': n, 'pads': c} for n, c in sense],
    'small_supplies': [{'net': n, 'pads': c} for n, c in skipped_small],
    'bus_candidates': {k: v for k, v in buses.items()},
    'unclassed_power': [n for n, _c in unclassed_power],
    'proposed_patterns': proposal,
    'applied': written,
}
if JSON_OUT:
    with io.open(JSON_OUT, 'w', encoding='utf-8') as f:
        f.write(json.dumps(report, indent=1))

if QUIET:
    print('power_rails=%d unclassed=%d sense=%d buses=%d applied=%d'
          % (len(power), len(unclassed_power), len(sense), len(buses), written))
else:
    print('\n'.join(out))
    if JSON_OUT:
        print('\njson: %s' % JSON_OUT)

sys.exit(1 if (unclassed_power and not APPLY) else 0)
