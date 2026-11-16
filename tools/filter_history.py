"""Bitbucket migration step 2 (owner decision D5 (a), 2026-11-12; reports/repo_audit_bitbucket_2026-11-12.md):
build a mirror clone whose history no longer carries the files the repository keeps outside git (OUTSIDE_GIT.md),
and prove that nothing else changed.

    py tools/filter_history.py <mirror dir> [--source .]        (needs: pip install git-filter-repo)

1. `git clone --mirror --no-local <source>` into <mirror dir> (a real copy: no hard links to the working repo, no
   stray pack files); the remote-tracking refs of the source (refs/remotes/*) are dropped.
2. git filter-repo --invert-paths with the globs below (fnmatch: `*` also matches `/`), over every commit and tag.
   They are the outside-git groups of OUTSIDE_GIT.md: reference projects, CE technical-file binaries, generated
   deliverables of DOC/ (top level only), report binaries, fabrication packages, scratch folders.
3. Checks (exit 1 on any failure):
   - the tree of every branch head is identical before and after;
   - the tree of every tag is identical too, unless the tag's tree held a filtered file (then only the filtered
     files may be missing; listed);
   - the same branch and tag names exist;
   - git fsck --full passes;
   - the size of the packed history, before and after.
Commit hashes change; tag names are kept. The source repository is never modified.
"""
import os
import re
import shutil
import subprocess
import sys
from fnmatch import fnmatchcase

GLOBS = [
    'reference/*',
    'build/*',
    'deliveries/*',
    'en/*',
    *[f'DOC/GapOne_CE_Technical_Documentation/*.{e}' for e in
      ('pdf', 'PDF', 'png', 'PNG', 'jpg', 'JPG', 'jpeg', 'docx', 'xlsx', 'xls', 'zip', 'STEP', 'step')],
    *[f'reports/*.{e}' for e in ('png', 'pdf', 'docx', 'zip', 'xlsx', 'kicad_pcb')],
    'hardware/*/production/*',
    'hardware/*/gerbers/*',
]
MARK = 'FILTER_HISTORY_MIRROR'                                  # marks a folder this script may delete and rebuild
TOP_DOC = re.compile(r'^DOC/[^/]+\.(xlsx|docx|pdf)$', re.I)     # DOC/*.xlsx at the top level only (DOC/source stays)


def filtered(path):
    return TOP_DOC.match(path) or any(fnmatchcase(path, g) for g in GLOBS)


def git(repo, *args, check=True):
    r = subprocess.run(['git', '-C', repo, *args], capture_output=True, text=True, encoding='utf-8', errors='replace')
    if check and r.returncode:
        sys.exit(f'git {" ".join(args)}: {r.stderr.strip()}')
    return r.stdout


def refs(repo):
    out = {}
    for ln in git(repo, 'for-each-ref', '--format=%(refname) %(objectname)', 'refs/heads', 'refs/tags').splitlines():
        name, oid = ln.split()
        out[name] = git(repo, 'rev-parse', oid + '^{tree}').strip()
    return out


def files(repo, tree):
    return {e.split('\t', 1)[1]: e.split()[2] for e in git(repo, 'ls-tree', '-r', '-z', tree).split('\0') if e}


def pack_mb(repo):
    m = re.search(r'size-pack: (\d+)', git(repo, 'count-objects', '-v'))
    return int(m.group(1)) / 1024 if m else 0


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    mirror = os.path.abspath(a[0])
    source = os.path.abspath(a[a.index('--source') + 1] if '--source' in a else '.')
    if os.path.exists(mirror):          # a previous run: only a bare mirror is ever removed
        if not os.path.isfile(os.path.join(mirror, MARK)):
            sys.exit(f'{mirror} exists and was not made by this script - choose another folder')

        def unlock(fn, p, _):
            os.chmod(p, 0o666)
            fn(p)
        shutil.rmtree(mirror, onexc=unlock)
    r = subprocess.run(['git', 'clone', '-q', '--mirror', '--no-local', source, mirror], capture_output=True, text=True)
    if r.returncode:
        sys.exit('clone: ' + r.stderr)
    open(os.path.join(mirror, MARK), 'w').write(f'filtered mirror of {source}\n')
    for ln in git(mirror, 'for-each-ref', '--format=%(refname)', 'refs/remotes').splitlines():
        git(mirror, 'update-ref', '-d', ln)
    before = refs(mirror)
    before_files = {name: files(mirror, t) for name, t in before.items()}
    mb0 = pack_mb(mirror)

    pf = os.path.join(mirror, 'filter-paths.txt')
    with open(pf, 'w', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join('glob:' + g for g in GLOBS) + '\n')
        f.write('regex:^DOC/[^/]+\\.(xlsx|docx|pdf|XLSX|DOCX|PDF)$\n')
    r = subprocess.run([sys.executable, '-m', 'git_filter_repo', '--force', '--invert-paths', '--paths-from-file', pf],
                       cwd=mirror, capture_output=True, text=True, encoding='utf-8', errors='replace')
    print(r.stdout.strip().splitlines()[-1] if r.stdout.strip() else '', r.stderr.strip()[-500:])
    if r.returncode:
        sys.exit('filter-repo failed')
    os.remove(pf)
    git(mirror, 'reflog', 'expire', '--expire=now', '--all')
    git(mirror, 'gc', '--prune=now', '--aggressive', '-q')
    after = refs(mirror)
    bad = []
    if set(after) != set(before):
        bad.append(f'refs differ: lost {sorted(set(before) - set(after))}, new {sorted(set(after) - set(before))}')
    for name in sorted(set(before) & set(after)):
        if before[name] == after[name]:
            print(f'  same tree   {name}')
            continue
        fa = files(mirror, after[name])
        fb = before_files[name]
        gone = sorted(set(fb) - set(fa))
        wrong = [p for p in gone if not filtered(p)]
        changed = [p for p in fa if fa[p] != fb.get(p)]
        if wrong or changed:
            bad.append(f'{name}: unexpected changes, removed {wrong[:5]}, changed {changed[:5]}')
        elif name.startswith('refs/heads/'):
            bad.append(f'{name}: the branch head lost tracked files {gone[:5]} - the latest tree must not change')
        else:
            print(f'  {name}: only filtered files removed ({len(gone)}: {", ".join(gone[:4])}{" ..." if len(gone) > 4 else ""})')
    fs = subprocess.run(['git', '-C', mirror, 'fsck', '--full'], capture_output=True, text=True)
    if fs.returncode:
        bad.append('git fsck failed: ' + fs.stderr[-500:])
    print(f'packed history: {mb0:.1f} MB -> {pack_mb(mirror):.1f} MB; '
          f'{len(after)} refs; commits {git(mirror, "rev-list", "--all", "--count").strip()}')
    if bad:
        print('FAIL\n  ' + '\n  '.join(bad))
        sys.exit(1)
    print(f'PASS - filtered mirror ready: {mirror}')


if __name__ == '__main__':
    main()
