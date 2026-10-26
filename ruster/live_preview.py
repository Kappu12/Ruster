"""Explicit local playtest controls; importing this never touches a game process."""
import atexit
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import os
from pathlib import Path
import sys
import time

import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty, IntProperty, PointerProperty, StringProperty

from .core import live_preview as backend, preview_client, settings
from .core.preview_protocol import MAX_PLACEMENTS
from .ui_style import ICONS, action, properties, wrapped, section

_classes = []
_job = None
_pool = None
_future = None
_future_kind = ''
_clients = []
_probe_message = 'Checking for Rust…'
_next_probe = 0.
_last_snapshot = None
_error = ''
_snapshot_error = ''
_client_allowed = False
_module_loaded = False
_client_status = ''
_logs = ()
_status = {'status': 'IDLE', 'message': 'Start a private local Rust preview server'}
_next_status = 0.
_dirty = True
_generation = 0
_capture = None
_capture_generation = 0
_capture_rows = []
_ui_signature = None
RESTART_NOTICE = preview_client.RESTART_NOTICE


def installation():
    from .core import steam
    path = steam.resolve_install(settings.load().get('rust_install', ''))
    if not path:raise ValueError('Choose your Rust installation in Preferences > Assets first')
    return path


def dll_path():return Path(__file__).resolve().parent/'preview_native/bin/RusterPreview.dll'


def placement_rows():
    from . import scene
    from .assets import catalog
    roots = scene.prefab_roots()
    if len(roots) > MAX_PLACEMENTS:raise ValueError('Live preview supports at most 2,000 prefab placements')
    if not roots:return
    with closing(catalog.read_connection(scene.cache_dir())) as db:
        ids = {int(root['ruster_uid']) for root in roots}
        paths = dict(db.execute('SELECT uid,path FROM names WHERE uid IN ('+','.join('?' for _ in ids)+')', tuple(ids)))
    for root in roots:
        if scene.matrix_has_shear(root.matrix_world):raise ValueError(root.name+': group transform introduces shear')
        uid = int(root['ruster_uid'])
        path = paths.get(uid)
        if not path:raise ValueError(root.name+': original prefab path is missing from the catalog')
        location, rotation, scale = root.matrix_world.decompose()
        unity = (scene.BASIS @ rotation.to_matrix() @ scene.BASIS).to_quaternion()
        yield {'key': root.session_uid, 'uid': uid, 'path': path,
            'position': scene.to_unity(location), 'rotation': (unity.x, unity.y, unity.z, unity.w),
            'scale': scene.to_unity(scale), 'euler': scene.blender_euler(rotation)}


def placements():
    bpy.context.view_layer.update()
    return sorted(placement_rows(), key=lambda row: row['key'])


def status():return _status


def submit(kind, function, *args):
    global _future, _future_kind, _error
    # Completed results still belong to tick; never silently overwrite one.
    if _future is not None:raise ValueError('Wait for the current client operation to finish')
    if _pool is None:raise ValueError('Live preview is not initialized')
    if kind != 'probe':_error = ''
    _future_kind = kind;_future = _pool.submit(function, *args)


def probe_clients():
    path = installation();clients = preview_client.discover(path)
    if not clients:return clients, False, False, 'Rust is not running'
    if len(clients) != 1:return clients, False, False, 'Close extra Rust instances before injecting'
    loaded = any(Path(name).name.casefold() == 'rusterpreview.dll' for name in clients[0].modules)
    try:preview_client.verify_probe(clients[0], path)
    except ValueError as error:return clients, False, loaded, str(error)
    return clients, not loaded, loaded, ('Preview module is loaded' if loaded else 'EAC checks passed; rechecked on Inject')


@persistent
def scene_changed(_scene, _depsgraph=None):
    global _dirty, _generation
    _dirty = True;_generation += 1


@persistent
def invalidate_capture(_dummy):
    global _capture, _capture_rows
    _capture = None;_capture_rows = []
    scene_changed(None)


