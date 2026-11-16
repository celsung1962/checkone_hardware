#!/usr/bin/env python3
"""Release package of one board, from a tag <prefix>-v<version> (e.g. con-v2.0), configured in hw_checks.json "release".

Builds into --out (default build/release/<tag>/), every file named <board>_V<version>_...:
  _gerbers.zip          Gerber X2 of the copper / mask / paste / silk / Edge.Cuts layers (+ user layers that carry
                        drawings), Excellon drill PTH / NPTH, drill maps, .gbrjob
  _BOM_JLCPCB.csv       Comment, Designator, Footprint, JLCPCB Part # (from the LCSC field), DNP excluded
  _CPL_JLCPCB.csv       Designator, Mid X, Mid Y, Layer, Rotation (mm), DNP excluded
  _schematic.pdf        all sheets
  _kicad_project.zip    the KiCad project as tagged (sources, project libraries)
  + the documents listed in the config ({version} filled in), e.g. technical documentation PDF and BOM .xlsx
  SHA256SUMS.txt, release_notes.md
Gate (a release for fabrication): hardware checks PASS for the board, zero DRC errors (ignored types left out),
schematic title-block revision == tag version, every listed document present, Gerbers carry X2 attributes, drill
files present. A tag with -rc / -test / -pre (e.g. con-v2.0-rc1) is a pre-release: gate failures become warnings
and the notes say NOT FOR FABRICATION.

    python tools/hw_checks/hw_release.py con-v2.0 [--out DIR] [--publish [--store DIR] [--replace]]
Exit 0 = package built and the gate passed (or pre-release); 1 = gate failed (package still built, for inspection);
2 = publish refused.

--publish copies the package to the company store (OUTSIDE_GIT.md), <store>/releases/<tag>/, and verifies every copy
against SHA256SUMS.txt. Store = --store, else "release.store" of the config ({OneDrive} = the OneDrive for Business
folder), else <OneDrive>/<repo folder name>. Refused when the gate failed, when HEAD is not the tagged commit, when a
tracked file differs from it (the package would not be the tag), or when the tag is already published (a published
release is never overwritten; --replace moves the old folder to <tag>_superseded_<UTC time>/ first).
"""
import argparse
import csv
import datetime
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = os.getcwd()
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hw_checks import kicad_cli, run  # noqa: E402

SKIP_DIRS = {'.history'}
SKIP_RX = re.compile(r'(-backups$|\.kicad_prl$|fp-info-cache$|\.lck$|_autosave-|~\$)')


def natkey(s):
    return [int(t) if t.isdigit() else t for t in re.split(r'(\d+)', s)]


