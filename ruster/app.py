"""Application lifecycle, native Blender operators, and background asset jobs."""
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import bpy
from bpy.app.handlers import persistent
from bpy.props import StringProperty, IntProperty, EnumProperty, PointerProperty, BoolProperty
from bpy_extras.io_utils import ImportHelper, ExportHelper

from . import scene
from .core import project, settings, wire
from .assets import catalog

_classes = []
_keymaps = []
_job = None
_job_log = None
_job_action = None
_visual_queue = []
_session_dirs = []
_pending_project = None
_job_cancelled = False


def query_changed(state,context):
    state.query_page=0


class RUSTER_PG_project(bpy.types.PropertyGroup):
    mode: EnumProperty(items=[('BLENDER', 'Blender', ''), ('MAP', 'Rust map', '')], default='BLENDER')
    title: StringProperty(default='Untitled')
    project_path: StringProperty(subtype='FILE_PATH')
    source_map: StringProperty(subtype='FILE_PATH')
    map_size: IntProperty(default=4000)
    query: StringProperty(name='Search prefabs', options={'SKIP_SAVE'},update=query_changed)
    asset_status: StringProperty(default='Choose your Rust installation', options={'SKIP_SAVE'})
    busy: BoolProperty(default=False, options={'SKIP_SAVE'})
    terrain_state: PointerProperty(type=bpy.types.Text)
    query_page: IntProperty(default=0,min=0,options={'SKIP_SAVE'})
    preview_resolution:EnumProperty(name='Terrain Detail',items=[('129','Fast','Lowest viewport memory use'),
        ('257','Balanced','Balanced detail and performance'),('513','Detailed','More terrain samples in the viewport'),
        ('1025','Very Detailed','Highest viewport memory use')],default='257')


def session_dir():
    # Keep directories alive for the session, especially .ruster's embedded source.map.
    directory = tempfile.TemporaryDirectory(prefix='ruster-')
    _session_dirs.append(directory)
    return Path(directory.name)


def worker_python():
    if path := os.environ.get('RUSTER_WORKER_PYTHON'):
        return path
    base = Path(bpy.app.binary_path).parent
    candidates = list(base.glob('*/python/bin/python*'))
    if sys.platform == 'win32':
        candidates += list(base.glob('*/python/bin/python.exe'))
    if sys.platform == 'darwin':
        candidates += list(base.glob('../Resources/*/python/bin/python*'))
    candidates = [p for p in candidates if p.is_file() and '-config' not in p.name]
    if not candidates:
        raise ValueError('Bundled Python not found; set RUSTER_WORKER_PYTHON for development')
    return str(sorted(candidates)[0].resolve())


def start_job(action, ids=None):
    global _job, _job_log, _job_action, _job_cancelled
    if _job is not None and _job.poll() is None:
        raise ValueError('An asset operation is already running')
    config = settings.load()
    root = settings.validate_install(config.get('rust_install', ''))
    cache = scene.cache_dir()
    cache.mkdir(parents=True, exist_ok=True)
    args = [worker_python(), str(Path(__file__).parent / 'assets/worker.py'), action,
            '--install', str(root), '--cache', str(cache)]
    if ids is not None:
        ids_path = session_dir() / 'ids.json'
        ids_path.write_text(json.dumps(ids))
        args += ['--ids-file', str(ids_path)]
    (cache / 'progress.json').write_text(json.dumps({'state': 'STARTING'}))
    _job_log = (cache / 'worker.log').open('w')
    kwargs = {'creationflags': subprocess.CREATE_NO_WINDOW} if sys.platform == 'win32' else {}
    _job = subprocess.Popen(args, stdout=_job_log, stderr=subprocess.STDOUT, **kwargs)
    _job_action = action
    _job_cancelled = False
    bpy.context.scene.ruster.busy = True
    if not bpy.app.timers.is_registered(poll_job):
        bpy.app.timers.register(poll_job, first_interval=.2)


def redraw():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()


