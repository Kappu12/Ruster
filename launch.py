#!/usr/bin/env python3
"""Launch a separate Ruster application process using a bundled or local Blender."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(sys.executable if getattr(sys, 'frozen', False) else __file__).resolve().parent


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
    raise FileNotFoundError('Blender 4.5 LTS was not found. Run tools/package.py or set RUSTER_BLENDER.')


def main():
    parser = argparse.ArgumentParser(description='Ruster — Blender-based Rust map editor')
    parser.add_argument('project', nargs='?', help='A .map or .ruster file')
    parser.add_argument('--blender', help='Path to Blender 4.5 LTS')
    parser.add_argument('--background', action='store_true', help='Launch without a window (development)')
    args = parser.parse_args()
    try:
        executable = find_blender(args.blender)
        sys.path.insert(0, str(ROOT))
        from ruster.core.settings import user_root
        env = os.environ.copy()
        env['BLENDER_USER_CONFIG'] = str(user_root() / 'blender-config')
        env['BLENDER_USER_SCRIPTS'] = str(user_root() / 'blender-scripts')
        if (ROOT/'python_modules').exists():
            env['RUSTER_PYTHON_MODULES'] = str(ROOT/'python_modules')
        command = [executable, '--factory-startup', '--disable-autoexec', '--python', str(ROOT/'bootstrap.py')]
        if args.background:
            command.insert(1, '--background')
        if args.project:
            path = Path(args.project).expanduser().resolve()
            if path.suffix.lower() not in ('.map', '.ruster') or not path.is_file():
                parser.error('Choose an existing .map or .ruster file')
            command += ['--', str(path)]
        return subprocess.call(command, env=env)
    except (FileNotFoundError, OSError) as error:
        print(f'Ruster: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
