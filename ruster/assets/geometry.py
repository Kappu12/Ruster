"""Small binary mesh cache: convert/load one mesh at a time, never a world."""
import gzip
import os
from pathlib import Path
import struct
import tempfile

HEADER=struct.Struct('<4sIIII')
MAX_BYTES=128*1024*1024


def _header(stream):
    raw=stream.read(HEADER.size)
    if len(raw)!=HEADER.size:raise ValueError('Truncated mesh cache header')
    magic,vertices,uv,faces,slots=HEADER.unpack(raw)
    size=vertices*12+uv*8+faces*12+slots*4
    if magic!=b'RMS1' or size>MAX_BYTES or slots>65536 or uv not in (0,vertices):
        raise ValueError('Invalid or oversized mesh cache')
    raw=stream.read(slots*4)
    if len(raw)!=slots*4:raise ValueError('Truncated mesh material slots')
    counts=struct.unpack('<'+'I'*slots,raw)
    if sum(counts)!=faces:raise ValueError('Invalid mesh triangle counts')
    return vertices,uv,faces,counts


def info(path):
    with gzip.open(path,'rb') as stream:
        vertices,uv,faces,counts=_header(stream)
    return {'vertices':vertices,'uv_count':uv,'faces':faces,'submesh_counts':list(counts)}


def bounds(path):
    """Read only vertex coordinates in small chunks for model metadata queries."""
    import numpy as np
    low=high=None
    with gzip.open(path,'rb') as stream:
        vertices,_,_,_=_header(stream)
        for start in range(0,vertices,16384):
            length=min(16384,vertices-start)*12
            data=stream.read(length)
            if len(data)!=length:raise ValueError('Truncated mesh coordinate payload')
            points=np.frombuffer(data,dtype='<f4').reshape(-1,3)
            if not np.isfinite(points).all():raise ValueError('Mesh contains nonfinite coordinates')
            lo,hi=points.min(axis=0),points.max(axis=0)
            low=lo if low is None else np.minimum(low,lo)
            high=hi if high is None else np.maximum(high,hi)
    return None if low is None else (low.tolist(),high.tolist())


def write(path,vertices,uv,submeshes):
    import numpy as np
    vertices=np.asarray(vertices,dtype='<f4').reshape(-1,3)
    uv=np.asarray(uv,dtype='<f4')
    uv=uv[:,:2] if uv.size and uv.ndim==2 and len(uv)==len(vertices) else np.empty((0,2),dtype='<f4')
    parts=[np.asarray(part,dtype='<u4').reshape(-1,3) for part in submeshes]
    counts=[len(part) for part in parts];faces=sum(counts)
    if vertices.nbytes+uv.nbytes+faces*12+len(counts)*4>MAX_BYTES:raise ValueError('Mesh exceeds the per-mesh cache limit')
    if not np.isfinite(vertices).all() or not np.isfinite(uv).all():raise ValueError('Mesh contains nonfinite coordinates')
    if any(part.size and part.max()>=len(vertices) for part in parts):raise ValueError('Mesh triangle references a missing vertex')
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    descriptor,temporary=tempfile.mkstemp(prefix='.mesh-',dir=path.parent);os.close(descriptor)
    try:
        with gzip.open(temporary,'wb',compresslevel=1) as stream:
            stream.write(HEADER.pack(b'RMS1',len(vertices),len(uv),faces,len(counts)))
            stream.write(struct.pack('<'+'I'*len(counts),*counts))
            stream.write(vertices.tobytes());stream.write(uv.tobytes())
            for part in parts:stream.write(part.tobytes())
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)
    return {'vertices':len(vertices),'uv_count':len(uv),'faces':faces,'submesh_counts':counts}


def read(path):
    import numpy as np
    with gzip.open(path,'rb') as stream:
        vertices,uv,faces,counts=_header(stream)
        length=vertices*12+uv*8+faces*12
        data=stream.read(length+1)
    if len(data)!=length:raise ValueError('Truncated or oversized mesh cache payload')
    points=np.frombuffer(data,dtype='<f4',count=vertices*3).reshape(-1,3)
    coords=np.frombuffer(data,dtype='<f4',count=uv*2,offset=vertices*12).reshape(-1,2)
    indices=np.frombuffer(data,dtype='<u4',count=faces*3,offset=vertices*12+uv*8).reshape(-1,3)
    if not np.isfinite(points).all() or not np.isfinite(coords).all():raise ValueError('Mesh contains nonfinite coordinates')
    if indices.size and indices.max()>=vertices:raise ValueError('Mesh triangle references a missing vertex')
    return points,coords,indices,counts
