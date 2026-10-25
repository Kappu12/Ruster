"""Explicit local playtest controls; importing this never touches a game process."""
import atexit
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import os
from pathlib import Path
import sys
import time

import bpy
from bpy.props import BoolProperty, IntProperty, PointerProperty, StringProperty

from .core import live_preview as backend, preview_client, settings
from .core.preview_protocol import MAX_PLACEMENTS
from .ui_style import properties, wrapped, section

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


def installation():
    from .core import steam
    path = steam.resolve_install(settings.load().get('rust_install', ''))
    if not path:raise ValueError('Choose your Rust installation in Preferences > Assets first')
    return path


def dll_path():return Path(__file__).resolve().parent/'preview_native/bin/RusterPreview.dll'


def placements():
    from . import scene
    from .assets import catalog
    bpy.context.view_layer.update()
    roots = scene.prefab_roots()
    if len(roots) > MAX_PLACEMENTS:raise ValueError('Live preview supports at most 2,000 prefab placements')
    if not roots:return []
    rows = []
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
            rows.append({'key': root.session_uid, 'uid': uid, 'path': path,
                'position': scene.to_unity(location), 'rotation': (unity.x, unity.y, unity.z, unity.w),
                'scale': scene.to_unity(scale), 'euler': scene.blender_euler(rotation)})
    return sorted(rows, key=lambda row: row['key'])


def status():return _job.info() if _job else {'status': 'IDLE', 'message': 'Start a private local Rust preview server'}


def submit(kind, function, *args):
    global _future, _future_kind, _error
    if _future and not _future.done():raise ValueError('Wait for the current client operation to finish')
    _error = '';_future_kind = kind;_future = _pool.submit(function, *args)


def tick():
    global _future, _future_kind, _clients, _probe_message, _next_probe, _error, _last_snapshot
    from .app import redraw
    if _future and _future.done():
        kind, future = _future_kind, _future;_future = None
        try:
            result = future.result()
            if kind == 'probe':
                _clients = result
                if not result:_probe_message = 'Rust is not running'
                elif len(result) != 1:_probe_message = 'Close extra Rust instances before injecting'
                else:
                    try:preview_client.verify_probe(result[0], installation());_probe_message = 'Process checks passed; EAC will be checked again on Inject'
                    except ValueError as error:_probe_message = str(error)
            elif kind == 'launch':_probe_message = 'Rust is starting. Wait for the main menu.'
            elif kind == 'inject':_probe_message = 'Preview DLL loaded; waiting for its compatibility check'
        except Exception as error:
            if kind == 'probe':_clients = [];_probe_message = str(error)
            else:_error = str(error)
        _next_probe = time.monotonic()+3
    if (not _future) and time.monotonic() >= _next_probe and not os.environ.get('RUSTER_PREVIEW_TEST_NO_DISCOVERY'):
        try:submit('probe', preview_client.discover, installation())
        except ValueError as error:_probe_message = str(error);_next_probe = time.monotonic()+5
    if _job and _job.active:
        try:
            rows = placements()
            if rows != _last_snapshot:_job.update(rows);_last_snapshot = rows
        except Exception as error:_error = str(error)
    redraw()
    return .5


class RUSTER_PG_live_preview(bpy.types.PropertyGroup):
    port: IntProperty(name='Game Port', default=28015, min=1024, max=65533, options={'SKIP_SAVE'})
    owner: StringProperty(name='Owner Steam ID', description='Optional 17-digit SteamID64', options={'SKIP_SAVE'})
    console: StringProperty(name='Command', description='Run a command on this local preview server', options={'SKIP_SAVE'})
    show_log: BoolProperty(name='Console Log', default=True, options={'SKIP_SAVE'})


class RUSTER_OT_start_live_preview(bpy.types.Operator):
    bl_idname = 'ruster.start_live_preview'
    bl_label = 'Start Live Preview'
    bl_description = 'Download a dedicated server on first use, then start a private local preview'
    def execute(self, context):
        global _job, _last_snapshot, _error
        try:
            if _job and _job.active:raise ValueError('Live preview is already running')
            if not dll_path().is_file():raise ValueError('Preview DLL is missing. Run tools/build_preview_client.py when running from source')
            state = context.window_manager.ruster_live_preview
            rows = placements()
            config = settings.load();config['preview_port'] = state.port;config['preview_owner'] = backend.owner_id(state.owner);settings.save(config)
            _job = backend.PreviewSession(settings.user_root()/'live-preview', state.port, state.owner, rows).start()
            _last_snapshot = rows;_error = ''
            return {'FINISHED'}
        except Exception as error:self.report({'ERROR'}, str(error));return {'CANCELLED'}


class RUSTER_OT_stop_live_preview(bpy.types.Operator):
    bl_idname = 'ruster.stop_live_preview'
    bl_label = 'Stop Live Preview'
    def execute(self, context):
        if _job:_job.request_stop()
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
    def execute(self, context):
        port = _job.port if _job else context.window_manager.ruster_live_preview.port
        context.window_manager.clipboard = f'127.0.0.1:{port}'
        self.report({'INFO'}, 'Local preview address copied');return {'FINISHED'}


