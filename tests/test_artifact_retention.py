import json
from types import SimpleNamespace

import pytest

from tools import prune_artifacts


def run(number, conclusion='success', status='completed'):
    return {'id': number, 'run_number': number, 'conclusion': conclusion, 'status': status}


def artifact(number, name='Ruster-Windows', expired=False):
    return {'id': f'{number}-{name}', 'workflow_run': {'id': number},
            'name': name, 'expired': expired, 'size_in_bytes': 10}


def pair(number):
    return [artifact(number), artifact(number, 'Ruster-Linux')]


def test_keep_two_newest_complete_successful_builds():
    artifacts = pair(1) + pair(3) + pair(2)
    retained, obsolete = prune_artifacts.retention_plan(artifacts, [run(2), run(1), run(3)])
    assert retained == {2, 3}
    assert obsolete == pair(1)


def test_failed_and_incomplete_builds_do_not_displace_complete_downloads():
    artifacts = pair(1) + pair(2) + [artifact(3)] + pair(4)
    retained, obsolete = prune_artifacts.retention_plan(
        artifacts, [run(1), run(2), run(3), run(4, 'failure')])
    assert retained == {1, 2}
    assert obsolete == [artifact(3)] + pair(4)


def test_active_unknown_unrelated_and_expired_artifacts_are_untouched():
    artifacts = (pair(1) + pair(2) + pair(3) + pair(4)
                 + [artifact(1, 'diagnostics'), artifact(5, expired=True)])
    retained, obsolete = prune_artifacts.retention_plan(
        artifacts, [run(1), run(2), run(3, None, 'in_progress'), run(5)])
    assert retained == {1, 2}
    assert obsolete == []


def test_fewer_than_two_complete_builds_are_preserved():
    assert prune_artifacts.retention_plan(pair(1), [run(1)]) == ({1}, [])
    assert prune_artifacts.retention_plan([], []) == (set(), [])


def test_custom_keep_count_and_invalid_count():
    retained, obsolete = prune_artifacts.retention_plan(pair(1) + pair(2), [run(1), run(2)], 1)
    assert retained == {2}
    assert obsolete == pair(1)
    with pytest.raises(ValueError):
        prune_artifacts.retention_plan([], [], 0)


def test_all_api_pages_are_combined(monkeypatch):
    def invoke(command, **kwargs):
        assert command == ['gh', 'api', 'repos/example/repo/actions/artifacts?per_page=100',
                           '--paginate', '--slurp']
        assert kwargs['check'] is True
        return SimpleNamespace(stdout=json.dumps([{'artifacts': pair(1)}, {'artifacts': pair(2)}]))
    monkeypatch.setattr(prune_artifacts.subprocess, 'run', invoke)
    assert prune_artifacts.pages('example/repo', 'artifacts', 'artifacts') == pair(1) + pair(2)


@pytest.mark.parametrize('apply', [False, True])
def test_cli_only_deletes_planned_artifacts_with_explicit_apply(monkeypatch, apply):
    def pages(repo, endpoint, key):
        assert repo == 'example/repo'
        return pair(1) + pair(2) + pair(3) if key == 'artifacts' else [run(1), run(2), run(3)]
    calls = []
    monkeypatch.setattr(prune_artifacts, 'pages', pages)
    monkeypatch.setattr(prune_artifacts.subprocess, 'run', lambda command, **_kwargs: calls.append(command))
    prune_artifacts.main(['--repo', 'example/repo', *(['--apply'] if apply else [])])
    assert calls == ([['gh', 'api', '--method', 'DELETE',
                       f'repos/example/repo/actions/artifacts/{item["id"]}']
                      for item in pair(1)] if apply else [])
