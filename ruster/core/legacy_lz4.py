"""Rust's LZ4Stream framing, not the incompatible modern LZ4 frame format.

Reader supports compressed and raw chunks. Writer deliberately emits valid raw
chunks; this keeps the distribution dependency-free and preserves compatibility.
Framing reference: MiloszKrajewski/lz4net LZ4Stream; no third-party code copied.
"""
from .wire import FormatError, read_varint, varint

MAX_BYTES = 512 * 1024 * 1024
MAX_CHUNK = 64 * 1024 * 1024


def decompress_block(data, expected):
    out, pos = bytearray(), 0

    def length(base, pos):
        if base == 15:
            while True:
                if pos >= len(data):
                    raise FormatError("Truncated LZ4 length")
                byte = data[pos]
                pos += 1
                base += byte
                if byte != 255:
                    break
        return base, pos

    while pos < len(data):
        token = data[pos]
        pos += 1
        literals, pos = length(token >> 4, pos)
        if pos + literals > len(data) or len(out) + literals > expected:
            raise FormatError("Invalid LZ4 literal length")
        out.extend(data[pos:pos + literals])
        pos += literals
        if pos == len(data):
            break
        if pos + 2 > len(data):
            raise FormatError("Truncated LZ4 match")
        offset = int.from_bytes(data[pos:pos + 2], 'little')
        pos += 2
        if offset == 0 or offset > len(out):
            raise FormatError("Invalid LZ4 match offset")
        count, pos = length(token & 15, pos)
        count += 4
        if len(out) + count > expected:
            raise FormatError("LZ4 block exceeds its declared size")
        pattern = bytes(out[-offset:])
        repeats, tail = divmod(count, offset)
        out.extend(pattern * repeats + pattern[:tail])
    if len(out) != expected:
        raise FormatError("LZ4 block length mismatch")
    return bytes(out)


def decompress(data, max_bytes=MAX_BYTES):
    out, pos = bytearray(), 0
    while pos < len(data):
        flags, pos = read_varint(data, pos)
        if flags & ~3:
            raise FormatError("Unsupported LZ4Stream chunk flags")
        original, pos = read_varint(data, pos)
        stored = original
        if flags & 1:
            stored, pos = read_varint(data, pos)
        if original > MAX_CHUNK or len(out) + original > max_bytes:
            raise FormatError("Map exceeds the decompression limit")
        if stored > original or stored > len(data) - pos:
            raise FormatError("Truncated or invalid LZ4Stream chunk")
        chunk = data[pos:pos + stored]
        pos += stored
        out.extend(decompress_block(chunk, original) if flags & 1 else chunk)
    return bytes(out)


def compress(data, block_size=1024 * 1024):
    if not 0 < block_size <= MAX_CHUNK or len(data) > MAX_BYTES:
        raise FormatError("Map exceeds the supported size")
    return b"".join(b'\x00' + varint(len(data[i:i + block_size])) + data[i:i + block_size]
                    for i in range(0, len(data), block_size))
