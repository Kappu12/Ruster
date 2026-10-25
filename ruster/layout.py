"""Native whole-prefab layout tools, shared with the typed automation backend."""
import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty

from . import scene, placement, mcp_blender, mcp_prefab_ops, mcp_bridge, map_prefabs
from .ui_style import action, properties, wrapped

_classes = []
AXES = [(axis, axis, 'World '+axis+' axis') for axis in 'XYZ']
OPERATIONS = [('LINEAR', 'Linear Array', 'Repeat selected placements or groups with a world offset'),
              ('RADIAL', 'Radial Array', 'Create independent rotated copies around a center'),
              ('ALIGN', 'Align Bounds', 'Align loaded model bounds to the active selection'),
              ('DISTRIBUTE', 'Distribute', 'Space placements in their current axis order'),
              ('GRID', 'Snap to Grid', 'Snap origins to a world grid'),
              ('PLANE', 'Place on Plane', 'Place the bottom bound of each selected model on a plane')]


class RUSTER_OT_layout(bpy.types.Operator):
    bl_idname = 'ruster.layout'
    bl_label = 'Prefab Layout'
    bl_description = 'Arrange whole original prefabs with exact world transforms'
    bl_options = {'REGISTER', 'UNDO'}
    operation: EnumProperty(items=OPERATIONS, default='LINEAR')
    count: IntProperty(name='New Copies', default=3, min=1, max=2000)
    offset: FloatVectorProperty(name='Step Offset', size=3, default=(3, 0, 0), subtype='TRANSLATION')
    center: FloatVectorProperty(name='Center / Grid Origin', size=3, subtype='TRANSLATION')
    axis: EnumProperty(name='Axis', items=AXES, default='X')
    angle: FloatProperty(name='Angle per Copy', default=90, min=-36000, max=36000,
                         description='Degrees per new copy; four sides use three new copies at 90 degrees')
    bound: EnumProperty(name='Bound', items=[('MIN', 'Minimum', ''), ('CENTER', 'Center', ''), ('MAX', 'Maximum', '')])
    mode: EnumProperty(name='Spacing Mode', items=[('ORIGIN', 'Origins', 'Distance between origins'),
                        ('BOUNDS_GAP', 'Bounds Gap', 'Gap between loaded render bounds; negative values overlap')])
    spacing: FloatProperty(name='Spacing', default=3, min=-1e7, max=1e7, unit='LENGTH')
    step: FloatProperty(name='Grid Size', default=1, min=1e-5, max=1e7, unit='LENGTH')
    axes: EnumProperty(name='Grid Axes', default='XYZ', items=[(axis, axis, '') for axis in ('XYZ', 'XY', 'XZ', 'YZ', 'X', 'Y', 'Z')])
    target: FloatProperty(name='Plane Coordinate', default=0, min=-1e7, max=1e7, unit='LENGTH')
    cursor: BoolProperty(name='Use 3D Cursor', default=False,
                         description='Use the current 3D cursor as the array center or grid origin')

    @classmethod
    def poll(cls, context):return context.mode == 'OBJECT' and bool(placement.selected_roots())

    def invoke(self, context, event):
        if self.operation in {'RADIAL', 'PLANE'}:self.axis = 'Z'
        return context.window_manager.invoke_props_dialog(self, width=380)

    def draw(self, context):
        fields = properties(self.layout)
        fields.prop(self, 'operation', text='Tool')
        if self.operation in {'LINEAR', 'RADIAL'}:fields.prop(self, 'count')
        if self.operation == 'LINEAR':fields.prop(self, 'offset')
        if self.operation in {'RADIAL', 'ALIGN', 'DISTRIBUTE', 'PLANE'}:fields.prop(self, 'axis', expand=True)
        if self.operation == 'RADIAL':fields.prop(self, 'angle')
        if self.operation == 'ALIGN':
            fields.prop(self, 'bound')
            wrapped(self.layout, context, 'The active selected object is the reference.')
        if self.operation == 'DISTRIBUTE':
            fields.prop(self, 'mode');fields.prop(self, 'spacing')
            wrapped(self.layout, context, 'Ordered by current axis position; the first stays fixed.')
        if self.operation == 'GRID':fields.prop(self, 'step');fields.prop(self, 'axes')
        if self.operation in {'RADIAL', 'GRID'}:
            fields.prop(self, 'cursor')
            row = fields.column();row.enabled = not self.cursor;row.prop(self, 'center')
        if self.operation == 'PLANE':fields.prop(self, 'target')

    def execute(self, context):
        try:
            mcp_bridge.require_idle();mcp_bridge.require_editor()
            context.view_layer.update()
            roots = sorted(placement.selected_roots(), key=lambda obj: obj.name)
            if not 1 <= len(roots) <= 200:raise ValueError('Select 1–200 whole placements or groups')
            center = list(context.scene.cursor.location if self.cursor else self.center)
            if self.operation in {'LINEAR', 'RADIAL'}:
                rotation = [0., 0., 0.]
                if self.operation == 'RADIAL':rotation['XYZ'.index(self.axis)] = self.angle
                mcp_prefab_ops.clone_arrays(roots, self.count, self.offset if self.operation == 'LINEAR' else (0, 0, 0),
                                           rotation, mcp_bridge, anchor=center if self.operation == 'RADIAL' else None)
            else:
                roots = mcp_blender.editable_roots([obj.name for obj in roots], mcp_bridge)
                if self.operation in {'ALIGN', 'PLANE'}:
                    active = context.view_layer.objects.active
                    if self.operation == 'ALIGN':
                        if active not in roots:raise ValueError('Make one selected placement or group active as the reference')
                        roots.remove(active);roots.insert(0, active)
                    mcp_prefab_ops.align(roots, self.axis, self.bound if self.operation == 'ALIGN' else 'MIN',
                                        None if self.operation == 'ALIGN' else self.target, mcp_bridge)
                else:
                    if self.operation == 'DISTRIBUTE':roots.sort(key=lambda obj: (obj.matrix_world.translation['XYZ'.index(self.axis)], obj.name))
                    matrices = [obj.matrix_world.copy() for obj in roots]
                    if self.operation == 'DISTRIBUTE':
                        matrices = mcp_blender.distribution_matrices(roots, matrices, self.axis, self.mode, self.spacing)
                    elif self.operation == 'GRID':matrices = mcp_blender.grid_matrices(matrices, self.step, center, self.axes)
                    mcp_blender.apply_matrices(roots, matrices, mcp_bridge)
            return {'FINISHED'}
        except Exception as error:self.report({'ERROR'}, str(error));return {'CANCELLED'}