def poll_job():
    global _job, _job_log, _visual_queue, _job_action
    state = bpy.context.scene.ruster
    progress = {}
    try:
        progress = json.loads((scene.cache_dir() / 'progress.json').read_text())
        phase = progress.get('state', 'STARTING')
        if phase == 'ERROR':
            state.asset_status = progress.get('error', 'Asset operation failed')
        elif phase == 'READY':
            state.asset_status = f"Assets ready · {progress.get('failures', 0)} reported issues"
        else:
            state.asset_status = f"{phase.title()} {progress.get('current', 0)}/{progress.get('total', '?')} · {progress.get('item', '')}"
    except (OSError, ValueError):
        pass
    if _job and _job.poll() is None:
        redraw()
        return .5
    code = _job.returncode if _job else 0
    _job = None
    if _job_log:
        _job_log.close()
        _job_log = None
    state.busy = False
    if _job_cancelled:
        state.asset_status='Asset import cancelled. Completed cache entries are available.'
    elif code and progress.get('state') != 'ERROR':
        state.asset_status = 'Asset import failed — see the asset report / worker.log'
    action, _job_action = _job_action, None
    if not code and action == 'index' and state.mode == 'MAP' and scene.prefab_roots():
        try:
            start_job('extract', [int(o['ruster_uid']) for o in scene.prefab_roots()])
            return .5
        except Exception as error:
            state.asset_status = str(error)
    _visual_queue = [obj.name for obj in scene.prefab_roots()]
    if not bpy.app.timers.is_registered(load_visuals):
        bpy.app.timers.register(load_visuals, first_interval=.1)
    redraw()
    return None


def load_visuals():
    for _ in range(4):
        if not _visual_queue:
            redraw()
            return None
        name = _visual_queue.pop()
        obj = bpy.data.objects.get(name)
        if obj and obj.get('ruster_kind') == 'PREFAB':
            try:
                scene.attach_visual(obj,force=True)
            except Exception as error:
                bpy.context.scene.ruster.asset_status = f'Could not load {name}: {error}'
    redraw()
    return .01


class RUSTER_OT_setup(bpy.types.Operator):
    bl_idname = 'ruster.setup'
    bl_label = 'Locate Rust'
    bl_description = 'Choose the Rust game installation to load local assets'
    directory: StringProperty(name='Rust installation', subtype='DIR_PATH')

    def invoke(self, context, event):
        self.directory = settings.load().get('rust_install', '')
        return context.window_manager.invoke_props_dialog(self, width=520)

    def draw(self, context):
        col = self.layout.column()
        col.label(text='Welcome to Ruster', icon='WORLD')
        col.label(text='Select the Rust game folder in your Steam library.')
        col.label(text='Assets stay on your computer. Your game files are read only.')
        col.separator()
        col.prop(self, 'directory')

    def execute(self, context):
        global _pending_project
        try:
            root = settings.validate_install(bpy.path.abspath(self.directory))
            config = settings.load()
            config['rust_install'] = str(root)
            settings.save(config)
            start_job('index')
            if _pending_project:
                pending, _pending_project = _pending_project, None
                open_path(pending)
            else:
                bpy.ops.ruster.welcome('INVOKE_DEFAULT')
            return {'FINISHED'}
        except Exception as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}

    def cancel(self, context):
        bpy.ops.ruster.welcome('INVOKE_DEFAULT')


class RUSTER_OT_welcome(bpy.types.Operator):
    bl_idname = 'ruster.welcome'
    bl_label = 'Ruster'

    def invoke(self, context, event):
        return context.window_manager.invoke_popup(self, width=460)

    def draw(self, context):
        col = self.layout.column()
        col.scale_y = 1.25
        col.label(text='Ruster', icon='WORLD')
        col.label(text='Create something new, or build on a Rust world.')
        col.separator()
        col.operator('ruster.open', text='Open Map or Project', icon='FILE_FOLDER')
        col.operator('ruster.new', text='New Project', icon='FILE_NEW')
        col.operator('ruster.new_map',text='New Rust Map',icon='WORLD')
        col.separator()
        col.operator('ruster.setup', text='Rust Installation', icon='PREFERENCES')
        col.label(text='Rust .map   ·   Ruster .ruster')
        recent=settings.load().get('recent_projects',[])
        recovery=settings.load().get('last_recovery','')
        if recovery and Path(recovery).is_file():
            col.separator()
            col.operator('ruster.open',text='Recover Autosaved Session',icon='RECOVER_LAST').filepath=recovery
        for path in recent[:5]:
            if Path(path).is_file():
                col.operator('ruster.open',text=Path(path).name,icon='FILE_BLEND').filepath=path

    def execute(self, context):
        return {'FINISHED'}


class RUSTER_OT_new(bpy.types.Operator):
    bl_idname = 'ruster.new'
    bl_label = 'New Project'
    bl_description = 'Start with the normal Blender workspace'

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event, title='Create a new project?',
            message='Save your current project first. Unsaved changes will be discarded.')

    def execute(self, context):
        bpy.ops.wm.read_factory_settings(app_template='')
        context.preferences.filepaths.use_scripts_auto_execute = False
        context.preferences.view.show_splash = False
        # Python registrations persist across read_homefile.
        context.scene.ruster.mode = 'BLENDER'
        context.scene.ruster.title = 'Untitled'
        context.scene.ruster.project_path = ''
        return {'FINISHED'}


