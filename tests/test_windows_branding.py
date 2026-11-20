"""Targeted PE identity test; copies one executable and never edits the runtime."""
import ctypes
from ctypes import wintypes as w
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import pytest

pytestmark=pytest.mark.skipif(sys.platform!='win32',reason='Windows PE identity')
ROOT=Path(__file__).resolve().parents[1]


def resources(path):
    import pefile
    with pefile.PE(str(path),fast_load=True) as pe:
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_RESOURCE']])
        result={}
        for type_ in pe.DIRECTORY_ENTRY_RESOURCE.entries:
            for name in type_.directory.entries:
                for language in name.directory.entries:
                    item=language.data.struct
                    result[(type_.id,str(name.name) if name.name else name.id,language.id)]=pe.get_data(item.OffsetToData,item.Size)
        return result


def code_sections(path):
    import pefile
    with pefile.PE(str(path),fast_load=True) as pe:
        sections=[(section.Name,section.PointerToRawData,section.SizeOfRawData)
                  for section in pe.sections if section.Characteristics&0x20]
    result={}
    with Path(path).open('rb') as stream:
        for name,offset,size in sections:
            stream.seek(offset);digest=hashlib.sha256()
            while size:
                data=stream.read(min(size,1024*1024));assert data
                digest.update(data);size-=len(data)
            result[name]=digest.hexdigest()
    return result


def icon_pixels(icon):
    user=ctypes.WinDLL('user32');gdi=ctypes.WinDLL('gdi32')
    class ICONINFO(ctypes.Structure):
        _fields_=[('icon',w.BOOL),('x',w.DWORD),('y',w.DWORD),('mask',w.HBITMAP),('color',w.HBITMAP)]
    class BITMAP(ctypes.Structure):
        _fields_=[('type',w.LONG),('width',w.LONG),('height',w.LONG),('stride',w.LONG),('planes',w.WORD),('bits',w.WORD),('data',ctypes.c_void_p)]
    class INFO(ctypes.Structure):
        _fields_=[('size',w.DWORD),('width',w.LONG),('height',w.LONG),('planes',w.WORD),('bits',w.WORD),('compression',w.DWORD),('image_size',w.DWORD),('x',w.LONG),('y',w.LONG),('used',w.DWORD),('important',w.DWORD)]
    user.GetIconInfo.argtypes=[w.HICON,ctypes.POINTER(ICONINFO)]
    gdi.GetObjectW.argtypes=[w.HANDLE,ctypes.c_int,ctypes.c_void_p]
    gdi.CreateCompatibleDC.argtypes=[w.HDC];gdi.CreateCompatibleDC.restype=w.HDC
    gdi.GetDIBits.argtypes=[w.HDC,w.HBITMAP,w.UINT,w.UINT,ctypes.c_void_p,ctypes.c_void_p,w.UINT]
    gdi.DeleteObject.argtypes=[w.HANDLE];gdi.DeleteDC.argtypes=[w.HDC]
    details=ICONINFO();assert user.GetIconInfo(icon,ctypes.byref(details))
    dc=None
    try:
        bitmap=BITMAP();assert gdi.GetObjectW(details.color,ctypes.sizeof(bitmap),ctypes.byref(bitmap))
        info=INFO();info.size=ctypes.sizeof(info);info.width=bitmap.width;info.height=-bitmap.height;info.planes=1;info.bits=32
        data=ctypes.create_string_buffer(bitmap.width*bitmap.height*4);dc=gdi.CreateCompatibleDC(None)
        assert gdi.GetDIBits(dc,details.color,0,bitmap.height,data,ctypes.byref(info),0)==bitmap.height
        return bitmap.width,bitmap.height,hashlib.sha256(data.raw).hexdigest()
    finally:
        if dc:gdi.DeleteDC(dc)
        for bitmap in (details.color,details.mask):
            if bitmap:gdi.DeleteObject(bitmap)


def test_runtime_icon_groups_and_default_extraction(tmp_path):
    pytest.importorskip('PyInstaller');pytest.importorskip('pefile')
    from tools.package import brand_windows_runtime
    from PyInstaller.utils.win32.icon import IconFile
    runtime=Path(os.environ.get('RUSTER_TEST_RUNTIME',ROOT/'dist/Ruster-windows-x64-5.2/runtime/blender.exe'))
    if not runtime.is_file():pytest.skip('A packaged Windows runtime fixture is required')
    target=tmp_path/'Rustmatics-engine-icon-test.exe';shutil.copy2(runtime,target)
    before_code=code_sections(target);before=resources(target);ico=ROOT/'ruster/branding/ruster.ico';source=IconFile(str(ico))
    result=brand_windows_runtime(target,ico);after=resources(target)
    assert code_sections(target)==before_code
    assert {key:data for key,data in before.items() if key[0] not in (3,14)}=={key:data for key,data in after.items() if key[0] not in (3,14)}
    groups={key:data for key,data in after.items() if key[0]==14}
    assert groups and set(key for key in before if key[0]==14)<=set(groups)
    for (_type,_name,language),group in groups.items():
        reserved,type_,count=struct.unpack_from('<HHH',group)
        assert reserved==0 and type_==1 and count==len(source.images)
        for index,image in enumerate(source.images):
            image_id=struct.unpack_from('<H',group,6+index*14+12)[0]
            assert after[(3,image_id,language)]==image
    shell=ctypes.WinDLL('shell32');user=ctypes.WinDLL('user32')
    shell.ExtractIconExW.argtypes=[w.LPCWSTR,ctypes.c_int,ctypes.POINTER(w.HICON),ctypes.POINTER(w.HICON),w.UINT]
    shell.ExtractIconExW.restype=w.UINT
    user.LoadImageW.argtypes=[w.HINSTANCE,w.LPCWSTR,w.UINT,ctypes.c_int,ctypes.c_int,w.UINT];user.LoadImageW.restype=w.HANDLE
    user.DestroyIcon.argtypes=[w.HICON]
    extracted=[]
    for group_index in range(len({key[1] for key in groups})):
        big=w.HICON();small=w.HICON();assert shell.ExtractIconExW(str(target),group_index,ctypes.byref(big),ctypes.byref(small),1)>=1
        for native in (small,big):
            expected=None
            try:
                width,height,digest=icon_pixels(native)
                expected=user.LoadImageW(None,str(ico),1,width,height,0x10);assert expected
                assert icon_pixels(expected)==(width,height,digest)
                extracted.append({'group_index':group_index,'width':width,'height':height,'pixel_sha256':digest})
            finally:
                if expected:user.DestroyIcon(expected)
                user.DestroyIcon(native)
    evidence={**result,'default_extractions':extracted,'original_group_names':[str(key[1]) for key in groups],'other_resources_preserved':True,'engine_code_unchanged':True}
    if destination:=os.environ.get('RUSTER_PE_IDENTITY_EVIDENCE'):
        Path(destination).write_text(json.dumps(evidence,indent=2),encoding='utf8')
    print('RUSTER_RUNTIME_PE_IDENTITY_OK '+json.dumps(evidence))
