from ruster.core.volume_picking import clip_segment,project_segment,wire_hit


def test_edges_clip_before_perspective_divide_when_camera_is_inside():
    # One endpoint is behind the eye. The visible part enters at the near plane.
    result=project_segment((.2,0,-3,-1),(.2,0,0,2),100,100)
    assert result is not None
    assert all(0<=p[0]<=100 and 0<=p[1]<=100 for p in result)
    assert abs(result[0][2]+1)<1e-8
    assert clip_segment((0,0,-3,-1),(1,0,-3,-1)) is None


def test_offscreen_edges_and_far_plane_do_not_make_phantom_hits():
    assert project_segment((2,0,0,1),(3,0,0,1),100,100) is None
    assert project_segment((0,0,2,1),(1,0,3,1),100,100) is None
    assert wire_hit((50,50),[],8) is None


def test_enclosing_volume_interior_does_not_swallow_nested_boundary():
    outer=[((0,0,0),(100,0,0)),((100,0,0),(100,100,0)),
           ((100,100,0),(0,100,0)),((0,100,0),(0,0,0))]
    inner=[((40,40,.2),(60,40,.2))]
    assert wire_hit((50,40),outer,8) is None
    assert wire_hit((50,40),inner,8)==(0.,.2)
    assert wire_hit((50,5),outer,8)==(5.,0.)


def test_degenerate_edge_and_depth_interpolation():
    assert wire_hit((12,10),[((10,10,.5),(10,10,.5))],3)==(2.,.5)
    assert wire_hit((50,0),[((0,0,-1),(100,0,1))],8)==(0.,0.)
