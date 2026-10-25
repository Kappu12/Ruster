"""Large repeated compositions yield between batches and remain cancelable."""
import os,sys,tempfile,traceback,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
if '--' in sys.argv:sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import bpy,ruster
from ruster import app,scene,studio,loading,quitting,construction
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
        native_groups=construction.symmetry_groups;scans=[]
        def groups(*args,**kwargs):
            scans.append(1);return native_groups(*args,**kwargs)
        construction.symmetry_groups=groups
        try:
            bpy.context.scene.ruster_construction.symmetry=False
            scans.clear()
            for _ in range(20):construction.sync_symmetry(bpy.context.scene)
            assert not scans,'Disabled symmetry scanned the scene on dependency updates'
        finally:construction.symmetry_groups=native_groups
        from types import SimpleNamespace
        native_bpy=app.bpy
        app.bpy=SimpleNamespace(context=SimpleNamespace(window_manager=SimpleNamespace(is_interface_locked=True)))
        queued=app._visual_queue[:]
        try:
            assert app.load_visuals()==.1 and app.poll_job()==.5
            assert app._visual_queue==queued,'Asset timers mutated a locked scene'
        finally:app.bpy=native_bpy
        native_start=app.start_job;starts=[]
        app._job=SimpleNamespace(poll=lambda:0,returncode=0)
        app._job_action='extract';app._job_ids={42};app._job_cancelled=False
        try:
            bpy.ops.ruster.cancel_assets()
            assert app.request_assets([42])
            assert app._pending_asset_ids=={42},'Retry was mistaken for canceled in-flight work'
            app.start_job=lambda action,ids:starts.append((action,ids))
            assert app.poll_job()==.5
            assert starts==[('extract',[42])],'Completion discarded a request made after Cancel'
        finally:
            app.start_job=native_start;app._job=None;app._job_action=None
            app._job_ids.clear();app._pending_asset_ids.clear();app._job_cancelled=False
        # Save-status polling must yield on the same large scene too. Closing
        # still compares the complete document, including during a partial scan.
        app.save_project(Path(directory)/'large.ruster')
        samples=[]
        def refresh_status():
            for _ in range(10000):
                started=time.perf_counter();delay=quitting.status_tick()
                samples.append(time.perf_counter()-started)
                if delay==1.:return
                assert delay==.01
            raise AssertionError('Save-status scan never completed')
        assert quitting.status_tick()==.01 and quitting._status_scan is not None
        root=scene.prefab_roots()[0];saved_location=root.location.copy()
        root.location.x+=5
        assert quitting.has_unsaved_changes(),'A partial status scan hid unsaved work at close'
        refresh_status();refresh_status()
        assert quitting.save_status()=='Unsaved changes'
        root.location=saved_location
        refresh_status()
        assert quitting.save_status()=='Saved','Returning to the saved document stayed dirty'
        assert quitting.status_tick()==.01
        quitting.mark_saved()
        assert quitting._status_scan is None,'Save retained a scan from the previous savepoint'
        assert quitting.status_tick()==.01
        quitting.reset()
        assert quitting._status_scan is None,'New retained references to the previous scene'
        assert len(samples)>len(scene.prefab_roots())//quitting.STATUS_STEPS_PER_TICK
        print(f'RUSTER_STATUS_BUDGET_OK: {len(samples)} ticks; maximum {max(samples)*1000:.2f}ms',flush=True)
        ruster.unregister()


try:run()
except Exception:traceback.print_exc();os._exit(1)
