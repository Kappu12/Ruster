"""Native duplicate/move, cancel, search, F9 and viewport controls."""
import gzip
import json
import os
from pathlib import Path
import sys
import tempfile
import traceback
from contextlib import closing

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import bpy
import ruster
from ruster import scene, studio, ui, layout, protection
from ruster.assets import catalog
from tests.fixtures import triangle_asset

temporary = tempfile.TemporaryDirectory(prefix='ruster-blender-controls-')
os.environ['RUSTER_USER_DIR'] = str(Path(temporary.name)/'user')
draws = set()


def checked(cls, name):
    original = cls.draw
    def draw(self, context):
        try:original(self, context);draws.add(name)
        except Exception:traceback.print_exc();os._exit(1)
    cls.draw = draw


for cls in (ui.RUSTER_MT_object, layout.RUSTER_MT_layout, layout.RUSTER_MT_symmetry,
            layout.RUSTER_PT_composition_checks, protection.RUSTER_MT_commands):checked(cls, cls.__name__)
checked(layout.RUSTER_OT_layout, 'layout_dialog')
ruster.register()
bpy.context.window_manager.keyconfigs.update()
state = {'stage': 0}


def tick():
    try:
        window = bpy.context.window_manager.windows[0]
        area = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
        region = next(r for r in area.regions if r.type == 'WINDOW')
        x, y = region.x+region.width//2, region.y+region.height//2
        def key(kind, **kwargs):
            window.event_simulate(type=kind, value='PRESS', x=x, y=y, **kwargs)
            kwargs.pop('unicode', None)
            window.event_simulate(type=kind, value='RELEASE', x=x, y=y, **kwargs)
        with bpy.context.temp_override(window=window, area=area, region=region):
            stage = state['stage']
            if stage == 0:
                key('ESC');studio.new_prefab()
                cache = scene.cache_dir()
                with closing(catalog.connect(cache)) as db:
                    db.execute('INSERT INTO names VALUES(?,?)', (123456, 'assets/test/triangle.prefab'));db.commit()
                (cache/'prefabs').mkdir(parents=True, exist_ok=True)
                (cache/'prefabs/123456.json.gz').write_bytes(gzip.compress(json.dumps(triangle_asset()).encode()))
                bpy.ops.ruster.place(uid='123456')
                state['source_id'] = bpy.context.object['ruster_instance']
                bpy.ops.ed.undo_push(message='Before native duplicate')
            elif stage == 1:key('D', shift=True)
            elif stage == 2:
                assert len(scene.prefab_roots()) == 2
                assert bpy.context.object['ruster_instance'] != state['source_id']
                key('X')
            elif stage == 3:key('THREE', unicode='3')
            elif stage == 4:key('RET')
            elif stage == 5:
                roots = scene.prefab_roots()
                assert len({obj['ruster_instance'] for obj in roots}) == 2
                assert roots[0].instance_collection == roots[1].instance_collection and roots[0].instance_collection.library
                assert abs(bpy.context.object.matrix_world.translation.x-3) < 1e-4
                assert not bpy.context.object.get('ruster_symmetry_source')
                bpy.ops.ed.undo()
                assert len(scene.prefab_roots()) == 1, 'Duplicate plus move must undo together'
            elif stage == 6:
                bpy.ops.ed.redo();assert len(scene.prefab_roots()) == 2
            elif stage == 7:key('D', shift=True)
            elif stage == 8:key('ESC')
            elif stage == 9:
                assert len(scene.prefab_roots()) == 3, 'Escape cancels only translation, like Blender'
                assert abs(bpy.context.object.matrix_world.translation.x-3) < 1e-4
                bpy.ops.ed.undo();assert len(scene.prefab_roots()) == 2
            elif stage == 10:key('F3')
            elif stage == 11:
                for char in 'linear array':key('SPACE' if char == ' ' else char.upper(), unicode=char)
            elif stage == 12:key('RET')
            elif stage == 13:
                assert 'layout_dialog' in draws, 'F3 must search and invoke a layout action'
                key('RET')
            elif stage == 14:
                assert len(scene.prefab_roots()) == 5
                assert bpy.context.window_manager.operators[-1].bl_idname == 'RUSTER_OT_layout'
                key('F9')
            elif stage == 15:
                bpy.ops.screen.screenshot(filepath=str(ROOT/'build/blender-controls-f9.png'))
                key('ESC')
            elif stage == 16:bpy.ops.wm.call_menu(name='RUSTER_MT_object')
            elif stage == 17:
                assert 'RUSTER_MT_object' in draws
                key('ESC')
            elif stage == 18:bpy.ops.wm.call_panel(name='RUSTER_PT_composition_checks', keep_open=True)
            elif stage == 19:
                assert 'RUSTER_PT_composition_checks' in draws
                key('ESC')
            elif stage == 20:key('X')
            elif stage == 21:
                assert len(scene.prefab_roots()) == 5, 'X must request confirmation'
                key('ESC')
            elif stage == 22:
                assert len(scene.prefab_roots()) == 5
                key('DEL')
            elif stage == 23:
                assert len(scene.prefab_roots()) == 2, 'Delete must remove selected copies immediately'
                bpy.ops.ed.undo()
            elif stage == 24:assert len(scene.prefab_roots()) == 5
            else:
                assert {'RUSTER_MT_layout','RUSTER_MT_symmetry','RUSTER_MT_commands'} <= draws
                print('Native Blender duplicate, cancel, undo, F3 search, F9 and menus passed', flush=True)
                bpy.ops.wm.quit_blender();return None
        state['stage'] += 1
        return .6
    except Exception:traceback.print_exc();os._exit(1)


bpy.app.timers.register(tick, first_interval=2)
