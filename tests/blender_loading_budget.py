"""Large repeated compositions yield between batches and remain cancelable."""
import os,sys,tempfile,traceback,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
if '--' in sys.argv:sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import bpy,ruster
from ruster import app,scene,studio,loading
from ruster.core import wire
from ruster.core.rustedit_prefab import RustEditPrefab


def run():
    with tempfile.TemporaryDirectory() as directory:
        os.environ['RUSTER_USER_DIR']=directory
        ruster.register();studio.new_prefab()
        records=[[wire.encode(2,0,42)] for _ in range(2000)]
        path=Path(directory)/'large.prefab';path.write_bytes(RustEditPrefab.create(records).write())
        native_attach=scene.attach_visual;native_request=app.request_assets
        calls=[]
        scene.attach_visual=lambda obj,**kwargs:calls.append(obj['ruster_instance']) or True
        app.request_assets=lambda ids:True
        try:
            group=studio.import_prefab(path)
            assert len(group.children)==2000 and not calls,'Import synchronously attached previews'
            app._visual_queue=[42]
            started=time.perf_counter();delay=app.load_visuals()
            assert 0<len(calls)<=app.VISUALS_PER_TICK and delay is not None
            assert app._visual_queue==[42],'One UID must remain queued until every placement is attached'
            # Native names and deletion can change while the iterator yields.
            root=group.children[-1];root.name='Renamed while loading'
            bpy.data.objects.remove(group.children[-2],do_unlink=True)
            while app._visual_queue:app.load_visuals()
            assert len(set(calls))==1999 and len(calls)==1999
            elapsed=time.perf_counter()-started
            app._visual_queue=[42];calls.clear();app.load_visuals()
            bpy.ops.ruster.cancel_assets();app.load_visuals()
            assert not app._visual_queue and app._visual_iterator is None
            print(f'RUSTER_LOADING_BUDGET_OK: 1999 placements in {elapsed:.3f}s; maximum {app.VISUALS_PER_TICK} per tick',flush=True)
        finally:scene.attach_visual=native_attach;app.request_assets=native_request
        native_summary=loading.model_summary;counts=[]
        loading._summary_cache=None
        loading.model_summary=lambda:counts.append(1) or dict(READY=1999)
        try:
            for _ in range(20):loading.cached_model_summary()
            assert len(counts)==1,'Every viewport redraw rescanned the scene'
        finally:loading.model_summary=native_summary
        ruster.unregister()


try:run()
except Exception:traceback.print_exc();os._exit(1)
