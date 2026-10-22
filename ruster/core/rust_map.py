"""Read versions 9/10 of Rust .map, preserving unknown data on write."""
from dataclasses import dataclass
from pathlib import Path
import math
import struct
from . import wire, legacy_lz4
from .wire import FormatError


@dataclass
class RustMap:
    version: int
    timestamp: bytes
    fields: list

    @classmethod
    def read(cls, data):
        if len(data) < 5 or len(data) > legacy_lz4.MAX_BYTES:
            raise FormatError("Invalid or oversized Rust map")
        version = struct.unpack_from('<I', data)[0]
        if version not in (9, 10):
            raise FormatError(f"Unsupported Rust map version {version}; supported: 9 and 10")
        offset = 12 if version == 10 else 4
        if len(data) <= offset:
            raise FormatError("Truncated map header")
        fields = wire.parse(legacy_lz4.decompress(data[offset:]))
        size = wire.get(fields, 1, 0)
        if not isinstance(size, int) or not 1 <= size <= 32768:
            raise FormatError("Invalid map size")
        return cls(version, data[4:offset], fields)

    @classmethod
    def load(cls, path):
        if Path(path).stat().st_size > legacy_lz4.MAX_BYTES:
            raise FormatError("Map exceeds the file size limit")
        return cls.read(Path(path).read_bytes())

    @property
    def size(self):
        return wire.get(self.fields, 1)

    def messages(self, number):
        return [wire.parse(f.value) for f in self.fields if f.number == number and f.wire == 2]

    @property
    def prefabs(self):
        return self.messages(3)

    @property
    def paths(self):
        return self.messages(4)

    @property
    def layers(self):
        return {wire.get(f, 1, b'').decode('utf8'): wire.get(f, 2, b'')
                for f in self.messages(2)}

    def replace_prefabs(self, prefabs):
        """Replace only prefab records; all other fields keep their exact bytes."""
        pending = iter(prefabs)
        result = []
        for f in self.fields:
            if f.number == 3:
                prefab = next(pending, None)
                if prefab is not None:
                    result.append(wire.encode(3, 2, wire.serialize(prefab)))
            else:
                result.append(f)
        result.extend(wire.encode(3, 2, wire.serialize(p)) for p in pending)
        self.fields = result

    def set_layer(self, name, data):
        """Update a layer's bytes while retaining its unknown metadata fields."""
        result, found = [], False
        for field in self.fields:
            if field.number == 2 and field.wire == 2:
                fields = wire.parse(field.value)
                if wire.get(fields, 1) == name.encode():
                    if found:
                        raise FormatError(f'Duplicate map layer: {name}')
                    found = True
                    if wire.get(fields, 2) != data:
                        fields = wire.replace(fields, 2, 2, data)
                        field = wire.encode(2, 2, wire.serialize(fields))
            result.append(field)
        if not found:
            result.append(wire.encode(2, 2, wire.serialize([
                wire.encode(1, 2, name.encode()), wire.encode(2, 2, data)])))
        self.fields = result

    def replace_paths(self, paths):
        pending = iter(paths)
        result = []
        for field in self.fields:
            if field.number == 4 and field.wire == 2:
                value = next(pending, None)
                if value is not None:
                    data = wire.serialize(value)
                    result.append(field if data == field.value else wire.encode(4, 2, data))
            else:
                result.append(field)
        result.extend(wire.encode(4, 2, wire.serialize(p)) for p in pending)
        self.fields = result

    def write(self):
        return (struct.pack('<I', self.version) + self.timestamp +
                legacy_lz4.compress(wire.serialize(self.fields)))

    def height_grid(self, name='terrain'):
        raw = self.layers.get(name)
        if raw is None:
            raise FormatError(f"Map has no {name} layer")
        n = math.isqrt(len(raw) // 2)
        if n < 2 or n * n * 2 != len(raw):
            raise FormatError(f"Invalid {name} heightmap dimensions")
        # Rust.World BitUtility.Short2Float uses signed Int16 / 32766.
        values = struct.unpack(f'<{n*n}h', raw)
        return n, values


def prefab_id(fields):
    value = wire.get(fields, 2, 0)
    if not isinstance(value, int) or not 0 <= value <= 0xFFFFFFFF:
        raise FormatError("Invalid prefab ID")
    return value


def prefab_transform(fields):
    return (wire.vector(wire.get(fields, 3)), wire.vector(wire.get(fields, 4)),
            wire.vector(wire.get(fields, 5), (1., 1., 1.)))


def update_transform(fields, position, rotation, scale):
    for index, values in ((3, position), (4, rotation), (5, scale)):
        if not all(math.isfinite(v) for v in values):
            raise FormatError("Prefab transform contains non-finite values")
        fields = wire.replace(fields, index, 2, wire.set_vector(wire.get(fields, index), values))
    return fields
