"""Build the Windows x64 preview DLL; never open or inject a Rust process."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ZIG_URL = 'https://ziglang.org/download/0.15.2/zig-x86_64-windows-0.15.2.zip'
ZIG_SHA256 = '3a0ed1e8799a2f8ce2a6e6290a9ff22e6906f8227865911fb7ddedc3cc14cb0c'


def build(compiler=None, output=None):
    output = Path(output or ROOT/'ruster/preview_native/bin/RusterPreview.dll').resolve()
    if compiler is None:
        compiler = shutil.which('zig')
    if compiler is None:
        directory = ROOT/'build/preview-compiler';directory.mkdir(parents=True, exist_ok=True)
        archive = directory/'zig.zip'
        if not archive.is_file() or hashlib.sha256(archive.read_bytes()).hexdigest() != ZIG_SHA256:
            urllib.request.urlretrieve(ZIG_URL, archive)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != ZIG_SHA256:raise ValueError('Compiler SHA256 verification failed')
        compiler = directory/'zig-x86_64-windows-0.15.2/zig.exe'
        if not compiler.is_file():
            from ruster.core.live_preview import extract_zip
            extract_zip(archive, directory, limit=1024*1024*1024)
    output.parent.mkdir(parents=True, exist_ok=True)
    cache = ROOT/'build/preview-compiler/cache';cache.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(compiler), 'c++', '-std=c++17', '-O2', '-shared', '-target', 'x86_64-windows-gnu',
        str(ROOT/'ruster/preview_native/client.cpp'), '-o', str(output), '-ladvapi32', '-luser32'], check=True, cwd=ROOT,
        env={**os.environ, 'ZIG_GLOBAL_CACHE_DIR': str(cache), 'ZIG_LOCAL_CACHE_DIR': str(cache/'local')})
    output.with_suffix('.json').write_text(json.dumps({'protocol': 1, 'platform': 'windows-x64',
        'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
        'source_sha256': hashlib.sha256((ROOT/'ruster/preview_native/client.cpp').read_bytes()).hexdigest()}, indent=2))
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zig', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    print(build(args.zig, args.output))
