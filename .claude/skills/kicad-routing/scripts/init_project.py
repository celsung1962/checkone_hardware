#!/usr/bin/env python
"""init_project.py - seed a per-project parameter file from a REAL board.

MUST be run with KiCad's own Python (it imports pcbnew):

    "<kicad>/bin/python" init_project.py <board.kicad_pcb> --fab jlcpcb --layers 4 --copper 1oz

The shipped template is deliberately empty. A length group or via-budget pattern copied from
another design matches zero nets and then reports a clean pass while auditing nothing, so the
only safe starting point is this board's own netlist.

Writes kicad_golden.project.json next to the board containing:
  * the project name, taken from the board file
  * the fabricator profile actually chosen (name, layers, copper, captured date, kicad_rules)
  * empty length_groups / diff_pairs / via_budget, each annotated with the CANDIDATES found on
    this board so the decisions are informed rather than invented
  * silkscreen and teardrop defaults

It never guesses a length group or a via budget: those are engineering decisions. It only
shows what exists so a human can decide.

Options:
  --fab NAME       fabricator profile stem in fabricators/ (e.g. jlcpcb)
  --layers N       2, 4 or 6
  --copper 1oz|2oz
  --force          overwrite an existing kicad_golden.project.json
  --json PATH      also write the discovery report as JSON

Exit codes: 0 ok, 1 refused (file exists, unknown profile), 2 usage.
"""
import io
import os
import re
import sys
import json
from collections import defaultdict, Counter

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)


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


FAB = opt('--fab')
LAYERS = opt('--layers')
COPPER = opt('--copper')
FORCE = '--force' in args
JSON_OUT = opt('--json')

OUT = os.path.join(os.path.dirname(BOARD), 'kicad_golden.project.json')
if os.path.isfile(OUT) and not FORCE:
    die('%s already exists (use --force to overwrite)' % os.path.basename(OUT))

try:
    import pcbnew
except ImportError as e:
    die("cannot import pcbnew (%s). Run this with KiCad's own Python." % e)

board = pcbnew.LoadBoard(BOARD)

# ---------------------------------------------------------------- discovery
pads = Counter()
pts = defaultdict(list)
for fp in board.GetFootprints():
    for p in fp.Pads():
        n = p.GetNetname()
        if n:
            pads[n] += 1
            c = p.GetCenter()
            pts[n].append((c.x / 1e6, c.y / 1e6))

layer_count = board.GetCopperLayerCount()

# differential pair candidates: _P/_N or +/- siblings
dp = []
for n in pads:
    m = re.match(r'^(.*)(_P|_N|\+|-)$', n)
    if not m:
        continue
    base, suf = m.group(1), m.group(2)
    twin = base + ('_N' if suf == '_P' else '_P' if suf == '_N' else '-' if suf == '+' else '+')
    if twin in pads and base not in [d['base'] for d in dp]:
        dp.append({'base': base, 'nets': sorted([n, twin])})

# bus candidates: shared prefix with a trailing index
buses = defaultdict(list)
for n in pads:
    m = re.match(r'^(.*?[A-Za-z_])(\d{1,2})$', n)
    if m:
        buses[m.group(1)].append(n)
buses = {k: sorted(v) for k, v in buses.items() if len(v) >= 4}

# long-haul nets: the ones an autorouter starves
import math
long_haul = []
for n, p in pts.items():
    if len(p) < 2:
        continue
    xs = [q[0] for q in p]
    ys = [q[1] for q in p]
    d = math.hypot(max(xs) - min(xs), max(ys) - min(ys))
    if d >= 50:
        long_haul.append({'net': n, 'span_mm': round(d, 1), 'pads': len(p)})
long_haul.sort(key=lambda d: -d['span_mm'])

# footprint-local clearance overrides
sys.path.insert(0, HERE)
import kicad_sexp as K  # noqa: E402
overrides = [{'ref': r, 'clearance_mm': v} for r, v in K.footprint_local_clearances(BOARD)]

# ---------------------------------------------------------------- fabricator
fab_block = {'_doc': 'Fabricator capability. Manufacturer limits always win over the golden defaults.',
             'name': ''}
if FAB:
    path = os.path.join(SKILL, 'fabricators', FAB + '.json')
    if not os.path.isfile(path):
        avail = [f[:-5] for f in os.listdir(os.path.join(SKILL, 'fabricators')) if f.endswith('.json')]
        die('unknown fabricator %r; available: %s' % (FAB, ', '.join(avail) or 'none'))
    with io.open(path, encoding='utf-8') as f:
        fd = json.load(f)
    if not (LAYERS and COPPER):
        die('--fab also needs --layers and --copper', 2)
    key = '%sL-%s' % (LAYERS, COPPER)
    prof = fd.get('profiles', {}).get(key)
    if not prof:
        die('profile %s not in %s; available: %s' % (key, FAB, ', '.join(fd.get('profiles', {}))))
    fab_block = {
        '_doc': fab_block['_doc'],
        'name': '%s %s-layer %s' % (fd.get('fabricator', FAB), LAYERS, COPPER),
        'profile': key, 'layers': int(LAYERS), 'copper': COPPER,
        'captured': fd.get('captured'), 'kicad_rules': prof.get('kicad_rules', {}),
        # board review rev. 0.2, issue 11: the price tier, not only the capability minimum (read by the audit)
        'economical_via_drill_mm': prof.get('economical_via_drill_mm',
                                            prof.get('kicad_rules', {}).get('min_through_hole_diameter')),
        'fine_vias_approved': False,
    }
    if prof.get('absolute_min'):
        fab_block['absolute_min'] = {k: v for k, v in prof['absolute_min'].items() if not k.startswith('_')}
    if int(LAYERS) != layer_count:
        print('WARNING: --layers %s but the board declares %d copper layers'
              % (LAYERS, layer_count))

