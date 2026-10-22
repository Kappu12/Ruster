"""Native Blender UI; map mode exposes supported Rust actions only."""
import bpy
from . import scene
from .assets import catalog

_classes = []
_draws = []
_polls = []


def is_map(context):
    return bool(context.scene and hasattr(context.scene, 'ruster') and context.scene.ruster.mode == 'MAP')


class RUSTER_MT_file(bpy.types.Menu):
    bl_label = 'Ruster'
    def draw(self, context):
        layout = self.layout
        layout.operator('ruster.welcome', text='Start', icon='HOME')
        layout.operator('ruster.new', text='New Project', icon='FILE_NEW')
        layout.operator('ruster.open', text='Open Map or Project…', icon='FILE_FOLDER')
        layout.separator()
        layout.operator('ruster.save', text='Save Project', icon='FILE_TICK')
        layout.operator('ruster.save', text='Save Project As…').save_as = True
        if is_map(context):
            layout.separator()
            layout.operator('ruster.export_map', text='Export Rust Map…', icon='EXPORT')
        layout.separator()
        layout.operator('ruster.setup', text='Rust Installation…', icon='PREFERENCES')
        layout.separator()
        layout.operator('wm.quit_blender', text='Quit Ruster', icon='QUIT')


class RUSTER_MT_edit(bpy.types.Menu):
    bl_label = 'Edit'
    def draw(self, context):
        layout = self.layout
        layout.operator('ed.undo', icon='LOOP_BACK')
        layout.operator('ed.redo', icon='LOOP_FORWARDS')
        layout.separator()
        layout.operator('ruster.duplicate', icon='DUPLICATE')
        layout.operator('ruster.delete', icon='TRASH')


class RUSTER_MT_map(bpy.types.Menu):
    bl_label = 'Map'
    def draw(self, context):
        self.layout.operator('ruster.validate', icon='CHECKMARK')
        self.layout.operator('ruster.export_map', icon='EXPORT')


class RUSTER_MT_assets(bpy.types.Menu):
    bl_label = 'Assets'
    def draw(self, context):
        layout = self.layout
        layout.operator('ruster.assets', text='Load Map Assets', icon='IMPORT')
        layout.operator('ruster.assets', text='Refresh Rust Asset Catalog', icon='FILE_REFRESH').rebuild = True
        layout.operator('ruster.asset_report', icon='TEXT')
        layout.separator()
        layout.operator('ruster.setup', text='Rust Installation…', icon='FILE_FOLDER')


class RUSTER_PT_map(bpy.types.Panel):
    bl_label = 'Map'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Ruster'

    @classmethod
    def poll(cls, context):
        return is_map(context)

    def draw(self, context):
        state = context.scene.ruster
        layout = self.layout
        layout.label(text=state.title, icon='WORLD')
        row = layout.row()
        row.label(text=f'{state.map_size:,} m')
        row.label(text=f'{len(scene.prefab_roots()):,} prefabs')
        layout.separator()
        layout.operator('ruster.save', text='Save Project', icon='FILE_TICK')
        layout.operator('ruster.validate', icon='CHECKMARK')
        layout.operator('ruster.export_map', icon='EXPORT')


class RUSTER_PT_prefabs(bpy.types.Panel):
    bl_label = 'Prefab Browser'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Ruster'

    @classmethod
    def poll(cls, context):
        return is_map(context)

    def draw(self, context):
        layout = self.layout
        state = context.scene.ruster
        layout.prop(state, 'query', text='', icon='VIEWZOOM')
        try:
            matches = catalog.search(scene.cache_dir(), state.query, limit=40)
        except Exception:
            matches = []
        if not matches:
            layout.label(text='No matching local prefabs', icon='INFO')
            layout.operator('ruster.assets', text='Refresh Asset Catalog', icon='FILE_REFRESH').rebuild = True
        for uid, path, available in matches:
            row = layout.row(align=True)
            row.enabled = bool(available)
            row.operator('ruster.place', text=path.rsplit('/',1)[-1].removesuffix('.prefab'),
                         icon='ADD').uid = str(uid)
        layout.label(text='Places at the 3D cursor')
        if len(matches) == 40:
            layout.label(text='Refine your search for more results')


class RUSTER_PT_selection(bpy.types.Panel):
    bl_label = 'Placement'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Ruster'

    @classmethod
    def poll(cls, context):
        return is_map(context)

    def draw(self, context):
        layout = self.layout
        obj = context.active_object
        if not obj or obj.get('ruster_kind') != 'PREFAB':
            layout.label(text='Select a prefab in the viewport or outliner')
            return
        layout.label(text=obj.name, icon='OUTLINER_OB_EMPTY')
        layout.label(text='Prefab ID: ' + obj.get('ruster_uid', '?'))
        layout.use_property_split = True
        layout.prop(obj, 'location')
        layout.prop(obj, 'rotation_quaternion', text='Rotation')
        layout.prop(obj, 'scale')
        layout.use_property_split = False
        row = layout.row(align=True)
        row.operator('ruster.duplicate', icon='DUPLICATE')
        row.operator('ruster.delete', icon='TRASH')


class RUSTER_PT_assets(bpy.types.Panel):
    bl_label = 'Local Rust Assets'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Ruster'

    def draw(self, context):
        layout = self.layout
        state = context.scene.ruster
        # Wrap the status without introducing a custom visual style.
        status = state.asset_status
        while status:
            layout.label(text=status[:42])
            status = status[42:]
        if state.busy:
            layout.label(text='You can keep editing while assets load', icon='TIME')
        else:
            layout.operator('ruster.assets', text='Load Map Assets', icon='IMPORT')
            layout.operator('ruster.assets', text='Refresh Asset Catalog', icon='FILE_REFRESH').rebuild = True
        layout.operator('ruster.setup', text='Rust Installation', icon='FILE_FOLDER')
        layout.operator('ruster.asset_report', icon='TEXT')


