#!/usr/bin/env python3
"""Publish tested app packages directly to a versioned GitHub Release."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time

PLATFORMS = ('windows-x64', 'linux-x64')
ROOT = Path(__file__).resolve().parents[1]


def validate_tag(tag):
    if not tag or not re.fullmatch(r'v\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?', tag):
        raise ValueError('Use a version tag such as v1.2.3 or v1.2.3-rc.1')
    return tag


def asset_name(tag, platform):
    validate_tag(tag)
    if platform not in PLATFORMS:
        raise ValueError('Unsupported release platform')
    return f'Rustmatics-{platform}-{tag}.zip'


def gh(*args):
    result = subprocess.run(['gh', *args], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f'GitHub CLI failed: {args[0]}')
    return result.stdout


def get_release(repo, tag, missing_ok=False):
    validate_tag(tag)
    # The by-tag REST endpoint only finds published releases. Listing also finds
    # drafts when authenticated with the workflow's contents:write permission.
    pages = json.loads(gh('api', f'repos/{repo}/releases?per_page=100', '--paginate', '--slurp'))
    release = next((release for page in pages for release in page if release['tag_name'] == tag), None)
    if release is None and not missing_ok:
        raise ValueError(f'Release does not exist: {tag}')
    return release


def verify_downloads(release, tag, published=True):
    validate_tag(tag)
    if release.get('tag_name') != tag:
        raise ValueError('Release does not match the requested version tag')
    if published and release.get('draft') is not False:
        raise ValueError('Release is not published; existing Actions downloads must be preserved')
    assets = {asset['name']: asset for asset in release.get('assets', [])}
    for platform in PLATFORMS:
        name = asset_name(tag, platform)
        asset = assets.get(name)
        if not asset or asset.get('state') != 'uploaded' or asset.get('size', 0) <= 0:
            raise ValueError(f'Release download is missing or incomplete: {name}')
    return release


def prepare(repo, tag):
    release = get_release(repo, tag, missing_ok=True)
    if release is not None:
        if release.get('tag_name') != tag or not release.get('draft'):
            raise ValueError('This version is already published; push a new version tag')
        print(f'Resuming draft release {tag}')
        return
    engine_version = json.loads((ROOT/'engine.lock.json').read_text(encoding='utf-8'))['version']
    ruster_source = f'https://github.com/{repo}/tree/{tag}'
    blender_source = f'https://download.blender.org/source/blender-{engine_version}.tar.xz'
    notes = ('The Windows x64 ZIP contains `Rustmatics.exe`. Extract the ZIP before opening the app. '
             'On Ubuntu x64, extract the Linux ZIP and run `./Rustmatics.sh`.\n\n'
             f'Corresponding source: [Rustmatics]({ruster_source}) and [Blender {engine_version}]({blender_source}).')
    args = ['release', 'create', tag, '--repo', repo, '--verify-tag', '--draft',
            '--title', f'Rustmatics {tag}', '--generate-notes', '--notes', notes]
    if '-' in tag:
        args.append('--prerelease')
    gh(*args)
    print(f'Created draft release {tag}')


def upload(repo, tag, platform, directory=Path('dist')):
    archive = Path(directory) / asset_name(tag, platform)
    if not archive.is_file() or not 0 < archive.stat().st_size < 2 ** 31:
        raise ValueError(f'Expected a nonempty release ZIP smaller than 2 GiB: {archive}')
    # A newly created draft may take a few seconds to appear in the list API.
    for delay in (1, 2, 4):
        release = get_release(repo, tag, missing_ok=True)
        if release is not None:
            break
        time.sleep(delay)
    else:
        release = get_release(repo, tag)
    if release.get('tag_name') != tag or not release.get('draft'):
        raise ValueError('Packages may only be uploaded to this version\'s draft release')
    # Only a draft's own platform asset is replaced when a failed job is retried.
    gh('release', 'upload', tag, str(archive), '--repo', repo, '--clobber')
    print(f'Uploaded {archive.name}')


def publish(repo, tag):
    release = verify_downloads(get_release(repo, tag), tag, published=False)
    if release['draft']:
        gh('release', 'edit', tag, '--repo', repo, '--draft=false')
    release = verify_downloads(get_release(repo, tag), tag)
    print(f'Published release: {release["html_url"]}')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'upload', 'publish'))
    parser.add_argument('--repo', default=os.environ.get('GITHUB_REPOSITORY'))
    parser.add_argument('--tag', default=os.environ.get('RELEASE_TAG'))
    parser.add_argument('--platform', choices=PLATFORMS)
    parser.add_argument('--directory', type=Path, default=Path('dist'), help='Directory containing the release ZIP')
    args = parser.parse_args(argv)
    if not args.repo or args.repo.count('/') != 1:
        parser.error('Set --repo or GITHUB_REPOSITORY to owner/repository')
    validate_tag(args.tag)
    if args.command == 'upload':
        if not args.platform:
            parser.error('Uploading requires --platform')
        upload(args.repo, args.tag, args.platform, args.directory)
    else:
        {'prepare': prepare, 'publish': publish}[args.command](args.repo, args.tag)


if __name__ == '__main__':
    main()
