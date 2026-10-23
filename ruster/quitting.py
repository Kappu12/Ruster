"""Project-aware closing; Blender's private .blend is never a save target."""
import hashlib
import json
import re
from pathlib import Path

import bpy

_saved = None
_dialog_open = False
_classes = []

# Original source records and group metadata are the editable document.
# Model loading/status, selection, cursor and viewport settings are previews.
DOCUMENT_PROPERTIES = ('ruster_kind', 'ruster_uid', 'ruster_record',
                       'ruster_prefab_source', 'ruster_prefab_index',
                       'ruster_linked_extensions', 'ruster_prefab_matrix',
                       'ruster_instance', 'ruster_symmetry_source',
                       'ruster_symmetry_center', 'ruster_symmetry_angle')


def property_value(value):
    return value.to_list() if hasattr(value, 'to_list') else value


def collection_tree(collection):
    return (collection.name, collection.hide_viewport, collection.hide_render,
            sorted(collection_tree(child) for child in collection.children))


def fingerprint():
    state = bpy.context.scene.ruster
    objects, sources = [], set()
    for obj in bpy.context.scene.objects:
        if obj.get('ruster_kind') == 'VISUAL':continue
        if source := obj.get('ruster_prefab_source'):sources.add(source)
        # A generated name may change when a cached model arrives after Save.
        generated = obj.get('ruster_generated_name')
        placeholder = (not generated and obj.get('ruster_kind') == 'PREFAB'
                       and re.fullmatch(r'Prefab '+str(obj.get('ruster_uid', ''))+r'(?:\.\d+)?', obj.name))
        name = '' if obj.name == generated or placeholder else obj.name
        parent = obj.parent
        objects.append((name, obj.type, parent.name if parent else '',
                        tuple(tuple(row) for row in obj.matrix_basis),
                        tuple(tuple(row) for row in obj.matrix_parent_inverse),
                        tuple((key, property_value(obj.get(key))) for key in DOCUMENT_PROPERTIES),
                        tuple(sorted(c.name for c in obj.users_collection)),
                        obj.hide_viewport, obj.hide_render, obj.hide_get()))
    texts = [(name, bpy.data.texts[name].as_string() if name in bpy.data.texts else None)
             for name in sorted(sources)]
    settings = bpy.context.scene.ruster_construction
    construction = (settings.object_snap, settings.snap_element, settings.angle_snap,
                    settings.symmetry, settings.sides, tuple(settings.center))
    document = (state.mode, state.title, state.project_path, state.source_map, state.map_size,
                sorted(objects, key=repr), texts, construction,
                collection_tree(bpy.context.scene.collection))
    return hashlib.sha256(json.dumps(document, sort_keys=True).encode()).digest()


def mark_saved():
    global _saved
    _saved = fingerprint()


def reset():
    global _saved, _dialog_open
    _saved = None
    _dialog_open = False


def has_unsaved_changes():
    if _saved is not None:
        state = bpy.context.scene.ruster
        return (not state.project_path or not Path(state.project_path).is_file()
                or fingerprint() != _saved)
    return bool(bpy.context.scene.objects)


def finish_quit():
    # EXEC bypasses the native .blend confirmation after our own decision.
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
        self.layout.operator('ruster.discard_and_quit', text="Don't Save")

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
    for cls in (RUSTER_OT_quit, RUSTER_OT_discard_and_quit):
        bpy.utils.register_class(cls);_classes.append(cls)
    from . import native_close
    native_close.register()


def unregister():
    from . import native_close
    native_close.unregister()
    if bpy.app.timers.is_registered(finish_quit):bpy.app.timers.unregister(finish_quit)
    for cls in reversed(_classes):bpy.utils.unregister_class(cls)
    _classes.clear()
    reset()
