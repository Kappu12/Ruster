"""Long thin original IO pieces preserve exact records and permit normal edits."""
import os,sys,tempfile,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
if '--' in sys.argv:sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import bpy,ruster
from mathutils import Vector
from ruster import scene,studio,placement
from ruster.core import wire
from ruster.core.rust_map import prefab_transform

def run():
    with tempfile.TemporaryDirectory() as folder:
        os.environ['RUSTER_USER_DIR']=folder;ruster.register();studio.new_prefab()
        original=[wire.encode(2,0,147092032),wire.encode(3,2,wire.set_vector(None,(12,3,5))),
                  wire.encode(4,2,wire.set_vector(None,(0,23.3,17.2))),
                  wire.encode(5,2,wire.set_vector(None,(772.099,1,.821408))),
                  wire.encode(77,2,b'preserve hidden IO extension')]
        root=scene.root_object(original,bpy.context.scene.collection);bpy.context.view_layer.update()
        result=studio.prefab_records([root],Vector((0,0,0)))
        assert wire.serialize(result[0])==wire.serialize(original)
        root.location.x+=1;bpy.context.view_layer.update()
        result=studio.prefab_records([root],Vector((0,0,0)))
        assert abs(prefab_transform(result[0])[0][0]-13)<.001
        assert wire.get(result[0],77)==b'preserve hidden IO extension'
        group=placement.group([root]);group.scale=(2,1,1);root.rotation_euler.z+=.5;bpy.context.view_layer.update()
        try:studio.prefab_records([root],Vector((0,0,0)))
        except ValueError as error:assert 'shear' in str(error)
        else:raise AssertionError('A genuinely sheared placement was exported')
        ruster.unregister()
    print('RUSTER_LONG_IO_TRANSFORMS_OK',flush=True)

try:run()
except Exception:traceback.print_exc();os._exit(1)
