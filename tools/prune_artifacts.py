#!/usr/bin/env python3
"""Keep the newest complete Ruster builds, with a dry run unless --apply is set."""
import argparse
import json
import os
import subprocess

ARTIFACT_NAMES = {'Ruster-Windows', 'Ruster-Linux'}


def pages(repo, endpoint, key):
    result = subprocess.run(
        ['gh', 'api', f'repos/{repo}/actions/{endpoint}?per_page=100', '--paginate', '--slurp'],
        check=True, capture_output=True, text=True,
    )
    return [item for page in json.loads(result.stdout) for item in page[key]]


def retention_plan(artifacts, runs, keep=2):
    if keep < 1:
        raise ValueError('Keep at least one successful build')
    completed = {run['id']: run for run in runs if run['status'] == 'completed'}
    packages = [artifact for artifact in artifacts
                if artifact['name'] in ARTIFACT_NAMES and not artifact['expired']]
    names = {}
    for artifact in packages:
        names.setdefault(artifact['workflow_run']['id'], set()).add(artifact['name'])
    successful = sorted(
        (run for run in completed.values()
         if run['conclusion'] == 'success' and names.get(run['id']) == ARTIFACT_NAMES),
        key=lambda run: run['run_number'], reverse=True,
    )
    retained = {run['id'] for run in successful[:keep]}
    # Unknown workflows and active runs are left alone, including uploads in progress.
    obsolete = [artifact for artifact in packages
                if artifact['workflow_run']['id'] in completed
                and artifact['workflow_run']['id'] not in retained]
    return retained, obsolete


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', default=os.environ.get('GH_REPOSITORY')
                        or os.environ.get('GITHUB_REPOSITORY'))
    parser.add_argument('--keep', type=int, default=2)
    parser.add_argument('--apply', action='store_true', help='Delete the obsolete artifacts')
    args = parser.parse_args(argv)
    if not args.repo or args.repo.count('/') != 1:
        parser.error('Set --repo to owner/repository')
    if args.keep < 1:
        parser.error('--keep must be at least 1')
    # Fetch every page before deleting anything, so pagination cannot skip artifacts.
    artifacts = pages(args.repo, 'artifacts', 'artifacts')
    runs = pages(args.repo, 'workflows/package.yml/runs', 'workflow_runs')
    retained, obsolete = retention_plan(artifacts, runs, args.keep)
    print('Retaining complete builds from runs: ' + ', '.join(map(str, sorted(retained))))
    size = sum(artifact['size_in_bytes'] for artifact in obsolete)
    print(f'{len(obsolete)} obsolete artifacts, {size:,} bytes')
    for artifact in obsolete:
        print(f'{"Deleting" if args.apply else "Would delete"} {artifact["id"]}: {artifact["name"]}', flush=True)
        if args.apply:
            subprocess.run(['gh', 'api', '--method', 'DELETE',
                            f'repos/{args.repo}/actions/artifacts/{artifact["id"]}'], check=True)


if __name__ == '__main__':
    main()
