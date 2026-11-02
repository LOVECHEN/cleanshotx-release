"""只处理公开官方安装包；下载源和异常中的 URL 不输出到公共日志。"""
import argparse
from datetime import datetime
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import string
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

REPOSITORY = 'LOVECHEN/cleanshotx-release'
VERSION = re.compile(r'[0-9]{1,4}(?:\.[0-9]{1,4}){1,3}\Z')
MIN_BYTES = 1024 * 1024
MAX_BYTES = 1024 * 1024 * 1024


class MirrorError(Exception):
    pass


def version_key(version):
    if not VERSION.fullmatch(version):
        raise MirrorError('Invalid version identifier')
    parts = tuple(map(int, version.split('.')))
    return parts + (0,) * (4 - len(parts))


class VersionParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.depth = 0
        self.parts = []
        self.versions = set()
        self.dates = {}
        self.pending_date = None
        self.capture = None

    def handle_starttag(self, tag, attrs):
        classes = (dict(attrs).get('class') or '').split()
        if tag == 'div' and 'version' in classes:
            self.pending_date = None
        if self.depth:
            if tag not in ('br', 'img', 'input', 'hr', 'meta', 'link', 'wbr'):
                self.depth += 1
        elif (tag == 'div' and ('number' in classes or 'date' in classes)) or tag in ('h2', 'h3'):
            self.depth, self.parts = 1, []
            self.capture = 'date' if 'date' in classes else 'version'

    def handle_endtag(self, tag):
        if tag in ('br', 'img', 'input', 'hr', 'meta', 'link', 'wbr'):
            return
        if self.depth:
            self.depth -= 1
            if not self.depth:
                text = ' '.join(''.join(self.parts).split())
                if self.capture == 'date':
                    try:
                        self.pending_date = datetime.strptime(text, '%d %B, %Y').date().isoformat()
                    except ValueError:
                        raise MirrorError('Changelog contains an invalid release date') from None
                elif VERSION.fullmatch(text):
                    if text in self.dates and self.dates[text] != self.pending_date:
                        raise MirrorError('Changelog contains conflicting version dates')
                    self.versions.add(text)
                    self.dates[text] = self.pending_date
                    self.pending_date = None

    def handle_data(self, text):
        if self.depth:
            self.parts.append(text)


def parse_versions(text):
    return list(parse_catalog(text))


def parse_catalog(text):
    parser = VersionParser()
    parser.feed(text)
    if not parser.versions or len(parser.versions) > 300:
        raise MirrorError('Changelog has no valid bounded version inventory')
    return {version: parser.dates[version] for version in sorted(parser.versions, key=lambda value: (version_key(value), value), reverse=True)}


def https_url(url):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise MirrorError('Source must be an HTTPS URL without embedded credentials')
    return url


def sources(env=os.environ):
    changelog = env.get('SOURCE_CHANGELOG', '').strip()
    template = env.get('SOURCE_DOWNLOAD_TEMPLATE', '').strip()
    fields = [(field, spec, conversion) for _, field, spec, conversion in string.Formatter().parse(template) if field is not None]
    if fields != [('version', '', None)]:
        raise MirrorError('Download template must contain exactly one version placeholder')
    https_url(changelog)
    https_url(template.format(version='1.0'))
    return changelog, template


def request(url):
    return urllib.request.urlopen(urllib.request.Request(https_url(url), headers={'User-Agent': 'Mozilla/5.0'}), timeout=120)


def discover(changelog):
    return list(discover_catalog(changelog))


def discover_catalog(changelog):
    for attempt in range(3):
        try:
            with request(changelog) as response:
                https_url(response.geturl())
                data = response.read(2 * 1024 * 1024 + 1)
            if len(data) > 2 * 1024 * 1024:
                raise MirrorError('Changelog exceeds size limit')
            return parse_catalog(data.decode('utf-8'))
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == 2:
                raise MirrorError('Official changelog request failed') from None
            time.sleep(attempt + 1)
    raise MirrorError('Official changelog unavailable')


