"""Rust-focused prefab composition and interchange tools."""
import base64
import math
import struct
from pathlib import Path
import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty, StringProperty
from bpy_extras.io_utils import ExportHelper, ImportHelper
from mathutils import Matrix, Vector

from . import app, scene, placement
from .assets import catalog
from .core import wire
from .core.asset_categories import GROUPS
from .core.project import atomic_write
from .core.rust_map import prefab_transform, update_transform
from .core.rustedit_prefab import RustEditPrefab

_classes, _keymaps = [], []
_menu_cache = {}
MENU_CACHE_LIMIT = 2
_category_menus = {}
_model_items = []

# Scalar settings verified against the installed SerializedIOEntity contract.
IO_SETTINGS = {
    'access_level': (5,'int',0), 'door_effect': (6,'int',0),
    'timer_length': (7,'float',0.), 'frequency': (8,'int',0),
    'unlimited_ammo': (9,'bool',False), 'peacekeeper': (10,'bool',False),
    'weapon': (11,'str',''), 'branch_amount': (12,'int',0),
    'counter_target': (13,'int',0), 'camera_identifier': (14,'str',''),
    'counter_passthrough': (15,'bool',False), 'floors': (16,'int',1),
    'phone_name': (17,'str',''),
}


def io_value(fields, name):
    number, kind, default = IO_SETTINGS[name]
    raw = wire.get(fields, number)
    if raw is None:return default
    if kind == 'str':return raw.decode('utf8')
    if kind == 'float':return struct.unpack('<f',raw)[0]
    if kind == 'bool':return bool(raw)
    return raw - (1 << 64) if raw >= (1 << 63) else raw


def io_source(root):
    if not root or root.get('ruster_kind') != 'PREFAB':return None
    group = next((obj for obj in placement.parent_chain(root) if obj.get('ruster_prefab_source')),None)
    if not group:return None
    text = bpy.data.texts.get(group['ruster_prefab_source'])
    if not text:return None
    source = RustEditPrefab.read(base64.b64decode(text.as_string(),validate=True))
    position = prefab_transform(wire.parse(base64.b64decode(root['ruster_record'])))[0]
    found = []
    for index, field in enumerate(source.fields):
        if field.number != 5 or field.wire != 2:continue
        entries = wire.parse(field.value)
        for entry_index, entry in enumerate(entries):
            if entry.number != 1 or entry.wire != 2:continue
            entity = wire.parse(entry.value)
            value = wire.get(entity,2)
            if value is not None and max(abs(a-b) for a,b in zip(wire.vector(value),position)) < .001:
                found.append((text,source,index,entries,entry_index,entity))
    if len(found)>1:raise ValueError('Multiple IO entities share this position')
    return found[0] if found else None


class RUSTER_OT_io_settings(bpy.types.Operator):
    bl_idname = 'ruster.io_settings'
    bl_label = 'Rust IO Settings'
    bl_options = {'REGISTER','UNDO'}
    access_level: IntProperty(name='Card Access Level',min=0,max=3)
    door_effect: IntProperty(name='Door Effect',min=-1,max=3)
    timer_length: FloatProperty(name='Timer / Access Duration',min=0,max=86400,unit='TIME')
    frequency: IntProperty(name='Radio Frequency',min=0,max=9999999)
    unlimited_ammo: BoolProperty(name='Unlimited Turret Ammo')
    peacekeeper: BoolProperty(name='Peacekeeper Turret')
    weapon: StringProperty(name='Turret Weapon Shortname',maxlen=256)
    branch_amount: IntProperty(name='Branch Amount',min=0)
    counter_target: IntProperty(name='Counter Target',min=0)
    camera_identifier: StringProperty(name='Camera Identifier',maxlen=256)
    counter_passthrough: BoolProperty(name='Counter Passthrough')
    floors: IntProperty(name='Elevator Floors',min=1,max=100,default=1)
    phone_name: StringProperty(name='Phone Name',maxlen=256)

    def invoke(self,context,event):
        try:
            found = io_source(context.active_object)
            if not found:raise ValueError('Select an imported prefab with existing RustEdit IO data')
            for name in IO_SETTINGS:setattr(self,name,io_value(found[-1],name))
            return context.window_manager.invoke_props_dialog(self,width=460)
        except Exception as error:self.report({'ERROR'},str(error));return {'CANCELLED'}

    def draw(self,context):
        for name in IO_SETTINGS:self.layout.prop(self,name)

    def execute(self,context):
        try:
            found = io_source(context.active_object)
            if not found:raise ValueError('The selected prefab has no imported IO settings')
            text,source,index,entries,entry_index,entity = found
            for name,(number,kind,_default) in IO_SETTINGS.items():
                value = getattr(self,name)
                if value == io_value(entity,name):continue
                raw = value.encode('utf8') if kind=='str' else (struct.pack('<f',value) if kind=='float' else int(value)&0xffffffffffffffff)
                entity = wire.replace(entity,number,2 if kind=='str' else (5 if kind=='float' else 0),raw)
            entries[entry_index] = wire.encode(1,2,wire.serialize(entity))
            source.fields[index] = wire.encode(5,2,wire.serialize(entries))
            text.clear();text.write(base64.b64encode(source.write()).decode('ascii'))
            return {'FINISHED'}
        except Exception as error:self.report({'ERROR'},str(error));return {'CANCELLED'}


