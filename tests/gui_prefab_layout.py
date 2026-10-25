"""Draw every layout dialog and check native operator undo in a disposable UI."""
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
from ruster import layout, studio, scene
from ruster.assets import catalog
from tests.fixtures import triangle_asset

temporary = tempfile.TemporaryDirectory(prefix='ruster-layout-ui-')
os.environ['RUSTER_USER_DIR'] = str(Path(temporary.name)/'user')
draws = set()


def checked_draw(cls, name):
    original = cls.draw
    def draw(self, context):
        try:
            original(self, context)
            draws.add(self.operation if name == 'layout' else name)
        except Exception:
            traceback.print_exc();os._exit(1)
    cls.draw = draw


checked_draw(layout.RUSTER_OT_layout, 'layout')
checked_draw(layout.RUSTER_OT_composition_check, 'check')
checked_draw(layout.RUSTER_PT_layout, 'panel')
ruster.register()
keymap = bpy.context.window_manager.keyconfigs.addon.keymaps['3D View']
item = keymap.keymap_items.new('ruster.layout', 'F8', 'PRESS')
item.properties.operation = 'LINEAR';item.properties.count = 3
item.properties.offset = (3, 0, 0)
bpy.context.window_manager.keyconfigs.update()
state = {'stage': 0}
operations = [value for value, _label, _description in layout.OPERATIONS]


def tick():
    try:
        stage = state['stage']
        window = bpy.context.window
        area = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
        region = next(r for r in area.regions if r.type == 'WINDOW')
        with bpy.context.temp_override(window=window, area=area, region=region):
            if stage == 0:
                window.event_simulate(type='ESC', value='PRESS')
                studio.new_prefab()
                cache = scene.cache_dir()
                with closing(catalog.connect(cache)) as db:
                    db.execute('INSERT INTO names VALUES(?,?)', (123456, 'assets/test/triangle.prefab'));db.commit()
                (cache/'prefabs').mkdir(parents=True, exist_ok=True)
                (cache/'prefabs/123456.json.gz').write_bytes(gzip.compress(json.dumps(triangle_asset()).encode()))
                bpy.ops.ruster.place(uid='123456')
                bpy.ops.ed.undo_push(message='Before layout')
            elif stage <= len(operations)*2:
                index = (stage-1)//2
                if stage % 2:
                    bpy.ops.ruster.layout('INVOKE_DEFAULT', operation=operations[index])
                else:
                    assert operations[index] in draws, draws
                    window.event_simulate(type='ESC', value='PRESS')
            elif stage == 13:bpy.ops.ruster.composition_check('INVOKE_DEFAULT')
            elif stage == 14:
                assert 'check' in draws
                window.event_simulate(type='ESC', value='PRESS')
            elif stage == 15:bpy.ops.wm.call_panel(name='RUSTER_PT_layout', keep_open=True)
            elif stage == 16:
                assert 'panel' in draws
                bpy.ops.screen.screenshot(filepath=str(ROOT/'build/prefab-layout-ui.png'))
                window.event_simulate(type='ESC', value='PRESS')
            elif stage == 17:
                window.event_simulate(type='MOUSEMOVE', value='NOTHING', x=region.x+100, y=region.y+100)
                window.event_simulate(type='F8', value='PRESS', x=region.x+100, y=region.y+100)
                window.event_simulate(type='F8', value='RELEASE', x=region.x+100, y=region.y+100)
            elif stage == 18:
                window.event_simulate(type='RET', value='PRESS', x=region.x+100, y=region.y+100)
                window.event_simulate(type='RET', value='RELEASE', x=region.x+100, y=region.y+100)
            elif stage == 19:
                assert len(scene.prefab_roots()) == 4
                bpy.ops.ed.undo()
                assert len(scene.prefab_roots()) == 1, 'Layout must undo in one step'
            elif stage == 20:
                bpy.ops.ed.redo()
                assert len(scene.prefab_roots()) == 4
            else:
                print('Graphical prefab layout dialogs and single-step undo/redo passed', flush=True)
                bpy.ops.wm.quit_blender();return None
        state['stage'] += 1
        return .5
    except Exception:
        traceback.print_exc();os._exit(1)


bpy.app.timers.register(tick, first_interval=2)
