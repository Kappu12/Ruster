import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
PYTHON = getattr(sys, '_base_executable', sys.executable)


def test_allocation_is_refused_before_a_large_buffer_can_be_created():
    code = '''
from ruster.core.process_limits import protect_process, MIB
protect_process(96 * MIB)
try:
    data = bytearray(256 * MIB)
except MemoryError:
    print('ALLOCATION_REFUSED')
else:
    raise AssertionError('Memory cap was not enforced')
'''
    result = subprocess.run([PYTHON, '-c', code], cwd=ROOT, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert 'ALLOCATION_REFUSED' in result.stdout


def test_owned_worker_exits_when_parent_dies(tmp_path):
    ready = tmp_path / 'ready'
    child_code = f'''
import os,time
from pathlib import Path
from ruster.core.process_limits import protect_process, MIB
protect_process(96 * MIB, os.getppid())
Path({str(ready)!r}).write_text('ready')
time.sleep(30)
'''
    parent_code = f'''
import subprocess,sys,time
child=subprocess.Popen([sys.executable,'-c',{child_code!r}])
print(child.pid,flush=True)
time.sleep(30)
'''
    parent = subprocess.Popen([PYTHON, '-c', parent_code], cwd=ROOT,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        child_pid = int(parent.stdout.readline())
        deadline = time.monotonic() + 8
        while not ready.exists() and time.monotonic() < deadline:time.sleep(.05)
        assert ready.exists(), 'Worker did not install its parent-death guard'
        if sys.platform == 'win32':
            import ctypes
            from ctypes import wintypes as w
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
            kernel.OpenProcess.restype = w.HANDLE
            kernel.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
            kernel.CloseHandle.argtypes = [w.HANDLE]
            handle = kernel.OpenProcess(0x100000, False, child_pid)
            assert handle
            try:
                parent.terminate();parent.wait(timeout=5)
                assert kernel.WaitForSingleObject(handle, 5000) == 0, 'Worker survived its owner'
            finally:kernel.CloseHandle(handle)
        else:
            parent.terminate();parent.wait(timeout=5)
            # The child's inherited output pipe closes when its watchdog exits.
            parent.communicate(timeout=5)
    finally:
        if parent.poll() is None:parent.kill()
        parent.communicate(timeout=5)
