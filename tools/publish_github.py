"""Publish this project using Git's existing GitHub credentials; never print them."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.parse
import urllib.request


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
    try:
        with urllib.request.urlopen(req, timeout=180) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        # Return only API error data; never print request headers or credentials.
        body = json.loads(exc.read().decode())
        raise RuntimeError(f'GitHub API returned {exc.code}: {body.get("message", "request failed")}') from None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=('check', 'create', 'release'))
    parser.add_argument('--owner', required=True)
    parser.add_argument('--repository', default='msfs-input-studio')
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
    release = request(token, f'/repos/{repo_name}/releases', 'POST', {
        'tag_name': 'v0.1.0', 'target_commitish': 'main', 'name': 'v0.1.0 — initial Windows test build',
        'prerelease': True, 'draft': False,
        'body': 'Portable Windows app for editing MSFS 2024 controller profiles with the simulator closed.\n\n'
                'Includes Windows controller detection, searchable actions, individual and guided recording, '
                'editable input names, primary/secondary bindings, axis tuning, input search and conflict filtering.\n\n'
                'Validation: 14 automated tests passed, including round trips across 48 real profile exports; '
                'the packaged executable passed startup and controller initialization. '
                'XRAY hardware capture and generated-profile import/in-flight behavior still need user testing. '
                'Full settings/developer-editor parity remains in progress; see FEATURE_MATRIX.md.\n\n'
                'Download MSFSInputStudio.exe to run without installing Python. '
                'MSFSInputStudio-source.zip contains the corresponding source and licensed reference fixtures.'})
    upload_url = release['upload_url'].split('{', 1)[0]
    assets = []
    for filename, content_type in [('MSFSInputStudio.exe', 'application/octet-stream'),
                                   ('MSFSInputStudio-source.zip', 'application/zip')]:
        data = (Path('dist') / filename).read_bytes()
        asset = request(token, upload_url + '?name=' + urllib.parse.quote(filename),
                        'POST', data, content_type)
        assets.append({'name': asset['name'], 'size': asset['size'], 'url': asset['browser_download_url']})
        print(json.dumps({'uploaded': asset['name'], 'bytes': asset['size']}), flush=True)
    print(json.dumps({'release': release['html_url'], 'prerelease': release['prerelease'], 'assets': assets}))


if __name__ == '__main__':
    main()
