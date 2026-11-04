"""Exercise bootstrap, prefab startup, native menus and Preferences on a desktop."""
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
# The harness's distribution argument is not a project to open in the app.
original_argv=sys.argv[:]
try:
    if '--' in sys.argv:sys.argv=sys.argv[:sys.argv.index('--')]
    runpy.run_path(str(distribution / 'bootstrap.py'))
finally:sys.argv=original_argv
from ruster import app, ui, studio, preferences
from tests.fixtures import sample_world

assert bpy.app.version[:2] == (5, 2), 'Run startup checks against the pinned Blender 5.2 runtime'
# This is metadata/UI coverage. Importing the fixture must not launch asset work.
app.request_missing_visuals = lambda _objects: None
state = {'stage': 0, 'welcome': False, 'start': False, 'scene': False,
         'preferences': set()}


def checked_draw(original, key):
    def draw(self, context):
        try:
            original(self, context)
            state[key] = True
        except Exception:
            traceback.print_exc()
            os._exit(1)
    return draw


ui.RUSTER_PT_welcome.draw = checked_draw(ui.RUSTER_PT_welcome.draw, 'welcome')
ui.RUSTER_PT_start.draw = checked_draw(ui.RUSTER_PT_start.draw, 'start')
bpy.types.SCENE_PT_scene.draw = checked_draw(bpy.types.SCENE_PT_scene.draw, 'scene')
studio.RUSTER_MT_add.draw=checked_draw(studio.RUSTER_MT_add.draw,'add')
bpy.types.VIEW3D_PT_tools_active.draw=checked_draw(bpy.types.VIEW3D_PT_tools_active.draw,'toolbar')
for cls in (preferences.RUSTER_PT_preferences_assets, preferences.RUSTER_PT_preferences_mcp):
    def checked_preferences(original, section):
        def draw(self, context, layout):
            try:
                original(self, context, layout)
                state['preferences'].add(section)
            except Exception:
                traceback.print_exc()
                os._exit(1)
        return draw
    cls.draw_centered = checked_preferences(cls.draw_centered, cls.section)


def prefab_workspace(window):
    assert window.scene.ruster.mode == 'PREFAB'
    assert not ui.is_map(bpy.context)
    assert not window.scene.ruster.source_map and window.scene.ruster.terrain_state is None
    assert not any(obj.get('ruster_kind') in {'TERRAIN', 'WATER', 'PATH', 'PATH_PREVIEW'}
                   for obj in window.scene.objects)