# ---------------------------------------------------------------- write
params = {
    '_doc': ('Per-project parameters, seeded by init_project.py from this board. Lists start EMPTY '
             'on purpose - a rule copied from another design matches zero nets and then reports a '
             'clean pass while auditing nothing. The _candidates blocks below are observations from '
             'this board, not decisions; fill the real lists yourself.'),
    'project': os.path.splitext(os.path.basename(BOARD))[0],
    'fabricator': fab_block,
    'stackup_reference': {
        '_doc': 'Controlled-impedance stackup this board was designed on, if any (Q-13).',
        'name': '', 'diff_pair_target_ohm': None, 'single_ended_target_ohm': None,
    },
    'length_groups': [],
    '_length_group_candidates': {
        '_doc': 'Bus-like groups found on this board. Turn the ones that are length-critical into '
                'length_groups entries with a pattern, max_spread_mm and clock rule.',
        'groups': {k: v for k, v in sorted(buses.items(), key=lambda kv: -len(kv[1]))},
    },
    'diff_pairs': {'_doc': 'Intra-pair mismatch limits (Q-06).', 'rules': []},
    '_diff_pair_candidates': {
        '_doc': 'Net pairs whose names look like a differential pair. Confirm before adding rules.',
        'pairs': dp,
    },
    'via_budget': {'_doc': 'Maximum vias on fast nets (Q-09).', 'fast_patterns': [],
                   'max_vias_fast': None, 'max_vias_default': None},
    '_routability': {
        '_doc': 'Observations that decide how the router must be driven. Not rules.',
        'copper_layers': layer_count,
        'footprint_local_clearance_overrides': overrides,
        'clearance_floor_mm': max([o['clearance_mm'] for o in overrides], default=0.0),
        'long_haul_nets': long_haul[:25],
    },
    'keepouts': {'_doc': 'Q-10: may a net change layer to pass under a keepout?',
                 'layer_change_allowed': False},
    'silkscreen': {'_doc': 'Q-14: references hidden by default; set false for boards assembled or '
                           'debugged by third parties.', 'references_hidden': True},
    'teardrops': {'_doc': 'Q-15: teardrops off by default.', 'allowed': False, 'allowed_patterns': []},
}

# 1.18.0: the keys added in 1.16.0 are written here, from the template, with every DECISION list empty.
# Before, they were missing and the playbook (A12) said to add them by hand - copying the template's block
# imported another board's via-in-pad parts (U1, U3, IC3 of the reference board; on ServiceOne U3 is an ESD
# array). The numeric defaults (detour limits, router costs) are kept; the lists are cleared.
_tpl = os.path.join(SKILL, 'templates', 'kicad_golden.project.json')
with io.open(_tpl, encoding='utf-8') as f:
    _t = json.load(f)
for _k, _clear in (('via_in_pad', ('allowed_refs',)), ('shared_pad_gaps', ('allowed_parts',)),
                   ('plane_net_exceptions', ('allowed',)), ('detour_limits', ()),
                   ('priority_routing', ('critical_nets',)), ('router_costs', ()),
                   ('layout_checks', ('kelvin', 'decoupling', 'separation')),
                   ('approved_rule_deviations', ()), ('plane_plan', ('islands',))):
    if _k in _t and _k not in params:
        _blk = json.loads(json.dumps(_t[_k]))
        for _c in _clear:
            if isinstance(_blk.get(_c), list):
                _blk[_c] = []
        if _k == 'approved_rule_deviations':             # decisions of THIS project only: keep the _doc
            _blk = {k: v for k, v in _blk.items() if k.startswith('_')}
        if _k == 'shared_pad_gaps':
            _blk['allowed'] = False                       # Q-16 default: ask the user
        params[_k] = _blk

with io.open(OUT, 'w', encoding='utf-8') as f:
    f.write(json.dumps(params, indent=2, ensure_ascii=False))

print('=' * 72)
print('PROJECT INITIALISED  -  %s' % os.path.basename(OUT))
print('=' * 72)
print('  project            : %s' % params['project'])
print('  copper layers      : %d' % layer_count)
print('  fabricator         : %s' % (fab_block.get('name') or '(not set - pass --fab/--layers/--copper)'))
print('  clearance floor    : %.3f mm%s' % (params['_routability']['clearance_floor_mm'],
                                            (' (from %s)' % ', '.join(o['ref'] for o in overrides)) if overrides else ''))
print('  long-haul nets     : %d (route these first)' % len(long_haul))
print('  bus candidates     : %d' % len(buses))
print('  diff-pair candidates: %d' % len(dp))
print('')
print('  length_groups, diff_pairs.rules and via_budget are EMPTY and must stay empty until you')
print('  decide them. The _candidates blocks list what this board actually has.')
print('')
print('  NEXT: netclass_propose.py --apply, then apply_settings.js, then route_report.py')

if JSON_OUT:
    with io.open(JSON_OUT, 'w', encoding='utf-8') as f:
        f.write(json.dumps({'buses': buses, 'diff_pairs': dp, 'long_haul': long_haul,
                            'overrides': overrides, 'copper_layers': layer_count}, indent=1))
    print('  json: %s' % JSON_OUT)
sys.exit(0)
