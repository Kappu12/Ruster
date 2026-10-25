import copy
import json
from types import SimpleNamespace

import pytest

from tools import prune_artifacts
from tools.release import asset_name

TAG = 'v1.2.3'


def run(number, status='completed'):
    return {'id': number, 'status': status}


def artifact(number, name='Ruster-Windows', expired=False):
    return {'id': f'{number}-{name}', 'workflow_run': {'id': number},
            'name': name, 'expired': expired, 'size_in_bytes': 10}


def pair(number):
    return [artifact(number), artifact(number, 'Ruster-Linux')]


def published_release():
    return {'tag_name': TAG, 'draft': False, 'assets': [
        {'name': asset_name(TAG, platform), 'state': 'uploaded', 'size': 100}
        for platform in ('windows-x64', 'linux-x64')]}


def test_all_completed_build_packages_are_removed_after_release():
    assert prune_artifacts.cleanup_plan(pair(1) + pair(2), [run(1), run(2)]) == pair(1) + pair(2)


def test_active_unknown_unrelated_and_expired_artifacts_are_untouched():
    artifacts = pair(1) + pair(2) + pair(3) + [artifact(1, 'diagnostics'), artifact(4, expired=True)]
    assert prune_artifacts.cleanup_plan(artifacts, [run(1), run(2, 'in_progress'), run(4)]) == pair(1)


def test_all_api_pages_are_combined_before_deletion(monkeypatch):
    def invoke(command, **kwargs):
        assert command == ['gh', 'api', 'repos/example/repo/actions/artifacts?per_page=100',
                           '--paginate', '--slurp']
        assert kwargs['check'] is True
        return SimpleNamespace(stdout=json.dumps([{'artifacts': pair(1)}, {'artifacts': pair(2)}]))
    monkeypatch.setattr(prune_artifacts.subprocess, 'run', invoke)
    assert prune_artifacts.pages('example/repo', 'artifacts', 'artifacts') == pair(1) + pair(2)


@pytest.mark.parametrize('apply', [False, True])
def test_cli_only_deletes_old_packages_with_verified_release_and_explicit_apply(monkeypatch, apply):
    events = []
    def release(repo, tag):
        assert (repo, tag) == ('example/repo', TAG)
        events.append('verify')
        return published_release()
    def pages(repo, endpoint, key):
        assert events == ['verify']
        return pair(1) + pair(2) if key == 'artifacts' else [run(1), run(2)]
    calls = []
    monkeypatch.setattr(prune_artifacts, 'get_release', release)
    monkeypatch.setattr(prune_artifacts, 'pages', pages)
    monkeypatch.setattr(prune_artifacts.subprocess, 'run', lambda command, **_kwargs: calls.append(command))
    prune_artifacts.main(['--repo', 'example/repo', '--released-tag', TAG, *(['--apply'] if apply else [])])
    assert calls == ([['gh', 'api', '--method', 'DELETE',
                       f'repos/example/repo/actions/artifacts/{item["id"]}']
                      for item in pair(1) + pair(2)] if apply else [])


@pytest.mark.parametrize('problem', ['draft', 'missing-platform', 'empty', 'uploading', 'wrong-tag'])
def test_incomplete_release_prevents_even_listing_artifacts(monkeypatch, problem):
    release = copy.deepcopy(published_release())
    if problem == 'draft':release['draft'] = True
    elif problem == 'missing-platform':release['assets'].pop()
    elif problem == 'empty':release['assets'][0]['size'] = 0
    elif problem == 'uploading':release['assets'][0]['state'] = 'new'
    else:release['tag_name'] = 'v9.9.9'
    monkeypatch.setattr(prune_artifacts, 'get_release', lambda *_args: release)
    monkeypatch.setattr(prune_artifacts, 'pages', lambda *_args: pytest.fail('Must verify release before inspecting artifacts'))
    with pytest.raises(ValueError):
        prune_artifacts.main(['--repo', 'example/repo', '--released-tag', TAG, '--apply'])
