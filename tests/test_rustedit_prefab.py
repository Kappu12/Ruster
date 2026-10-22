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


def test_moving_io_placements_moves_entities_and_connection_targets():
    rows=[record(123,(1,2,3)),record(456,(4,5,6))]
    prefab=RustEditPrefab.create(rows)
    connection=wire.serialize([wire.encode(1,2,b'target.prefab'),
        wire.encode(2,2,wire.set_vector(None,(4,5,6))),wire.encode(4,0,2)])
    entity=wire.serialize([wire.encode(1,2,b'source.prefab'),
        wire.encode(2,2,wire.set_vector(None,(1,2,3))),wire.encode(4,2,connection),
        wire.encode(7,5,struct.pack('<f',30)),wire.encode(99,2,b'opaque')])
    prefab.fields=wire.replace(prefab.fields,5,2,wire.serialize([wire.encode(1,2,entity)]))
    prefab.replace_prefabs([record(123,(7,8,9)),record(456,(10,11,12))])
    entity=wire.parse(wire.get(wire.parse(wire.get(prefab.fields,5)),1))
    assert wire.vector(wire.get(entity,2))==(7,8,9)
    assert wire.vector(wire.get(wire.parse(wire.get(entity,4)),2))==(10,11,12)
    assert wire.get(entity,99)==b'opaque'
    assert wire.get(entity,7)==struct.pack('<f',30)
    with pytest.raises(ValueError,match='IDs and order'):
        prefab.replace_prefabs([record(999,(7,8,9)),record(456,(10,11,12))])
