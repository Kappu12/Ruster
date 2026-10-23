"""Disposable native welcome QA; run with --enable-event-simulate, never a live editor.

Optional RUSTER_WELCOME_SCREENSHOTS points at a directory for the four UI states.
RUSTER_BRANDING_ONLY=1 verifies native identity and exits before click simulation.
Only synthetic empty objects are created; Steam detection and asset jobs are disabled.
"""
import os
import json
from pathlib import Path
import sys
import tempfile
import traceback

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if '--' in sys.argv and sys.argv[sys.argv.index('--')+1:]:
    sys.path.insert(0, sys.argv[sys.argv.index('--')+1])
import ruster
from ruster import app
from ruster.core import steam

temporary = tempfile.TemporaryDirectory(prefix='ruster-welcome-')
os.environ['RUSTER_USER_DIR'] = str(Path(temporary.name) / 'user')
steam.resolve_install = lambda *_args: None
new_invocations = []
original_new_invoke = app.RUSTER_OT_new.invoke
def new_invoke(self, context, event):
    new_invocations.append(len(context.scene.objects))
    return original_new_invoke(self, context, event)
app.RUSTER_OT_new.invoke = new_invoke
if scale:=os.environ.get('RUSTER_WELCOME_UI_SCALE'):
    bpy.context.preferences.view.ui_scale=float(scale)
ruster.register()
stage = 0
mouse_x = mouse_y = 0


def verify_branding():
    """Check shared previews everywhere, plus Windows-native identity on Windows."""
    from types import SimpleNamespace
    from ruster import branding, __version__
    assert bpy.app.version[:2] == (5, 2), 'Run welcome checks against the pinned Blender 5.2 runtime'
    previews = {name: branding._previews[name].icon_id
                for name in ('black', 'white', 'welcome-black', 'welcome-white')}
    assert all(previews.values()) and len(set(previews.values())) == 4
    variants = {}
    for theme, shade, color in (('light', 1., 'black'), ('dark', 0., 'white')):
        fake_context = SimpleNamespace(preferences=SimpleNamespace(themes=[
            SimpleNamespace(user_interface=SimpleNamespace(wcol_menu_back=SimpleNamespace(inner=[shade]*4)))]))
        variants[theme] = {'icon':branding.icon_id(fake_context),
                           'welcome':branding.icon_id(fake_context, welcome=True)}
        assert variants[theme]['icon'] == previews[color]
        assert variants[theme]['welcome'] == previews['welcome-' + color]
    evidence={'pid':os.getpid(),'version':__version__,'platform':sys.platform,
              'previews':previews,'theme_variants':variants,'windows':[]}
    print('RUSTER_BRANDING_PREVIEWS_OK '+json.dumps(evidence),flush=True)
    if sys.platform != 'win32':
        # HICON, WM_GETICON and taskbar AppID are Windows APIs. Linux still
        # exercises the same branded native popup, theme variants and clicks.
        evidence['native_identity_skipped']='Windows-native handles are not available on this platform'
        if destination := os.environ.get('RUSTER_BRANDING_EVIDENCE'):
            Path(destination).write_text(json.dumps(evidence,indent=2),encoding='utf8')
        return
    import ctypes
    from ctypes import wintypes as w
    branding.refresh_windows()
    assert len(branding._handles) == 2 and all(branding._handles)
    user = ctypes.WinDLL('user32', use_last_error=True)
    user.IsWindow.argtypes=[w.HWND];user.IsWindow.restype=w.BOOL
    user.GetWindowThreadProcessId.argtypes=[w.HWND,ctypes.POINTER(w.DWORD)]
    user.GetWindowTextW.argtypes=[w.HWND,w.LPWSTR,ctypes.c_int]
    user.SendMessageW.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM];user.SendMessageW.restype=w.LPARAM
    windows=[]
    for hwnd in branding._windows:
        if not user.IsWindow(hwnd):continue
        process=w.DWORD();user.GetWindowThreadProcessId(hwnd,ctypes.byref(process))
        assert process.value == os.getpid(), 'Branding tracked a different process window'
        title=ctypes.create_unicode_buffer(512);user.GetWindowTextW(hwnd,title,len(title))
        small=user.SendMessageW(hwnd,0x7f,0,0);big=user.SendMessageW(hwnd,0x7f,1,0)
        assert [small,big] == list(branding._handles), 'Native WM_GETICON did not return the Ruster HICON handles'
        assert 'Ruster' in title.value and __version__ in title.value
        windows.append({'hwnd':int(hwnd),'title':title.value,'small_icon':int(small),'big_icon':int(big)})
    assert windows, 'No native Ruster window was verified'
    evidence['windows']=windows
    if destination := os.environ.get('RUSTER_BRANDING_EVIDENCE'):
        Path(destination).write_text(json.dumps(evidence,indent=2),encoding='utf8')
    print('RUSTER_NATIVE_BRANDING_OK '+json.dumps(evidence),flush=True)