def capture_snapshot():
    """Copy RNA on the main thread, yielding between bounded placement batches."""
    global _capture, _capture_rows, _capture_generation, _dirty, _last_snapshot, _snapshot_error
    if _capture is not None and _capture_generation != _generation:_capture = None
    if _capture is None:
        if not _dirty:return
        bpy.context.view_layer.update()
        _capture = placement_rows();_capture_rows = [];_capture_generation = _generation;_dirty = False
    deadline = time.monotonic()+.004
    try:
        while time.monotonic() < deadline:_capture_rows.append(next(_capture))
    except StopIteration:
        rows = sorted(_capture_rows, key=lambda row: row['key']);_capture = None;_capture_rows = []
        try:
            if rows != _last_snapshot:_job.update(rows);_last_snapshot = rows
            _snapshot_error = ''
        except Exception as error:_snapshot_error = str(error)
    except Exception as error:
        _capture = None;_capture_rows = [];_snapshot_error = str(error)


def refresh_status():
    global _status, _client_status, _logs
    _status = _job.info() if _job else {'status': 'IDLE', 'message': 'Start a private local Rust preview server'}
    _logs = tuple(_job.log_tail(6)) if _job else ()
    _client_status = ''
    if _job:
        try:_client_status = ' · '.join(backend.read_bounded(_job.directory/'client.status').splitlines()[:2])
        except (OSError, ValueError, UnicodeError):pass


def redraw_panel():
    global _ui_signature
    current = (tuple(_status.items()), _probe_message, _client_allowed, _module_loaded,
        bool(_future), _error, _snapshot_error, _client_status, _logs)
    if current == _ui_signature:return
    _ui_signature = current
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'PROPERTIES':area.tag_redraw()


def tick():
    global _future, _future_kind, _clients, _probe_message, _next_probe, _error
    global _client_allowed, _module_loaded, _next_status
    if bpy.context.window_manager.is_interface_locked:return .5
    if _future and _future.done():
        kind, future = _future_kind, _future;_future = None
        try:
            result = future.result()
            if kind == 'probe':
                _clients, _client_allowed, _module_loaded, _probe_message = result
            elif kind == 'launch':_probe_message = 'Rust is starting. Wait for the main menu.'
            elif kind == 'inject':
                _module_loaded = True;_client_allowed = False
                _probe_message = 'Preview module loaded; waiting for its compatibility check'
        except Exception as error:
            if kind == 'probe':_clients = [];_client_allowed = False;_module_loaded = False;_probe_message = str(error)
            else:_error = str(error)
        _next_probe = time.monotonic()+3
    if (not _future) and time.monotonic() >= _next_probe and not os.environ.get('RUSTER_PREVIEW_TEST_NO_DISCOVERY'):
        try:submit('probe', probe_clients)
        except ValueError as error:_probe_message = str(error);_next_probe = time.monotonic()+5
    if _job and _job.active and _job.status not in ('STOPPING', 'STOPPED', 'FAILED'):
        capture_snapshot()
    if time.monotonic() >= _next_status:
        refresh_status();_next_status = time.monotonic()+1.
    redraw_panel()
    return .02 if _capture is not None else .5


class RUSTER_PG_live_preview(bpy.types.PropertyGroup):
    port: IntProperty(name='Game Port', description='Local game port; the next two ports are reserved for RCON and queries', default=28015, min=1024, max=65533, options={'SKIP_SAVE'})
    owner: StringProperty(name='Owner Steam ID', description='Optional 17-digit SteamID64', options={'SKIP_SAVE'})
    console: StringProperty(name='Command', description='Run a command on this local preview server', options={'SKIP_SAVE'})
    show_log: BoolProperty(name='Console Log', default=True, options={'SKIP_SAVE'})
    update_server: BoolProperty(name='Update Server on Start', description='Update the separate dedicated server and Carbon before starting; use after Rust updates or a server version mismatch', default=False, options={'SKIP_SAVE'})


