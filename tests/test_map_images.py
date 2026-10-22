import numpy as np
import pytest
from ruster.core.terrain import Terrain,empty_world
from ruster.core import map_images


@pytest.mark.parametrize('layer',map_images.LAYERS)
def test_maps_are_bounded_rgba_and_do_not_modify_source(layer):
    document=Terrain(empty_world(100,20));before=document.snapshot()
    pixels,meta=map_images.preview(document,layer,max_size=32)
    assert pixels.shape==(32,32,4) and np.isfinite(pixels).all()
    assert 0<=pixels.min()<=pixels.max()<=1 and np.all(pixels[:,:,3]==1)
    assert document.snapshot()==before and not document.modified_layers
    assert meta['preview_resolution']==32


def test_image_north_and_topology_unknown_bits_are_preserved():
    document=Terrain(empty_world(100,20));grid=document.grid('topology')
    grid[:]=0;grid[0,-1,:]=np.uint32(1<<31)
    pixels,_=map_images.preview(document,'topology',31,max_size=2048)
    assert np.all(pixels[-1,:,:3]==1) and np.all(pixels[0,:,:3]==0)
    assert np.any(map_images.preview(document,'topology',-1)[0][-1,:,:3]>0)


def test_single_splat_channel_and_height_have_meaningful_values():
    document=Terrain(empty_world(100,20))
    pixels,_=map_images.preview(document,'splat',4)
    assert np.all(pixels[:,:,:3]==1)
    pixels,meta=map_images.preview(document,'terrain')
    assert abs(float(pixels[0,0,0])-.52)<.001 and abs(meta['minimum']-20)<.1