def download(url, path):
    for attempt in range(3):
        try:
            digest, size = hashlib.sha256(), 0
            with request(url) as response, path.open('wb') as output:
                https_url(response.geturl())
                expected = response.headers.get('Content-Length')
                expected = int(expected) if expected is not None else None
                if expected is not None and not MIN_BYTES <= expected <= MAX_BYTES:
                    raise MirrorError('Installer content length is outside bounds')
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    size += len(block)
                    if size > MAX_BYTES:
                        raise MirrorError('Installer exceeds size limit')
                    output.write(block)
                    digest.update(block)
            if size < MIN_BYTES or (expected is not None and size != expected):
                raise MirrorError('Installer content length mismatch')
            with path.open('rb') as handle:
                handle.seek(-512, 2)
                if handle.read(4) != b'koly':
                    raise MirrorError('Installer does not have a UDIF trailer')
            return size, digest.hexdigest()
        except urllib.error.HTTPError as error:
            if error.code in (403, 404, 410):
                return None
            if attempt == 2:
                raise MirrorError('Official installer request failed') from None
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == 2:
                raise MirrorError('Official installer download failed') from None
        time.sleep(attempt + 1)
    raise MirrorError('Official installer unavailable')


def gh(*args, missing=False):
    result = subprocess.run(['gh', *args], capture_output=True, text=True)
    if result.returncode:
        if missing and 'HTTP 404' in result.stderr:
            return None
        raise MirrorError('GitHub operation failed: ' + args[0])
    return result.stdout


def api(path, missing=False):
    value = gh('api', path, missing=missing)
    return json.loads(value) if value is not None else None


def release_index():
    # 尚未创建标签的草稿不能通过 /releases/tags/{tag} 查到，列表接口才能覆盖。
    groups = json.loads(gh('api', f'repos/{REPOSITORY}/releases?per_page=100', '--paginate', '--slurp'))
    return {release['tag_name']: release for group in groups for release in group}


def check_target(env=os.environ):
    if env.get('GITHUB_REPOSITORY') != REPOSITORY:
        raise MirrorError('Writes are restricted to the configured public release repository')


def complete(release, version):
    if not release:
        return False
    sizes = {asset['name']: asset['size'] for asset in release.get('assets', []) if asset.get('state') == 'uploaded'}
    return (sizes.get(f'CleanShot-X-{version}.dmg', 0) >= MIN_BYTES
            and sizes.get('SHA256SUMS.txt', 0) > 0)


def release_notes(version, date, checksum):
    lines = [f'发布日期：{date}', ''] if date else []
    lines.extend(['| SHA-256 | 文件名 |', '|---|---|',
                  f'| `{checksum or "见 SHA256SUMS.txt"}` | `CleanShot-X-{version}.dmg` |'])
    return '\n'.join(lines) + '\n'


def refresh_release_notes(release, version, date):
    body = release.get('body') or ''
    installer = next(asset for asset in release['assets'] if asset['name'] == f'CleanShot-X-{version}.dmg')
    digest = installer.get('digest') or ''
    checksum = digest[7:] if re.fullmatch(r'sha256:[0-9a-f]{64}', digest) else None
    updated = release_notes(version, date, checksum)
    if updated != body:
        with tempfile.TemporaryDirectory(prefix='cleanshotx-notes-', dir=os.environ.get('RUNNER_TEMP')) as directory:
            path = Path(directory) / 'notes.md'
            path.write_text(updated)
            gh('release', 'edit', f'mac-{version}', '-R', REPOSITORY, '--notes-file', str(path))
        time.sleep(1)
        print(f'Updated notes: {version}', flush=True)
    if any(asset['name'] == 'metadata.json' for asset in release['assets']):
        gh('release', 'delete-asset', f'mac-{version}', 'metadata.json', '-R', REPOSITORY, '--yes')
        time.sleep(1)
        print(f'Removed metadata asset: {version}', flush=True)


