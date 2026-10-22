import struct
from types import SimpleNamespace as S
import pytest
from UnityPy.files.SerializedFile import SerializedFile
from UnityPy.streams import EndianBinaryReader
from ruster.assets.streaming import streamed_bundles
from ruster.assets.serialized import ObjectTable


def serialized_fixture():
    meta=bytearray(b'2022.3.1f1\0'+struct.pack('<i?i',19,False,1))
    meta+=struct.pack('<i?h',43,False,-1)+bytes(16)  # Mesh type, no embedded type tree.
    meta+=struct.pack('<i',2)
    meta+=bytes((-len(meta))%4)
    meta+=struct.pack('<qqIi',-40,0,4,0)+struct.pack('<qqIi',90,4,4,0)
    meta+=struct.pack('<iii',0,0,0)+b'\0'
    start=48+len(meta)
    return struct.pack('>IIII',0,0,22,0)+bytes(4)+struct.pack('>Iqqq',len(meta),start+8,start,0)+meta+b'12345678'


def test_compact_table_matches_pinned_parser_and_restores_hook():
    raw=serialized_fixture()
    original=SerializedFile.__init__
    native=SerializedFile(EndianBinaryReader(raw),name='fixture')
    with streamed_bundles(skip_containers=True):
        compact=SerializedFile(EndianBinaryReader(raw),name='fixture')
        assert isinstance(compact.objects,ObjectTable)
        assert list(compact.objects)==list(native.objects)
        for key in native.objects:
            for field in ('path_id','type_id','class_id','byte_start','byte_size'):
                assert getattr(compact.objects[key],field)==getattr(native.objects[key],field)
            assert compact.objects[key].get_raw_data()==native.objects[key].get_raw_data()
        assert [obj.path_id for obj in compact.objects.of_type('Mesh')]==[-40,90]
        assert not list(compact.objects.of_type('GameObject'))
    assert SerializedFile.__init__ is original


def test_compact_table_handles_unsorted_ids_and_keeps_a_bounded_reader_cache():
    import numpy as np
    dtype=np.dtype([('id','<i8'),('start','<i8'),('size','<u4'),('type','<i4')])
    records=np.zeros(1024,dtype=dtype);records['id']=np.arange(1024)[::-1]
    file=S(reader=S(endian='<'),types=[S(class_id=43)],header=S(data_offset=100))
    table=ObjectTable(file,records.tobytes(),len(records))
    for index in range(1024):assert table[index].path_id==index
    assert len(table.cache)<=256
    with pytest.raises(KeyError):table[2000]
