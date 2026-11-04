#!/usr/bin/env python3
"""Launch a separate Ruster application process using a bundled or local Blender."""
import argparse
import os
from pathlib import Path
import shutil
import signal
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
    raise FileNotFoundError('Blender 5.2 LTS was not found. Run tools/package.py or set RUSTER_BLENDER.')


def main():
    parser = argparse.ArgumentParser(description='Ruster — Rust prefab studio')
    parser.add_argument('project', nargs='?', help='A .prefab, prefab-only .map import, or .ruster project')
    parser.add_argument('--blender', help='Path to Blender 5.2 LTS')
    parser.add_argument('--background', action='store_true', help='Launch without a window (development)')
    parser.add_argument('--headless', action='store_true', help='Run a persistent MCP host without a desktop window')
    parser.add_argument('--user-dir', help='Settings/cache directory (headless defaults to a separate profile)')
    parser.add_argument('--mcp-port', type=int, help='Headless MCP port (default 9878 on first use)')
    parser.add_argument('--rust-install', help='Rust game directory to index in headless mode')
    args = parser.parse_args()
    if (args.mcp_port is not None or args.rust_install) and not args.headless:
        parser.error('--mcp-port and --rust-install require --headless')
    if args.mcp_port is not None and not 1024 <= args.mcp_port <= 65535:
        parser.error('--mcp-port must be between 1024 and 65535')
    try:
        executable = find_blender(args.blender)
        sys.path.insert(0, str(ROOT))
        from ruster.core.headless import configure_user_dir
        configure_user_dir(args.user_dir, headless=args.headless)
        from ruster.core.settings import user_root
        env = os.environ.copy()
        # Do not inherit a host mode accidentally when launching the desktop.
        env.pop('RUSTER_HEADLESS', None)
        if args.headless:
            env['RUSTER_HEADLESS'] = '1'
            if args.mcp_port is not None:env['RUSTER_HEADLESS_PORT'] = str(args.mcp_port)
            if args.rust_install:env['RUSTER_HEADLESS_RUST_INSTALL'] = str(Path(args.rust_install).expanduser().resolve())
        env['RUSTER_LAUNCHER_PID'] = str(os.getpid())
        env['BLENDER_USER_CONFIG'] = str(user_root() / 'blender-config')
        env['BLENDER_USER_SCRIPTS'] = str(user_root() / 'blender-scripts')
        if (ROOT/'ruster/branding/splash.png').is_file():
            env['BLENDER_CUSTOM_SPLASH']=str(ROOT/'ruster/branding/splash.png')
        if (ROOT/'python_modules').exists():
            env['RUSTER_PYTHON_MODULES'] = str(ROOT/'python_modules')
        command = [executable, '--factory-startup', '--disable-autoexec', '--python-exit-code', '1',
                   '--python', str(ROOT/'bootstrap.py')]
        if args.background or args.headless:
            command.insert(1, '--background')
        if args.project:
            path = Path(args.project).expanduser().resolve()
            if path.suffix.lower() not in ('.map', '.prefab', '.ruster') or not path.is_file():
                parser.error('Choose an existing .map, .prefab or .ruster file')
            command += ['--', str(path)]
        log_path = user_root() / 'logs' / 'startup.log'
        log_path.parent.mkdir(parents=True, exist_ok=True)
        if args.headless:
            # Keep readiness/errors visible to CMD and supervising agents.
            flags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0
            process = subprocess.Popen(command, env=env, creationflags=flags)
            def stop_child(_signum=None, _frame=None):
                if process.poll() is None:
                    process.send_signal(signal.CTRL_BREAK_EVENT if sys.platform == 'win32' else signal.SIGTERM)
            signals = (signal.SIGTERM, *([signal.SIGBREAK] if hasattr(signal, 'SIGBREAK') else []))
            previous = {kind: signal.signal(kind, stop_child) for kind in signals}
            try:
                code = process.wait()
            except KeyboardInterrupt:
                stop_child()
                try:code = process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(); code = 1
            finally:
                for kind, handler in previous.items():signal.signal(kind, handler)
        else:
            with log_path.open('w', encoding='utf-8') as log:
                code = subprocess.call(command, env=env, stdout=log, stderr=subprocess.STDOUT)
        if code:
            details = 'See the terminal output above.' if args.headless else f'Details: {log_path}'
            raise OSError(f'Ruster could not start (exit {code}). {details}')
        return code
    except (FileNotFoundError, OSError) as error:
        if sys.stderr is not None:
            print(f'Ruster: {error}', file=sys.stderr)
        elif sys.platform == 'win32':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, str(error), 'Ruster could not start', 0x10)
        return 1


if __name__ == '__main__':
    sys.exit(main())
