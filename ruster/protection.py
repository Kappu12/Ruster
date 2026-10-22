"""Read-only Rust model libraries and validation of placement-only editing.

Game geometry is linked, never appended to a map as editable meshes. Blender
itself rejects mesh edit/sculpt/modifier operations on these library IDs. This
is an authoring constraint, not a sandbox against arbitrary Python scripts.
"""
import hashlib
import os
import shutil
from pathlib import Path
import tempfile
import uuid
import bpy
from . import scene

VERSION=2
_classes=[]
_keymaps=[]


def library_path(key):
    token=hashlib.sha256((f'ruster-model-v{VERSION}:'+key).encode()).hexdigest()
    return scene.cache_dir()/'models'/f'{token}.blend'


def linked_collection(path,name):
    with bpy.data.libraries.load(str(path),link=True,relative=False) as (_source,destination):
        destination.collections=[name]
    collection=destination.collections[0]
    if collection is None:raise ValueError('Rust model library has no prefab collection')
    return collection


def freeze(collection,uid,key=None,verified=False):
    """Write an isolated preview library and replace its local IDs with linked IDs."""
    if collection.library and not collection.is_editable and collection.get('ruster_model_version')==VERSION:
        return collection
    key=key or 'legacy:'+str(uid)+':'+uuid.uuid4().hex
    path=library_path(key);path.parent.mkdir(parents=True,exist_ok=True)
    collection['ruster_model_version']=VERSION
    collection['ruster_uid']=str(uid)
    collection['ruster_model_verified']=verified
    collection['ruster_asset_key']=key
    objects=list(collection.all_objects)
    local_data={o.data for o in objects if o.data is not None and not o.data.library}
    local_materials={slot.material for o in objects for slot in o.material_slots if slot.material and not slot.material.library}
    local_materials.update(mat for data in local_data for mat in getattr(data,'materials',[]) if mat and not mat.library)
    local_images={node.image for mat in local_materials if mat.use_nodes for node in mat.node_tree.nodes
        if node.type=='TEX_IMAGE' and node.image and not node.image.library}
    for obj in objects:
        obj.hide_select=True
        obj.lock_location=(True,True,True)
        obj.lock_rotation=(True,True,True)
        obj.lock_scale=(True,True,True)
    fd,temp=tempfile.mkstemp(suffix='.blend',prefix='ruster-model-',dir=path.parent);os.close(fd)
    try:
        bpy.data.libraries.write(temp,{collection},fake_user=True,compress=True,path_remap='ABSOLUTE')
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)
    result=linked_collection(path,collection.name)
    # Local construction data must not remain as editable duplicates in the file.
    removable=[collection,*objects]
    # Shared fallback materials may still have external users: remove only data
    # owned by this preview after its local objects have been removed.
    collection.user_remap(result)
    bpy.data.batch_remove(ids=removable)
    orphaned=[data for data in local_data if data.users==0]
    if orphaned:bpy.data.batch_remove(ids=orphaned)
    for data in local_materials:
        if data.users==0:bpy.data.materials.remove(data)
    for image in local_images:
        if image.users==0:bpy.data.images.remove(image)
    return result


def protect_root(root):
    collection=root.instance_collection
    if collection and not collection.library and not collection.get('ruster_model_version'):
        root.instance_collection=freeze(collection,root['ruster_uid'])
    collection=root.instance_collection
    if collection and not collection.get('ruster_model_verified'):
        # Old local previews may already have been edited. Lock them immediately,
        # but only trust an original rebuilt from the user's local asset cache.
        if (scene.cache_dir()/'prefabs'/f"{root['ruster_uid']}.json.gz").exists():
            scene.attach_visual(root,force=True)
    return root.instance_collection


def model_error(root,checked=None):
    if root.type!='EMPTY' or root.data is not None:
        return 'Rust prefabs must remain whole model instances; custom mesh geometry cannot export'
    collection=root.instance_collection
    if not collection:
        return 'Prefab model was detached; restore its original model' if root.get('ruster_visual') else None
    if root.instance_type!='COLLECTION':return 'Prefab instancing was disabled; restore its original model'
    if (not collection.library or collection.is_editable or collection.override_library or
        collection.get('ruster_model_version')!=VERSION):
        return 'Prefab geometry must use the original read-only model; restore its original model'
    if not collection.get('ruster_model_verified'):
        return 'Legacy preview needs original Rust assets before export; load the map assets'
    if collection.get('ruster_uid')!=root.get('ruster_uid'):
        return 'Preview model does not match this Rust prefab ID'
    key=collection.as_pointer()
    if checked is not None and key in checked:return checked[key]
    for obj in collection.all_objects:
        if not obj.library or obj.is_editable or obj.override_library:
            return 'Editable prefab model parts cannot export'
        if obj.data and (not obj.data.library or obj.data.is_editable or obj.data.override_library):
            return 'Editable prefab mesh data cannot export'
    if checked is not None:checked[key]=None
    return None


