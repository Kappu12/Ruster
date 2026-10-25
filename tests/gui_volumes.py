"""Draw and select collider volumes in the native viewport."""
import os,sys,tempfile,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import bpy,ruster
from mathutils import Quaternion,Vector
from bpy_extras.view3d_utils import location_3d_to_region_2d
from ruster import studio,scene,volumes
from ruster.core import wire
from tests.blender_volumes import asset
temporary=tempfile.TemporaryDirectory()
os.environ['RUSTER_USER_DIR']=temporary.name
draws=[]
original=volumes.RUSTER_GT_volume.draw
def checked(self,context):
    try:original(self,context);draws.append(self.root.name)
    except Exception:traceback.print_exc();os._exit(1)
volumes.RUSTER_GT_volume.draw=checked
ruster.register()
stage=0


def tick():
    global stage
    try:
        window=bpy.context.window
        area=next(a for a in window.screen.areas if a.type=='VIEW_3D')
        region=next(r for r in area.regions if r.type=='WINDOW')
        with bpy.context.temp_override(window=window,area=area,region=region):
            if stage==0:
                window.event_simulate(type='ESC',value='PRESS')
                studio.new_prefab()
                for uid,kind in enumerate(('SphereCollider','BoxCollider','CapsuleCollider'),1):
                    data=asset(uid,kind);data['colliders'][0]['center']=[0,0,0]
                    root=scene.root_object([wire.encode(2,0,uid)],bpy.context.scene.collection)
                    volumes.attach(root,data,Path(temporary.name))
                    root.location=((uid-2)*7,0,0)
                area.spaces.active.region_3d.view_rotation=Quaternion((1,0,0,0))
                area.spaces.active.region_3d.view_location=(0,0,0)
                area.spaces.active.region_3d.view_distance=30
                area.spaces.active.region_3d.view_perspective='ORTHO'
                area.spaces.active.show_region_ui=False
            elif stage==2:
                assert len(set(draws))==3,draws
                bpy.ops.screen.screenshot(filepath=str(ROOT/'build/volume-preview-before.png'))
                point=location_3d_to_region_2d(region,area.spaces.active.region_3d,Vector((-7,0,0)))
                window.event_simulate(type='MOUSEMOVE',value='NOTHING',x=region.x+int(point.x),y=region.y+int(point.y))
            elif stage==3:
                point=location_3d_to_region_2d(region,area.spaces.active.region_3d,Vector((-7,0,0)))
                for value in ('PRESS','RELEASE'):
                    window.event_simulate(type='LEFTMOUSE',value=value,x=region.x+int(point.x),y=region.y+int(point.y))
            elif stage==4:
                assert bpy.context.object and bpy.context.object['ruster_uid']=='1','Volume surface was not selectable'
                bpy.ops.screen.screenshot(filepath=str(ROOT/'build/volume-preview.png'))
                bpy.context.scene.ruster_show_volumes=False;draws.clear()
            elif stage==6:
                assert not draws,'Hidden volumes still drew'
                bpy.context.scene.ruster_show_volumes=True
            elif stage==8:
                assert draws,'Volumes did not return after toggling'
                print('RUSTER_GUI_VOLUMES_OK',flush=True)
                os._exit(0)
        stage+=1;return .5
    except Exception:traceback.print_exc();os._exit(1)
bpy.app.timers.register(tick,first_interval=1.)
