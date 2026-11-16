#!/usr/bin/env python3
"""update_skills.py - keeps a project's .claude/skills/<skill>/ copies at the newest release of the skills repository
on Bitbucket. Bitbucket version of templates/update-skills.yml (GitHub). Copy it to <project>/tools/update_skills.py
and run it from the project's bitbucket-pipelines.yml (templates/bitbucket-pipelines-update-skills.yml), on a
schedule or by hand.

For every .claude/skills/<skill>/SKILL.md, the newest release <skill>-<X.Y.Z>.zip in the skills repository's
Downloads is compared with the "| Skill version |" row. For each newer release:
  1. downloads <skill>-<X.Y.Z>.zip and .sha256 and checks the sha256;
  2. on a new branch skills/<skill>-<X.Y.Z> from the base branch, replaces .claude/skills/<skill>/ with the zip,
     commits "Update <skill> to X.Y.Z" and pushes the branch;
  3. opens a pull request to the base branch whose description is the release notes
     (<skill>-<X.Y.Z>.notes.md from the Downloads, when present) and a warning when the project's copy is a local
     variant (a "## X.Y.Z-<project>.N" heading at the top of its CHANGELOG.md).
Nothing is merged. A skill whose branch already exists is skipped (its PR is pending).

Environment:
  SKILLS_REPO        <workspace>/<repo_slug> of the skills repository (required)
  SKILLS_TOKEN       access token that can read the skills repository (repository or workspace access token,
                     scope repository); Bearer auth. Or SKILLS_USER + SKILLS_TOKEN for an app password (Basic).
  PROJECT_REPO       <workspace>/<repo_slug> of this project (default: $BITBUCKET_REPO_FULL_NAME)
  PROJECT_TOKEN      token with "pullrequest:write" on this project (default: SKILLS_TOKEN); PROJECT_USER for Basic
  SKILLS_BASE_BRANCH branch the PRs go to (default: the current branch)
  BB_API             API root (default https://api.bitbucket.org/2.0; the self-test points it at a local server)

    python tools/update_skills.py [--only skill ...] [--dry-run]
--dry-run lists what would be updated and changes nothing (no branch, no push, no PR).
Exit 0 = done (or nothing to do), 1 = an error.
"""
import base64
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile

API = os.environ.get('BB_API', 'https://api.bitbucket.org/2.0').rstrip('/')
VER = re.compile(r'^\|\s*Skill version\s*\|\s*(\d+\.\d+\.\d+)', re.M)


def vkey(v):
    return tuple(int(x) for x in v.split('.'))


class _NoAuthOnOtherHost(urllib.request.HTTPRedirectHandler):
    """Downloads answer with a redirect to a storage host: the Authorization header must not follow it there."""
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and urllib.parse.urlsplit(newurl).netloc != urllib.parse.urlsplit(req.full_url).netloc:
            new.headers.pop('Authorization', None)
            new.unredirected_hdrs.pop('Authorization', None)
        return new


OPENER = urllib.request.build_opener(_NoAuthOnOtherHost)


def auth(user, token):
    if not token:
        return {}
    if user:
        return {'Authorization': 'Basic ' + base64.b64encode(f'{user}:{token}'.encode()).decode()}
    return {'Authorization': 'Bearer ' + token}


def http(url, hdr, data=None, method=None):
    req = urllib.request.Request(url, data=data, method=method, headers=dict(hdr))
    if data is not None:
        req.add_header('Content-Type', 'application/json')
    with OPENER.open(req, timeout=60) as r:
        return r.read()


def downloads(repo, hdr):
    """{file name: download URL} of a repository's Downloads (all pages)."""
    out, url = {}, f'{API}/repositories/{repo}/downloads?pagelen=100'
    while url:
        page = json.loads(http(url, hdr))
        for v in page.get('values', []):
            out[v['name']] = v['links']['self']['href']
        url = page.get('next')
    return out


def git(*args, check=True):
    r = subprocess.run(['git', *args], capture_output=True, text=True, encoding='utf-8', errors='replace')
    if check and r.returncode:
        raise RuntimeError(f'git {" ".join(args)}: {r.stderr.strip()}')
    return r.stdout.strip()


