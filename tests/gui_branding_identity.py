"""Disposable Windows taskbar identity QA. Never connect to an existing editor."""
import ctypes
from ctypes import wintypes as w
import json
import os
from pathlib import Path
import sys
import tempfile
import traceback

import bpy
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
if '--' in sys.argv and sys.argv[sys.argv.index('--')+1:]:
    sys.path.insert(0,str(Path(sys.argv[sys.argv.index('--')+1]).resolve()))
from ruster import branding,app,studio,__version__
import ruster

temporary=tempfile.TemporaryDirectory(prefix='ruster-window-identity-')
os.environ['RUSTER_USER_DIR']=str(Path(temporary.name)/'user')
asset_jobs=[]
def reject_job(*args,**kwargs):
    asset_jobs.append((args,kwargs));raise AssertionError('Identity QA must not launch asset jobs')
app.start_job=reject_job
ruster.register();studio.new_prefab()


def run():
    try:
        assert bpy.app.version[:2]==(5,2),bpy.app.version_string
        branding.refresh_windows()
        user=ctypes.WinDLL('user32',use_last_error=True)
        user.SendMessageW.argtypes=[w.HWND,w.UINT,w.WPARAM,w.LPARAM];user.SendMessageW.restype=w.LPARAM
        user.IsWindow.argtypes=[w.HWND];user.IsWindow.restype=w.BOOL
        user.GetWindowTextW.argtypes=[w.HWND,w.LPWSTR,ctypes.c_int]
        expected=branding.relaunch_properties();windows=[];originals={}
        app_root=Path(ruster.__file__).resolve().parent.parent
        launcher=app_root/'Ruster.exe'
        if launcher.is_file():
            import subprocess
            assert expected[2]==subprocess.list2cmdline([str(launcher)]),'Packaged relaunch command bypasses Ruster.exe'
        else:
            assert bpy.app.binary_path in expected[2],'Development relaunch command bypasses the current Blender engine'
        for hwnd,icons in branding._windows.items():
            if not user.IsWindow(hwnd):continue
            props=branding.window_properties(hwnd)
            assert props==expected,(props,expected)
            actual=[user.SendMessageW(hwnd,0x7f,index,0) for index in (0,1)]
            assert actual==branding._handles
            title=ctypes.create_unicode_buffer(512);user.GetWindowTextW(hwnd,title,len(title))
            assert 'Ruster' in title.value and __version__ in title.value
            old={pid:ctypes.wstring_at(value.pointer) if value.vt==31 and value.pointer else None
                 for pid,value in branding._window_properties[hwnd].items()}
            originals[hwnd]=(icons,old)
            windows.append({'hwnd':int(hwnd),'title':title.value,'icons':actual,'properties':props})
        assert windows and not asset_jobs
        branding.unregister()
        for hwnd,(icons,props) in originals.items():
            assert [user.SendMessageW(hwnd,0x7f,index,0) for index in (0,1)]==list(icons)
            assert branding.window_properties(hwnd)==props,'Unregister did not restore previous window properties'
        evidence={'pid':os.getpid(),'app_version':__version__,'engine_version':bpy.app.version_string,
            'engine_branch':bpy.app.build_branch.decode(),'engine_hash':bpy.app.build_hash.decode(),
            'engine_executable':bpy.app.binary_path,'app_root':str(app_root),'relaunch_uses_launcher':launcher.is_file(),'windows':windows,'originals_restored':True,'asset_jobs':len(asset_jobs)}
        if destination:=os.environ.get('RUSTER_IDENTITY_EVIDENCE'):
            Path(destination).write_text(json.dumps(evidence,indent=2),encoding='utf8')
        print('RUSTER_TASKBAR_IDENTITY_OK '+json.dumps(evidence),flush=True)
        ruster.unregister();bpy.ops.wm.quit_blender();return None
    except Exception:
        traceback.print_exc();os._exit(1)

bpy.app.timers.register(run,first_interval=2.)
