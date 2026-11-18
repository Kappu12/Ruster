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
import tempfile
import urllib.request
import zipfile

if __package__:
    from .native_checks import run_suite
else:
    from native_checks import run_suite

ROOT = Path(__file__).resolve().parents[1]


def fetch(url, target, digest):
    if target.is_file():
        with target.open('rb') as cached:
            if hashlib.file_digest(cached, 'sha256').hexdigest() == digest:
                return
    print(f'Downloading {url}', flush=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as temporary:
        downloaded = Path(temporary)/target.name
        urllib.request.urlretrieve(url, downloaded)
        with downloaded.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != digest:
                raise ValueError('Blender archive SHA256 verification failed')
        downloaded.replace(target)


def brand_windows_runtime(executable, icon):
    """Replace every executable icon group without changing engine code/version.

    PyInstaller is a build-time dependency only. Updating every original group
    also covers Blender's native class-icon resource, not just Explorer's first
    icon. All non-icon PE resources, including version/licensing, are retained.
    Call this on a staged executable, never the user's running engine.
    """
    from PyInstaller.compat import win32api
    from PyInstaller.utils.win32.icon import IconFile
    executable,icon=Path(executable).resolve(),Path(icon).resolve()
    source=IconFile(str(icon))
    if source.header.idType!=1 or not 1<=len(source.images)<=256 or any(
            len(image)!=entry.dwBytesInRes or not image for image,entry in zip(source.images,source.entries)):
        raise ValueError('Invalid Ruster ICO resource')
    module=win32api.LoadLibraryEx(str(executable),0,2)
    try:
        try:groups=win32api.EnumResourceNames(module,14)
        except OSError:groups=[]
        targets=[(name,language) for name in groups for language in win32api.EnumResourceLanguages(module,14,name)]
        try:existing=win32api.EnumResourceNames(module,3)
        except OSError:existing=[]
        first=max((name for name in existing if isinstance(name,int)),default=0)+1
    finally:win32api.FreeLibrary(module)
    if first+len(source.images)>65536:raise ValueError('Executable icon resource IDs are exhausted')
    if not targets:targets=[(1,0)]
    languages={language for _name,language in targets}
    group=source.grp_icon_dir()+source.grp_icondir_entries(first)
    handle=win32api.BeginUpdateResource(str(executable),False)
    try:
        for language in languages:
            for index,image in enumerate(source.images,first):win32api.UpdateResource(handle,3,index,image,language)
        for name,language in targets:win32api.UpdateResource(handle,14,name,group,language)
    except Exception:
        win32api.EndUpdateResource(handle,True);raise
    else:win32api.EndUpdateResource(handle,False)
    return {'executable':str(executable),'icon':str(icon),'icon_groups':len(targets),'images':len(source.images)}


def stage_runtime(archive, runtime):
    if archive.suffix == '.dmg':
        runtime.mkdir()
        with tempfile.TemporaryDirectory(prefix='ruster-blender-') as mount:
            subprocess.run(['hdiutil', 'attach', '-readonly', '-nobrowse', '-mountpoint', mount, str(archive)], check=True)
            try:
                subprocess.run(['ditto', str(Path(mount)/'Blender.app'), str(runtime/'Blender.app')], check=True)
            finally:
                subprocess.run(['hdiutil', 'detach', mount], check=True)
        return runtime/'Blender.app/Contents/MacOS/Blender', runtime/'Blender.app/Contents/Resources'
    with tempfile.TemporaryDirectory(prefix='engine-', dir=archive.parent) as staging:
        extract = Path(staging)
        if archive.suffix == '.zip':
            with zipfile.ZipFile(archive) as stream:
                stream.extractall(extract)
            binary = 'blender.exe'
        else:
            with tarfile.open(archive) as stream:
                stream.extractall(extract, filter='data')
            binary = 'blender'
        engine = next(p for p in extract.iterdir() if p.is_dir())
        shutil.move(str(engine), runtime)
    return runtime/binary, runtime


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--archive', action='store_true', help='Also create a distributable ZIP')
    parser.add_argument('--output-name', help='Distribution folder name for side-by-side builds')
    parser.add_argument('--output-dir', type=Path, default=ROOT/'dist', help='Parent directory for the package and ZIP')
    args = parser.parse_args()
    lock = json.loads((ROOT/'engine.lock.json').read_text())
    system = platform.system()
    machine = platform.machine().lower()
    if system == 'Darwin' and machine == 'arm64':
        target = 'macos-arm64'
    elif system in ('Windows', 'Linux') and machine in ('amd64', 'x86_64'):
        target = f'{system.lower()}-x64'
    else:
        parser.error('Packaging supports Windows x64, Linux x64 and macOS Apple Silicon (native arm64 Python).')
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
    output = args.output_dir.resolve()/output_name
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    executable, engine_resources = stage_runtime(archive, output/'runtime')
    for name in ('ruster','bootstrap.py','launch.py','mcp_server.py','Ruster.cmd','Ruster.sh','LICENSE',
                 'README.md','FEATURES.md','THIRD_PARTY_NOTICES.md','engine.lock.json','docs'):
        source, destination = ROOT/name, output/name
        if source.is_dir():
            shutil.copytree(source, destination, ignore=shutil.ignore_patterns('__pycache__','*.pyc','*.pdb','*.lib','bin'))
        else:
            shutil.copy2(source, destination)
    if system == 'Windows':
        # Build into the package so existing copies of the DLL stay untouched.
        if __package__:from .build_preview_client import build as build_preview
        else:from build_preview_client import build as build_preview
        build_preview(output=output/'ruster/preview_native/bin/RusterPreview.dll')
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--only-binary=:all:', '--no-binary=tpk_ar',
                    '--target', str(output/'python_modules'), '-r', str(ROOT/'requirements-assets.txt'),
                    '-r',str(ROOT/'requirements-mcp.txt')], check=True)
    if system == 'Windows':
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'pyinstaller==6.16.0'], check=True)
        print('Runtime identity:',brand_windows_runtime(executable,output/'ruster/branding/ruster.ico'),flush=True)
    # Exercise the exact distribution with the same prefab contract as CI.
    run_suite(executable, app_root=output)
    python=next(p for p in sorted(engine_resources.glob('*/python/bin/python*'))
        if p.is_file() and '-config' not in p.name and (system!='Windows' or p.name=='python.exe'))
    subprocess.run([str(python),str(ROOT/'tests/mcp_stdio_smoke.py'),str(output)],check=True)
    if system == 'Windows':
        subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onefile', '--windowed',
                        '--name', 'Ruster', '--distpath', str(output),
                        '--icon',str(ROOT/'ruster/branding/ruster.ico'),
                        '--workpath', str(build/'launcher'), '--specpath', str(build),
                        str(ROOT/'launch.py')], check=True)
    else:
        (output/'Ruster.sh').chmod(0o755)
    if args.archive and system == 'Darwin':
        subprocess.run(['ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', str(output), f'{output}.zip'], check=True)
    elif args.archive:
        shutil.make_archive(str(output), 'zip', output.parent, output.name)
    print(f'Ready: {output}')


if __name__ == '__main__':
    main()
