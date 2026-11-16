"""Launcher lifecycle regressions; no user editor or game process is touched."""
from pathlib import Path
import pytest
import launch


@pytest.mark.parametrize('code',[-1,0xFFFFFFFF])
def test_windows_forced_stop_after_ready_does_not_claim_startup_failed(tmp_path,monkeypatch,code):
    monkeypatch.setattr(launch.sys,'platform','win32')
    log=tmp_path/'startup.log';log.write_text('RUSTER_READY 0.11.2 / Blender\nproject opened\n')
    assert launch.check_exit(code,log)==0
    assert 'RUSTER_STOPPED' in log.read_text()


@pytest.mark.parametrize('code',[1,-1,0xFFFFFFFF])
def test_failures_before_ready_remain_errors_with_their_own_log(tmp_path,code):
    log=tmp_path/'failed-run.log';log.write_text('bootstrap error\n')
    with pytest.raises(OSError,match='could not start') as failure:launch.check_exit(code,log)
    assert str(log) in str(failure.value)


def test_access_violation_after_ready_is_not_silenced(tmp_path,monkeypatch):
    monkeypatch.setattr(launch.sys,'platform','win32')
    log=tmp_path/'crash.log';log.write_text('RUSTER_READY 0.11.2\n')
    with pytest.raises(OSError,match='stopped unexpectedly'):launch.check_exit(0xC0000005,log)


def test_two_launcher_runs_keep_independent_logs(tmp_path,monkeypatch):
    from ruster.core import settings
    monkeypatch.setattr(settings,'user_root',lambda:tmp_path)
    monkeypatch.setattr(launch,'find_blender',lambda _: 'fixture-engine')
    monkeypatch.setattr(launch.sys,'argv',['launch.py','--background'])
    files=[]
    def child(command,*,env,stdout,stderr):
        files.append(Path(stdout.name));stdout.write('RUSTER_READY fixture\n');stdout.flush();return 0
    monkeypatch.setattr(launch.subprocess,'call',child)
    assert launch.main()==launch.main()==0
    assert files[0]!=files[1] and all(p.read_text()=='RUSTER_READY fixture\n' for p in files)
    assert (tmp_path/'logs/latest-startup.txt').read_text()==str(files[-1])
