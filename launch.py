#!/usr/bin/env python3
"""Launch a separate Ruster application process using a bundled or local Blender."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(sys.executable if getattr(sys, 'frozen', False) else __file__).resolve().parent


def startup_completed(log_path):
    with Path(log_path).open('r',encoding='utf-8',errors='replace') as stream:
        return any(line.startswith('RUSTER_READY ') for line in stream.read(65536).splitlines())


def check_exit(code, log_path):
    if not code:return 0
    ready=startup_completed(log_path)
    # Windows TerminateProcess (including Stop-Process during an update) uses
    # -1. An editor that already started was stopped, not a failed startup.
    if sys.platform=='win32' and code in (-1,0xFFFFFFFF) and ready:
        with Path(log_path).open('a',encoding='utf-8') as stream:
            stream.write('\nRUSTER_STOPPED: editor stopped after successful startup (exit -1).\n')
        return 0
    action='Ruster stopped unexpectedly' if ready else 'Ruster could not start'
    raise OSError(f'{action} (exit {code}). Details: {log_path}')


def find_blender(explicit=None):
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if path.is_file():
            return str(path)
        raise FileNotFoundError(f'Blender executable does not exist: {path}')
    if value := os.environ.get('RUSTER_BLENDER'):
        return find_blender(value)
    candidates = [ROOT/'runtime/blender.exe', ROOT/'runtime/blender',
                  ROOT/'runtime/Blender.app/Contents/MacOS/Blender',
                  Path('/Applications/Blender.app/Contents/MacOS/Blender')]
    for path in candidates:
        if path.is_file():
            return str(path)
    if path := shutil.which('blender'):
        return path
    raise FileNotFoundError('Blender 5.2 LTS was not found. Run tools/package.py or set RUSTER_BLENDER.')


def main():
    parser = argparse.ArgumentParser(description='Ruster — Rust prefab studio')
    parser.add_argument('project', nargs='?', help='A .prefab, prefab-only .map import, or .ruster project')
    parser.add_argument('--blender', help='Path to Blender 5.2 LTS')
    parser.add_argument('--background', action='store_true', help='Launch without a window (development)')
    args = parser.parse_args()
    try:
        executable = find_blender(args.blender)
        sys.path.insert(0, str(ROOT))
        from ruster.core.settings import user_root
        env = os.environ.copy()
        env['RUSTER_LAUNCHER_PID'] = str(os.getpid())
        env['BLENDER_USER_CONFIG'] = str(user_root() / 'blender-config')
        env['BLENDER_USER_SCRIPTS'] = str(user_root() / 'blender-scripts')
        if (ROOT/'ruster/branding/splash.png').is_file():
            env['BLENDER_CUSTOM_SPLASH']=str(ROOT/'ruster/branding/splash.png')
        if (ROOT/'python_modules').exists():
            env['RUSTER_PYTHON_MODULES'] = str(ROOT/'python_modules')
        command = [executable, '--factory-startup', '--disable-autoexec', '--python-exit-code', '1',
                   '--python', str(ROOT/'bootstrap.py')]
        if args.background:
            command.insert(1, '--background')
        if args.project:
            path = Path(args.project).expanduser().resolve()
            if path.suffix.lower() not in ('.map', '.prefab', '.ruster') or not path.is_file():
                parser.error('Choose an existing .map, .prefab or .ruster file')
            command += ['--', str(path)]
        logs=user_root()/'logs';logs.mkdir(parents=True,exist_ok=True)
        descriptor,filename=tempfile.mkstemp(prefix='startup-',suffix='.log',dir=logs)
        os.close(descriptor);log_path=Path(filename)
        # Concurrent launches must never overwrite another editor's diagnostics.
        (logs/'latest-startup.txt').write_text(str(log_path),encoding='utf-8')
        with log_path.open('w', encoding='utf-8') as log:
            code = subprocess.call(command, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:shutil.copyfile(log_path,logs/'startup.log')
        except OSError:pass  # An older launcher can still have startup.log open.
        return check_exit(code,log_path)
    except (FileNotFoundError, OSError) as error:
        if sys.stderr is not None:
            print(f'Ruster: {error}', file=sys.stderr)
        elif sys.platform == 'win32':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, str(error), 'Ruster application error', 0x10)
        return 1


if __name__ == '__main__':
    sys.exit(main())
