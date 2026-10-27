"""Native volume edits reach snapshots including delete/undo, with no game I/O."""
import os,sys,tempfile,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
if '--' in sys.argv:
    target=Path(sys.argv[sys.argv.index('--')+1]);sys.path.insert(0,str(target));sys.path.insert(0,str(target/'python_modules'))
import bpy,ruster
from ruster import scene,volumes,live_preview,placement,studio
from ruster.assets import catalog
from ruster.core import wire,preview_protocol
from tests.blender_volumes import asset


def run():
    with tempfile.TemporaryDirectory(prefix='ruster-volume-preview-') as directory:
        os.environ['RUSTER_USER_DIR']=directory;ruster.register();studio.new_prefab()
        db=catalog.connect(scene.cache_dir())
        for uid,name in ((3521578167,'prevent_movment_volume'),(4190049974,'prevent_building_cube')):
            path='assets/test/'+name+'.prefab'
            db.execute('INSERT INTO names VALUES(?,?)',(uid,path))
            root=scene.root_object([wire.encode(2,0,uid)],bpy.context.scene.collection)
            source=asset(uid,'BoxCollider');source['colliders'][0].update(center=[0,0,0],size=[1,1,1])
            volumes.attach(root,source,Path(directory))
        db.commit();db.close()
        baseline=live_preview.placements();assert {r['uid'] for r in baseline}=={3521578167,4190049974}
        bpy.context.scene.ruster_show_volumes=False
        assert live_preview.placements()==baseline,'Viewport visibility changed the native snapshot'
        bpy.context.scene.ruster_show_volumes=True
        bpy.context.preferences.edit.use_global_undo=True
        bpy.ops.ed.undo_push(message='Native volumes before edit')
        root=scene.prefab_roots()[0];instance=root['ruster_instance'];placement.select([root])
        root.location=(10,20,30);root.rotation_euler=(.2,.3,.4);root.scale=(133.25,133.25,64.25)
        bpy.context.view_layer.update();bpy.ops.ed.undo_push(message='Native volumes after edit')
        changed=live_preview.placements();assert changed!=baseline
        assert {r['uid'] for r in changed}=={3521578167,4190049974}
        assert bpy.ops.ed.undo()=={'FINISHED'}
        assert live_preview.placements()==baseline
        assert bpy.ops.ed.redo()=={'FINISHED'}
        assert live_preview.placements()==changed
        root=next(o for o in scene.prefab_roots() if o['ruster_instance']==instance);placement.select([root])
        bpy.ops.ruster.delete(confirm=False);bpy.ops.ed.undo_push(message='Native volume removed')
        removed=live_preview.placements();assert len(removed)==1
        assert bpy.ops.ed.undo()=={'FINISHED'}
        restored=live_preview.placements();assert len(restored)==2
        assert {r['uid'] for r in restored}=={3521578167,4190049974}
        assert bpy.ops.ed.redo()=={'FINISHED'} and len(live_preview.placements())==1
        # Both runtimes receive these same native IDs and Unity transforms. This
        # validates capture/encoding; it does not certify gameplay collision.
        for revision,rows in enumerate((baseline,changed,removed,restored),1):
            assert preview_protocol.encode_snapshot(revision,rows).startswith(b'RUSLIVE1')
        # Solid vehicle barriers share the same native snapshot/undo path, with
        # a 200 m vertical scale. This still does not simulate a vehicle impact.
        uid=3000049339;db=catalog.connect(scene.cache_dir())
        db.execute('INSERT INTO names VALUES(?,?)',(uid,'assets/test/invisible_collider.prefab'));db.commit();db.close()
        solid=scene.root_object([wire.encode(2,0,uid)],bpy.context.scene.collection)
        source=asset(uid,'BoxCollider');source['colliders'][0].update(center=[0,0,0],size=[1,1,1])
        volumes.attach(solid,source,Path(directory));instance=solid['ruster_instance'];placement.select([solid])
        baseline=live_preview.placements();bpy.ops.ed.undo_push(message='Solid collider before edit')
        solid.location=(10,20,0);solid.rotation_euler=(0,0,.5);solid.scale=(8.2,2,200)
        bpy.context.view_layer.update();bpy.ops.ed.undo_push(message='Solid collider after edit')
        changed=live_preview.placements();row=next(r for r in changed if r['uid']==uid)
        assert row['scale'][1]==200 and changed!=baseline
        assert bpy.ops.ed.undo()=={'FINISHED'} and live_preview.placements()==baseline
        assert bpy.ops.ed.redo()=={'FINISHED'} and live_preview.placements()==changed
        placement.select([next(o for o in scene.prefab_roots() if o['ruster_instance']==instance)])
        bpy.ops.ruster.delete(confirm=False);bpy.ops.ed.undo_push(message='Solid collider removed')
        assert all(r['uid']!=uid for r in live_preview.placements())
        assert bpy.ops.ed.undo()=={'FINISHED'} and any(r['uid']==uid for r in live_preview.placements())
        assert preview_protocol.encode_snapshot(10,live_preview.placements()).startswith(b'RUSLIVE1')
        ruster.unregister()
    print('RUSTER_VOLUME_PREVIEW_SNAPSHOTS_OK',flush=True)


try:run()
except Exception:traceback.print_exc();os._exit(1)
