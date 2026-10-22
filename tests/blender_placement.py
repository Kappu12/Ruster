"""Grouping, reusable prefab assemblies, scatter and transforms in Blender."""
import os
from pathlib import Path
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
if '--' in sys.argv and sys.argv[sys.argv.index('--')+1:]:
    sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import bpy
from mathutils import Vector
import ruster
from ruster import scene,placement
from ruster.core.rust_map import RustMap,prefab_transform
from tests.fixtures import sample_world


def run():
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp);os.environ['RUSTER_USER_DIR']=str(root/'user')
        ruster.register()
        source=root/'source.map';source.write_bytes(sample_world().write());scene.import_map(source)
        objects=scene.prefab_roots()
        placement.select(objects)
        initial=[obj.matrix_world.translation.copy() for obj in objects]
        assert bpy.ops.ruster.group()=={'FINISHED'}
        group=bpy.context.object
        group.location+=Vector((10,20,30))
        bpy.context.view_layer.update()
        for obj,position in zip(objects,initial):
            assert (obj.matrix_world.translation-position-Vector((10,20,30))).length<1e-4
        assert not scene.validate()[0]
        assert bpy.ops.ruster.duplicate()=={'FINISHED'}
        assert len(scene.prefab_roots())==4
        assert len(bpy.context.object.children)==2
        assert bpy.ops.ruster.delete()=={'FINISHED'}
        assert len(scene.prefab_roots())==2
        placement.select([group])
        assembly=root/'monument.rusterprefab'
        assert bpy.ops.ruster.assembly_export(filepath=str(assembly))=={'FINISHED'}
        bpy.context.scene.cursor.location=(200,100,0)
        assert bpy.ops.ruster.assembly_import(filepath=str(assembly))=={'FINISHED'}
        assert len(scene.prefab_roots())==4
        imported=bpy.context.object
        assert (imported.matrix_world.translation-Vector((200,100,0))).length<1e-4
        assert bpy.ops.ruster.ungroup()=={'FINISHED'}
        assert all(o.parent is None for o in bpy.context.selected_objects)
        placement.select([scene.prefab_roots()[0]])
        assert bpy.ops.ruster.surface_snap()=={'FINISHED'}
        assert bpy.ops.ruster.scatter(count=10,radius=30,spacing=3,seed=1)=={'FINISHED'}
        assert len(scene.prefab_roots())==14
        assert not scene.validate()[0]
        scene.export_map(root/'result.map')
        assert len(RustMap.load(root/'result.map').prefabs)==14
        ruster.unregister()
    print('RUSTER_PLACEMENT_SMOKE_OK',flush=True)


try:run()
except Exception:
    import traceback
    traceback.print_exc();os._exit(1)
