"""Project-aware closing; Blender's private .blend is never a save target."""
import hashlib
import json
import re
import time
from pathlib import Path

import bpy
from bpy.props import EnumProperty, StringProperty

_saved = None
_dialog_open = False
_classes = []
_dirty = False
_continuation = None
_status_scan = None
STATUS_CHECK_BUDGET = .003
STATUS_STEPS_PER_TICK = 32

# Original source records and group metadata are the editable document.
# Model loading/status, selection, cursor and viewport settings are previews.
DOCUMENT_PROPERTIES = ('ruster_kind', 'ruster_uid', 'ruster_record',
                       'ruster_prefab_source', 'ruster_prefab_index',
                       'ruster_linked_extensions', 'ruster_prefab_matrix',
                       'ruster_instance', 'ruster_symmetry_source',
                       'ruster_symmetry_center', 'ruster_symmetry_angle',
                       'ruster_symmetry_axis', 'ruster_symmetry_rotate')


def property_value(value):
    return value.to_list() if hasattr(value, 'to_list') else value


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def collection_steps(collection):
    children = []
    for child in collection.children:
        children.append((yield from collection_steps(child)))
    value = digest((collection.name, collection.hide_viewport, collection.hide_render,
                    sorted(children)))
    yield
    return value


def fingerprint_steps():
    """Hash independent records so timer scans can yield before encoding more."""
    state = bpy.context.scene.ruster
    objects, sources = [], set()
    for obj in bpy.context.scene.objects:
        if obj.get('ruster_kind') == 'VISUAL':
            yield
            continue
        if source := obj.get('ruster_prefab_source'):sources.add(source)
        # A generated name may change when a cached model arrives after Save.
        generated = obj.get('ruster_generated_name')
        placeholder = (not generated and obj.get('ruster_kind') == 'PREFAB'
                       and re.fullmatch(r'Prefab '+str(obj.get('ruster_uid', ''))+r'(?:\.\d+)?', obj.name))
        name = '' if obj.name == generated or placeholder else obj.name
        parent = obj.parent
        objects.append(digest((name, obj.type, parent.name if parent else '',
                        tuple(tuple(row) for row in obj.matrix_basis),
                        tuple(tuple(row) for row in obj.matrix_parent_inverse),
                        tuple((key, property_value(obj.get(key))) for key in DOCUMENT_PROPERTIES),
                        tuple(sorted(c.name for c in obj.users_collection)),
                        obj.hide_viewport, obj.hide_render, obj.hide_get())))
        yield
    texts = []
    for name in sorted(sources):
        text = bpy.data.texts.get(name)
        content = None
        if text is not None:
            content = hashlib.sha256()
            for line in text.lines:
                body = line.body
                for offset in range(0, len(body), 65536):
                    content.update(body[offset:offset+65536].encode())
                    yield
                content.update(b'\n')
                yield
            content = content.hexdigest()
        texts.append((name, content))
        yield
    collections = yield from collection_steps(bpy.context.scene.collection)
    settings = bpy.context.scene.ruster_construction
    construction = (settings.object_snap, settings.snap_element, settings.angle_snap,
                    settings.symmetry, settings.sides, tuple(settings.center), settings.axis, settings.rotate_copies)
    document = (state.mode, state.title, state.project_path, state.source_map, state.map_size,
                sorted(objects), texts, construction, collections)
    return digest(document)


def fingerprint():
    steps = fingerprint_steps()
    while True:
        try:next(steps)
        except StopIteration as finished:return finished.value


def mark_saved():
    global _saved, _dirty, _status_scan
    _status_scan = None
    _saved = fingerprint()
    _dirty = False


def reset():
    global _saved, _dialog_open, _dirty, _status_scan
    _status_scan = None
    _saved = None
    _dialog_open = False
    _dirty = False


