"""Real Blender terrain/path persistence and undo regression suite."""
import os
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
if '--' in sys.argv and sys.argv[sys.argv.index('--')+1:]:
    staged=Path(sys.argv[sys.argv.index('--')+1])
    sys.path.insert(0,str(staged))
    sys.path.insert(0,str(staged/'python_modules'))
if os.environ.get('RUSTER_PYTHON_MODULES'):
    sys.path.insert(0,os.environ['RUSTER_PYTHON_MODULES'])
import bpy
from mathutils import Vector
import ruster
from ruster import app,scene,editing
from ruster.core.rust_map import RustMap
from ruster.core.terrain import Terrain,empty_world
from ruster.core import paths,wire


def run():
    with tempfile.TemporaryDirectory(prefix='ruster-editing-') as temp:
        root=Path(temp)
        os.environ['RUSTER_USER_DIR']=str(root/'settings')
        ruster.register()
        source=root/'base.map';source.write_bytes(empty_world(100,20).write())
        scene.import_map(source)
        state=bpy.context.scene.ruster
        brush=bpy.context.scene.ruster_brush
        before=editing.terrain().raw('terrain')
        assert not state.terrain_state
        brush.radius=15;brush.strength=1.;brush.tool='RAISE'
        assert bpy.ops.ruster.terrain_apply()=={'FINISHED'}
        assert state.terrain_state and editing.terrain().raw('terrain')!=before
        brush.layer='biome';brush.biome='4'
        assert bpy.ops.ruster.terrain_apply()=={'FINISHED'}
        brush.layer='topology';brush.topology='11'
        assert bpy.ops.ruster.terrain_apply()=={'FINISHED'}
        brush.layer='alpha';brush.remove=True
        assert bpy.ops.ruster.terrain_apply()=={'FINISHED'}
        terrain_obj=next(o for o in bpy.context.scene.objects if o.get('ruster_kind')=='TERRAIN')
        assert len(terrain_obj.data.polygons)<64*64
        brush.remove=False
        assert bpy.ops.ruster.terrain_apply()=={'FINISHED'}
        brush.layer='water';brush.tool='FLATTEN';brush.height=50
        assert bpy.ops.ruster.terrain_apply()=={'FINISHED'}
        assert any(o.get('ruster_kind')=='WATER' and len(o.data.polygons)>0 for o in bpy.context.scene.objects)
        assert bpy.ops.ruster.path_add(kind='Road')=={'FINISHED'}
        path=bpy.context.object
        path.ruster_path.width=12
        path.location.y=8
        bpy.context.view_layer.update()
        assert bpy.ops.ruster.path_snap()=={'FINISHED'}
        assert bpy.ops.ruster.path_grade()=={'FINISHED'}
        expected=editing.terrain().export_world().layers
        map_path=root/'edited.map';scene.export_map(map_path)
        exported=RustMap.load(map_path)
        for name,data in expected.items():assert exported.layers[name]==data,name
        assert len(exported.paths)==1
        record=paths.read(exported.paths[0])
        assert record['width']==12 and all(abs(n[2]-8)<1e-4 for n in record['nodes'])
        target=root/'edited.ruster'
        assert bpy.ops.ruster.save(filepath=str(target))=={'FINISHED'}
        source.unlink()
        app.open_path(target)
        assert bpy.context.scene.ruster.terrain_state
        for name,data in expected.items():assert editing.terrain().export_world().layers[name]==data
        scene.export_map(root/'reopened.map')
        assert RustMap.load(root/'reopened.map').layers==expected
        # Native Blender global undo must restore the authoritative terrain pointer.
        bpy.context.preferences.edit.use_global_undo=True
        bpy.ops.ed.undo_push(message='Terrain before stroke')
        baseline=editing.terrain().raw('terrain')
        brush=bpy.context.scene.ruster_brush;brush.layer='terrain';brush.tool='RAISE'
        brush.strength=1;brush.radius=15
        bpy.ops.ruster.terrain_apply()
        bpy.ops.ed.undo_push(message='Terrain after stroke')
        changed=editing.terrain().raw('terrain')
        assert changed!=baseline
        assert bpy.ops.ed.undo()=={'FINISHED'}
        assert editing.terrain().raw('terrain')==baseline,'Terrain data did not undo with Blender'
        assert bpy.ops.ed.redo()=={'FINISHED'}
        assert editing.terrain().raw('terrain')==changed,'Terrain data did not redo with Blender'
        # A recovery save must never replace the user's normal save destination.
        normal=bpy.context.scene.ruster.project_path
        recovery=root/'recovery.ruster'
        app.save_project(recovery,update_path=False)
        assert bpy.context.scene.ruster.project_path==normal and recovery.is_file()
        # Height image import must preserve unsigned 16-bit range and resolution.
        import numpy as np
        image_path=root/'height.raw'
        samples=np.full((65,65),40000,dtype='<u2');samples.tofile(image_path)
        assert bpy.ops.ruster.height_import(filepath=str(image_path))=={'FINISHED'}
        assert np.all(editing.terrain().grid('terrain')==round(40000/65535*32766))
        try:
            from PIL import Image
        except ImportError:
            if '--' in sys.argv:raise  # Packaged builds must include Pillow.
        else:
            png=root/'height.png'
            assert bpy.ops.ruster.height_export(filepath=str(png))=={'FINISHED'}
            with Image.open(png) as image:
                values=np.asarray(image)
            assert values.shape==(65,65) and values.min()>255
            expected_height=editing.terrain().raw('terrain')
            assert bpy.ops.ruster.height_import(filepath=str(png))=={'FINISHED'}
            assert editing.terrain().raw('terrain')==expected_height
            # Layer masks use authoritative full-resolution data and native undo.
            from ruster.core import layer_images
            mask=root/'topology-mask.png'
            Image.fromarray(np.array([[0,255],[255,0]],dtype='u1')).save(mask)
            baseline={key:editing.terrain().raw(key) for key in editing.terrain().base_layers}
            bpy.ops.ed.undo_push(message='Before mask import')
            assert bpy.ops.ruster.mask_import(filepath=str(mask),layer='topology',channel='11')=={'FINISHED'}
            changed=editing.terrain().raw('topology')
            assert changed!=baseline['topology']
            for key,value in baseline.items():
                if key!='topology':assert editing.terrain().raw(key)==value
            bpy.ops.ed.undo_push(message='After mask import')
            assert bpy.ops.ed.undo()=={'FINISHED'}
            assert editing.terrain().raw('topology')==baseline['topology']
            assert bpy.ops.ed.redo()=={'FINISHED'}
            assert editing.terrain().raw('topology')==changed
            exported_mask=root/'exported-mask.png'
            assert bpy.ops.ruster.mask_export(filepath=str(exported_mask),layer='topology',channel='11')=={'FINISHED'}
            assert np.array_equal(layer_images.read_image(exported_mask),layer_images.image_array(editing.terrain(),'topology',11))
            snapshot=bpy.context.scene.ruster.terrain_state
            assert bpy.ops.ruster.mask_import(filepath=str(exported_mask),layer='topology',channel='11')=={'FINISHED'}
            assert bpy.context.scene.ruster.terrain_state==snapshot,'No-op mask import created a redundant snapshot'
            Image.fromarray(np.full((2,2),100,dtype='u1')).save(mask)
            assert bpy.ops.ruster.mask_import(filepath=str(mask),layer='biome',channel='4')=={'FINISHED'}
            assert np.all(editing.terrain().grid('biome')[4]==100)
            assert np.all(editing.terrain().grid('biome').sum(axis=0)==255)
            Image.fromarray(np.array([[0,255],[255,255]],dtype='u1')).save(mask)
            faces_before=len(next(o for o in bpy.context.scene.objects if o.get('ruster_kind')=='TERRAIN').data.polygons)
            assert bpy.ops.ruster.mask_import(filepath=str(mask),layer='alpha')=={'FINISHED'}
            assert len(next(o for o in bpy.context.scene.objects if o.get('ruster_kind')=='TERRAIN').data.polygons)<faces_before
            expected=editing.terrain().export_world().layers
            bundle=root/'masks.ruster'
            assert bpy.ops.ruster.save(filepath=str(bundle))=={'FINISHED'}
            app.open_path(bundle)
            scene.export_map(root/'masks.map')
            assert RustMap.load(root/'masks.map').layers==expected
        ruster.unregister()
    print('RUSTER_EDITING_SMOKE_OK',flush=True)


try:
    run()
except Exception:
    import traceback
    traceback.print_exc();os._exit(1)
