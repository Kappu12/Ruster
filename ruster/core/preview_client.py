"""Windows-only, fail-closed checks and explicit injection of our preview DLL.

Nothing runs against a game process at import, registration, or server startup.
The user must click Inject. No debug privilege, driver, patch, or EAC bypass.
"""
from dataclasses import dataclass, field
from pathlib import Path
import ctypes
from ctypes import wintypes as W
import hashlib
import json
import re
import subprocess
import sys

RESTART_NOTICE = 'After injecting, restart your computer before launching Rust again.'


def is_eac_name(value):
    name = str(value).replace('\\', '/').rsplit('/', 1)[-1].casefold()
    return ('easyanticheat' in name or name == 'start_protected_game.exe'
            or name.startswith(('eac_', 'eac.', 'eac-', 'eacclient', 'eacserver', 'eacdriver', 'eaclauncher', 'eacservice')))


@dataclass
class ClientProbe:
    pid: int = 0
    executable: str = ''
    created: int = 0
    command_line: str = ''
    parent_name: str = ''
    modules: list = field(default_factory=list)
    eac_processes: list = field(default_factory=list)
    eac_services: list = field(default_factory=list)
    error: str = ''


def verify_probe(probe, installation):
    """An absent EAC flag alone is never accepted as evidence."""
    if probe.error:raise ValueError('Cannot verify EAC is off: ' + probe.error)
    expected = (Path(installation)/'RustClient.exe').resolve()
    if not probe.pid or not probe.created or Path(probe.executable).resolve() != expected:
        raise ValueError('The detected process is not this installation\'s RustClient.exe')
    missing = [name for name, value in (('launch command line', probe.command_line),
        ('original launcher', probe.parent_name), ('loaded modules', probe.modules)) if not value]
    if missing:
        raise ValueError('Cannot verify EAC is off: missing '+', '.join(missing)+'. Close Rust and use Launch Rust Without EAC.')
    if (is_eac_name(probe.parent_name) or Path(probe.parent_name).name.casefold() == 'rust.exe'
            or re.search(r'(?i)(?:^|\s)[-/](?:eac|easyanticheat)', probe.command_line)):
        raise ValueError('Rust was launched through an EAC wrapper; close it and use Launch Rust Without EAC')
    found = [str(v) for v in probe.modules if is_eac_name(v)] + probe.eac_processes + probe.eac_services
    if found:raise ValueError('EAC is active: ' + ', '.join(found[:3]))
    names = {Path(str(p)).name.casefold() for p in probe.modules}
    if not {'gameassembly.dll', 'unityplayer.dll'} <= names:
        raise ValueError('Rust is still starting, or its modules could not be verified')
    return probe


def _windows():
    if sys.platform != 'win32':raise ValueError('Client preview injection currently requires Windows x64')
    if ctypes.sizeof(ctypes.c_void_p) != 8:raise ValueError('Client preview requires a 64-bit process')
    return WindowsInspector()