class RUSTER_OT_composition_check(bpy.types.Operator):
    bl_idname = 'ruster.composition_check'
    bl_label = 'Check Composition'
    bl_description = 'Inspect export errors, overlapping copies, mirrored placements and imported IO scaling'

    def invoke(self, context, event):
        self.errors, self.notes = map_prefabs.validate()
        return context.window_manager.invoke_props_dialog(self, width=540)

    def draw(self, context):
        errors = getattr(self, 'errors', [])
        for message in errors[:12]:wrapped(self.layout, context, message, icon='error', width=500)
        if len(errors) > 12:self.layout.label(text=f'{len(errors)-12} more errors; fix these and check again.')
        for message in getattr(self, 'notes', []):wrapped(self.layout, context, message, icon='info', width=500)
        wrapped(self.layout, context, 'Rust exports original prefab IDs and transforms. Editor names may contain spaces. Networked doors, IO and deployables use unit scale; test gameplay in Rust.')

    def execute(self, context):
        errors, notes = map_prefabs.validate()
        self.report({'WARNING'} if errors else {'INFO'}, f'{len(errors)} export errors. '+ '; '.join(notes[:3]))
        return {'FINISHED'}


class RUSTER_OT_select_composition_issue(bpy.types.Operator):
    bl_idname = 'ruster.select_composition_issue'
    bl_label = 'Select Composition Issues'
    bl_description = 'Select matching placements without modifying or deleting them'
    issue: EnumProperty(items=[('DUPLICATES', 'Overlapping Copies', ''), ('MIRRORED', 'Mirrored Placements', ''),
                               ('SCALED_IO', 'Scaled Imported IO', '')])

    def execute(self, context):
        context.view_layer.update()
        objects = next((roots for code, roots, _message in map_prefabs.placement_warnings(scene.prefab_roots()) if code == self.issue), [])
        if objects:placement.select(objects)
        self.report({'INFO'}, f'{len(objects)} matching placements')
        return {'FINISHED'}


class RUSTER_PT_layout(bpy.types.Panel):
    bl_label = 'Prefab Layout'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Ruster'
    bl_options = {'DEFAULT_CLOSED'}
    bl_order = 20

    def draw(self, context):
        for operation, label, _description in OPERATIONS:
            action(self.layout, 'ruster.layout', text=label+'…').operation = operation
        self.layout.separator()
        action(self.layout, 'ruster.composition_check')
        for code, label in [('DUPLICATES', 'Select Overlapping Copies'), ('MIRRORED', 'Select Mirrored'), ('SCALED_IO', 'Select Scaled Imported IO')]:
            action(self.layout, 'ruster.select_composition_issue', text=label).issue = code


def register():
    for cls in (RUSTER_OT_layout, RUSTER_OT_composition_check, RUSTER_OT_select_composition_issue, RUSTER_PT_layout):
        bpy.utils.register_class(cls);_classes.append(cls)


def unregister():
    for cls in reversed(_classes):bpy.utils.unregister_class(cls)
    _classes.clear()
