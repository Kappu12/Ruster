"""Compact Unity 22 object metadata, with ObjectReaders created on demand.

The pinned UnityPy parser ordinarily allocates a Python object for every entry
in a CAB, including hundreds of thousands of unrelated meshes and textures.
Keep its native type trees/pointer API but store the fixed-size table as bytes.
"""
from collections import OrderedDict
from collections.abc import Mapping


class ObjectTable(Mapping):
    def __init__(self,file,data,count):
        import numpy as np
        self.file=file
        self.rows=np.frombuffer(data,dtype=np.dtype([(name,file.reader.endian+kind)
            for name,kind in [('id','i8'),('start','i8'),('size','u4'),('type','i4')]]),count=count)
        self.ids=self.rows['id']
        self.order=None if bool(np.all(self.ids[:-1]<=self.ids[1:])) else np.argsort(self.ids)
        self.sorted_ids=np.ascontiguousarray(self.ids if self.order is None else self.ids[self.order])
        self.cache=OrderedDict()

    def __len__(self):return len(self.rows)
    def __iter__(self):return (int(value) for value in self.ids)

    def _object(self,index):
        from UnityPy.files.ObjectReader import ObjectReader
        from UnityPy.enums import ClassIDType
        row=self.rows[index];path_id=int(row['id'])
        if path_id in self.cache:return self.cache[path_id]
        type_id=int(row['type']);typ=self.file.types[type_id]
        result=ObjectReader(self.file,self.file.reader,path_id,type_id,typ,typ.class_id,
            ClassIDType(typ.class_id),int(row['start'])+self.file.header.data_offset,int(row['size']),None,None)
        self.cache[path_id]=result
        if len(self.cache)>256:self.cache.popitem(last=False)
        return result

    def __getitem__(self,path_id):
        import numpy as np
        if path_id in self.cache:return self.cache[path_id]
        index=int(np.searchsorted(self.sorted_ids,path_id))
        if index>=len(self.rows) or self.sorted_ids[index]!=path_id:raise KeyError(path_id)
        return self._object(index if self.order is None else int(self.order[index]))

    def values(self):return (self._object(index) for index in range(len(self.rows)))

    def of_type(self,name):
        import numpy as np
        from UnityPy.enums import ClassIDType
        types=[index for index,typ in enumerate(self.file.types) if ClassIDType(typ.class_id).name==name]
        return (self._object(int(index)) for index in np.flatnonzero(np.isin(self.rows['type'],types)))


def parse(file,reader,parent,name,original,kwargs):
    """Unity serialized version 22; other formats retain the pinned parser."""
    from UnityPy import config
    from UnityPy.files.File import File
    from UnityPy.files.SerializedFile import (SerializedFileHeader,SerializedType,FileIdentifier,
        LocalSerializedObjectIdentifier)
    from UnityPy.enums import BuildTarget
    from UnityPy.helpers.ContainerHelper import ContainerHelper
    reader.Position=0
    header=SerializedFileHeader(reader)
    if header.version!=22:
        reader.Position=0
        return original(file,reader,parent=parent,name=name,**kwargs)
    File.__init__(file,parent=parent,name=name,**kwargs)
    file.reader=reader;file.header=header;file._cache={}
    header.endian='>' if reader.read_boolean() else '<'
    header.reserved=reader.read_bytes(3)
    header.metadata_size=reader.read_u_int();header.file_size=reader.read_long()
    header.data_offset=reader.read_long();file.unknown=reader.read_long()
    reader.endian=header.endian
    file.set_version(reader.read_string_to_null())
    file._m_target_platform=reader.read_int();file.target_platform=BuildTarget(file._m_target_platform)
    file._enable_type_tree=reader.read_boolean()
    type_count=reader.read_int()
    if not 0<=type_count<=65536:raise ValueError('Invalid serialized type count')
    file.types=[SerializedType(reader,file,False) for _ in range(type_count)]
    file.big_id_enabled=0
    count=reader.read_int();reader.align_stream()
    if not 0<=count<=2000000:raise ValueError('Invalid serialized object count')
    length=count*24
    parts=[]
    while length:
        size=min(length,16*1024*1024);parts.append(reader.read_bytes(size));length-=size
    data=b''.join(parts)
    if len(data)!=count*24:raise ValueError('Truncated serialized object table')
    file.objects=ObjectTable(file,data,count)
    scripts=reader.read_int()
    if not 0<=scripts<=2000000:raise ValueError('Invalid script count')
    file.script_types=[LocalSerializedObjectIdentifier(header,reader) for _ in range(scripts)]
    externals=reader.read_int()
    if not 0<=externals<=65536:raise ValueError('Invalid external file count')
    file.externals=[FileIdentifier(header,reader) for _ in range(externals)]
    refs=reader.read_int()
    if not 0<=refs<=65536:raise ValueError('Invalid reference type count')
    file.ref_types=[SerializedType(reader,file,True) for _ in range(refs)]
    if config.SERIALIZED_FILE_PARSE_TYPETREE is False:file._enable_type_tree=False
    file.userInformation=reader.read_string_to_null()
    # Extraction resolves requested paths itself; never expand the preload table.
    file.assetbundle=None;file._container=ContainerHelper([])
