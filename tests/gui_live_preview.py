"""Draw launch, inject, and EAC-blocked states with synthetic process data only."""
import os
from pathlib import Path
import sys
import tempfile
import time
import traceback

ROOT = Path(__file__).resolve().parents[1];sys.path.insert(0, str(ROOT))
os.environ['RUSTER_PREVIEW_TEST_NO_DISCOVERY'] = '1'
import bpy
import ruster
from ruster import app, live_preview
from ruster.core.preview_client import ClientProbe

temporary = tempfile.TemporaryDirectory(prefix='ruster-preview-ui-')
root = Path(temporary.name);os.environ['RUSTER_USER_DIR'] = str(root/'user')
app.startup = lambda: None
live_preview.installation = lambda: root
state = {'phase': 0, 'draws': set(), 'started': time.monotonic()}


class FakeJob:
    active = True;status = 'RUNNING';port = 28015;directory = root
    def info(self):return {'status': 'RUNNING', 'message': 'Local server ready at 127.0.0.1:28015'}
    def log_tail(self, count):return ['Local preview bridge ready', 'Server scene revision 8 (24 placements)']
    def update(self, rows):pass
    def close(self):pass


class RUSTER_PT_preview_draw_check(bpy.types.Panel):
    bl_label = 'Live Preview'
    bl_space_type = 'VIEW_3D';bl_region_type = 'UI';bl_category = 'Preview Test';bl_order = -100
    def draw(self, context):
        try:
            live_preview.RUSTER_PT_live_preview.draw(self, context)
            state['draws'].add(state['phase'])
        except Exception:traceback.print_exc();os._exit(1)


ruster.register();bpy.utils.register_class(RUSTER_PT_preview_draw_check)


def tick():
    try:
        if time.monotonic()-state['started'] > 30:raise AssertionError('Preview draw check timed out')
        window = bpy.context.window_manager.windows[0]
        area = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
        area.spaces.active.show_region_ui = True
        region = next((r for r in area.regions if r.type == 'UI'), None)
        if region:
            try:region.active_panel_category = 'Preview Test'
            except (AttributeError, TypeError):pass
        if not state.get('configured'):
            window.event_simulate(type='ESC', value='PRESS')
            window.event_simulate(type='ESC', value='RELEASE')
            state['configured'] = True
            area.tag_redraw();return .3
        if state['phase'] not in state['draws']:
            area.tag_redraw();return .2
        if capture := os.environ.get('RUSTER_PREVIEW_CAPTURE'):
            target = Path(capture);target.mkdir(parents=True, exist_ok=True)
            with bpy.context.temp_override(window=window):bpy.ops.screen.screenshot(filepath=str(target/f"preview-{state['phase']}.png"))
        phase = state['phase']+1;state['phase'] = phase
        if phase == 1:
            live_preview._job = FakeJob()
            live_preview._clients = [ClientProbe(pid=1, created=1, executable=str(root/'RustClient.exe'),
                command_line='RustClient.exe', parent_name='explorer.exe', modules=['GameAssembly.dll', 'UnityPlayer.dll'])]
            live_preview._probe_message = 'Process checks passed; EAC will be checked again on Inject'
        elif phase == 2:
            live_preview._clients[0].eac_services = ['EasyAntiCheat_EOS']
            live_preview._probe_message = 'EAC is active: EasyAntiCheat_EOS'
        else:
            assert state['draws'] >= {0, 1, 2}
            live_preview._job = None
            bpy.utils.unregister_class(RUSTER_PT_preview_draw_check);ruster.unregister()
            print('RUSTER_LIVE_PREVIEW_DRAW_STATES_OK', flush=True)
            bpy.ops.wm.quit_blender();return None
        area.tag_redraw();return .5
    except Exception:traceback.print_exc();os._exit(1)


bpy.app.timers.register(tick, first_interval=1.)