class RUSTER_OT_start_live_preview(bpy.types.Operator):
    bl_idname = 'ruster.start_live_preview'
    bl_label = 'Start Live Preview'
    bl_description = 'Download a dedicated server on first use, then start a private local preview'
    def execute(self, context):
        global _job, _last_snapshot, _error, _dirty, _snapshot_error, _capture, _next_status
        try:
            if _job and _job.active:raise ValueError('Live preview is already running')
            preview_client.verify_module(dll_path())
            if context.window_manager.is_interface_locked:raise ValueError('Wait for the current editor operation to finish')
            state = context.window_manager.ruster_live_preview
            rows = placements()
            config = settings.load();config['preview_port'] = state.port;config['preview_owner'] = backend.owner_id(state.owner);settings.save(config)
            _job = backend.PreviewSession(settings.user_root()/'live-preview', state.port, state.owner, rows, update_server=state.update_server).start()
            _last_snapshot = rows;_error = '';_snapshot_error = '';_capture = None;_dirty = True;_next_status = 0
            refresh_status()
            return {'FINISHED'}
        except Exception as error:self.report({'ERROR'}, str(error));return {'CANCELLED'}


class RUSTER_OT_stop_live_preview(bpy.types.Operator):
    bl_idname = 'ruster.stop_live_preview'
    bl_label = 'Stop Live Preview'
    bl_description = 'Stop the owned local server and client bridge; restart your computer before launching Rust again after injection'
    def execute(self, context):
        if _job:_job.request_stop()
        refresh_status()
        return {'FINISHED'}


class RUSTER_OT_launch_preview_rust(bpy.types.Operator):
    bl_idname = 'ruster.launch_preview_rust'
    bl_label = 'Launch Rust Without EAC'
    bl_description = 'Launch the official RustClient.exe directly, without the EAC wrapper'
    def execute(self, context):
        try:submit('launch', preview_client.launch, installation());return {'FINISHED'}
        except Exception as error:self.report({'ERROR'}, str(error));return {'CANCELLED'}


class RUSTER_OT_inject_preview(bpy.types.Operator):
    bl_idname = 'ruster.inject_preview'
    bl_label = 'Inject'
    bl_description = 'Verify EAC is inactive, then load only Ruster\'s local preview module'
    def execute(self, context):
        try:
            if not _job or _job.status != 'RUNNING':raise ValueError('Wait for the preview server to become ready')
            if len(_clients) != 1:raise ValueError('Exactly one RustClient.exe must be running')
            submit('inject', preview_client.inject, installation(), dll_path(), _job.directory, _clients[0].pid)
            return {'FINISHED'}
        except Exception as error:self.report({'ERROR'}, str(error));return {'CANCELLED'}


class RUSTER_OT_preview_copy_ip(bpy.types.Operator):
    bl_idname = 'ruster.preview_copy_ip'
    bl_label = 'Copy IP'
    bl_description = 'Copy the local preview address for the Rust F1 console connect command'
    def execute(self, context):
        port = _job.port if _job and _job.active else context.window_manager.ruster_live_preview.port
        context.window_manager.clipboard = f'127.0.0.1:{port}'
        self.report({'INFO'}, 'Local preview address copied');return {'FINISHED'}


class RUSTER_OT_preview_command(bpy.types.Operator):
    bl_idname = 'ruster.preview_command'
    bl_label = 'Send Command'
    bl_description = 'Run the entered console command on this local preview server'
    def execute(self, context):
        try:
            if not _job:raise ValueError('Start live preview first')
            state = context.window_manager.ruster_live_preview
            _job.send_command(state.console);state.console = ''
            return {'FINISHED'}
        except Exception as error:self.report({'ERROR'}, str(error));return {'CANCELLED'}


class RUSTER_OT_preview_owner(bpy.types.Operator):
    bl_idname = 'ruster.preview_owner'
    bl_label = 'Grant Owner ID'
    bl_description = 'Grant administrator permissions to this SteamID64 on the local preview server; reconnect to apply'
    def execute(self, context):
        try:
            if not _job:raise ValueError('Start live preview first')
            owner = backend.owner_id(context.window_manager.ruster_live_preview.owner)
            if not owner:raise ValueError('Enter your SteamID64 first')
            _job.send_command('ownerid '+owner+' "Ruster preview owner"')
            self.report({'INFO'}, 'Owner ID sent; reconnect in Rust to apply permissions')
            return {'FINISHED'}
        except Exception as error:self.report({'ERROR'}, str(error));return {'CANCELLED'}


