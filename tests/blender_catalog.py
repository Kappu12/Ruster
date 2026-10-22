"""Catalog refresh must not schedule bulk models; queued requests stay visible."""
import os,sys,tempfile,traceback,json,gzip
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
if '--' in sys.argv:sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import bpy,ruster
from ruster import app,scene,studio
from ruster.core import wire


def run():
    with tempfile.TemporaryDirectory() as directory:
        os.environ['RUSTER_USER_DIR']=directory
        ruster.register()
        roots=[scene.root_object([wire.encode(2,0,uid)],bpy.context.scene.collection) for uid in (42,43)]
        app._job_action='index';app._job_ids={42};app._visual_queue=[]
        app.poll_job()
        assert not app._visual_queue,'Catalog discovery loaded models'
        native_start=app.start_job
        def queued(_action,ids):app._job_action='extract';app._job_ids=set(ids)
        app.start_job=queued
        try:
            app._job_action='extract';app._job_ids={42};app._pending_asset_ids={43}
            assert app.poll_job()==.5
            app.poll_job()
            assert set(app._visual_queue)=={root.name for root in roots},'Queued batch completion lost a model update'
        finally:app.start_job=native_start
        scene.cache_dir().mkdir(parents=True,exist_ok=True)
        (scene.cache_dir()/'asset-report.json').write_text(json.dumps([{'uid':42,'error':'Missing source mesh'}]))
        app._job_action='extract';app._job_ids={42}
        app.poll_job()
        assert roots[0]['ruster_model_status']=='Model unavailable'
        assert roots[0]['ruster_model_error']=='Missing source mesh'
        assert not roots[0].get('ruster_visual')
        app._pending_asset_ids.clear()
        assert app.request_assets(range(101)) is False
        from contextlib import closing
        from ruster.assets import catalog
        with closing(catalog.connect(scene.cache_dir())) as db:
            db.executemany('INSERT INTO names VALUES(?,?)',[
                (42,'assets/test/sound/trigger.prefab'),
                (43,'assets/bundled/prefabs/modding/cubes/tiled/cube_tiled_dev_01.prefab')])
            db.commit()
        class Search:category='@DEVELOPMENT'
        assert studio.search_items(Search(),None)[0][1]=='Dev Cube Tiled 01'
        cache=scene.cache_dir()/'prefabs';cache.mkdir()
        (cache/'42.json.gz').write_bytes(gzip.compress(json.dumps({'schema':1,'marker':'SOUND','meshes':{},
            'path':'assets/test/sound/trigger.prefab'}).encode()))
        assert bpy.ops.ruster.place(uid='42')=={'FINISHED'}
        sound=bpy.context.active_object
        assert sound.get('ruster_marker')=='SOUND' and sound.empty_display_type=='SPHERE'
        assert sound.name.endswith('(Sound effect)') and app._job is None
        assert bpy.ops.ruster.place(uid='42')=={'FINISHED'}
        assert bpy.context.active_object.name==sound.name+' 2'
        assert '.' not in bpy.context.active_object.name and '_' not in bpy.context.active_object.name
        ruster.unregister()
    print('RUSTER_CATALOG_ON_DEMAND_OK',flush=True)


try:run()
except Exception:traceback.print_exc();os._exit(1)