def sync(max_per_run, only_version):
    check_target()
    changelog, template = sources()
    catalog = discover_catalog(changelog)
    versions = list(catalog)
    latest = versions[0]
    if only_version:
        version_key(only_version)
        if only_version not in versions:
            raise MirrorError('Requested version is absent from the official changelog')
        versions = [only_version]
    made = 0
    releases = release_index()
    print(f'Discovered {len(versions)} versions; newest={latest}', flush=True)
    for version in versions:
        tag = f'mac-{version}'
        release = releases.get(tag)
        if complete(release, version) and not release['draft']:
            refresh_release_notes(release, version, catalog[version])
            print(f'Complete: {tag}', flush=True)
            continue
        if made >= max_per_run:
            break
        with tempfile.TemporaryDirectory(prefix='cleanshotx-mirror-', dir=os.environ.get('RUNNER_TEMP')) as directory:
            root = Path(directory)
            filename = f'CleanShot-X-{version}.dmg'
            installer = root / filename
            result = download(template.format(version=version), installer)
            if result is None:
                if version == latest:
                    raise MirrorError('Newest official installer is not available yet')
                print(f'Unavailable historical version: {version}', flush=True)
                continue
            size, checksum = result
            # 已发布附件若与当前官方文件不符，不静默覆盖历史归档。
            if release:
                for asset in release['assets']:
                    if asset['name'] == filename and (asset['size'] != size or asset.get('digest') not in (None, 'sha256:' + checksum)):
                        raise MirrorError('Existing installer differs from the official download')
            sums = root / 'SHA256SUMS.txt'
            sums.write_text(f'{checksum}  {filename}\n')
            notes = root / 'notes.md'
            notes.write_text(release_notes(version, catalog[version], checksum))
            if not release:
                gh('release', 'create', tag, '-R', REPOSITORY, '--target', 'main', '--draft', '--title', f'CleanShot X {version} · macOS', '--notes-file', str(notes))
            gh('release', 'upload', tag, str(installer), str(sums), '-R', REPOSITORY, '--clobber')
            if release and any(asset['name'] == 'metadata.json' for asset in release['assets']):
                gh('release', 'delete-asset', tag, 'metadata.json', '-R', REPOSITORY, '--yes')
            uploaded = release_index().get(tag)
            if not complete(uploaded, version):
                raise MirrorError('Release upload is incomplete')
            for asset in uploaded['assets']:
                if asset['name'] == filename and (asset['size'] != size or asset.get('digest') not in (None, 'sha256:' + checksum)):
                    raise MirrorError('Uploaded installer digest mismatch')
            gh('release', 'edit', tag, '-R', REPOSITORY, '--draft=false', '--latest=' + str(version == latest).lower(), '--notes-file', str(notes))
            made += 1
            print(f'Published: {tag}, bytes={size}, sha256={checksum}', flush=True)
    current = release_index().get(f'mac-{latest}')
    if complete(current, latest) and not current['draft']:
        marked = api(f'repos/{REPOSITORY}/releases/latest', missing=True)
        if not marked or marked['tag_name'] != f'mac-{latest}':
            gh('release', 'edit', f'mac-{latest}', '-R', REPOSITORY, '--latest=true')
    print(f'Completed {made} new or repaired releases', flush=True)


def keepalive():
    check_target()
    last_commit = int(subprocess.check_output(['git', 'log', '-1', '--format=%ct'], text=True).strip())
    if time.time() - last_commit > 50 * 86400:
        subprocess.run(['git', '-c', 'user.name=github-actions[bot]', '-c', 'user.email=41898282+github-actions[bot]@users.noreply.github.com',
                        'commit', '--allow-empty', '-m', 'chore: keep scheduled mirror active'], check=True)
        subprocess.run(['git', 'push', 'origin', 'HEAD:main'], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('discover', 'sync', 'keepalive'))
    args = parser.parse_args()
    try:
        if args.action == 'discover':
            changelog, _ = sources()
            print('\n'.join(discover(changelog)))
        elif args.action == 'sync':
            limit = int(os.environ.get('MAX_PER_RUN', '8'))
            if not 1 <= limit <= 32:
                raise MirrorError('MAX_PER_RUN must be between 1 and 32')
            sync(limit, os.environ.get('ONLY_VERSION', '').strip())
        else:
            keepalive()
    except (MirrorError, ValueError, KeyError, UnicodeError, subprocess.CalledProcessError):
        parser.exit(1, 'Mirror operation failed; source details suppressed\n')
    except Exception:
        parser.exit(1, 'Unexpected mirror failure; no source details logged\n')


if __name__ == '__main__':
    main()
