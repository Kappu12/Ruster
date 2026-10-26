"""Real toolbar draws, native transform snapping and symmetry undo/redo.

Run with --enable-event-simulate in a graphical Blender session.
"""
import gzip
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if '--' in sys.argv and sys.argv[sys.argv.index('--')+1:]:
    sys.path.insert(0, sys.argv[sys.argv.index('--')+1])
import bpy
from bpy_extras import view3d_utils
from mathutils import Quaternion, Vector
import ruster
from ruster import app, construction, placement, scene, studio, ui
from ruster.assets import catalog
from tests.fixtures import triangle_asset

temporary = tempfile.TemporaryDirectory(prefix='ruster-gui-construction-')
os.environ['RUSTER_USER_DIR'] = str(Path(temporary.name)/'user')
state = {'stage': 0, 'draws': set()}
for cls in (construction.RUSTER_PT_construction, construction.RUSTER_PT_snapping, construction.RUSTER_PT_symmetry):
    original = cls.draw
    def checked(original, name):
        def draw(self, context):
            try:
                original(self, context)
                state['draws'].add(name)
            except Exception:
                traceback.print_exc()
                os._exit(1)
        return draw
    cls.draw = checked(original, cls.__name__)
ruster.register()
keymap = bpy.context.window_manager.keyconfigs.addon.keymaps['3D View']
keymap.keymap_items.new('ruster.symmetry_apply', 'F8', 'PRESS')
bpy.context.window_manager.keyconfigs.update()


def at_view():
    return bpy.context.temp_override(window=state['window'], area=state['area'], region=state['region'])


def point(world):
    result = view3d_utils.location_3d_to_region_2d(state['region'], state['area'].spaces.active.region_3d, Vector(world))
    assert result is not None
    return round(result.x+state['region'].x), round(result.y+state['region'].y)


def assert_matrices(expected):
    for name, matrix in expected.items():
        actual = bpy.context.scene.objects[name].matrix_world
        assert max(abs(a-b) for row, other in zip(actual, matrix) for a, b in zip(row, other)) < 2e-4, name


