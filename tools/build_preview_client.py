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
    with tempfile.TemporaryDirectory(dir=output.parent, prefix='preview-build-') as folder:
        temporary = Path(folder)/output.name
        subprocess.run([str(compiler), 'c++', '-std=c++17', '-O2', '-shared', '-target', 'x86_64-windows-gnu',
            str(ROOT/'ruster/preview_native/client.cpp'), '-o', str(temporary), '-ladvapi32', '-luser32', '-liphlpapi', '-lws2_32'], check=True, cwd=ROOT,
            env=env)
        if sys.platform == 'win32':check_protocol(compiler, env)
        manifest = temporary.with_suffix('.json')
        manifest.write_text(json.dumps({'protocol': 1, 'platform': 'windows-x64',
            'client_bridge': 2, 'gc_handle_bits': 64, 'sha256': hashlib.sha256(temporary.read_bytes()).hexdigest(),
            'source_sha256': hashlib.sha256((ROOT/'ruster/preview_native/client.cpp').read_bytes()).hexdigest()}, indent=2))
        # Publish only a build whose standalone checks succeeded. If publication
        # is interrupted, integrity verification rejects a mismatched manifest.
        temporary.replace(output);manifest.replace(output.with_suffix('.json'))
    return output


def check_protocol(compiler, env):
    """Execute only our standalone binary parser, never a game or injection API."""
    with tempfile.TemporaryDirectory(dir=ROOT/'build', prefix='preview-protocol-') as folder:
        binary = Path(folder)/'decoder.exe'
        subprocess.run([str(compiler), 'c++', '-std=c++17', '-O2', '-target', 'x86_64-windows-gnu',
            str(ROOT/'tests/preview_protocol_native.cpp'), '-o', str(binary), '-ladvapi32', '-luser32', '-liphlpapi', '-lws2_32'], check=True, env=env)
        path = Path(folder)/'snapshot.bin'
        for data, expected in protocol_cases():
            path.write_bytes(data)
            result = subprocess.run([str(binary), str(path)], capture_output=True)
            if result.returncode != expected:raise RuntimeError('Native preview protocol check failed: '+result.stderr.decode(errors='replace'))
        for data, expected in peer_cases():
            path.write_bytes(data)
            result = subprocess.run([str(binary), '--peer', str(path)], capture_output=True)
            if result.returncode != expected:raise RuntimeError('Native connection proof check failed: '+result.stderr.decode(errors='replace'))
    print('Native decoder, pointer-sized handle polling/cleanup, API bindings, rollback and UDP ownership passed (no Rust process used)', flush=True)


def peer_cases():
    import struct
    url = b'http://127.0.0.1:12345/test.map'
    valid = b'RUSPEER2'+bytes.fromhex('a'*64)+struct.pack('<IIqI',123,23456,10000,len(url))+url
    def corrupt(offset, fmt, value):
        data = bytearray(valid);struct.pack_into(fmt,data,offset,value);return bytes(data)
    return [(valid,0),(valid[:59],1),(valid+b'extra',1),(b'BADPEER!'+valid[8:],1),
        (corrupt(40,'<I',0),1),(corrupt(40,'<I',456),1),(corrupt(44,'<I',0),1),(corrupt(44,'<I',65536),1),
        (corrupt(48,'<q',0),1),(corrupt(48,'<q',1),1),(corrupt(56,'<I',2049),1),
        (valid[:8]+b'\0'+valid[9:],1),(valid[:-1]+b'\0',1)]


def protocol_cases():
    """The same valid/malformed snapshots exercise both independent readers."""
    import struct
    sys.path.insert(0, str(ROOT))
    from ruster.core.preview_protocol import encode_snapshot
    row = {'key': 17, 'uid': 123456, 'path': 'assets/test/source.prefab',
        'position': (1., 2., -3.), 'rotation': (0., 0., 0., 1.), 'scale': (1., 2., 3.)}
    valid = encode_snapshot(7, [row])
    def corrupt(offset, fmt, value):
        data = bytearray(valid);struct.pack_into(fmt, data, offset, value);return bytes(data)
    return [(valid, 0), (encode_snapshot(8, []), 0), (encode_snapshot(2**63-1, [row]), 0),
        (valid[:19], 1), (b'NOTLIVE!'+valid[8:], 1), (valid+b'extra', 1),
        (corrupt(len(valid)-16, '<f', 0.), 1), (corrupt(len(valid)-4, '<f', 0.), 1),
        (corrupt(len(valid)-40, '<f', float('nan')), 1), (corrupt(8, '<Q', 0), 1),
        (corrupt(8, '<Q', 2**63), 1), (corrupt(16, '<I', 2001), 1),
        (corrupt(20, '<Q', 0), 1), (corrupt(28, '<I', 0), 1), (corrupt(32, '<I', 4097), 1),
        (valid[:36]+b'\xff'+valid[37:], 1), (valid[:43]+b'..'+valid[45:], 1),
        (valid[:16]+struct.pack('<I', 2)+valid[20:]+valid[20:], 1)]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zig', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    print(build(args.zig, args.output))
