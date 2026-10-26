"""Native Blender inspection and layout tools for exportable Rust compositions."""
import math

import bpy
from mathutils import Euler, Matrix, Vector

from . import app, scene, mcp_building, mcp_prefab_ops, construction, placement

READ = {'get_blender_context', 'get_viewport_state', 'measure_objects'}
EDIT = {'set_viewport_state', 'set_cursor', 'transform_objects_relative',
        'radial_array_objects', 'distribute_objects', 'snap_objects_to_grid'}


def number(value, label, minimum=-1e7, maximum=1e7):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f'{label} must be a finite number from {minimum} to {maximum}')
    return value


def cursor_info():
    cursor = bpy.context.scene.cursor
    return {'position': list(cursor.location),
            'rotation_degrees': [math.degrees(v) for v in cursor.matrix.to_euler('XYZ')]}


def viewport_state():
    _window, area, _region = mcp_building.viewport()
    space = area.spaces.active
    view = space.region_3d
    return {'target': list(view.view_location), 'distance': view.view_distance,
            'rotation_degrees': [math.degrees(v) for v in view.view_rotation.to_euler('XYZ')],
            'projection': view.view_perspective, 'shading': space.shading.type,
            'color_type': space.shading.color_type, 'show_overlays': space.overlay.show_overlays,
            'show_xray': space.shading.show_xray, 'lens': space.lens,
            'clip_start': space.clip_start, 'clip_end': space.clip_end}


def set_viewport(p, bridge):
    _window, area, _region = mcp_building.viewport()
    space = area.spaces.active
    view = space.region_3d
    allowed = {'target', 'distance', 'rotation_degrees', 'projection', 'shading',
               'color_type', 'show_overlays', 'show_xray', 'lens', 'clip_start', 'clip_end'}
    if not p or set(p)-allowed:
        raise ValueError('Provide supported viewport settings')
    changes = []
    for key, value in p.items():
        if key == 'target':
            value = bridge.vector(value, 'View target'); owner, prop = view, 'view_location'
            if any(abs(v) > 1e7 for v in value):raise ValueError('View target exceeds supported coordinates')
        elif key == 'rotation_degrees':
            angles = bridge.vector(value, 'View rotation')
            value = Euler(tuple(math.radians(v % 360.) for v in angles), 'XYZ').to_quaternion()
            owner, prop = view, 'view_rotation'
        elif key in {'projection', 'shading', 'color_type'}:
            enums = {'projection': {'PERSP', 'ORTHO'}, 'shading': {'WIREFRAME', 'SOLID', 'MATERIAL', 'RENDERED'},
                     'color_type': {'MATERIAL', 'OBJECT', 'RANDOM', 'SINGLE', 'TEXTURE'}}
            if not isinstance(value, str) or value not in enums[key]:raise ValueError('Invalid viewport '+key)
            owner, prop = (view, 'view_perspective') if key == 'projection' else (space.shading, 'type' if key == 'shading' else key)
        elif key in {'show_overlays', 'show_xray'}:
            if type(value) != bool:raise ValueError(key+' must be boolean')
            owner, prop = (space.overlay if key == 'show_overlays' else space.shading), key
        else:
            owner, prop = (view, 'view_distance') if key == 'distance' else (space, key)
            rna = owner.bl_rna.properties[prop]
            value = number(value, key, max(1e-4, rna.hard_min), min(1e7, rna.hard_max))
        changes.append((owner, prop, value))
    if p.get('clip_start', space.clip_start) >= p.get('clip_end', space.clip_end):
        raise ValueError('clip_start must be less than clip_end')
    before = [(owner, prop, getattr(owner, prop).copy() if hasattr(getattr(owner, prop), 'copy') else getattr(owner, prop))
              for owner, prop, _value in changes]
    try:
        for owner, prop, value in changes:setattr(owner, prop, value)
    except Exception:
        for owner, prop, value in before:setattr(owner, prop, value)
        raise
    area.tag_redraw()
    return viewport_state()


def editable_roots(names, bridge):
    objects = mcp_building.object_names(names, bridge)
    mcp_building.independent(objects)
    # A depsgraph symmetry callback can mutate peers outside this transaction.
    if bpy.context.scene.ruster_construction.symmetry:
        linked = {obj for members in construction.symmetry_groups(bpy.context.scene).values() for obj in members.values()}
        if any(obj in linked for tree in mcp_prefab_ops.trees(objects) for obj in tree):
            raise ValueError('Turn off Radial Symmetry before batch layout of linked symmetry members')
    return objects