class RUSTER_OT_preview_command(bpy.types.Operator):
    bl_idname = 'ruster.preview_command'
    bl_label = 'Send'
    owner: BoolProperty(default=False, options={'SKIP_SAVE'})
    def execute(self, context):
        try:
            if not _job:raise ValueError('Start live preview first')
            state = context.window_manager.ruster_live_preview
            value = 'ownerid '+backend.owner_id(state.owner)+' "Ruster preview owner"' if self.owner else state.console
            if self.owner and not backend.owner_id(state.owner):raise ValueError('Enter your SteamID64 first')
            _job.send_command(value)
            if not self.owner:state.console = ''
            return {'FINISHED'}
        except Exception as error:self.report({'ERROR'}, str(error));return {'CANCELLED'}


class RUSTER_PT_live_preview(bpy.types.Panel):
    bl_label = 'Live Preview'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Ruster'
    bl_options = {'DEFAULT_CLOSED'}
    def draw(self, context):
        layout = self.layout;state = context.window_manager.ruster_live_preview
        if sys.platform != 'win32':
            wrapped(layout, context, 'Client live preview currently requires Windows x64.', icon='info')
            return
        active = bool(_job and _job.active);running = bool(_job and _job.status == 'RUNNING')
        wrapped(layout, context, 'First start downloads a separate local Rust server (several GB).')
        fields = properties(layout.column());fields.enabled = not active
        fields.prop(state, 'port')
        properties(layout.column()).prop(state, 'owner')
        controls = layout.column()
        controls.operator('ruster.stop_live_preview' if active else 'ruster.start_live_preview', icon='PAUSE' if active else 'PLAY')
        wrapped(layout, context, status()['message'], icon='busy' if active and not running else 'info')
        row = layout.row(align=True);row.label(text=f'127.0.0.1:{_job.port if active else state.port}')
        row.operator('ruster.preview_copy_ip', icon='COPYDOWN')
        layout.separator()
        wrapped(layout, context, 'Launch RustClient.exe directly, or use the button below. Steam Play launches EAC. Wait for the main menu before injecting.', icon='info')
        row = layout.row();row.enabled = not bool(_future)
        if _clients:
            allowed = False
            if len(_clients) == 1:
                try:preview_client.verify_probe(_clients[0], installation());allowed = True
                except ValueError:pass
            row.enabled = row.enabled and running and allowed
            row.operator('ruster.inject_preview', icon='PLUGIN')
        else:row.operator('ruster.launch_preview_rust', icon='PLAY')
        wrapped(layout, context, _probe_message, icon='info')
        wrapped(layout, context, 'Active or unknown EAC blocks Inject. Restart Rust after preview before joining EAC servers.', icon='locked')
        if _error:wrapped(layout, context, _error, icon='error')
        if _job:
            try:
                lines = (_job.directory/'client.status').read_text().splitlines()
                if lines:wrapped(layout, context, 'Client: '+ ' — '.join(lines[:2]), icon='info')
            except OSError:pass
        wrapped(layout, context, 'In Rust: F1, then connect followed by the copied IP. Client preview is experimental.')
        details = section(layout, 'ruster_preview_eac_checks', 'EAC Checks', 'locked')
        if details is not None:
            wrapped(details, context, 'Inject verifies the executable, launch information, loaded modules, EAC processes, services and drivers. Incomplete inspection blocks injection. The server must report EAC disabled before Inject is enabled.')
        row = layout.row();row.enabled = running
        row.operator('ruster.preview_command', text='Grant Owner ID', icon='USER').owner = True
        row = layout.row(align=True);row.enabled = running
        row.prop(state, 'console', text='');row.operator('ruster.preview_command', icon='CONSOLE')
        layout.prop(state, 'show_log')
        if state.show_log and _job:
            box = layout.box()
            for line in _job.log_tail(8):box.label(text=line[:140])
            layout.operator('wm.path_open', text='Open Preview Logs', icon='FILE_FOLDER').filepath = str(_job.directory)


def shutdown():
    if _job:_job.close()


def register():
    global _pool
    for cls in (RUSTER_PG_live_preview, RUSTER_OT_start_live_preview, RUSTER_OT_stop_live_preview,
                RUSTER_OT_launch_preview_rust, RUSTER_OT_inject_preview, RUSTER_OT_preview_copy_ip, RUSTER_OT_preview_command):
        bpy.utils.register_class(cls);_classes.append(cls)
    bpy.types.WindowManager.ruster_live_preview = PointerProperty(type=RUSTER_PG_live_preview)
    config = settings.load();state = bpy.context.window_manager.ruster_live_preview
    port = config.get('preview_port', 28015)
    state.port = port if type(port) is int and 1024 <= port <= 65533 else 28015
    state.owner = str(config.get('preview_owner', ''))
    _pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='Ruster preview client')
    bpy.app.timers.register(tick, first_interval=1.)
    atexit.register(shutdown)


def unregister():
    global _pool, _job, _future, _clients
    atexit.unregister(shutdown)
    if bpy.app.timers.is_registered(tick):bpy.app.timers.unregister(tick)
    shutdown()
    if _pool:_pool.shutdown(wait=False, cancel_futures=True)
    _pool = None;_job = None;_future = None;_clients = []
    if hasattr(bpy.types.WindowManager, 'ruster_live_preview'):del bpy.types.WindowManager.ruster_live_preview
    for cls in reversed(_classes):bpy.utils.unregister_class(cls)
    _classes.clear()