def open_path(path):
    global _pending_project
    path = Path(path).resolve()
    if path.suffix.lower() == '.map':
        scene.import_map(path)
        from . import ui
        ui.map_workspace()
        config = settings.load()
        if config.get('rust_install') and not bpy.context.scene.ruster.busy:
            try:
                start_job('extract', [int(o['ruster_uid']) for o in scene.prefab_roots()])
            except Exception as error:
                bpy.context.scene.ruster.asset_status = str(error)
    elif path.suffix.lower() == '.ruster':
        directory = session_dir()
        manifest = project.unpack(path, directory)
        # No embedded Python, drivers, or file UI is trusted or executed.
        bpy.ops.wm.open_mainfile(filepath=str(directory / 'scene.blend'), load_ui=False, use_scripts=False)
        state = bpy.context.scene.ruster
        state.project_path = str(path)
        state.mode = manifest['mode']
        state.title = manifest.get('title', path.stem)
        state.source_map = str(directory / 'source.map') if manifest['mode'] == 'MAP' else ''
        state.busy = _job is not None and _job.poll() is None
        if state.mode == 'MAP':
            scene.restore_map_tools()
            from . import ui
            ui.map_workspace()
    else:
        raise ValueError('Choose a Rust .map or Ruster .ruster file')
    # File import and post-load source relocation must be an undo baseline.
    # Otherwise the first brush undo can restore the old scene or a stale source.
    if bpy.context.preferences.edit.use_global_undo:
        bpy.ops.ed.undo_push(message='Open Ruster Project')
    remember_project(path)


def remember_project(path):
    config=settings.load()
    path=str(Path(path).resolve())
    recent=[path]+[p for p in config.get('recent_projects',[]) if p!=path]
    settings.save({**config,'last_project':path,'recent_projects':recent[:10]})


def save_project(path,update_path=True):
    state=bpy.context.scene.ruster
    old_path,old_title=state.project_path,state.title
    try:
        if update_path:
            state.project_path=str(Path(path).resolve())
            state.title=Path(path).stem
        with tempfile.TemporaryDirectory(prefix='ruster-save-') as temp:
            blend=Path(temp)/'scene.blend'
            bpy.ops.file.pack_all()
            bpy.ops.wm.save_as_mainfile(filepath=str(blend),copy=True,check_existing=False,compress=True)
            project.save(path,blend,state.mode,state.source_map or None,state.title)
        if update_path:remember_project(path)
    except Exception:
        state.project_path,state.title=old_path,old_title
        raise


def recovery_tick():
    if bpy.app.background:return None
    try:
        if bpy.context.window_manager.is_interface_locked or bpy.context.mode!='OBJECT':return 20.
        from . import editing
        if editing.stroke_active:return 20.
        state=bpy.context.scene.ruster
        path=settings.user_root()/'recovery'/'last-session.ruster'
        save_project(path,update_path=False)
        config=settings.load();config['last_recovery']=str(path);settings.save(config)
    except Exception:
        # Recovery must never interrupt active editing; manual saves still report errors.
        pass
    return 120.


class RUSTER_OT_open(bpy.types.Operator, ImportHelper):
    bl_idname = 'ruster.open'
    bl_label = 'Open Map or Project'
    filter_glob: StringProperty(default='*.map;*.ruster', options={'HIDDEN'})

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event, title='Open a map or project?',
            message='Save your current project first. Opening replaces the current scene.')

    def execute(self, context):
        # Confirmation runs before file selection, so it also covers .map imports.
        if not self.filepath:
            context.window_manager.fileselect_add(self)
            return {'RUNNING_MODAL'}
        try:
            open_path(self.filepath)
            return {'FINISHED'}
        except Exception as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}


class RUSTER_OT_save(bpy.types.Operator, ExportHelper):
    bl_idname = 'ruster.save'
    bl_label = 'Save Ruster Project'
    filename_ext = '.ruster'
    filter_glob: StringProperty(default='*.ruster', options={'HIDDEN'})
    save_as: BoolProperty(default=False, options={'HIDDEN'})

    def invoke(self, context, event):
        if context.scene.ruster.project_path and not self.save_as:
            self.filepath = context.scene.ruster.project_path
            return self.execute(context)
        self.filepath = context.scene.ruster.title + '.ruster'
        return ExportHelper.invoke(self, context, event)

    def execute(self, context):
        try:
            if Path(self.filepath).suffix.lower() != '.ruster':
                self.filepath += '.ruster'
            save_project(self.filepath)
            self.report({'INFO'}, f'Saved {Path(self.filepath).name}')
            return {'FINISHED'}
        except Exception as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}