def new_prefab():
    scene.clear_scene()
    state = bpy.context.scene.ruster
    state.mode, state.title = 'PREFAB', 'Untitled Prefab'
    state.project_path = state.source_map = ''
    state.terrain_state = None
    scene.new_collection('Prefabs')
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type=='VIEW_3D':
                shading=area.spaces.active.shading
                shading.type='SOLID';shading.color_type='TEXTURE';shading.light='STUDIO'
    from . import ui
    if not bpy.app.background:bpy.app.timers.register(ui.start_workspace, first_interval=.1)


def prefab_records(roots, origin):
    records = []
    bpy.context.view_layer.update()
    from .protection import model_error
    checked_models = {}
    for root in roots:
        problem = model_error(root, checked_models)
        if problem:raise ValueError(root.name + ': ' + problem)
        old = wire.parse(base64.b64decode(root['ruster_record'], validate=True))
        position, rotation, scale = prefab_transform(old)
        relative = root.matrix_world.copy();relative.translation -= origin
        baseline = root.get('ruster_prefab_matrix')
        original=(Matrix([baseline[i*4:i*4+4] for i in range(4)]) if baseline else
                  Matrix.LocRotScale(scene.to_blender(position),scene.unity_euler(rotation),scene.to_blender(scale)))
        same_matrix=all(math.isclose(relative[i][j],original[i][j],rel_tol=3e-7,abs_tol=5e-6)
                        for i in range(4) for j in range(4))
        if same_matrix:
            # Original Rust IO tubes can be hundreds of metres long and very
            # thin. Preserve their exact records before float32 decomposition.
            records.append(old);continue
        location, quaternion, actual_scale = root.matrix_world.decompose()
        if not all(math.isfinite(v) for v in (*location, *quaternion, *actual_scale)):
            raise ValueError('Prefab has an invalid transform')
        if scene.matrix_has_shear(root.matrix_world):
            raise ValueError('Group scaling introduces shear; use uniform group scale')
        location -= origin
        unchanged = ((location - scene.to_blender(position)).length < 1e-5
                     and abs(quaternion.dot(scene.unity_euler(rotation))) > 1 - 1e-7
                     and (actual_scale - scene.to_blender(scale)).length < 1e-6)
        records.append(old if unchanged else update_transform(old, scene.to_unity(location),
                       scene.blender_euler(quaternion), scene.to_unity(actual_scale)))
    return records


