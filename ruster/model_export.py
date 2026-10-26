"""Export disposable realized copies; protected Rust libraries stay read-only."""
from contextlib import contextmanager
from pathlib import Path
import subprocess
import tempfile
import bpy
from mathutils import Matrix
from .model_geometry import placement_meshes

# Only formats whose operators exist in this Blender build are offered.
FORMATS = {
    'GLB': ('glTF Binary', '.glb', 'export_scene.gltf', {'export_format': 'GLB', 'use_selection': True, 'use_active_scene': True, 'export_animations': False}),
    'GLTF': ('glTF', '.gltf', 'export_scene.gltf', {'export_format': 'GLTF_SEPARATE', 'use_selection': True, 'use_active_scene': True, 'export_animations': False}),
    'FBX': ('FBX', '.fbx', 'export_scene.fbx', {'use_selection': True, 'bake_anim': False, 'path_mode': 'COPY', 'embed_textures': True}),
    'OBJ': ('Wavefront OBJ', '.obj', 'wm.obj_export', {'export_selected_objects': True, 'path_mode': 'COPY'}),
    'PLY': ('PLY', '.ply', 'wm.ply_export', {'export_selected_objects': True}),
    'STL': ('STL', '.stl', 'wm.stl_export', {'export_selected_objects': True}),
    'USD': ('Universal Scene Description', '.usd', 'wm.usd_export', {'selected_objects_only': True, 'export_textures_mode': 'NEW'}),
    'USDA': ('USD ASCII', '.usda', 'wm.usd_export', {'selected_objects_only': True, 'export_textures_mode': 'NEW'}),
    'USDC': ('USD Binary', '.usdc', 'wm.usd_export', {'selected_objects_only': True, 'export_textures_mode': 'NEW'}),
    'ABC': ('Alembic', '.abc', 'wm.alembic_export', {'selected': True, 'start': 1, 'end': 1, 'as_background_job': False}),
    'BLEND': ('Blender Scene', '.blend', None, {}),
}


def operator(name):
    group, name = name.split('.')
    return getattr(getattr(bpy.ops, group), name)


def available_formats():
    result = []
    for key, (label, extension, name, _kwargs) in FORMATS.items():
        try:
            if name:operator(name).get_rna_type()
        except (AttributeError, RuntimeError):continue
        result.append((key, label + ' (' + extension + ')', label))
    return result