class RUSTER_OT_preview_logs(bpy.types.Operator):
    bl_idname = 'ruster.preview_logs'
    bl_label = 'Open Preview Logs'
    bl_description = 'Open this preview session folder with server, client and installation logs'
    def execute(self, context):
        if not _job:self.report({'ERROR'}, 'Start live preview first');return {'CANCELLED'}
        bpy.ops.wm.path_open(filepath=str(_job.directory));return {'FINISHED'}


class RUSTER_PT_live_preview(bpy.types.Panel):
    bl_label = 'Live Preview'
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'scene'
    bl_options = {'HIDE_HEADER'}
    def draw(self, context):
        layout = self.layout;state = context.window_manager.ruster_live_preview
        if sys.platform != 'win32':
            wrapped(layout, context, 'Client live preview currently requires Windows x64.', icon='info')
            return
        active = bool(_job and _job.active);running = bool(_job and _job.status == 'RUNNING')
        if not active:wrapped(layout, context, 'First start downloads a separate local Rust server (several GB).')
        fields = properties(layout.column());fields.enabled = not active
        fields.prop(state, 'port')
        properties(layout.column()).prop(state, 'owner', text='Steam ID')
        controls = layout.column()
        controls.enabled = not active or _job.status != 'STOPPING'
        action(controls, 'ruster.stop_live_preview' if active else 'ruster.start_live_preview')
        message = status()
        wrapped(layout, context, message['message'], icon='error' if message['status'] == 'FAILED' else 'busy' if active and not running else 'info')
        if active and message.get('progress') is not None:
            layout.progress(factor=message['progress'], type='BAR', text=f"Setup · ~{message['progress']:.0%}")
        row = layout.row(align=True);row.label(text=f'127.0.0.1:{_job.port if active else state.port}')
        action(row, 'ruster.preview_copy_ip')
        layout.separator()
        if not _clients:wrapped(layout, context, 'Keep Steam open. Launch without EAC and wait for the main menu.', icon='info')
        row = layout.row();row.enabled = not bool(_future)
        failed_module = _module_loaded and _client_status.startswith(('ERROR', 'BLOCKED'))
        if _clients:
            row.enabled = row.enabled and running and _client_allowed and not _module_loaded
            action(row, 'ruster.inject_preview', text='Preview Unavailable' if failed_module else 'Preview Module Loaded' if _module_loaded else None)
        else:action(row, 'ruster.launch_preview_rust')
        wrapped(layout, context, 'Module loaded; preview could not start. See the client error below.' if failed_module else _probe_message,
            icon='error' if failed_module or (_clients and not _client_allowed and not _module_loaded) else 'info')
        if _clients and not running and not _module_loaded:
            wrapped(layout, context, 'Inject unlocks when the local server is Ready.', icon='busy')
        wrapped(layout, context, 'Active or unknown EAC blocks Inject.', icon='locked')
        notice = layout.box()
        wrapped(notice, context, RESTART_NOTICE, icon='locked')
        if _error:wrapped(layout, context, _error, icon='error')
        if _snapshot_error:wrapped(layout, context, _snapshot_error, icon='error')
        if _client_status:wrapped(layout, context, 'Client: '+_client_status, icon='error' if _client_status.startswith(('ERROR', 'BLOCKED')) else 'info')
        wrapped(layout, context, f'Rust F1: connect 127.0.0.1:{_job.port if active else state.port}')
        details = section(layout, 'ruster_preview_eac_checks', 'Setup and EAC Checks', 'locked')
        if details is not None:
            update = details.column();update.enabled = not active;update.prop(state, 'update_server')
            wrapped(details, context, 'Client preview is experimental. Use Launch Rust Without EAC or run RustClient.exe directly. Keep Steam running; Steam Play and Rust.exe launch EAC. Wait for the main menu before Inject.')
            wrapped(details, context, 'Inject verifies the executable, launch information, loaded modules, EAC processes, services and drivers. Incomplete inspection blocks injection. The server must report EAC disabled before Inject is enabled.')
            wrapped(details, context, 'New prefabs use the client\'s own asset loader. A failed load leaves the previous preview scene intact. Some assets may still require inclusion in the initial map.')
        console = section(layout, 'ruster_preview_console', 'Server Console', 'console', closed=False)
        if console is not None:
            row = console.row();row.enabled = running
            action(row, 'ruster.preview_owner')
            row = console.row(align=True);row.enabled = running
            row.prop(state, 'console', text='');action(row, 'ruster.preview_command', text='Send')
            console.prop(state, 'show_log')
            if state.show_log and _job:
                box = console.box()
                for line in _logs[-4:]:box.label(text=line[:140])
                if not _logs:box.label(text='Waiting for server output…', icon=ICONS['busy'])
                action(console, 'ruster.preview_logs')