def import_prefab(path):
    path = Path(path)
    data = RustEditPrefab.load(path)  # Validate everything before creating objects.
    cursor = bpy.context.scene.cursor.location.copy()
    collection = bpy.data.collections.get('Prefabs') or scene.new_collection('Prefabs')
    io_positions = set()
    linked_extensions = bool(data.populated_extensions)
    for field in data.fields:
        if field.number == 5 and field.wire == 2:
            for entry in wire.parse(field.value):
                if entry.number == 1 and entry.wire == 2:
                    position = wire.get(wire.parse(entry.value),2)
                    if position is not None:io_positions.add(tuple(round(v,3) for v in wire.vector(position)))
    created = []
    root = None
    try:
        for index, fields in enumerate(data.prefabs):
            obj = scene.root_object(fields, collection)
            obj.location += cursor
            obj['ruster_prefab_index'] = index
            obj['ruster_has_io'] = tuple(round(v,3) for v in prefab_transform(fields)[0]) in io_positions
            obj['ruster_linked_extensions'] = linked_extensions
            scene.attach_visual(obj)
            created.append(obj)
        root = placement.group(created, path.stem)
        # RustEdit's pivot is the file's origin, not the mean placement position.
        matrices = [(obj, obj.matrix_world.copy()) for obj in created]
        root.location = cursor
        bpy.context.view_layer.update()
        for obj, matrix in matrices:obj.matrix_world = matrix
        bpy.context.view_layer.update()
        for obj in created:
            matrix = obj.matrix_world.copy();matrix.translation -= cursor
            obj['ruster_prefab_matrix'] = [matrix[i][j] for i in range(4) for j in range(4)]
        text = bpy.data.texts.new('RustEdit source: ' + path.name)
        text.write(base64.b64encode(data.original).decode('ascii'))
        root['ruster_prefab_source'] = text.name
        app.request_missing_visuals(created)
        return root
    except Exception:
        for obj in created:
            if obj.name in bpy.data.objects:bpy.data.objects.remove(obj, do_unlink=True)
        if root and root.name in bpy.data.objects:bpy.data.objects.remove(root, do_unlink=True)
        raise


def export_prefab(path, selected=True):
    roots = placement.selected_prefabs() if selected else scene.prefab_roots()
    if not roots:raise ValueError('Select prefab placements or a prefab group')
    active = bpy.context.active_object
    groups = {next((parent for parent in placement.parent_chain(obj)
                    if parent.get('ruster_prefab_source')),None) for obj in roots}
    if len(groups)>1:
        raise ValueError('Export imported custom-prefab groups separately to preserve their metadata')
    source_group = next(iter(groups))
    if not source_group and any(obj.get('ruster_linked_extensions') for obj in roots):
        raise ValueError('The imported prefab group is missing; restore it before exporting linked metadata')
    source = None
    if source_group:
        text = bpy.data.texts.get(source_group.get('ruster_prefab_source', ''))
        if not text:raise ValueError('The imported prefab metadata is missing')
        source = RustEditPrefab.read(base64.b64decode(text.as_string(), validate=True))
        roots.sort(key=lambda o: int(o.get('ruster_prefab_index', -1)))
        origin = source_group.matrix_world.translation.copy()
    else:
        origin = (active.matrix_world.translation.copy() if active and active.get('ruster_kind') == 'GROUP'
                  else bpy.context.scene.cursor.location.copy())
    records = prefab_records(roots, origin)
    if source:source.replace_prefabs(records)
    else:source = RustEditPrefab.create(records)
    atomic_write(Path(path).with_suffix('.prefab'), source.write())


def prefab_menu_data(context, category=''):
    """One small metadata snapshot per native menu, never model/bundle data."""
    from .core import palettes, settings
    from .core.asset_names import display_name, menu_label, IO_SEARCH_ORDER
    state=(context or bpy.context).scene.ruster
    path=scene.cache_dir()/'catalog.sqlite3'
    favorites=frozenset(palettes.favorite_ids(settings.load()))
    # Shift+A is the complete catalog, independent of sidebar category/helper
    # filters. Explicit category entry points keep their local-availability filter.
    available_only=state.available_only if category and category!='@ALL_ASSETS' else False
    key=(str(path),path.stat().st_mtime_ns if path.exists() else 0,category,available_only,favorites)
    if key not in _menu_cache:
        rows=catalog.search(scene.cache_dir(),limit=-1,category=category,
                            include_helpers=True,available_only=available_only)
        rows.sort(key=lambda row:(row[0] not in favorites,display_name(row[1]).casefold(),row[0]))
        items=[]
        for uid,source,available in rows:
            stem=Path(source).stem.casefold()
            rank=IO_SEARCH_ORDER.index(stem) if '/ioslothandles/' in source.casefold() and stem in IO_SEARCH_ORDER else None
            weight=1000-rank*50 if rank is not None else (20 if uid in favorites else 0)
            icon='SOLO_ON' if uid in favorites else 'MESH_CUBE' if available else 'QUESTION'
            items.append((str(uid),menu_label(source),source,weight,icon))
        _menu_cache[key]={'items':items,'total':len(items)}
    data=_menu_cache.pop(key);_menu_cache[key]=data
    while len(_menu_cache)>MENU_CACHE_LIMIT:
        del _menu_cache[next(iter(_menu_cache))]
    return data


