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
from mathutils import Euler, Matrix, Vector
import ruster
from ruster import app, construction, placement, scene, studio
from ruster.assets import catalog
from tests.fixtures import triangle_asset


def near(a, b):
    assert (Vector(a)-Vector(b)).length < 1e-4, (a, b)


def refresh():
    bpy.context.view_layer.update()
    construction.sync_symmetry(bpy.context.scene)
    bpy.context.view_layer.update()


def matrix_near(actual, expected):
    assert max(abs(a-b) for row, other in zip(actual, expected) for a, b in zip(row, other)) < 2e-4, (actual, expected)


def assert_set(source_id, canonical, center):
    members = [obj for obj in scene.prefab_roots() if obj.get('ruster_instance') == source_id
               or obj.get('ruster_symmetry_source') == source_id]
    for obj in members:
        matrix_near(obj.matrix_world, construction.radial_matrix(canonical, center, obj.get('ruster_symmetry_angle', 0.)))
    return members


def new_set(uid, sides=4, center=(3, -2, 1)):
    studio.new_prefab()
    refresh()
    settings = bpy.context.scene.ruster_construction
    settings.symmetry, settings.sides, settings.center = True, sides, center
    settings.object_snap, settings.angle_snap = False, 'OFF'
    bpy.context.scene.cursor.location = Vector(center)+Vector((7, 0, 2))
    assert bpy.ops.ruster.place(uid=str(uid)) == {'FINISHED'}
    source = bpy.context.object
    refresh()
    return source, [obj for obj in scene.prefab_roots() if obj != source]


