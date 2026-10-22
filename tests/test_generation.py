"""Generation lifecycle tests use a synthetic child, never a real Rust install."""
import os
from pathlib import Path
import subprocess
import sys
import time
import pytest
from ruster.core import generation
from .fixtures import sample_world
_writer_closed=generation.writer_closed


def wait(job,seconds=8):
    deadline=time.monotonic()+seconds
    while job.active and time.monotonic()<deadline:time.sleep(.03)
    assert not job.active,job.info()


def setup(tmp_path,monkeypatch,script):
    binary=tmp_path/'RustDedicated';binary.touch();binary.chmod(0o700)
    script_path=tmp_path/'child.py';script_path.write_text(script)
    real_popen=subprocess.Popen
    def child(args,**kwargs):return real_popen([sys.executable,str(script_path)],**kwargs)
    monkeypatch.setattr(generation.subprocess,'Popen',child)
    monkeypatch.setattr(generation,'free_ports',lambda:(28015,28017,28016))
    # Lifecycle tests isolate OS completion probing, covered independently below.
    monkeypatch.setattr(generation,'writer_closed',lambda path,pid:True)
    return binary


def test_ready_stops_child_before_playable_startup_and_preserves_bytes(tmp_path,monkeypatch):
    source=tmp_path/'fixture';source.write_bytes(sample_world().write())
    binary=setup(tmp_path,monkeypatch,"""from pathlib import Path
import time
root=Path('.')
target=root/'maps/proceduralmap.1000.123.999.map'
target.parent.mkdir(exist_ok=True)
data=(root/'fixture').read_bytes()
target.write_bytes(data[:20])
time.sleep(.9)
target.write_bytes(data)
time.sleep(10)
(root/'playable-server-started').touch()
""")
    job=generation.Generation(binary,123,1000,tmp_path/'output').start()
    wait(job)
    assert job.status=='READY',job.info()
    assert job.result.read_bytes()==source.read_bytes()
    assert job.process.poll() is not None
    assert not (tmp_path/'playable-server-started').exists()
    assert job.elapsed<8 and job.info()['result']


def test_cancel_reaps_owned_child_without_touching_existing_server(tmp_path,monkeypatch):
    binary=setup(tmp_path,monkeypatch,'import time; time.sleep(20)')
    profile=tmp_path/'server/existing';profile.mkdir(parents=True)
    original=profile/'player.sav';original.write_bytes(b'keep me')
    job=generation.Generation(binary,123,1000,tmp_path/'output').start()
    deadline=time.monotonic()+3
    while job.process is None and time.monotonic()<deadline:time.sleep(.02)
    job.close();assert job.status=='CANCELLED'
    assert job.process.poll() is not None and original.read_bytes()==b'keep me'


def test_unchanged_cache_is_not_accepted_as_new_output(tmp_path,monkeypatch):
    binary=setup(tmp_path,monkeypatch,'pass')
    cache=tmp_path/'maps';cache.mkdir()
    old=cache/'proceduralmap.1000.123.100.map';old.write_bytes(sample_world().write())
    job=generation.Generation(binary,123,1000,tmp_path/'output').start();wait(job)
    assert job.status=='FAILED' and 'unchanged cached map' in job.error
    assert job.result is None and old.read_bytes()==sample_world().write()


def test_seed_boundary_and_symlink_escape(tmp_path,monkeypatch):
    binary=setup(tmp_path,monkeypatch,'pass');cache=tmp_path/'maps';cache.mkdir()
    (cache/'proceduralmap.1000.1234.map').touch()
    outside=tmp_path/'outside.map';outside.touch()
    if os.name!='nt':(cache/'proceduralmap.1000.123.map').symlink_to(outside)
    job=generation.Generation(binary,123,1000,tmp_path/'output')
    assert list(job._candidates())==[]


@pytest.mark.parametrize('seed,size',[(-1,1000),(2147483648,1000),(True,1000),(1,999),(1,6001),(1,1000.0)])
def test_invalid_parameters(seed,size):
    with pytest.raises(ValueError):generation.parameters(seed,size)


def test_command_is_headless_loopback_unique_profile():
    args=generation.command(Path('/some/RustDedicated'),123,1000,'ruster_gen_abc',Path('/job/log'),(1,2,3))
    assert '-nographics' in args and '-batchmode' in args
    assert args[args.index('+server.ip')+1]=='127.0.0.1'
    assert args[args.index('+server.maxplayers')+1]=='0'
    assert args[args.index('+server.identity')+1]=='ruster_gen_abc'
    assert len(args[args.index('+rcon.password')+1])>=32