def search_items(operator, context):
    """Compatibility metadata adapter for callers inspecting the Add catalog."""
    data=prefab_menu_data(context,getattr(operator,'category',''))
    if 'enum_items' not in data:
        data['enum_items']=[(uid,name,path+'\nID: '+uid) for uid,name,path,_weight,_icon in data['items']]
    return data['enum_items'] or [('NONE','No local catalog — select a Rust installation','')]


def draw_prefab_menu(menu, context, category=''):
    layout=menu.layout
    if context.mode!='OBJECT':
        layout.label(text='Finish editing before adding prefabs')
        return
    layout.operator_context='EXEC_DEFAULT'
    data=prefab_menu_data(context,category)
    if not data['items']:
        layout.label(text='Select a Rust installation in Assets preferences',icon='INFO')
        return
    for uid,name,_source,weight,icon in data['items']:
        layout.operator('ruster.place',text=name,icon=icon,search_weight=weight).uid=uid


class RUSTER_OT_add_prefab(bpy.types.Operator):
    bl_idname = 'ruster.add_prefab'
    bl_label = 'Add Rust Prefab'
    category: StringProperty(default='',options={'SKIP_SAVE'})

    def invoke(self, context, event):
        menu=_category_menus.get(self.category) if self.category else RUSTER_MT_add
        if menu is None:
            self.report({'ERROR'},'Unknown Rust prefab category')
            return {'CANCELLED'}
        return bpy.ops.wm.call_menu(name=menu.__name__)

    def execute(self, context):
        return self.invoke(context,None)


class RUSTER_MT_add(bpy.types.Menu):
    bl_label = 'Add'
    bl_options = {'SEARCH_ON_KEY_PRESS'}

    def draw(self, context):
        draw_prefab_menu(self,context)


def category_menu(key, label):
    def draw(self, context):
        draw_prefab_menu(self,context,'@'+key)
    return type('RUSTER_MT_add_'+key,(bpy.types.Menu,),
                {'__module__':__name__,'bl_label':label,
                 'bl_options':{'SEARCH_ON_KEY_PRESS'},'draw':draw})


class RUSTER_OT_prefab_import(bpy.types.Operator, ImportHelper):
    bl_idname = 'ruster.prefab_import'
    bl_label = 'Import RustEdit Prefab'
    bl_options = {'REGISTER', 'UNDO'}
    filter_glob: StringProperty(default='*.prefab', options={'HIDDEN'})
    def execute(self, context):
        try:import_prefab(self.filepath);return {'FINISHED'}
        except Exception as error:self.report({'ERROR'}, str(error));return {'CANCELLED'}


class RUSTER_OT_prefab_export(bpy.types.Operator, ExportHelper):
    bl_idname = 'ruster.prefab_export'
    bl_label = 'Export RustEdit Prefab'
    filename_ext = '.prefab'
    filter_glob: StringProperty(default='*.prefab', options={'HIDDEN'})
    selected_only: BoolProperty(name='Selected Prefabs Only', default=True)
    def execute(self, context):
        try:export_prefab(self.filepath, self.selected_only);return {'FINISHED'}
        except Exception as error:self.report({'ERROR'}, str(error));return {'CANCELLED'}


def model_formats(_operator, _context):
    global _model_items
    from .model_export import available_formats
    if not _model_items:_model_items = available_formats()
    return _model_items