class WindowsInspector:
    def __init__(self):
        self.k = ctypes.WinDLL('kernel32', use_last_error=True)
        self.a = ctypes.WinDLL('advapi32', use_last_error=True)
        self.n = ctypes.WinDLL('ntdll')
        signatures = {
            'CreateToolhelp32Snapshot': (W.HANDLE, [W.DWORD, W.DWORD]),
            'OpenProcess': (W.HANDLE, [W.DWORD, W.BOOL, W.DWORD]),
            'CloseHandle': (W.BOOL, [W.HANDLE]),
            'QueryFullProcessImageNameW': (W.BOOL, [W.HANDLE, W.DWORD, W.LPWSTR, ctypes.POINTER(W.DWORD)]),
            'GetProcessTimes': (W.BOOL, [W.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]),
            'VirtualAllocEx': (ctypes.c_void_p, [W.HANDLE, ctypes.c_void_p, ctypes.c_size_t, W.DWORD, W.DWORD]),
            'VirtualFreeEx': (W.BOOL, [W.HANDLE, ctypes.c_void_p, ctypes.c_size_t, W.DWORD]),
            'WriteProcessMemory': (W.BOOL, [W.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]),
            'CreateRemoteThread': (W.HANDLE, [W.HANDLE, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p, W.DWORD, ctypes.c_void_p]),
            'WaitForSingleObject': (W.DWORD, [W.HANDLE, W.DWORD]),
            'GetExitCodeThread': (W.BOOL, [W.HANDLE, ctypes.POINTER(W.DWORD)]),
            'LoadLibraryExW': (W.HMODULE, [W.LPCWSTR, W.HANDLE, W.DWORD]),
            'GetProcAddress': (ctypes.c_void_p, [W.HMODULE, ctypes.c_char_p]),
            'FreeLibrary': (W.BOOL, [W.HMODULE]),
            'GetModuleHandleExW': (W.BOOL, [W.DWORD, ctypes.c_void_p, ctypes.POINTER(W.HMODULE)]),
            'GetModuleFileNameW': (W.DWORD, [W.HMODULE, W.LPWSTR, W.DWORD]),
        }
        for name, (restype, args) in signatures.items():
            fn = getattr(self.k, name);fn.restype = restype;fn.argtypes = args
        self.n.NtQueryInformationProcess.restype = W.LONG
        self.n.NtQueryInformationProcess.argtypes = [W.HANDLE, W.ULONG, ctypes.c_void_p, W.ULONG, ctypes.POINTER(W.ULONG)]

    @staticmethod
    def require(ok, message):
        if not ok:raise OSError(ctypes.get_last_error(), message)

    def processes(self):
        class Entry(ctypes.Structure):
            _fields_ = [('size', W.DWORD), ('usage', W.DWORD), ('pid', W.DWORD), ('heap', ctypes.c_size_t),
                ('module', W.DWORD), ('threads', W.DWORD), ('parent', W.DWORD), ('priority', W.LONG),
                ('flags', W.DWORD), ('name', W.WCHAR*260)]
        snap = self.k.CreateToolhelp32Snapshot(2, 0)
        self.require(snap != ctypes.c_void_p(-1).value, 'Cannot enumerate processes')
        try:
            entry = Entry();entry.size = ctypes.sizeof(entry)
            for name in ('Process32FirstW', 'Process32NextW'):
                fn = getattr(self.k, name);fn.argtypes = [W.HANDLE, ctypes.POINTER(Entry)];fn.restype = W.BOOL
            self.require(self.k.Process32FirstW(snap, ctypes.byref(entry)), 'Cannot read process list')
            result = {}
            while True:
                result[entry.pid] = (entry.name, entry.parent)
                if not self.k.Process32NextW(snap, ctypes.byref(entry)):break
            if ctypes.get_last_error() != 18:raise OSError('Process enumeration was incomplete')
            return result
        finally:self.k.CloseHandle(snap)

    def modules(self, pid):
        class Entry(ctypes.Structure):
            _fields_ = [('size', W.DWORD), ('id', W.DWORD), ('pid', W.DWORD), ('global_', W.DWORD),
                ('usage', W.DWORD), ('base', ctypes.c_void_p), ('bytes', W.DWORD), ('handle', W.HMODULE),
                ('name', W.WCHAR*256), ('path', W.WCHAR*260)]
        snap = self.k.CreateToolhelp32Snapshot(0x18, pid)
        self.require(snap != ctypes.c_void_p(-1).value, 'Cannot inspect Rust modules; EAC state is unknown')
        try:
            entry = Entry();entry.size = ctypes.sizeof(entry)
            for name in ('Module32FirstW', 'Module32NextW'):
                fn = getattr(self.k, name);fn.argtypes = [W.HANDLE, ctypes.POINTER(Entry)];fn.restype = W.BOOL
            self.require(self.k.Module32FirstW(snap, ctypes.byref(entry)), 'Cannot read Rust modules')
            result = []
            while True:
                result.append((entry.path, entry.base))
                if not self.k.Module32NextW(snap, ctypes.byref(entry)):break
            if ctypes.get_last_error() != 18:raise OSError('Module enumeration was incomplete')
            return result
        finally:self.k.CloseHandle(snap)

    def active_eac_services(self):
        class Status(ctypes.Structure):
            _fields_ = [(name, W.DWORD) for name in ('type', 'state', 'accept', 'exit', 'specific', 'checkpoint', 'hint', 'pid', 'flags')]
        class Entry(ctypes.Structure):
            _fields_ = [('name', W.LPWSTR), ('display', W.LPWSTR), ('status', Status)]
        a = self.a
        a.OpenSCManagerW.argtypes = [W.LPCWSTR, W.LPCWSTR, W.DWORD];a.OpenSCManagerW.restype = W.HANDLE
        a.CloseServiceHandle.argtypes = [W.HANDLE]
        a.EnumServicesStatusExW.argtypes = [W.HANDLE, ctypes.c_int, W.DWORD, W.DWORD, ctypes.c_void_p,
            W.DWORD, ctypes.POINTER(W.DWORD), ctypes.POINTER(W.DWORD), ctypes.POINTER(W.DWORD), W.LPCWSTR]
        a.EnumServicesStatusExW.restype = W.BOOL
        manager = a.OpenSCManagerW(None, None, 4)
        self.require(manager, 'Cannot inspect EAC services and drivers')
        try:
            needed, count, resume = W.DWORD(), W.DWORD(), W.DWORD()
            buffer = ctypes.create_string_buffer(256*1024)
            self.require(a.EnumServicesStatusExW(manager, 0, 0x3f, 3, buffer, len(buffer),
                ctypes.byref(needed), ctypes.byref(count), ctypes.byref(resume), None), 'Cannot enumerate EAC services')
            entries = ctypes.cast(buffer, ctypes.POINTER(Entry))
            return [entries[i].name for i in range(count.value) if entries[i].status.state != 1
                and (is_eac_name(entries[i].name) or is_eac_name(entries[i].display))]
        finally:a.CloseServiceHandle(manager)

    def inspect(self, pid):
        probe = ClientProbe(pid=pid)
        handle = None
        try:
            processes = self.processes()
            if pid not in processes:raise OSError('Rust process exited')
            parent = processes[pid][1]
            probe.parent_name = processes.get(parent, ('', 0))[0]
            probe.eac_processes = [name for name, _ in processes.values() if is_eac_name(name)]
            handle = self.k.OpenProcess(0x1010, False, pid)
            self.require(handle, 'Rust process is not readable; EAC state is unknown')
            path, size = ctypes.create_unicode_buffer(32768), W.DWORD(32768)
            self.require(self.k.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)), 'Cannot verify Rust executable')
            probe.executable = path.value
            times = [ctypes.c_uint64() for _ in range(4)]
            self.require(self.k.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)), 'Cannot verify process identity')
            probe.created = times[0].value
            parent_handle = self.k.OpenProcess(0x1000, False, parent)
            self.require(parent_handle, 'The original Rust launcher cannot be verified')
            try:
                parent_times = [ctypes.c_uint64() for _ in range(4)]
                self.require(self.k.GetProcessTimes(parent_handle, *(ctypes.byref(t) for t in parent_times)), 'Cannot verify Rust launcher identity')
                if parent_times[0].value > probe.created:raise OSError('Rust launcher PID was reused; restart using the preview launch button')
            finally:self.k.CloseHandle(parent_handle)
            class UnicodeString(ctypes.Structure):
                _fields_ = [('length', W.USHORT), ('maximum', W.USHORT), ('buffer', ctypes.c_void_p)]
            buffer = ctypes.create_string_buffer(131072);used = W.ULONG()
            status = self.n.NtQueryInformationProcess(handle, 60, buffer, len(buffer), ctypes.byref(used))
            self.require(status == 0, 'Cannot inspect how Rust was launched')
            value = UnicodeString.from_buffer(buffer)
            begin, end = ctypes.addressof(buffer), ctypes.addressof(buffer)+len(buffer)
            self.require(value.length % 2 == 0 and value.buffer and begin <= value.buffer < end
                         and value.buffer+value.length <= end, 'Invalid process command line')
            probe.command_line = ctypes.wstring_at(value.buffer, value.length//2)
            probe.modules = [path for path, _ in self.modules(pid)]
            probe.eac_services = self.active_eac_services()
        except (OSError, ValueError) as error:probe.error = str(error)
        finally:
            if handle:self.k.CloseHandle(handle)
        return probe


def discover(installation):
    if sys.platform != 'win32':return []
    inspector = _windows()
    return [inspector.inspect(pid) for pid, (name, _) in inspector.processes().items()
            if name.casefold() == 'rustclient.exe']


def launch(installation):
    _windows()
    binary = (Path(installation)/'RustClient.exe').resolve()
    if not binary.is_file():raise ValueError('RustClient.exe was not found in your Rust installation')
    if discover(installation):raise ValueError('Rust is already running; close it before launching another instance')
    # The official direct executable route omits the EAC bootstrapper.
    return subprocess.Popen([str(binary)], cwd=binary.parent,
        creationflags=subprocess.CREATE_BREAKAWAY_FROM_JOB).pid


def verify_module(dll):
    """Validate our on-disk artifact before mapping it into another process."""
    dll = Path(dll)
    try:
        if not 0 < dll.stat().st_size <= 16*1024*1024:raise ValueError('Invalid preview DLL size')
        manifest = json.loads(dll.with_suffix('.json').read_text())
        if manifest.get('gc_handle_bits') != 64:
            raise ValueError('This preview DLL predates the Unity 6 object-handle fix. Rebuild or use the updated Ruster build.')
        if (manifest.get('protocol') != 1 or manifest.get('platform') != 'windows-x64'
                or hashlib.sha256(dll.read_bytes()).hexdigest() != manifest.get('sha256')):
            raise ValueError('Preview DLL integrity check failed; rebuild or reinstall Ruster')
        source = dll.parent.parent/'client.cpp'
        if source.is_file() and hashlib.sha256(source.read_bytes()).hexdigest() != manifest.get('source_sha256'):
            raise ValueError('Preview module source changed; rebuild the client module before starting preview')
    except (OSError, KeyError, json.JSONDecodeError) as error:
        raise ValueError('The preview module or its build manifest is missing or invalid; rebuild or reinstall Ruster') from error
    return manifest


def inject(installation, dll, session, pid):
    inspector = _windows()
    first = verify_probe(inspector.inspect(pid), installation)
    dll, session = Path(dll).resolve(), Path(session).resolve()
    if not dll.is_file():raise ValueError('The preview client DLL is missing; build the native preview module')
    if not (session/'scene.bin').is_file():raise ValueError('Start the local preview server first')
    def check():
        current = verify_probe(inspector.inspect(pid), installation)
        if current.created != first.created:raise ValueError('Rust restarted during verification; injection cancelled')
        from .live_preview import verify_session
        verify_session(session)
    check()
    verify_module(dll)
    if any(Path(name).name.casefold() == 'rusterpreview.dll' for name in first.modules):
        raise ValueError('A preview module is already loaded. '+RESTART_NOTICE)
    # Validate the export before the first remote write. DONT_RESOLVE_DLL_REFERENCES
    # maps our DLL locally without running its entry point or initializers.
    local = inspector.k.LoadLibraryExW(str(dll), None, 1)
    inspector.require(local, 'Could not inspect the preview module')
    try:
        entry = inspector.k.GetProcAddress(local, b'RusterStart')
        if not entry:raise ValueError('The preview DLL has no RusterStart entry point')
        entry_offset = entry-local
    finally:inspector.k.FreeLibrary(local)
    handle = inspector.k.OpenProcess(0x43a, False, pid)
    inspector.require(handle, 'Could not open the verified client; no privilege escalation is attempted')
    allocations = []
    try:
        def remote_call(address, text):
            check()
            payload = ctypes.create_unicode_buffer(text)
            length = ctypes.sizeof(payload)
            memory = inspector.k.VirtualAllocEx(handle, None, length, 0x3000, 4)
            inspector.require(memory, 'Could not allocate preview configuration')
            allocations.append(memory)
            written = ctypes.c_size_t()
            inspector.require(inspector.k.WriteProcessMemory(handle, memory, payload, length, ctypes.byref(written))
                and written.value == length, 'Could not write preview configuration')
            check()
            thread = inspector.k.CreateRemoteThread(handle, None, 0, address, memory, 0, None)
            inspector.require(thread, 'Could not start preview module')
            try:
                if inspector.k.WaitForSingleObject(thread, 15000) != 0:
                    # A timed-out thread might still read its parameter. Retain
                    # that tiny allocation until the game exits; never free it.
                    allocations.remove(memory)
                    raise ValueError('Preview load did not finish. '+RESTART_NOTICE)
                code = W.DWORD();inspector.require(inspector.k.GetExitCodeThread(thread, ctypes.byref(code)), 'Could not read loader result')
                return code.value
            finally:inspector.k.CloseHandle(thread)
        # Resolve LoadLibraryW in the target's kernel32 rather than assuming ASLR
        # produced the same base address in Blender and Rust.
        modules = inspector.modules(pid)
        if any(Path(name).name.casefold() == 'rusterpreview.dll' for name, _ in modules):
            raise ValueError('A preview module was loaded during verification. '+RESTART_NOTICE)
        local = inspector.k.LoadLibraryExW('kernel32.dll', None, 0)
        inspector.require(local, 'Cannot inspect the Windows loader')
        try:
            address = inspector.k.GetProcAddress(local, b'LoadLibraryW')
            containing = W.HMODULE()
            inspector.require(address and inspector.k.GetModuleHandleExW(6, address, ctypes.byref(containing)), 'Cannot resolve the Windows loader module')
            path = ctypes.create_unicode_buffer(32768)
            inspector.require(inspector.k.GetModuleFileNameW(containing, path, len(path)), 'Cannot resolve the Windows loader path')
            offset = address-containing.value
        finally:inspector.k.FreeLibrary(local)
        base = next((base for name, base in modules if Path(name).name.casefold() == Path(path.value).name.casefold()), None)
        if base is None:raise ValueError('The Windows loader module was not found in the verified client')
        remote_call(base+offset, str(dll))
        remote = next((base for path, base in inspector.modules(pid) if Path(path).resolve() == dll), None)
        if not remote:raise ValueError('The preview DLL did not load')
        code = remote_call(remote+entry_offset, str(session))
        if code != 0:raise ValueError(f'Client preview initialization refused ({code}); see the preview log')
    finally:
        for memory in allocations:inspector.k.VirtualFreeEx(handle, memory, 0, 0x8000)
        inspector.k.CloseHandle(handle)
