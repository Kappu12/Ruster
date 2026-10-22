import math
import pytest
from ruster.core import prefabs,wire
from tests.fixtures import sample_world


def test_assembly_retains_unknown_prefab_records():
    records=sample_world().prefabs
    title,result=prefabs.decode_assembly(prefabs.encode_assembly(records,'Test Monument'))
    assert title=='Test Monument'
    assert [wire.serialize(x) for x in result]==[wire.serialize(x) for x in records]


def test_invalid_assembly_is_rejected():
    with pytest.raises(ValueError):prefabs.decode_assembly(b'{"format":"wrong","schema":1}')
    with pytest.raises(ValueError):prefabs.encode_assembly([])


def test_scatter_is_repeatable_and_respects_spacing():
    points=prefabs.scatter_points((3,4),20,50,spacing=3,seed=42)
    assert points==prefabs.scatter_points((3,4),20,50,spacing=3,seed=42)
    assert all(math.dist((3,4),p)<=20 for p in points)
    assert all(math.dist(a,b)>=3 for i,a in enumerate(points) for b in points[i+1:])


def test_scatter_retains_existing_occupancy():
    points=prefabs.scatter_points((0,0),3,40,spacing=2,seed=10,occupied=[(0,0)])
    assert all(math.dist((0,0),p)>=2 for p in points)
    assert len(points)<40


def test_paint_spacing_includes_existing_objects_and_adjacent_cells():
    from ruster.core.prefabs import SpacingIndex
    index=SpacingIndex(4,[(0,0)])
    assert not index.available((3.9,0))
    assert index.available((4,0))
    index.add((4,0))
    assert not index.available((6,1))
    assert index.available((-4,0))


def test_surface_placement_rejects_holes_steep_slopes_and_outside_map():
    from ruster.core.prefabs import surface
    from ruster.core.terrain import Terrain,empty_world
    doc=Terrain(empty_world(100,20))
    assert surface(doc,0,0)[0]>19
    assert surface(doc,51,0) is None
    doc.brush('PAINT',0,0,10,layer='alpha',invert=True)
    assert surface(doc,0,0) is None
    assert surface(doc,0,0,respect_holes=False) is not None
    doc.brush('SLOPE',0,0,30,height=20,slope=60,strength=1)
    assert surface(doc,0,0,max_slope=30,respect_holes=False) is None