def pack_models():
    # Native packing accepts relative paths only. Stage cross-drive libraries on
    # the active file's drive, then restore their real paths after packing. This
    # keeps Windows portable apps working when the app/cache use different drives.
    pending=[lib for lib in bpy.data.libraries if not lib.packed_file]
    if not pending:return
    originals={lib:str(Path(bpy.path.abspath(lib.filepath,library=lib.parent)).resolve()) for lib in pending}
    previous_cwd=Path.cwd()
    try:
        if not bpy.data.filepath:
            from .core.settings import user_root
            user_root().mkdir(parents=True,exist_ok=True)
            os.chdir(user_root())
        base=Path(bpy.path.abspath('//')).resolve()
        with tempfile.TemporaryDirectory(prefix='ruster-pack-',dir=base) as temporary:
            for index,lib in enumerate(pending):
                path=originals[lib]
                relative=bpy.path.relpath(path)
                if not relative.startswith('//'):
                    staged=Path(temporary)/f'model-{index}.blend'
                    shutil.copyfile(path,staged)
                    relative=bpy.path.relpath(str(staged))
                lib.filepath=relative
            bpy.ops.file.pack_libraries()
    finally:
        # Packed data do not require these files; retaining the real paths also
        # preserves correct resolution if the user explicitly unpacks later.
        for lib,path in originals.items():lib.filepath=path
        os.chdir(previous_cwd)


class RUSTER_OT_restore_models(bpy.types.Operator):
    bl_idname='ruster.restore_models'
    bl_label='Restore Original Prefab Models'
    bl_description='Restore selected placements to their original read-only models and remove unpacked preview parts'
    bl_options={'REGISTER','UNDO'}
    @classmethod
    def poll(cls,context):
        return bool(context.scene and context.scene.ruster.mode=='MAP')
    def execute(self,context):
        try:return self.restore(context)
        except Exception as error:
            self.report({'ERROR'},str(error));return {'CANCELLED'}
    def restore(self,context):
        from .placement import selected_prefabs
        roots=selected_prefabs()
        if not roots:
            self.report({'WARNING'},'Select prefab placements to restore');return {'CANCELLED'}
        ids={root['ruster_uid'] for root in roots}
        for obj in list(context.scene.objects):
            if obj.get('ruster_kind')=='VISUAL' and str(obj.get('ruster_source_uid','')) in ids:
                bpy.data.objects.remove(obj,do_unlink=True)
        failed=0
        for root in roots:
            collection=next((c for c in bpy.data.collections if c.library and not c.is_editable and
                c.get('ruster_uid')==root['ruster_uid'] and c.get('ruster_model_version')==VERSION and c.get('ruster_model_verified')),None)
            if root.type!='EMPTY':
                matrix=root.matrix_world.copy();parent=root.parent
                import base64
                from .core import wire
                replacement=scene.root_object(wire.parse(base64.b64decode(root['ruster_record'])),root.users_collection[0])
                replacement.parent=parent;replacement.matrix_world=matrix
                for child in list(root.children):
                    transform=child.matrix_world.copy();child.parent=replacement;child.matrix_world=transform
                bpy.data.objects.remove(root,do_unlink=True);root=replacement
                root.select_set(True);context.view_layer.objects.active=root
            original=scene.cache_dir()/'prefabs'/f"{root['ruster_uid']}.json.gz"
            if original.exists():
                scene.attach_visual(root,force=True)
            elif collection:
                root.instance_type='COLLECTION';root.instance_collection=collection;root['ruster_visual']=True
            else:
                root['ruster_visual']=False
                scene.attach_visual(root,force=True)
            if model_error(root):failed+=1
        if failed:self.report({'WARNING'},f'{failed} models still need their original local Rust assets; load the map assets')
        return {'FINISHED'}


class RUSTER_MT_commands(bpy.types.Menu):
    bl_label='Ruster Commands'
    def draw(self,context):
        layout=self.layout
        layout.operator('ruster.open');layout.operator('ruster.save')
        layout.operator('ruster.validate');layout.operator('ruster.export_map')
        layout.separator()
        layout.operator('ruster.duplicate');layout.operator('ruster.delete')
        layout.operator('ruster.group');layout.operator('ruster.ungroup')
        layout.operator('ruster.surface_snap');layout.operator('ruster.restore_models')
        layout.separator()
        layout.operator_menu_enum('ruster.path_add','kind',text='Add Path')
        layout.operator('wm.tool_set_by_id',text='Terrain Brush').name='ruster.terrain_brush'
        layout.operator('wm.tool_set_by_id',text='Prefab Paint').name='ruster.prefab_brush'
        layout.operator('ruster.assembly_import')


class RUSTER_OT_commands(bpy.types.Operator):
    bl_idname='ruster.commands'
    bl_label='Ruster Commands'
    @classmethod
    def poll(cls,context):
        return bool(context.scene and context.scene.ruster.mode=='MAP')
    def execute(self,context):
        bpy.ops.wm.call_menu(name='RUSTER_MT_commands');return {'FINISHED'}


def register():
    for cls in (RUSTER_OT_restore_models,RUSTER_MT_commands,RUSTER_OT_commands):
        bpy.utils.register_class(cls);_classes.append(cls)
    config=bpy.context.window_manager.keyconfigs.addon
    if config:
        km=config.keymaps.new(name='Window',space_type='EMPTY')
        for key,shift,ctrl in [('F3',False,False),('A',True,False),('A',False,True)]:
            item=km.keymap_items.new('ruster.commands',key,'PRESS',shift=shift,ctrl=ctrl)
            _keymaps.append((km,item))


def unregister():
    for km,item in _keymaps:km.keymap_items.remove(item)
    _keymaps.clear()
    for cls in reversed(_classes):bpy.utils.unregister_class(cls)
    _classes.clear()
