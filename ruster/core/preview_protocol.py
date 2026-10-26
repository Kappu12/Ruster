"""Bounded placement snapshots shared by the local server and preview client."""
import json
import math
from pathlib import Path
import struct

from .project import atomic_write
from .rust_map import RustMap
from . import wire

MAGIC = b'RUSLIVE1'
MAX_SNAPSHOT = 16 * 1024 * 1024
MAX_REVISION = 2**63-1


def validate_placements(placements):
    seen = set()
    for row in placements:
        key, uid, path = row['key'], row['uid'], row['path']
        if type(key) is not int or not 0 < key < 2**64 or key in seen:
            raise ValueError('Preview placement IDs must be unique positive integers')
        seen.add(key)
        if type(uid) is not int or not 0 < uid < 2**32:
            raise ValueError('Invalid Rust prefab ID')
        if (not path.startswith('assets/') or not path.endswith('.prefab')
                or '..' in path or '\\' in path or '\x00' in path or len(path.encode()) > 4096):
            raise ValueError('Preview requires an original Rust prefab asset path')
        for name, length in (('position', 3), ('rotation', 4), ('scale', 3)):
            values = row[name]
            if len(values) != length or not all(type(v) in (int, float) and math.isfinite(v) and abs(v) < 1e7 for v in values):
                raise ValueError('Invalid preview transform')
        if any(abs(v) < 1e-6 for v in row['scale']):
            raise ValueError('Preview does not support zero scale')
        if abs(sum(v*v for v in row['rotation']) - 1) > .001:
            raise ValueError('Preview rotation must be a normalized quaternion')
        euler = row.get('euler', (0., 0., 0.))
        if len(euler) != 3 or not all(type(v) in (int, float) and math.isfinite(v) and abs(v) < 1e7 for v in euler):
            raise ValueError('Invalid map rotation')


def canonical_placements(placements):
    """Detach caller-owned mutable vectors and agree with both float32 readers."""
    placements = list(placements)
    validate_placements(placements)
    rows = []
    for source in placements:
        row = {key: source[key] for key in ('key', 'uid', 'path')}
        for key in ('position', 'rotation', 'scale', 'euler'):
            if key in source:
                values = source[key]
                row[key] = tuple(struct.unpack('<'+'f'*len(values), struct.pack('<'+'f'*len(values), *values)))
        rows.append(row)
    validate_placements(rows)
    return rows


def encode_snapshot(revision, placements):
    if type(revision) is not int or not 1 <= revision <= MAX_REVISION:raise ValueError('Invalid preview revision')
    placements = canonical_placements(placements)
    chunks = [MAGIC, struct.pack('<QI', revision, len(placements))]
    for row in placements:
        path = row['path'].encode('utf8')
        chunks.extend((struct.pack('<QII', row['key'], row['uid'], len(path)), path,
                       struct.pack('<10f', *row['position'], *row['rotation'], *row['scale'])))
    result = b''.join(chunks)
    if len(result) > MAX_SNAPSHOT:raise ValueError('Preview snapshot is too large')
    return result


def write_snapshot(directory, revision, placements):
    placements = canonical_placements(placements)
    payload = encode_snapshot(revision, placements)
    directory = Path(directory)
    # Each consumer sees either a complete old snapshot or a complete new one.
    atomic_write(directory/'scene.bin', payload)
    atomic_write(directory/'scene.json', json.dumps({'revision': revision, 'placements': placements},
        separators=(',', ':'), allow_nan=False).encode())


def composition_origin(placements):
    """Choose one stable center for the current document without editing it."""
    rows = canonical_placements(placements)
    if not rows:return (0., 0., 0.)
    return tuple((min(row['position'][axis] for row in rows)+max(row['position'][axis] for row in rows))/2 for axis in range(3))


def centered_placements(placements, origin):
    rows = canonical_placements(placements)
    for row in rows:row['position'] = tuple(value-offset for value, offset in zip(row['position'], origin))
    return canonical_placements(rows)


def preview_map(placements, size=1000, *, preload=()):
    """A void preview map: hidden terrain holes and no world scenery or paths."""
    placements = canonical_placements(placements)
    if size != 1000:raise ValueError('The void preview map is fixed at 1,000 metres')
    if any('euler' not in row for row in placements):raise ValueError('Initial map placements require Euler rotation metadata')
    n, m = 513, 512
    layers = {
        'height': b'\0\0' * n*n,
        'terrain': b'\0\0' * n*n,
        'water': b'\0\0' * n*n,
        'splat': b'\0\0\0\0\xff\0\0\0' * m*m,
        'biome': b'\0\xff\0\0' * m*m,
        'topology': b'\0\0\0\0' * m*m,
        'alpha': b'\0' * m*m,
    }
    fields = [wire.encode(1, 0, size)]
    for name, payload in layers.items():
        fields.append(wire.encode(2, 2, wire.serialize([
            wire.encode(1, 2, name.encode()), wire.encode(2, 2, payload)])))
    # Baking the initial scene loads its original asset scenes on both sides.
    # Both companions claim these exact placements before applying any edits.
    # Markers are map records only: never part of the editable snapshots or
    # initial placement claims. Their records make Rust load every asset scene.
    from .preview_preload import WARMUP_CATEGORY
    preload = list(preload)
    if len(preload) > 4096:raise ValueError('Too many prefab preload markers')
    markers = []
    for index, marker in enumerate(preload):
        if type(marker.get('uid')) is not int or not 0 < marker['uid'] < 2**32:raise ValueError('Invalid preload prefab ID')
        markers.append({'uid': marker['uid'], 'position': (10000.+index*32., -10000., 10000.),
            'euler': (0., 0., 0.), 'scale': (.001, .001, .001)})
    for category, row in [(b'RusterPreview', row) for row in placements]+[(WARMUP_CATEGORY, row) for row in markers]:
        record = [wire.encode(1, 2, category), wire.encode(2, 0, row['uid'])]
        for number, values in ((3, row['position']), (4, row.get('euler', (0., 0., 0.))), (5, row['scale'])):
            record.append(wire.encode(number, 2, wire.set_vector(None, values)))
        fields.append(wire.encode(3, 2, wire.serialize(record)))
    return RustMap(10, struct.pack('<q', 0), fields).write()
