#!/usr/bin/env python
"""doctor.py - report what this machine can actually do before you rely on it.

Run it with BOTH interpreters; they differ, and the difference matters:

    python scripts/doctor.py                      # the system interpreter
    "<kicad>/bin/python" scripts/doctor.py        # KiCad's interpreter

Every entry below cost real debugging time at least once:

  * pcbnew lives only in KiCad's interpreter; the DSN/SES round-trip is impossible without it.
  * shapely may be installed in ONE interpreter and not the other. rail_zones.py is documented
    as running on the system python, and on at least one machine shapely was present only in
    KiCad's - so the tool reported "shapely missing" while it was installed.
  * the Freerouting jar needs Java 21+. Where the only java is 8, the jar is unusable and the
    native launcher is the only option; discovery must find the launcher, not the jar.
  * kicad-cli is needed for DRC and plots.
  * node runs the audit and the settings tools.

Nothing here is modified; it only reports.

Options:
  --json PATH   write the findings as JSON
  --quiet       one line per capability
Exit codes: 0 everything essential present, 1 something essential missing.
"""
import io
import os
import re
import sys
import json
import glob
import shutil
import platform
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
args = sys.argv[1:]


def opt(name, default=None):
    if name in args:
        i = args.index(name)
        return args[i + 1] if i + 1 < len(args) else default
    return default


JSON_OUT = opt('--json')
QUIET = '--quiet' in args
rows = []


def add(name, ok, detail, essential=False):
    rows.append({'capability': name, 'ok': bool(ok), 'detail': str(detail), 'essential': essential})


# ---------------------------------------------------------------- interpreter
add('python', True, '%s  (%s)' % (platform.python_version(), sys.executable))

try:
    import pcbnew
    add('pcbnew', True, pcbnew.GetBuildVersion(), essential=False)
    has_pcbnew = True
except Exception as e:
    add('pcbnew', False, 'not in THIS interpreter (%s)' % type(e).__name__)
    has_pcbnew = False

if has_pcbnew:
    two_arg = all(hasattr(pcbnew, f) for f in ('ExportSpecctraDSN', 'ImportSpecctraSES'))
    add('specctra dsn/ses', two_arg,
        'ExportSpecctraDSN + ImportSpecctraSES present' if two_arg else 'MISSING - cannot round-trip')
    v = hasattr(getattr(pcbnew, 'PCB_VIA', object), 'GetFrontWidth')
    add('via GetFrontWidth', v,
        'layer-aware via width available' if v else
        'absent - arg-less GetWidth() may assert and hang a headless run')

try:
    import shapely
    add('shapely', True, '%s (in THIS interpreter)' % shapely.__version__)
except Exception:
    add('shapely', False, 'not in this interpreter - rail_zones.py will refuse to run here')

# ---------------------------------------------------------------- external tools
def which(name):
    return shutil.which(name)


node = which('node')
ver = ''
if node:
    try:
        ver = subprocess.check_output([node, '--version'], stderr=subprocess.STDOUT).decode().strip()
    except Exception:
        pass
add('node', bool(node), '%s %s' % (ver, node or 'NOT FOUND'), essential=True)

cli = which('kicad-cli')
if not cli:
    for pat in (r'C:\Program Files\KiCad\*\bin\kicad-cli.exe',
                '/usr/bin/kicad-cli', '/usr/local/bin/kicad-cli',
                '/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'):
        hits = sorted(glob.glob(pat))
        if hits:
            cli = hits[-1]
            break
add('kicad-cli', bool(cli), cli or 'NOT FOUND - no DRC, no plots', essential=True)

# java: only relevant for the Freerouting JAR
java = which('java')
jmajor = None
if java:
    try:
        out = subprocess.check_output([java, '-version'], stderr=subprocess.STDOUT).decode()
        m = re.search(r'version "(\d+)(?:\.(\d+))?', out)
        if m:
            jmajor = int(m.group(1))
            if jmajor == 1 and m.group(2):
                jmajor = int(m.group(2))
    except Exception:
        pass
