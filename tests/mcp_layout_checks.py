"""Checks shared by the actual Blender MCP fixture; uses synthetic catalog assets."""
import bpy
from mathutils import Vector

from ruster import construction, mcp_bridge, protection, scene


def near(actual, expected):
    assert (Vector(actual)-Vector(expected)).length < 1e-4, (actual, expected)


def run(server, call, uid):
    def fail(kind, **params):
        result = server.execute_command({'token': server.token, 'type': kind, 'params': params})
        assert result['status'] == 'error', result
        return result['message']

    context = call('get_blender_context')
    assert context['mode'] == 'OBJECT' and context['geometry_read_only']
    assert context['design_guide'] == 'ruster://guide/design'
    original_cursor = bpy.context.scene.cursor.matrix.copy()
    call('set_cursor', position=[3, -4, 5], rotation_degrees=[20, 30, 40])
    near(call('get_blender_context')['cursor']['position'], [3, -4, 5])
    near(call('get_blender_context')['cursor']['rotation_degrees'], [20, 30, 40])
    cursor = bpy.context.scene.cursor.matrix.copy()
    fail('set_cursor', position=[1, 2, 3], rotation_degrees=[0, float('nan'), 0])
    assert bpy.context.scene.cursor.matrix == cursor
    bpy.context.scene.cursor.matrix = original_cursor

    view = call('get_viewport_state')
    selection = [obj.name for obj in bpy.context.selected_objects]
    originals = {obj.name: obj.matrix_world.copy() for obj in scene.prefab_roots()}
    state = call('set_viewport_state', target=[3, 4, 5], distance=12., rotation_degrees=[60, 0, 35],
                 projection='ORTHO', shading='SOLID', color_type='TEXTURE', show_overlays=False,
                 show_xray=True, lens=60., clip_start=.1, clip_end=5000.)
    near(state['target'], [3, 4, 5]); near(state['rotation_degrees'], [60, 0, 35])
    assert state['distance'] == 12. and state['projection'] == 'ORTHO'
    assert state['color_type'] == 'TEXTURE' and not state['show_overlays'] and state['show_xray']
    assert [obj.name for obj in bpy.context.selected_objects] == selection
    assert all(bpy.data.objects[name].matrix_world == matrix for name, matrix in originals.items())
    for params in ({'target': [9, 9, 9], 'clip_start': 5001.}, {'distance': float('nan')},
                   {'distance': 1e300}, {'show_overlays': 'false'}, {'shading': 'INVALID'},
                   {'target': [0, 1]}, {'unsupported': True}, {}):
        fail('set_viewport_state', **params)
        assert call('get_viewport_state') == state, params
    call('set_viewport_state', **view)

    batch = call('place_prefabs', placements=[{'uid': uid, 'position': [x, 0, 0]} for x in (2, 7, 11)])
    names = [obj['name'] for obj in batch['objects']]
    first, second, third = names
    model = bpy.data.objects[first].instance_collection
    measure = call('measure_objects', first=first, second=second)
    assert measure['origin_distance'] == 5. and measure['bounds_distance'] == 3.
    near(measure['bounds_gap'], [3, 0, 0])
    assert 'bounds' not in call('measure_objects', first=first, second=second, include_bounds=False)
    call('distribute_objects', names=names, spacing=4., axis='X')
    for name, x in zip(names, (2, 6, 10)):near(bpy.data.objects[name].matrix_world.translation, [x, 0, 0])
    call('distribute_objects', names=names, spacing=.75, axis='X', mode='BOUNDS_GAP')
    for name, x in zip(names, (2, 4.75, 7.5)):near(bpy.data.objects[name].matrix_world.translation, [x, 0, 0])
    call('distribute_objects', names=list(reversed(names)), spacing=-3., axis='Y')
    for name, y in zip(reversed(names), (0, -3, -6)):assert abs(bpy.data.objects[name].matrix_world.translation.y-y) < 1e-5

    call('transform_object', name=first, position=[2, 0, 0])
    call('transform_objects_relative', names=[first], offset=[0, 0, 1], rotation_degrees=[0, 0, 90], pivot=[0, 0, 0])
    near(bpy.data.objects[first].matrix_world.translation, [0, 2, 1])
    call('undo'); near(bpy.data.objects[first].matrix_world.translation, [2, 0, 0])
    call('redo'); near(bpy.data.objects[first].matrix_world.translation, [0, 2, 1])
    call('transform_object',name=first,rotation_degrees=[13.7,-28.2,119.6],scale=[1.3,.7,2.2])
    before = {name: bpy.data.objects[name].matrix_basis.copy() for name in names}
    channels={name:tuple(tuple(getattr(bpy.data.objects[name],field)) for field in ('location','rotation_euler','scale')) for name in names}
    real_transform = mcp_bridge.set_transform
    attempts = []
    def fail_second(obj, *args, **kwargs):
        attempts.append(obj.name)
        if len(attempts) == 2:raise ValueError('Synthetic second transform failure')
        return real_transform(obj, *args, **kwargs)
    mcp_bridge.set_transform = fail_second
    try:
        fail('transform_objects_relative', names=names, offset=[1, 2, 3])
        assert len(attempts) == 2
        assert all(bpy.data.objects[name].matrix_basis == matrix for name, matrix in before.items())
        assert all(tuple(tuple(getattr(bpy.data.objects[name],field)) for field in ('location','rotation_euler','scale'))==value for name,value in channels.items())
    finally:mcp_bridge.set_transform = real_transform
    call('transform_object', name=first, rotation_degrees=[0, 0, 45],scale=[1,1,1])
    before = {name: bpy.data.objects[name].matrix_world.copy() for name in names}
    assert 'shear' in fail('transform_objects_relative', names=names, scale=[2, 1, 1])
    assert all(bpy.data.objects[name].matrix_world == matrix for name, matrix in before.items())
    for kind, params in (
        ('transform_objects_relative', {'names': names, 'scale': [0, 1, 1]}),
        ('transform_objects_relative', {'names': names, 'offset': [1e300, 0, 0]}),
        ('snap_objects_to_grid', {'names': names, 'step': 0}),
        ('snap_objects_to_grid', {'names': names, 'step': 1, 'axes': 'XX'}),
        ('distribute_objects', {'names': names, 'spacing': float('inf')})):
        fail(kind, **params)
        assert all(bpy.data.objects[name].matrix_world == matrix for name, matrix in before.items())

    call('transform_object', name=first, position=[2, 0, 0], rotation_degrees=[0, 0, 0])
    call('select_objects', names=[first])
    before_names = {obj.name for obj in bpy.context.scene.objects}
    ring = call('radial_array_objects', names=[first], count=3, center=[1, 0, 0], angle_degrees=90.)
    assert ring['new_prefab_count'] == 3
    for name, position in zip(ring['objects'], ([1, 1, 0], [0, 0, 0], [1, -1, 0])):
        near(bpy.data.objects[name].matrix_world.translation, position)
        assert bpy.data.objects[name].instance_collection == model
        assert not protection.model_error(bpy.data.objects[name])
    assert [obj.name for obj in bpy.context.selected_objects] == [first]
    fail('radial_array_objects', names=[first], count=2001, center=[0, 0, 0], angle_degrees=45.)
    fail('radial_array_objects', names=[first], count=2, center=[1e300, 0, 0], angle_degrees=45.)
    assert {obj.name for obj in bpy.context.scene.objects} == before_names | set(ring['objects'])
    call('delete_objects', names=ring['objects'])
    # A late copy failure cleans up every new root and restores selection.
    attempts.clear(); mcp_bridge.set_transform = fail_second
    try:fail('radial_array_objects', names=[first], count=3, center=[1, 0, 0], angle_degrees=90.)
    finally:mcp_bridge.set_transform = real_transform
    assert {obj.name for obj in bpy.context.scene.objects} == before_names
    assert [obj.name for obj in bpy.context.selected_objects] == [first]
    for axis, expected in (('X', [0, 0, 2]), ('Y', [2, 0, 0])):
        call('transform_object', name=first, position=[0, 2, 0] if axis == 'X' else [0, 0, 2])
        copies = call('radial_array_objects', names=[first], count=1, center=[0, 0, 0], angle_degrees=90., axis=axis)
        near(bpy.data.objects[copies['objects'][0]].matrix_world.translation, expected)
        call('delete_objects', names=copies['objects'])

    call('transform_object', name=first, position=[.5, -.5, 2.3], rotation_degrees=[0, 0, 0])
    call('snap_objects_to_grid', names=[first], step=1., axes='XY')
    near(bpy.data.objects[first].matrix_world.translation, [1, -1, 2.3])
    call('snap_objects_to_grid', names=[first], step=2., origin=[.5, .5, .5], axes='Z')
    near(bpy.data.objects[first].matrix_world.translation, [1, -1, 2.5])
    group = call('group_objects', names=[first, second], name='Layout rollback group')['name']
    fail('transform_objects_relative', names=[group, first], offset=[1, 0, 0])
    # Active symmetry must not mutate peers outside a transaction.
    settings = bpy.context.scene.ruster_construction
    settings.symmetry, settings.sides = True, 3
    peers = construction.add_symmetry(bpy.data.objects[third], bpy.context)
    peer_names = [obj.name for obj in peers]
    before = {obj.name: obj.matrix_world.copy() for obj in [bpy.data.objects[third], *peers]}
    assert 'Radial Symmetry' in fail('transform_objects_relative', names=[third], offset=[1, 0, 0])
    assert 'Radial Symmetry' in fail('transform_objects', transforms=[{'name': third, 'position': [8, 1, 2]}])
    assert 'Radial Symmetry' in fail('align_objects', names=[third], target=0)
    assert 'Radial Symmetry' in fail('snap_objects_to_plane', names=[third], target=0)
    assert all(bpy.data.objects[name].matrix_world == matrix for name, matrix in before.items())
    settings.symmetry = False
    call('delete_objects', names=[group, third, *peer_names])
    assert all(not protection.model_error(obj) for obj in scene.prefab_roots())
