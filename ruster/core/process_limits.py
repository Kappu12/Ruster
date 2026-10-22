"""Hard allocation limits and parent-death cleanup for owned child processes."""
import os
import sys
import threading

MIB = 1024 * 1024
ASSET_MEMORY = 768 * MIB
EDITOR_MEMORY = 4096 * MIB
_handles = []  # Job handles must stay open for the lifetime of the process.


def protect_process(memory_bytes, parent_pid=None):
    if sys.platform == 'win32':
        import ctypes
        from ctypes import wintypes as w

        class Basic(ctypes.Structure):
            _fields_ = [('process_time', ctypes.c_longlong), ('job_time', ctypes.c_longlong),
                        ('flags', w.DWORD), ('min_working_set', ctypes.c_size_t),
                        ('max_working_set', ctypes.c_size_t), ('active_processes', w.DWORD),
                        ('affinity', ctypes.c_size_t), ('priority', w.DWORD), ('scheduling', w.DWORD)]

        class IO(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in
                        ('reads', 'writes', 'other', 'read_bytes', 'write_bytes', 'other_bytes')]

        class Extended(ctypes.Structure):
            _fields_ = [('basic', Basic), ('io', IO), ('process_memory', ctypes.c_size_t),
                        ('job_memory', ctypes.c_size_t), ('peak_process', ctypes.c_size_t),
                        ('peak_job', ctypes.c_size_t)]

        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
        kernel.CreateJobObjectW.restype = w.HANDLE
        kernel.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
        kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        kernel.GetCurrentProcess.restype = w.HANDLE
        kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        kernel.OpenProcess.restype = w.HANDLE
        kernel.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
        kernel.CloseHandle.argtypes = [w.HANDLE]
        job = kernel.CreateJobObjectW(None, None)
        if not job:raise ctypes.WinError(ctypes.get_last_error())
        limits = Extended()
        limits.basic.flags = 0x2000 | 0x200  # KILL_ON_JOB_CLOSE | JOB_MEMORY
        limits.job_memory = memory_bytes
        if not kernel.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.get_last_error();kernel.CloseHandle(job);raise ctypes.WinError(error)
        if not kernel.AssignProcessToJobObject(job, kernel.GetCurrentProcess()):
            error = ctypes.get_last_error();kernel.CloseHandle(job);raise ctypes.WinError(error)
        _handles.append(job)
        if parent_pid:
            parent = kernel.OpenProcess(0x100000, False, parent_pid)  # SYNCHRONIZE
            if not parent:raise RuntimeError('The owning editor/worker is no longer running')
            _handles.append(parent)

            def watch():
                kernel.WaitForSingleObject(parent, 0xFFFFFFFF)
                os._exit(1)  # Closing our job handle also terminates our children.

            threading.Thread(target=watch, daemon=True).start()
    else:
        import resource
        _, hard = resource.getrlimit(resource.RLIMIT_AS)
        cap = memory_bytes if hard == resource.RLIM_INFINITY else min(memory_bytes, hard)
        resource.setrlimit(resource.RLIMIT_AS, (cap, cap))
        if parent_pid:
            def watch():
                import time
                while os.getppid() == parent_pid:time.sleep(.25)
                os._exit(1)
            threading.Thread(target=watch, daemon=True).start()
