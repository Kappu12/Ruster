"""Exercise the real Maps Image Editor workspace and layer selector."""
import os,sys,tempfile,traceback
from pathlib import Path
import bpy
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import ruster
from ruster import app,maps,editing
from tests.fixtures import sample_world
temp=tempfile.TemporaryDirectory(prefix='ruster-gui-maps-');root=Path(temp.name)
os.environ['RUSTER_USER_DIR']=str(root/'user');ruster.register();state={'stage':0}


def perform():
    stage=state['stage']
    if stage==0:
        bpy.context.window.event_simulate(type='ESC',value='PRESS')
        path=root/'base.map';world=sample_world();world.set_layer('height',world.layers['terrain']);path.write_bytes(world.write());app.open_path(path)
        assert bpy.context.workspace.get('ruster_workspace')=='3D'
    elif stage==1:
        bpy.ops.ruster.map_view(view='MAPS')
    elif 2<=stage<10:
        assert bpy.context.workspace.get('ruster_workspace')=='MAPS'
        area=next(a for a in bpy.context.screen.areas if a.type=='IMAGE_EDITOR')
        bpy.context.scene.ruster_maps.layer=maps.map_images.LAYERS[stage-2]
        with bpy.context.temp_override(area=area):
            image=maps.update_image(bpy.context)
            assert area.spaces.active.image==image
        state['area']=area
    elif stage==10:
        bpy.context.scene.ruster_maps.layer='splat';bpy.context.scene.ruster_maps.channel='2'
        with bpy.context.temp_override(area=state['area']):maps.update_image(bpy.context)
        state['before']=list(state['area'].spaces.active.image.pixels[:])
        bpy.ops.ed.undo_push(message='Before map paint')
        document=editing.terrain(fresh=True);document.brush('PAINT',0,0,400,layer='splat',channel=2,strength=1)
        editing.commit(document);bpy.ops.ed.undo_push(message='Map paint')
    elif stage==11:
        with bpy.context.temp_override(area=state['area']):image=maps.update_image(bpy.context)
        assert state['before']!=list(image.pixels[:]);bpy.ops.ed.undo()
    elif stage==12:
        area=next(a for a in bpy.context.screen.areas if a.type=='IMAGE_EDITOR')
        with bpy.context.temp_override(area=area):image=maps.update_image(bpy.context)
        assert state['before']==list(image.pixels[:]),'Map preview did not follow undo'
        bpy.ops.ruster.map_view(view='3D')
    else:
        assert bpy.context.workspace.get('ruster_workspace')=='3D' and any(a.type=='VIEW_3D' for a in bpy.context.screen.areas)
        print('RUSTER_GUI_MAP_LAYERS_UNDO_OK',flush=True);bpy.ops.wm.quit_blender();return None
    state['stage']+=1;return .5


def step():
    try:
        with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):return perform()
    except Exception:traceback.print_exc();os._exit(1)
bpy.app.timers.register(step,first_interval=2)
