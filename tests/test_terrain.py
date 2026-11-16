import numpy as np
import pytest
from ruster.core.terrain import Terrain,empty_world,normalize_weights
from ruster.core.rust_map import RustMap
from ruster.core import wire,paths
from tests.fixtures import sample_world


def document():
    return Terrain(empty_world(100,20))


def test_brush_changes_full_resolution_not_only_preview():
    doc=Terrain(empty_world(1000,20))
    n=doc.grid('terrain').shape[-1]
    index=255  # omitted by the 257-vertex preview grid
    x=(index/(n-1)-.5)*doc.size
    before=doc.grid('terrain')[0,index,index]
    doc.brush('RAISE',x,x,.1,strength=1)
    after=RustMap.read(doc.export_world().write())
    assert after.height_grid()[0]==n
    assert np.frombuffer(after.layers['terrain'],dtype='<i2').reshape(n,n)[index,index]>before


@pytest.mark.parametrize('tool',['RAISE','LOWER','FLATTEN','SMOOTH','ERODE','SHARPEN','TERRACE','NOISE','CLONE','PINCH','TWIST','SLOPE'])
def test_height_brushes_are_finite_and_bounded(tool):
    doc=document()
    doc.brush('RAISE',0,0,15,strength=1)
    doc.brush(tool,0,0,20,strength=.8,height=50,source=(20,20))
    assert np.isfinite(doc.heights()).all()
    assert doc.heights().min()>=-500
    assert doc.heights().max()<=500


def test_derived_height_preserves_relief_while_terrain_moves():
    doc=document()
    terrain=doc.grid('terrain')
    derived=doc.grid('height')
    derived[:]+=100
    doc.brush('RAISE',0,0,10,strength=1)
    assert np.all(derived.astype(int)-terrain.astype(int)==100)


def test_outside_map_brush_does_not_edit():
    doc=document()
    assert doc.brush('RAISE',10000,10000,1) is False
    assert not doc.modified_layers


def test_height_mask_blocks_paint_outside_limits():
    doc=document()
    before=doc.raw('terrain')
    doc.brush('RAISE',0,0,10,minimum=100,maximum=200)
    assert doc.raw('terrain')==before


@pytest.mark.parametrize('channels',[4,5,8])
def test_weight_normalization_exactly_255(channels):
    rng=np.random.default_rng(3)
    weights=rng.random((channels,11,13))*1000
    weights[:,0,0]=0
    result=normalize_weights(weights)
    assert result.dtype==np.uint8
    assert np.all(result.sum(axis=0)==255)


