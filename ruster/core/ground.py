"""Native Rust terrain patches, independent of the editable Blender preview mesh."""
import math
import numpy as np
from .terrain import Terrain, empty_world, BIOMES, SPLATS
from .wire import FormatError


def flat_ground(size=512., height=0., biome='Temperate', splat='Grass', world_size=1000):
    if (isinstance(size,bool) or not isinstance(size,(int,float)) or not math.isfinite(size)
            or not 16 <= size <= 2000):
        raise FormatError('Ground size must be 16–2,000 metres')
    if type(world_size) is not int or not 1000 <= world_size <= 2000 or size > world_size:
        raise FormatError('World size must be 1,000–2,000 metres and contain the ground patch')
    if isinstance(height,bool) or not isinstance(height,(int,float)) or not math.isfinite(height) or not -500 <= height <= 500:
        raise FormatError('Ground height must be −500–500 metres')
    if biome not in BIOMES or splat not in SPLATS:
        raise FormatError('Choose a supported Rust biome and splat')
    world=empty_world(world_size,height)
    doc=Terrain(world)
    n=doc.grid('alpha').shape[-1]
    axis=np.linspace(-world_size/2,world_size/2,n)
    inside=(np.abs(axis[:,None])<=size/2)&(np.abs(axis[None,:])<=size/2)
    alpha=np.where(inside,255,0).astype('u1')
    ground=np.zeros((8,n,n),dtype='u1');ground[SPLATS.index(splat)]=255
    # Current Rust maps store five planar channels, including explicit Jungle.
    # RGBA biome textures use an implicit remainder, but map bytes do not.
    biomes=np.zeros((5,n,n),dtype='u1');biomes[BIOMES.index(biome)]=255
    topology=np.zeros((n,n),dtype='<u4')
    topology[inside]=(1<<0)|(1<<5)|(1<<24)|(1<<26)|(1<<29)
    world.set_layer('splat',ground.tobytes())
    world.set_layer('biome',biomes.tobytes())
    world.set_layer('alpha',alpha.tobytes())
    world.set_layer('topology',topology.tobytes())
    world.set_layer('water',np.zeros_like(doc.grid('water')).tobytes())
    return world


def validate_ground(world):
    """Check native channel counts, resolutions, weights and finite height data."""
    doc=Terrain(world)
    if not 1000<=world.size<=6000:raise FormatError('Unsupported ground world size')
    n=2**math.ceil(math.log2(world.size*.5))
    for name in ('terrain','height','water'):
        if doc.grid(name).shape!=(1,n+1,n+1):raise FormatError(f'Invalid native {name} resolution')
        if np.any(doc.grid(name)<0) or np.any(doc.grid(name)>32766):raise FormatError(f'Invalid native {name} samples')
    for name,channels in (('splat',8),('alpha',1),('topology',1)):
        if doc.grid(name).shape!=(channels,n,n):raise FormatError(f'Invalid native {name} layout')
    if doc.grid('biome').shape not in ((4,n,n),(5,n,n)):raise FormatError('Invalid native biome layout')
    if not np.all(doc.grid('splat').sum(axis=0,dtype=np.int32)==255):raise FormatError('Splat weights must sum to 255')
    if np.any(doc.grid('biome').sum(axis=0,dtype=np.int32)>255):raise FormatError('Biome weights exceed 255')
    if len(doc.grid('biome'))==5 and not np.all(doc.grid('biome').sum(axis=0,dtype=np.int32)==255):
        raise FormatError('Native biome weights must sum to 255')
    if not np.all(np.isin(doc.grid('alpha'),[0,255])):raise FormatError('Invalid terrain alpha mask')
    return doc


def native_world(world):
    """Upgrade a legacy RGBA biome map for current Rust without editing its source."""
    doc=validate_ground(world)
    if len(doc.grid('biome'))==5:return world
    from .rust_map import RustMap
    result=RustMap(world.version,world.timestamp,list(world.fields))
    result.set_layer('biome',doc.biome_weights().tobytes())
    validate_ground(result)
    return result
