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
(game / 'RustClient.exe').touch()
settings.save({'rust_install': str(game)})
runpy.run_path(str(distribution / 'bootstrap.py'))
from ruster import app, ui
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
                props = next(a for a in window.screen.areas if a.type == 'PROPERTIES')
                props.spaces.active.context = 'SCENE'
            elif stage == 2:
                assert state['scene'], 'Scene properties did not draw'
                path = Path(temporary.name) / 'test.map'
                path.write_bytes(sample_world().write())
                app.open_path(path)
            elif 3 <= stage <= 12:
                # Click through every native Properties context, including Scene,
                # before and after returning from map mode. This catches stale RNA
                # panel pointers that headless registration tests cannot exercise.
                if stage == 8:
                    bpy.ops.ruster.new('EXEC_DEFAULT')
                    state['stage'] += 1
                    return .6  # The previous window/screen references are invalid.
                props = next(a for a in window.screen.areas if a.type == 'PROPERTIES')
                props.spaces.active.context = ('SCENE', 'WORLD', 'VIEW_LAYER', 'RENDER', 'OUTPUT')[(stage - 3) % 5]
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