def shutdown():
    if _job:_job.close()


def document_replaced():
    global _capture, _last_snapshot, _snapshot_error, _dirty
    if _job and _job.active:_job.request_stop()
    _capture = None;_last_snapshot = None;_snapshot_error = '';_dirty = True


def restore_settings():
    config = settings.load();state = bpy.context.window_manager.ruster_live_preview
    port = config.get('preview_port', 28015)
    state.port = port if type(port) is int and 1024 <= port <= 65533 else 28015
    state.owner = str(config.get('preview_owner', ''))


@persistent
def after_load(_dummy):
    document_replaced();restore_settings()
    if not bpy.app.timers.is_registered(tick):bpy.app.timers.register(tick, first_interval=.5, persistent=True)


def reset_state():
    global _job, _future, _future_kind, _clients, _probe_message, _next_probe, _last_snapshot, _error
    global _snapshot_error, _client_allowed, _module_loaded, _client_status, _logs, _status, _next_status
    global _dirty, _generation, _capture, _capture_generation, _capture_rows, _ui_signature
    _job = None;_future = None;_future_kind = '';_clients = [];_probe_message = 'Checking for Rust…'
    _next_probe = 0.;_last_snapshot = None;_error = '';_snapshot_error = ''
    _client_allowed = False;_module_loaded = False;_client_status = '';_logs = ()
    _status = {'status': 'IDLE', 'message': 'Start a private local Rust preview server'};_next_status = 0.
    _dirty = True;_generation = 0;_capture = None;_capture_generation = 0;_capture_rows = [];_ui_signature = None


def register():
    global _pool
    reset_state()
    for cls in (RUSTER_PG_live_preview, RUSTER_OT_start_live_preview, RUSTER_OT_stop_live_preview,
                RUSTER_OT_launch_preview_rust, RUSTER_OT_inject_preview, RUSTER_OT_preview_copy_ip,
                RUSTER_OT_preview_command, RUSTER_OT_preview_owner, RUSTER_OT_preview_logs):
        bpy.utils.register_class(cls);_classes.append(cls)
    bpy.types.WindowManager.ruster_live_preview = PointerProperty(type=RUSTER_PG_live_preview)
    restore_settings()
    _pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='Ruster preview client')
    bpy.app.timers.register(tick, first_interval=1., persistent=True)
    bpy.app.handlers.load_post.append(after_load)
    for handlers in (bpy.app.handlers.undo_pre, bpy.app.handlers.redo_pre, bpy.app.handlers.load_pre):handlers.append(invalidate_capture)
    for handlers in (bpy.app.handlers.depsgraph_update_post, bpy.app.handlers.undo_post, bpy.app.handlers.redo_post):handlers.append(scene_changed)
    atexit.register(shutdown)


def unregister():
    global _pool, _job, _future, _clients
    atexit.unregister(shutdown)
    if bpy.app.timers.is_registered(tick):bpy.app.timers.unregister(tick)
    if after_load in bpy.app.handlers.load_post:bpy.app.handlers.load_post.remove(after_load)
    for handlers in (bpy.app.handlers.undo_pre, bpy.app.handlers.redo_pre, bpy.app.handlers.load_pre):
        if invalidate_capture in handlers:handlers.remove(invalidate_capture)
    for handlers in (bpy.app.handlers.depsgraph_update_post, bpy.app.handlers.undo_post, bpy.app.handlers.redo_post):
        if scene_changed in handlers:handlers.remove(scene_changed)
    shutdown()
    if _pool:_pool.shutdown(wait=False, cancel_futures=True)
    _pool = None;reset_state()
    if hasattr(bpy.types.WindowManager, 'ruster_live_preview'):del bpy.types.WindowManager.ruster_live_preview
    for cls in reversed(_classes):bpy.utils.unregister_class(cls)
    _classes.clear()
