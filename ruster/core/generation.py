"""Generation-only lifecycle around an installed, unmodified RustDedicated.

Rust's generator is not redistributed or extracted. All file validation and
process monitoring run off Blender's UI thread. Never reuse a server identity.
"""
from pathlib import Path
import math
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
import uuid

from . import steam
from .project import atomic_write
from .rust_map import RustMap


def executable(path):
    path=Path(path).expanduser().resolve()
    if path.is_dir():
        path=path/('RustDedicated.exe' if sys.platform=='win32' else 'RustDedicated')
    if path.name not in ('RustDedicated','RustDedicated.exe') or not path.is_file():
        raise ValueError('Choose an installed RustDedicated executable or its folder')
    if sys.platform!='win32' and not os.access(path,os.X_OK):
        raise ValueError('RustDedicated is not executable')
    return path


def detect(roots=None):
    """Steam app 258550 and standard names only; no recursive drive scanning."""
    for root in steam.library_roots(steam.steam_roots() if roots is None else roots):
        apps=root/'steamapps';common=(apps/'common').resolve();names=['Rust Dedicated Server','RustDedicated']
        try:
            state=steam.read_vdf(apps/'appmanifest_258550.acf').get('appstate',{})
            if isinstance(state,dict) and isinstance(state.get('installdir'),str):names.insert(0,state['installdir'])
        except (OSError,ValueError):pass
        for name in names:
            try:
                path=(common/name).resolve()
                if path.is_relative_to(common):return executable(path)
            except (OSError,ValueError):pass
    return None


def parameters(seed,size):
    if type(seed) is not int or not 0<=seed<=2147483647:raise ValueError('Seed must be an integer from 0 to 2147483647')
    if type(size) is not int or not 1000<=size<=6000:raise ValueError('Map size must be an integer from 1000 to 6000 metres')


def free_ports():
    """Separate ephemeral loopback ports; Rust will report bind races in its log."""
    handles=[]
    try:
        for kind in (socket.SOCK_DGRAM,socket.SOCK_DGRAM,socket.SOCK_STREAM):
            handle=socket.socket(socket.AF_INET,kind);handles.append(handle);handle.bind(('127.0.0.1',0))
        return tuple(handle.getsockname()[1] for handle in handles)
    finally:
        for handle in handles:handle.close()


def command(binary,seed,size,identity,log,ports):
    parameters(seed,size)
    game,query,rcon=ports
    return [str(binary),'-batchmode','-nographics','-logfile',str(log),
        '+server.level','Procedural Map','+server.seed',str(seed),'+server.worldsize',str(size),
        '+server.identity',identity,'+server.ip','127.0.0.1','+server.port',str(game),
        '+server.queryport',str(query),'+server.maxplayers','0',
        '+rcon.ip','127.0.0.1','+rcon.port',str(rcon),'+rcon.password',secrets.token_urlsafe(32),
        '+app.listenip','127.0.0.1','+app.port','0']


def writer_closed(path,pid):
    """Do not mistake a temporarily stable, parseable prefix for a finished map.

    Windows uses an exclusive-open probe; Linux inspects only our owned child's
    file descriptors. Fail closed if the completion probe is unavailable.
    """
    if sys.platform=='win32':
        import ctypes
        from ctypes import wintypes
        api=ctypes.WinDLL('kernel32',use_last_error=True)
        api.CreateFileW.argtypes=(wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,wintypes.LPVOID,
                                 wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE)
        api.CreateFileW.restype=wintypes.HANDLE
        api.CloseHandle.argtypes=(wintypes.HANDLE,);api.CloseHandle.restype=wintypes.BOOL
        handle=api.CreateFileW(str(path),0x80000000,0,None,3,0x80,None)
        if handle==ctypes.c_void_p(-1).value:
            code=ctypes.get_last_error()
            if code in (2,3,32,33):return False
            raise OSError(code,'Cannot verify generated map is closed')
        api.CloseHandle(handle);return True
    return linux_writer_closed(path,pid)


def linux_writer_closed(path,pid,proc_root=Path('/proc')):
    descriptors=proc_root/str(pid)/'fd'
    target=path.stat()
    try:entries=list(descriptors.iterdir())
    except FileNotFoundError as error:
        raise RuntimeError('Cannot verify generated map completion: owned process descriptors are unavailable') from error
    for entry in entries:
        try:
            stat=entry.stat()
            if (stat.st_dev,stat.st_ino)==(target.st_dev,target.st_ino):return False
        except FileNotFoundError:continue
    return True


