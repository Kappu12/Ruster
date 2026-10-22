"""Full-resolution Rust terrain editing, independent of Blender's preview mesh.

Arrays use Rust's planar [channel,z,x] layout. Every brush works in world metres.
Unmodified layers are kept byte-for-byte; weight painting sums to exactly 255.
"""
import base64
import math
import struct
import time
import zlib
import numpy as np
from . import wire
from .rust_map import RustMap
from .wire import FormatError

SPLATS = ('Dirt','Snow','Sand','Rock','Grass','Forest','Stones','Gravel')
BIOMES = ('Arid','Temperate','Tundra','Arctic','Jungle')
TOPOLOGIES = ('Field','Cliff','Summit','Beachside','Beach','Forest','Forestside',
              'Ocean','Oceanside','Decor','Monument','Road','Roadside','Swamp',
              'River','Riverside','Lake','Lakeside','Offshore','Powerline','Runway',
              'Building','Cliffside','Mountain','Clutter','Alt','Tier0','Tier1',
              'Tier2','Mainland','Hilltop')


def decode_grid(raw, dtype, channels=1):
    dtype = np.dtype(dtype)
    n = math.isqrt(len(raw) // (dtype.itemsize * channels))
    if n < 2 or n*n*channels*dtype.itemsize != len(raw):
        raise FormatError('Layer dimensions or channel count are unsupported')
    return np.frombuffer(raw, dtype=dtype).reshape(channels,n,n).copy()


def normalize_weights(values):
    """Largest remainder normalization: exact sum, stable and unbiased ties."""
    values = np.maximum(np.asarray(values, dtype=np.float64), 0)
    total = values.sum(axis=0, keepdims=True)
    empty = total[0] == 0
    if np.any(empty):
        values[0,empty] = 1
        total = values.sum(axis=0, keepdims=True)
    scaled = values / total * 255
    whole = np.floor(scaled).astype(np.uint8)
    remainder = 255-whole.sum(axis=0, dtype=np.int16)
    order = np.argsort(-(scaled-whole), axis=0, kind='stable')
    for rank in range(values.shape[0]):
        extra = remainder > rank
        if np.any(extra):
            yy,xx = np.nonzero(extra)
            whole[order[rank,yy,xx],yy,xx] += 1
    return whole


def resample(array, x, z):
    """Bilinear sampling in pixel coordinates, clamped to the source extent."""
    h,w = array.shape[-2:]
    x = np.clip(x,0,w-1)
    z = np.clip(z,0,h-1)
    x0,z0 = np.floor(x).astype(int),np.floor(z).astype(int)
    x1,z1 = np.minimum(x0+1,w-1),np.minimum(z0+1,h-1)
    tx,tz = x-x0,z-z0
    return ((1-tx)*(1-tz)*array[...,z0,x0] + tx*(1-tz)*array[...,z0,x1] +
            (1-tx)*tz*array[...,z1,x0] + tx*tz*array[...,z1,x1])


class Terrain:
    def __init__(self, world, edits=None):
        self.world = world
        self.base_layers = world.layers
        self.edits = dict(edits or {})
        self._arrays = {}

    @property
    def size(self):
        return self.world.size

    def resolve(self, name):
        if name == 'splat' and 'ground' in self.base_layers:
            return 'ground'
        return name

    def raw(self, name):
        name = self.resolve(name)
        if name in self._arrays:
            return self._arrays[name].tobytes()
        if name in self.edits:
            return self.edits[name]
        raw = self.base_layers.get(name)
        if raw is None:
            raise FormatError(f'Map has no {name} layer')
        return raw

    def grid(self, name):
        name = self.resolve(name)
        if name not in self._arrays:
            raw = self.raw(name)
            channels = 1
            dtype = '<i2' if name in ('terrain','height','water') else ('<u4' if name=='topology' else 'u1')
            if name in ('ground','splat'):
                channels = 8
            elif name == 'biome':
                options = [c for c in (5,4) if math.isqrt(len(raw)//c)**2*c == len(raw)]
                if len(options) != 1:
                    raise FormatError('Unrecognized biome channel layout')
                channels = options[0]
            self._arrays[name] = decode_grid(raw,dtype,channels)
        return self._arrays[name]

    def heights(self, layer='terrain'):
        return self.grid(layer)[0].astype(np.float64)/32766*1000-500

    def sample_height(self, x, z):
        heights = self.grid('terrain')[0]
        n = heights.shape[0]
        return resample(heights,(np.asarray(x)/self.size+.5)*(n-1),
                        (np.asarray(z)/self.size+.5)*(n-1))/32766*1000-500

    def ray_intersect(self,origin,direction):
        """Intersect the height surface even where an alpha hole hides its mesh.

        Coordinates are editor-space (x, map-z, height), matching Blender.
        """
        origin,direction=np.asarray(origin,dtype=float),np.asarray(direction,dtype=float)
        if origin.shape!=(3,) or direction.shape!=(3,) or not np.isfinite([origin,direction]).all():
            raise FormatError('Invalid terrain ray')
        low=np.array([-self.size/2,-self.size/2,-500.])
        high=np.array([self.size/2,self.size/2,500.])
        near,far=0.,math.inf
        for i in range(3):
            if abs(direction[i])<1e-12:
                if origin[i]<low[i] or origin[i]>high[i]:return None
            else:
                a,b=(low[i]-origin[i])/direction[i],(high[i]-origin[i])/direction[i]
                near=max(near,min(a,b));far=min(far,max(a,b))
        if not math.isfinite(far) or far<near:return None
        t=np.linspace(near,far,257)
        points=origin[None,:]+t[:,None]*direction[None,:]
        difference=points[:,2]-self.sample_height(points[:,0],points[:,1])
        crossing=np.flatnonzero(difference[:-1]*difference[1:]<=0)
        if not len(crossing):return None
        index=int(crossing[0]);a,b=t[index],t[index+1];value=difference[index]
        for _ in range(20):
            middle=(a+b)/2;point=origin+middle*direction
            delta=point[2]-float(self.sample_height(point[0],point[1]))
            if delta*value>0:a=middle;value=delta
            else:b=middle
        return origin+(a+b)/2*direction

    def changed(self, name):
        name = self.resolve(name)
        self.edits[name] = self._arrays[name].tobytes()

    def region(self, n, x, z, radius, falloff=0.6, shape='CIRCLE'):
        if not all(math.isfinite(v) for v in (x,z,radius,falloff)) or radius <= 0:
            raise FormatError('Brush position and radius must be finite; radius must be positive')
        step = self.size/(n-1)
        x0=max(0,math.floor((x-radius+self.size/2)/step))
        x1=min(n,math.ceil((x+radius+self.size/2)/step)+1)
        z0=max(0,math.floor((z-radius+self.size/2)/step))
        z1=min(n,math.ceil((z+radius+self.size/2)/step)+1)
        if x0>=x1 or z0>=z1:
            return None
        xx,zz=np.meshgrid(np.arange(x0,x1)*step-self.size/2,
                          np.arange(z0,z1)*step-self.size/2)
        distance = np.maximum(abs(xx-x),abs(zz-z)) if shape=='SQUARE' else np.hypot(xx-x,zz-z)
        t=np.clip((1-distance/radius)/max(falloff,1e-6),0,1)
        weight=t*t*(3-2*t)
        return (slice(z0,z1),slice(x0,x1)),weight,xx,zz

    def brush(self, tool, x, z, radius, strength=.3, height=0., channel=0,
              layer='terrain', falloff=.6, shape='CIRCLE', invert=False,
              minimum=-500., maximum=500., min_slope=0., max_slope=90., seed=0,
              source=None, terrace=5., stamp=None, rotation=0., slope=0.):
        name = self.resolve(layer)
        grid = self.grid(name)
        region = self.region(grid.shape[-1],x,z,radius,falloff,shape)
        if region is None:
            return False
        slices,weight,xx,zz = region
        strength=float(np.clip(strength,0,1))
        if min_slope>0 or max_slope<90 or minimum>-500 or maximum<500:
            terrain_heights=self.grid('terrain')[0]
            n=terrain_heights.shape[0]
            gx=(xx/self.size+.5)*(n-1);gz=(zz/self.size+.5)*(n-1)
            sampled=resample(terrain_heights,gx,gz)/32766*1000-500
            valid=(sampled>=minimum)&(sampled<=maximum)
            if min_slope>0 or max_slope<90:
                step=self.size/(n-1)
                dx=(resample(terrain_heights,gx+1,gz)-resample(terrain_heights,gx-1,gz))/32766*1000/(2*step)
                dy=(resample(terrain_heights,gx,gz+1)-resample(terrain_heights,gx,gz-1))/32766*1000/(2*step)
                slopes=np.degrees(np.arctan(np.hypot(dx,dy)))
                valid &= (slopes>=min_slope)&(slopes<=max_slope)
            weight *= valid
        if not np.any(weight):
            return False
        if name in ('terrain','height','water'):
            before=grid[0][slices].astype(np.float64)/32766*1000-500
            if tool in ('RAISE','LOWER'):
                direction=(-1 if tool=='LOWER' else 1)*(-1 if invert else 1)
                after=before+weight*strength*10*direction
            elif tool=='FLATTEN':
                after=before+(height-before)*weight*strength
            elif tool in ('SMOOTH','ERODE','SHARPEN'):
                zslice,xslice=slices
                n=grid.shape[-1]
                iz=np.clip(np.arange(zslice.start-1,zslice.stop+1),0,n-1)
                ix=np.clip(np.arange(xslice.start-1,xslice.stop+1),0,n-1)
                padded=grid[0][np.ix_(iz,ix)].astype(np.float64)/32766*1000-500
                total=np.zeros_like(before)
                for dz in range(3):
                    for dx in range(3):
                        total += padded[dz:dz+before.shape[0],dx:dx+before.shape[1]]
                target=total/9
                if tool=='ERODE':
                    target=np.minimum(target,before)
                after=before+(before-target if tool=='SHARPEN' else target-before)*weight*strength
            elif tool=='TERRACE':
                if terrace<=0:
                    raise FormatError('Terrace step must be positive')
                target=np.round(before/terrace)*terrace
                after=before+(target-before)*weight*strength
            elif tool=='NOISE':
                # Stable in world space; brush spacing does not change the noise pattern.
                noise=(np.sin(xx*12.9898+zz*78.233+seed*37.719)*43758.5453)%1*2-1
                after=before+noise*weight*strength*10
            elif tool=='CLONE':
                if source is None:
                    raise FormatError('Set a clone source first')
                n=grid.shape[-1]
                target=resample(grid[0],((xx-x+source[0])/self.size+.5)*(n-1),
                                ((zz-z+source[1])/self.size+.5)*(n-1))/32766*1000-500
                after=before+(target-before)*weight*strength
            elif tool in ('PINCH','TWIST'):
                rx,rz=xx-x,zz-z
                amount=weight*strength*(-1 if invert else 1)
                if tool=='PINCH':
                    rx=rx*(1+amount*.5);rz=rz*(1+amount*.5)
                else:
                    angle=amount*math.pi/4
                    rx,rz=rx*np.cos(angle)-rz*np.sin(angle),rx*np.sin(angle)+rz*np.cos(angle)
                n=grid.shape[-1]
                after=resample(grid[0],((rx+x)/self.size+.5)*(n-1),((rz+z)/self.size+.5)*(n-1))/32766*1000-500
            elif tool=='SLOPE':
                heading=math.radians(rotation)
                target=height+((xx-x)*math.cos(heading)+(zz-z)*math.sin(heading))*math.tan(math.radians(slope))
                after=before+(target-before)*weight*strength
            elif tool=='STAMP':
                if stamp is None or np.asarray(stamp).ndim!=2:
                    raise FormatError('Choose a grayscale stamp image first')
                stamp=np.asarray(stamp,dtype=float)
                angle=math.radians(rotation)
                rx,rz=(xx-x)/radius,(zz-z)/radius
                sx=rx*math.cos(angle)-rz*math.sin(angle)
                sz=rx*math.sin(angle)+rz*math.cos(angle)
                sample=resample(stamp,(sx*.5+.5)*(stamp.shape[1]-1),(sz*.5+.5)*(stamp.shape[0]-1))
                after=before+sample*height*weight*strength*(-1 if invert else 1)
            else:
                raise FormatError(f'Unsupported height tool: {tool}')
            grid[0][slices]=np.rint((np.clip(after,-500,500)+500)/1000*32766).astype('<i2')
            # Keep the derived spawn-height surface in step while preserving prefab relief.
            if name=='terrain' and 'height' in self.base_layers:
                height_grid=self.grid('height')
                if height_grid.shape==grid.shape:
                    delta=grid[0][slices].astype(np.int32)-np.rint((before+500)/1000*32766).astype(np.int32)
                    height_grid[0][slices]=np.clip(height_grid[0][slices].astype(np.int32)+delta,0,32766)
                    self.changed('height')
        elif name in ('ground','splat','biome'):
            if not 0<=channel<grid.shape[0]:
                raise FormatError('This map does not contain the selected paint channel')
            values=grid[(slice(None),)+slices].astype(np.float64)
            opacity=weight*strength
            if invert:
                values[channel] *= 1-opacity
            else:
                values *= 1-opacity
                values[channel] += 255*opacity
            grid[(slice(None),)+slices]=normalize_weights(values)
        elif name=='topology':
            if not 0<=channel<=31:
                raise FormatError('Invalid topology bit')
            active=(weight>=.5)&(strength>0)
            part=grid[0][slices]
            bit=np.uint32(1<<channel)
            if invert:
                part[active] &= ~bit
            else:
                part[active] |= bit
        elif name=='alpha':
            part=grid[0][slices]
            part[(weight>=.5)&(strength>0)]=0 if invert else 255
        else:
            raise FormatError(f'Layer is not editable: {name}')
        self.changed(name)
        return True

    def generate_island(self,seed=1,amplitude=160.,frequency=4,octaves=5):
        if not 1<=frequency<=32 or not 1<=octaves<=8 or not 0<=amplitude<=500:
            raise FormatError('Invalid terrain generator settings')
        grid=self.grid('terrain')
        n=grid.shape[-1]
        rng=np.random.default_rng(seed)
        terrain=np.zeros((n,n),dtype=np.float64)
        norm=0.
        # Work in strips so large maps do not need many full-size scratch arrays.
        for octave in range(octaves):
            count=frequency*2**octave+1
            lattice=rng.uniform(-1,1,(count,count))
            amplitude_=2.**(-octave)
            x=np.linspace(0,count-1,n)[None,:]
            for start in range(0,n,128):
                end=min(n,start+128)
                z=np.linspace(0,count-1,n)[start:end,None]
                terrain[start:end]+=resample(lattice,x,z)*amplitude_
            norm+=amplitude_
        axis=np.linspace(-1,1,n)
        for start in range(0,n,128):
            end=min(n,start+128)
            radial=np.hypot(axis[None,:],axis[start:end,None])
            mask=np.clip((1-radial)/.4,0,1)
            mask=mask*mask*(3-2*mask)
            terrain[start:end]=-100+mask*(140+terrain[start:end]/norm*amplitude)
        before=grid[0].astype(np.int32)
        grid[0]=np.rint((np.clip(terrain,-500,500)+500)/1000*32766).astype('<i2')
        self.changed('terrain')
        if 'height' in self.base_layers:
            derived=self.grid('height')
            if derived.shape==grid.shape:
                derived[0]=np.clip(derived[0].astype(np.int32)+grid[0].astype(np.int32)-before,0,32766)
                self.changed('height')

    def bridge(self, start, end, width, strength=1.):
        """Grade a strip between two world-space (x,z,height) points."""
        start,end=np.asarray(start,dtype=float),np.asarray(end,dtype=float)
        delta=end[:2]-start[:2]
        length=float(np.linalg.norm(delta))
        if length<1e-6 or width<=0:
            raise FormatError('Bridge endpoints must differ and width must be positive')
        count=max(2,int(math.ceil(length/max(width*.25,self.size/(self.grid('terrain').shape[-1]-1)))))
        if count>10000:
            raise FormatError('Bridge has too many samples; increase its width')
        for t in np.linspace(0,1,count):
            point=start+(end-start)*t
            self.brush('FLATTEN',point[0],point[1],width/2,strength=strength,height=point[2])

    def export_world(self):
        world=RustMap(self.world.version,self.world.timestamp,list(self.world.fields))
        for name in self.edits:
            world.set_layer(name,self.raw(name))
        return world

    def snapshot(self):
        fields=[]
        for name in sorted(self.edits):
            fields.append(wire.encode(1,2,wire.serialize([
                wire.encode(1,2,name.encode()),wire.encode(2,2,self.raw(name))])))
        return base64.b85encode(zlib.compress(wire.serialize(fields),3)).decode('ascii')

    @classmethod
    def restore(cls,world,text):
        try:
            compressed=base64.b85decode(text.encode('ascii'))
            decoder=zlib.decompressobj()
            data=decoder.decompress(compressed,512*1024*1024+1)
            if len(data)>512*1024*1024 or not decoder.eof:
                raise FormatError('Terrain snapshot is oversized or truncated')
            edits={}
            for field in wire.parse(data):
                record=wire.parse(field.value)
                edits[wire.get(record,1).decode()]=wire.get(record,2)
            return cls(world,edits)
        except (ValueError,TypeError,zlib.error) as error:
            raise FormatError(f'Invalid terrain snapshot: {error}') from error


def empty_world(size=1000,height=20.,version=10):
    if not 100<=size<=6000 or not -500<=height<=500:
        raise FormatError('Map size must be 100–6000 m, height −500–500 m')
    textures=2**math.ceil(math.log2(size*.5))
    n=textures+1
    terrain=np.full((n,n),round((height+500)/1000*32766),dtype='<i2').tobytes()
    water=np.full((n,n),16383,dtype='<i2').tobytes()
    ground=np.zeros((8,textures,textures),dtype='u1');ground[4]=255
    biome=np.zeros((5,textures,textures),dtype='u1');biome[1]=255
    topology=np.full((textures,textures),(1<<0)|(1<<26)|(1<<29),dtype='<u4')
    world=RustMap(version,struct.pack('<q',time.time_ns()//100+621355968000000000) if version==10 else b'',
                  [wire.encode(1,0,int(size))])
    for name,data in {'terrain':terrain,'height':terrain,'water':water,'splat':ground.tobytes(),
                      'biome':biome.tobytes(),'topology':topology.tobytes(),
                      'alpha':np.full((textures,textures),255,dtype='u1').tobytes()}.items():
        world.set_layer(name,data)
    return world
