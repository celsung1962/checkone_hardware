#!/usr/bin/env python
"""dsn_filter.py - restrict a Specctra DSN to a subset of nets.

Runs on ANY python - it is pure text surgery, no pcbnew.

    python dsn_filter.py <in.dsn> <out.dsn> [--nets A,B] [--params FILE] [--invert]

Freerouting has no command-line option for "route only these nets": hand it a board and it
routes everything it can reach. Phase-1-only routing therefore has to be expressed in the DSN
itself - keep the phase's nets in the (network) block, drop the rest, and filter the class
member lists so no class references a net that is no longer there.

Net selection, first match wins:
  --nets A,B,C          explicit list
  --params FILE         priority_routing.critical_nets from a kicad_golden.project.json
  (nothing)             refuses to guess

Options:
  --invert   keep everything EXCEPT the listed nets (useful for a "everything else" phase)
  --quiet    one summary line

The output is checked for balanced parentheses before it is written; an unbalanced DSN would be
rejected by the router with an unhelpful message.

Exit codes: 0 ok, 1 nothing selected / unbalanced result, 2 usage.
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
SRC, DST = os.path.abspath(args[0]), os.path.abspath(args[1])
if not os.path.isfile(SRC):
    die('no such dsn: ' + SRC, 2)


def opt(name, default=None):
    if name in args:
        i = args.index(name)
        if i + 1 >= len(args):
            die(name + ' needs a value', 2)
        return args[i + 1]
    return default


INVERT = '--invert' in args
QUIET = '--quiet' in args
NETS_RAW = opt('--nets')
PARAMS = opt('--params')

sel = []
if NETS_RAW:
    sel, how = [n.strip() for n in NETS_RAW.split(',') if n.strip()], '--nets'
elif PARAMS:
    with io.open(PARAMS, encoding='utf-8') as f:
        p = json.load(f)
    sel = [n for n in ((p.get('priority_routing') or {}).get('critical_nets') or [])
           if not str(n).startswith('_')]
    how = os.path.basename(PARAMS)
if not sel:
    die('no nets selected. Pass --nets or --params with priority_routing.critical_nets. '
        'This script will not guess which nets belong to a phase.')
sel = set(sel)

BS = chr(92)


def balanced(text):
    """Structural signature of a DSN.

    Specctra is NOT KiCad s-expression: a backslash is an ordinary character (the header carries
    Windows paths like "C:\\Users\\..."), and the parser block declares its quote character with a
    bare  (string_quote ")  whose value is a lone double quote. A scanner written for .kicad_pcb
    therefore reports a perfectly good DSN as unbalanced.

    Rather than lex DSN exactly, this returns a signature and callers compare the OUTPUT against
    the INPUT: a transformation that preserves the signature preserved the structure, whatever
    the absolute numbers are."""
    depth, mind, in_str = 0, 0, False
    skip = False
    for i, c in enumerate(text):
        if skip:
            skip = False
            continue
        if c == '"':
            # (string_quote ") - a quote used as a value, not as a delimiter
            if not in_str and text[i:i + 2] == '")' and text[max(0, i - 14):i].rstrip().endswith('string_quote'):
                continue
            in_str = not in_str
        elif not in_str:
            if c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
                mind = min(mind, depth)
    return depth, mind, in_str


def matching(text, i):
    depth, j, in_str, esc = 0, i, False, False
    while j < len(text):
        c = text[j]
        if in_str:
            if esc:
                esc = False
            elif c == BS:
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    die('unbalanced input dsn')


def children(block):
    out, i, depth, in_str, esc, s = [], 1, 0, False, False, None
    while i < len(block):
        c = block[i]
        if in_str:
            if esc:
                esc = False
            elif c == BS:
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == '(':
            if depth == 0:
                s = i
            depth += 1
        elif c == ')':
            depth -= 1
            if depth == 0:
                out.append((s, i + 1))
        i += 1
    return out


src = io.open(SRC, encoding='utf-8', newline='').read()
if '(network' not in src:
    die('no (network ...) block in this dsn')
n0 = src.index('(network')
n1 = matching(src, n0)
block = src[n0:n1]


def wanted(name):
    hit = name in sel
    return (not hit) if INVERT else hit


kept, dropped, classes = [], [], []
pieces = ['(network']
for a, b in children(block):
    ch = block[a:b]
    head = ch[1:].split(None, 1)[0].strip('()')
    if head == 'net':
        m = re.match(r'\(net\s+("([^"]*)"|\S+)', ch)
        name = (m.group(2) if m and m.group(2) is not None else (m.group(1) if m else None))
        if name is not None and wanted(name):
            kept.append(name)
            pieces.append('\n    ' + ch.strip())
        else:
            dropped.append(name)
    elif head == 'class':
        # (class NAME net net ... (circuit ...) (rule ...))
        # The first '(' must be found OUTSIDE quotes: KiCad net names routinely contain
        # parentheses - "Net-(U7-EN)" - and a naive find() splits the header mid-string,
        # producing a DSN with unbalanced quotes and parens.
        first_sub, k, in_s, es = -1, 1, False, False
        while k < len(ch):
            c = ch[k]
            if in_s:
                if es:
                    es = False
                elif c == BS:
                    es = True
                elif c == '"':
                    in_s = False
            elif c == '"':
                in_s = True
            elif c == '(':
                first_sub = k
                break
            k += 1
        header = ch[:first_sub] if first_sub > 0 else ch[:-1]
        rest = ch[first_sub:] if first_sub > 0 else ')'
        # Net names may be quoted AND contain spaces - "/Solar MPPT  - Power/REGN" is a real
        # example. A plain .split() shreds them into fragments and the rebuilt DSN ends up with
        # unbalanced quotes, which the router rejects with an unhelpful error.
        toks = re.findall(r'"[^"]*"|\S+', header[len('(class'):])
        if not toks:
            continue
        cls, members = toks[0], toks[1:]
        keep = [t for t in members if wanted(t.strip('"'))]
        classes.append((cls, len(members), len(keep)))
        pieces.append('\n    (class ' + cls + ((' ' + ' '.join(keep)) if keep else '')
                      + '\n      ' + rest.strip())
    else:
        pieces.append('\n    ' + ch.strip())
pieces.append('\n  )')
out_text = src[:n0] + ''.join(pieces) + src[n1:]

# Compare against the INPUT's signature, not against a notional (0,0,False): see balanced().
sig_in = balanced(src)
sig_out = balanced(out_text)
if sig_out != sig_in:
    die('refusing to write: structure changed (input %s, output %s). The filter damaged the DSN.'
        % (sig_in, sig_out))
io.open(DST, 'w', encoding='utf-8', newline='').write(out_text)

missing = sorted(n for n in sel if n not in kept) if not INVERT else []
if QUIET:
    print('kept=%d dropped=%d missing=%d' % (len(kept), len(dropped), len(missing)))
else:
    print('  selection   : %s (%d net%s)%s' % (how, len(sel), '' if len(sel) == 1 else 's',
                                               ' [INVERTED]' if INVERT else ''))
    print('  nets kept   : %d' % len(kept))
    print('  nets dropped: %d' % len(dropped))
    for c, tot, k in classes:
        print('  class %-22s members %d -> %d' % (c, tot, k))
    if missing:
        print('  WARNING: %d selected net(s) are not in this DSN: %s'
              % (len(missing), ', '.join(missing[:8])))
    print('  written     : %s' % DST)
sys.exit(0)