def any_member_regressions(uid, directory):
    center = (3, -2, 1)
    source, peers = new_set(uid, center=center)
    source_id, model = source['ruster_instance'], source.instance_collection
    driver = peers[1]
    desired = Matrix.LocRotScale(Vector((9, 7, 5)), Euler((.2, -.35, .7), 'XYZ').to_quaternion(), Vector((1.25, .8, 2.)))
    driver.matrix_world = desired
    refresh()
    canonical = construction.radial_matrix(desired, center, -driver['ruster_symmetry_angle'])
    assert len(assert_set(source_id, canonical, center)) == 4
    matrix_near(driver.matrix_world, desired)
    assert all(obj.instance_collection == model and obj.instance_collection.library for obj in scene.prefab_roots())
    # The original remains a driver after editing a companion.
    desired = Matrix.LocRotScale(Vector((5, -7, 8)), Euler((-.4, .1, -.6), 'XYZ').to_quaternion(), Vector((.75, 1.5, 2.5)))
    source.matrix_world = desired
    refresh()
    assert_set(source_id, desired, center)
    # New-set controls must not replace this set's saved center/angles.
    settings = bpy.context.scene.ruster_construction
    settings.center, settings.sides = (40, 30, 20), 7
    desired = driver.matrix_world.copy()
    desired.translation += Vector((2, 3, -1))
    driver.matrix_world = desired
    refresh()
    canonical = construction.radial_matrix(desired, center, -driver['ruster_symmetry_angle'])
    assert_set(source_id, canonical, center)
    saved = {obj['ruster_instance']: obj.matrix_world.copy() for obj in scene.prefab_roots()}
    app.save_project(directory/'any-member.ruster')
    app.open_path(directory/'any-member.ruster')
    refresh()
    for obj in scene.prefab_roots():matrix_near(obj.matrix_world, saved[obj['ruster_instance']])
    source = next(obj for obj in scene.prefab_roots() if obj.get('ruster_instance') == source_id)
    driver = next(obj for obj in scene.prefab_roots() if obj.get('ruster_symmetry_source') == source_id)
    desired = driver.matrix_world.copy()
    desired.translation += Vector((-3, 1, 2))
    driver.matrix_world = desired
    refresh()
    canonical = construction.radial_matrix(desired, center, -driver['ruster_symmetry_angle'])
    assert_set(source_id, canonical, center)
    # Disabled edits and deletion leave every other member in place.
    bpy.context.scene.ruster_construction.symmetry = False
    refresh()
    others = {obj.name: obj.matrix_world.copy() for obj in scene.prefab_roots() if obj != driver}
    desired = driver.matrix_world.copy()
    desired.translation += Vector((11, -4, 3))
    driver.matrix_world = desired
    refresh()
    matrix_near(driver.matrix_world, desired)
    for name, matrix in others.items():matrix_near(bpy.context.scene.objects[name].matrix_world, matrix)
    bpy.data.objects.remove(source, do_unlink=True)
    refresh()
    assert len(scene.prefab_roots()) == 3
    bpy.context.scene.ruster_construction.symmetry = True
    refresh()
    desired = driver.matrix_world.copy()
    desired.translation += Vector((1, 2, 3))
    driver.matrix_world = desired
    refresh()
    canonical = construction.radial_matrix(desired, center, -driver['ruster_symmetry_angle'])
    assert len(assert_set(source_id, canonical, center)) == 3
    # Both Ruster deletion and direct Blender removal expand from any member.
    for direct in (False, True):
        for original in (False, True):
            source, peers = new_set(uid)
            victim = source if original else peers[0]
            if direct:bpy.data.objects.remove(victim, do_unlink=True)
            else:
                placement.select([victim])
                placement.delete_selected()
            refresh()
            assert not scene.prefab_roots(), 'Deleting a member did not remove its enabled symmetry set'
    for original in (False, True):
        source, peers = new_set(uid)
        bpy.context.scene.ruster_construction.symmetry = False
        refresh()
        placement.select([source if original else peers[0]])
        placement.delete_selected()
        refresh()
        assert len(scene.prefab_roots()) == 3, 'Disabled deletion removed another member'
    source, peers = new_set(uid, sides=2)
    bpy.data.objects.remove(peers[0], do_unlink=True)
    refresh()
    assert not scene.prefab_roots(), 'Deleting the sole companion left the original'
    # MCP duplicates remain independent; its delete count covers the whole set.
    from ruster import mcp_bridge
    server = mcp_bridge.RusterMCPServer(9877, 'construction-test-token-1234567890123456789')
    source, peers = new_set(uid)
    result = server.dispatch('duplicate_objects', {'names': [peers[0].name], 'offset': [2, 0, 0]})
    duplicate = bpy.context.scene.objects[result['objects'][0]]
    assert not duplicate.get('ruster_symmetry_source')
    result = server.dispatch('delete_objects', {'names': [peers[0].name]})
    refresh()
    assert result['deleted_objects'] == 4 and len(result['deleted']) == 4
    assert scene.prefab_roots() == [duplicate]
    # Undo restores complete sets and seeds the next companion edit.
    studio.new_prefab()
    refresh()
    bpy.context.preferences.edit.use_global_undo = True
    bpy.ops.ed.undo_push(message='Before symmetry regression')
    source, peers = new_set(uid)
    source_id, driver_id = source['ruster_instance'], peers[1]['ruster_instance']
    before = {obj['ruster_instance']: obj.matrix_world.copy() for obj in scene.prefab_roots()}
    bpy.ops.ed.undo_push(message='Symmetry regression placement')
    desired = peers[1].matrix_world.copy()
    desired.translation += Vector((2, -3, 1))
    peers[1].matrix_world = desired
    refresh()
    moved = {obj['ruster_instance']: obj.matrix_world.copy() for obj in scene.prefab_roots()}
    bpy.ops.ed.undo_push(message='Symmetry regression companion move')
    assert bpy.ops.ed.undo() == {'FINISHED'}
    refresh()
    assert len(scene.prefab_roots()) == 4
    for obj in scene.prefab_roots():matrix_near(obj.matrix_world, before[obj['ruster_instance']])
    assert bpy.ops.ed.redo() == {'FINISHED'}
    refresh()
    for obj in scene.prefab_roots():matrix_near(obj.matrix_world, moved[obj['ruster_instance']])
    driver = next(obj for obj in scene.prefab_roots() if obj['ruster_instance'] == driver_id)
    placement.select([driver])
    placement.delete_selected()
    refresh()
    bpy.ops.ed.undo_push(message='Symmetry regression delete set')
    assert not scene.prefab_roots()
    assert bpy.ops.ed.undo() == {'FINISHED'}
    refresh()
    assert len(scene.prefab_roots()) == 4
    for obj in scene.prefab_roots():matrix_near(obj.matrix_world, moved[obj['ruster_instance']])
    assert bpy.ops.ed.redo() == {'FINISHED'}
    refresh()
    assert not scene.prefab_roots()
    assert bpy.ops.ed.undo() == {'FINISHED'}
    refresh()
    driver = next(obj for obj in scene.prefab_roots() if obj['ruster_instance'] == driver_id)
    desired = driver.matrix_world.copy()
    desired.translation += Vector((-1, 2, 0))
    driver.matrix_world = desired
    refresh()
    canonical = construction.radial_matrix(desired, center, -driver['ruster_symmetry_angle'])
    assert len(assert_set(source_id, canonical, center)) == 4


