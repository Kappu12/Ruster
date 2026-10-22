"""Placement snapping and radial copies of whole, read-only prefab instances."""
import math
import uuid

import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, EnumProperty, FloatVectorProperty, IntProperty, PointerProperty
from mathutils import Matrix, Vector

_classes = []
_syncing = False
COPY_KEYS = ('ruster_symmetry_source', 'ruster_symmetry_center', 'ruster_symmetry_angle')


def update_snapping(settings, context):
    tools = settings.id_data.tool_settings
    tools.use_snap = settings.object_snap or settings.angle_snap != 'OFF'
    tools.use_snap_translate = settings.object_snap
    tools.use_snap_rotate = settings.angle_snap != 'OFF'
    tools.use_snap_scale = False
    elements = {settings.snap_element} if settings.object_snap else set()
    if settings.angle_snap != 'OFF':elements.add('INCREMENT')
    tools.snap_elements = elements or {settings.snap_element}
    tools.snap_target = 'CLOSEST'
    # Original linked model parts are intentionally not selectable. They must
    # still participate in snapping, including collection instances.
    tools.use_snap_selectable = False
    tools.use_snap_align_rotation = False
    if settings.angle_snap != 'OFF':
        angle = math.radians(int(settings.angle_snap))
        tools.snap_angle_increment_3d = angle
        tools.snap_angle_increment_3d_precision = angle


class RUSTER_PG_construction(bpy.types.PropertyGroup):
    object_snap: BoolProperty(name='Object Snapping', default=False, update=update_snapping,
        description='Snap moving placements to nearby original model geometry')
    snap_element: EnumProperty(name='Snap To', default='VERTEX', update=update_snapping,
        items=[('VERTEX', 'Vertices', 'Snap to model corners'),
               ('EDGE', 'Edges', 'Snap to model edges'), ('FACE', 'Faces', 'Snap to model surfaces')])
    angle_snap: EnumProperty(name='Rotation Step', default='OFF', update=update_snapping,
        items=[('OFF', 'Off', 'Free rotation'), ('45', '45°', 'Rotate in 45 degree steps'),
               ('90', '90°', 'Rotate in 90 degree steps')])
    symmetry: BoolProperty(name='Radial Symmetry', default=False,
        description='Repeat newly added prefabs around the center; use Make Independent to unlink an existing set')
    sides: IntProperty(name='Sides', default=4, min=2, max=16,
        description='Total placements per set, including the original (applies to newly added prefabs)')
    center: FloatVectorProperty(name='Center', size=3, subtype='TRANSLATION',
        description='World center for new symmetry sets; rotation is around the vertical Z axis')


def clear_copy_link(obj):
    for key in COPY_KEYS:
        if key in obj:del obj[key]


def radial_matrix(matrix, center, angle):
    center = Vector(center)
    return Matrix.Translation(center) @ Matrix.Rotation(angle, 4, 'Z') @ Matrix.Translation(-center) @ matrix


def add_symmetry(source, context):
    """Create copies atomically. Selection stays on the editable original."""
    settings = context.scene.ruster_construction
    if not settings.symmetry:return []
    context.view_layer.update()
    created = []
    try:
        for index in range(1, settings.sides):
            obj = source.copy()
            source.users_collection[0].objects.link(obj)
            created.append(obj)
            obj['ruster_instance'] = uuid.uuid4().hex
            obj['ruster_symmetry_source'] = source['ruster_instance']
            obj['ruster_symmetry_center'] = list(settings.center)
            obj['ruster_symmetry_angle'] = math.tau * index / settings.sides
            if 'ruster_frame_on_load' in obj:del obj['ruster_frame_on_load']
            obj.matrix_world = radial_matrix(source.matrix_world, settings.center, obj['ruster_symmetry_angle'])
            obj.select_set(False)
        return created
    except Exception:
        for obj in created:bpy.data.objects.remove(obj, do_unlink=True)
        raise


@persistent
def sync_symmetry(context_scene, _depsgraph=None):
    global _syncing
    if _syncing:return
    _syncing = True
    try:
        roots = [obj for obj in context_scene.objects if obj.get('ruster_kind') == 'PREFAB']
        copies = [obj for obj in roots if obj.get('ruster_symmetry_source')]
        if not copies:return
        sources = {obj['ruster_instance']: obj for obj in roots
                   if obj.get('ruster_instance') and not obj.get('ruster_symmetry_source')}
        for obj in copies:
            source = sources.get(obj.get('ruster_symmetry_source'))
            if source is None:continue
            target = radial_matrix(source.matrix_world, obj['ruster_symmetry_center'], obj['ruster_symmetry_angle'])
            if any(abs(a-b) > 1e-6 for row, other in zip(obj.matrix_world, target) for a, b in zip(row, other)):
                obj.matrix_world = target
    finally:
        _syncing = False


def symmetry_members(roots):
    """Deleting an original also deletes its generated companions."""
    sources = {obj['ruster_instance'] for root in roots for obj in [root, *root.children_recursive]
               if obj.get('ruster_kind') == 'PREFAB' and obj.get('ruster_instance')}
    return [obj for obj in bpy.context.scene.objects if obj.get('ruster_symmetry_source') in sources]


class RUSTER_OT_symmetry_center(bpy.types.Operator):
    bl_idname = 'ruster.symmetry_center'
    bl_label = 'Center at 3D Cursor'
    bl_description = 'Use the 3D cursor as the center for newly added symmetry sets'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        context.scene.ruster_construction.center = context.scene.cursor.location
        return {'FINISHED'}


