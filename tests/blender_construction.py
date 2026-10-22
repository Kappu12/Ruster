"""Exercise snapping, radial placement, linked models and saved symmetry sets."""
import gzip
import json
import math
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if '--' in sys.argv and sys.argv[sys.argv.index('--')+1:]:
    sys.path.insert(0, sys.argv[sys.argv.index('--')+1])
import bpy
from mathutils import Matrix, Vector
import ruster
from ruster import app, construction, placement, scene, studio
from ruster.assets import catalog
from tests.fixtures import triangle_asset


def near(a, b):
    assert (Vector(a)-Vector(b)).length < 1e-4, (a, b)


def run():
    with tempfile.TemporaryDirectory(prefix='ruster-construction-') as temporary:
        directory = Path(temporary)
        os.environ['RUSTER_USER_DIR'] = str(directory/'user')
        ruster.register()
        studio.new_prefab()
        uid = 123456
        cache = scene.cache_dir()
        from contextlib import closing
        with closing(catalog.connect(cache)) as db:
            db.execute('INSERT INTO names VALUES(?,?)', (uid, 'assets/test/triangle.prefab'))
            db.commit()
        (cache/'prefabs').mkdir(parents=True, exist_ok=True)
        (cache/'prefabs'/f'{uid}.json.gz').write_bytes(gzip.compress(json.dumps(triangle_asset(uid)).encode()))
        settings = bpy.context.scene.ruster_construction
        tools = bpy.context.scene.tool_settings
        assert not settings.symmetry and not settings.object_snap
        settings.object_snap = True
        assert tools.use_snap and tools.use_snap_translate and not tools.use_snap_rotate
        assert tools.snap_elements == {'VERTEX'} and not tools.use_snap_selectable
        for mode in ('FACE', 'EDGE', 'VERTEX'):
            settings.snap_element = mode
            assert tools.snap_elements == {mode}
        for angle in ('45', '90'):
            settings.angle_snap = angle
            assert tools.use_snap_rotate
            assert abs(tools.snap_angle_increment_3d-math.radians(int(angle))) < 1e-6
            assert abs(tools.snap_angle_increment_3d_precision-math.radians(int(angle))) < 1e-6
        settings.object_snap = False
        assert tools.use_snap and not tools.use_snap_translate and tools.use_snap_rotate
        settings.angle_snap = 'OFF'
        assert not tools.use_snap
        settings.symmetry = True
        settings.center = (3, -2, 1)
        settings.sides = 4
        bpy.context.scene.cursor.location = (13, -2, 4)
        assert bpy.ops.ruster.place(uid=str(uid)) == {'FINISHED'}
        source = bpy.context.object
        peers = construction.symmetry_members([source])
        assert len(peers) == 3 and len(scene.prefab_roots()) == 4
        assert list(bpy.context.selected_objects) == [source]
        assert len({obj['ruster_instance'] for obj in scene.prefab_roots()}) == 4
        for obj, position in zip(peers, [(3,8,4), (-7,-2,4), (3,-12,4)]):
            near(obj.matrix_world.translation, position)
            assert obj.instance_collection == source.instance_collection
            assert obj.instance_collection.library and not obj.instance_collection.is_editable
        source.location = (8, 3, 7)
        source.rotation_euler = (.2, .4, .6)
        source.scale = (2, 3, 4)
        bpy.context.view_layer.update()
        construction.sync_symmetry(bpy.context.scene)
        bpy.context.view_layer.update()
        for obj in peers:
            expected = construction.radial_matrix(source.matrix_world, settings.center, obj['ruster_symmetry_angle'])
            for row, other in zip(obj.matrix_world, expected):near(row, other)
        settings.angle_snap = '45'
        assert bpy.ops.ruster.snap_rotation() == {'FINISHED'}
        bpy.context.view_layer.update()
        euler = source.matrix_world.to_euler()
        for value in euler:assert abs(value/(math.pi/4)-round(value/(math.pi/4))) < 1e-4
        # Changing the next set's controls leaves the existing set unchanged.
        settings.sides = 6
        settings.center = (0, 0, 0)
        bpy.context.scene.cursor.location = (6, 0, 0)
        assert bpy.ops.ruster.place(uid=str(uid)) == {'FINISHED'}
        second = bpy.context.object
        assert len(construction.symmetry_members([second])) == 5
        assert len(scene.prefab_roots()) == 10
        # A companion can take the user back to its editable original.
        placement.select([construction.symmetry_members([second])[0]])
        assert bpy.ops.ruster.symmetry_original() == {'FINISHED'}
        assert bpy.context.object == second
        app.save_project(directory/'symmetry.ruster')
        app.open_path(directory/'symmetry.ruster')
        settings = bpy.context.scene.ruster_construction
        assert settings.symmetry and settings.sides == 6 and settings.angle_snap == '45'
        second = next(obj for obj in scene.prefab_roots() if not obj.get('ruster_symmetry_source') and abs(obj.location.x-6) < 1e-4)
        second.location.y = 2
        bpy.context.view_layer.update()
        construction.sync_symmetry(bpy.context.scene)
        bpy.context.view_layer.update()
        near(construction.symmetry_members([second])[0].matrix_world.translation, (3-math.sqrt(3), 3*math.sqrt(3)+1, 0))
        # Duplicate a companion independently; deleting its source removes only
        # the original set, and release allows all remaining copies to be edited.
        peer = construction.symmetry_members([second])[0]
        placement.select([peer])
        duplicate = placement.duplicate_selected()[0]
        assert not duplicate.get('ruster_symmetry_source')
        placement.select([second])
        placement.delete_selected()
        assert len(scene.prefab_roots()) == 5
        first = next(obj for obj in scene.prefab_roots() if not obj.get('ruster_symmetry_source') and obj != duplicate)
        placement.select([first])
        assert bpy.ops.ruster.symmetry_release() == {'FINISHED'}
        assert not any(obj.get('ruster_symmetry_source') for obj in scene.prefab_roots())
        count = len(scene.prefab_roots())
        settings.symmetry = False
        assert bpy.ops.ruster.place(uid=str(uid)) == {'FINISHED'}
        assert len(scene.prefab_roots()) == count+1
        ruster.unregister()
        assert construction.sync_symmetry not in bpy.app.handlers.depsgraph_update_post
    print('Construction snapping and symmetry checks passed', flush=True)


run()
