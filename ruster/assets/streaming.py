"""Read UnityFS blocks on demand instead of materializing an entire bundle.

The adapter targets the pinned UnityPy version and is installed only inside an
asset worker. Serialized files and resource streams are seekable slices sharing
one decompressed block per bundle; meshes/textures are never decoded by indexing.
"""
from bisect import bisect_right
from contextlib import contextmanager
import io

MAX_BLOCK = 16 * 1024 * 1024
MAX_READ = 32 * 1024 * 1024
MAX_DIRECTORY = 16 * 1024 * 1024


class BlockStream(io.RawIOBase):
    def __init__(self, reader, blocks, decompress, data_end):
        self.reader, self.decompress = reader, decompress
        self.blocks, self.starts = [], []
        self.position = self.length = 0
        self.cached_index, self.cached = -1, b''
        offset = reader.Position
        for raw_size, packed_size, flags in blocks:
            uncompressed = flags & 0x3f == 0
            if uncompressed and raw_size != packed_size:
                raise ValueError('Invalid uncompressed UnityFS block length')
            if raw_size <= 0 or packed_size <= 0 or (not uncompressed and max(raw_size,packed_size) > MAX_BLOCK):
                raise ValueError('UnityFS block exceeds the 16 MiB streaming limit')
            if offset + packed_size > data_end:
                raise ValueError('UnityFS block extends beyond bundle data')
            self.starts.append(self.length)
            self.blocks.append((offset, packed_size, raw_size, flags))
            offset += packed_size
            self.length += raw_size

    def readable(self):return True
    def seekable(self):return True
    def tell(self):return self.position

    def seek(self, offset, whence=0):
        target = offset + (self.position if whence == 1 else self.length if whence == 2 else 0)
        if whence not in (0, 1, 2) or target < 0:
            raise ValueError('Invalid bundle seek')
        self.position = target
        return target

    def read(self, size=-1):
        size = min(self.length - self.position, size if size >= 0 else self.length)
        if size > MAX_READ:
            raise ValueError('Asset read exceeds the 32 MiB per-object limit')
        if size <= 0:return b''
        parts = []
        while size:
            index = bisect_right(self.starts, self.position) - 1
            offset, packed, raw, flags = self.blocks[index]
            inside = self.position - self.starts[index]
            if flags & 0x3f == 0:
                # Current Rust ships large raw blocks. Seeking within them needs
                # no decompression or full-block allocation.
                count = min(size, raw-inside)
                self.reader.Position = offset+inside
                chunk = self.reader.read_bytes(count)
                if len(chunk)!=count:raise ValueError('Truncated uncompressed UnityFS block')
                parts.append(chunk);self.position+=count;size-=count
                continue
            if index != self.cached_index:
                self.cached = b''  # Release the previous block before allocating another.
                offset, packed, raw, flags = self.blocks[index]
                self.reader.Position = offset
                self.cached = self.decompress(self.reader.read_bytes(packed), raw, flags, index)
                if len(self.cached) != raw:
                    raise ValueError('UnityFS decompressed block length mismatch')
                self.cached_index = index
            inside = self.position - self.starts[index]
            count = min(size, len(self.cached) - inside)
            parts.append(self.cached[inside:inside + count])
            self.position += count
            size -= count
        return b''.join(parts)

    def close(self):
        self.cached = b''
        self.reader.dispose()
        super().close()


class SliceStream(io.RawIOBase):
    def __init__(self, source, offset, length):
        if offset < 0 or length < 0 or offset + length > source.length:
            raise ValueError('UnityFS directory entry extends beyond bundle data')
        self.source, self.offset, self.length = source, offset, length
        self.position = 0

    def readable(self):return True
    def seekable(self):return True
    def tell(self):return self.position

    def seek(self, offset, whence=0):
        target = offset + (self.position if whence == 1 else self.length if whence == 2 else 0)
        if whence not in (0, 1, 2) or target < 0:
            raise ValueError('Invalid asset slice seek')
        self.position = target
        return target

    def read(self, size=-1):
        size = max(0, min(self.length - self.position, size if size >= 0 else self.length))
        self.source.seek(self.offset + self.position)
        result = self.source.read(size)
        self.position += len(result)
        return result

    def readinto(self,buffer):
        data=self.read(len(buffer));buffer[:len(data)]=data
        return len(data)


class BufferedSlice(io.BufferedReader):
    """Buffer metadata's tiny reads without allowing an unbounded read-all."""
    def __init__(self,raw):super().__init__(raw,buffer_size=16*1024)

    def read(self,size=-1):
        remaining=self.raw.length-self.tell()
        requested=remaining if size is None or size<0 else min(size,remaining)
        if requested>MAX_READ:raise ValueError('Asset read exceeds the 32 MiB per-object limit')
        return super().read(size)


