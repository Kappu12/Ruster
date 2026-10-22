"""Native map workspaces and generated image pixels, without game files."""
import os,sys,tempfile,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
if '--' in sys.argv and sys.argv[sys.argv.index('--')+1:]:sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import bpy
import ruster
from ruster import app,maps,editing
from tests.fixtures import sample_world


def run():
    with tempfile.TemporaryDirectory(prefix='ruster-maps-') as temp:
        root=Path(temp);os.environ['RUSTER_USER_DIR']=str(root/'user');ruster.register()
        source=root/'base.map';world=sample_world();world.set_layer('height',world.layers['terrain']);source.write_bytes(world.write());app.open_path(source)
        assert bpy.context.window.workspace.get('ruster_workspace')=='3D'
        assert any(a.type=='VIEW_3D' for a in bpy.context.window.screen.areas)
        workspace=next(w for w in bpy.data.workspaces if w.get('ruster_workspace')=='MAPS')
        assert workspace.screens
        state=bpy.context.scene.ruster_maps
        before=editing.terrain().snapshot()
        for layer in maps.map_images.LAYERS:
            state.layer=layer;image=maps.update_image(bpy.context)
            assert image.size[0]>=32 and image.get('ruster_map_preview')
        assert before==editing.terrain().snapshot()
        state.layer='splat';state.channel='2';image=maps.update_image(bpy.context)
        old=list(image.pixels[:])
        document=editing.terrain(fresh=True);document.brush('PAINT',0,0,400,layer='splat',channel=2,strength=1)
        editing.commit(document);image=maps.update_image(bpy.context)
        assert old!=list(image.pixels[:]),'2D map view stayed stale after an edit'
        app.save_project(root/'view.ruster');app.open_path(root/'view.ruster')
        assert any(w.get('ruster_workspace')=='MAPS' for w in bpy.data.workspaces)
        maps.update_image(bpy.context)
        ruster.unregister()
    print('RUSTER_MAP_WORKSPACE_IMAGES_OK',flush=True)


try:run()
except Exception:traceback.print_exc();os._exit(1)
