"""Build the Windows x64 preview DLL; never open or inject a Rust process."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
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
            with zipfile.ZipFile(archive) as bundle:
                for item in bundle.infolist():
                    path = Path(item.filename.replace('\\', '/'))
                    if path.is_absolute() or '..' in path.parts or ':' in item.filename:raise ValueError('Unsafe compiler archive')
                bundle.extractall(directory)
    output.parent.mkdir(parents=True, exist_ok=True)
    cache = ROOT/'build/preview-compiler/cache';cache.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, 'ZIG_GLOBAL_CACHE_DIR': str(cache), 'ZIG_LOCAL_CACHE_DIR': str(cache/'local')}
    subprocess.run([str(compiler), 'c++', '-std=c++17', '-O2', '-shared', '-target', 'x86_64-windows-gnu',
        str(ROOT/'ruster/preview_native/client.cpp'), '-o', str(output), '-ladvapi32', '-luser32'], check=True, cwd=ROOT,
        env=env)
    output.with_suffix('.json').write_text(json.dumps({'protocol': 1, 'platform': 'windows-x64',
        'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
        'source_sha256': hashlib.sha256((ROOT/'ruster/preview_native/client.cpp').read_bytes()).hexdigest()}, indent=2))
    if sys.platform == 'win32':check_protocol(compiler, env)
    return output


def check_protocol(compiler, env):
    """Execute only our standalone binary parser, never a game or injection API."""
    binary = ROOT/'build/preview-protocol-test.exe'
    subprocess.run([str(compiler), 'c++', '-std=c++17', '-O2', '-target', 'x86_64-windows-gnu',
        str(ROOT/'tests/preview_protocol_native.cpp'), '-o', str(binary), '-ladvapi32', '-luser32'], check=True, env=env)
    sys.path.insert(0, str(ROOT))
    from ruster.core.preview_protocol import encode_snapshot
    row = {'key': 17, 'uid': 123456, 'path': 'assets/test/source.prefab',
        'position': (1., 2., -3.), 'rotation': (0., 0., 0., 1.), 'scale': (1., 2., 3.)}
    valid = encode_snapshot(7, [row])
    import struct
    bad_rotation = bytearray(valid);struct.pack_into('<f', bad_rotation, len(valid)-16, 0.)
    with tempfile.TemporaryDirectory(dir=ROOT/'build', prefix='preview-protocol-') as folder:
        path = Path(folder)/'snapshot.bin'
        for data, expected in ((valid, 0), (encode_snapshot(8, []), 0), (valid[:19], 1),
                (b'NOTLIVE!'+valid[8:], 1), (valid+b'extra', 1), (bytes(bad_rotation), 1),
                (valid[:16]+struct.pack('<I', 2001)+valid[20:], 1)):
            path.write_bytes(data)
            result = subprocess.run([str(binary), str(path)], capture_output=True)
            if result.returncode != expected:raise RuntimeError('Native preview protocol check failed: '+result.stderr.decode(errors='replace'))
    print('Native preview protocol and EAC-name checks passed (no Rust process used)', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zig', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    print(build(args.zig, args.output))
