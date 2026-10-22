"""Custom prefab assemblies and deterministic scatter placement."""
import base64
import json
import math
import random
from . import wire
from .rust_map import prefab_id,prefab_transform
from .wire import FormatError


def encode_assembly(records,title='Custom Prefab'):
    records=list(records)
    if not 1<=len(records)<=100000:
        raise FormatError('A custom prefab needs 1–100,000 placements')
    return json.dumps({'format':'ruster-prefab','schema':1,'title':title,
        'prefabs':[base64.b64encode(wire.serialize(p)).decode() for p in records]},indent=2).encode()


def decode_assembly(data):
    if len(data)>32*1024*1024:
        raise FormatError('Custom prefab exceeds the size limit')
    value=json.loads(data)
    if value.get('format')!='ruster-prefab' or value.get('schema')!=1:
        raise FormatError('Unsupported custom prefab format')
    records=value.get('prefabs',[])
    if not 1<=len(records)<=100000:
        raise FormatError('Invalid custom prefab placement count')
    parsed=[]
    for record in records:
        fields=wire.parse(base64.b64decode(record,validate=True))
        prefab_id(fields)
        if not all(math.isfinite(v) for vector in prefab_transform(fields) for v in vector):
            raise FormatError('Custom prefab contains an invalid transform')
        parsed.append(fields)
    return value.get('title','Custom Prefab'),parsed


def scatter_points(center,radius,count,spacing=0.,seed=0,occupied=()):
    if not all(math.isfinite(v) for v in (*center,radius,spacing)) or radius<=0 or spacing<0 or not 1<=count<=5000:
        raise FormatError('Invalid scatter settings')
    random_=random.Random(seed)
    cell=max(spacing,1e-6)
    cells={}
    def add(point):
        key=(math.floor(point[0]/cell),math.floor(point[1]/cell))
        cells.setdefault(key,[]).append(point)
    for point in occupied:add(point)
    result=[]
    for _ in range(count*50):
        theta=random_.uniform(0,2*math.pi)
        distance=math.sqrt(random_.random())*radius
        point=(center[0]+math.cos(theta)*distance,center[1]+math.sin(theta)*distance)
        if spacing:
            key=(math.floor(point[0]/cell),math.floor(point[1]/cell))
            if any(math.dist(point,old)<spacing for dx in (-1,0,1) for dy in (-1,0,1)
                   for old in cells.get((key[0]+dx,key[1]+dy),())):
                continue
        result.append(point);add(point)
        if len(result)==count:break
    return result


class SpacingIndex:
    """World-space minimum spacing without scanning all placements per stamp."""
    def __init__(self,spacing,points=()):
        if not math.isfinite(spacing) or spacing<=0:raise FormatError('Spacing must be positive')
        self.spacing=spacing;self.cells={}
        for point in points:self.add(point)
    def key(self,point):return (math.floor(point[0]/self.spacing),math.floor(point[1]/self.spacing))
    def add(self,point):self.cells.setdefault(self.key(point),[]).append(tuple(point[:2]))
    def available(self,point):
        x,y=self.key(point)
        return not any(math.dist(point[:2],other)<self.spacing for dx in (-1,0,1) for dy in (-1,0,1)
            for other in self.cells.get((x+dx,y+dy),()))


def surface(document,x,z,max_slope=90.,respect_holes=True):
    if abs(x)>document.size/2 or abs(z)>document.size/2:return None
    if respect_holes and 'alpha' in document.base_layers:
        grid=document.grid('alpha')[0];n=grid.shape[-1]
        ix=round((x/document.size+.5)*(n-1));iz=round((z/document.size+.5)*(n-1))
        if grid[iz,ix]<128:return None
    step=document.size/(document.grid('terrain').shape[-1]-1)
    dx=(float(document.sample_height(x+step,z))-float(document.sample_height(x-step,z)))/(2*step)
    dz=(float(document.sample_height(x,z+step))-float(document.sample_height(x,z-step)))/(2*step)
    if math.degrees(math.atan(math.hypot(dx,dz)))>max_slope:return None
    length=math.sqrt(dx*dx+dz*dz+1)
    return float(document.sample_height(x,z)),(-dx/length,-dz/length,1/length)