def perform():
    stage = state['stage']
    window = bpy.context.window
    if stage == 0:
        window.event_simulate(type='ESC', value='PRESS')
        studio.new_prefab()
        area = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
        state.update(window=window, area=area)
        area.spaces.active.show_region_toolbar = True
        cache = scene.cache_dir()
        from contextlib import closing
        with closing(catalog.connect(cache)) as db:
            db.execute('INSERT INTO names VALUES(?,?)', (123456, triangle_asset()['path']))
            db.commit()
        (cache/'prefabs').mkdir(parents=True, exist_ok=True)
        (cache/'prefabs/123456.json.gz').write_bytes(gzip.compress(json.dumps(triangle_asset()).encode()))
    elif stage == 1:
        state['region'] = next(r for r in state['area'].regions if r.type == 'WINDOW')
        assert 'RUSTER_PT_construction' in state['draws'], state['draws']
        settings = bpy.context.scene.ruster_construction
        settings.symmetry = True
        settings.sides = 6
        bpy.context.scene.cursor.location = (6, 0, 0)
        with at_view():
            bpy.ops.ed.undo_push(message='Before radial placement')
            bpy.ops.ruster.place(uid='123456')
            bpy.ops.ed.undo_push(message='Radial placement')
        assert len(scene.prefab_roots()) == 6
        source = bpy.context.object
        state['source_name'] = source.name
        space = state['area'].spaces.active
        space.region_3d.view_perspective = 'ORTHO'
        space.region_3d.view_rotation = Quaternion((1, 0, 0, 0))
        space.region_3d.view_location = (0, 0, 0)
        space.region_3d.view_distance = 25
    elif stage == 2:
        if bpy.context.scene.ruster.busy:return .1
        with at_view():bpy.ops.ed.undo()
        assert not scene.prefab_roots(), 'Placement was not a single undo step'
    elif stage == 3:
        with at_view():bpy.ops.ed.redo()
        assert len(scene.prefab_roots()) == 6
        assert all(obj.get('ruster_visual') for obj in scene.prefab_roots()) or app._visual_queue, 'Redo stranded a placeholder without queued preview recovery'
        settings = bpy.context.scene.ruster_construction
        settings.object_snap = True
        settings.angle_snap = '45'
        x, y = point((8, 0, 0))
        window.event_simulate(type='MOUSEMOVE', value='NOTHING', x=x, y=y)
    elif stage == 4:
        # Native modal rotation, approximately 31 degrees, must land on 45.
        with at_view():bpy.ops.transform.rotate('INVOKE_DEFAULT', orient_axis='Z')
    elif stage == 5:
        x, y = point((6+2*math.cos(.54), 2*math.sin(.54), 0))
        window.event_simulate(type='MOUSEMOVE', value='NOTHING', x=x, y=y)
    elif stage == 6:
        window.event_simulate(type='LEFTMOUSE', value='PRESS')
        window.event_simulate(type='LEFTMOUSE', value='RELEASE')
    elif stage == 7:
        source = bpy.data.objects[state['source_name']]
        angle = source.rotation_euler.z
        assert abs(abs(angle)-math.pi/4) < 1e-4, f'Native rotation did not snap to 45 degrees: {angle}'
        peers = construction.symmetry_members([source])
        assert len(peers) == 5
        for peer in peers:
            expected = construction.radial_matrix(source.matrix_world, (0,0,0), peer['ruster_symmetry_angle'])
            assert max(abs(a-b) for row, other in zip(peer.matrix_world, expected) for a,b in zip(row,other)) < 1e-4
        with at_view():bpy.ops.wm.call_panel(name='RUSTER_PT_snapping', keep_open=True)
    elif stage == 8:
        assert 'RUSTER_PT_snapping' in state['draws']
        window.event_simulate(type='ESC', value='PRESS')
    elif stage == 9:
        with at_view():bpy.ops.wm.call_panel(name='RUSTER_PT_symmetry', keep_open=True)
    elif stage == 10:
        assert 'RUSTER_PT_symmetry' in state['draws']
        bpy.ops.screen.screenshot(filepath=str(Path(temporary.name)/'construction-ui.png'))
        window.event_simulate(type='ESC', value='PRESS')
    elif stage == 11:
        # Snap one whole instance onto another instance's original geometry.
        settings = bpy.context.scene.ruster_construction
        settings.symmetry = False
        settings.angle_snap = 'OFF'
        settings.object_snap = True
        bpy.context.scene.cursor.location = (-3, 0, 0)
        with at_view():bpy.ops.ruster.place(uid='123456')
        state['moving'] = bpy.context.object.name
        x, y = point((-3,0,0))
        window.event_simulate(type='MOUSEMOVE', value='NOTHING', x=x, y=y)
    elif stage == 12:
        with at_view():bpy.ops.transform.translate('INVOKE_DEFAULT')
    elif stage == 13:
        # Root at (6,0), turned 45 degrees; this is one model vertex.
        state['target'] = (6+math.sqrt(2), math.sqrt(2), 0)
        x, y = point(state['target'])
        window.event_simulate(type='MOUSEMOVE', value='NOTHING', x=x+2, y=y+2)
    elif stage == 14:
        window.event_simulate(type='LEFTMOUSE', value='PRESS')
        window.event_simulate(type='LEFTMOUSE', value='RELEASE')
    elif stage == 15:
        moving = bpy.data.objects[state['moving']]
        print('Object snap result', tuple(moving.matrix_world.translation), 'target', state['target'], flush=True)
        assert (moving.matrix_world.translation-Vector(state['target'])).length < .02, 'Native object snapping missed linked instance geometry'
        bpy.context.scene.ruster_construction.angle_snap = '90'
        state['pivot'] = moving.matrix_world.translation.copy()
        x, y = point(state['pivot']+Vector((2,0,0)))
        window.event_simulate(type='MOUSEMOVE', value='NOTHING', x=x, y=y)
    elif stage == 16:
        with at_view():bpy.ops.transform.rotate('INVOKE_DEFAULT', orient_axis='Z')
    elif stage == 17:
        x, y = point(state['pivot']+Vector((2*math.cos(.95), 2*math.sin(.95), 0)))
        window.event_simulate(type='MOUSEMOVE', value='NOTHING', x=x, y=y)
    elif stage == 18:
        window.event_simulate(type='LEFTMOUSE', value='PRESS')
        window.event_simulate(type='LEFTMOUSE', value='RELEASE')
    elif stage == 19:
        moving = bpy.data.objects[state['moving']]
        assert abs(abs(moving.rotation_euler.z)-math.pi/2) < 1e-4, 'Native rotation did not snap to 90 degrees'
    elif stage == 20:
        settings = bpy.context.scene.ruster_construction
        settings.symmetry, settings.object_snap, settings.angle_snap = True, False, 'OFF'
        source = bpy.context.scene.objects[state['source_name']]
        peer = construction.symmetry_members([source])[1]
        state['peer_name'] = peer.name
        state['before_peer_move'] = {obj.name: obj.matrix_world.copy() for obj in [source, *construction.symmetry_members([source])]}
        state['independent_matrix'] = bpy.context.scene.objects[state['moving']].matrix_world.copy()
        placement.select([peer])
        state['desired_peer'] = peer.matrix_world.copy()
        state['desired_peer'].translation += Vector((1.5, -.75, 1.))
        with at_view():
            bpy.ops.ed.undo_push(message='Before companion translation')
            assert bpy.ops.transform.translate(value=(1.5, -.75, 1.)) == {'FINISHED'}
    elif stage == 21:
        peer = bpy.context.scene.objects[state['peer_name']]
        source = bpy.context.scene.objects[state['source_name']]
        assert_matrices({peer.name: state['desired_peer'], state['moving']: state['independent_matrix']})
        canonical = construction.radial_matrix(peer.matrix_world, (0,0,0), -peer['ruster_symmetry_angle'])
        for obj in [source, *construction.symmetry_members([source])]:
            assert_matrices({obj.name: construction.radial_matrix(canonical, (0,0,0), obj.get('ruster_symmetry_angle', 0.))})
        state['after_peer_move'] = {name: bpy.context.scene.objects[name].matrix_world.copy() for name in state['before_peer_move']}
        with at_view():bpy.ops.ed.undo_push(message='Companion translation')
    elif stage == 22:
        with at_view():assert bpy.ops.ed.undo() == {'FINISHED'}
        assert_matrices(state['before_peer_move'])
    elif stage == 23:
        with at_view():assert bpy.ops.ed.redo() == {'FINISHED'}
        assert_matrices(state['after_peer_move'])
    elif stage == 24:
        placement.select([bpy.context.scene.objects[state['peer_name']]])
        with at_view():assert bpy.ops.ruster.delete() == {'FINISHED'}
    elif stage == 25:
        assert len(scene.prefab_roots()) == 1, 'Companion deletion did not remove exactly its linked set'
        assert_matrices({state['moving']: state['independent_matrix']})
        with at_view():
            bpy.ops.ed.undo_push(message='Delete companion set')
            assert bpy.ops.ed.undo() == {'FINISHED'}
    elif stage == 26:
        assert len(scene.prefab_roots()) == 7
        assert_matrices(state['after_peer_move'])
        with at_view():assert bpy.ops.ed.redo() == {'FINISHED'}
    elif stage == 27:
        assert len(scene.prefab_roots()) == 1
        with at_view():assert bpy.ops.ed.undo() == {'FINISHED'}
    elif stage == 28:
        assert len(scene.prefab_roots()) == 7
        bpy.context.scene.ruster_construction.symmetry = False
        placement.select([bpy.context.scene.objects[state['peer_name']]])
        with at_view():assert bpy.ops.ruster.delete() == {'FINISHED'}
    elif stage == 29:
        assert len(scene.prefab_roots()) == 6, 'Disabled symmetry deleted another member'
        peer = next(obj for obj in scene.prefab_roots() if obj.get('ruster_symmetry_source'))
        state['disabled_others'] = {obj.name: obj.matrix_world.copy() for obj in scene.prefab_roots() if obj != peer}
        state['disabled_peer'] = peer.name
        state['disabled_desired'] = peer.matrix_world.copy()
        state['disabled_desired'].translation += Vector((2, 1, 0))
        placement.select([peer])
        with at_view():assert bpy.ops.transform.translate(value=(2, 1, 0)) == {'FINISHED'}
    elif stage == 30:
        assert_matrices(state['disabled_others'])
        assert_matrices({state['disabled_peer']: state['disabled_desired']})
    elif stage == 31:
        studio.new_prefab()
        settings = bpy.context.scene.ruster_construction
        settings.symmetry, settings.sides, settings.axis = True, 4, 'X'
        settings.rotate_copies = False
        bpy.context.scene.cursor.location = (0, 4, 0)
        with at_view():bpy.ops.ruster.place(uid='123456')
        assert len(scene.prefab_roots()) == 4
        window.event_simulate(type='MOUSEMOVE', value='NOTHING', x=state['region'].x+100, y=state['region'].y+100)
    elif stage == 32:
        bpy.context.scene.ruster_construction.sides = 6
        # Timer-invoked Python operators do not get Blender's automatic undo
        # push. Dispatch through a native keymap to test the real UI contract.
        with at_view():bpy.ops.ed.undo_push(message='Before symmetry resize')
        window.event_simulate(type='F8', value='PRESS', x=state['region'].x+100, y=state['region'].y+100)
        window.event_simulate(type='F8', value='RELEASE', x=state['region'].x+100, y=state['region'].y+100)
    elif stage == 33:
        assert len(scene.prefab_roots()) == 6, f'Resize did not run: {len(scene.prefab_roots())} placements'
        with at_view():bpy.ops.ed.undo()
        assert len(scene.prefab_roots()) == 4, 'Symmetry resize must undo in one step'
    elif stage == 34:
        with at_view():bpy.ops.ed.redo()
        assert len(scene.prefab_roots()) == 6
        assert all(tuple(obj.get('ruster_symmetry_axis', (1,0,0))) == (1,0,0) for obj in scene.prefab_roots())
    else:
        print('Graphical construction controls, native snapping, any-member symmetry and undo/redo passed', flush=True)
        bpy.ops.wm.quit_blender()
        return None
    state['stage'] += 1
    return .5


def tick():
    try:return perform()
    except Exception:
        traceback.print_exc()
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(1)


bpy.app.timers.register(tick, first_interval=2)
