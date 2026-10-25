"""Build first-use Blender libraries in an owned background process."""
import gzip
import json
import os
from pathlib import Path
import subprocess
import tempfile
import bpy
from . import scene

_job=None
_ready=set()


def cancel():
    global _job
    job,_job=_job,None
    if job is None:return
    process=job['process']
    if process.poll() is None:
        process.terminate()
        try:process.wait(timeout=1)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=1)
    job['log'].close()
    job['temporary'].cleanup()


def prepare(uid):
    """Return READY/WAIT/ERROR. No bpy model construction happens in this call."""
    global _job
    # Headless callers already have no interactive viewport to starve.
    if bpy.app.background:return 'READY',''
    from .protection import library_path
    cache=scene.cache_dir().resolve()
    source=cache/'prefabs'/f'{uid}.json.gz'
    if not source.is_file():
        cancel();return 'READY',''
    asset_key=scene.model_asset_key(uid)
    stat=source.stat()
    key=(str(cache),asset_key,stat.st_mtime_ns,stat.st_size)
    if _job and _job['key']!=key:cancel()
    if _job:
        process=_job['process']
        if process.poll() is None:return 'WAIT',''
        try:
            result=json.loads(_job['report'].read_text())
            if process.returncode or result.get('error'):
                return 'ERROR',result.get('error') or f'Preview worker exited with code {process.returncode}'
            if result.get('asset_key')!=asset_key:
                return 'ERROR','Asset cache changed during preview preparation; retry loading'
            if not library_path(asset_key).is_file():
                return 'ERROR','Background preparation did not create a model library; retry loading'
        except (OSError,ValueError) as error:
            return 'ERROR',f'Could not prepare the preview: {error}. See {cache / "preview-worker.log"}'
        finally:cancel()
    if key in _ready or library_path(asset_key).is_file():return 'READY',''
    # Helpers need no mesh/material construction. The compact conversion JSON
    # references mesh buffers instead of embedding the source geometry.
    with gzip.open(source,'rt',encoding='utf-8') as stream:metadata=json.load(stream)
    if metadata.get('marker') or not metadata.get('meshes'):
        _ready.add(key)
        if len(_ready)>256:_ready.pop()
        return 'READY',''
    temporary=tempfile.TemporaryDirectory(prefix='preview-',dir=cache)
    report=Path(temporary.name)/'result.json'
    environment=os.environ.copy()
    for variable,folder in (('BLENDER_USER_CONFIG','config'),('BLENDER_USER_EXTENSIONS','extensions')):
        path=Path(temporary.name)/folder;path.mkdir()
        environment[variable]=str(path)
    log=(cache/'preview-worker.log').open('w',encoding='utf-8')
    command=[bpy.app.binary_path,'--background','--factory-startup','-t','2',
        '--disable-autoexec','--python-exit-code','1','--python',
        str(Path(__file__).parent/'assets'/'preview_worker.py'),'--',
        '--cache',str(cache),'--uid',str(uid),'--report',str(report),'--parent-pid',str(os.getpid())]
    try:
        process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,env=environment,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
    except Exception:
        log.close();temporary.cleanup();raise
    _job={'key':key,'process':process,'report':report,'temporary':temporary,'log':log}
    return 'WAIT',''
