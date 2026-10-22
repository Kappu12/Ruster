"""Ruster splash and native Windows identity; semantic tool icons stay native."""
import os
from pathlib import Path
import sys

ASSETS=Path(__file__).with_name('branding')
_previews=None
_handles=[]
_windows={}


def configure():
    path=ASSETS/'splash.png'
    if path.is_file():os.environ['BLENDER_CUSTOM_SPLASH']=str(path)
    if sys.platform=='win32':
        import ctypes
        shell=ctypes.WinDLL('shell32')
        shell.SetCurrentProcessExplicitAppUserModelID.argtypes=[ctypes.c_wchar_p]
        shell.SetCurrentProcessExplicitAppUserModelID.restype=ctypes.c_long
        shell.SetCurrentProcessExplicitAppUserModelID('Ruster.PrefabStudio')


def icon_id(context=None,*,welcome=False):
    if _previews is None:return 0
    import bpy
    context=context or bpy.context
    try:light=sum(context.preferences.themes[0].user_interface.wcol_menu_back.inner[:3])/3>.5
    except (AttributeError,IndexError):light=False
    return _previews[('welcome-' if welcome else '')+('black' if light else 'white')].icon_id


def label(layout,text='',context=None):
    value=icon_id(context)
    if value:layout.label(text=text,icon_value=value)
    else:layout.label(text=text,icon='WORLD')


def refresh_windows():
    """Set icons on this process's own native windows, including Preferences."""
    if sys.platform!='win32':return None
    import bpy,ctypes
    from ctypes import wintypes as w
    from . import __version__
    user=ctypes.WinDLL('user32',use_last_error=True)
    user.LoadImageW.argtypes=[w.HINSTANCE,w.LPCWSTR,w.UINT,ctypes.c_int,ctypes.c_int,w.UINT]
    user.LoadImageW.restype=w.HANDLE
    user.SendMessageW.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM];user.SendMessageW.restype=w.LPARAM
    user.GetWindowThreadProcessId.argtypes=[w.HWND,ctypes.POINTER(w.DWORD)]
    user.GetClassNameW.argtypes=[w.HWND,w.LPWSTR,ctypes.c_int]
    user.GetWindowTextW.argtypes=[w.HWND,w.LPWSTR,ctypes.c_int]
    user.SetWindowTextW.argtypes=[w.HWND,w.LPCWSTR]
    if not _handles:
        loaded=[]
        for size in (32,64):
            handle=user.LoadImageW(None,str(ASSETS/'ruster.ico'),1,size,size,0x10)
            if not handle:
                user.DestroyIcon.argtypes=[w.HICON]
                for previous in loaded:user.DestroyIcon(previous)
                return 5.
            loaded.append(handle)
        _handles.extend(loaded)
    callback_type=ctypes.WINFUNCTYPE(w.BOOL,w.HWND,w.LPARAM)
    @callback_type
    def update(hwnd,_unused):
        process=w.DWORD();user.GetWindowThreadProcessId(hwnd,ctypes.byref(process))
        if process.value!=os.getpid():return True
        kind=ctypes.create_unicode_buffer(128);user.GetClassNameW(hwnd,kind,len(kind))
        if kind.value!='GHOST_WindowClass':return True
        if hwnd not in _windows:
            _windows[hwnd]=(user.SendMessageW(hwnd,0x80,0,_handles[0]),user.SendMessageW(hwnd,0x80,1,_handles[1]))
        caption=ctypes.create_unicode_buffer(512);user.GetWindowTextW(hwnd,caption,len(caption))
        title=('Preferences' if 'Preferences' in caption.value else getattr(getattr(bpy.context.scene,'ruster',None),'title','Prefab Studio'))
        wanted=f'{title} — Ruster {__version__}'
        if caption.value!=wanted:user.SetWindowTextW(hwnd,wanted)
        return True
    user.EnumWindows.argtypes=[callback_type,w.LPARAM];user.EnumWindows(update,0)
    return 5.


def register():
    global _previews
    import bpy,bpy.utils.previews
    configure()
    if _previews is None:
        _previews=bpy.utils.previews.new()
        for name in ('black','white'):
            _previews.load(name,str(ASSETS/f'icon-{name}.png'),'IMAGE')
            _previews.load('welcome-'+name,str(ASSETS/f'welcome-{name}.png'),'IMAGE')
    if not bpy.app.background and not bpy.app.timers.is_registered(refresh_windows):
        bpy.app.timers.register(refresh_windows,first_interval=.2,persistent=True)


def unregister():
    global _previews
    import bpy,bpy.utils.previews
    if bpy.app.timers.is_registered(refresh_windows):bpy.app.timers.unregister(refresh_windows)
    if _previews is not None:bpy.utils.previews.remove(_previews);_previews=None
    if sys.platform=='win32':
        import ctypes
        from ctypes import wintypes as w
        user=ctypes.WinDLL('user32')
        user.SendMessageW.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM]
        for hwnd,(small,big) in _windows.items():
            user.SendMessageW(hwnd,0x80,0,small);user.SendMessageW(hwnd,0x80,1,big)
        user.DestroyIcon.argtypes=[w.HICON]
        for handle in _handles:user.DestroyIcon(handle)
    _windows.clear();_handles.clear()
