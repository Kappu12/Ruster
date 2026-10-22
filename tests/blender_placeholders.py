"""Unresolved placements remain visible without changing Rust placement data."""
import base64
import gzip
import json
import os
from pathlib import Path
import sys
import tempfile
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if '--' in sys.argv:
    sys.path.insert(0, sys.argv[sys.argv.index('--') + 1])
import bpy
from mathutils import Matrix, Vector
import ruster
from ruster import scene, studio
from ruster.core import wire
from tests.fixtures import sample_world, triangle_asset


def run():
    with tempfile.TemporaryDirectory(prefix='ruster-placeholders-') as directory:
        os.environ['RUSTER_USER_DIR'] = directory
        ruster.register()
        fields = sample_world().prefabs[0]
        root = scene.root_object(fields, bpy.context.scene.collection)
        bpy.context.view_layer.update()
        matrix = root.matrix_world.copy()
        record = root['ruster_record']
        assert root.type == 'EMPTY' and root.data is None
        assert root.empty_display_type == 'CUBE' and root.empty_display_size == .5
        assert 'placeholder' in root['ruster_model_status']
        assert not scene.attach_visual(root) and not root.get('ruster_visual')
        # Existing unresolved projects gain the box too, without losing status.
        root.empty_display_type = 'PLAIN_AXES'
        root['ruster_model_status'] = 'Loading model and materials…'
        assert not scene.attach_visual(root)
        assert root.empty_display_type == 'CUBE'
        assert root['ruster_model_status'] == 'Loading model and materials…'
        cache = scene.cache_dir() / 'prefabs'
        cache.mkdir(parents=True)
        uid = int(root['ruster_uid'])
        (cache / f'{uid}.json.gz').write_bytes(gzip.compress(json.dumps(triangle_asset(uid)).encode()))
        assert scene.attach_visual(root)
        collection = root.instance_collection
        assert collection.library and root.get('ruster_visual')
        assert root.empty_display_type == 'PLAIN_AXES' and root.empty_display_size < .001
        assert root['ruster_model_status'] == 'Model loaded'
        bpy.context.view_layer.update()
        assert root.matrix_world == matrix and root['ruster_record'] == record
        assert base64.b64decode(record) == wire.serialize(fields)
        # A second placement exercises the already-linked collection path.
        second = scene.root_object(fields, bpy.context.scene.collection)
        assert scene.attach_visual(second) and second.instance_collection == collection
        assert second.empty_display_size < .001
        # Removing the live IDs exercises loading the existing on-disk library.
        bpy.data.objects.remove(root, do_unlink=True)
        bpy.data.objects.remove(second, do_unlink=True)
        bpy.data.collections.remove(collection)
        third = scene.root_object(fields, bpy.context.scene.collection)
        assert scene.attach_visual(third) and third.instance_collection.library
        assert third.empty_display_size < .001
        exported = studio.prefab_records([third], scene.to_blender((0, 0, 0)))
        assert wire.serialize(exported[0]) == wire.serialize(fields)
        # Sound, terrain and runtime helpers retain their explicit marker status.
        for i, marker in enumerate(('SOUND', 'TERRAIN', 'HELPER'), 1):
            asset = triangle_asset(uid + i)
            asset.update(marker=marker, meshes={}, materials={})
            (cache / f'{uid+i}.json.gz').write_bytes(gzip.compress(json.dumps(asset).encode()))
            helper = scene.root_object([wire.encode(2, 0, uid + i)], bpy.context.scene.collection)
            assert scene.attach_visual(helper) and helper['ruster_marker'] == marker
            assert not helper['ruster_visual'] and helper.instance_collection is None
            assert 'placeholder' not in helper['ruster_model_status']
            display = helper.empty_display_type
            scene.model_placeholder(helper)
            assert helper.empty_display_type == display
        # Long thin tubes and very large placements must survive float32 TRS.
        rotation = scene.unity_euler((23.7, 44.999996, 17.2))
        for scale in ((772.098999, 1, .821408), (100000, .001, -2), (1, 1, 1)):
            transform = Matrix.LocRotScale(Vector((10000, 42, -8000)), rotation, Vector(scale))
            assert not scene.matrix_has_shear(transform)
        # A rotated child under a nonuniformly scaled group creates real shear.
        shear = Matrix.Diagonal((2, 1, 1, 1)) @ Matrix.Rotation(.7, 4, 'Z')
        assert scene.matrix_has_shear(shear)
        assert scene.matrix_has_shear(Matrix.Diagonal((0, 1, 1, 1)))
        source = Path(directory) / 'source.map'
        source.write_bytes(sample_world().write())
        bpy.context.scene.ruster.mode = 'MAP'
        bpy.context.scene.ruster.source_map = str(source)
        third.matrix_world = shear
        bpy.context.view_layer.update()
        # Blender decomposes an unparented assignment to TRS; model actual group shear.
        group = bpy.data.objects.new('Nonuniform group', None)
        bpy.context.scene.collection.objects.link(group)
        group['ruster_kind'] = 'GROUP'
        group.scale = (2, 1, 1)
        third.parent = group
        third.rotation_euler = (0, 0, .7)
        third.scale = (1, 1, 1)
        errors, _ = scene.validate()
        assert any('introduce shear' in error for error in errors), errors
        ruster.unregister()
    print('RUSTER_LOADING_PLACEHOLDERS_OK', flush=True)


try:
    run()
except Exception:
    traceback.print_exc()
    os._exit(1)