class Generation:
    """One owned child. READY means a complete validated map, not server startup.

    Only newly written/changed seed-and-size-matching maps are eligible. Existing
    maps are never silently accepted: filenames alone cannot prove game version.
    Jobs preserve logs/results. No profile or game files are deleted on cleanup.
    """
    def __init__(self,binary,seed,size,output_root,timeout=1800):
        parameters(seed,size)
        if not 1<=timeout<=7200:raise ValueError('Generation timeout must be 1–7200 seconds')
        self.binary=executable(binary);self.seed=seed;self.size=size;self.timeout=timeout
        self.identity='ruster_gen_'+uuid.uuid4().hex
        self.directory=Path(output_root).resolve()/self.identity
        self.directory.mkdir(parents=True,exist_ok=False)
        self.roots=(self.binary.parent/'maps',self.binary.parent,
                    self.binary.parent/'server'/self.identity)
        self.status='STARTING';self.message='Starting Rust map generation';self.result=None
        self.error='';self.process=None;self.started=time.monotonic();self._cancel=threading.Event()
        self._stop_lock=threading.Lock()
        self._before={str(p):self._stat(p) for p in self._candidates()}
        self._thread=None

    def start(self):
        if self._thread is not None:raise ValueError('Generation job already started')
        self._thread=threading.Thread(target=self._run,name='Rustmatics map generation',daemon=True)
        self._thread.start();return self

    @property
    def active(self):return self.status in ('STARTING','GENERATING','VALIDATING')

    def cancel(self):self._cancel.set()

    def close(self):
        self.cancel()
        if self._thread:self._thread.join(timeout=6)
        # Validation may still be decoding a large map; the process must not
        # outlive a closing app just because validation has not returned yet.
        self._stop()

    def info(self):
        return {'status':self.status,'message':self.message,'seed':self.seed,'size':self.size,
            'elapsed_seconds':round(time.monotonic()-self.started,1) if self.active else getattr(self,'elapsed',0),
            'result':str(self.result) if self.result else None,'error':self.error,'logs':str(self.directory)}

    @staticmethod
    def _stat(path):
        stat=path.stat();return stat.st_size,stat.st_mtime_ns

    def _candidates(self):
        prefix=f'proceduralmap.{self.size}.{self.seed}'
        for root in self.roots:
            if not root.is_dir():continue
            for path in root.glob(prefix+'*.map'):
                # Require a separator after seed (123 must not match 1234).
                suffix=path.name[len(prefix):]
                if not suffix.startswith('.') or not path.is_file():continue
                resolved=path.resolve()
                if resolved.parent==root.resolve():yield resolved

    def _validate(self,path,signature):
        # One read/decompression only: large worlds must not be decoded twice.
        from .legacy_lz4 import MAX_BYTES
        if signature[0]>MAX_BYTES:raise ValueError('Generated map exceeds the supported file size')
        data=path.read_bytes();world=RustMap.read(data)
        if world.size!=self.size:raise ValueError('Generated map has an unexpected size')
        # Decompression/protobuf alone could accept an incomplete world record.
        layers=world.layers
        for name in ('terrain','water'):
            raw=layers.get(name,b'');n=math.isqrt(len(raw)//2)
            if n<2 or n*n*2!=len(raw):raise ValueError(f'Generated map has an invalid {name} heightmap')
        if signature!=self._stat(path):raise ValueError('Map is still being written')
        return world,data

    def _stop(self):
        with self._stop_lock:
            if self.process is None:return
            if self.process.poll() is None:self.process.terminate()
            try:self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill();self.process.wait(timeout=2)

    def _run(self):
        final='FAILED';seen={};exit_seen=None
        try:
            if self._cancel.is_set():final='CANCELLED';return
            args=command(self.binary,self.seed,self.size,self.identity,self.directory/'unity.log',free_ports())
            flags={'creationflags':subprocess.CREATE_NO_WINDOW} if sys.platform=='win32' else {}
            with (self.directory/'process.log').open('wb') as log:
                self.process=subprocess.Popen(args,cwd=self.binary.parent,stdout=log,stderr=subprocess.STDOUT,**flags)
                self.status='GENERATING';self.message='Generating map — waiting for complete terrain data'
                while not self._cancel.is_set():
                    if time.monotonic()-self.started>self.timeout:raise TimeoutError('Map generation timed out; see generation logs')
                    for path in self._candidates():
                        signature=self._stat(path);key=str(path)
                        if signature==self._before.get(key) or signature[0]<16:continue
                        if seen.get(key)!=signature:seen[key]=signature;continue
                        if self.process.poll() is None and not writer_closed(path,self.process.pid):continue
                        self.status='VALIDATING';self.message='Validating generated map'
                        try:
                            world,data=self._validate(path,signature)
                        except (OSError,ValueError,OverflowError):
                            self.status='GENERATING';continue
                        # Stop immediately: no wait for playable-server startup.
                        if self._cancel.is_set():break
                        self._stop()
                        target=self.directory/f'proceduralmap.{self.size}.{self.seed}.map'
                        atomic_write(target,data);self.result=target
                        # Counting top-level records avoids parsing every prefab
                        # solely for a status label on monument-heavy maps.
                        count=sum(f.number==3 and f.wire==2 for f in world.fields)
                        self.message=f'Map ready — {count:,} prefabs';final='READY';return
                    if self.process.poll() is not None:
                        if exit_seen is None:exit_seen=time.monotonic()
                        elif time.monotonic()-exit_seen>1:
                            raise RuntimeError(f'RustDedicated exited ({self.process.returncode}) without a new valid map. Check logs; an unchanged cached map is not accepted.')
                    self._cancel.wait(.35)
                final='CANCELLED';self.message='Map generation cancelled'
        except Exception as error:
            self.error=str(error);self.message=self.error
        finally:
            try:self._stop()
            except Exception as error:self.error=str(error);final='FAILED'
            if final=='CANCELLED':self.message='Map generation cancelled'
            self.elapsed=round(time.monotonic()-self.started,1);self.status=final
