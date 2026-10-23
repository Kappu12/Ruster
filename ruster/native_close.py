"""Route the Windows titlebar close/Alt+F4 through the Ruster save workflow.

Window callbacks only queue a request. Blender UI operators run on the regular
main-thread timer, outside the native message callback. Other windows retain
their normal close behavior, including Preferences and additional main windows.
"""
import sys

_api = None
_callback = None
_hooks = set()
_pending = None
_active = False
SUBCLASS_ID = 0x52555354


def hook_window(hwnd):
    global _api, _callback
    if not _active or sys.platform != 'win32' or hwnd in _hooks:return
    if _api is None:
        import ctypes
        from ctypes import wintypes as w
        user = ctypes.WinDLL('user32', use_last_error=True)
        common = ctypes.WinDLL('comctl32', use_last_error=True)
        proc = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, w.HWND, w.UINT, w.WPARAM,
                                 w.LPARAM, ctypes.c_size_t, ctypes.c_size_t)
        common.SetWindowSubclass.argtypes = [w.HWND, proc, ctypes.c_size_t, ctypes.c_size_t]
        common.SetWindowSubclass.restype = w.BOOL
        common.RemoveWindowSubclass.argtypes = [w.HWND, proc, ctypes.c_size_t]
        common.RemoveWindowSubclass.restype = w.BOOL
        common.DefSubclassProc.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
        common.DefSubclassProc.restype = ctypes.c_ssize_t
        user.GetWindow.argtypes = [w.HWND, w.UINT];user.GetWindow.restype = w.HWND
        user.IsWindow.argtypes = [w.HWND];user.IsWindow.restype = w.BOOL

        @proc
        def dispatch(handle, message, wparam, lparam, _id, _data):
            global _pending
            if message == 0x0010 and not user.GetWindow(handle, 4):  # WM_CLOSE, GW_OWNER
                main = [h for h in _hooks if user.IsWindow(h) and not user.GetWindow(h, 4)]
                if len(main) == 1:
                    _pending = handle
                    return 0
            elif message == 0x0082:  # WM_NCDESTROY: remove before native destruction.
                common.RemoveWindowSubclass(handle, _callback, SUBCLASS_ID)
                _hooks.discard(handle)
            return common.DefSubclassProc(handle, message, wparam, lparam)

        _api = user, common
        _callback = dispatch  # Keep the ctypes callback alive until hooks are removed.
    if not _api[1].SetWindowSubclass(hwnd, _callback, SUBCLASS_ID, 0):
        raise OSError('Could not install the Ruster window close handler')
    _hooks.add(hwnd)


def poll_close():
    global _pending
    if _pending is not None:
        import bpy
        if bpy.context.window_manager.is_interface_locked:return .1
        windows = list(bpy.context.window_manager.windows)
        if not windows:return .1
        _pending = None
        with bpy.context.temp_override(window=windows[0]):
            bpy.ops.ruster.quit('INVOKE_DEFAULT')
    return .1


def register():
    global _active
    import bpy
    _active = True
    if sys.platform == 'win32' and not bpy.app.background:
        bpy.app.timers.register(poll_close, first_interval=.1, persistent=True)


def unregister():
    global _pending, _active
    import bpy
    _active = False
    if bpy.app.timers.is_registered(poll_close):bpy.app.timers.unregister(poll_close)
    if _api is not None:
        user, common = _api
        for hwnd in tuple(_hooks):
            if user.IsWindow(hwnd) and not common.RemoveWindowSubclass(hwnd, _callback, SUBCLASS_ID):
                raise OSError('Could not remove the Ruster window close handler')
            _hooks.discard(hwnd)
    _pending = None
