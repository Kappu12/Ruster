#!/usr/bin/env python3
"""Remove old Actions packages only after a complete GitHub Release is published."""
import argparse
import json
import os
import subprocess

if __package__:
    from .release import get_release, verify_downloads
else:
    from release import get_release, verify_downloads

ARTIFACT_NAMES = {'Ruster-Windows', 'Ruster-Linux'}


def pages(repo, endpoint, key):
    result = subprocess.run(
        ['gh', 'api', f'repos/{repo}/actions/{endpoint}?per_page=100', '--paginate', '--slurp'],
        check=True, capture_output=True, text=True,
    )
    return [item for page in json.loads(result.stdout) for item in page[key]]


def cleanup_plan(artifacts, runs):
    completed = {run['id'] for run in runs if run['status'] == 'completed'}
    # Unknown workflows and active runs are left alone, including uploads in progress.
    return [artifact for artifact in artifacts
            if artifact['name'] in ARTIFACT_NAMES and not artifact['expired']
            and artifact['workflow_run']['id'] in completed]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', default=os.environ.get('GH_REPOSITORY')
                        or os.environ.get('GITHUB_REPOSITORY'))
    parser.add_argument('--released-tag', required=True)
    parser.add_argument('--apply', action='store_true', help='Delete the obsolete artifacts')
    args = parser.parse_args(argv)
    if not args.repo or args.repo.count('/') != 1:
        parser.error('Set --repo to owner/repository')
    # Never remove the only available downloads after a failed/partial release.
    verify_downloads(get_release(args.repo, args.released_tag), args.released_tag)
    # Fetch every page before deleting anything, so pagination cannot skip artifacts.
    artifacts = pages(args.repo, 'artifacts', 'artifacts')
    runs = pages(args.repo, 'workflows/package.yml/runs', 'workflow_runs')
    obsolete = cleanup_plan(artifacts, runs)
    size = sum(artifact['size_in_bytes'] for artifact in obsolete)
    print(f'{len(obsolete)} obsolete artifacts, {size:,} bytes')
    for artifact in obsolete:
        print(f'{"Deleting" if args.apply else "Would delete"} {artifact["id"]}: {artifact["name"]}', flush=True)
        if args.apply:
            subprocess.run(['gh', 'api', '--method', 'DELETE',
                            f'repos/{args.repo}/actions/artifacts/{artifact["id"]}'], check=True)


if __name__ == '__main__':
    main()