def step():
    try:
        window = bpy.context.window_manager.windows[0]
        with bpy.context.temp_override(window=window):
            stage = state['stage']
            print('Prefab startup regression stage', stage, flush=True)
            if stage == 0:
                assert state['welcome'], 'Native Ruster welcome panel did not draw'
                prefab_workspace(window)
                assert not window.scene.objects, 'Startup did not create an empty prefab composition'
                window.event_simulate(type='ESC', value='PRESS')
            elif stage == 1:
                if any(a.ui_type=='TIMELINE' for a in window.screen.areas):
                    state['workspace_waits']=state.get('workspace_waits',0)+1
                    assert state['workspace_waits']<30,'Workspace cleanup did not finish'
                    return .6  # Material Preview can delay the first area-close tick.
                assert state['start'], 'Persistent start controls did not draw'
                area = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
                region = next(r for r in area.regions if r.type == 'UI')
                assert area.spaces.active.show_region_ui and region.active_panel_category == 'Ruster'
                prefab_workspace(window)
                assert not window.scene.objects
                assert area.spaces.active.show_region_toolbar
                assert not area.spaces.active.overlay.show_relationship_lines
                assert any(a.type=='PROPERTIES' for a in window.screen.areas), 'Dedicated live-preview editor is missing'
                assert not any(a.ui_type=='TIMELINE' for a in window.screen.areas)
                area.spaces.active.show_region_toolbar=True
                with bpy.context.temp_override(area=area):bpy.ops.wm.call_menu(name='VIEW3D_MT_add')
            elif stage == 2:
                assert state.get('add'),'Blender Add menu did not route to Rust prefab categories'
                assert state.get('toolbar'),'The native Blender toolbar did not draw'
                window.event_simulate(type='ESC',value='PRESS')
                path = Path(temporary.name) / 'test.map'
                path.write_bytes(sample_world().write())
                app.open_path(path)
            elif stage==3:
                prefab_workspace(window)
                assert len(app.scene.prefab_roots()) == 2
                assert len(window.scene.objects) == 2, '.map opening created objects other than prefab placements'
                if bpy.app.timers.is_registered(ui.close_map_timeline):bpy.app.timers.unregister(ui.close_map_timeline)
                props=next(a for a in window.screen.areas if a.type=='PROPERTIES')
                props.spaces.active.context='SCENE'
            elif 4 <= stage <= 8:
                # Only Ruster's preview belongs in Properties; native Scene,
                # World and Render panels must remain hidden in every context.
                props=next(a for a in window.screen.areas if a.type=='PROPERTIES')
                props.spaces.active.context=('SCENE','WORLD','VIEW_LAYER','RENDER','OUTPUT')[stage-4]
            elif stage==9:
                props=next(a for a in window.screen.areas if a.type=='PROPERTIES')
                with bpy.context.temp_override(area=props):bpy.ops.screen.area_close()
                bpy.ops.ruster.new('EXEC_DEFAULT')
            elif stage==10:
                # New Prefab closes and splits editors over several UI ticks.
                # Under software rendering, one test interval can run before
                # the layout timer has converted the split into Properties.
                if (not any(a.type=='PROPERTIES' for a in window.screen.areas)
                        or any(a.ui_type=='TIMELINE' for a in window.screen.areas)):
                    state['new_workspace_waits']=state.get('new_workspace_waits',0)+1
                    assert state['new_workspace_waits']<30, 'New Prefab layout did not finish rebuilding'
                    return .2
                prefab_workspace(window)
                assert not window.scene.objects
                assert any(a.type=='PROPERTIES' for a in window.screen.areas), 'New Prefab did not restore the preview editor'
                assert not any(a.ui_type=='TIMELINE' for a in window.screen.areas)
                assert not state['scene'], 'Unrelated native Scene panels leaked into the prefab editor'
                labels = {item[0]:item[1] for item in preferences.SECTIONS if item}
                assert labels['RUSTER_ASSETS'] == 'Assets' and labels['RUSTER_MCP'] == 'MCP'
                bpy.ops.ruster.preferences('EXEC_DEFAULT', section='RUSTER_ASSETS')
            elif stage==11:
                assert 'RUSTER_ASSETS' in state['preferences'], 'Assets preferences did not draw'
                bpy.ops.ruster.preferences('EXEC_DEFAULT', section='RUSTER_MCP')
            elif stage==12:
                assert 'RUSTER_MCP' in state['preferences'], 'MCP preferences did not draw'
                bpy.ops.ruster.preferences('EXEC_DEFAULT', section='INTERFACE')
                assert bpy.context.preferences.active_section == 'INTERFACE'
            elif stage==13:
                bpy.ops.ruster.preferences('EXEC_DEFAULT', section='THEMES')
                assert bpy.context.preferences.active_section == 'THEMES'
            elif stage==14:
                preference_windows = [candidate for candidate in bpy.context.window_manager.windows
                    if candidate != window and any(area.type == 'PREFERENCES' for area in candidate.screen.areas)]
                assert preference_windows, 'Preferences did not open a native window'
                for candidate in preference_windows:
                    with bpy.context.temp_override(window=candidate):bpy.ops.wm.window_close()
            else:
                assert len(bpy.context.window_manager.windows) == 1
                assert app._job is None and not app._visual_queue, 'Startup UI test launched asset work'
                import ruster
                ruster.unregister()
                temporary.cleanup()
                print('RUSTER_GUI_PREFAB_STARTUP_PREFERENCES_OK', flush=True)
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
