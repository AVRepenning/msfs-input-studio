"""Publish this project using Git's existing GitHub credentials; never print them."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from msfs_config import __version__


class APIError(RuntimeError):
    def __init__(self, status, message):
        self.status = status
        super().__init__(f'GitHub API returned {status}: {message}')


def credential():
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='never')
    result = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
                            text=True, capture_output=True, env=env)
    fields = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    token = fields.get('password')
    if result.returncode or not token:
        raise RuntimeError('No non-interactive GitHub credential is available in Git Credential Manager.')
    return token


def request(token, path, method='GET', payload=None, content_type=None):
    url = path if path.startswith('https://') else 'https://api.github.com' + path
    if urllib.parse.urlparse(url).hostname not in ('api.github.com', 'uploads.github.com'):
        raise ValueError('Unexpected GitHub API host.')
    data = payload if isinstance(payload, bytes) else json.dumps(payload).encode() if payload is not None else None
    headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json',
               'User-Agent': 'MSFSInputStudio-publisher', 'X-GitHub-Api-Version': '2022-11-28'}
    if data is not None:
        headers['Content-Type'] = content_type or 'application/json'
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    for attempt in range(3 if method == 'GET' else 1):
        try:
            with urllib.request.urlopen(req, timeout=30 if method == 'GET' else 60) as response:
                result = response.read()
                return json.loads(result) if result else {}
        except urllib.error.HTTPError as exc:
            # Return only API error data; never print headers or credentials.
            body = json.loads(exc.read().decode())
            raise APIError(exc.code, body.get('message', 'request failed')) from None
        except (TimeoutError, urllib.error.URLError):
            if attempt == (2 if method == 'GET' else 0):
                raise RuntimeError('GitHub did not respond. Rerun this command; release publication resumes safely.') from None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=('check', 'create', 'release'))
    parser.add_argument('--owner', required=True)
    parser.add_argument('--repository', default='msfs-input-studio')
    parser.add_argument('--version', default=__version__)
    parser.add_argument('--asset-directory', type=Path)
    parser.add_argument('--notes', type=Path, default=Path('RELEASE_NOTES.md'))
    args = parser.parse_args()
    token = credential()
    user = request(token, '/user')
    if user['login'].casefold() != args.owner.casefold():
        raise RuntimeError('The stored GitHub credential belongs to a different account.')
    if args.operation == 'check':
        print(json.dumps({'authenticated_account': user['login'], 'credential_source': 'Git Credential Manager'}))
        return
    if args.operation == 'create':
        repo = request(token, '/user/repos', 'POST', {'name': args.repository, 'private': True,
                       'description': 'Portable offline Windows editor for MSFS 2024 controller profiles. Initial test build.',
                       'auto_init': False})
        print(json.dumps({'repository': repo['full_name'], 'url': repo['html_url'], 'private': repo['private']}))
        return
    repo_name = args.owner + '/' + args.repository
    tag = 'v' + args.version
    asset_directory = args.asset_directory or Path('dist') / tag
    definition = {
        'tag_name': tag, 'target_commitish': 'main', 'name': tag + ' — controller setup and recording improvements',
        'prerelease': True, 'draft': False,
        'body': args.notes.read_text(encoding='utf-8')}
    try:
        release = request(token, f'/repos/{repo_name}/releases/tags/{tag}')
    except APIError as exc:
        if exc.status != 404:
            raise
        release = request(token, f'/repos/{repo_name}/releases', 'POST', definition)
    print(json.dumps({'release': release['html_url'], 'stage': 'uploading assets'}), flush=True)
    upload_url = release['upload_url'].split('{', 1)[0]
    assets = []
    for filename, content_type in [('MSFSInputStudio.exe', 'application/octet-stream'),
                                   ('MSFSInputStudio-source.zip', 'application/zip')]:
        data = (asset_directory / filename).read_bytes()
        existing = next((a for a in release['assets'] if a['name'] == filename), None)
        if existing:
            digest = 'sha256:' + hashlib.sha256(data).hexdigest()
            if existing['state'] != 'uploaded' or existing['size'] != len(data) or (existing.get('digest') and existing['digest'] != digest):
                raise RuntimeError(f'The existing release asset {filename} does not match the local file.')
            assets.append({'name': existing['name'], 'size': existing['size'], 'url': existing['browser_download_url']})
            print(json.dumps({'already_uploaded': filename}), flush=True)
            continue
        asset = request(token, upload_url + '?name=' + urllib.parse.quote(filename),
                        'POST', data, content_type)
        assets.append({'name': asset['name'], 'size': asset['size'], 'url': asset['browser_download_url']})
        print(json.dumps({'uploaded': asset['name'], 'bytes': asset['size']}), flush=True)
    print(json.dumps({'release': release['html_url'], 'prerelease': release['prerelease'], 'assets': assets}))


if __name__ == '__main__':
    main()
