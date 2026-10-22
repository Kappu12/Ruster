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
        layout.operator('ruster.new_map', text='New Rust Map', icon='WORLD')
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
        layout.separator()
        layout.operator('ruster.group')
        layout.operator('ruster.ungroup')
        layout.operator('ruster.surface_snap')


class RUSTER_MT_map(bpy.types.Menu):
    bl_label = 'Map'
    def draw(self, context):
        self.layout.operator('ruster.new_map',icon='WORLD')
        self.layout.operator('ruster.path_add',icon='CURVE_PATH')
        self.layout.separator()
        self.layout.operator('ruster.height_import',icon='IMPORT')
        self.layout.operator('ruster.height_export',icon='EXPORT')
        self.layout.separator()
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
        layout.label(text='F3: Ruster commands',icon='INFO')
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
        layout.prop(state,'category',text='')
        layout.prop(state,'favorites_only',icon='SOLO_ON')
        from .core import settings,palettes
        favorites=set(palettes.favorite_ids(settings.load()))
        try:
            matches = catalog.search(scene.cache_dir(),state.query,limit=41,offset=state.query_page*40,
                category='' if state.category=='ALL' else state.category,
                favorites=favorites if state.favorites_only else None)
        except Exception:
            matches = []
        if not matches:
            layout.label(text='No matching local prefabs', icon='INFO')
            layout.operator('ruster.assets', text='Refresh Asset Catalog', icon='FILE_REFRESH').rebuild = True
        for uid, path, available in matches[:40]:
            row = layout.row(align=True)
            row.operator('ruster.favorite',text='',icon='SOLO_ON' if uid in favorites else 'SOLO_OFF').uid=str(uid)
            body=row.row(align=True);body.enabled=bool(available)
            body.operator('ruster.place', text=path.rsplit('/',1)[-1].removesuffix('.prefab'),
                         icon='ADD').uid = str(uid)
            body.operator('ruster.paint_asset',text='',icon='BRUSH_DATA').uid=str(uid)
        layout.label(text='Places at the 3D cursor')
        row=layout.row(align=True)
        previous=row.row();previous.enabled=state.query_page>0
        previous.operator('ruster.catalog_page',text='Previous').delta=-1
        row.label(text=f'Page {state.query_page+1}')
        next_=row.row();next_.enabled=len(matches)>40
        next_.operator('ruster.catalog_page',text='Next').delta=1


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
        if not obj or obj.get('ruster_kind') not in {'PREFAB','GROUP'}:
            layout.label(text='Select a prefab in the viewport or outliner')
            return
        layout.label(text=obj.name, icon='OUTLINER_OB_EMPTY')
        if obj.get('ruster_kind')=='PREFAB':
            layout.label(text='Prefab ID: ' + obj.get('ruster_uid', '?'))
            layout.label(text='Original Rust model · read-only',icon='LOCKED')
            from .protection import model_error
            problem=model_error(obj)
            if problem:layout.label(text='Restore this prefab model before exporting.',icon='ERROR')
            layout.operator('ruster.restore_models',icon='FILE_REFRESH')
        layout.use_property_split = True
        layout.prop(obj, 'location')
        layout.prop(obj,'rotation_quaternion' if obj.rotation_mode=='QUATERNION' else 'rotation_euler',text='Rotation')
        layout.prop(obj, 'scale')
        layout.use_property_split = False
        row = layout.row(align=True)
        row.operator('ruster.duplicate', icon='DUPLICATE')
        row.operator('ruster.delete', icon='TRASH')
        layout.separator()
        layout.operator('ruster.surface_snap')
        layout.operator('ruster.select_same')
        layout.operator('ruster.replace')
        layout.operator('ruster.scatter')
        row=layout.row(align=True)
        row.operator('ruster.group',text='Group')
        row.operator('ruster.ungroup',text='Ungroup')
        row=layout.row(align=True)
        row.operator('ruster.assembly_import',text='Import Group')
        row.operator('ruster.assembly_export',text='Export Group')


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
            layout.operator('ruster.cancel_assets',icon='CANCEL')
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
        layout.label(text='Terrain, paths and prefabs export to .map.')
        layout.label(text='Use the Terrain and Paths panels to edit.')


