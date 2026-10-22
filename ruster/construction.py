"""Placement snapping and radial copies of whole, read-only prefab instances."""
import math
import uuid

import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, EnumProperty, FloatVectorProperty, IntProperty, PointerProperty
from mathutils import Matrix, Vector

_classes = []
_syncing = False
_restoring = False
_snapshots = {}
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


def update_symmetry(settings, context):
    """Resume from current placements, without replaying edits made while off."""
    global _syncing
    if _syncing or _restoring:return
    _syncing = True
    try:
        if context and context.view_layer:context.view_layer.update()
        remember_symmetry(settings.id_data)
    finally:
        _syncing = False


class RUSTER_PG_construction(bpy.types.PropertyGroup):
    object_snap: BoolProperty(name='Object Snapping', default=False, update=update_snapping,
        description='Snap moving placements to nearby original model geometry')
    snap_element: EnumProperty(name='Snap To', default='VERTEX', update=update_snapping,
        items=[('VERTEX', 'Vertices', 'Snap to model corners'),
               ('EDGE', 'Edges', 'Snap to model edges'), ('FACE', 'Faces', 'Snap to model surfaces')])
    angle_snap: EnumProperty(name='Rotation Step', default='OFF', update=update_snapping,
        items=[('OFF', 'Off', 'Free rotation'), ('45', '45°', 'Rotate in 45 degree steps'),
               ('90', '90°', 'Rotate in 90 degree steps')])
    symmetry: BoolProperty(name='Radial Symmetry', default=False, update=update_symmetry,
        description='Repeat new prefabs around the center; editing or deleting any member affects its set while enabled')
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
        remember_symmetry(context.scene)
        return created
    except Exception:
        for obj in created:bpy.data.objects.remove(obj, do_unlink=True)
        raise


def symmetry_groups(context_scene, previous=None):
    """Read saved links; snapshots retain IDs and matrices, never deleted objects."""
    roots = {obj['ruster_instance']: obj for obj in context_scene.objects
             if obj.get('ruster_kind') == 'PREFAB' and obj.get('ruster_instance') and not obj.library}
    groups = {}
    for instance, obj in roots.items():
        source = obj.get('ruster_symmetry_source')
        if source:groups.setdefault(source, {})[instance] = obj
    # Also recognize deletion of the only companion in a two-member set.
    for source in previous or ():
        if source in roots:groups.setdefault(source, {})
    for source, members in groups.items():
        if source in roots and not roots[source].get('ruster_symmetry_source'):
            members[source] = roots[source]
    return groups


def remember_symmetry(context_scene):
    _snapshots[context_scene.as_pointer()] = {
        source: {instance: obj.matrix_world.copy() for instance, obj in members.items()}
        for source, members in symmetry_groups(context_scene).items()}


def matrix_changed(matrix, previous):
    return any(abs(a-b) > 1e-6 for row, other in zip(matrix, previous) for a, b in zip(row, other))


@persistent
def suspend_symmetry(_dummy):
    global _restoring
    _restoring = True
    _snapshots.clear()


@persistent
def restore_symmetry(_dummy):
    global _restoring
    try:
        for context_scene in bpy.data.scenes:remember_symmetry(context_scene)
    finally:
        _restoring = False


