import copy
import json
from types import SimpleNamespace

import pytest

from tools import release

TAG = 'v1.2.3'
REPO = 'example/repo'


def downloads(draft=False):
    return {'tag_name': TAG, 'draft': draft, 'html_url': 'https://github.com/example/repo/releases/tag/'+TAG,
            'assets': [{'name': release.asset_name(TAG, platform), 'state': 'uploaded', 'size': 100}
                       for platform in release.PLATFORMS]}


@pytest.mark.parametrize('tag', ['v1.2.3', 'v1.2.3-rc.1', 'v1.2.3+build.1'])
def test_version_tags_produce_versioned_platform_downloads(tag):
    assert release.asset_name(tag, 'linux-x64') == f'Ruster-linux-x64-{tag}.zip'


@pytest.mark.parametrize('tag', [None, '', 'main', 'v1', 'v1.2.3/extra', 'v1.2.3";echo unexpected'])
def test_invalid_tags_are_rejected_before_any_api_call(monkeypatch, tag):
    monkeypatch.setattr(release, 'gh', lambda *_args: pytest.fail('Must reject invalid tags before calling GitHub'))
    with pytest.raises(ValueError):
        release.prepare(REPO, tag)


def test_release_lookup_includes_drafts_across_pages(monkeypatch):
    def gh(*args):
        assert args == ('api', 'repos/example/repo/releases?per_page=100', '--paginate', '--slurp')
        return json.dumps([[{'tag_name': 'v9.9.9'}], [downloads(draft=True)]])
    monkeypatch.setattr(release, 'gh', gh)
    assert release.get_release(REPO, TAG) == downloads(draft=True)


def test_missing_release_and_api_failure_are_distinct(monkeypatch):
    monkeypatch.setattr(release, 'gh', lambda *_args: '[]')
    assert release.get_release(REPO, TAG, missing_ok=True) is None
    with pytest.raises(ValueError, match='does not exist'):
        release.get_release(REPO, TAG)
    def denied(*_args):raise RuntimeError('HTTP 403')
    monkeypatch.setattr(release, 'gh', denied)
    with pytest.raises(RuntimeError, match='403'):
        release.prepare(REPO, TAG)


@pytest.mark.parametrize('tag', [TAG, 'v1.2.3-rc.1'])
def test_prepare_creates_only_a_draft_from_an_existing_tag(monkeypatch, tag):
    calls = []
    monkeypatch.setattr(release, 'get_release', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(release, 'gh', lambda *args: calls.append(args))
    release.prepare(REPO, tag)
    call, = calls
    assert call[:10] == ('release', 'create', tag, '--repo', REPO, '--verify-tag', '--draft',
                        '--title', f'Ruster {tag}', '--generate-notes')
    assert call[10] == '--notes'
    assert f'https://github.com/{REPO}/tree/{tag}' in call[11]
    assert 'https://download.blender.org/source/blender-' in call[11]
    assert call[12:] == (('--prerelease',) if '-rc' in tag else ())


def test_prepare_reuses_draft_and_refuses_published_version(monkeypatch):
    monkeypatch.setattr(release, 'gh', lambda *_args: pytest.fail('Existing releases must not be recreated'))
    monkeypatch.setattr(release, 'get_release', lambda *_args, **_kwargs: downloads(draft=True))
    release.prepare(REPO, TAG)
    monkeypatch.setattr(release, 'get_release', lambda *_args, **_kwargs: downloads())
    with pytest.raises(ValueError, match='already published'):
        release.prepare(REPO, TAG)


def test_upload_uses_direct_release_assets_and_can_retry_a_draft(monkeypatch, tmp_path):
    archive = tmp_path / release.asset_name(TAG, 'windows-x64')
    archive.write_bytes(b'package')
    calls = []
    monkeypatch.setattr(release, 'get_release', lambda *_args: downloads(draft=True))
    monkeypatch.setattr(release, 'gh', lambda *args: calls.append(args))
    release.upload(REPO, TAG, 'windows-x64', tmp_path)
    assert calls == [('release', 'upload', TAG, str(archive), '--repo', REPO, '--clobber')]
    monkeypatch.setattr(release, 'get_release', lambda *_args: downloads())
    with pytest.raises(ValueError, match='draft'):
        release.upload(REPO, TAG, 'windows-x64', tmp_path)
    assert len(calls) == 1


def test_empty_or_missing_packages_never_upload(monkeypatch, tmp_path):
    monkeypatch.setattr(release, 'gh', lambda *_args: pytest.fail('Missing packages must not be uploaded'))
    for exists in (False, True):
        if exists:(tmp_path / release.asset_name(TAG, 'linux-x64')).touch()
        with pytest.raises(ValueError, match='nonempty'):
            release.upload(REPO, TAG, 'linux-x64', tmp_path)


def test_publish_waits_for_both_platforms_then_verifies_published_state(monkeypatch):
    calls = []
    states = iter([downloads(draft=True), downloads()])
    monkeypatch.setattr(release, 'get_release', lambda *_args: next(states))
    monkeypatch.setattr(release, 'gh', lambda *args: calls.append(args))
    release.publish(REPO, TAG)
    assert calls == [('release', 'edit', TAG, '--repo', REPO, '--draft=false')]


def test_partial_release_is_never_published(monkeypatch):
    data = copy.deepcopy(downloads(draft=True))
    data['assets'].pop()
    monkeypatch.setattr(release, 'get_release', lambda *_args: data)
    monkeypatch.setattr(release, 'gh', lambda *_args: pytest.fail('Partial release must remain a draft'))
    with pytest.raises(ValueError, match='missing or incomplete'):
        release.publish(REPO, TAG)


def test_failed_publication_is_not_reported_as_success(monkeypatch):
    monkeypatch.setattr(release, 'get_release', lambda *_args: downloads(draft=True))
    monkeypatch.setattr(release, 'gh', lambda *_args: None)
    with pytest.raises(ValueError, match='not published'):
        release.publish(REPO, TAG)


def test_github_errors_preserve_the_server_message(monkeypatch):
    monkeypatch.setattr(release.subprocess, 'run', lambda *_args, **_kwargs:
                        SimpleNamespace(returncode=1, stderr='gh: HTTP 403', stdout=''))
    with pytest.raises(RuntimeError, match='HTTP 403'):
        release.gh('release', 'create', TAG)