@contextmanager
def streamed_bundles(node_filter=None,skip_containers=False):
    import UnityPy
    from UnityPy.enums import ArchiveFlags, ArchiveFlagsOld
    from UnityPy.files import BundleFile, SerializedFile
    from UnityPy.helpers import ImportHelper
    from UnityPy.streams import EndianBinaryReader
    from UnityPy.files.ObjectReader import ObjectReader

    streams = []
    original_fs, original_files = BundleFile.read_fs, BundleFile.read_files
    original_legacy = BundleFile.read_web_raw
    original_parse = ObjectReader.parse_as_object
    original_serialized=SerializedFile.__init__

    def parse_serialized(file,reader,parent=None,name=None,**kwargs):
        from .serialized import parse
        return parse(file,reader,parent,name,original_serialized,kwargs)

    def parse_object(reader,*args,**kwargs):
        if skip_containers and reader.type.name=='AssetBundle':
            # Extraction already has the exact scene/path or object ID. UnityPy
            # otherwise eagerly builds a multi-million-pointer container here.
            from types import SimpleNamespace
            return SimpleNamespace(m_PreloadTable=[],m_Container=[])
        return original_parse(reader,*args,**kwargs)

    class LazyNode:
        is_dependency=True
        files={}
        def __init__(self,reader,parent,name):
            self.reader,self.parent,self.name=reader,parent,name
            self.parsed=None
        def load(self):
            if self.parsed is None:
                if isinstance(self.reader.stream,SliceStream):
                    self.reader=EndianBinaryReader(BufferedSlice(self.reader.stream))
                self.reader.Position=0
                self.parsed=ImportHelper.parse_file(self.reader,self.parent,self.name,is_dependency=True)
                self.parsed.flags=self.flags
                self.parent.files[self.name]=self.parsed
                if self.parent.environment:self.parent.environment.register_cab(self.name,self.parsed)
            return self.parsed
        def __getattr__(self,name):return getattr(self.load(),name)

    def read_fs(bundle, reader):
        declared_size = reader.read_long()
        packed, raw, flags = reader.read_u_int(), reader.read_u_int(), reader.read_u_int()
        if declared_size != reader.Length or not 0 < packed <= MAX_DIRECTORY or not 0 < raw <= MAX_DIRECTORY:
            raise ValueError('Invalid or oversized UnityFS directory')
        if bundle.signature != 'UnityFS':reader.read_byte()
        version = bundle.parse_version()
        old_flags = (version < (2020,) or (version[0] == 2020 and version < (2020, 3, 34))
                     or (version[0] == 2021 and version < (2021, 3, 2))
                     or (version[0] == 2022 and version < (2022, 1, 1)))
        bundle.dataflags = (ArchiveFlagsOld if old_flags else ArchiveFlags)(flags)
        if bundle.dataflags & bundle.dataflags.UsesAssetBundleEncryption:
            raise ValueError('Encrypted bundles are not supported by the bounded reader')
        if bundle.version >= 7 or (version[0] == 2019 and version >= (2019, 4, 15)):
            reader.align_stream(16)
            bundle._uses_block_alignment = True
        start = reader.Position
        at_end = bool(flags & 0x80)
        if at_end:reader.Position = reader.Length - packed
        directory = bundle.decompress_data(reader.read_bytes(packed), raw, flags)
        if len(directory) != raw:raise ValueError('UnityFS directory length mismatch')
        info = EndianBinaryReader(directory)
        info.read_bytes(16)
        count = info.read_int()
        if count < 0 or count > (raw - info.Position) // 10:
            raise ValueError('Invalid UnityFS block count')
        blocks = [(info.read_u_int(), info.read_u_int(), info.read_u_short()) for _ in range(count)]
        count = info.read_int()
        if count < 0 or count > (raw - info.Position) // 21:
            raise ValueError('Invalid UnityFS file count')
        from types import SimpleNamespace
        nodes = [SimpleNamespace(offset=info.read_long(), size=info.read_long(),
                 flags=info.read_u_int(), path=info.read_string_to_null()) for _ in range(count)]
        if at_end:reader.Position = start
        if not old_flags and flags & 0x200:reader.align_stream(16)
        stream = BlockStream(reader, blocks, bundle.decompress_data, reader.Length - packed if at_end else reader.Length)
        streams.append(stream)
        if blocks:bundle._block_info_flags = blocks[0][2]
        return nodes, stream

    def read_files(bundle, stream, nodes):
        for node in nodes:
            source=SliceStream(stream,node.offset,node.size)
            eager=node_filter is None or node_filter(node.path)
            reader = EndianBinaryReader(BufferedSlice(source) if eager else source)
            if not eager:
                parsed = reader
                if not node.path.lower().endswith(('.ress','.resource')):
                    parsed = LazyNode(reader,bundle,node.path)
            else:
                parsed = ImportHelper.parse_file(reader, bundle, node.path, is_dependency=bundle.is_dependency)
            if isinstance(parsed, (EndianBinaryReader, SerializedFile, LazyNode)) and bundle.environment:
                bundle.environment.register_cab(node.path, parsed)
            parsed.flags = getattr(node, 'flags', 0)
            bundle.files[node.path] = parsed

    def reject_legacy(*_args):
        raise ValueError('Legacy UnityWeb/UnityRaw bundles require a bounded streaming adapter')

    BundleFile.read_fs, BundleFile.read_files = read_fs, read_files
    BundleFile.read_web_raw = reject_legacy
    ObjectReader.parse_as_object=parse_object
    if skip_containers:SerializedFile.__init__=parse_serialized
    try:
        yield UnityPy
    finally:
        BundleFile.read_fs, BundleFile.read_files = original_fs, original_files
        BundleFile.read_web_raw = original_legacy
        ObjectReader.parse_as_object=original_parse
        SerializedFile.__init__=original_serialized
        for stream in streams:stream.close()
