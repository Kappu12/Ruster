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
from ruster import app, live_preview, ui
from ruster.core.preview_client import ClientProbe

temporary = tempfile.TemporaryDirectory(prefix='ruster-preview-ui-')
root = Path(temporary.name);os.environ['RUSTER_USER_DIR'] = str(root/'user')
app.startup = lambda: None
live_preview.installation = lambda: root
state = {'phase': 0, 'draws': set(), 'started': time.monotonic()}


class FakeJob:
    active = True;status = 'RUNNING';port = 28015;directory = root
    def info(self):return {'status': self.status, 'message': getattr(self, 'message', 'Local server ready at 127.0.0.1:28015'),
        'progress': getattr(self, 'progress', None)}
    def log_tail(self, count):return ['Local preview bridge ready', 'Server scene revision 8 (24 placements)']
    def update(self, rows):pass
    def close(self):pass


original_draw = live_preview.RUSTER_PT_live_preview.draw
def checked_draw(self, context):
    try:
        original_draw(self, context);state['draws'].add(state['phase'])
    except Exception:traceback.print_exc();os._exit(1)
live_preview.RUSTER_PT_live_preview.draw = checked_draw


ruster.register();ui.start_workspace()
if os.environ.get('RUSTER_PREVIEW_LIGHT_THEME'):
    theme=next(Path(path)/'Blender_Light.xml' for path in bpy.utils.preset_paths('interface_theme') if (Path(path)/'Blender_Light.xml').exists())
    bpy.ops.script.execute_preset(filepath=str(theme),menu_idname='USERPREF_MT_interface_theme_presets')


def tick():
    try:
        if time.monotonic()-state['started'] > 30:raise AssertionError('Preview draw check timed out')
        window = bpy.context.window_manager.windows[0]
        area = next(a for a in window.screen.areas if a.type == 'PROPERTIES')
        outliner = next(a for a in window.screen.areas if a.type == 'OUTLINER')
        assert area.y < outliner.y and area.x == outliner.x, 'Live Preview is not below Placements'
        assert next(r for r in area.regions if r.type=='NAVIGATION_BAR').width<=1
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
            live_preview._probe_message = 'EAC checks passed; rechecked on Inject'
            live_preview._client_allowed = True
            live_preview.refresh_status()
        elif phase == 2:
            live_preview._clients[0].eac_services = ['EasyAntiCheat_EOS']
            live_preview._probe_message = 'EAC is active: EasyAntiCheat_EOS'
            live_preview._client_allowed = False
        elif phase == 3:
            live_preview._module_loaded = True
            live_preview._probe_message = 'Preview module is loaded'
            live_preview._client_status = 'READY · Live scene revision 8 applied (24 placements).'
        elif phase in (4, 5):
            live_preview._module_loaded = False;live_preview._clients = [];live_preview._client_status = ''
            live_preview._probe_message = 'Rust is not running'
            live_preview._job.status = 'DOWNLOADING'
            live_preview._job.message = 'Updating SteamCMD · 50%' if phase == 4 else 'Downloading Rust server · 50%'
            live_preview._job.progress = .075 if phase == 4 else .46
            live_preview.refresh_status()
        else:
            assert state['draws'] >= {0, 1, 2, 3, 4, 5}
            live_preview._job = None
            ruster.unregister()
            print('RUSTER_LIVE_PREVIEW_DRAW_STATES_OK', flush=True)
            bpy.ops.wm.quit_blender();return None
        area.tag_redraw();return .5
    except Exception:traceback.print_exc();os._exit(1)


bpy.app.timers.register(tick, first_interval=1.)
