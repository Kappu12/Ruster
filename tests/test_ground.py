import numpy as np
import pytest
from ruster.core.ground import flat_ground, validate_ground
from ruster.core.terrain import Terrain
from ruster.core.rust_map import RustMap, prefab_id
from ruster.core import preview_protocol as protocol, map_images


def test_native_jungle_is_four_channels_with_implicit_remainder():
    world=flat_ground(384,0,'Jungle','Forest')
    doc=validate_ground(RustMap.read(world.write()))
    assert doc.grid('biome').shape==(4,512,512)
    assert np.all(doc.grid('biome')==0)
    assert np.all(doc.biome_weights()[4]==255)
    assert np.all(doc.grid('splat')[5]==255)
    assert np.all(doc.grid('splat').sum(axis=0)==255)
    assert np.max(abs(doc.heights()))<.031
    pixels,meta=map_images.preview(doc,'biome',4,max_size=32)
    assert np.all(pixels[:,:,:3]==1) and meta['channels']==5


def test_ground_patch_has_native_solid_alpha_inside_and_no_topology_outside():
    doc=validate_ground(flat_ground(384,0))
    alpha=doc.grid('alpha')[0]
    assert alpha[256,256]==255 and alpha[0,0]==0
    assert doc.grid('topology')[0,256,256]&(1<<5)
    assert doc.grid('topology')[0,0,0]==0
    assert np.all(doc.grid('water')==0)


def test_jungle_can_be_painted_and_blended_without_fifth_native_channel():
    doc=Terrain(flat_ground(256,0,'Temperate'))
    original=doc.grid('biome').copy()
    doc.brush('PAINT',0,0,30,layer='biome',channel=4,strength=.5)
    weights=doc.biome_weights()
    assert 100<weights[4,256,256]<140
    assert np.all(weights.sum(axis=0)==255)
    assert np.array_equal(doc.grid('biome')[:,0,0],original[:,0,0])
    doc.brush('PAINT',0,0,20,layer='biome',channel=0,strength=.5)
    assert 100<doc.grid('biome')[0,256,256]<140
    assert len(doc.grid('biome'))==4
    restored=Terrain(RustMap.read(doc.export_world().write()))
    assert np.array_equal(restored.biome_weights(),doc.biome_weights())


def test_preview_map_preserves_native_ground_and_source_bytes():
    world=flat_ground(384,0,'Jungle','Forest');before=world.write()
    rows=[{'key':1,'uid':123,'path':'assets/test.prefab','position':(3.,0.,4.),
           'rotation':(0.,0.,0.,1.),'scale':(1.,1.,1.),'euler':(0.,0.,0.)}]
    actual=RustMap.read(protocol.preview_map(rows,ground=before,preload=[{'uid':456}]))
    assert actual.layers==world.layers and actual.size==world.size
    assert [prefab_id(r) for r in actual.prefabs]==[123,456]
    assert world.write()==before
    validate_ground(actual)


@pytest.mark.parametrize('kwargs',[{'size':float('nan')},{'size':-1},{'size':2001},
    {'size':1200,'world_size':1000},{'height':float('inf')},{'world_size':True},
    {'biome':'Unknown'},{'splat':'Unknown'}])
def test_invalid_ground_is_rejected_before_allocation(kwargs):
    with pytest.raises(ValueError):flat_ground(**kwargs)