class RUSTER_OT_export(bpy.types.Operator, ExportHelper):
    bl_idname = 'ruster.export_map'
    bl_label = 'Export Rust Map'
    filename_ext = '.map'
    filter_glob: StringProperty(default='*.map', options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return context.scene.ruster.mode == 'MAP'

    def execute(self, context):
        try:
            scene.export_map(self.filepath)
            self.report({'INFO'}, 'Exported map terrain, paths and prefab placements')
            return {'FINISHED'}
        except Exception as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}


class RUSTER_OT_validate(bpy.types.Operator):
    bl_idname = 'ruster.validate'
    bl_label = 'Validate Map'

    def execute(self, context):
        errors, notes = scene.validate()
        def draw(popup, _context):
            for error in errors:
                popup.layout.label(text=error, icon='ERROR')
            if not errors:
                popup.layout.label(text='Map data is ready to export', icon='CHECKMARK')
            for note in notes:
                popup.layout.label(text=note, icon='INFO')
        context.window_manager.popup_menu(draw, title='Map Validation')
        return {'FINISHED'}


class RUSTER_OT_assets(bpy.types.Operator):
    bl_idname = 'ruster.assets'
    bl_label = 'Load Map Assets'
    rebuild: BoolProperty(default=False, options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return not context.scene.ruster.busy

    def execute(self, context):
        try:
            start_job('index' if self.rebuild else 'extract',
                      None if self.rebuild else [int(o['ruster_uid']) for o in scene.prefab_roots()])
            return {'FINISHED'}
        except Exception as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}


class RUSTER_OT_cancel_assets(bpy.types.Operator):
    bl_idname='ruster.cancel_assets'
    bl_label='Cancel Asset Import'
    def execute(self,context):
        global _job_cancelled
        if _job is not None and _job.poll() is None:
            _job_cancelled=True;_job.terminate()
        return {'FINISHED'}


class RUSTER_OT_catalog_page(bpy.types.Operator):
    bl_idname='ruster.catalog_page'
    bl_label='Change Prefab Page'
    delta:IntProperty(default=1)
    def execute(self,context):
        context.scene.ruster.query_page=max(0,context.scene.ruster.query_page+self.delta)
        return {'FINISHED'}


class RUSTER_FH_project(bpy.types.FileHandler):
    bl_idname='RUSTER_FH_project'
    bl_label='Ruster Map or Project'
    bl_import_operator='ruster.open'
    bl_file_extensions='.map;.ruster'
    @classmethod
    def poll_drop(cls,context):return context.area is not None and context.area.type=='VIEW_3D'


class RUSTER_OT_place(bpy.types.Operator):
    bl_idname = 'ruster.place'
    bl_label = 'Place Prefab'
    bl_options = {'REGISTER', 'UNDO'}
    uid: StringProperty()

    def execute(self, context):
        try:
            uid = int(self.uid)
            if not 0 <= uid <= 0xFFFFFFFF or not catalog.find(scene.cache_dir(), uid):
                raise ValueError('Prefab is not in the local Rust catalog')
            fields = [wire.encode(1, 2, b'Decor'), wire.encode(2, 0, uid)]
            fields = wire.replace(fields, 3, 2, wire.set_vector(None, scene.to_unity(context.scene.cursor.location)))
            fields = wire.replace(fields, 5, 2, wire.set_vector(None, (1.,1.,1.)))
            collection = bpy.data.collections.get('Prefabs') or scene.new_collection('Prefabs')
            obj = scene.root_object(fields, collection)
            scene.attach_visual(obj)
            for item in context.selected_objects:
                item.select_set(False)
            obj.select_set(True)
            context.view_layer.objects.active = obj
            if not obj.get('ruster_visual') and not context.scene.ruster.busy:
                start_job('extract', [uid])
            return {'FINISHED'}
        except Exception as error:
            self.report({'ERROR'}, str(error))
            return {'CANCELLED'}