def test_dedicated_install_detection_and_manifest_traversal(tmp_path):
    common=tmp_path/'steamapps/common';install=common/'My Server';install.mkdir(parents=True)
    binary=install/('RustDedicated.exe' if sys.platform=='win32' else 'RustDedicated');binary.touch();binary.chmod(0o700)
    manifest=tmp_path/'steamapps/appmanifest_258550.acf'
    manifest.write_text('"AppState" { "installdir" "My Server" }')
    assert generation.detect([tmp_path])==binary.resolve()
    manifest.write_text('"AppState" { "installdir" "../../escape" }')
    assert generation.detect([tmp_path]) is None


def test_timeout_stops_child(tmp_path,monkeypatch):
    binary=setup(tmp_path,monkeypatch,'import time; time.sleep(20)')
    job=generation.Generation(binary,123,1000,tmp_path/'output',timeout=1).start();wait(job)
    assert job.status=='FAILED' and 'timed out' in job.error and job.process.poll() is not None


def test_validation_reads_once_without_expanding_height_tuples(tmp_path,monkeypatch):
    binary=setup(tmp_path,monkeypatch,'pass')
    job=generation.Generation(binary,123,1000,tmp_path/'output')
    source=tmp_path/'complete.map';raw=sample_world().write();source.write_bytes(raw)
    def forbidden(*_args,**_kwargs):raise AssertionError('Unnecessary height/prefab expansion')
    monkeypatch.setattr(generation.RustMap,'height_grid',forbidden)
    monkeypatch.setattr(generation.RustMap,'prefabs',property(forbidden))
    world,data=job._validate(source,job._stat(source))
    assert world.size==1000 and data==raw


@pytest.mark.parametrize('layer',('terrain','water'))
def test_structurally_incomplete_world_is_not_ready(tmp_path,monkeypatch,layer):
    binary=setup(tmp_path,monkeypatch,'pass');job=generation.Generation(binary,123,1000,tmp_path/'output')
    world=sample_world();world.set_layer(layer,b'\0\0\0')
    source=tmp_path/'incomplete.map';source.write_bytes(world.write())
    with pytest.raises(ValueError,match='heightmap'):job._validate(source,job._stat(source))


def test_completion_probe_waits_for_file_close(tmp_path):
    source=tmp_path/'still-writing.map'
    with source.open('wb') as handle:
        handle.write(b'complete-looking prefix');handle.flush()
        try:closed=generation.writer_closed(source,os.getpid())
        except (OSError,RuntimeError) as error:pytest.skip('Process descriptors unavailable in this runtime: '+str(error))
        assert not closed
    assert generation.writer_closed(source,os.getpid())


def test_parseable_prefix_is_not_imported_while_writer_is_open(tmp_path,monkeypatch):
    from ruster.core import legacy_lz4,wire
    # Require a real, permitted OS completion probe for this integration case.
    probe=tmp_path/'probe'
    with probe.open('wb') as handle:
        handle.write(b'probe');handle.flush()
        try:closed=_writer_closed(probe,os.getpid())
        except (OSError,RuntimeError) as error:pytest.skip('Process descriptors unavailable in this runtime: '+str(error))
        assert not closed
    first=sample_world().write();tail=legacy_lz4.compress(wire.encode(98,2,b'last field').raw)
    (tmp_path/'fixture').write_bytes(first);(tmp_path/'tail').write_bytes(tail)
    binary=setup(tmp_path,monkeypatch,"""from pathlib import Path
import time
target=Path('maps/proceduralmap.1000.123.999.map');target.parent.mkdir(exist_ok=True)
with target.open('wb') as handle:
 handle.write(Path('fixture').read_bytes());handle.flush()
 time.sleep(1.2)
 handle.write(Path('tail').read_bytes())
time.sleep(10)
""")
    monkeypatch.setattr(generation,'writer_closed',_writer_closed)
    job=generation.Generation(binary,123,1000,tmp_path/'output').start();wait(job)
    assert job.status=='READY',job.info()
    assert job.result.read_bytes()==first+tail,'Accepted a valid prefix before the writer finished'


def test_linux_completion_probe_inode_matching_and_fail_closed(tmp_path):
    source=tmp_path/'map';source.write_bytes(b'prefix')
    proc=tmp_path/'proc';fds=proc/'321/fd';fds.mkdir(parents=True)
    os.link(source,fds/'10')
    assert not generation.linux_writer_closed(source,321,proc)
    (fds/'10').unlink()
    assert generation.linux_writer_closed(source,321,proc)
    with pytest.raises(RuntimeError,match='unavailable'):generation.linux_writer_closed(source,999,proc)
