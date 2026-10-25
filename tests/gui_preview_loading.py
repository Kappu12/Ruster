"""Actual background Blender preparation, incremental linking and cancellation."""
import gzip,json,os,sys,tempfile,time,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
if '--' in sys.argv:sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import bpy,ruster
from ruster import app,scene,studio,protection,preview_jobs
from ruster.core import wire
from tests.fixtures import triangle_asset
temporary=tempfile.TemporaryDirectory()
os.environ['RUSTER_USER_DIR']=temporary.name
ruster.register()
state={'stage':0,'ticks':0,'max_tick':0.,'started':time.monotonic()}
original_freeze=protection.freeze


def no_main_thread_build(collection,*args,**kwargs):
    assert collection.library,'The UI built the first model synchronously'
    return original_freeze(collection,*args,**kwargs)


def tick():
    try:
        stage=state['stage']
        if stage==0:
            bpy.context.window.event_simulate(type='ESC',value='PRESS')
            studio.new_prefab()
            cache=scene.cache_dir()/'prefabs';cache.mkdir(parents=True)
            for uid in (123456,123457):
                (cache/f'{uid}.json.gz').write_bytes(gzip.compress(json.dumps(triangle_asset(uid)).encode()))
            for i in range(300):
                root=scene.root_object([wire.encode(2,0,123456)],bpy.context.scene.collection)
                root.location=(i%20,i//20,0)
            app._visual_queue=[123456]
            protection.freeze=no_main_thread_build
            assert app.load_visuals() is not None
            assert preview_jobs._job is not None
            state['pid']=preview_jobs._job['process'].pid
            assert state['pid']!=os.getpid() and not any(o.get('ruster_visual') for o in scene.prefab_roots())
            state['stage']=1
        elif stage==1:
            before=time.monotonic();app.load_visuals()
            state['max_tick']=max(state['max_tick'],time.monotonic()-before)
            state['ticks']+=1
            if app._visual_queue:
                assert time.monotonic()-state['started']<60,'Background preparation did not complete'
                return .05
            roots=scene.prefab_roots()
            assert all(o.get('ruster_visual') for o in roots)
            assert len({o.instance_collection for o in roots})==1
            assert state['ticks']>3,'The entire file attached in one blocking tick'
            # A second uncached library starts independently and can be canceled.
            extra=scene.root_object([wire.encode(2,0,123457)],bpy.context.scene.collection)
            app._visual_queue=[123457];app.load_visuals()
            process=preview_jobs._job['process']
            bpy.ops.ruster.cancel_assets()
            assert process.poll() is not None and preview_jobs._job is None
            assert not extra.get('ruster_visual') and extra['ruster_uid']=='123457'
            # A corrupt cache reports an issue without rebuilding on the UI.
            broken=triangle_asset(123458)
            next(iter(broken['meshes'].values()))['buffer']='meshes/missing.mesh.gz'
            (scene.cache_dir()/'prefabs/123458.json.gz').write_bytes(gzip.compress(json.dumps(broken).encode()))
            root=scene.root_object([wire.encode(2,0,123458)],bpy.context.scene.collection)
            state['failed_root']=root['ruster_instance']
            app._visual_queue=[123458];state['stage']=2
        elif stage in (2,3):
            app.load_visuals()
            if app._visual_queue:
                assert time.monotonic()-state['started']<60
                return .05
            root=next(o for o in scene.prefab_roots() if o['ruster_instance']==state['failed_root'])
            if stage==2:
                assert root.get('ruster_model_error_kind')=='PREVIEW' and not root.get('ruster_visual')
                assert preview_jobs._job is None
                (scene.cache_dir()/'prefabs/123458.json.gz').write_bytes(gzip.compress(json.dumps(triangle_asset(123458)).encode()))
                app._visual_queue=[123458];state['stage']=3
            else:
                assert root.get('ruster_visual') and not root.get('ruster_model_error')
                print('RUSTER_ASYNC_PREVIEWS_OK',json.dumps(state),flush=True)
                os._exit(0)
        return .05
    except Exception:
        traceback.print_exc();preview_jobs.cancel();os._exit(1)
bpy.app.timers.register(tick,first_interval=1.)