class RUSTER_OT_duplicate(bpy.types.Operator):
    bl_idname = 'ruster.duplicate'
    bl_label = 'Duplicate Prefabs'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from .placement import duplicate_selected
        if not duplicate_selected():
            self.report({'WARNING'}, 'Select prefab placements to duplicate')
            return {'CANCELLED'}
        return {'FINISHED'}


class RUSTER_OT_delete(bpy.types.Operator):
    bl_idname = 'ruster.delete'
    bl_label = 'Delete Prefabs'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from .placement import delete_selected
        delete_selected()
        return {'FINISHED'}


class RUSTER_OT_report(bpy.types.Operator):
    bl_idname = 'ruster.asset_report'
    bl_label = 'Asset Report'

    def execute(self, context):
        path = scene.cache_dir() / 'asset-report.json'
        text = path.read_text() if path.exists() else 'No extraction report yet.\n' + context.scene.ruster.asset_status
        block = bpy.data.texts.get('Ruster Asset Report') or bpy.data.texts.new('Ruster Asset Report')
        block.clear()
        block.write(text)
        def draw(popup, _context):
            popup.layout.label(text=context.scene.ruster.asset_status[:120])
            popup.layout.label(text=f'Full report: {scene.cache_dir()}')
        context.window_manager.popup_menu(draw, title='Asset Report')
        return {'FINISHED'}


@persistent
def after_load(_dummy):
    from . import editing
    editing.clear_cache()
    if hasattr(bpy.context.scene, 'ruster'):
        bpy.context.scene.ruster.busy = _job is not None and _job.poll() is None


def startup():
    global _pending_project
    if bpy.app.background:
        return None
    if bpy.context.window is None:
        windows=list(bpy.context.window_manager.windows)
        if not windows:return .2
        with bpy.context.temp_override(window=windows[0]):
            return startup()
    config = settings.load()
    try:
        settings.validate_install(config.get('rust_install', ''))
    except ValueError:
        bpy.ops.ruster.setup('INVOKE_DEFAULT')
        return None
    if _pending_project:
        try:
            pending, _pending_project = _pending_project, None
            open_path(pending)
        except Exception as error:
            bpy.context.scene.ruster.asset_status = str(error)
            bpy.ops.ruster.welcome('INVOKE_DEFAULT')
    else:
        bpy.ops.ruster.welcome('INVOKE_DEFAULT')
    return None


def register():
    from . import ui
    if hasattr(bpy.types.Scene, 'ruster'):
        return
    classes = [RUSTER_PG_project, RUSTER_OT_setup, RUSTER_OT_welcome, RUSTER_OT_new,
               RUSTER_OT_open, RUSTER_OT_save, RUSTER_OT_export, RUSTER_OT_validate,
               RUSTER_OT_assets, RUSTER_OT_place, RUSTER_OT_duplicate, RUSTER_OT_delete,
               RUSTER_OT_report,RUSTER_OT_cancel_assets,RUSTER_OT_catalog_page,RUSTER_FH_project]
    for cls in classes:
        bpy.utils.register_class(cls)
        _classes.append(cls)
    bpy.types.Scene.ruster = PointerProperty(type=RUSTER_PG_project)
    from . import editing
    editing.register()
    from . import placement
    placement.register()
    ui.register()
    bpy.app.handlers.load_post.append(after_load)
    config = bpy.context.window_manager.keyconfigs.addon
    if config:
        km = config.keymaps.new(name='Window', space_type='EMPTY')
        for key, shift, op in [('S',False,'ruster.save'), ('S',True,'ruster.save'), ('O',False,'ruster.open')]:
            item = km.keymap_items.new(op, key, 'PRESS', ctrl=True, shift=shift)
            if key == 'S':
                item.properties.save_as = shift
            _keymaps.append((km,item))
    bpy.context.preferences.view.show_splash = False
    bpy.context.preferences.filepaths.use_scripts_auto_execute = False
    if not bpy.app.background and not bpy.app.timers.is_registered(recovery_tick):
        bpy.app.timers.register(recovery_tick,first_interval=120.)


def unregister():
    from . import ui
    if _job is not None and _job.poll() is None:
        _job.terminate()
    for callback in (poll_job, load_visuals, startup,recovery_tick):
        if bpy.app.timers.is_registered(callback):
            bpy.app.timers.unregister(callback)
    if after_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(after_load)
    for km, item in _keymaps:
        km.keymap_items.remove(item)
    _keymaps.clear()
    ui.unregister()
    from . import placement
    placement.unregister()
    from . import editing
    editing.unregister()
    if hasattr(bpy.types.Scene, 'ruster'):
        del bpy.types.Scene.ruster
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
    _classes.clear()
