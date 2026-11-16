#!/usr/bin/env python3
"""
Copies the files the repository keeps OUTSIDE git (the ignored inputs and outputs of the repository policy:
reference projects, generated documents, renders, delivery packages) to the company store - by default the
OneDrive for Business folder <OneDrive>/<repo name>/ - keeping each file's repository path. One way only: it adds
new files and updates changed ones (sha256), never deletes anything in the store and never touches the repository.

Which files: every file git ignores (`git ls-files --others --ignored --exclude-standard`) plus tracked files that
match an ignore rule (left over from before the policy), minus the junk that is never stored (build/ scratch,
KiCad backups / autosaves / lock files / caches, Python caches, Office lock files, OS files, and the self-test outputs
of the skills under .claude/).

Usage:
    python .claude/skills/kicad-schematic/scripts/store_outside_git.py [--store DIR] [--only PREFIX ...] [--copy]
      (no --copy: list what would be copied - new / changed / same - and the totals)
Writes <store>/store_manifest.txt (repo path, bytes, sha256, date) on --copy.

Releases are not stored with this script: the release tool publishes each tagged package to
<store>/releases/<tag>/ (see OUTSIDE_GIT.md of the repository).
"""
import argparse, datetime, hashlib, os, re, shutil, subprocess, sys

JUNK = re.compile(r'^\.claude/|(^|/)(build|__pycache__|\.history|[^/]*-backups|\.git)/|'
                  r'(\.kicad_prl|fp-info-cache|\.lck|\.pyc|\.DS_Store|Thumbs\.db)$|'
                  r'(^|/)(_autosave-|~\$|#auto_saved_files#)')


def git(*args):
    r = subprocess.run(['git', *args], capture_output=True)
    if r.returncode:
        sys.exit('git ' + ' '.join(args) + ': ' + r.stderr.decode('utf-8', 'replace').strip())
    return [f for f in r.stdout.decode('utf-8').split('\0') if f]


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--store', help='store folder (default: %%OneDriveCommercial%%/<repo name>)')
    ap.add_argument('--only', nargs='*', default=[], help='repository path prefixes to limit the copy (e.g. reference/)')
    ap.add_argument('--copy', action='store_true', help='copy (default: list only)')
    a = ap.parse_args()
    root =subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True).stdout.strip()
    os.chdir(root)
    store = a.store
    if not store:
        od = os.environ.get('OneDriveCommercial') or os.environ.get('OneDrive')
        if not od:
            sys.exit('no --store given and no OneDrive folder in the environment (OneDriveCommercial / OneDrive)')
        store = os.path.join(od, os.path.basename(root))
    files = set(git('ls-files', '-z', '--others', '--ignored', '--exclude-standard'))
    files |= set(git('ls-files', '-z', '--cached', '--ignored', '--exclude-standard'))
    files = sorted(f for f in files if not JUNK.search(f) and os.path.isfile(f)
                   and (not a.only or any(f.startswith(p) for p in a.only)))
    new, changed, same = [], [], []
    for f in files:
        dst = os.path.join(store, f.replace('/', os.sep))
        if not os.path.isfile(dst):
            new.append(f)
        elif os.path.getsize(dst) != os.path.getsize(f) or sha(dst) != sha(f):
            changed.append(f)
        else:
            same.append(f)
    mb = lambda fs: sum(os.path.getsize(f) for f in fs) / 1e6
    print(f'store: {store}')
    print(f'new {len(new)} ({mb(new):.1f} MB), changed {len(changed)} ({mb(changed):.1f} MB), '
          f'already stored {len(same)}')
    for tag, fs in (('+', new), ('~', changed)):
        for f in fs:
            print(f'  {tag} {f}')
    if not a.copy:
        print('(list only - add --copy to copy)')
        return
    today = datetime.date.today().isoformat()
    for f in new + changed:
        dst = os.path.join(store, f.replace('/', os.sep))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(f, dst)
        if sha(dst) != sha(f):
            sys.exit('HASH MISMATCH after copy: ' + f)
    man = os.path.join(store, 'store_manifest.txt')
    rows = {}
    if os.path.isfile(man):
        for ln in open(man, encoding='utf-8'):
            if ln.strip() and not ln.startswith('#'):
                rows[ln.rstrip('\n').split('\t')[-1]] = ln.rstrip('\n')
    for f in new + changed:
        rows[f] = f'{os.path.getsize(f)}\t{sha(f)}\t{today}\t{f}'
    with open(man, 'w', encoding='utf-8', newline='\n') as fh:
        fh.write('# bytes\tsha256\tstored\trepo path (store_outside_git.py; the store keeps the repository paths)\n')
        fh.write('\n'.join(rows[k] for k in sorted(rows)) + '\n')
    print(f'copied and verified: {len(new) + len(changed)} files -> {store}')


if __name__ == '__main__':
    main()
