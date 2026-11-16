#!/usr/bin/env python
"""rules_writer.py - generate the Freerouting .rules file that drives the autorouter.

Runs on ANY python - pure text, no pcbnew.

    python rules_writer.py <board.dsn> <out.rules> [--via-cost N] [--params FILE]

Why this exists: Freerouting's autorouter costs (how much a via is "worth", preferred routing
direction per layer, rip-up aggressiveness) are GUI settings that live in the session, not in
freerouting.json. They are therefore invisible to a batch run and different on every engineer's
machine. `freerouting -dr <file>` reads them from a file instead, which makes them part of the
project rather than part of somebody's install.

**Via cost is the lever worth knowing about.** Vias on power and long-haul nets are inductance and
return-path discontinuities. Raising `via_cost` makes the router work harder to avoid them. This
is far cheaper than phased routing, which buys the same thing at the cost of unrouted connections.

VERIFIED against Freerouting 2.4.1:

  * the design name in `(rules PCB <name>)` MUST equal the DSN's basename without extension, or
    the reader warns `designName not matching` and the rules may not apply. It is read from the
    DSN here rather than guessed.
  * `autoroute_settings`, `via_costs`, `plane_via_costs`, `start_ripup_costs`, `layer_rule`,
    `preferred_direction` and `against_preferred_direction_trace_cost` are all recognised.
  * plane layers are forced inactive by Freerouting itself ("dedicated power plane and cannot be
    routed"), so a rules file cannot accidentally enable routing on them. Signal layers only are
    emitted as routable.

NOT settable from here, and not settable from anywhere a script can reach: "automatic neckdown",
"vias snap to SMD pad centers" and "drag components". Those are interactive-editor state, absent
from the rules vocabulary. The standard defends against their effects at the audit instead -
via-in-pad is a FAIL, neckdowns are stripped and re-checked, footprint identity is verified.

Options:
  --via-cost N          cost of a via (Freerouting default 50; higher = fewer vias)
  --plane-via-cost N    cost of a via to a plane (default 5; these you generally want)
  --ripup-cost N        rip-up start cost (default 100)
  --pref-cost F         trace cost in the preferred direction (default 1.0)
  --against-cost F      trace cost against it (default 2.0)
  --params FILE         read the same keys from router_costs in a kicad_golden.project.json
  --quiet               one summary line

Explicit flags win over --params. Exit codes: 0 ok, 2 usage.
"""
import io
import os
import re
import sys
import json


def die(msg, code=1):
    sys.stderr.write(str(msg).rstrip() + '\n')
    sys.exit(code)


args = sys.argv[1:]
if len(args) < 2 or args[0].startswith('--'):
    die(__doc__, 2)
DSN, OUT = os.path.abspath(args[0]), os.path.abspath(args[1])
if not os.path.isfile(DSN):
    die('no such dsn: ' + DSN, 2)


def opt(name, default=None):
    if name in args:
        i = args.index(name)
        if i + 1 >= len(args):
            die(name + ' needs a value', 2)
        return args[i + 1]
    return default


QUIET = '--quiet' in args
PARAMS = opt('--params')

cfg = {'via_cost': 50, 'plane_via_cost': 5, 'ripup_cost': 100,
       'pref_cost': 1.0, 'against_cost': 2.0, 'preferred_direction': {}}
if PARAMS:
    if not os.path.isfile(PARAMS):
        die('no such params file: ' + PARAMS, 2)
    with io.open(PARAMS, encoding='utf-8') as f:
        p = json.load(f)
    rc = p.get('router_costs') or {}
    for k in list(cfg):
        if k in rc and not str(k).startswith('_'):
            cfg[k] = rc[k]

if opt('--via-cost'):
    cfg['via_cost'] = float(opt('--via-cost'))
if opt('--plane-via-cost'):
    cfg['plane_via_cost'] = float(opt('--plane-via-cost'))
if opt('--ripup-cost'):
    cfg['ripup_cost'] = float(opt('--ripup-cost'))
