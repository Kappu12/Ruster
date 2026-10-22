import numpy as np
import pytest
from PIL import Image
from ruster.core import layer_images as masks,wire
from ruster.core.terrain import Terrain,empty_world,normalize_weights
from ruster.core.rust_map import RustMap
from tests.fixtures import sample_world


def document():return Terrain(empty_world(100,20))


@pytest.mark.parametrize('layer,channel',[('splat',7),('biome',4),('topology',11),('alpha',0)])
def test_asymmetric_image_roundtrip_is_not_flipped_and_does_not_mutate_export(tmp_path,layer,channel):
    doc=document();n=doc.grid(layer).shape[-1]
    values=np.zeros((n,n),dtype='u1');values[:n//2,n//2:]=255
    masks.apply_mask(doc,values,layer,channel)
    before=doc.snapshot()
    path=tmp_path/'mask.png';masks.export_image(doc,path,layer,channel)
    assert doc.snapshot()==before
    assert np.array_equal(masks.read_image(path),values)
    assert masks.import_image(doc,path,layer,channel) is False
    assert doc.snapshot()==before
    other=document();masks.import_image(other,path,layer,channel)
    assert other.raw(layer)==doc.raw(layer)


@pytest.mark.parametrize('layer,channels',[('splat',8),('biome',5)])
def test_channel_weights_are_exact_with_stable_rounding_and_no_unrelated_layer_edits(layer,channels):
    doc=document();grid=doc.grid(layer)
    rng=np.random.default_rng(19)
    grid[:]=normalize_weights(rng.random(grid.shape))
    before=grid.copy();other_layers={key:doc.raw(key) for key in doc.base_layers if key!=doc.resolve(layer)}
    values=rng.integers(0,256,size=grid.shape[1:],dtype='u1')
    masks.apply_mask(doc,values,layer,channels-1,flip_y=True)
    assert np.array_equal(grid[-1],values)
    assert np.all(grid.sum(axis=0)==255)
    original=before[:-1].astype(float)
    ideal=original/original.sum(axis=0)*(255-values.astype(int))
    assert np.max(abs(grid[:-1].astype(float)-ideal))<1.00001
    for key,value in other_layers.items():assert doc.raw(key)==value
    result=RustMap.read(doc.export_world().write())
    assert result.layers[doc.resolve(layer)]==doc.raw(layer)


def test_empty_other_channels_have_deterministic_fallback():
    doc=document();grid=doc.grid('splat');grid[:]=0;grid[3]=255
    masks.apply_mask(doc,np.full(grid.shape[1:],100,dtype='u1'),'splat',3)
    assert np.all(grid[3]==100) and np.all(grid[0]==155)
    assert np.all(grid[[1,2,4,5,6,7]]==0)


def test_bilinear_weights_and_nearest_binary_resize():
    doc=document();source=np.array([[0,255],[0,255]],dtype='u1')
    masks.apply_mask(doc,source,'splat',1)
    grid=doc.grid('splat');n=grid.shape[-1]
    assert np.all(grid[1,:,0]==0) and np.all(grid[1,:,-1]==255)
    assert np.all(grid[1,:,n//2]==round(255*(n//2)/(n-1)))
    masks.apply_mask(doc,source,'alpha')
    assert set(np.unique(doc.grid('alpha')))=={0,255}
    assert np.all(doc.grid('alpha')[0,:,:n//2]==0)


def test_topology_replaces_only_selected_bit_and_keeps_unknown_bits():
    doc=document();grid=doc.grid('topology')
    grid[:]=np.uint32((1<<31)|(1<<2)|(1<<11))
    source=np.array([[0,255],[127,128]],dtype='u1')
    masks.apply_mask(doc,source,'topology',11)
    assert np.all(grid&np.uint32(1<<31)) and np.all(grid&np.uint32(1<<2))
    image=masks.image_array(doc,'topology',11)
    assert image[0,0]==0 and image[0,-1]==255 and image[-1,0]==0 and image[-1,-1]==255
    assert np.array_equal(grid[0]&~np.uint32(1<<11),np.full(grid.shape[1:],(1<<31)|(1<<2),dtype='u4'))


def test_four_channel_biome_rejects_jungle_without_any_edit():
    doc=Terrain(sample_world());before=doc.snapshot()
    with pytest.raises(ValueError):masks.apply_mask(doc,np.zeros((2,2),dtype='u1'),'biome',4)
    assert doc.snapshot()==before
    masks.apply_mask(doc,np.full((2,2),128,dtype='u1'),'biome',3)
    assert doc.grid('biome').shape[0]==4 and np.all(doc.grid('biome')[3]==128)


@pytest.mark.parametrize('source',[np.zeros((1,2),dtype='u1'),np.zeros((2,2,3),dtype='u1'),
    np.full((2,2),256),np.full((2,2),-1),np.full((2,2),np.nan),np.full((2,2),.5)])
def test_invalid_mask_never_changes_document(source):
    doc=document();before=doc.snapshot()
    with pytest.raises(ValueError):masks.apply_mask(doc,source,'splat',0)
    assert doc.snapshot()==before


def test_png16_normalization_flip_and_boolean_mask(tmp_path):
    source=np.array([[0,65535],[257,32768]],dtype='uint16')
    path=tmp_path/'mask.png';Image.fromarray(source).save(path)
    assert np.array_equal(masks.read_image(path),[[0,255],[1,128]])
    doc=document();masks.import_image(doc,path,'splat',1,flip_y=True)
    assert doc.grid('splat')[1,0,-1]==255 and doc.grid('splat')[1,-1,-1]==128
    masks.apply_mask(doc,np.array([[False,True],[True,False]]),'alpha')
    assert masks.image_array(doc,'alpha')[0,-1]==255


@pytest.mark.parametrize('mode',['RGB','RGBA','P','F'])
def test_non_grayscale_images_fail_without_color_conversion(tmp_path,mode):
    path=tmp_path/'mask.tiff';Image.new(mode,(2,2)).save(path)
    with pytest.raises(ValueError,match='grayscale'):masks.read_image(path)


def test_ground_alias_and_unknown_records_survive_mask_import():
    world=sample_world()
    for i,field in enumerate(world.fields):
        if field.number==2:
            record=wire.parse(field.value)
            if wire.get(record,1)==b'splat':
                world.fields[i]=wire.encode(2,2,wire.serialize(wire.replace(record,1,2,b'ground')+[wire.encode(72,2,b'future')]))
    doc=Terrain(world);masks.apply_mask(doc,np.full((2,2),120,dtype='u1'),'splat',1)
    result=RustMap.read(doc.export_world().write())
    assert 'splat' not in result.layers and 'ground' in result.layers
    record=next(record for record in result.messages(2) if wire.get(record,1)==b'ground')
    assert wire.get(record,72)==b'future'
    for key,value in world.layers.items():
        if key!='ground':assert result.layers[key]==value