class RUSTER_PT_properties(bpy.types.Panel):
    bl_label = 'Rust Map'
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'scene'

    @classmethod
    def poll(cls, context):
        return is_map(context)

    def draw(self, context):
        layout = self.layout
        state = context.scene.ruster
        layout.label(text=state.title, icon='WORLD')
        layout.label(text=f'Map size: {state.map_size:,} m')
        layout.separator()
        layout.operator('ruster.validate', icon='CHECKMARK')
        layout.operator('ruster.export_map', icon='EXPORT')
        layout.separator()
        layout.label(text='Terrain and paths are protected previews.')
        layout.label(text='This version exports prefab placement edits.')


def patch_draw(cls, replacement):
    original = cls.draw
    _draws.append((cls, original))
    def draw(self, context):
        if is_map(context):
            replacement(self, context)
        else:
            original(self, context)
            if cls == bpy.types.TOPBAR_MT_editor_menus:
                self.layout.menu('RUSTER_MT_file', text='Ruster')
    cls.draw = draw


def menus(self, context):
    layout = self.layout
    layout.menu('RUSTER_MT_file', text='Ruster')
    layout.menu('RUSTER_MT_edit')
    layout.menu('RUSTER_MT_map')
    layout.menu('RUSTER_MT_assets')


def view_header(self, context):
    layout = self.layout
    layout.menu('VIEW3D_MT_view', text='View')
    layout.menu('VIEW3D_MT_select_object', text='Select')
    layout.separator()
    row = layout.row(align=True)
    row.operator('wm.tool_set_by_id', text='', icon='RESTRICT_SELECT_OFF').name = 'builtin.select_box'
    row.operator('wm.tool_set_by_id', text='Move').name = 'builtin.move'
    row.operator('wm.tool_set_by_id', text='Rotate').name = 'builtin.rotate'
    row.operator('wm.tool_set_by_id', text='Scale').name = 'builtin.scale'
    layout.separator()
    layout.prop(context.scene.tool_settings, 'use_snap', text='', icon='SNAP_ON')
    layout.prop(context.scene.tool_settings, 'snap_elements', text='')
    layout.separator_spacer()
    space = context.space_data
    layout.prop(space.overlay, 'show_overlays', text='', icon='OVERLAY')
    layout.prop(space.shading, 'type', text='', expand=True)


def context_menu(self, context):
    layout = self.layout
    layout.operator('transform.translate', text='Move')
    layout.operator('transform.rotate', text='Rotate')
    layout.operator('transform.resize', text='Scale')
    layout.separator()
    layout.operator('ruster.duplicate', icon='DUPLICATE')
    layout.operator('ruster.delete', icon='TRASH')


def properties_header(self, context):
    self.layout.label(text='Rust Map', icon='WORLD')


def map_workspace():
    # Keep the current useful viewport/outliner arrangement; omit unrelated
    # Animation, Compositing, Geometry Nodes and rendering workspaces in map mode.
    current = bpy.context.window.workspace if bpy.context.window else None
    if current:
        current.name = 'Rust Map'
        unused = [workspace for workspace in bpy.data.workspaces if workspace != current]
        if unused:
            bpy.data.batch_remove(ids=unused)
    for window in bpy.context.window_manager.windows:
        for area in list(window.screen.areas):
            if area.type == 'PROPERTIES':
                area.spaces.active.context = 'SCENE'
            elif area.type == 'DOPESHEET_EDITOR':
                # Close the timeline in a GUI context, leaving the main view larger.
                if not bpy.app.background:
                    try:
                        with bpy.context.temp_override(window=window, area=area):
                            bpy.ops.screen.area_close()
                    except (RuntimeError, TypeError):
                        pass


def register():
    classes = [RUSTER_MT_file, RUSTER_MT_edit, RUSTER_MT_map, RUSTER_MT_assets,
               RUSTER_PT_map, RUSTER_PT_prefabs, RUSTER_PT_selection, RUSTER_PT_assets,
               RUSTER_PT_properties]
    for cls in classes:
        bpy.utils.register_class(cls)
        _classes.append(cls)
    patch_draw(bpy.types.TOPBAR_MT_editor_menus, menus)
    patch_draw(bpy.types.VIEW3D_HT_header, view_header)
    patch_draw(bpy.types.VIEW3D_MT_object_context_menu, context_menu)
    patch_draw(bpy.types.PROPERTIES_HT_header, properties_header)
    # Suppress unrelated built-in property panels only in Rust map mode.
    # Class-local originals are restored exactly on unregister.
    for name in dir(bpy.types):
        cls = getattr(bpy.types, name)
        if not isinstance(cls, type) or not issubclass(cls, bpy.types.Panel) or name.startswith('RUSTER_'):
            continue
        space = getattr(cls, 'bl_space_type', '')
        if space != 'PROPERTIES':
            continue
        own_poll = cls.__dict__.get('poll')
        original = getattr(cls, 'poll', None)
        _polls.append((cls, own_poll))
        def make_poll(original):
            def poll(panel, context):
                return False if is_map(context) else (original(context) if original else True)
            return poll
        cls.poll = classmethod(make_poll(original))


def unregister():
    for cls, poll in reversed(_polls):
        if poll is None:
            delattr(cls, 'poll')
        else:
            cls.poll = poll
    _polls.clear()
    for cls, draw in reversed(_draws):
        cls.draw = draw
    _draws.clear()
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
    _classes.clear()
