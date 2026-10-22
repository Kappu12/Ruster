"""Runs inside real Blender, headless or GUI. No game installation required."""
import gzip
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if '--' in sys.argv and sys.argv[sys.argv.index('--')+1:]:
    # Test the staged package itself when invoked by tools/package.py.
    sys.path.insert(0, sys.argv[sys.argv.index('--')+1])

import bpy
from mathutils import Vector
import ruster
from ruster import app, scene
from ruster.core import wire, project
from ruster.core.rust_map import RustMap, prefab_transform
from tests.fixtures import sample_world


def run():
    with tempfile.TemporaryDirectory(prefix='ruster-smoke-') as directory:
        directory = Path(directory)
        os.environ['RUSTER_USER_DIR'] = str(directory/'user')
        ruster.register()
        assert hasattr(bpy.context.scene, 'ruster')
        assert bpy.context.scene.ruster.mode == 'BLENDER'
        assert 'Modeling' in bpy.data.workspaces
        source = directory/'source.map'
        source.write_bytes(sample_world().write())
        original = RustMap.load(source)
        scene.import_map(source)
        assert bpy.context.scene.ruster.mode == 'MAP'
        assert len(scene.prefab_roots()) == 2
        terrain = next(o for o in bpy.context.scene.objects if o.get('ruster_kind') == 'TERRAIN')
        assert len(terrain.data.vertices) == 33*33
        assert max(v.co.z for v in terrain.data.vertices) > 110
        assert len([o for o in bpy.context.scene.objects if o.get('ruster_kind') == 'PATH_PREVIEW']) == 1
        # Test Unity Euler conversion, including the singular case, by comparing rotations.
        for angles in [(0,90,0),(10,20,30),(-70,160,35),(90,50,15),(-90,-70,20)]:
            q = scene.unity_euler(angles)
            assert abs(q.dot(scene.unity_euler(scene.blender_euler(q)))) > 1-1e-6
        unchanged = directory/'unchanged.map'
        scene.export_map(unchanged)
        assert wire.serialize(RustMap.load(unchanged).fields) == wire.serialize(original.fields)
        root = scene.prefab_roots()[0]
        root.location += Vector((5,7,11))
        edited = directory/'edited.map'
        scene.export_map(edited)
        changed = RustMap.load(edited)
        before = prefab_transform(original.prefabs[0])[0]
        after = prefab_transform(changed.prefabs[0])[0]
        assert tuple(round(a-b,3) for a,b in zip(after,before)) == (5,11,7)
        assert [f.raw for f in original.fields if f.number!=3] == [f.raw for f in changed.fields if f.number!=3]
        # Attach a tiny original test asset: proves conversion cache -> Blender mesh/material.
        cache = scene.cache_dir()/'prefabs'
        cache.mkdir(parents=True)
        uid = root['ruster_uid']
        fixture = {'schema':1,'path':'assets/test/pyramid.prefab','uid':int(uid),
          'nodes':[{'name':'Pyramid','parent':None,'position':[0,0,0],'rotation':[1,0,0,0],
                    'scale':[1,1,1],'mesh':'test','materials':['testmat']}],
          'meshes':{'test':{'vertices':[[0,0,0],[2,0,0],[0,2,0],[0,0,2]],
                            'submeshes':[[[0,1,2],[0,3,1],[0,2,3],[1,3,2]]],'uv':[]}},
          'materials':{'testmat':{'name':'Test','color':[.6,.3,.1,1],'texture':None}}}
        (cache/f'{uid}.json.gz').write_bytes(gzip.compress(json.dumps(fixture).encode()))
        assert scene.attach_visual(root)
        assert root.instance_type == 'COLLECTION'
        assert root.instance_collection.objects[0].type == 'MESH'
        for obj in bpy.context.selected_objects:
            obj.select_set(False)
        root.select_set(True)
        bpy.context.view_layer.objects.active = root
        assert bpy.ops.ruster.duplicate() == {'FINISHED'}
        assert len(scene.prefab_roots()) == 3
        assert bpy.context.active_object.instance_collection == root.instance_collection
        assert bpy.ops.ruster.delete() == {'FINISHED'}
        assert len(scene.prefab_roots()) == 2
        target = directory/'world.ruster'
        assert bpy.ops.ruster.save(filepath=str(target)) == {'FINISHED'}
        assert target.exists()
        scene.clear_scene()
        source.unlink()
        app.open_path(target)
        assert bpy.context.scene.ruster.mode == 'MAP'
        assert Path(bpy.context.scene.ruster.source_map).is_file()
        assert len(scene.prefab_roots()) == 2
        assert any(o.instance_collection is not None for o in scene.prefab_roots())
        assert bpy.context.preferences.filepaths.use_scripts_auto_execute is False
        assert bpy.ops.ruster.save(filepath=str(directory/'again.ruster')) == {'FINISHED'}
        scene.export_map(directory/'after-reopen.map')
        bpy.ops.mesh.primitive_cube_add()
        assert any('custom objects' in e for e in scene.validate()[0])
        assert bpy.ops.ruster.new('EXEC_DEFAULT') == {'FINISHED'}
        assert bpy.context.scene.ruster.mode == 'BLENDER'
        assert 'Modeling' in bpy.data.workspaces
        assert bpy.ops.ruster.save(filepath=str(directory/'blank.ruster')) == {'FINISHED'}
        app.open_path(directory/'blank.ruster')
        assert bpy.context.scene.ruster.mode == 'BLENDER'
        assert bpy.data.objects.get('Cube')
        ruster.unregister()
        assert not hasattr(bpy.types.Scene,'ruster')
        ruster.register()
        ruster.unregister()
    print('RUSTER_BLENDER_SMOKE_OK',flush=True)


try:
    run()
except Exception:
    import traceback
    traceback.print_exc()
    # Blender can otherwise return zero after a Python exception.
    os._exit(1)
