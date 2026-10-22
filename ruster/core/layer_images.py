"""Grayscale layer masks, independent of Blender and its preview resolution.

Images are top-to-bottom (+editor Y to -Y), while Rust grids start at -Y.
Binary layers resize with nearest samples; weights resize bilinearly. Operations
work in strips to avoid allocating full-size float arrays for every channel.
"""
from io import BytesIO
from pathlib import Path
import numpy as np
from .project import atomic_write
from .terrain import resample
from .wire import FormatError

MAX_IMAGE_PIXELS=4096*4096
LAYERS=('splat','biome','topology','alpha')


def target(document,layer,channel):
    if layer not in LAYERS:raise FormatError('Choose a ground texture, biome, topology or terrain-hole layer')
    grid=document.grid(layer)
    count=32 if layer=='topology' else grid.shape[0]
    if isinstance(channel,bool) or not isinstance(channel,(int,np.integer)) or not 0<=channel<count:
        raise FormatError('This map does not contain the selected layer channel')
    return grid


def mask_array(document,layer,channel=0):
    """Return a byte mask in grid order; no edits or normalizations occur."""
    grid=target(document,layer,channel)
    if layer=='topology':return np.where(grid[0]&np.uint32(1<<channel),255,0).astype('u1')
    if layer=='alpha':return np.where(grid[0]>0,255,0).astype('u1')
    return grid[channel].copy()


def image_array(document,layer,channel=0,flip_y=False):
    values=mask_array(document,layer,channel)
    return values if flip_y else np.flipud(values)


def read_image(path):
    from PIL import Image
    with Image.open(path) as image:
        if image.format not in {'PNG','TIFF'}:raise FormatError('Use a grayscale PNG or TIFF mask')
        if image.width<2 or image.height<2 or image.width*image.height>MAX_IMAGE_PIXELS:
            raise FormatError('Mask images must have at least 2 pixels per side and at most 16 megapixels')
        if getattr(image,'n_frames',1)!=1:raise FormatError('Use a single-frame mask image')
        if image.mode not in {'1','L','I','I;16','I;16L','I;16B'}:
            raise FormatError('Convert the mask to single-channel 8-bit or 16-bit grayscale first')
        if image.mode=='1':return np.asarray(image.convert('L')).copy()
        values=np.asarray(image)
        if values.min()<0 or values.max()>(255 if image.mode=='L' else 65535):
            raise FormatError('Mask values are outside the grayscale range')
        return values.copy() if image.mode=='L' else np.rint(values.astype(float)/257).astype('u1')


def export_image(document,path,layer,channel=0,flip_y=False):
    from PIL import Image
    if Path(path).suffix.lower()!='.png':raise FormatError('Export layer masks as .png files')
    data=BytesIO()
    Image.fromarray(image_array(document,layer,channel,flip_y)).save(data,format='PNG')
    atomic_write(path,data.getvalue())


def fit_mask(source,shape,binary):
    if source.shape==shape:return source
    result=np.empty(shape,dtype='u1')
    x=np.linspace(0,source.shape[1]-1,shape[1])[None,:]
    for start in range(0,shape[0],64):
        end=min(start+64,shape[0]);y=np.linspace(0,source.shape[0]-1,shape[0])[start:end,None]
        if binary:result[start:end]=source[np.floor(y+.5).astype(int),np.floor(x+.5).astype(int)]
        else:result[start:end]=np.rint(resample(source,x,y)).clip(0,255).astype('u1')
    return result


def balance_channel(grid,channel,values):
    """Set the requested weight exactly and distribute the remaining budget.

    Preserve ratios between other channels with largest-remainder rounding.
    If the old cell was entirely this channel, use the first other channel as
    fallback. Valid, unchanged pixels remain byte-exact.
    """
    result=grid.copy()
    others=[i for i in range(len(grid)) if i!=channel]
    weights=grid[others].astype(float)
    total=weights.sum(axis=0)
    empty=total==0
    weights[0,empty]=1;total[empty]=1
    budget=255-values.astype(np.int16)
    scaled=weights/total*budget
    whole=np.floor(scaled).astype('u1')
    remaining=budget-whole.sum(axis=0,dtype=np.int16)
    order=np.argsort(-(scaled-whole),axis=0,kind='stable')
    for rank in range(len(others)):
        yy,xx=np.nonzero(remaining>rank)
        whole[order[rank,yy,xx],yy,xx]+=1
    result[others]=whole;result[channel]=values
    return result


def apply_mask(document,source,layer,channel=0,flip_y=False):
    """Apply an image-order mask transactionally to one full-resolution layer."""
    grid=target(document,layer,channel)
    source=np.asarray(source)
    if source.ndim!=2 or min(source.shape)<2 or source.size>MAX_IMAGE_PIXELS:
        raise FormatError('Use a two-dimensional mask with at least 2 pixels per side and at most 16 megapixels')
    if source.dtype.kind not in 'uib' or source.min()<0 or source.max()>255:
        raise FormatError('Mask samples must be integer grayscale values from 0 to 255')
    source=source.astype('u1')*(255 if source.dtype.kind=='b' else 1)
    samples=fit_mask(source if flip_y else np.flipud(source),grid.shape[1:],layer in {'alpha','topology'})
    result=grid.copy()
    if layer in {'splat','biome'}:
        for start in range(0,grid.shape[1],64):
            end=min(start+64,grid.shape[1])
            result[:,start:end]=balance_channel(grid[:,start:end],channel,samples[start:end])
    elif layer=='alpha':result[0]=np.where(samples>=128,255,0)
    else:
        bit=np.uint32(1<<channel)
        result[0]=(grid[0]&~bit)|np.where(samples>=128,bit,np.uint32(0))
    if np.array_equal(grid,result):return False
    grid[:]=result
    document.changed(layer)
    return True


def import_image(document,path,layer,channel=0,flip_y=False):
    return apply_mask(document,read_image(path),layer,channel,flip_y)
