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

from ruster.assets.streaming import BlockStream, MAX_READ, SliceStream, BufferedSlice, streamed_bundles


def test_builtin_resources_resolve_only_game_files_with_size_limit(tmp_path):
    from ruster.assets.worker import builtin_resource
    resources=tmp_path/'RustClient_Data'/'Resources'
    resources.mkdir(parents=True)
    resource=resources/'unity default resources';resource.write_bytes(b'fixture')
    assert builtin_resource(tmp_path,'Library/Unity Default Resources')==resource
    assert builtin_resource(tmp_path,r'Library\unity default resources')==resource
    assert builtin_resource(tmp_path,'../unrelated') is None
    assert builtin_resource(tmp_path,'unity_builtin_extra') is None
    with resource.open('wb') as output:output.truncate(32*1024*1024+1)
    with pytest.raises(ValueError,match='32 MiB'):builtin_resource(tmp_path,'Library/unity default resources')


def bundle(path, at_end=False, count=512,node=b'CAB-test.resS'):
    block = b'abcd' * 16384
    packed = lz4.block.compress(block, store_size=False)
    info = (bytes(16) + struct.pack('>i', count)
            + struct.pack('>IIH', len(block), len(packed), 2) * count
            + struct.pack('>iqqI', 1, 0, count * len(block), 0) + node+b'\0')
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


def test_buffered_metadata_reads_still_reject_read_all_above_limit():
    class Source:
        length=MAX_READ+100
        def seek(self,*args):pass
        def read(self,*args):pytest.fail('An oversized read must fail before touching the source')
    stream=BufferedSlice(SliceStream(Source(),0,Source.length))
    with pytest.raises(ValueError,match='32 MiB'):stream.read()
    with pytest.raises(ValueError,match='32 MiB'):stream.read(MAX_READ+1)


def test_small_metadata_reads_share_a_bounded_buffer():
    class Source(io.BytesIO):
        length=65536
        reads=0
        def read(self,size=-1):
            self.reads+=1
            return super().read(size)
    source=Source(b'abcd'*16384)
    stream=BufferedSlice(SliceStream(source,0,source.length))
    for _ in range(1000):assert stream.read(4)==b'abcd'
    assert source.reads==1


def test_oversized_and_truncated_blocks_are_rejected_before_allocation():
    from UnityPy.streams import EndianBinaryReader
    source = EndianBinaryReader(b'1234')
    with pytest.raises(ValueError, match='16 MiB'):
        BlockStream(source, [(100 * 1024 * 1024, 4, 2)], lambda *_args: pytest.fail(), 4)
    with pytest.raises(ValueError, match='beyond'):
        BlockStream(source, [(5, 5, 0)], lambda *_args: pytest.fail(), 4)


def test_large_raw_block_reads_only_requested_bytes(tmp_path):
    from UnityPy.streams import EndianBinaryReader
    path=tmp_path/'large-raw'
    with path.open('wb') as output:
        output.seek(64*1024*1024);output.write(b'end')
    with path.open('rb') as input_:
        stream=BlockStream(EndianBinaryReader(input_),[(path.stat().st_size,path.stat().st_size,0)],
                           lambda *_args: pytest.fail('Raw data must never decompress'),path.stat().st_size)
        stream.seek(-3,2)
        assert stream.read(3)==b'end' and stream.cached==b''


def test_unselected_serialized_node_waits_for_pointer_access(tmp_path,monkeypatch):
    from UnityPy.helpers import ImportHelper
    from types import SimpleNamespace
    path=tmp_path/'bundle';bundle(path,count=1,node=b'CAB-delayed')
    calls=[]
    with streamed_bundles(node_filter=lambda _name:False) as UnityPy:
        env=UnityPy.load(str(path));container=next(iter(env.files.values()))
        lazy=container.files['CAB-delayed']
        monkeypatch.setattr(ImportHelper,'parse_file',lambda *_args,**_kwargs:
                            calls.append('parsed') or SimpleNamespace(objects={42:'mesh'}))
        assert not calls
        assert lazy.objects[42]=='mesh'
        assert lazy.objects[42]=='mesh' and calls==['parsed']


def test_extraction_can_skip_unused_bundle_container_and_restore_hook():
    from UnityPy.files.ObjectReader import ObjectReader
    from types import SimpleNamespace
    original=ObjectReader.parse_as_object
    with streamed_bundles(skip_containers=True):
        result=ObjectReader.parse_as_object(SimpleNamespace(type=SimpleNamespace(name='AssetBundle')))
        assert result.m_Container==[] and result.m_PreloadTable==[]
    assert ObjectReader.parse_as_object is original


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
