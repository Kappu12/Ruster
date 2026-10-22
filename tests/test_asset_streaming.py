"""Synthetic bundles verify bounded reads without touching installed Rust."""
import io
from pathlib import Path
import struct
import os
import sqlite3
import subprocess
import sys

import lz4.block
import pytest

from ruster.assets.streaming import BlockStream, MAX_READ, SliceStream, streamed_bundles


def bundle(path, at_end=False, count=512):
    block = b'abcd' * 16384
    packed = lz4.block.compress(block, store_size=False)
    info = (bytes(16) + struct.pack('>i', count)
            + struct.pack('>IIH', len(block), len(packed), 2) * count
            + struct.pack('>iqqI', 1, 0, count * len(block), 0) + b'CAB-test.resS\0')
    prefix = b'UnityFS\0' + struct.pack('>I', 7) + b'5.x.x\0' + b'2022.3.1f1\0'
    header_size = (len(prefix) + 20 + 15) // 16 * 16
    size = header_size + len(info) + len(packed) * count
    header = prefix + struct.pack('>qIII', size, len(info), len(info), 0x40 | (0x80 if at_end else 0))
    with path.open('wb') as stream:
        stream.write(header.ljust(header_size, b'\0'))
        if not at_end:stream.write(info)
        for _ in range(count):stream.write(packed)
        if at_end:stream.write(info)
    return len(block) * count


@pytest.mark.parametrize('at_end', [False, True])
def test_real_unitypy_reads_virtual_bundle_without_materializing_it(tmp_path, monkeypatch, at_end):
    from UnityPy.files import BundleFile
    path = tmp_path / 'bundle'
    length = bundle(path, at_end, count=1024)  # 64 MiB logical, about 280 KiB on disk.
    original = BundleFile.decompress_data
    decoded = []

    def track(self, packed, raw, flags, index=0):
        decoded.append(raw)
        return original(self, packed, raw, flags, index)

    monkeypatch.setattr(BundleFile, 'decompress_data', track)
    with streamed_bundles() as UnityPy:
        env = UnityPy.load(str(path))
        reader = next(iter(env.files.values())).files['CAB-test.resS']
        assert reader.Length == length
        reader.Position = length - 7
        assert reader.read(7) == b'bcdabcd'
        assert sum(decoded) < 256 * 1024  # Directory plus just the first and last blocks.
        reader.Position = 0
        with pytest.raises(ValueError, match='32 MiB'):
            reader.read(MAX_READ + 1)
    path.unlink()  # The adapter must release its file handles.


def test_slice_crosses_blocks_and_clamps_eof():
    from UnityPy.streams import EndianBinaryReader
    source = EndianBinaryReader(b'abcdeXYZ')
    stream = BlockStream(source, [(5, 5, 0), (3, 3, 0)], lambda data, *_args: data, 8)
    view = SliceStream(stream, 3, 4)
    assert view.read(100) == b'deXY'
    assert view.read(1) == b''
    view.seek(-2, 2)
    assert view.read() == b'XY'
    with pytest.raises(ValueError):SliceStream(stream, 2, 20)


def test_oversized_and_truncated_blocks_are_rejected_before_allocation():
    from UnityPy.streams import EndianBinaryReader
    source = EndianBinaryReader(b'1234')
    with pytest.raises(ValueError, match='16 MiB'):
        BlockStream(source, [(100 * 1024 * 1024, 4, 0)], lambda *_args: pytest.fail(), 4)
    with pytest.raises(ValueError, match='beyond'):
        BlockStream(source, [(5, 5, 0)], lambda *_args: pytest.fail(), 4)


def test_isolated_bundle_worker_uses_the_streaming_adapter(tmp_path):
    root = Path(__file__).resolve().parents[1]
    game = tmp_path / 'Rust'
    (game / 'Bundles').mkdir(parents=True)
    (game / 'RustClient.exe').touch()
    path = game / 'Bundles' / 'synthetic.bundle'
    bundle(path)
    cache = tmp_path / 'cache'
    env = os.environ.copy()
    import UnityPy
    env['RUSTER_PYTHON_MODULES'] = str(Path(UnityPy.__file__).resolve().parent.parent)
    result = subprocess.run([sys.executable, str(root / 'ruster/assets/worker.py'),
                             'index-bundle', '--install', str(game), '--cache', str(cache),
                             '--bundle', 'Bundles/synthetic.bundle', '--parent-pid', str(os.getpid())],
                            env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr + result.stdout
    with sqlite3.connect(cache / 'catalog.sqlite3') as db:
        assert db.execute('SELECT path FROM bundles').fetchall() == [('Bundles/synthetic.bundle',)]
