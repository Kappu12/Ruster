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
        def call(rpc_kind,**params):
            result=server.execute_command({'token':server.token,'type':rpc_kind,'params':params})
            assert result['status']=='success',result
            return result['result']
        assert server.execute_command({'type':'place_prefab','params':{}})['status']=='error'
        assert server.execute_command({'token':server.token,'type':'execute_code','params':{'code':'raise Exception()'}})['status']=='error'
        assert call('search_prefabs',query='') ['prefabs'][0]['id']==123456
        assert call('search_prefabs',query='')['next_offset'] is None
        assert call('get_editor_status')['catalog_ready']
        assert call('list_prefab_categories')['total_prefabs']==1
        details=call('get_prefab_details',uid=123456)
        assert details['cached'] and details['local_bounds']['dimensions']==[2,1,2] and details['triangle_count']==1
        # The current converter stores mesh counts in JSON and coordinates in RMS1.
        from ruster.assets import geometry
        spec=asset['meshes']['mesh'];buffer=cache/'meshes/triangle.mesh.gz'
        asset['meshes']['mesh']=geometry.write(buffer,spec['vertices'],[],spec['submeshes'])
        asset['meshes']['mesh']['buffer']='meshes/triangle.mesh.gz'
        (cache/'123456.json.gz').write_bytes(gzip.compress(json.dumps(asset).encode()))
        binary_details=call('get_prefab_details',uid=123456)
        assert binary_details['local_bounds']==details['local_bounds'] and binary_details['triangle_count']==1
        assert abs(call('sample_surface',positions=[[0,0]])['samples'][0]['position'][2]-20)<.1
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
        assert all(abs(a-b)<1e-5 for a,b in zip(call('get_object_info',name=name)['world_scale'],[2,3,4]))
        count=len(scene.prefab_roots())
        failed=server.execute_command({'token':server.token,'type':'place_prefabs','params':{'placements':[{'uid':123456,'position':[0,0,20]},{'uid':99,'position':[0,0,20]}]}})
        assert failed['status']=='error' and len(scene.prefab_roots())==count,'Partial composition leaked'
        batch=call('place_prefabs',placements=[{'uid':123456,'position':[0,0,20]},{'uid':123456,'position':[3,0,20]}],group_name='Test Composition')
        group=batch['group']['name'];children=[o['name'] for o in batch['objects']]
        assert batch['group']['kind']=='GROUP' and len(batch['group']['children'])==2
        assert batch['group']['world_bounds']['dimensions'][0]>=5
        old=[bpy.data.objects[n].matrix_world.copy() for n in children]
        failed=server.execute_command({'token':server.token,'type':'transform_objects','params':{'transforms':[{'name':children[0],'position':[9,0,20]},{'name':children[1],'scale':[0,1,1]}]}})
        assert failed['status']=='error' and all(bpy.data.objects[n].matrix_world==m for n,m in zip(children,old)),'Batch transforms did not roll back'
        call('transform_objects',transforms=[{'name':group,'position':[1,1,21],'scale':[2,2,2]}])
        call('rename_object',name=group,new_name='AI Composition');group='AI Composition'
        call('snap_objects_to_terrain',names=[group],offset=2)
        assert abs(bpy.data.objects[group].matrix_world.translation.z-22)<.1
        assert call('list_map_objects',query='AI Composition',kind='GROUP')['total']==1
        assert call('list_map_objects',prefab_id=123456)['total']==3
        call('export_assembly',names=[group],path=str(root/'build.rusterprefab'))
        assert (root/'build.rusterprefab').is_file()
        imported=call('import_assembly',path=str(root/'build.rusterprefab'),position=[10,10,20],name='Imported Composition')
        assert imported['prefab_count']==2
        call('delete_object',name=imported['group']['name'])
        call('ungroup_object',name=group)
        assert not bpy.data.objects.get(group)
        regrouped=call('group_objects',names=children,name='Rebuilt')['name']
        call('delete_object',name=regrouped)
        road=call('create_path',kind='Road',nodes=[[0,0,20],[10,0,20]],settings={'width':12,'topology':0xffffffff})
        assert road['width']==12 and road['topology']==0xffffffff
        road=call('update_path',name=road['object'],nodes=[[0,0,21],[5,5,21],[10,0,21]],settings={'width':8,'topology':1})
        assert len(road['nodes'])==3 and road['topology']==1 and road['nodes'][1]==[5,5,21]
        assert call('get_path_info',name=road['object'])['width']==8
        failed=server.execute_command({'token':server.token,'type':'update_path','params':{'name':road['object'],'settings':{'width':1000}}})
        assert failed['status']=='error' and call('get_path_info',name=road['object'])['width']==8
        call('paint_terrain',layer='alpha',tool='PAINT',x=0,y=0,radius=20,strength=1.,height=0.,channel=0,invert=True)
        assert not call('sample_surface',positions=[[0,0]])['samples'][0]['has_ground']
        assert not protection.model_error(bpy.data.objects[name])
        assert not call('validate_map')['errors']
        target=root/'out.map';call('export_map',path=str(target));assert target.is_file()
        assert server.execute_command({'token':server.token,'type':'export_map','params':{'path':str(target)}})['status']=='error'
        call('save_project',path=str(root/'out.ruster'))
        assert not settings.load().get('mcp_enabled',False),'Project saving enabled MCP'
        with closing(catalog.connect(scene.cache_dir())) as db:
            db.executemany('INSERT INTO names VALUES(?,?)',[(i,f'assets/prefabs/discovery/part_{i}.prefab') for i in range(200,405)]);db.commit()
        seen=[];offset=0
        while True:
            page=call('search_prefabs',category='assets/prefabs/discovery',limit=100,offset=offset)
            seen.extend(p['id'] for p in page['prefabs'])
            if page['next_offset'] is None:break
            offset=page['next_offset']
        assert len(seen)==205 and len(set(seen))==205,'Catalog pagination omitted or repeated assets'
        assert len(call('search_prefabs',query='part_20')['prefabs'])==10
        assert len(call('search_prefabs',available_only=True)['prefabs'])==1
        previous=app.start_job
        def failed_worker(*_args,**_kwargs):raise ValueError('Test worker could not start')
        try:
            app.start_job=failed_worker
            failure=server.execute_command({'token':server.token,'type':'request_prefab_assets','params':{'uids':[123456]}})
            assert failure['status']=='error' and 'could not start' in failure['message']
            assert 123456 not in app._pending_asset_ids
            status=call('get_editor_status');assert status['queued_prefabs']==0
        finally:
            app.start_job=previous;app._pending_asset_ids.clear()
        app._visual_queue.append(name)
        try:assert call('get_editor_status')['busy'] and call('get_editor_status')['pending_visuals']>0
        finally:app._visual_queue.clear()
        ruster.unregister()
    print('RUSTER_BLENDER_MCP_TYPED_COMMANDS_OK',flush=True)


try:run()
except Exception:traceback.print_exc();os._exit(1)
