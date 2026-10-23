"""Exercise Windows WM_CLOSE and the real project save/cancel popup."""
import os, sys, tempfile, traceback
from pathlib import Path
import bpy
ROOT = Path(__file__).resolve().parents[1];sys.path.insert(0, str(ROOT))
if '--' in sys.argv:sys.path.insert(0, sys.argv[sys.argv.index('--')+1])
temporary = tempfile.TemporaryDirectory(prefix='ruster-close-ui-')
os.environ['RUSTER_USER_DIR'] = temporary.name
import ruster
from ruster import app, scene, studio, quitting, native_close, branding
from ruster.core import wire
ruster.register()
state = {'phase':0};decisions = []
native_quit = quitting.schedule_quit
def pretend_quit():
    quitting._dialog_open = False
    decisions.append('quit')
quitting.schedule_quit = pretend_quit


def close():
    if sys.platform == 'win32':
        import ctypes
        from ctypes import wintypes as w
        branding.refresh_windows()
        user = ctypes.WinDLL('user32')
        user.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
        main = [h for h in native_close._hooks if not native_close._api[0].GetWindow(h, 4)]
        assert len(main) == 1, 'Expected one hooked main window'
        assert user.PostMessageW(main[0], 0x0010, 0, 0)
    else:
        bpy.ops.ruster.quit('INVOKE_DEFAULT')


def step():
    try:
        window = bpy.context.window_manager.windows[0]
        phase = state['phase']
        area = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
        region = next(r for r in area.regions if r.type == 'WINDOW')
        with bpy.context.temp_override(window=window, area=area, region=region):
            if phase == 0:
                studio.new_prefab()
                scene.root_object([wire.encode(2, 0, 42)], bpy.context.scene.collection)
                app.save_project(Path(temporary.name)/'Saved Project.ruster')
                close()
            elif phase == 1:
                assert decisions == ['quit'] and not quitting._dialog_open
                scene.prefab_roots()[0].location.x = 7
                close()
            elif phase == 2:
                assert quitting._dialog_open and decisions == ['quit']
                if directory := os.environ.get('RUSTER_CLOSE_SCREENSHOTS'):
                    Path(directory).mkdir(parents=True, exist_ok=True)
                    bpy.ops.screen.screenshot(filepath=str(Path(directory)/'ruster-close.png'))
                window.event_simulate(type='ESC', value='PRESS')
                window.event_simulate(type='ESC', value='RELEASE')
            elif phase == 3:
                assert not quitting._dialog_open and quitting.has_unsaved_changes()
                assert decisions == ['quit']
                # Ctrl+Q must use the same project-aware confirmation.
                window.event_simulate(type='Q', value='PRESS', ctrl=True)
                window.event_simulate(type='Q', value='RELEASE', ctrl=True)
            elif phase == 4:
                assert quitting._dialog_open
                window.event_simulate(type='RET', value='PRESS')
                window.event_simulate(type='RET', value='RELEASE')
            elif phase == 5:
                assert decisions == ['quit', 'quit'] and not quitting.has_unsaved_changes()
                studio.new_prefab()
                scene.root_object([wire.encode(2, 0, 43)], bpy.context.scene.collection)
                close()
            elif phase == 6:
                assert quitting._dialog_open
                window.event_simulate(type='RET', value='PRESS')
                window.event_simulate(type='RET', value='RELEASE')
            elif phase == 7:
                # Untitled Save opens the .ruster selector and does not quit.
                assert decisions == ['quit', 'quit']
                assert not bpy.context.scene.ruster.project_path
                areas = [a for w in bpy.context.window_manager.windows for a in w.screen.areas if a.type == 'FILE_BROWSER']
                assert areas, 'Saving an untitled project did not open a file selector'
                assert areas[0].spaces.active.params.filename.endswith('.ruster')
                browser_window = next(w for w in bpy.context.window_manager.windows if any(a.type == 'FILE_BROWSER' for a in w.screen.areas))
                browser_area = next(a for a in browser_window.screen.areas if a.type == 'FILE_BROWSER')
                with bpy.context.temp_override(window=browser_window, area=browser_area):
                    bpy.ops.file.cancel()
            elif phase == 8:
                assert decisions == ['quit', 'quit'] and quitting.has_unsaved_changes()
                if sys.platform == 'win32':
                    bpy.ops.screen.userpref_show('INVOKE_DEFAULT')
            elif phase == 9:
                if sys.platform == 'win32':
                    import ctypes
                    from ctypes import wintypes as w
                    branding.refresh_windows()
                    assert len(bpy.context.window_manager.windows) == 2
                    user = ctypes.WinDLL('user32')
                    user.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
                    owned = [h for h in native_close._hooks if native_close._api[0].GetWindow(h, 4)]
                    assert len(owned) == 1, 'Preferences must retain its native close behavior'
                    user.PostMessageW(owned[0], 0x0010, 0, 0)
            elif phase == 10:
                assert len(bpy.context.window_manager.windows) == 1
                assert decisions == ['quit', 'quit']
                quitting.schedule_quit = native_quit
                ruster.unregister()
                assert not native_close._hooks and not bpy.app.timers.is_registered(native_close.poll_close)
                ruster.register()
                if os.environ.get('RUSTER_CLOSE_REAL_EXIT') == 'discard':
                    close()
                else:
                    app.save_project(Path(temporary.name)/'Final.ruster')
                    print('RUSTER_GUI_PROJECT_CLOSE_SAVED_EXIT_OK', flush=True)
                    close()
                    return None
            elif phase == 11:
                assert quitting._dialog_open
                print('RUSTER_GUI_PROJECT_CLOSE_DISCARD_EXIT_OK', flush=True)
                bpy.ops.ruster.discard_and_quit()
                return None
        state['phase'] += 1
        return .5
    except Exception:
        traceback.print_exc();os._exit(1)


bpy.app.timers.register(step, first_interval=.5, persistent=True)
