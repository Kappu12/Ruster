"""Offline tests only: never inspect, launch, or inject the user's Rust client."""
from dataclasses import replace
import io
from pathlib import Path
import struct
import sys
import threading
from unittest.mock import Mock
import zipfile

import pytest

from ruster.core import live_preview as server, preview_client as client, preview_protocol as protocol
from ruster.core.rust_map import RustMap, prefab_id, prefab_transform


def placement(**changes):
    return {'key': 17, 'uid': 123456, 'path': 'assets/test/original.prefab',
            'position': (1., 2., 3.), 'rotation': (0., 0., 0., 1.), 'scale': (1., 2., 3.),
            'euler': (0., 90., 0.), **changes}


def safe_probe(tmp_path):
    return client.ClientProbe(pid=123, executable=str(tmp_path/'RustClient.exe'), created=100,
        command_line='"'+str(tmp_path/'RustClient.exe')+'"', parent_name='explorer.exe',
        modules=[str(tmp_path/'GameAssembly.dll'), str(tmp_path/'UnityPlayer.dll')])


def test_no_eac_requires_multiple_independent_observations(tmp_path):
    probe = safe_probe(tmp_path)
    assert client.verify_probe(probe, tmp_path) is probe
    for changes in ({'error': 'access denied'}, {'command_line': ''}, {'parent_name': ''},
                    {'modules': []}, {'modules': ['UnityPlayer.dll']}, {'created': 0},
                    {'parent_name': 'Rust.exe'}, {'parent_name': 'EasyAntiCheat_EOS.exe'},
                    {'command_line': 'RustClient.exe -eac-nop-loaded'},
                    {'command_line': 'RustClient.exe /EAC'},
                    {'modules': probe.modules+['EasyAntiCheat_EOS.dll']},
                    {'eac_services': ['EasyAntiCheat_EOS']},
                    {'eac_processes': ['EasyAntiCheat.exe']},
                    {'executable': str(tmp_path/'AnotherGame.exe')}):
        with pytest.raises(ValueError):client.verify_probe(replace(probe, **changes), tmp_path)


@pytest.mark.parametrize('name', ['EasyAntiCheat_EOS.sys', 'C:\\Games\\EasyAntiCheat_x64.dll', 'EAC_Client.dll',
    'easyanticheat_eos', 'EACDriver.sys', 'start_protected_game.exe'])
def test_eac_names_include_drivers_and_case(name):
    assert client.is_eac_name(name)


def test_failed_verification_never_opens_process_for_injection(tmp_path, monkeypatch):
    inspector = Mock();inspector.inspect.return_value = replace(safe_probe(tmp_path), eac_services=['EasyAntiCheat'])
    monkeypatch.setattr(client, '_windows', lambda: inspector)
    with pytest.raises(ValueError, match='EAC is active'):
        client.inject(tmp_path, tmp_path/'RusterPreview.dll', tmp_path, 123)
    inspector.k.OpenProcess.assert_not_called()
    inspector.k.VirtualAllocEx.assert_not_called()
    inspector.k.CreateRemoteThread.assert_not_called()


def test_recheck_blocks_race_before_any_write(tmp_path, monkeypatch):
    inspector = Mock();probe = safe_probe(tmp_path)
    inspector.inspect.side_effect = [probe, replace(probe, error='modules became unreadable')]
    monkeypatch.setattr(client, '_windows', lambda: inspector)
    (tmp_path/'RusterPreview.dll').write_bytes(b'not executed')
    (tmp_path/'scene.bin').write_bytes(b'not executed')
    with pytest.raises(ValueError, match='Cannot verify'):
        client.inject(tmp_path, tmp_path/'RusterPreview.dll', tmp_path, 123)
    inspector.k.OpenProcess.assert_not_called()
    inspector.k.WriteProcessMemory.assert_not_called()


def test_pid_reuse_blocks_injection(tmp_path, monkeypatch):
    inspector = Mock();probe = safe_probe(tmp_path)
    inspector.inspect.side_effect = [probe, replace(probe, created=200)]
    monkeypatch.setattr(client, '_windows', lambda: inspector)
    (tmp_path/'RusterPreview.dll').touch();(tmp_path/'scene.bin').touch()
    with pytest.raises(ValueError, match='restarted'):
        client.inject(tmp_path, tmp_path/'RusterPreview.dll', tmp_path, 123)
    inspector.k.OpenProcess.assert_not_called()