def sha(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


def plot_layers(pcb_text):
    """Copper layers of the stackup + the fixed fab layers + user layers that carry drawings."""
    head = pcb_text[pcb_text.index('(layers'):]
    head = head[:head.index('\n\t)') if '\n\t)' in head else 4000]
    copper = [m.group(1) for m in re.finditer(r'\(\d+ "([^"]+\.Cu)" (?:signal|power|mixed|jumper)', head)]
    fab = ['F.Paste', 'B.Paste', 'F.Silkscreen', 'B.Silkscreen', 'F.Mask', 'B.Mask', 'Edge.Cuts']
    used = set()
    for m in re.finditer(r'\n\t\((?:gr_\w+|dimension)\b', pcb_text):       # board-level drawings only
        lm = re.search(r'\(layer "([^"]+)"', pcb_text[m.end():m.end() + 3000])
        if lm:
            used.add(lm.group(1))
    user = sorted(u for u in used if re.fullmatch(r'User\.\d+|Dwgs\.User', u))
    return copper + fab + user


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('tag')
    ap.add_argument('--config', default='hw_checks.json')
    ap.add_argument('--out')
    ap.add_argument('--skip-checks', action='store_true', help='do not run hw_checks.py (already run in CI)')
    ap.add_argument('--publish', action='store_true', help='copy the package to <store>/releases/<tag>/')
    ap.add_argument('--store', help='store folder (default: release.store of the config, else <OneDrive>/<repo>)')
    ap.add_argument('--replace', action='store_true', help='republish a tag (old folder kept as _superseded_)')
    ap.add_argument('--no-documents', action='store_true',
                    help='CI build: the generated documents are kept outside git (OUTSIDE_GIT.md) and are not in a '
                         'checkout; leave them out and say so in the notes. Refused with --publish.')
    a = ap.parse_args()
    cfg = json.load(open(os.path.join(ROOT, a.config), encoding='utf-8-sig'))
    rel = cfg['release']
    m = re.fullmatch(r'([a-z0-9_]+)-v(\d+(?:\.\d+)*)(-(?:rc|test|pre)[0-9a-z.]*)?', a.tag)
    if not m or m.group(1) not in rel['boards']:
        sys.exit(f"tag {a.tag!r}: expected <prefix>-v<version>[-rcN], prefix one of {sorted(rel['boards'])}")
    prefix, version, pre = m.group(1), m.group(2), bool(m.group(3))
    rb = rel['boards'][prefix]
    board = next(b for b in cfg['boards'] if b['name'] == rb['board'])
    name = board['name']
    stem = os.path.splitext(os.path.join(ROOT, board['project']))[0]
    proj_dir = os.path.dirname(stem)
    out = a.out or os.path.join(ROOT, 'build', 'release', a.tag)
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out)
    base = f'{name}_V{version}'
    cli = kicad_cli()
    tmp = tempfile.mkdtemp()
    gate, warn, made, info = [], [], [], []

    def fail(msg):
        (warn if pre else gate).append(msg)
        print(('WARNING (pre-release): ' if pre else 'GATE FAIL: ') + msg)

    def ok(r, what):
        if r.returncode:
            sys.exit(f'{what} failed: {(r.stderr or r.stdout).strip()[-800:]}')

    # 1. gate: hardware checks, DRC errors, revision
    if not a.skip_checks:
        r, _ = run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hw_checks.py'),
                    '--config', a.config, '--board', name])
        print(r.stdout[-3000:])
        if r.returncode:
            fail('hardware checks FAIL (see the job log / hw_checks.py)')
    drc = os.path.join(tmp, 'drc.json')
    run([cli, 'pcb', 'drc', '--format', 'json', '--severity-error', '--schematic-parity', '-o', drc, stem + '.kicad_pcb'])
    d = json.load(open(drc, encoding='utf-8'))
    ign = {i['type'] for i in cfg.get('ignore', []) if i.get('check', 'drc') == 'drc'}
    errs = [v for v in d['violations'] + d.get('schematic_parity', []) if v['type'] not in ign]
    n_unc = len(d.get('unconnected_items', []))
    if errs or n_unc:
        types = sorted({v['type'] for v in errs})
        fail(f'DRC: {len(errs)} error(s) {types[:8]}, {n_unc} unconnected item(s) - a fabrication release needs 0')
    sch_text = open(stem + '.kicad_sch', encoding='utf-8').read()
    rev = (re.search(r'\(rev "([^"]*)"\)', sch_text) or [None, ''])[1]
    if rev != version:
        fail(f'schematic title-block revision is {rev!r}, the tag says {version!r}')

    # 2. Gerbers + drill
    pcb_text = open(stem + '.kicad_pcb', encoding='utf-8').read()
    layers = plot_layers(pcb_text)
    gdir = os.path.join(tmp, 'gerbers')
    os.makedirs(gdir)
    r, _ = run([cli, 'pcb', 'export', 'gerbers', '--output', gdir + os.sep, '--check-zones', '--layers', ','.join(layers),
                stem + '.kicad_pcb'])
    ok(r, 'gerber export')
    r, _ = run([cli, 'pcb', 'export', 'drill', '--output', gdir + os.sep, '--format', 'excellon',
                '--excellon-separate-th', '--generate-map', '--map-format', 'gerberx2', stem + '.kicad_pcb'])
    ok(r, 'drill export')
    gfiles = sorted(os.listdir(gdir))
    cu = [f for f in gfiles if re.search(r'-F_Cu\.g', f)]
    if not cu or not open(os.path.join(gdir, cu[0]), encoding='utf-8', errors='replace').readline().startswith('%TF.'):
        fail('front copper Gerber missing or without X2 attributes')
    if not any(f.endswith('-PTH.drl') for f in gfiles):
        fail('no plated drill file (-PTH.drl)')
    gz = os.path.join(out, f'{base}_gerbers.zip')
    with zipfile.ZipFile(gz, 'w', zipfile.ZIP_DEFLATED) as z:
        for f in gfiles:
            z.write(os.path.join(gdir, f), f)
    made.append((gz, f'Gerber X2 + Excellon drill + maps + job file ({len(gfiles)} files; layers {", ".join(layers)})'))

    # 3. JLCPCB BOM and CPL
    raw = os.path.join(tmp, 'bom.csv')
    r, _ = run([cli, 'sch', 'export', 'bom', '--output', raw, '--fields', 'Value,Reference,Footprint,LCSC,${QUANTITY}',
                '--labels', 'Comment,Designator,Footprint,JLCPCB Part #,Qty', '--group-by', 'Value,Footprint,LCSC',
                '--ref-range-delimiter', '', '--exclude-dnp', stem + '.kicad_sch'])
    ok(r, 'BOM export')
    rows = list(csv.DictReader(open(raw, encoding='utf-8-sig')))
    na_rx = [re.compile(x) for x in rel.get('not_assembled', [])]     # board features: holes, wire / probe pads
    board_only = [rw for rw in rows if any(x.search(rw['Footprint'].split(':')[-1]) for x in na_rx)]
    rows = [rw for rw in rows if rw not in board_only]
    skip_refs = {r.strip() for rw in board_only for r in rw['Designator'].split(',')}
    no_lcsc = [rw['Designator'] for rw in rows if not rw['JLCPCB Part #'].strip() or rw['JLCPCB Part #'].strip() in
               ('TBD', '-', '~')]
    if no_lcsc:
        fail(f'BOM lines without an LCSC part: {"; ".join(no_lcsc)[:300]}')
    bom = os.path.join(out, f'{base}_BOM_JLCPCB.csv')
    with open(bom, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['Comment', 'Designator', 'Footprint', 'JLCPCB Part #'])
        for rw in rows:
            w.writerow([rw['Comment'], rw['Designator'], rw['Footprint'].split(':')[-1], rw['JLCPCB Part #'].strip()])
    n_parts = sum(int(rw['Qty'] or 0) for rw in rows)
    made.append((bom, f'{len(rows)} lines, {n_parts} parts, DNP excluded'
                      + (f'; not assembled (board features): {", ".join(sorted(skip_refs, key=natkey))}' if skip_refs else '')))
    pos = os.path.join(tmp, 'pos.csv')
    r, _ = run([cli, 'pcb', 'export', 'pos', '--output', pos, '--format', 'csv', '--units', 'mm', '--side', 'both',
                '--exclude-dnp', stem + '.kicad_pcb'])
    ok(r, 'position export')
    bom_refs = {r.strip() for rw in rows for r in rw['Designator'].split(',')}
    allpos = [p for p in csv.DictReader(open(pos, encoding='utf-8-sig')) if p['Ref'] not in skip_refs]
    prow = [p for p in allpos if p['Ref'] in bom_refs]            # BOM and CPL must hold the same designators
    extra = sorted({p['Ref'] for p in allpos} - bom_refs, key=natkey)
    missing = sorted(bom_refs - {p['Ref'] for p in prow}, key=natkey)
    if missing:
        fail(f'BOM parts with no placement in the PCB: {", ".join(missing)[:300]}')
    cpl = os.path.join(out, f'{base}_CPL_JLCPCB.csv')
    with open(cpl, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['Designator', 'Mid X', 'Mid Y', 'Layer', 'Rotation'])
        for p in prow:
            w.writerow([p['Ref'], p['PosX'], p['PosY'], 'Top' if p['Side'].lower().startswith('top') else 'Bottom',
                        p['Rot']])
    made.append((cpl, f'{len(prow)} placements, same designators as the BOM (mm, KiCad rotation - check the JLCPCB '
                      f'preview for rotation offsets)' + (f'; not in the BOM, left out: {", ".join(extra)}' if extra else '')))

    # 4. schematic PDF
    pdf = os.path.join(out, f'{base}_schematic.pdf')
    r, _ = run([cli, 'sch', 'export', 'pdf', '--output', pdf, stem + '.kicad_sch'])
    ok(r, 'schematic PDF export')
    made.append((pdf, 'all sheets'))

    # 5. KiCad project snapshot
    pz = os.path.join(out, f'{base}_kicad_project.zip')
    n = 0
    with zipfile.ZipFile(pz, 'w', zipfile.ZIP_DEFLATED) as z:
        for dp, dns, fns in os.walk(proj_dir):
            dns[:] = [x for x in dns if x not in SKIP_DIRS and not SKIP_RX.search(x)]
            for fn in fns:
                if not SKIP_RX.search(fn):
                    p = os.path.join(dp, fn)
                    z.write(p, f'{base}/' + os.path.relpath(p, proj_dir).replace(os.sep, '/'))
                    n += 1
    made.append((pz, f'{n} files of {os.path.relpath(proj_dir, ROOT).replace(os.sep, "/")} as tagged'))

    # 6. documents
    if a.no_documents and a.publish:
        sys.exit('--no-documents is for CI builds; a published release carries its documents')
    if a.no_documents and rb.get('documents'):
        info.append('documents left out (--no-documents, CI build): '
                    + ', '.join(d.format(version=version) for d in rb['documents'])
                    + ' - the published release in the store carries them')
    for doc in [] if a.no_documents else rb.get('documents', []):
        p = os.path.join(ROOT, doc.format(version=version))
        if not os.path.isfile(p) or os.path.getsize(p) == 0:
            fail(f'document missing: {doc.format(version=version)}')
            continue
        dst = os.path.join(out, os.path.basename(p))
        shutil.copy2(p, dst)
        made.append((dst, 'document from the repository'))

    # 7. checksums and notes
    sums = os.path.join(out, 'SHA256SUMS.txt')
    with open(sums, 'w', newline='\n') as f:
        for p, _ in made:
            f.write(f'{sha(p)}  {os.path.basename(p)}\n')
    commit = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
    kv = subprocess.run([cli, 'version'], capture_output=True, text=True).stdout.strip()
    notes = [f'**{name} V{version}**' + (' - PRE-RELEASE, NOT FOR FABRICATION' if pre else ''), '',
             f'Commit `{commit[:10]}`, KiCad {kv}, built {datetime.datetime.now(datetime.timezone.utc):%Y-%m-%d %H:%M} UTC.', '',
             '| File | Content |', '|---|---|']
    notes += [f'| `{os.path.basename(p)}` | {what} |' for p, what in made]
    notes += ['| `SHA256SUMS.txt` | checksums of the files above |', '', '### Gate']
    if gate:
        notes += [f'- FAIL: {g}' for g in gate]
    elif warn:
        notes += [f'- not met (pre-release): {g}' for g in warn]
    else:
        notes += ['- hardware checks PASS, DRC 0 errors / 0 unconnected, title-block revision = tag, all documents '
                  'present, Gerber X2 and drill files present.']
    notes += ([''] + [f'Note: {i}' for i in info]) if info else []
    notes += ['', '🤖 Generated with [Claude Code](https://claude.com/claude-code)']
    open(os.path.join(out, 'release_notes.md'), 'w', encoding='utf-8', newline='\n').write('\n'.join(notes) + '\n')
    print('\n'.join(notes))
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
            f.write(f'dir={out}\nprerelease={"true" if pre else "false"}\ntitle={name} V{version}'
                    f'{" (pre-release)" if pre else ""}\n')
    print(f'\nRELEASE {a.tag}: ' + ('GATE FAIL' if gate else 'OK') + f' - {len(made)} files in {out}')
    if gate:
        if a.publish:
            print('PUBLISH REFUSED: the gate failed')
        sys.exit(1)
    if a.publish:
        sys.exit(publish(a, rel, out))
    sys.exit(0)