def apply_matrices(objects, matrices, bridge):
    """Keep exact TRS semantics; never silently decompose a sheared delta."""
    for matrix in matrices:
        if any(not math.isfinite(v) for row in matrix for v in row) or scene.matrix_has_shear(matrix):
            raise ValueError('Layout introduces shear, zero scale or an invalid transform; use uniform scale')
    before = {obj: placement.transform_state(obj) for obj in objects}
    try:
        for obj, matrix in zip(objects, matrices):
            location, rotation, scale = matrix.decompose()
            bridge.set_transform(obj, list(location), [math.degrees(v) for v in rotation.to_euler('XYZ')], list(scale))
    except Exception:
        for obj, state in before.items():placement.restore_transform(obj,state)
        bpy.context.view_layer.update()
        raise


def loaded_bounds(objects):
    if any(not obj.instance_collection for obj in mcp_prefab_ops.prefabs_in(objects)):
        raise ValueError('Load original model geometry for every target before bounds measurements or spacing')
    hierarchy = mcp_building.hierarchy(); cache = {}
    boxes = [mcp_building.object_bounds(obj, hierarchy, cache) for obj in objects]
    if any(box is None for box in boxes):raise ValueError('Targets have no loaded model bounds')
    return boxes


def distribution_matrices(objects, matrices, axis, mode, spacing):
    if len(objects) < 2:raise ValueError('Choose at least two objects in the desired spacing order')
    if axis not in {'X', 'Y', 'Z'} or mode not in {'ORIGIN', 'BOUNDS_GAP'}:raise ValueError('Use axis X/Y/Z and mode ORIGIN/BOUNDS_GAP')
    spacing = number(spacing, 'Spacing'); index = 'XYZ'.index(axis)
    boxes = loaded_bounds(objects) if mode == 'BOUNDS_GAP' else None
    edge = boxes[0]['max'][index] if boxes else matrices[0].translation[index]
    for i in range(1, len(objects)):
        position = matrices[i].translation.copy()
        position[index] += edge+spacing-(boxes[i]['min'][index] if boxes else position[index])
        matrices[i].translation = position
        edge = position[index]+boxes[i]['max'][index]-objects[i].matrix_world.translation[index] if boxes else position[index]
    return matrices


def grid_matrices(matrices, step, origin, axes):
    step = number(step, 'Grid step', 1e-5, 1e7)
    if not isinstance(axes, str) or not axes or set(axes)-set('XYZ') or len(set(axes)) != len(axes):raise ValueError('Axes must contain unique X/Y/Z letters')
    for matrix in matrices:
        position = matrix.translation.copy()
        for axis in axes:
            i = 'XYZ'.index(axis); value = (position[i]-origin[i])/step
            position[i] = origin[i]+math.copysign(math.floor(abs(value)+.5), value)*step
        matrix.translation = position
    return matrices