def test_injection_rechecks_server_runtime_eac_before_writing(tmp_path, monkeypatch):
    inspector = Mock();inspector.inspect.return_value = safe_probe(tmp_path)
    monkeypatch.setattr(client, '_windows', lambda: inspector)
    (tmp_path/'RusterPreview.dll').touch();(tmp_path/'scene.bin').touch()
    (tmp_path/'active.flag').touch()
    (tmp_path/'server.ready').write_text('{"protocol":1,"secure":true,"ip":"127.0.0.1"}')
    with pytest.raises(ValueError, match='inactive EAC'):
        client.inject(tmp_path, tmp_path/'RusterPreview.dll', tmp_path, 123)
    inspector.k.OpenProcess.assert_not_called()


def test_cross_language_snapshot_layout_and_atomic_outputs(tmp_path):
    row = placement()
    data = protocol.encode_snapshot(8, [row])
    assert data[:8] == b'RUSLIVE1'
    assert struct.unpack_from('<QI', data, 8) == (8, 1)
    key, uid, length = struct.unpack_from('<QII', data, 20)
    assert (key, uid) == (17, 123456)
    assert data[36:36+length].decode() == row['path']
    assert struct.unpack_from('<10f', data, 36+length) == (*row['position'], *row['rotation'], *row['scale'])
    protocol.write_snapshot(tmp_path, 8, [row])
    assert (tmp_path/'scene.bin').read_bytes() == data
    import json
    assert json.loads((tmp_path/'scene.json').read_text())['revision'] == 8


@pytest.mark.parametrize('changes', [
    {'key': 0}, {'uid': -1}, {'path': 'assets/../../bad.prefab'},
    {'path': 'C:/arbitrary.dll'}, {'path': 'assets/a\0.prefab'},
    {'position': (float('nan'), 0, 0)}, {'rotation': (0, 0, 0, 0)}, {'scale': (0, 1, 1)},
])
def test_invalid_snapshots_cannot_reach_either_runtime(changes):
    with pytest.raises(ValueError):protocol.encode_snapshot(1, [placement(**changes)])


def test_duplicate_and_oversized_snapshots_are_rejected():
    with pytest.raises(ValueError):protocol.encode_snapshot(1, [placement(), placement()])
    with pytest.raises(ValueError):protocol.encode_snapshot(1, [placement(key=i+1) for i in range(2001)])


def test_initial_map_contains_exact_original_placements_and_flat_layers():
    world = RustMap.read(protocol.preview_map([placement()]))
    assert world.size == 1000 and len(world.prefabs) == 1
    assert prefab_id(world.prefabs[0]) == 123456
    assert prefab_transform(world.prefabs[0]) == ((1., 2., 3.), (0., 90., 0.), (1., 2., 3.))
    assert world.height_grid()[0] == 513
    assert world.layers['alpha'] == b'\xff'*(512*512)


@pytest.mark.parametrize('name', ['../escape', '/root/file', 'C:/outside', 'safe/../../escape', 'safe\\..\\..\\escape'])
def test_unsafe_download_archives_are_rejected_before_any_write(tmp_path, name):
    archive = tmp_path/'bad.zip'
    with zipfile.ZipFile(archive, 'w') as output:
        output.writestr('first.txt', b'not partially extracted');output.writestr(name, b'bad')
    with pytest.raises(ValueError):server.extract_zip(archive, tmp_path/'install')
    assert not (tmp_path/'install/first.txt').exists()


def test_cancelled_or_corrupt_download_does_not_publish(tmp_path, monkeypatch):
    class Response(io.BytesIO):pass
    monkeypatch.setattr(server.urllib.request, 'urlopen', lambda *a, **k: Response(b'payload'))
    cancel = threading.Event();cancel.set()
    with pytest.raises(InterruptedError):server.download('https://example.com', tmp_path/'file.zip', cancel)
    cancel.clear()
    with pytest.raises(ValueError, match='SHA256'):
        server.download('https://example.com', tmp_path/'file.zip', cancel, digest='0'*64)
    assert not (tmp_path/'file.zip').exists() and not list(tmp_path.glob('*.download'))