def publish(a, rel, out):
    """Copy the package to <store>/releases/<tag>/; 0 = published, 2 = refused."""
    def git(*args):
        return subprocess.run(['git', *args], capture_output=True, text=True)
    tagc = git('rev-parse', '--verify', '--quiet', a.tag + '^{commit}').stdout.strip()
    head = git('rev-parse', 'HEAD').stdout.strip()
    if not tagc:
        print(f'PUBLISH REFUSED: tag {a.tag} does not exist - create it on the released commit first')
        return 2
    if tagc != head:
        print(f'PUBLISH REFUSED: HEAD {head[:10]} is not the commit of {a.tag} ({tagc[:10]}) - check out the tag')
        return 2
    dirty = git('status', '--porcelain', '--untracked-files=no').stdout.strip()
    if dirty:
        print('PUBLISH REFUSED: tracked files differ from the tag:\n' + dirty[:1500])
        return 2
    od = os.environ.get('OneDriveCommercial') or os.environ.get('OneDrive') or ''
    store = a.store or (rel.get('store') or '').replace('{OneDrive}', od) or \
        (os.path.join(od, os.path.basename(ROOT)) if od else '')
    if not store or not os.path.isdir(store):
        print(f'PUBLISH REFUSED: store folder not found ({store or "no --store, no release.store, no OneDrive"})')
        return 2
    dst = os.path.join(store, 'releases', a.tag)
    if os.path.exists(dst):
        if not a.replace:
            print(f'PUBLISH REFUSED: {dst} already exists - a published release is not overwritten (--replace)')
            return 2
        old = f'{dst}_superseded_{datetime.datetime.now(datetime.timezone.utc):%Y%m%dT%H%M%SZ}'
        os.rename(dst, old)
        print(f'previous publication moved to {old}')
    shutil.copytree(out, dst)
    bad = []
    for ln in open(os.path.join(dst, 'SHA256SUMS.txt'), encoding='utf-8'):
        h, fn = ln.rstrip('\n').split('  ', 1)
        if sha(os.path.join(dst, fn)) != h:
            bad.append(fn)
    if bad:
        print('PUBLISH FAILED: checksum mismatch in the store: ' + ', '.join(bad))
        return 2
    print(f'PUBLISHED {a.tag} -> {dst} (checksums verified)')
    return 0


if __name__ == '__main__':
    main()
