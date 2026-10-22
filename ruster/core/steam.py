"""Bounded local Rust discovery from Steam roots, libraries and app manifests."""
import os
from pathlib import Path
import re
import sys
from .settings import validate_install


def read_vdf(path):
    """Parse Steam's quoted KeyValues subset without executing file contents."""
    path=Path(path)
    if path.stat().st_size>1024*1024:raise ValueError('Steam metadata is too large')
    source=path.read_text(encoding='utf-8-sig',errors='replace')
    tokens=[token for token in re.findall(r'"(?:\\.|[^"\\])*"|[{}]|//[^\n]*',source) if not token.startswith('//')]
    index=0
    def quoted(token):
        if not token.startswith('"'):raise ValueError('Invalid Steam metadata')
        return re.sub(r'\\([\\"])',r'\1',token[1:-1])
    def parse(depth=0):
        nonlocal index
        if depth>16:raise ValueError('Steam metadata nesting is too deep')
        result={}
        while index<len(tokens):
            if tokens[index]=='}':
                if not depth:raise ValueError('Unexpected Steam metadata brace')
                index+=1;return result
            key=quoted(tokens[index]);index+=1
            if index==len(tokens):raise ValueError('Missing Steam metadata value')
            token=tokens[index];index+=1
            result[key.lower()]=parse(depth+1) if token=='{' else quoted(token)
        if depth:raise ValueError('Unclosed Steam metadata object')
        return result
    return parse()


def registry_roots():
    if sys.platform!='win32':return []
    import winreg
    roots=[]
    for hive,key,value in ((winreg.HKEY_CURRENT_USER,r'Software\Valve\Steam','SteamPath'),
        (winreg.HKEY_LOCAL_MACHINE,r'SOFTWARE\Valve\Steam','InstallPath'),
        (winreg.HKEY_LOCAL_MACHINE,r'SOFTWARE\WOW6432Node\Valve\Steam','InstallPath')):
        try:
            with winreg.OpenKey(hive,key) as handle:
                path,_kind=winreg.QueryValueEx(handle,value)
                if isinstance(path,str) and path:roots.append(Path(path))
        except OSError:pass
    return roots


def steam_roots():
    home=Path.home()
    roots=registry_roots()
    if sys.platform=='win32':
        for key,fallback in (('ProgramFiles(x86)',r'C:\Program Files (x86)'),('ProgramFiles',r'C:\Program Files')):
            roots.append(Path(os.environ.get(key,fallback))/'Steam')
    elif sys.platform=='darwin':roots.append(home/'Library/Application Support/Steam')
    else:
        roots.extend((home/'.local/share/Steam',home/'.steam/steam',home/'.steam/root',
            home/'.var/app/com.valvesoftware.Steam/.local/share/Steam'))
        if os.environ.get('XDG_DATA_HOME'):roots.append(Path(os.environ['XDG_DATA_HOME'])/'Steam')
    return roots


def library_roots(roots):
    result=[];seen=set()
    for root in roots:
        root=Path(root).expanduser()
        try:key=str(root.resolve())
        except (OSError,RuntimeError):continue
        if key in seen:continue
        seen.add(key);result.append(root)
        try:
            data=read_vdf(root/'steamapps/libraryfolders.vdf').get('libraryfolders',{})
            if not isinstance(data,dict):continue
            for number,value in data.items():
                if not number.isdecimal():continue
                path=value.get('path') if isinstance(value,dict) else value
                if not isinstance(path,str) or not path:continue
                library=Path(path).expanduser()
                if not library.is_absolute():continue
                key=str(library.resolve())
                if key not in seen:seen.add(key);result.append(library)
        except (OSError,ValueError,RuntimeError):continue
    return result


def detect_install(roots=None):
    """Return a validated game folder, or None. Never scans drives recursively."""
    candidates=[]
    if os.environ.get('RUST_INSTALL_PATH'):candidates.append(Path(os.environ['RUST_INSTALL_PATH']))
    for root in library_roots(steam_roots() if roots is None else roots):
        apps=root/'steamapps'
        try:
            state=read_vdf(apps/'appmanifest_252490.acf').get('appstate',{})
            directory=state.get('installdir') if isinstance(state,dict) else None
            if isinstance(directory,str) and directory:
                common=(apps/'common').resolve();candidate=(common/directory).resolve()
                if candidate.is_relative_to(common):candidates.append(candidate)
        except (OSError,ValueError,RuntimeError):pass
        candidates.append(apps/'common/Rust')
    seen=set()
    for candidate in candidates:
        try:
            key=str(candidate.resolve())
            if key in seen:continue
            seen.add(key)
            return validate_install(candidate)
        except (OSError,ValueError,RuntimeError):continue
    return None