def test_server_command_is_private_insecure_and_uses_requested_port():
    args = server.command(Path('RustDedicated.exe'), 'ruster_preview_test', 29000, 'http://127.0.0.1/test.map', Path('log'))
    assert '-insecure' in args
    for field in ('+server.ip', '+rcon.ip', '+app.listenip'):assert args[args.index(field)+1] == '127.0.0.1'
    assert args[args.index('+server.port')+1] == '29000'
    assert args[args.index('+server.maxplayers')+1] == '1'
    assert len(args[args.index('+rcon.password')+1]) >= 32


@pytest.mark.parametrize('value', ['ownerid 123', '76561198000000000\nquit', 'abc', '１２３４５６７８９０１２３４５６７'])
def test_owner_field_cannot_inject_commands(value):
    with pytest.raises(ValueError):server.owner_id(value)


def test_console_commands_are_owned_bounded_and_single_line(tmp_path):
    job = object.__new__(server.PreviewSession);job.status = 'RUNNING';job.directory = tmp_path
    job.send_command('status')
    assert len(list((tmp_path/'commands').glob('*.json'))) == 1
    with pytest.raises(ValueError):job.send_command('status\nquit')
    job.status = 'STARTING'
    with pytest.raises(ValueError):job.send_command('ownerid 76561198000000000')


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows-only preview lifecycle')
def test_owned_server_lifecycle_with_synthetic_child(tmp_path, monkeypatch):
    import subprocess
    import sys
    import time
    monkeypatch.setattr(server, 'check_ports', lambda port: None)
    job = server.PreviewSession(tmp_path, port=29000, placements=[])
    job._install = lambda: tmp_path/'RustDedicated.exe'
    def map_server():
        job.url = 'http://127.0.0.1:12345/synthetic.map'
        (job.directory/'map.url').write_text(job.url)
    job._serve_map = map_server
    script = tmp_path/'synthetic-server.py'
    script.write_text("""import os,time
from pathlib import Path
session=Path(os.environ['RUSTER_PREVIEW_DIR'])
(session/'server.ready').write_text('{"protocol":1,"secure":false,"ip":"127.0.0.1"}')
while (session/'active.flag').exists():time.sleep(.02)
""")
    real_popen = subprocess.Popen
    def popen(args, **kwargs):
        kwargs.pop('creationflags', None);kwargs['cwd'] = tmp_path
        return real_popen([sys.executable, str(script)], **kwargs)
    monkeypatch.setattr(server.subprocess, 'Popen', popen)
    untouched = tmp_path/'other-server.sav';untouched.write_bytes(b'keep')
    job.start()
    deadline = time.monotonic()+5
    try:
        while job.status != 'RUNNING' and time.monotonic() < deadline:time.sleep(.03)
        assert job.status == 'RUNNING', job.info()
        job.update([placement()])
        deadline = time.monotonic()+3
        while job.revision < 2 and time.monotonic() < deadline:time.sleep(.03)
        assert job.revision == 2
    finally:job.close()
    assert job.status == 'STOPPED' and job.process.poll() is not None
    assert untouched.read_bytes() == b'keep' and not (job.directory/'active.flag').exists()


def test_server_runtime_report_must_confirm_inactive_eac(tmp_path):
    import json
    path = tmp_path/'server.ready'
    path.write_text(json.dumps({'protocol': 1, 'secure': False, 'ip': '127.0.0.1'}))
    server.verify_server_ready(path)
    for report in ({'protocol': 1, 'secure': True, 'ip': '127.0.0.1'},
                   {'protocol': 1, 'secure': False, 'ip': '0.0.0.0'},
                   {'protocol': 1, 'ip': '127.0.0.1'}):
        path.write_text(json.dumps(report))
        with pytest.raises(ValueError):server.verify_server_ready(path)


def test_stop_marker_survives_windows_delete_pending_error(tmp_path, monkeypatch):
    job = object.__new__(server.PreviewSession);job.directory = tmp_path
    (tmp_path/'active.flag').write_text('active')
    original = Path.unlink
    def unlink(path, *args, **kwargs):
        if path.name == 'active.flag':raise PermissionError('Windows delete-pending')
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'unlink', unlink)
    job._stop_marker()
    assert (tmp_path/'stop.flag').is_file()
