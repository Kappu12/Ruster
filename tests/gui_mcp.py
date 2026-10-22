"""Real stdio MCP -> community socket bridge -> native Blender integration."""
import gzip,json,os,shutil,socket,subprocess,sys,tempfile,time,traceback
from pathlib import Path
from contextlib import closing
import bpy
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
APP_ROOT=Path(sys.argv[sys.argv.index('--')+1]).resolve() if '--' in sys.argv and sys.argv[sys.argv.index('--')+1:] else ROOT
sys.path.insert(0,str(APP_ROOT))
import ruster
from ruster import app,scene,mcp_bridge,protection
from ruster.core import settings,steam
from ruster.assets import catalog
from tests.fixtures import triangle_asset

temp=tempfile.TemporaryDirectory(prefix='ruster-mcp-gui-');directory=Path(temp.name)
os.environ['RUSTER_USER_DIR']=str(directory/'user')
ruster.register()
state={'stage':0,'started':time.monotonic()}


def perform():
    stage=state['stage']
    if time.monotonic()-state['started']>75:raise AssertionError('MCP integration timed out')
    if stage==0:
        bpy.context.window.event_simulate(type='ESC',value='PRESS')
        bpy.context.window.event_simulate(type='MOUSEMOVE',value='NOTHING',x=600,y=500)
        # First-run discovery skips the folder dialog and starts indexing.
        game=directory/'Steam/steamapps/common/Rust';(game/'Bundles').mkdir(parents=True);(game/'RustClient.exe').write_bytes(b'MZ test fixture')
        (game/'Bundles/AssetSceneManifest.json').write_text('{}')
        old_detect,old_job=steam.detect_install,app.start_job;jobs=[]
        try:
            steam.detect_install=lambda *_args,**_kwargs:game
            app.start_job=lambda action,*_args:jobs.append(action)
            app._pending_project=None;app.startup()
            assert settings.load()['rust_install']==str(game) and jobs[0]=='index'
            assert bpy.context.scene.ruster.mode=='PREFAB' and not bpy.context.scene.objects
        finally:steam.detect_install,app.start_job=old_detect,old_job
        window=bpy.context.window
        window.event_simulate(type='ESC',value='PRESS')
        bpy.context.preferences.edit.use_global_undo=True
        bpy.ops.ed.undo_push(message='MCP fixture empty composition')
        cache=scene.cache_dir()/'prefabs';cache.mkdir(parents=True,exist_ok=True)
        asset=triangle_asset(123456);path=asset['path']
        with closing(catalog.connect(scene.cache_dir())) as db:
            db.execute('INSERT OR REPLACE INTO names VALUES(?,?)',(123456,path))
            db.execute('INSERT OR REPLACE INTO assets VALUES(?,?,?,?)',(path,'bundle','file',123456));db.commit()
        (cache/'123456.json.gz').write_bytes(gzip.compress(json.dumps(asset).encode()))
        profile=bpy.context.window_manager.ruster_mcp
        assert not profile.enabled and not mcp_bridge.running()
        if os.environ.get('RUSTER_MCP_TEST_PORT'):port=int(os.environ['RUSTER_MCP_TEST_PORT'])
        else:
            with socket.socket() as probe:probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
        profile.port=port;profile.enabled=True
        assert mcp_bridge.running(),profile.status
        state['port']=port
        client_python=os.environ.get('RUSTER_TEST_PYTHON') or shutil.which('python3') or shutil.which('python')
        if not client_python:raise AssertionError('Set RUSTER_TEST_PYTHON to the Python interpreter with requirements-mcp.txt installed')
        env={**os.environ,'RUSTER_MCP_TEST_STATE':str(directory),'RUSTER_MCP_APP_ROOT':str(APP_ROOT),'PYTHONIOENCODING':'utf-8'}
        # The SDK belongs to setup-python in CI, not Blender's private Python.
        # A runtime PYTHONHOME would redirect that external interpreter's stdlib.
        env.pop('PYTHONHOME',None)
        state['log']=(directory/'client.log').open('w',encoding='utf8')
        print('RUSTER_MCP_TEST_CLIENT '+str(client_python)+' APP_ROOT='+str(APP_ROOT),flush=True)
        state['client']=subprocess.Popen([client_python,str(ROOT/'tests/mcp_client_roundtrip.py')],env=env,stdout=state['log'],stderr=state['log'])
        state['stage']=1
    elif stage==1:
        if state['client'].poll() is not None:
            state['log'].flush();raise AssertionError((directory/'client.log').read_text(encoding='utf8',errors='replace'))
        if not (directory/'ready.json').exists():return .1
        data=json.loads((directory/'ready.json').read_text())
        assert not protection.model_error(bpy.data.objects[data['object']])
        bpy.context.window_manager.ruster_mcp.enabled=False
        assert not mcp_bridge.running()
        (directory/'disabled').touch();state['stage']=2
    else:
        code=state['client'].poll()
        if code is None:return .1
        state['log'].close()
        assert code==0,(directory/'client.log').read_text(encoding='utf8',errors='replace')
        if os.environ.get('RUSTER_MCP_PREVIEW'):
            Path(os.environ['RUSTER_MCP_PREVIEW']).write_bytes((directory/'viewport.png').read_bytes())
        bpy.context.window_manager.ruster_mcp.enabled=True
        assert mcp_bridge.running(),'MCP could not restart on the same port'
        ruster.unregister()
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
            probe.bind(('127.0.0.1',state['port']))
        print('RUSTER_GUI_MCP_AUTODETECT_TOGGLE_STDIO_OK',flush=True)
        bpy.ops.wm.quit_blender();return None
    return .1


def step():
    try:
        with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):return perform()
    except Exception:
        traceback.print_exc()
        if 'client' in state and state['client'].poll() is None:
            state['client'].terminate()
            try:state['client'].wait(timeout=3)
            except subprocess.TimeoutExpired:state['client'].kill();state['client'].wait(timeout=3)
        os._exit(1)

bpy.app.timers.register(step,first_interval=2.)