class RUSTER_PT_terrain(bpy.types.Panel):
    bl_label='Terrain'
    bl_space_type='VIEW_3D'
    bl_region_type='UI'
    bl_category='Ruster'
    @classmethod
    def poll(cls,context):
        return is_map(context)
    def draw(self,context):
        brush=context.scene.ruster_brush
        layout=self.layout
        layout.use_property_split=True
        layout.prop(brush,'layer')
        if brush.layer in {'terrain','water'}:
            layout.prop(brush,'tool')
            if brush.tool=='FLATTEN':layout.prop(brush,'height')
            if brush.tool=='TERRACE':layout.prop(brush,'terrace')
            if brush.tool=='NOISE':layout.prop(brush,'seed')
            if brush.tool=='CLONE':layout.operator('ruster.clone_source')
            if brush.tool in {'STAMP','SLOPE'}:
                layout.prop(brush,'height');layout.prop(brush,'rotation')
            if brush.tool=='STAMP':layout.prop(brush,'stamp_path')
            if brush.tool=='SLOPE':layout.prop(brush,'slope')
        elif brush.layer in {'splat','biome','topology'}:
            layout.prop(brush,brush.layer)
        if brush.layer in {'topology','alpha','splat','biome'}:
            layout.prop(brush,'remove')
        for prop in ('radius','strength','falloff','shape'):
            layout.prop(brush,prop)
        layout.use_property_split=False
        layout.operator('wm.tool_set_by_id',text='Paint in Viewport',icon='BRUSH_DATA').name='ruster.terrain_brush'
        layout.operator('ruster.terrain_apply',text='Apply at 3D Cursor')
        layout.label(text='Alt: invert · Shift: smooth')
        layout.prop(brush,'use_mask')
        if brush.use_mask:
            col=layout.column(align=True)
            for prop in ('minimum','maximum','min_slope','max_slope'):col.prop(brush,prop)
        layout.separator()
        layout.prop(brush,'display')
        layout.operator('ruster.terrain_overlay',text='Update Overlay',icon='FILE_REFRESH')
        row=layout.row(align=True)
        row.operator('ruster.height_import',text='Import Height')
        row.operator('ruster.height_export',text='Export Height')
        row=layout.row(align=True)
        row.operator('ruster.terrain_bridge',text='Set Bridge Start').set_start=True
        row.operator('ruster.terrain_bridge',text='Grade to Cursor')
        layout.operator('ruster.generate_island',icon='WORLD')
        layout.separator()
        layout.prop(context.scene.ruster,'preview_resolution')
        layout.operator('ruster.terrain_detail')


class RUSTER_PT_paint(bpy.types.Panel):
    bl_label='Prefab Paint'
    bl_space_type='VIEW_3D'
    bl_region_type='UI'
    bl_category='Ruster'
    @classmethod
    def poll(cls,context):return is_map(context)
    def draw(self,context):
        layout=self.layout;brush=context.scene.ruster_paint
        layout.use_property_split=True
        layout.prop(brush,'palette')
        if brush.palette=='SINGLE':layout.prop(brush,'uid')
        for prop in ('spacing','random_yaw','min_scale','max_scale','seed','align','offset','max_slope','respect_holes'):
            layout.prop(brush,prop)
        layout.use_property_split=False
        layout.operator('wm.tool_set_by_id',text='Paint Prefabs in Viewport',icon='BRUSH_DATA').name='ruster.prefab_brush'
        layout.label(text='Drag: place · Esc: cancel the whole stroke')
        layout.label(text='Spacing uses placement origins.')
        layout.label(text='Game prefab geometry stays read-only.',icon='LOCKED')