@pytest.mark.parametrize('layer,channel',[('splat',7),('biome',4)])
def test_weight_paint_preserves_normalization(layer,channel):
    doc=document()
    doc.brush('PAINT',0,0,20,layer=layer,channel=channel,strength=.3)
    grid=doc.grid(layer)
    assert grid[channel,grid.shape[1]//2,grid.shape[2]//2]>0
    assert np.all(grid.sum(axis=0)==255)


def test_old_four_channel_biome_layout_is_retained():
    doc=Terrain(sample_world())
    doc.brush('PAINT',0,0,100,layer='biome',channel=3)
    assert doc.grid('biome').shape[0]==4
    doc.brush('PAINT',0,0,100,layer='biome',channel=4,strength=1,falloff=0)
    assert doc.grid('biome').shape[0]==4
    assert doc.biome_weights()[4].max()==255


def test_topology_add_remove_retains_unrelated_and_unknown_bits():
    doc=document()
    grid=doc.grid('topology');grid[:]|=np.uint32(1<<31)
    doc.brush('PAINT',0,0,10,layer='topology',channel=11,strength=.2)
    center=grid.shape[1]//2
    assert grid[0,center,center]&(1<<11)
    doc.brush('PAINT',0,0,10,layer='topology',channel=11,invert=True)
    assert not grid[0,center,center]&(1<<11)
    assert np.all(grid&(1<<31))


def test_alpha_cut_and_restore():
    doc=document();n=doc.grid('alpha').shape[-1]
    doc.brush('PAINT',0,0,10,layer='alpha',invert=True)
    assert doc.grid('alpha')[0,n//2,n//2]==0
    doc.brush('PAINT',0,0,10,layer='alpha')
    assert doc.grid('alpha')[0,n//2,n//2]==255


def test_snapshot_roundtrip_preserves_every_edit():
    doc=document()
    for layer,channel in [('terrain',0),('splat',2),('biome',4),('alpha',0),('topology',3),('water',0)]:
        doc.brush('RAISE',0,0,10,layer=layer,channel=channel,invert=layer=='alpha')
    restored=Terrain.restore(doc.world,doc.snapshot())
    assert set(restored.modified_layers)==set(doc.modified_layers)
    for name in doc.modified_layers:assert restored.raw(name)==doc.raw(name)


def test_ground_layer_alias_preserves_name_and_unknown_metadata():
    world=sample_world()
    for i,field in enumerate(world.fields):
        if field.number==2:
            inner=wire.parse(field.value)
            if wire.get(inner,1)==b'splat':
                inner=wire.replace(inner,1,2,b'ground')+[wire.encode(72,2,b'future metadata')]
                world.fields[i]=wire.encode(2,2,wire.serialize(inner))
    doc=Terrain(world);doc.brush('PAINT',0,0,200,layer='splat',channel=1)
    result=doc.export_world()
    assert 'ground' in result.layers and 'splat' not in result.layers
    layer=next(x for x in result.messages(2) if wire.get(x,1)==b'ground')
    assert wire.get(layer,72)==b'future metadata'


def test_path_updates_retain_unknown_node_and_record_fields():
    world=sample_world()
    fields=world.paths[0]+[wire.encode(90,2,b'future path')]
    old=next(f for f in fields if f.number==15)
    extended=wire.parse(old.value)+[wire.encode(99,2,b'future node')]
    fields=[wire.encode(15,2,wire.serialize(extended)) if f is old else f for f in fields]
    record=paths.read(fields);record['width']=12;record['nodes'][0]=(1,2,3)
    changed=paths.update(fields,record)
    assert wire.get(changed,90)==b'future path'
    assert wire.get(wire.parse(next(f.value for f in changed if f.number==15)),99)==b'future node'
    result=paths.read(changed)
    assert result['width']==12 and result['nodes'][0]==(1,2,3)
    world.replace_paths([changed]);assert paths.read(RustMap.read(world.write()).paths[0])['width']==12


def test_path_unchanged_record_is_byte_exact():
    fields=sample_world().paths[0]
    assert wire.serialize(paths.update(fields,paths.read(fields)))==wire.serialize(fields)


def test_bridge_makes_an_even_grade():
    doc=document()
    doc.bridge((-30,0,10),(30,0,70),20)
    assert float(doc.sample_height(-25,0))<float(doc.sample_height(25,0))


def test_path_resampling_obeys_spacing_and_preserves_ends():
    result=paths.sample_polyline([(0,0,0),(10,0,0),(10,0,10)],2)
    assert result[0]==[0,0,0] and result[-1]==[10,0,10]
    assert np.linalg.norm(np.diff(result,axis=0),axis=1).max()<=2.00001


def test_stamp_raises_and_inverts_without_changing_outside_brush():
    doc=document();original=doc.heights().copy()
    stamp=np.ones((9,9))
    doc.brush('STAMP',0,0,10,stamp=stamp,height=40,strength=1)
    assert float(doc.sample_height(0,0))>50
    assert doc.heights()[0,0]==original[0,0]
    doc.brush('STAMP',0,0,10,stamp=stamp,height=40,strength=1,invert=True)
    assert abs(float(doc.sample_height(0,0))-20)<.05


def test_island_generator_is_seeded_and_has_underwater_edges():
    first,second=document(),document()
    first.generate_island(seed=14);second.generate_island(seed=14)
    assert first.raw('terrain')==second.raw('terrain')
    assert np.all(first.heights()[0]<0)
    assert first.heights().max()>0
