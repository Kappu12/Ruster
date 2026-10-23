"""Ruster splash and native Windows identity; semantic tool icons stay native."""
import os
from pathlib import Path
import sys

ASSETS=Path(__file__).with_name('branding')
_previews=None
_handles=[]
_windows={}
_window_properties={}
_property_types=None
APP_ID='Ruster.PrefabStudio'


def configure():
    path=ASSETS/'splash.png'
    if path.is_file():os.environ['BLENDER_CUSTOM_SPLASH']=str(path)
    if sys.platform=='win32':
        import ctypes
        shell=ctypes.WinDLL('shell32')
        shell.SetCurrentProcessExplicitAppUserModelID.argtypes=[ctypes.c_wchar_p]
        shell.SetCurrentProcessExplicitAppUserModelID.restype=ctypes.c_long
        shell.SetCurrentProcessExplicitAppUserModelID(APP_ID)


def relaunch_properties():
    """Taskbar identity points at the Ruster launcher, never a bare engine."""
    import subprocess
    root=ASSETS.parent.parent
    launcher=root/'Ruster.exe'
    if launcher.is_file():command=subprocess.list2cmdline([str(launcher)])
    else:
        # Development checkouts have no frozen launcher. Bootstrap the same
        # application with this Blender, without replaying its current file.
        import bpy
        command=subprocess.list2cmdline([bpy.app.binary_path,'--factory-startup','--disable-autoexec',
                                        '--python',str(root/'bootstrap.py')])
    return {2:command,3:str(ASSETS/'ruster.ico')+',0',4:'Ruster Prefab Studio',5:APP_ID}