def has_unsaved_changes():
    if _saved is not None:
        state = bpy.context.scene.ruster
        return (not state.project_path or not Path(state.project_path).is_file()
                or fingerprint() != _saved)
    return bool(bpy.context.scene.objects)


def save_status():
    """Drawing reads the result of the most recent bounded document scan."""
    state = bpy.context.scene.ruster
    if _dirty:return 'Unsaved changes'
    return 'Saved' if state.project_path else 'Not saved yet'


def status_tick():
    global _dirty, _status_scan
    if not hasattr(bpy.context.scene, 'ruster'):return 1.
    if bpy.context.window_manager.is_interface_locked:return 1.
    state = bpy.context.scene.ruster
    if _saved is None:
        _status_scan = None
        dirty = bool(bpy.context.scene.objects)
    elif not state.project_path or not Path(state.project_path).is_file():
        _status_scan = None
        dirty = True
    else:
        if _status_scan is None:_status_scan = fingerprint_steps()
        deadline = time.perf_counter() + STATUS_CHECK_BUDGET
        try:
            for _ in range(STATUS_STEPS_PER_TICK):
                try:next(_status_scan)
                except StopIteration as finished:
                    _status_scan = None
                    dirty = finished.value != _saved
                    break
                if time.perf_counter() >= deadline:return .01
            else:return .01
        except ReferenceError:
            # A native deletion or file load can invalidate a yielded RNA value.
            _status_scan = None
            return .01
    if dirty != _dirty:
        _dirty = dirty
        from .app import redraw
        redraw()
    return 1.


def continue_action(action, filepath=''):
    if action == 'NEW':return bpy.ops.ruster.new('EXEC_DEFAULT')
    if action == 'OPEN':return bpy.ops.ruster.open('EXEC_DEFAULT', filepath=filepath)
    raise ValueError('Unknown project action')


def perform_pending_action():
    global _continuation
    pending, _continuation = _continuation, None
    if pending is None:return None
    action, filepath, window = pending
    windows = list(bpy.context.window_manager.windows)
    if window not in windows:window = windows[0] if windows else None
    if window:
        area=next((area for area in window.screen.areas if area.type=='VIEW_3D'),None)
        region=next((region for region in area.regions if region.type=='WINDOW'),None) if area else None
        with bpy.context.temp_override(window=window,area=area,region=region):continue_action(action, filepath)
    return None


def schedule_action(action, filepath=''):
    """Let the save file selector close before opening another document/picker."""
    global _continuation
    _continuation = (action, filepath, bpy.context.window)
    if not bpy.app.timers.is_registered(perform_pending_action):
        bpy.app.timers.register(perform_pending_action, first_interval=.1)


def confirm_replacement(action, filepath=''):
    if not has_unsaved_changes():return continue_action(action, filepath)
    return bpy.ops.ruster.save_changes('INVOKE_DEFAULT', action=action, filepath=filepath)


class RUSTER_OT_save_changes(bpy.types.Operator):
    bl_idname = 'ruster.save_changes'
    bl_label = 'Save Changes'
    action: EnumProperty(items=[('NEW', 'New Prefab', ''), ('OPEN', 'Open Project', '')])
    filepath: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})

    def invoke(self, context, event):
        global _dialog_open
        if _dialog_open:return {'CANCELLED'}
        _dialog_open = True
        title = 'Save changes before starting a new prefab?' if self.action == 'NEW' else 'Save changes before opening?'
        window=context.window
        original=(event.mouse_x,event.mouse_y)
        try:
            window.cursor_warp(window.width//2,window.height//2)
            return context.window_manager.invoke_props_dialog(self, width=440,
                title=title, confirm_text='Save')
        finally:window.cursor_warp(*original)

    def draw(self, context):
        state = context.scene.ruster
        filename = Path(state.project_path).name if state.project_path else state.title + '.ruster'
        self.layout.label(text=filename, icon='FILE')
        # A regular operator button leaves native property dialogs open.
        # This template closes the popup before running its continuation.
        discard = self.layout.template_popup_confirm('ruster.discard_changes', text="Don't Save",
            cancel_text='',cancel_default=True)  # Return remains bound to the parent Save button.
        discard.action, discard.filepath = self.action, self.filepath

    def execute(self, context):
        global _dialog_open
        _dialog_open = False
        return bpy.ops.ruster.save('INVOKE_DEFAULT', after_save=self.action, next_filepath=self.filepath)

    def cancel(self, context):
        global _dialog_open
        _dialog_open = False


class RUSTER_OT_discard_changes(bpy.types.Operator):
    bl_idname = 'ruster.discard_changes'
    bl_label = "Don't Save"
    bl_description = 'Continue without saving the latest project changes'
    action: EnumProperty(items=[('NEW', 'New Prefab', ''), ('OPEN', 'Open Project', '')])
    filepath: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})

    def execute(self, context):
        global _dialog_open
        _dialog_open = False
        schedule_action(self.action, self.filepath)
        return {'FINISHED'}