class RUSTER_OT_symmetry_release(bpy.types.Operator):
    bl_idname = 'ruster.symmetry_release'
    bl_label = 'Make Symmetry Set Independent'
    bl_description = 'Keep the copies in place and allow each member of the selected sets to be edited independently'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        from .placement import selected_prefabs
        selected = selected_prefabs()
        return bool(selected) and (any(obj.get('ruster_symmetry_source') for obj in selected)
                                   or bool(symmetry_members(selected)))

    def execute(self, context):
        from .placement import selected_prefabs
        selected = selected_prefabs()
        ids = {obj.get('ruster_symmetry_source') or obj.get('ruster_instance') for obj in selected}
        for obj in context.scene.objects:
            if obj.get('ruster_symmetry_source') in ids:clear_copy_link(obj)
        return {'FINISHED'}


class RUSTER_OT_symmetry_original(bpy.types.Operator):
    bl_idname = 'ruster.symmetry_original'
    bl_label = 'Select Symmetry Original'
    bl_description = 'Select the original placement to move, rotate or scale this entire symmetry set'

    @classmethod
    def poll(cls, context):return bool(context.object and context.object.get('ruster_symmetry_source'))

    def execute(self, context):
        from .placement import select
        source_id = context.object.get('ruster_symmetry_source')
        source = next((obj for obj in context.scene.objects if obj.get('ruster_instance') == source_id), None)
        if source is None:
            self.report({'WARNING'}, 'The original has been deleted; make this set independent')
            return {'CANCELLED'}
        select([source])
        return {'FINISHED'}


class RUSTER_OT_snap_rotation(bpy.types.Operator):
    bl_idname = 'ruster.snap_rotation'
    bl_label = 'Align Rotation to Step'
    bl_description = 'Round selected whole placements or groups to the chosen world rotation step'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.scene.ruster_construction.angle_snap != 'OFF' and bool(context.selected_objects)

    def execute(self, context):
        from .placement import selected_roots
        angle = math.radians(int(context.scene.ruster_construction.angle_snap))
        context.view_layer.update()
        for obj in selected_roots():
            if obj.get('ruster_symmetry_source'):continue
            location, rotation, scale = obj.matrix_world.decompose()
            euler = rotation.to_euler('XYZ')
            for axis in range(3):euler[axis] = round(euler[axis] / angle) * angle
            obj.matrix_world = Matrix.LocRotScale(location, euler, scale)
        return {'FINISHED'}


class RUSTER_PT_snapping(bpy.types.Panel):
    bl_label = 'Placement Snapping'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'HEADER'
    bl_ui_units_x = 14

    def draw(self, context):
        settings = context.scene.ruster_construction
        layout = self.layout
        layout.prop(settings, 'object_snap')
        col = layout.column()
        col.enabled = settings.object_snap
        col.prop(settings, 'snap_element', text='')
        layout.separator()
        layout.label(text='Rotation Step')
        layout.prop(settings, 'angle_snap', expand=True)
        layout.operator('ruster.snap_rotation')
        layout.separator()
        layout.label(text='Use Move (G) or Rotate (R).')
        layout.label(text='Ctrl temporarily toggles snapping.')


class RUSTER_PT_symmetry(bpy.types.Panel):
    bl_label = 'Radial Symmetry'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'HEADER'
    bl_ui_units_x = 16

    def draw(self, context):
        settings = context.scene.ruster_construction
        layout = self.layout
        layout.prop(settings, 'symmetry')
        col = layout.column()
        col.enabled = settings.symmetry
        col.prop(settings, 'sides')
        col.prop(settings, 'center')
        col.operator('ruster.symmetry_center', icon='CURSOR')
        layout.label(text='New prefabs repeat around Z.')
        layout.label(text='Move the original to move its copies.')
        layout.operator('ruster.symmetry_release', icon='UNLINKED')


class RUSTER_PT_construction(bpy.types.Panel):
    bl_label = 'Construction'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'
    bl_options = {'HIDE_HEADER'}

    @classmethod
    def poll(cls, context):return context.mode == 'OBJECT'

    def draw(self, context):
        settings = context.scene.ruster_construction
        wide = context.region.width > 120 * context.preferences.system.ui_scale
        layout = self.layout.column(align=True)
        layout.separator()
        layout.prop(settings, 'object_snap', text='Object Snap' if wide else '', icon='SNAP_ON', toggle=True)
        layout.popover(panel='RUSTER_PT_snapping', text='Snap Settings' if wide else '', icon='PREFERENCES')
        layout.separator()
        layout.prop(settings, 'symmetry', text='Symmetry' if wide else '', icon='MOD_ARRAY', toggle=True)
        layout.popover(panel='RUSTER_PT_symmetry', text='Symmetry Settings' if wide else '', icon='MOD_MIRROR')


def register():
    for cls in (RUSTER_PG_construction, RUSTER_OT_symmetry_center, RUSTER_OT_symmetry_release, RUSTER_OT_symmetry_original,
                RUSTER_OT_snap_rotation, RUSTER_PT_snapping, RUSTER_PT_symmetry, RUSTER_PT_construction):
        bpy.utils.register_class(cls)
        _classes.append(cls)
    bpy.types.Scene.ruster_construction = PointerProperty(type=RUSTER_PG_construction)
    bpy.app.handlers.depsgraph_update_post.append(sync_symmetry)


def unregister():
    bpy.app.handlers.depsgraph_update_post.remove(sync_symmetry)
    del bpy.types.Scene.ruster_construction
    for cls in reversed(_classes):bpy.utils.unregister_class(cls)
    _classes.clear()
