"""Lossless Rust path records and curve sampling."""
import math
import struct
import numpy as np
from . import wire
from .wire import FormatError

FLOATS = {'width':5,'inner_padding':6,'outer_padding':7,'inner_fade':8,
          'outer_fade':9,'random_scale':10,'mesh_offset':11,'terrain_offset':12}
INTS = {'splat':13,'topology':14}
BOOLS = {'spline':2,'start':3,'end':4}


def read(fields):
    result={'name':wire.get(fields,1,b'Road').decode('utf8',errors='replace'),
            'nodes':[wire.vector(f.value) for f in fields if f.number==15 and f.wire==2]}
    result.update({k:struct.unpack('<f',wire.get(fields,i,struct.pack('<f',8. if k=='width' else 0.)))[0]
                   for k,i in FLOATS.items()})
    result.update({k:wire.get(fields,i,0) for k,i in INTS.items()})
    result.update({k:bool(wire.get(fields,i,0)) for k,i in BOOLS.items()})
    return result


def update(fields, values):
    result=list(fields)
    before=read(fields)
    for name,index in FLOATS.items():
        if name in values and not math.isclose(float(values[name]),before[name],abs_tol=1e-6,rel_tol=1e-6):
            value=float(values[name])
            if not math.isfinite(value) or (name=='width' and value<=0):
                raise FormatError(f'Invalid path {name}')
            result=wire.replace(result,index,5,struct.pack('<f',value))
    for name,index in INTS.items():
        if name in values and int(values[name])!=before[name]:
            if not 0<=int(values[name])<=0xFFFFFFFF:
                raise FormatError(f'Invalid path {name}')
            result=wire.replace(result,index,0,int(values[name]))
    for name,index in BOOLS.items():
        if name in values and bool(values[name])!=before[name]:
            result=wire.replace(result,index,0,int(bool(values[name])))
    if 'name' in values and values['name']!=before['name']:
        result=wire.replace(result,1,2,values['name'].encode())
    if 'nodes' in values:
        nodes=values['nodes']
        if len(nodes)<2 or len(nodes)>100000 or not all(len(n)==3 and all(math.isfinite(v) for v in n) for n in nodes):
            raise FormatError('Paths require 2–100,000 finite 3D nodes')
        same=(len(nodes)==len(before['nodes']) and
              np.allclose(nodes,before['nodes'],rtol=0,atol=1e-5))
        if not same:
            # Reuse node metadata by index when their point coordinates change.
            old=[f.value for f in result if f.number==15 and f.wire==2]
            points=[wire.encode(15,2,wire.set_vector(old[i] if i<len(old) else None,n)) for i,n in enumerate(nodes)]
            position=next((i for i,f in enumerate(result) if f.number==15),len(result))
            result=[f for f in result if f.number!=15]
            result[position:position]=points
    return result


def sample_polyline(nodes, spacing=2.):
    nodes=np.asarray(nodes,dtype=float)
    if nodes.ndim!=2 or nodes.shape[1]!=3 or len(nodes)<2 or spacing<=0:
        raise FormatError('Invalid path sampling input')
    output=[]
    for a,b in zip(nodes[:-1],nodes[1:]):
        length=np.linalg.norm(b-a)
        count=max(1,int(math.ceil(length/spacing)))
        if len(output)+count>100000:
            raise FormatError('Path needs too many samples; increase spacing')
        output.extend((a+(b-a)*t).tolist() for t in np.linspace(0,1,count,endpoint=False))
    output.append(nodes[-1].tolist())
    return output
