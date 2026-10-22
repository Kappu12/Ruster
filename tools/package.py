#!/usr/bin/env python3
"""Assemble a standalone Ruster distribution around a pinned official Blender.

Run on the target OS with the Python version in engine.lock.json.
Official downloads are SHA256-verified.
Game assets are never included. Blender's bundled licenses are retained.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def fetch(url, target, digest):
    if not target.exists() or hashlib.file_digest(target.open('rb'), 'sha256').hexdigest() != digest:
        print(f'Downloading {url}', flush=True)
        urllib.request.urlretrieve(url, target)
    actual = hashlib.file_digest(target.open('rb'), 'sha256').hexdigest()
    if actual != digest:
        target.unlink()
        raise ValueError('Blender archive SHA256 verification failed')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', action='store_true', help='Also create a distributable ZIP')
    parser.add_argument('--output-name', help='Distribution folder name inside dist (for side-by-side builds)')
    args = parser.parse_args()
    lock = json.loads((ROOT/'engine.lock.json').read_text())
    system = platform.system()
    target = {'Windows':'windows-x64', 'Linux':'linux-x64'}.get(system)
    if target is None or platform.machine().lower() not in ('amd64','x86_64'):
        raise SystemExit('Packaging currently supports Windows x64 and Linux x64. macOS support is pending.')
    python_version = lock['python_version']
    if sys.version_info[:2] != tuple(map(int, python_version.split('.'))):
        raise SystemExit(f'Use Python {python_version} to package dependencies for Blender {lock["series"]}.')
    entry = lock['archives'][target]
    build = ROOT/'build'
    build.mkdir(exist_ok=True)
    archive = build/entry['file']
    fetch(lock['base_url']+'/'+entry['file'], archive, entry['sha256'])
    output_name = args.output_name or f'Ruster-{target}'
    if output_name in ('.', '..') or Path(output_name).name != output_name:
        parser.error('--output-name must be a folder name')
    output = ROOT/'dist'/output_name
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    extract = build/'engine'
    if extract.exists():
        shutil.rmtree(extract)
    extract.mkdir()
    if archive.suffix == '.zip':
        with zipfile.ZipFile(archive) as stream:
            stream.extractall(extract)
    else:
        with tarfile.open(archive) as stream:
            stream.extractall(extract, filter='data')
    engine = next(p for p in extract.iterdir() if p.is_dir())
    shutil.move(str(engine), output/'runtime')
    for name in ('ruster','bootstrap.py','launch.py','mcp_server.py','Ruster.cmd','Ruster.sh','LICENSE',
                 'README.md','FEATURES.md','THIRD_PARTY_NOTICES.md','engine.lock.json','docs'):
        source, destination = ROOT/name, output/name
        if source.is_dir():
            shutil.copytree(source, destination, ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        else:
            shutil.copy2(source, destination)
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--only-binary=:all:', '--no-binary=tpk_ar',
                    '--target', str(output/'python_modules'), '-r', str(ROOT/'requirements-assets.txt'),
                    '-r',str(ROOT/'requirements-mcp.txt')], check=True)
    executable = output/'runtime'/('blender.exe' if system == 'Windows' else 'blender')
    # Fail packaging if the exact distribution cannot register and round-trip a scene.
    for test in ('blender_smoke.py','blender_editing.py','blender_placement.py','blender_protection.py','blender_ui.py','blender_mcp.py','blender_maps.py','blender_generation.py','blender_studio.py'):
        subprocess.run([str(executable), '-b', '--factory-startup', '--disable-autoexec', '--python-exit-code', '1',
                        '--python', str(ROOT/'tests'/test), '--', str(output)], check=True)
    python=next(p for p in sorted((output/'runtime').glob('*/python/bin/python*'))
        if p.is_file() and '-config' not in p.name and (system!='Windows' or p.name=='python.exe'))
    subprocess.run([str(python),str(ROOT/'tests/mcp_stdio_smoke.py'),str(output)],check=True)
    if system == 'Windows':
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'pyinstaller==6.16.0'], check=True)
        subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onefile', '--windowed',
                        '--name', 'Ruster', '--distpath', str(output),
                        '--workpath', str(build/'launcher'), '--specpath', str(build),
                        str(ROOT/'launch.py')], check=True)
    else:
        (output/'Ruster.sh').chmod(0o755)
    if args.archive:
        shutil.make_archive(str(output), 'zip', output.parent, output.name)
    print(f'Ready: {output}')


if __name__ == '__main__':
    main()