def screenshot(name):
    if directory := os.environ.get('RUSTER_WELCOME_SCREENSHOTS'):
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        bpy.ops.screen.screenshot(filepath=str(path / (name + '.png')))


def click(window, x, y):
    global mouse_x, mouse_y
    mouse_x, mouse_y = int(x), int(y)
    window.event_simulate(type='MOUSEMOVE', value='NOTHING', x=mouse_x, y=mouse_y)
    window.event_simulate(type='LEFTMOUSE', value='PRESS', x=mouse_x, y=mouse_y)
    window.event_simulate(type='LEFTMOUSE', value='RELEASE', x=mouse_x, y=mouse_y)


def step():
    global stage, mouse_x, mouse_y
    try:
        window = bpy.context.window_manager.windows[0]
        with bpy.context.temp_override(window=window):
            if stage == 0:
                # The popup must not follow a pointer parked in a corner.
                mouse_x, mouse_y = window.width-40, window.height-40
                window.event_simulate(type='MOUSEMOVE', value='NOTHING',
                    x=mouse_x, y=mouse_y)
            elif stage == 1:
                app.startup()
            elif stage == 2:
                assert bpy.context.scene.ruster.mode == 'PREFAB'
                assert not bpy.context.scene.objects, 'Startup did not create an empty composition'
                verify_branding()
                if os.environ.get('RUSTER_BRANDING_ONLY'):
                    bpy.ops.wm.quit_blender()
                    return None
                screenshot('welcome')
                from ruster.core import settings
                mouse_x,mouse_y=app.welcome_popup_position(window,bpy.context.preferences.system.ui_scale,settings.load())
                bpy.context.scene.ruster.title = 'Empty composition stays open'
                click(window, mouse_x-150*bpy.context.preferences.system.ui_scale, mouse_y)
            elif stage == 3:
                assert new_invocations == [0], 'Empty New Prefab button was not invoked'
                assert not bpy.context.scene.objects
                assert bpy.context.scene.ruster.title == 'Empty composition stays open'
                screenshot('empty-dismissed')
                obj = bpy.data.objects.new('Disposable welcome test', None)
                bpy.context.scene.collection.objects.link(obj)
                window.cursor_warp(40,40)
                bpy.ops.ruster.welcome('INVOKE_DEFAULT')
            elif stage == 4:
                screenshot('reopened-welcome')
                from ruster.core import settings
                mouse_x,mouse_y=app.welcome_popup_position(window,bpy.context.preferences.system.ui_scale,settings.load())
                click(window, mouse_x-150*bpy.context.preferences.system.ui_scale, mouse_y)
            elif stage == 5:
                assert new_invocations == [0, 1], 'New Prefab button was not invoked'
                assert len(bpy.context.scene.objects) == 1, 'Confirmation did not protect the current composition'
                screenshot('new-confirm')
                # Native confirmation placement differs between Win32 and X11.
                # Accept its focused default button through the real event loop.
                window.event_simulate(type='RET', value='PRESS')
                window.event_simulate(type='RET', value='RELEASE')
            elif stage == 6:
                assert not bpy.context.scene.objects, 'Confirmed New Prefab did not clear the composition'
                screenshot('new-confirmed')
                # Also cover the taller five-recents-plus-recovery layout.
                from ruster.core import settings
                recent=[]
                for index in range(5):
                    path=Path(temporary.name)/f'Example project {index}.ruster'
                    path.touch();recent.append(str(path))
                recovery=Path(temporary.name)/'Recovery.ruster';recovery.touch()
                settings.save({**settings.load(),'recent_projects':recent,'last_recovery':str(recovery)})
                window.cursor_warp(40,window.height-40)
                bpy.ops.ruster.welcome('INVOKE_DEFAULT')
            elif stage == 7:
                screenshot('welcome-with-recents')
                from ruster.core import settings
                mouse_x,mouse_y=app.welcome_popup_position(window,bpy.context.preferences.system.ui_scale,settings.load())
                click(window,mouse_x-150*bpy.context.preferences.system.ui_scale,mouse_y)
            else:
                assert new_invocations==[0,1,0], 'Taller centered welcome did not keep New Prefab functional'
                print('RUSTER_PREFAB_WELCOME_OK', flush=True)
                bpy.ops.wm.quit_blender()
                return None
        stage += 1
        return 1.
    except Exception:
        traceback.print_exc()
        os._exit(1)


bpy.app.timers.register(step, first_interval=1.)
