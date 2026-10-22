"""Bounded, read-only map-layer previews in Rust grid order (south to north)."""
import numpy as np
from .terrain import resample
from .wire import FormatError

SPLAT_COLORS=np.array([(.34,.24,.15),(.85,.89,.93),(.65,.55,.32),(.29,.30,.29),
    (.22,.35,.12),(.11,.22,.08),(.4,.39,.35),(.37,.34,.29)])
BIOME_COLORS=np.array([(.72,.45,.18),(.2,.5,.14),(.54,.5,.3),(.86,.92,1.),(.07,.24,.12)])
LAYERS=('terrain','splat','biome','topology','alpha','water','height','slope')


def preview(document,layer,channel=-1,max_size=1024):
    if layer not in LAYERS:raise FormatError('Unknown map preview layer')
    if type(max_size)!=int or not 16<=max_size<=2048:raise FormatError('Preview size must be 16–2048')
    if type(channel)!=int or channel< -1:raise FormatError('Invalid map channel')
    grid=document.grid('terrain' if layer=='slope' else layer)
    n=grid.shape[-1];size=min(n,max_size)
    axis=np.linspace(0,n-1,size);x=axis[None,:];y=axis[:,None]
    result=np.ones((size,size,4),dtype=np.float32)
    if layer in {'terrain','water','height','slope'}:
        values=resample(grid[0],x,y)/32766*1000-500
        if layer=='slope':
            step=document.size/(n-1)
            dx=(resample(grid[0],x+1,y)-resample(grid[0],x-1,y))/32766*1000/(2*step)
            dy=(resample(grid[0],x,y+1)-resample(grid[0],x,y-1))/32766*1000/(2*step)
            values=np.degrees(np.arctan(np.hypot(dx,dy)))
            display=values/90;units='degrees'
        else:display=(values+500)/1000;units='metres'
        result[:,:,:3]=np.clip(display[:,:,None],0,1)
        metadata={'minimum':float(values.min()),'maximum':float(values.max()),'units':units}
    elif layer in {'splat','biome'}:
        if channel>=len(grid):raise FormatError('This map does not contain that channel')
        samples=resample(grid,x,y)/255
        if channel>=0:result[:,:,:3]=samples[channel,:,:,None]
        else:
            palette=SPLAT_COLORS if layer=='splat' else BIOME_COLORS
            result[:,:,:3]=np.moveaxis(samples,0,-1)@palette[:len(grid)]
        metadata={'channels':len(grid),'units':'weight'}
    else:
        indexes=np.floor(axis+.5).astype(int);samples=grid[0][np.ix_(indexes,indexes)]
        if layer=='alpha':result[:,:,:3]=(samples>0)[:,:,None]
        elif channel>=0:
            if channel>31:raise FormatError('Invalid topology bit')
            result[:,:,:3]=((samples&np.uint32(1<<channel))!=0)[:,:,None]
        else:
            # Every bit has a deterministic display color; unknown bits stay visible.
            colors=np.array([((i*.61803398875)%1,(i*.381966+.3)%1,(i*.217+.6)%1) for i in range(32)])
            total=np.zeros((size,size),dtype=float);rgb=np.zeros((size,size,3),dtype=float)
            for i,color in enumerate(colors):
                active=(samples&np.uint32(1<<i))!=0;total+=active;rgb+=active[:,:,None]*color
            result[:,:,:3]=rgb/np.maximum(total,1)[:,:,None]
        metadata={'units':'mask'}
    return result,{'layer':layer,'source_resolution':n,'preview_resolution':size,'north':'+Y (top)',**metadata}