def dispatch(server, kind, p, bridge):
    if kind == 'get_blender_context':
        context = bpy.context; current = context.scene; tools = current.tool_settings
        return {'blender_version': bpy.app.version_string, 'scene': current.name,
                'workspace': context.workspace.name if context.workspace else None, 'mode': context.mode,
                'object_count': len(current.objects), 'selected_count': len(context.selected_objects),
                'active_object': context.object.name if context.object else None, 'cursor': cursor_info(),
                'coordinates': {'units': 'metres', 'up_axis': 'Z', 'rotation': 'XYZ Euler degrees'},
                'snapping': {'enabled': tools.use_snap, 'elements': sorted(tools.snap_elements)},
                'design_guide': 'ruster://guide/design', 'geometry_read_only': True}
    if kind == 'get_viewport_state':return viewport_state()
    if kind == 'measure_objects':
        objects = mcp_building.object_names([p['first'], p['second']], bridge)
        bpy.context.view_layer.update()
        delta = objects[1].matrix_world.translation-objects[0].matrix_world.translation
        include = p.get('include_bounds', True)
        if type(include) != bool:raise ValueError('include_bounds must be boolean')
        result = {'first': objects[0].name, 'second': objects[1].name,
                  'origin_delta': list(delta), 'origin_distance': delta.length, 'units': 'metres'}
        if include:
            a, b = loaded_bounds(objects)
            gap = [max(0., b['min'][i]-a['max'][i], a['min'][i]-b['max'][i]) for i in range(3)]
            result.update(bounds=[a, b], bounds_gap=gap, bounds_distance=math.hypot(*gap),
                          bounds_kind='world axis-aligned render bounds; not collision clearance')
        return result
    bridge.require_idle(); bridge.require_editor()
    if kind == 'set_viewport_state':return set_viewport(p, bridge)
    if kind == 'set_cursor':
        position = bridge.vector(p['position'], 'Cursor position')
        if any(abs(v) > 1e7 for v in position):raise ValueError('Cursor position exceeds supported coordinates')
        angles = bridge.vector(p.get('rotation_degrees', [0, 0, 0]), 'Cursor rotation')
        cursor = bpy.context.scene.cursor
        cursor.matrix = Matrix.LocRotScale(Vector(position), Euler(tuple(math.radians(v % 360.) for v in angles), 'XYZ').to_quaternion(), Vector((1, 1, 1)))
        app.redraw()
        return cursor_info()  # Like viewport navigation, Blender does not undo cursor state.
    else:
        objects = editable_roots(p['names'], bridge)
        bpy.context.view_layer.update()
        matrices = [obj.matrix_world.copy() for obj in objects]
        if kind == 'transform_objects_relative':
            offset = Vector(bridge.vector(p.get('offset', [0, 0, 0]), 'Offset'))
            angles = bridge.vector(p.get('rotation_degrees', [0, 0, 0]), 'Rotation delta')
            scale = Vector(bridge.vector(p.get('scale', [1, 1, 1]), 'Scale factors', True))
            pivot = Vector(bridge.vector(p['pivot'], 'Pivot')) if p.get('pivot') is not None else sum((m.translation for m in matrices), Vector())/len(matrices)
            rotation = Euler(tuple(math.radians(v % 360.) for v in angles), 'XYZ').to_quaternion()
            delta = Matrix.Translation(pivot+offset) @ Matrix.LocRotScale(Vector(), rotation, scale) @ Matrix.Translation(-pivot)
            apply_matrices(objects, [delta @ matrix for matrix in matrices], bridge)
            result = {'objects': mcp_building.object_infos(server, objects, bridge, False), 'pivot': list(pivot)}
        elif kind == 'radial_array_objects':
            count = mcp_building.bounded_int(p['count'], 1, mcp_prefab_ops.MAX_NEW, 'New copy count')
            center = bridge.vector(p['center'], 'Array center')
            axis = p.get('axis', 'Z')
            if axis not in {'X', 'Y', 'Z'}:raise ValueError('Use axis X/Y/Z')
            step = number(p['angle_degrees'], 'Angle step', -36000, 36000)
            rotation = [0., 0., 0.]; rotation['XYZ'.index(axis)] = step
            with mcp_prefab_ops.preserved_selection():
                roots, n = mcp_prefab_ops.clone_arrays(objects, count, (0, 0, 0), rotation, bridge, anchor=center)
            result = {'objects': [obj.name for obj in roots[:200]], 'root_count': len(roots),
                      'new_prefab_count': n, 'objects_truncated': len(roots) > 200, 'center': list(center)}
        elif kind == 'distribute_objects':
            axis = p.get('axis', 'X'); mode = p.get('mode', 'ORIGIN')
            apply_matrices(objects, distribution_matrices(objects, matrices, axis, mode, p['spacing']), bridge)
            result = {'objects': mcp_building.object_infos(server, objects, bridge, False), 'mode': mode}
        elif kind == 'snap_objects_to_grid':
            step = p['step']
            origin = bridge.vector(p.get('origin', [0, 0, 0]), 'Grid origin')
            axes = p.get('axes', 'XYZ')
            apply_matrices(objects, grid_matrices(matrices, step, origin, axes), bridge)
            result = {'objects': mcp_building.object_infos(server, objects, bridge, False)}
        else:raise ValueError('Unsupported Blender layout command')
    if bpy.context.preferences.edit.use_global_undo:bpy.ops.ed.undo_push(message='MCP: '+kind.replace('_', ' ').title())
    app.redraw()
    return result