def _property_store(hwnd):
    """Small ctypes IPropertyStore wrapper; no COM framework/runtime dependency."""
    global _property_types
    import ctypes
    from ctypes import wintypes as w
    import uuid
    if _property_types is None:
        class GUID(ctypes.Structure):
            _fields_=[('bytes',ctypes.c_ubyte*16)]
        class KEY(ctypes.Structure):
            _fields_=[('fmtid',GUID),('pid',w.DWORD)]
        class VALUE(ctypes.Union):
            _fields_=[('pointer',ctypes.c_void_p),('storage',ctypes.c_ubyte*16)]
        class VARIANT(ctypes.Structure):
            _anonymous_=('value',)
            _fields_=[('vt',ctypes.c_ushort),('reserved',ctypes.c_ushort*3),('value',VALUE)]
        _property_types=(GUID,KEY,VARIANT)
    GUID,KEY,VARIANT=_property_types
    def guid(value):return GUID((ctypes.c_ubyte*16).from_buffer_copy(uuid.UUID(value).bytes_le))
    fmtid=guid('9f4c2855-9f79-4b39-a8d0-e1d42de1d5f3')
    iid=guid('886d8eeb-8cf2-4446-8d02-cdba1dbdcf99')
    shell=ctypes.WinDLL('shell32');ole=ctypes.WinDLL('ole32')
    shell.SHGetPropertyStoreForWindow.argtypes=[w.HWND,ctypes.POINTER(GUID),ctypes.POINTER(ctypes.c_void_p)]
    shell.SHGetPropertyStoreForWindow.restype=ctypes.c_long
    ole.PropVariantClear.argtypes=[ctypes.POINTER(VARIANT)];ole.PropVariantClear.restype=ctypes.c_long
    pointer=ctypes.c_void_p()
    result=shell.SHGetPropertyStoreForWindow(hwnd,ctypes.byref(iid),ctypes.byref(pointer))
    if result<0:raise OSError(result,'Could not access native window identity')
    table=ctypes.cast(pointer,ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    release=ctypes.WINFUNCTYPE(w.ULONG,ctypes.c_void_p)(table[2])
    get=ctypes.WINFUNCTYPE(ctypes.c_long,ctypes.c_void_p,ctypes.POINTER(KEY),ctypes.POINTER(VARIANT))(table[5])
    set_=ctypes.WINFUNCTYPE(ctypes.c_long,ctypes.c_void_p,ctypes.POINTER(KEY),ctypes.POINTER(VARIANT))(table[6])
    class Store:
        def get(self,pid):
            value=VARIANT();result=get(pointer,ctypes.byref(KEY(fmtid,pid)),ctypes.byref(value))
            if result<0:raise OSError(result,'Could not read native window identity')
            return value
        def set(self,pid,value):
            result=set_(pointer,ctypes.byref(KEY(fmtid,pid)),ctypes.byref(value))
            if result<0:raise OSError(result,'Could not write native window identity')
        def string(self,pid,text):
            buffer=ctypes.create_unicode_buffer(text);value=VARIANT();value.vt=31
            value.pointer=ctypes.cast(buffer,ctypes.c_void_p);self.set(pid,value)
        def clear(self,value):ole.PropVariantClear(ctypes.byref(value))
        def close(self):release(pointer)
    return Store()


def window_properties(hwnd):
    """Read back the taskbar identity for focused native diagnostics."""
    import ctypes
    store=_property_store(hwnd)
    try:
        result={}
        for pid in (2,3,4,5):
            value=store.get(pid)
            try:result[pid]=ctypes.wstring_at(value.pointer) if value.vt==31 and value.pointer else None
            finally:store.clear(value)
        return result
    finally:store.close()


def _brand_window_properties(hwnd):
    if hwnd in _window_properties:return
    store=_property_store(hwnd);original={}
    try:
        wanted=relaunch_properties()
        for pid in wanted:original[pid]=store.get(pid)
        # Relaunch properties must precede AppID so Explorer groups/pins the
        # host window using the complete Ruster identity from its first use.
        for pid,value in wanted.items():store.string(pid,value)
        _window_properties[hwnd]=original
    except Exception:
        for pid,value in original.items():
            try:store.set(pid,value)
            finally:store.clear(value)
        raise
    finally:store.close()


def _restore_window_properties(hwnd,alive=True):
    import ctypes
    original=_window_properties.pop(hwnd,{})
    if not original:return
    store=None
    try:
        if alive:store=_property_store(hwnd)
        if store:
            for pid,value in original.items():store.set(pid,value)
    finally:
        ole=ctypes.WinDLL('ole32');variant_type=_property_types[2]
        ole.PropVariantClear.argtypes=[ctypes.POINTER(variant_type)]
        for value in original.values():ole.PropVariantClear(ctypes.byref(value))
        if store:store.close()


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
        from . import native_close
        native_close.hook_window(hwnd)
        _brand_window_properties(hwnd)
        if hwnd not in _windows:
            _windows[hwnd]=(user.SendMessageW(hwnd,0x80,0,_handles[0]),user.SendMessageW(hwnd,0x80,1,_handles[1]))
        caption=ctypes.create_unicode_buffer(512);user.GetWindowTextW(hwnd,caption,len(caption))
        title=('Preferences' if 'Preferences' in caption.value else getattr(getattr(bpy.context.scene,'ruster',None),'title','Prefab Studio'))
        from .quitting import save_status
        status='' if title=='Preferences' or not hasattr(bpy.context.scene,'ruster') else ' · '+save_status()
        wanted=f'{title}{status} — Ruster {__version__}'
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
        user.IsWindow.argtypes=[w.HWND];user.IsWindow.restype=w.BOOL
        for hwnd,(small,big) in _windows.items():
            alive=bool(user.IsWindow(hwnd))
            try:_restore_window_properties(hwnd,alive)
            finally:
                if alive:
                    user.SendMessageW(hwnd,0x80,0,small);user.SendMessageW(hwnd,0x80,1,big)
        user.DestroyIcon.argtypes=[w.HICON]
        for handle in _handles:user.DestroyIcon(handle)
    _windows.clear();_handles.clear()
