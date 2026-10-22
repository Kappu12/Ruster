"""Blender's own event simulation exercises a real viewport brush stroke.

Run in a graphical session with --enable-event-simulate. No OS input automation.
"""
import os
from pathlib import Path
import sys
import traceback
import numpy as np
import bpy
from bpy_extras import view3d_utils
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import ruster
from ruster import app,scene,editing,ui
from ruster.core.terrain import empty_world
os.environ['RUSTER_USER_DIR']='/tmp/ruster-gui-test-profile'
state={}
ruster.register()


def perform_step():
    try:
        stage=state.get('stage',0)
        if stage==0:
            bpy.context.window.event_simulate(type='ESC',value='PRESS')
            path=Path('/tmp/ruster-interaction.map');path.write_bytes(empty_world(1000,20).write())
            app.open_path(path)
            state['stage']=1
            return 1.
        elif stage==1:
            area=next(a for a in bpy.context.window.screen.areas if a.type=='VIEW_3D')
            region=next(r for r in area.regions if r.type=='WINDOW')
            state.update(area=area,region=region,window=bpy.context.window)
            with bpy.context.temp_override(area=area,region=region):
                bpy.ops.wm.tool_set_by_id(name='ruster.terrain_brush')
            bpy.context.scene.ruster_brush.radius=80
            bpy.context.scene.ruster_brush.strength=1
            state['before']=editing.terrain().raw('terrain')
        elif stage==2:
            area,region=state['area'],state['region']
            point=view3d_utils.location_3d_to_region_2d(region,area.spaces.active.region_3d,Vector((0,0,20)))
            assert point is not None
            state['x'],state['y']=round(region.x+point.x),round(region.y+point.y)
            state['window'].event_simulate(type='MOUSEMOVE',value='NOTHING',x=state['x'],y=state['y'])
        elif stage==3:
            state['window'].event_simulate(type='LEFTMOUSE',value='PRESS',x=state['x'],y=state['y'])
        elif stage==4:
            state['window'].event_simulate(type='MOUSEMOVE',value='NOTHING',x=state['x']+30,y=state['y'])
        elif stage==5:
            state['window'].event_simulate(type='LEFTMOUSE',value='RELEASE',x=state['x']+30,y=state['y'])
        elif stage==6:
            assert bpy.context.window.workspace.name=='Rust Map'
            assert bpy.context.scene.ruster.terrain_state is not None,'Viewport brush did not commit a stroke'
            assert editing.terrain().raw('terrain')!=state['before']
            state['after']=editing.terrain().raw('terrain')
            with bpy.context.temp_override(area=state['area'],region=state['region']):
                assert bpy.ops.ed.undo()=={'FINISHED'}
        elif stage==7:
            assert bpy.context.scene.ruster.mode=='MAP','Undo crossed the map import instead of undoing the stroke'
            assert editing.terrain().raw('terrain')==state['before'],'Undo did not restore the stroke baseline'
            with bpy.context.temp_override(area=state['area'],region=state['region']):
                assert bpy.ops.ed.redo()=={'FINISHED'}
        elif stage==8:
            assert editing.terrain().raw('terrain')==state['after']
            state['window'].event_simulate(type='LEFTMOUSE',value='PRESS',x=state['x'],y=state['y'])
        elif stage==9:
            assert editing.stroke_active
            state['window'].event_simulate(type='MOUSEMOVE',value='NOTHING',x=state['x']-30,y=state['y'])
        elif stage==10:
            state['window'].event_simulate(type='ESC',value='PRESS')
        elif stage==11:
            state['window'].event_simulate(type='LEFTMOUSE',value='RELEASE',x=state['x']-30,y=state['y'])
        elif stage==12:
            assert not editing.stroke_active
            assert editing.terrain().raw('terrain')==state['after'],'Cancelling a stroke changed committed terrain'
            obj=next(o for o in bpy.context.scene.objects if o.get('ruster_kind')=='TERRAIN')
            positions=np.empty(len(obj.data.vertices)*3,dtype=np.float32)
            obj.data.vertices.foreach_get('co',positions)
            positions=positions.reshape(-1,3)
            assert np.allclose(positions[:,2],editing.terrain().sample_height(positions[:,0],positions[:,1]),atol=.001)
            print('RUSTER_GUI_STROKE_UNDO_REDO_CANCEL_OK',flush=True)
            bpy.ops.wm.quit_blender();return None
        state['stage']=stage+1
        return 1.
    except Exception:
        traceback.print_exc();os._exit(1)


def step():
    windows=list(bpy.context.window_manager.windows)
    if not windows:
        print('No Blender window is available',flush=True);os._exit(1)
    with bpy.context.temp_override(window=windows[0]):
        return perform_step()


bpy.app.timers.register(step,first_interval=2.)
