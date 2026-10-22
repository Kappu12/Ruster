"""Synthetic SDK-shaped world; no game assets or proprietary maps."""
import math
import struct
from ruster.core import wire
from ruster.core.rust_map import RustMap


def sample_world(version=10):
    n, size = 33, 1000
    height = bytearray()
    for z in range(n):
        for x in range(n):
            h = 40 + 75 * math.exp(-((x-16)**2 + (z-16)**2)/70)
            height += struct.pack('<h', int((h+500)/1000*32766))
    layers = {'terrain': bytes(height), 'water': struct.pack('<h', 16383)*n*n,
              'splat': b'\0'*(32*32*4) + b'\xff'*(32*32) + b'\0'*(32*32*3),
              'biome': b'\0'*1024 + b'\xff'*1024 + b'\0'*2048,
              'topology': b'\x01\0\0\0'*1024, 'alpha': b'\xff'*1024}
    fields = [wire.encode(1,0,size)]
    for name, data in layers.items():
        fields.append(wire.encode(2,2,wire.serialize([
            wire.encode(1,2,name.encode()), wire.encode(2,2,data)])))
    for uid, position in ((123456, (0,116,0)), (234567,(120,70,20))):
        prefab = [wire.encode(1,2,b'Decor'),wire.encode(2,0,uid),
                  wire.encode(3,2,wire.set_vector(None,position)),
                  wire.encode(4,2,wire.set_vector(None,(0,90,0))),
                  wire.encode(5,2,wire.set_vector(None,(1,1,1))),
                  wire.encode(47,2,b'unknown prefab extension')]
        fields.append(wire.encode(3,2,wire.serialize(prefab)))
    path = [wire.encode(1,2,b'Road'), wire.encode(5,5,struct.pack('<f',8.))]
    path.extend(wire.encode(15,2,wire.set_vector(None,p)) for p in [(-200,60,-150),(0,115,0),(200,60,150)])
    fields.append(wire.encode(4,2,wire.serialize(path)))
    fields.append(wire.encode(99,2,b'unknown world extension'))
    return RustMap(version,struct.pack('<q',123456789) if version==10 else b'',fields)