class RUSTER_PT_paths(bpy.types.Panel):
    bl_label='Paths'
    bl_space_type='VIEW_3D'
    bl_region_type='UI'
    bl_category='Ruster'
    @classmethod
    def poll(cls,context):return is_map(context)
    def draw(self,context):
        layout=self.layout
        layout.operator_menu_enum('ruster.path_add','kind',text='Add Path',icon='CURVE_PATH')
        obj=context.object
        if not obj or obj.get('ruster_kind')!='PATH':
            layout.label(text='Select a path to edit its nodes and settings.');return
        layout.prop(obj,'name',text='Name')
        layout.operator('object.mode_set',text='Finish Editing Nodes' if obj.mode=='EDIT' else 'Edit Path Nodes').mode='OBJECT' if obj.mode=='EDIT' else 'EDIT'
        layout.label(text='Select nodes · G move · E extend · X delete')
        layout.use_property_split=True
        state=obj.ruster_path
        for prop in ('kind','width','inner_padding','outer_padding','inner_fade','outer_fade',
                     'terrain_offset','mesh_offset','random_scale','splat','topology','spline','start','end'):
            layout.prop(state,prop)
        layout.use_property_split=False
        layout.operator('ruster.path_snap')
        layout.operator('ruster.path_grade')


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
    layout.menu('VIEW3D_MT_select_edit_curve' if context.mode=='EDIT_CURVE' else 'VIEW3D_MT_select_object', text='Select')
    if context.mode=='EDIT_CURVE':
        layout.operator('object.mode_set',text='Finish Path').mode='OBJECT'
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
    layout.operator('ruster.restore_models',icon='FILE_REFRESH')


def readonly_source_menu(self,context):
    self.layout.label(text='Original Rust models are read-only',icon='LOCKED')
    self.layout.operator('ruster.restore_models',icon='FILE_REFRESH')


def properties_header(self, context):
    self.layout.label(text='Rust Map', icon='WORLD')


def topbar(self,context):
    layout=self.layout
    if context.region.alignment=='RIGHT':
        layout.template_reports_banner()
        layout.template_running_jobs()
        layout.label(text=context.scene.ruster.title,icon='WORLD')
    else:
        bpy.types.TOPBAR_MT_editor_menus.draw_collapsible(context,layout)
        layout.separator()
        layout.label(text='Rust Map')


def close_map_timeline():
    from . import editing,painting
    if editing.stroke_active or painting.stroke_active:return .5
    for window in bpy.context.window_manager.windows:
        if window.scene.ruster.mode!='MAP':continue
        for area in list(window.screen.areas):
            if area.type=='DOPESHEET_EDITOR' and area.ui_type=='TIMELINE':
                with bpy.context.temp_override(window=window,area=area):
                    bpy.ops.screen.area_close()
    return None


def map_workspace():
    # Focus map mode through native headers. Retaining inactive workspaces avoids
    # invalidating Blender's live editor event handlers during a map import.
    for window in bpy.context.window_manager.windows:
        window.workspace.name='Rust Map'
        for area in window.screen.areas:
            if area.type=='PROPERTIES':area.spaces.active.context='SCENE'
            area.tag_redraw()
    # Screen operators may clear the caller's context; run this after import.
    if not bpy.app.background and not bpy.app.timers.is_registered(close_map_timeline):
        bpy.app.timers.register(close_map_timeline,first_interval=.1)


def register():
    classes = [RUSTER_MT_file, RUSTER_MT_edit, RUSTER_MT_map, RUSTER_MT_assets,
               RUSTER_PT_map, RUSTER_PT_prefabs, RUSTER_PT_selection, RUSTER_PT_assets,
               RUSTER_PT_properties,RUSTER_PT_terrain,RUSTER_PT_paths,RUSTER_PT_paint]
    for cls in classes:
        bpy.utils.register_class(cls)
        _classes.append(cls)
    patch_draw(bpy.types.TOPBAR_HT_upper_bar,topbar)
    patch_draw(bpy.types.TOPBAR_MT_editor_menus, menus)
    patch_draw(bpy.types.VIEW3D_HT_header, view_header)
    patch_draw(bpy.types.VIEW3D_MT_object_context_menu, context_menu)
    for cls in (bpy.types.OUTLINER_MT_context_menu,bpy.types.OUTLINER_MT_object,bpy.types.OUTLINER_MT_collection):
        patch_draw(cls,context_menu)
    for cls in (bpy.types.OUTLINER_MT_id_data,bpy.types.OUTLINER_MT_liboverride,bpy.types.OUTLINER_MT_edit_datablocks):
        patch_draw(cls,readonly_source_menu)
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
    if bpy.app.timers.is_registered(close_map_timeline):
        bpy.app.timers.unregister(close_map_timeline)
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