@persistent
def sync_symmetry(context_scene, _depsgraph=None):
    global _syncing
    if _syncing or _restoring:return
    _syncing = True
    try:
        previous = _snapshots.get(context_scene.as_pointer(), {})
        groups = symmetry_groups(context_scene, previous)
        if context_scene.ruster_construction.symmetry:
            active = bpy.context.view_layer.objects.active if bpy.context.view_layer else None
            for source, members in groups.items():
                before = previous.get(source, {})
                if before.keys() - members.keys():
                    # Cover native Delete and scripted removal too. Linked model
                    # collections are untouched; only local placement roots go.
                    for obj in members.values():bpy.data.objects.remove(obj, do_unlink=True)
                    continue
                changed = [obj for instance, obj in members.items()
                           if instance in before and matrix_changed(obj.matrix_world, before[instance])]
                if not changed:continue
                driver = active if active in changed else changed[0]
                companion = next((obj for obj in members.values() if obj.get('ruster_symmetry_source')), None)
                if companion is None:continue
                center = companion['ruster_symmetry_center']
                angle = driver.get('ruster_symmetry_angle', 0.) if driver.get('ruster_symmetry_source') else 0.
                anchor = radial_matrix(driver.matrix_world, center, -angle)
                for obj in members.values():
                    target = radial_matrix(anchor, center, obj.get('ruster_symmetry_angle', 0.)
                                           if obj.get('ruster_symmetry_source') else 0.)
                    if obj != driver and matrix_changed(obj.matrix_world, target):obj.matrix_world = target
        remember_symmetry(context_scene)
    finally:
        _syncing = False


def symmetry_members(roots):
    """Return other members of selected sets, including placements inside groups."""
    selected = {obj for root in roots for obj in [root, *root.children_recursive]}
    sources = {obj.get('ruster_symmetry_source') or obj.get('ruster_instance') for obj in selected
               if obj.get('ruster_kind') == 'PREFAB'}
    sources.discard(None)
    return [obj for obj in bpy.context.scene.objects if obj not in selected and
            ((obj.get('ruster_symmetry_source') in sources) or
             (obj.get('ruster_kind') == 'PREFAB' and obj.get('ruster_instance') in sources))]


def deletion_roots(roots):
    """Expand enabled symmetry sets and keep each selected hierarchy only once."""
    from .placement import parent_chain
    roots = list(roots)
    if bpy.context.scene.ruster_construction.symmetry:roots.extend(symmetry_members(roots))
    selected = set(roots)
    return [obj for obj in roots if not any(parent in selected for parent in parent_chain(obj))]


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
        remember_symmetry(context.scene)
        return {'FINISHED'}


class RUSTER_OT_symmetry_original(bpy.types.Operator):
    bl_idname = 'ruster.symmetry_original'
    bl_label = 'Select Symmetry Original'
    bl_description = 'Select the first placement of this set; any member can move, rotate or scale the set'

    @classmethod
    def poll(cls, context):return bool(context.object and context.object.get('ruster_symmetry_source'))

    def execute(self, context):
        from .placement import select
        source_id = context.object.get('ruster_symmetry_source')
        source = next((obj for obj in context.scene.objects if obj.get('ruster_instance') == source_id), None)
        if source is None:
            self.report({'WARNING'}, 'The original was deleted; edit any remaining member or make the set independent')
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
        layout.label(text='Move, rotate or scale any member.')
        layout.label(text='Delete any member to delete its set.')
        layout.label(text='Turn symmetry off to edit independently.')
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
    for handlers in (bpy.app.handlers.undo_pre, bpy.app.handlers.redo_pre, bpy.app.handlers.load_pre):
        handlers.append(suspend_symmetry)
    for handlers in (bpy.app.handlers.undo_post, bpy.app.handlers.redo_post, bpy.app.handlers.load_post):
        handlers.append(restore_symmetry)
    restore_symmetry(None)


def unregister():
    bpy.app.handlers.depsgraph_update_post.remove(sync_symmetry)
    for handlers in (bpy.app.handlers.undo_pre, bpy.app.handlers.redo_pre, bpy.app.handlers.load_pre):
        handlers.remove(suspend_symmetry)
    for handlers in (bpy.app.handlers.undo_post, bpy.app.handlers.redo_post, bpy.app.handlers.load_post):
        handlers.remove(restore_symmetry)
    _snapshots.clear()
    del bpy.types.Scene.ruster_construction
    for cls in reversed(_classes):bpy.utils.unregister_class(cls)
    _classes.clear()
