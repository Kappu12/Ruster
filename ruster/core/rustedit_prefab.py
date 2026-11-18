"""RustEdit 1.2.19 custom-prefab interchange, independently implemented.

Contract verified against the user's installed PrefabSerialization type. Files
have a little-endian uint32 version followed by legacy LZ4Stream protobuf data.
Unknown payloads are retained, and an untouched input is emitted byte-for-byte.
"""
from dataclasses import dataclass, field
import hashlib
import math
from pathlib import Path
import struct

from . import legacy_lz4, wire
from .rust_map import prefab_id, prefab_transform
from .wire import FormatError

MAX_FILE = 32 * 1024 * 1024
MAX_BODY = 64 * 1024 * 1024
MAX_PLACEMENTS = 100000
FAMILIES = {2: 'terrain textures', 4: 'paths', 5: 'IO', 6: 'anchored paths',
            7: 'NPC spawners', 8: 'APC paths', 9: 'vehicles', 10: 'building grades'}


def validate_records(records):
    if not 1 <= len(records) <= MAX_PLACEMENTS:
        raise FormatError('A RustEdit prefab needs 1–100,000 placements')
    for record in records:
        if not prefab_id(record):raise FormatError('A Rust prefab ID must be nonzero')
        position, rotation, scale = prefab_transform(record)
        if not all(math.isfinite(v) for vector in (position, rotation, scale) for v in vector):
            raise FormatError('Prefab contains an invalid transform')
        if any(abs(v) < 1e-7 for v in scale):raise FormatError('Prefab contains zero scale')


def checksum(records):
    """Current RustEdit Checksum: ID bytes, then high three bytes per float32."""
    digest = hashlib.md5()
    for record in records:
        digest.update(struct.pack('<I', prefab_id(record)))
        for vector in prefab_transform(record):
            for value in vector:digest.update(struct.pack('<f', value)[1:])
    return digest.hexdigest()


@dataclass
class RustEditPrefab:
    fields: list
    original: bytes = field(default=b'', repr=False)
    original_body: bytes = field(default=b'', repr=False)

    @classmethod
    def read(cls, data):
        if not 5 <= len(data) <= MAX_FILE:raise FormatError('Invalid or oversized RustEdit prefab')
        if struct.unpack_from('<I', data)[0] != 1:raise FormatError('Unsupported RustEdit prefab version')
        body = legacy_lz4.decompress(data[4:], max_bytes=MAX_BODY)
        result = cls(wire.parse(body), data, body)
        validate_records(result.prefabs)
        return result

    @classmethod
    def load(cls, path):
        path = Path(path)
        if path.stat().st_size > MAX_FILE:raise FormatError('RustEdit prefab exceeds 32 MiB')
        return cls.read(path.read_bytes())

    @classmethod
    def create(cls, records, radius=0, fade=0):
        records = list(records)
        validate_records(records)
        if not 0 <= radius <= 32768 or not 0 <= fade <= 32768:
            raise FormatError('Invalid prefab radius or fade')
        options = wire.serialize([wire.encode(1, 0, radius), wire.encode(2, 0, fade)])
        fields = [wire.encode(1, 2, options)]
        fields += [wire.encode(3, 2, wire.serialize(row)) for row in records]
        fields += [wire.encode(number, 2, b'') for number in range(5, 11)]
        fields.append(wire.encode(11, 2, checksum(records).encode('ascii')))
        return cls(fields)

    @property
    def prefabs(self):return [wire.parse(f.value) for f in self.fields if f.number == 3 and f.wire == 2]

    @property
    def populated_extensions(self):
        return [label for number, label in FAMILIES.items()
                if any(f.number == number and f.wire == 2 and f.value for f in self.fields)]

    def set_terrain_options(self, width, fade):
        """Set RustEdit's stamp diameter and enabled channel masks."""
        from .rustedit_terrain import SPLAT_MASK, BIOME_MASK, TOPOLOGY_MASK
        if type(width) is not int or not 2 <= width <= 32768:
            raise FormatError('Terrain width must be an integer from 2 to 32768 metres')
        if type(fade) is not int or not 1 <= fade < width / 2:
            raise FormatError('Terrain edge fade must be positive and smaller than half the width')
        options = wire.parse(wire.get(self.fields, 1, b''))
        for number, value in enumerate((width, fade, SPLAT_MASK, BIOME_MASK, TOPOLOGY_MASK), 1):
            options = wire.replace(options, number, 0, value)
        self.fields = wire.replace(self.fields, 1, 2, wire.serialize(options))

    def replace_prefabs(self, records):
        records = list(records)
        validate_records(records)
        current = self.prefabs
        if [wire.serialize(r) for r in current] == [wire.serialize(r) for r in records]:return
        blocked = [label for label in self.populated_extensions if label != 'IO']
        if blocked:
            raise FormatError('This prefab carries ' + ', '.join(blocked)
                              + '; changing its placements requires editing those linked records too')
        fields = self.fields
        if 'IO' in self.populated_extensions:
            # Current RustEdit addresses IO entities and wire endpoints by their
            # prefab path and position. Keep placement identity/order stable and
            # move both ends with their corresponding placements.
            if len(current) != len(records) or any(prefab_id(a) != prefab_id(b) for a,b in zip(current, records)):
                raise FormatError('IO-linked prefabs must retain their placement IDs and order')
            positions = {}
            for old, new in zip(current, records):
                old_pos, new_pos = prefab_transform(old)[0], prefab_transform(new)[0]
                positions.setdefault(tuple(round(v, 3) for v in old_pos), []).append((old_pos, new_pos))
            def moved(message):
                value = wire.get(message, 2)
                if value is None:raise FormatError('IO record has no position; cannot safely move its links')
                position = wire.vector(value)
                matches = positions.get(tuple(round(v, 3) for v in position), [])
                if len(matches) != 1:
                    raise FormatError('IO position does not identify one unique prefab; cannot safely move its links')
                old, new = matches[0]
                if old == new:return message
                return wire.replace(message, 2, 2, wire.set_vector(value, new))
            fields = []
            for field_ in self.fields:
                if field_.number != 5 or field_.wire != 2 or not field_.value:
                    fields.append(field_);continue
                entities = []
                for entry in wire.parse(field_.value):
                    if entry.number != 1 or entry.wire != 2:
                        entities.append(entry);continue
                    entity = moved(wire.parse(entry.value))
                    links = []
                    for link in entity:
                        if link.number in (3,4) and link.wire == 2 and link.value:
                            links.append(wire.encode(link.number, 2, wire.serialize(moved(wire.parse(link.value)))))
                        else:links.append(link)
                    entities.append(wire.encode(1, 2, wire.serialize(links)))
                fields.append(wire.encode(5, 2, wire.serialize(entities)))
        result, inserted = [], False
        for f in fields:
            if f.number == 3:
                if not inserted:
                    result.extend(wire.encode(3, 2, wire.serialize(row)) for row in records)
                    inserted = True
            else:result.append(f)
        self.fields = wire.replace(result, 11, 2, checksum(records).encode('ascii'))

    def write(self):
        body = wire.serialize(self.fields)
        if body == self.original_body and self.original:return self.original
        if len(body) > MAX_BODY:raise FormatError('RustEdit prefab exceeds its data budget')
        data = struct.pack('<I', 1) + legacy_lz4.compress(body)
        if len(data) > MAX_FILE:raise FormatError('RustEdit prefab exceeds 32 MiB')
        return data
