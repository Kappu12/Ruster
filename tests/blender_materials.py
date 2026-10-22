"""Packed source masks, emission and transparency survive the linked preview."""
import gzip,json,os,sys,tempfile,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
if '--' in sys.argv:sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import bpy,ruster
from ruster import scene,protection
from ruster.core import wire
from tests.fixtures import triangle_asset


def run():
    with tempfile.TemporaryDirectory(prefix='ruster-materials-') as directory:
        os.environ['RUSTER_USER_DIR']=directory
        ruster.register()
        cache=scene.cache_dir()/'prefabs';(cache/'textures').mkdir(parents=True)
        image=bpy.data.images.new('Packed mask fixture',2,2)
        image.pixels[:]=[.1,.2,.3,.4]*4
        image.filepath_raw=str(cache/'textures/test.png');image.file_format='PNG';image.save()
        bpy.data.images.remove(image)
        asset=triangle_asset(42)
        from ruster.assets import geometry
        source_mesh=asset['meshes']['mesh']
        mesh_path=cache/'meshes/fixture.mesh.gz'
        asset['meshes']['mesh']=geometry.write(mesh_path,source_mesh['vertices'],[[0,0],[1,0],[0,1]],source_mesh['submeshes'])
        asset['meshes']['mesh']['buffer']='meshes/fixture.mesh.gz'
        asset['materials']['mat'].update(texture='textures/test.png',metallic_gloss_texture='textures/test.png',
            emission=[0,1.0353,1.498,1],alpha_blend=True,color=[0,.97,1,.75],gloss_map_scale=.7)
        (cache/'42.json.gz').write_bytes(gzip.compress(json.dumps(asset).encode()))
        root=scene.root_object([wire.encode(2,0,42)],bpy.context.scene.collection)
        assert scene.attach_visual(root) and not protection.model_error(root)
        mesh=root.instance_collection.objects[0].data
        assert len(mesh.vertices)==3 and len(mesh.polygons)==1 and len(mesh.uv_layers)==1
        assert tuple(mesh.polygons[0].vertices)==(2,1,0)
        assert tuple(mesh.vertices[2].co)==(0,1,2)
        assert tuple(mesh.uv_layers[0].data[0].uv)==(0,1)
        mat=root.instance_collection.objects[0].material_slots[0].material
        bsdf=mat.node_tree.nodes.get('Principled BSDF')
        assert bsdf.inputs['Emission Strength'].default_value==1
        assert abs(bsdf.inputs['Emission Color'].default_value[2]-1.498)<.0001
        assert bsdf.inputs['Metallic'].is_linked and bsdf.inputs['Roughness'].is_linked
        assert bsdf.inputs['Alpha'].is_linked
        textures={node.label:node for node in mat.node_tree.nodes if node.type=='TEX_IMAGE'}
        assert textures['texture'].image.colorspace_settings.name=='sRGB'
        assert textures['metallic_gloss_texture'].image.colorspace_settings.name=='Non-Color'
        assert all(node.image.packed_file for node in textures.values())
        assert mat.node_tree.nodes.active==textures['texture'],'Solid preview selected a mask instead of the base texture'
        assert mat.surface_render_method=='DITHERED'
        ruster.unregister()
    print('RUSTER_LINKED_SOURCE_MATERIALS_OK',flush=True)


try:run()
except Exception:traceback.print_exc();os._exit(1)
