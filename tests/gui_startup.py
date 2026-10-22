"""Exercise the real bootstrap, native splash and Scene tabs on a desktop."""
import os
from pathlib import Path
import runpy
import sys
import tempfile
import traceback

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
distribution = Path(sys.argv[sys.argv.index('--') + 1]) if '--' in sys.argv else ROOT
sys.path.insert(0, str(distribution))
temporary = tempfile.TemporaryDirectory(prefix='ruster-startup-')
os.environ['RUSTER_USER_DIR'] = str(Path(temporary.name) / 'user')
from ruster.core import settings

game = Path(temporary.name) / 'Rust'
(game / 'Bundles').mkdir(parents=True)
(game / 'RustClient.exe').write_bytes(b'MZ-test-fixture')
settings.save({'rust_install': str(game)})
runpy.run_path(str(distribution / 'bootstrap.py'))
from ruster import app, ui, studio
from tests.fixtures import sample_world

state = {'stage': 0, 'splash': False, 'start': False, 'scene': False}


def checked_draw(original, key):
    def draw(self, context):
        try:
            original(self, context)
            state[key] = True
        except Exception:
            traceback.print_exc()
            os._exit(1)
    return draw


bpy.types.WM_MT_splash.draw = checked_draw(bpy.types.WM_MT_splash.draw, 'splash')
bpy.types.WM_MT_splash_quick_setup.draw = checked_draw(bpy.types.WM_MT_splash_quick_setup.draw, 'splash')
ui.RUSTER_PT_start.draw = checked_draw(ui.RUSTER_PT_start.draw, 'start')
bpy.types.SCENE_PT_scene.draw = checked_draw(bpy.types.SCENE_PT_scene.draw, 'scene')
studio.RUSTER_MT_add.draw=checked_draw(studio.RUSTER_MT_add.draw,'add')
bpy.types.VIEW3D_PT_tools_active.draw=checked_draw(bpy.types.VIEW3D_PT_tools_active.draw,'toolbar')


def step():
    try:
        window = bpy.context.window_manager.windows[0]
        with bpy.context.temp_override(window=window):
            stage = state['stage']
            print('Startup/Scene regression stage', stage, flush=True)
            if stage == 0:
                assert state['splash'], 'Native Ruster splash did not draw'
                window.event_simulate(type='ESC', value='PRESS')
            elif stage == 1:
                assert state['start'], 'Persistent start controls did not draw'
                area = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
                region = next(r for r in area.regions if r.type == 'UI')
                assert area.spaces.active.show_region_ui and region.active_panel_category == 'Ruster'
                assert window.scene.ruster.mode=='PREFAB' and not list(window.scene.objects)
                assert not area.spaces.active.show_region_toolbar
                assert not any(a.type=='PROPERTIES' or a.ui_type=='TIMELINE' for a in window.screen.areas)
                area.spaces.active.show_region_toolbar=True
                with bpy.context.temp_override(area=area):bpy.ops.wm.call_menu(name='VIEW3D_MT_add')
            elif stage == 2:
                assert state.get('add'),'Blender Add menu did not route to Rust prefab categories'
                assert state.get('toolbar'),'The stripped placement toolbar did not draw'
                window.event_simulate(type='ESC',value='PRESS')
                path = Path(temporary.name) / 'test.map'
                path.write_bytes(sample_world().write())
                app.open_path(path)
            elif stage==3:
                assert ui.is_map(bpy.context)
                if bpy.app.timers.is_registered(ui.close_map_timeline):bpy.app.timers.unregister(ui.close_map_timeline)
                props=next(a for a in window.screen.areas if a.type=='OUTLINER')
                props.type='PROPERTIES';props.spaces.active.context='SCENE'
            elif 4 <= stage <= 8:
                # Explicitly recreate Properties to regression-test Scene context
                # callbacks even though the pared-down workspace removes it.
                props=next(a for a in window.screen.areas if a.type=='PROPERTIES')
                props.spaces.active.context=('SCENE','WORLD','VIEW_LAYER','RENDER','OUTPUT')[stage-4]
            elif stage==9:
                next(a for a in window.screen.areas if a.type=='PROPERTIES').type='OUTLINER'
                bpy.ops.ruster.new('EXEC_DEFAULT')
            elif stage==10:
                assert window.scene.ruster.mode=='PREFAB' and not list(window.scene.objects)
                assert not any(a.type=='PROPERTIES' or a.ui_type=='TIMELINE' for a in window.screen.areas)
            else:
                import ruster
                ruster.unregister()
                temporary.cleanup()
                print('RUSTER_GUI_NATIVE_SPLASH_START_SCENE_TABS_OK', flush=True)
                bpy.ops.wm.quit_blender()
                return None
            state['stage'] += 1
            for area in window.screen.areas:
                area.tag_redraw()
        return .6
    except Exception:
        traceback.print_exc()
        os._exit(1)


bpy.app.timers.register(step, first_interval=2., persistent=True)
