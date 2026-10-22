"""Typed MCP commands run against real Blender data; no game install needed."""
import gzip,json,os,sys,tempfile,traceback
from pathlib import Path
from contextlib import closing
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
if '--' in sys.argv and sys.argv[sys.argv.index('--')+1:]:sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import bpy
import ruster
from ruster import app,scene,editing,placement,protection,mcp_bridge
from ruster.core import settings
from ruster.core.terrain import empty_world
from ruster.assets import catalog
from tests.fixtures import triangle_asset


def run():
    with tempfile.TemporaryDirectory(prefix='ruster-mcp-') as temp:
        root=Path(temp);os.environ['RUSTER_USER_DIR']=str(root/'user')
        ruster.register()
        assert not mcp_bridge.running() and not bpy.context.window_manager.ruster_mcp.enabled
        source=root/'base.map';source.write_bytes(empty_world(100,20).write())
        bpy.context.preferences.edit.use_global_undo=True
        app.open_path(source)
        cache=scene.cache_dir()/'prefabs';cache.mkdir(parents=True,exist_ok=True)
        asset=triangle_asset(123456);path=asset['path']
        with closing(catalog.connect(scene.cache_dir())) as db:
            db.execute('INSERT OR REPLACE INTO names VALUES(?,?)',(123456,path))
            db.execute('INSERT OR REPLACE INTO assets VALUES(?,?,?,?)',(path,'bundle','file',123456));db.commit()
        (cache/'123456.json.gz').write_bytes(gzip.compress(json.dumps(asset).encode()))
        server=mcp_bridge.RusterMCPServer(9877,'test-token-123456789012345678901234567890')
        def call(kind,**params):
            result=server.execute_command({'token':server.token,'type':kind,'params':params})
            assert result['status']=='success',result
            return result['result']
        assert server.execute_command({'type':'place_prefab','params':{}})['status']=='error'
        assert server.execute_command({'token':server.token,'type':'execute_code','params':{'code':'raise Exception()'}})['status']=='error'
        assert call('search_prefabs',query='') ['prefabs'][0]['id']==123456
        placed=call('place_prefab',uid=123456,position=[1,2,25],rotation_degrees=[0,0,45],scale=[2,2,2]);name=placed['name']
        assert placed['geometry_read_only'] and abs(placed['rotation_degrees'][2]-45)<.001
        assert not protection.model_error(bpy.data.objects[name])
        call('undo');assert len(scene.prefab_roots())==0
        call('redo');assert len(scene.prefab_roots())==1
        call('transform_object',name=name,position=[10,20,30],rotation_degrees=[0,0,90],scale=[2,3,4])
        assert tuple(round(v,3) for v in bpy.data.objects[name].location)==(10,20,30)
        before=bpy.data.objects[name].matrix_world.copy()
        failed=server.execute_command({'token':server.token,'type':'transform_object','params':{'name':name,'scale':[0,1,1]}})
        assert failed['status']=='error' and bpy.data.objects[name].matrix_world==before
        failed=server.execute_command({'token':server.token,'type':'transform_object','params':{'name':name,'position':[1e300,0,0]}})
        assert failed['status']=='error' and bpy.data.objects[name].matrix_world==before
        terrain=next(o for o in bpy.context.scene.objects if o.get('ruster_kind')=='TERRAIN')
        assert server.execute_command({'token':server.token,'type':'transform_object','params':{'name':terrain.name,'scale':[1,2,1]}})['status']=='error'
        assert call('get_object_info',name=name)['world_scale']==[2,3,4]
        call('paint_terrain',layer='alpha',tool='PAINT',x=0,y=0,radius=20,strength=1.,height=0.,channel=0,invert=True)
        assert not protection.model_error(bpy.data.objects[name])
        assert not call('validate_map')['errors']
        target=root/'out.map';call('export_map',path=str(target));assert target.is_file()
        assert server.execute_command({'token':server.token,'type':'export_map','params':{'path':str(target)}})['status']=='error'
        call('save_project',path=str(root/'out.ruster'))
        assert not settings.load().get('mcp_enabled',False),'Project saving enabled MCP'
        ruster.unregister()
    print('RUSTER_BLENDER_MCP_TYPED_COMMANDS_OK',flush=True)


try:run()
except Exception:traceback.print_exc();os._exit(1)