add('java', bool(java), ('%s (major %s)' % (java, jmajor)) if java else 'not found (only needed for the Freerouting JAR)')

# freerouting: native launcher preferred over the jar
fr, how = None, ''
env = os.environ.get('FREEROUTING_CMD')
if env and os.path.isfile(env.strip('"')):
    fr, how = env.strip('"'), 'FREEROUTING_CMD'
if not fr:
    p = which('freerouting')
    if p:
        fr, how = p, 'PATH'
if not fr:
    for pat in (os.path.expandvars(r'%LOCALAPPDATA%\freerouting\freerouting.exe'),
                os.path.expandvars(r'%PROGRAMFILES%\Freerouting\freerouting.exe'),
                '/Applications/Freerouting.app/Contents/MacOS/Freerouting',
                os.path.expanduser('~/.local/share/freerouting/bin/freerouting'),
                '/opt/freerouting/bin/freerouting'):
        if os.path.isfile(pat):
            fr, how = pat, 'install location'
            break
jar = None
if not fr:
    for pat in (os.path.expandvars(r'%LOCALAPPDATA%\freerouting\freerouting*.jar'),
                os.path.expanduser('~/freerouting*.jar'), './freerouting*.jar'):
        hits = sorted(glob.glob(pat))
        if hits:
            jar = hits[-1]
            break
if fr:
    add('freerouting', True, '%s  [%s]  native launcher, carries its own runtime' % (fr, how), essential=True)
elif jar:
    usable = jmajor is not None and jmajor >= 21
    add('freerouting', usable,
        '%s  JAR only; needs Java 21+, found %s%s' % (jar, jmajor, '' if usable else ' -> UNUSABLE'),
        essential=True)
else:
    add('freerouting', False, 'NOT FOUND - no automated routing', essential=True)

# rendering, for the visual verification step
sof = which('soffice') or which('libreoffice')
if not sof:
    for pat in (r'C:\Program Files\LibreOffice\program\soffice.exe',
                '/Applications/LibreOffice.app/Contents/MacOS/soffice'):
        if os.path.isfile(pat):
            sof = pat
            break
add('libreoffice', bool(sof), sof or 'not found - cannot render a docx/pdf for visual checking')
add('pdftoppm', bool(which('pdftoppm')), which('pdftoppm') or 'not found - cannot rasterise a PDF')
add('inkscape', bool(which('inkscape')), which('inkscape') or 'not found - SVG layer renders unavailable')

# ---------------------------------------------------------------- report
missing_essential = [r for r in rows if r['essential'] and not r['ok']]
if QUIET:
    for r in rows:
        print('%-18s %-3s %s' % (r['capability'], 'ok' if r['ok'] else 'NO', r['detail']))
else:
    print('=' * 72)
    print('KICAD-ROUTING DOCTOR  -  %s' % platform.platform())
    print('=' * 72)
    for r in rows:
        mark = ' ok ' if r['ok'] else ('FAIL' if r['essential'] else ' -- ')
        print('  [%s] %-18s %s' % (mark, r['capability'], r['detail']))
    print('')
    if missing_essential:
        print('  MISSING, and the workflow needs them: %s'
              % ', '.join(r['capability'] for r in missing_essential))
    else:
        print('  every essential capability is present in this configuration')
    if not has_pcbnew:
        print('  NOTE: this interpreter has no pcbnew. Re-run with KiCad\'s python for the')
        print('        routing tools; only the node tools and rail_zones.py can run here.')

if JSON_OUT:
    with io.open(JSON_OUT, 'w', encoding='utf-8') as f:
        f.write(json.dumps({'platform': platform.platform(), 'interpreter': sys.executable,
                            'capabilities': rows}, indent=1))
    if not QUIET:
        print('  json: %s' % JSON_OUT)

sys.exit(1 if missing_essential else 0)
