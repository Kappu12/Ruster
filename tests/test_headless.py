"""CLI profile isolation and OS ownership, without requiring Blender."""
import os
from pathlib import Path
import subprocess
import sys

from ruster.core import headless, settings


def test_default_headless_profile_is_separate_and_stable(tmp_path, monkeypatch):
    monkeypatch.delenv('RUSTER_USER_DIR', raising=False)
    monkeypatch.setattr(settings, 'user_root', lambda: Path(os.environ.get('RUSTER_USER_DIR', tmp_path)))
    assert headless.configure_user_dir(headless=True) == tmp_path / 'headless'
    assert headless.configure_user_dir(headless=True) == tmp_path / 'headless'
    assert headless.configure_user_dir(tmp_path / 'custom', headless=True) == tmp_path / 'custom'


def test_profile_lock_blocks_other_processes_and_releases(tmp_path):
    code = ('import sys; from ruster.core.headless import ProfileLock; '
            'lock=ProfileLock(sys.argv[1]); lock.__enter__(); lock.__exit__()')
    command = [sys.executable, '-c', code, str(tmp_path)]
    with headless.ProfileLock(tmp_path):
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        assert result.returncode != 0 and 'already owns this profile' in result.stderr
    result = subprocess.run(command, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
