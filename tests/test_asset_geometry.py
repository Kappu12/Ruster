import gzip
import struct
import numpy as np
import pytest
from ruster.assets import geometry


def test_mesh_buffer_roundtrip_preserves_uv_and_submesh_slots(tmp_path):
    path=tmp_path/'mesh.gz'
    points=[[0,0,0],[1,0,0],[0,1,0],[0,0,1]]
    uv=[[0,0],[1,0],[0,1],[1,1]]
    spec=geometry.write(path,points,uv,[[[0,1,2]],[[0,2,3]]])
    assert geometry.info(path)==spec
    actual,coords,triangles,counts=geometry.read(path)
    assert np.array_equal(actual,points) and np.array_equal(coords,uv)
    assert np.array_equal(triangles,[[0,1,2],[0,2,3]]) and counts==(1,1)


def test_mesh_buffer_rejects_oversized_header_before_payload_read(tmp_path):
    path=tmp_path/'bad.gz'
    path.write_bytes(gzip.compress(geometry.HEADER.pack(b'RMS1',100000000,0,0,0)))
    with pytest.raises(ValueError,match='oversized'):geometry.read(path)


def test_mesh_buffer_rejects_invalid_indices_and_truncated_payload(tmp_path):
    path=tmp_path/'mesh.gz'
    with pytest.raises(ValueError,match='missing vertex'):geometry.write(path,[[0,0,0]],[],[[[0,1,2]]])
    path.write_bytes(gzip.compress(geometry.HEADER.pack(b'RMS1',1,0,0,0)))
    with pytest.raises(ValueError,match='payload'):geometry.read(path)


def test_mesh_buffer_rejects_invalid_slot_counts(tmp_path):
    path=tmp_path/'bad.gz'
    path.write_bytes(gzip.compress(geometry.HEADER.pack(b'RMS1',0,0,1,1)+struct.pack('<I',2)))
    with pytest.raises(ValueError,match='triangle counts'):geometry.read(path)


def test_bounds_read_only_coordinate_chunks_without_uv_or_triangles(tmp_path):
    path=tmp_path/'mesh.gz'
    points=np.tile([[1,2,3],[-4,-5,9]],(20000,1)).astype('<f4')
    # Deliberately omit the unused UV/index payload: metadata needs only vertices.
    path.write_bytes(gzip.compress(geometry.HEADER.pack(b'RMS1',len(points),len(points),1,1)+
                                  struct.pack('<I',1)+points.tobytes()))
    assert geometry.bounds(path)==([-4,-5,3],[1,2,9])
    with pytest.raises(ValueError,match='payload'):geometry.read(path)


def test_bounds_reject_truncated_nonfinite_and_oversized_coordinates(tmp_path):
    path=tmp_path/'mesh.gz'
    for points in (b'',struct.pack('<fff',float('nan'),0,0)):
        path.write_bytes(gzip.compress(geometry.HEADER.pack(b'RMS1',1,0,0,0)+points))
        with pytest.raises(ValueError):geometry.bounds(path)
    path.write_bytes(gzip.compress(geometry.HEADER.pack(b'RMS1',100000000,0,0,0)))
    with pytest.raises(ValueError,match='oversized'):geometry.bounds(path)
