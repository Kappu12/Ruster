"""Collider previews preserve source IDs, transforms and offline project data."""
import gzip,json,os,sys,tempfile,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
if '--' in sys.argv:sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import bpy,ruster
from mathutils import Vector
from ruster import scene,studio,volumes,quitting,app
from ruster.core import wire


def asset(uid,kind):
    shape={'node':0,'type':kind,'center':[1,2,3]}
    if kind=='BoxCollider':shape['size']=[2,4,6]
    else:shape.update(radius=2,height=8,direction=1)
    return {'schema':1,'uid':uid,'path':'assets/modding/volumes_and_triggers/example.prefab',
        'marker':'VOLUME','meshes':{},'materials':{},'colliders':[shape],
        'nodes':[{'name':'Root','parent':None,'position':[99,99,99],
                  'rotation':[1,0,0,0],'scale':[55,0,0]}]}


def run():
    with tempfile.TemporaryDirectory() as directory:
        os.environ['RUSTER_USER_DIR']=directory
        ruster.register();studio.new_prefab()
        cache=scene.cache_dir()/'prefabs';cache.mkdir(parents=True)
        for uid,kind in enumerate(('BoxCollider','SphereCollider','CapsuleCollider'),1):
            data=asset(uid,kind)
            (cache/f'{uid}.json.gz').write_bytes(gzip.compress(json.dumps(data).encode()))
            root=scene.root_object([wire.encode(2,0,uid)],bpy.context.scene.collection)
            assert scene.attach_visual(root)
            assert root.get('ruster_marker')=='VOLUME' and root.instance_collection is None
            root.scale=(2,3,4);root.location=(5,6,7)
            bpy.context.view_layer.update()
            vertices,faces,edges=volumes.meshes(root)[0]
            center=root.matrix_world @ Vector((1,3,2))
            if kind=='SphereCollider':
                assert all(abs((v-center).length-8)<1e-4 for v in vertices),'Sphere must use largest scale, not become an ellipsoid'
            elif kind=='BoxCollider':
                assert [round(max(v[i] for v in vertices)-min(v[i] for v in vertices)) for i in range(3)]==[4,18,16]
            else:
                assert round(max(v.z for v in vertices)-min(v.z for v in vertices))==32
            assert faces and edges
        roots=scene.prefab_roots()
        before=[wire.serialize(r) for r in studio.prefab_records(roots,Vector())]
        fingerprint=quitting.fingerprint()
        bpy.context.scene.ruster_show_volumes=False
        assert all(root.empty_display_size<=.0001 for root in roots)
        assert quitting.fingerprint()==fingerprint
        assert before==[wire.serialize(r) for r in studio.prefab_records(roots,Vector())]
        path=str(Path(directory)/'volumes.blend')
        bpy.ops.wm.save_as_mainfile(filepath=path)
        bpy.ops.wm.open_mainfile(filepath=path)
        assert not bpy.context.scene.ruster_show_volumes
        assert len(scene.prefab_roots())==3
        bpy.context.scene.ruster_show_volumes=True
        assert all(volumes.meshes(root) for root in scene.prefab_roots())
        # Cached legacy effects are relabeled without another game conversion.
        effect=asset(4,'BoxCollider');effect.update(marker='SOUND',colliders=[],
            path='assets/bundled/prefabs/fx/impacts/stab/concrete/concrete1.prefab')
        (cache/'4.json.gz').write_bytes(gzip.compress(json.dumps(effect).encode()))
        root=scene.root_object([wire.encode(2,0,4)],bpy.context.scene.collection)
        assert scene.attach_visual(root) and root['ruster_marker']=='EFFECT'
        assert root.empty_display_type=='ARROWS' and 'impact effect' in root.name
        # Saved projects with old helper markers schedule the targeted upgrade.
        legacy=asset(5,'BoxCollider');legacy.update(marker='HELPER',colliders=[])
        (cache/'5.json.gz').write_bytes(gzip.compress(json.dumps(legacy).encode()))
        root=scene.root_object([wire.encode(2,0,5)],bpy.context.scene.collection)
        root['ruster_marker']='HELPER';root.empty_display_type='SPHERE'
        app.restore_cached_visuals([root])
        assert 5 in app._visual_queue
        native_request=app.request_assets;requests=[]
        app.request_assets=lambda ids:requests.append(ids) or True
        try:
            while app._visual_queue:app.load_visuals()
            assert requests==[[5]] and root['ruster_model_error_kind']=='PREVIEW_UPGRADE'
            assert root['ruster_model_status'].startswith('Loading updated')
            assert not root.get('ruster_marker') and root.empty_display_type=='CUBE'
            root['ruster_model_error']='Source asset unavailable'
            app._visual_queue=[5];app.load_visuals()
            assert requests==[[5]],'Failed cache upgrades must not retry forever'
        finally:app.request_assets=native_request
        ruster.unregister()
    print('RUSTER_VOLUMES_OK',flush=True)


if __name__=='__main__':
    try:run()
    except Exception:traceback.print_exc();os._exit(1)