class RUSTER_OT_model_export(bpy.types.Operator, ExportHelper):
    bl_idname = 'ruster.model_export'
    bl_label = 'Export Models'
    filename_ext = ''
    format: EnumProperty(name='File Format', items=model_formats)
    selected_only: BoolProperty(name='Selected Prefabs Only', default=True)
    def execute(self, context):
        try:
            from .model_export import export_models
            roots = placement.selected_prefabs() if self.selected_only else scene.prefab_roots()
            result = export_models(self.filepath, self.format, roots)
            self.report({'INFO'}, 'Exported ' + result.name)
            return {'FINISHED'}
        except Exception as error:self.report({'ERROR'}, str(error));return {'CANCELLED'}


class RUSTER_OT_blend_export(bpy.types.Operator, ExportHelper):
    bl_idname = 'ruster.blend_export'
    bl_label = 'Export Blender File'
    bl_description = 'Export a standalone Blender scene with editable models and packed textures for rendering in Blender'
    filename_ext = '.blend'
    filter_glob: StringProperty(default='*.blend', options={'HIDDEN'})
    selected_only: BoolProperty(name='Selected Prefabs Only', default=False)
    def execute(self, context):
        try:
            from .model_export import export_models
            roots = placement.selected_prefabs() if self.selected_only else scene.prefab_roots()
            result = export_models(self.filepath, 'BLEND', roots)
            self.report({'INFO'}, 'Exported ' + result.name)
            return {'FINISHED'}
        except Exception as error:self.report({'ERROR'}, str(error));return {'CANCELLED'}


class RUSTER_OT_edit_mode(bpy.types.Operator):
    bl_idname = 'ruster.edit_mode'
    bl_label = 'Edit Path Nodes'
    def execute(self, context):
        obj = context.active_object
        if obj and obj.get('ruster_kind') == 'PATH':
            return bpy.ops.object.mode_set(mode='OBJECT' if context.mode == 'EDIT_CURVE' else 'EDIT')
        self.report({'INFO'}, 'Rust prefabs are edited as whole placements')
        return {'CANCELLED'}


def register():
    _category_menus.update(('@'+key,category_menu(key,label)) for key,label,_patterns in GROUPS)
    classes = [RUSTER_OT_io_settings, RUSTER_OT_add_prefab, RUSTER_MT_add, *_category_menus.values(), RUSTER_OT_prefab_import,
               RUSTER_OT_prefab_export, RUSTER_OT_model_export, RUSTER_OT_blend_export, RUSTER_OT_edit_mode]
    for cls in classes:bpy.utils.register_class(cls);_classes.append(cls)
    config = bpy.context.window_manager.keyconfigs.addon
    if config:
        view_keymap = config.keymaps.new(name='3D View', space_type='VIEW_3D')
        walk = view_keymap.keymap_items.new('view3d.walk', 'F', 'PRESS', shift=True)
        _keymaps.append((view_keymap, walk))
        add = view_keymap.keymap_items.new('wm.call_menu', 'A', 'PRESS', shift=True)
        add.properties.name = 'RUSTER_MT_add'
        _keymaps.append((view_keymap, add))
        keymap = config.keymaps.new(name='Object Mode', space_type='EMPTY')
        item = keymap.keymap_items.new('wm.call_menu', 'A', 'PRESS', shift=True)
        item.properties.name = 'RUSTER_MT_add';_keymaps.append((keymap, item))
        item = keymap.keymap_items.new('ruster.edit_mode', 'TAB', 'PRESS')
        _keymaps.append((keymap, item))
        item = keymap.keymap_items.new('ruster.commands','SPACE','PRESS')
        _keymaps.append((keymap,item))
        keymap = config.keymaps.new(name='Curve',space_type='EMPTY')
        item = keymap.keymap_items.new('wm.call_menu','A','PRESS',shift=True)
        item.properties.name = 'RUSTER_MT_add';_keymaps.append((keymap,item))


def unregister():
    _menu_cache.clear()
    for keymap, item in _keymaps:keymap.keymap_items.remove(item)
    _keymaps.clear()
    for cls in reversed(_classes):bpy.utils.unregister_class(cls)
    _classes.clear()
    _category_menus.clear()