def finish_quit():
    # EXEC bypasses the native .blend confirmation after our own decision.
    from . import preview_jobs
    preview_jobs.cancel()
    bpy.ops.wm.quit_blender('EXEC_DEFAULT')


def schedule_quit():
    global _dialog_open
    _dialog_open = False
    if not bpy.app.timers.is_registered(finish_quit):
        bpy.app.timers.register(finish_quit, first_interval=.1)


class RUSTER_OT_quit(bpy.types.Operator):
    bl_idname = 'ruster.quit'
    bl_label = 'Quit Ruster'
    bl_description = 'Close Ruster, offering to save changes to the .ruster project'

    def invoke(self, context, event):
        global _dialog_open
        if _dialog_open:return {'CANCELLED'}
        if not has_unsaved_changes():
            schedule_quit()
            return {'FINISHED'}
        _dialog_open = True
        window = context.window
        original = (event.mouse_x, event.mouse_y)
        try:
            window.cursor_warp(window.width//2, window.height//2)
            return context.window_manager.invoke_props_dialog(self, width=410,
                title='Save changes before closing?', confirm_text='Save')
        finally:
            window.cursor_warp(*original)

    def draw(self, context):
        state = context.scene.ruster
        filename = Path(state.project_path).name if state.project_path else state.title + '.ruster'
        self.layout.label(text=filename, icon='FILE')
        self.layout.template_popup_confirm('ruster.discard_and_quit', text="Don't Save", cancel_text='',cancel_default=True)

    def execute(self, context):
        global _dialog_open
        _dialog_open = False
        return bpy.ops.ruster.save('INVOKE_DEFAULT', quit_after_save=True)

    def cancel(self, context):
        global _dialog_open
        _dialog_open = False


class RUSTER_OT_discard_and_quit(bpy.types.Operator):
    bl_idname = 'ruster.discard_and_quit'
    bl_label = "Don't Save"
    bl_description = 'Close Ruster without saving the latest changes'

    def execute(self, context):
        schedule_quit()
        return {'FINISHED'}


def register():
    reset()
    for cls in (RUSTER_OT_quit, RUSTER_OT_discard_and_quit, RUSTER_OT_save_changes, RUSTER_OT_discard_changes):
        bpy.utils.register_class(cls);_classes.append(cls)
    if not bpy.app.background:
        bpy.app.timers.register(status_tick, first_interval=1., persistent=True)
    from . import native_close
    native_close.register()


def unregister():
    global _continuation
    from . import native_close
    native_close.unregister()
    if bpy.app.timers.is_registered(finish_quit):bpy.app.timers.unregister(finish_quit)
    for callback in (status_tick, perform_pending_action):
        if bpy.app.timers.is_registered(callback):bpy.app.timers.unregister(callback)
    _continuation = None
    for cls in reversed(_classes):bpy.utils.unregister_class(cls)
    _classes.clear()
    reset()