@contextmanager
def realized_scene(roots, local_dependencies=False, pack_images=False):
    from .protection import model_error
    from .scene import matrix_has_shear
    roots = list(roots)
    if not roots:raise ValueError('Select Rust prefab placements to export')
    sources, unique, vertices = [], set(), 0
    transforms={}
    for root in roots:
        problem = model_error(root)
        if problem:raise ValueError(root.name + ': ' + problem)
        if root.get('ruster_marker') in {'SOUND','EFFECT','VOLUME'}:continue
        collection = root.instance_collection
        if not collection:raise ValueError(root.name + ': load its original Rust model before model export')
        for obj,matrix in placement_meshes(root,transforms):
            # Flattened objects cannot store shear in location/rotation/scale.
            # Bake the full affine matrix into an isolated copy when necessary.
            # Count those copies against the existing mesh allocation budget.
            baked=matrix_has_shear(matrix)
            key=(obj.data.as_pointer(),tuple(v for row in matrix for v in row) if baked else None)
            sources.append((obj,matrix,key,baked))
            if key not in unique:
                unique.add(key);vertices += len(obj.data.vertices)
    if not sources:raise ValueError('Selected prefabs have no readable mesh geometry')
    if len(sources) > 50000 or vertices > 2000000:
        raise ValueError('Export exceeds the bounded model budget; export a smaller selection')
    temporary = bpy.data.scenes.new('Ruster Model Export')
    meshes = {}
    materials, images = {}, {}
    texture_directory = tempfile.TemporaryDirectory(prefix='ruster-export-textures-')
    image_bytes = 0
    def local_material(material):
        nonlocal image_bytes
        if not material or not local_dependencies:return material
        key=material.as_pointer()
        if key not in materials:
            result=materials[key]=material.copy()
            if result.use_nodes:
                for node in result.node_tree.nodes:
                    if node.type!='TEX_IMAGE' or not node.image:continue
                    image=node.image;image_key=image.as_pointer()
                    if image_key not in images:
                        image_bytes+=image.size[0]*image.size[1]*16
                        if image_bytes>256*1024*1024:
                            raise ValueError('Textures exceed the bounded library copy budget; export a smaller selection')
                        # Native OBJ and FBX resolve image file paths even when
                        # source images are packed in a linked model library.
                        texture=Path(texture_directory.name)/(str(image_key)+(Path(image.filepath).suffix or '.png'))
                        if not image.packed_file:raise ValueError('Original model texture is not packed')
                        texture.write_bytes(image.packed_file.data)
                        result_image=images[image_key]=bpy.data.images.load(str(texture),check_existing=False)
                        result_image.colorspace_settings.name=image.colorspace_settings.name
                        if pack_images:result_image.pack()
                    node.image=images[image_key]
        return materials[key]
    window = bpy.context.window
    original_scene = window.scene if window else None
    try:
        for obj, matrix, key, baked in sources:
            if key not in meshes:
                meshes[key] = obj.data.copy()
                if baked:
                    meshes[key].transform(matrix)
                    if matrix.determinant()<0:meshes[key].flip_normals()
                    meshes[key].update()
                if local_dependencies:
                    for index, material in enumerate(meshes[key].materials):
                        meshes[key].materials[index]=local_material(material)
            copy = bpy.data.objects.new(obj.name, meshes[key])
            temporary.collection.objects.link(copy)
            copy.matrix_world = Matrix.Identity(4) if baked else matrix
            # Source assets can use per-object material overrides.
            for index, slot in enumerate(obj.material_slots):
                if index < len(copy.material_slots):
                    copy.material_slots[index].link = 'OBJECT'
                    copy.material_slots[index].material = local_material(slot.material)
        if window:window.scene = temporary
        with bpy.context.temp_override(scene=temporary, view_layer=temporary.view_layers[0]):
            temporary.view_layers[0].update()
            for obj in temporary.objects:obj.select_set(True)
            temporary.view_layers[0].objects.active = next(iter(temporary.objects))
            yield temporary
    finally:
        if window:window.scene = original_scene
        for obj in list(temporary.objects):bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.scenes.remove(temporary)
        for mesh in meshes.values():
            if mesh.users == 0:bpy.data.meshes.remove(mesh)
        for material in materials.values():
            if material.users==0:bpy.data.materials.remove(material)
        for image in images.values():
            if image.users==0:bpy.data.images.remove(image)
        texture_directory.cleanup()


def write_blend_scene(path, temporary):
    """Save only the realized scene, with standard Blender workspaces and no cache links."""
    # Saving this editor's mainfile would include protected originals and other
    # scenes. Write the isolated scene, then let a factory Blender process turn
    # that library into a regular mainfile without touching the user's session.
    with tempfile.TemporaryDirectory(prefix='.ruster-blend-', dir=path.parent) as directory:
        staged = Path(directory)/path.name
        bpy.data.libraries.write(str(staged), {temporary}, fake_user=True, compress=True)
        code = ('import bpy; bpy.context.preferences.filepaths.save_version=0; '
                "bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath, check_existing=False, compress=True)")
        completed = subprocess.run([bpy.app.binary_path, '-b', '-t', '2', '--factory-startup',
            '--disable-autoexec', str(staged), '--python-exit-code', '1', '--python-expr', code],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace',
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), timeout=180)
        if completed.returncode or not staged.is_file() or not staged.stat().st_size:
            raise ValueError('Blender scene export failed: '+completed.stdout[-2000:])
        staged.replace(path)


def export_models(path, format_, roots):
    if format_ not in {item[0] for item in available_formats()}:
        raise ValueError('That exporter is unavailable in this Blender build')
    _label, extension, name, kwargs = FORMATS[format_]
    path = Path(path).with_suffix(extension)
    path.parent.mkdir(parents=True, exist_ok=True)
    with realized_scene(roots, local_dependencies=format_ in {'BLEND','FBX','OBJ','USD','USDA','USDC'},
                        pack_images=format_=='BLEND') as temporary:
        if name:
            result = operator(name)(filepath=str(path), **kwargs)
            if result != {'FINISHED'}:raise ValueError('Model exporter did not finish')
        else:
            write_blend_scene(path, temporary)
    if not path.is_file() or not path.stat().st_size:raise ValueError('Exporter did not produce a model file')
    return path