def main():
    a = sys.argv[1:]
    dry = '--dry-run' in a
    only = a[a.index('--only') + 1:] if '--only' in a else []
    only = [x for x in only if not x.startswith('--')]
    skills_repo = os.environ.get('SKILLS_REPO', '')
    if not re.fullmatch(r'[\w.-]+/[\w.-]+', skills_repo):
        print('ERROR: SKILLS_REPO must be <workspace>/<repo_slug> of the skills repository')
        return 1
    s_hdr = auth(os.environ.get('SKILLS_USER'), os.environ.get('SKILLS_TOKEN'))
    if not s_hdr:
        print('ERROR: SKILLS_TOKEN is not set (a token that can read %s)' % skills_repo)
        return 1
    project = os.environ.get('PROJECT_REPO') or os.environ.get('BITBUCKET_REPO_FULL_NAME', '')
    p_hdr = auth(os.environ.get('PROJECT_USER', os.environ.get('SKILLS_USER')),
                 os.environ.get('PROJECT_TOKEN') or os.environ.get('SKILLS_TOKEN'))
    base = os.environ.get('SKILLS_BASE_BRANCH') or git('rev-parse', '--abbrev-ref', 'HEAD')
    try:
        files = downloads(skills_repo, s_hdr)
    except urllib.error.HTTPError as e:
        print(f'ERROR: Downloads of {skills_repo}: HTTP {e.code} - check SKILLS_REPO and the token')
        return 1
    rel = {}
    for name in files:
        m = re.fullmatch(r'(.+)-(\d+\.\d+\.\d+)\.zip', name)
        if m:
            rel.setdefault(m.group(1), []).append(m.group(2))
    errors = 0
    for d in sorted(os.listdir('.claude/skills')) if os.path.isdir('.claude/skills') else []:
        sdir = os.path.join('.claude', 'skills', d)
        if not os.path.isfile(os.path.join(sdir, 'SKILL.md')) or (only and d not in only):
            continue
        m = VER.search(open(os.path.join(sdir, 'SKILL.md'), encoding='utf-8').read())
        have = m.group(1) if m else None
        if d not in rel:
            print(f'{d}: no release in {skills_repo}')
            continue
        want = max(rel[d], key=vkey)
        if have and vkey(have) >= vkey(want):
            print(f'{d}: {have} is current')
            continue
        branch = f'skills/{d}-{want}'
        if git('ls-remote', '--heads', 'origin', branch, check=False):
            print(f'{d}: branch {branch} already exists - PR pending')
            continue
        print(f'{d}: {have or "?"} -> {want}' + (' (dry run)' if dry else ''))
        if dry:
            continue
        try:
            zname, sname = f'{d}-{want}.zip', f'{d}-{want}.sha256'
            if sname not in files:
                raise RuntimeError(f'{sname} missing in the Downloads')
            blob = http(files[zname], s_hdr)
            expect = http(files[sname], s_hdr).decode().split()[0]
            if hashlib.sha256(blob).hexdigest() != expect:
                raise RuntimeError(f'{zname}: sha256 mismatch')
            notes = http(files[f'{d}-{want}.notes.md'], s_hdr).decode('utf-8') if f'{d}-{want}.notes.md' in files else ''
            cl = os.path.join(sdir, 'CHANGELOG.md')
            head = next((ln for ln in open(cl, encoding='utf-8') if ln.startswith('## ')), '') if os.path.isfile(cl) else ''
            variant = head[3:].split()[0] if re.match(r'## \d+\.\d+\.\d+-', head) else ''
            git('switch', '-q', '-c', branch, base)
            git('rm', '-q', '-r', '--', sdir)
            if os.path.isdir(sdir):
                shutil.rmtree(sdir)
            with zipfile.ZipFile(io.BytesIO(blob)) as z:
                bad = [n for n in z.namelist() if not n.startswith(d + '/') or '..' in n.split('/')]
                if bad:
                    raise RuntimeError(f'{zname}: entries outside {d}/: {bad[:3]}')
                z.extractall(os.path.join('.claude', 'skills'))
            git('add', '-A', '--', sdir)
            git('commit', '-q', '-m', f'Update {d} to {want}', '-m', f'From {skills_repo} release {d}-{want}.')
            git('push', '-q', 'origin', branch)
            body = (f'Updates `.claude/skills/{d}` from {have or "unknown"} to **{want}**, from the release '
                    f'`{zname}` of {skills_repo} (sha256 checked).\n\n')
            if variant:
                body += (f'> **This project had a local variant (`{variant}`). The update replaces it; carry the local '
                         f'change upstream or re-apply it before merging.**\n\n')
            body += '### Changes\n\n' + (notes or '(no release notes in the Downloads)')
            if project and p_hdr:
                pr = json.loads(http(f'{API}/repositories/{project}/pullrequests', p_hdr, json.dumps({
                    'title': f'Update {d} to {want}', 'description': body, 'close_source_branch': True,
                    'source': {'branch': {'name': branch}}, 'destination': {'branch': {'name': base}}}).encode(),
                    'POST'))
                print(f'  PR #{pr.get("id")}: {pr.get("links", {}).get("html", {}).get("href", "")}')
            else:
                print(f'  branch {branch} pushed; no PROJECT_REPO / token - open the PR by hand')
        except (RuntimeError, urllib.error.URLError, zipfile.BadZipFile, OSError) as e:
            errors += 1
            print(f'ERROR {d}: {e}')
        finally:
            if git('rev-parse', '--abbrev-ref', 'HEAD', check=False) != base:
                git('reset', '-q', '--hard', check=False)
                git('switch', '-q', base, check=False)
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main())