def extended_symmetry_regressions(uid, directory):
    for axis in 'XYZ':
        for rotate in (True, False):
            studio.new_prefab();refresh()
            settings = bpy.context.scene.ruster_construction
            settings.symmetry = False
            settings.sides, settings.axis, settings.rotate_copies = 4, axis, rotate
            settings.center = (2, -3, 1)
            bpy.context.scene.cursor.location = (8, 5, 4)
            bpy.ops.ruster.place(uid=str(uid))
            source = bpy.context.object
            source.rotation_euler = (.2, -.5, .7)
            refresh()
            assert bpy.ops.ruster.symmetry_create() == {'FINISHED'}
            refresh()
            peers = construction.symmetry_members([source])
            for peer in peers:
                expected = construction.radial_matrix(source.matrix_world, settings.center, peer['ruster_symmetry_angle'], axis, rotate)
                matrix_near(peer.matrix_world, expected)
            peer = peers[0]
            placement.select([peer])
            desired = peer.matrix_world.copy();desired.translation += Vector((1, 2, 3))
            peer.matrix_world = desired;refresh()
            anchor = construction.radial_matrix(desired, settings.center, -peer['ruster_symmetry_angle'], axis, rotate)
            matrix_near(source.matrix_world, anchor)
            # Explicit apply updates a set, preserving surviving instance IDs.
            old_ids = {o['ruster_instance'] for o in scene.prefab_roots()}
            settings.sides, settings.axis, settings.center = 6, 'Y', (7, 1, -2)
            assert bpy.ops.ruster.symmetry_apply() == {'FINISHED'}
            refresh()
            assert len(scene.prefab_roots()) == 6
            assert old_ids <= {o['ruster_instance'] for o in scene.prefab_roots()}
            settings.sides = 2
            assert bpy.ops.ruster.symmetry_apply() == {'FINISHED'}
            refresh()
            assert len(scene.prefab_roots()) == 2
            assert bpy.ops.ruster.symmetry_select() == {'FINISHED'}
            assert len(bpy.context.selected_objects) == 2
    # Moving a whole group must move its symmetry frame, not collapse members
    # back around the old world center. Rotation also tilts the saved axis.
    settings.axis, settings.rotate_copies = 'Z', True
    source, peers = new_set(uid)
    originals = {obj: obj.matrix_world.copy() for obj in [source, *peers]}
    root = placement.group([source, *peers]);refresh()
    delta = Matrix.LocRotScale(Vector((13, -6, 7)), Euler((.6, -.3, .2)).to_quaternion(), Vector((2, 2, 2)))
    root.matrix_world = delta @ root.matrix_world
    refresh()
    for obj, before in originals.items():matrix_near(obj.matrix_world, delta @ before)
    transformed_center = delta @ Vector((3, -2, 1))
    near(peers[0]['ruster_symmetry_center'], transformed_center)
    desired = peers[0].matrix_world.copy();desired.translation += Vector((1, -2, 0))
    peers[0].matrix_world = desired;refresh()
    anchor = construction.member_matrix(desired, peers[0], -peers[0]['ruster_symmetry_angle'])
    matrix_near(source.matrix_world, anchor)
    # Saved settings and tilted set axes survive a project roundtrip.
    matrices = {o['ruster_instance']: o.matrix_world.copy() for o in scene.prefab_roots()}
    settings.axis, settings.rotate_copies = 'X', False
    app.save_project(directory/'extended-symmetry.ruster')
    app.open_path(directory/'extended-symmetry.ruster');refresh()
    settings = bpy.context.scene.ruster_construction
    assert settings.axis == 'X' and not settings.rotate_copies
    for obj in scene.prefab_roots():matrix_near(obj.matrix_world, matrices[obj['ruster_instance']])
    # Failed creation must not enable symmetry or leave partial copies.
    studio.new_prefab();refresh()
    settings = bpy.context.scene.ruster_construction;settings.symmetry = False
    bpy.ops.ruster.place(uid=str(uid));source = bpy.context.object
    source['ruster_has_io'] = True
    try:bpy.ops.ruster.symmetry_create()
    except RuntimeError as error:assert 'metadata' in str(error)
    else:raise AssertionError('Cloned imported IO metadata')
    assert not settings.symmetry and scene.prefab_roots() == [source]
    settings.axis, settings.rotate_copies = 'Z', True


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
        any_member_regressions(uid, directory)
        extended_symmetry_regressions(uid, directory)
        ruster.unregister()
        assert construction.sync_symmetry not in bpy.app.handlers.depsgraph_update_post
    print('Construction snapping and symmetry checks passed', flush=True)


run()