if opt('--pref-cost'):
    cfg['pref_cost'] = float(opt('--pref-cost'))
if opt('--against-cost'):
    cfg['against_cost'] = float(opt('--against-cost'))

src = io.open(DSN, encoding='utf-8', newline='').read()

# Design name: Freerouting expects the DSN's basename without extension. Taking it from the file
# rather than from (pcb "...") avoids depending on how the path was written.
design = os.path.splitext(os.path.basename(DSN))[0]

# Layers, in DSN order, with their declared type. Only `signal` layers are routable; Freerouting
# forces `power` layers inactive regardless of what a rules file says.
layers = []
m = re.search(r'\(structure\b', src)
if not m:
    die('no (structure ...) block in the dsn')
for lm in re.finditer(r'\(layer\s+(\S+)\s*\r?\n\s*\(type\s+(\w+)\s*\)', src[m.start():]):
    name, typ = lm.group(1).strip('"'), lm.group(2)
    if (name, typ) not in layers:
        layers.append((name, typ))
    if len(layers) > 32:
        break
signal = [n for n, t in layers if t == 'signal']
if not signal:
    die('no signal layers found in the dsn')

# Default preferred directions: alternate vertical / horizontal starting with the top layer.
# A per-layer override may come from the params file.
pref = {}
for i, n in enumerate(signal):
    pref[n] = 'vertical' if i % 2 == 0 else 'horizontal'
for k, v in (cfg.get('preferred_direction') or {}).items():
    if k in pref and v in ('vertical', 'horizontal'):
        pref[k] = v

L = []
# The name MUST be quoted. Unquoted, Freerouting's reader stops at the first space: a board called
# "My Board v2" is read as 'My', the designName check fails, and the rules are silently ignored -
# the run looks fine and none of the costs applied. Verified against 2.4.1.
L.append('(rules PCB "%s"' % design)
for n, t in layers:
    if t != 'signal':
        # emitted for completeness; Freerouting forces these inactive itself
        L.append('  (layer_rule %s' % n)
        L.append('    (active off)')
        L.append('  )')
        continue
    L.append('  (layer_rule %s' % n)
    L.append('    (active on)')
    L.append('    (preferred_direction %s)' % pref[n])
    L.append('    (preferred_direction_trace_cost %.2f)' % float(cfg['pref_cost']))
    L.append('    (against_preferred_direction_trace_cost %.2f)' % float(cfg['against_cost']))
    L.append('  )')
L.append('  (autoroute_settings')
L.append('    (autoroute on)')
L.append('    (postroute on)')
L.append('    (vias on)')
L.append('    (via_costs %g)' % float(cfg['via_cost']))
L.append('    (plane_via_costs %g)' % float(cfg['plane_via_cost']))
L.append('    (start_ripup_costs %g)' % float(cfg['ripup_cost']))
L.append('    (start_pass_no 1)')
L.append('  )')
L.append(')')
text = '\n'.join(L) + '\n'

with io.open(OUT, 'w', encoding='utf-8', newline='\n') as f:
    f.write(text)

if QUIET:
    print('rules written design=%r signal_layers=%d via_cost=%g' % (design, len(signal), float(cfg['via_cost'])))
else:
    print('  design name   : %s   (must match the DSN basename, or Freerouting ignores the rules)' % design)
    print('  layers        : %s' % ', '.join('%s[%s]' % (n, t) for n, t in layers))
    print('  routable      : %s' % ', '.join('%s=%s' % (n, pref[n]) for n in signal))
    print('  via_costs     : %g   (Freerouting default 50; higher = the router avoids vias)' % float(cfg['via_cost']))
    print('  plane_via     : %g' % float(cfg['plane_via_cost']))
    print('  ripup / trace : %g / %.2f pref, %.2f against'
          % (float(cfg['ripup_cost']), float(cfg['pref_cost']), float(cfg['against_cost'])))
    print('  written       : %s' % OUT)
sys.exit(0)
