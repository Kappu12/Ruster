import struct
import pytest
from ruster.core import wire
from ruster.core.rustedit_prefab import RustEditPrefab, checksum
from ruster.core.rust_map import update_transform


def record(uid=123, position=(1, 2, 3)):
    return update_transform([wire.encode(1, 2, b'Decor'), wire.encode(2, 0, uid)],
                            position, (0, 90, 0), (1, 1, 1))


def test_native_header_and_roundtrip_preserve_opaque_records():
    prefab = RustEditPrefab.create([record()])
    prefab.fields.append(wire.encode(101, 2, b'future metadata'))
    data = prefab.write()
    assert data[:4] == struct.pack('<I', 1)
    loaded = RustEditPrefab.read(data)
    assert loaded.write() == data
    loaded.replace_prefabs([record(position=(2, 3, 4))])
    assert wire.get(loaded.fields, 101) == b'future metadata'
    assert wire.get(loaded.fields, 11).decode() == checksum(loaded.prefabs)


def test_linked_extension_data_cannot_be_silently_misaligned():
    prefab = RustEditPrefab.create([record()])
    prefab.fields.append(wire.encode(5, 2, wire.serialize([wire.encode(1, 2, b'IO entity')])))
    data = prefab.write()
    loaded = RustEditPrefab.read(data)
    loaded.replace_prefabs(loaded.prefabs)
    assert loaded.write() == data
    with pytest.raises(ValueError, match='IO'):
        loaded.replace_prefabs([record(position=(2, 3, 4))])


@pytest.mark.parametrize('data', [b'', struct.pack('<I', 0) + b'x', struct.pack('<I', 1) + b'broken'])
def test_invalid_files_are_rejected(data):
    with pytest.raises(ValueError):RustEditPrefab.read(data)


def test_invalid_placements_are_rejected():
    with pytest.raises(ValueError):RustEditPrefab.create([record(uid=0)])
    with pytest.raises(ValueError):RustEditPrefab.create([])
