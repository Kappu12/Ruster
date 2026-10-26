"""External MCP SDK client used by the native GUI integration test."""
import asyncio,base64,json,os,site,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
APP_ROOT=Path(os.environ.get('RUSTER_MCP_APP_ROOT',ROOT)).resolve()
sys.path.insert(0,str(APP_ROOT))
modules=APP_ROOT/'python_modules'
if modules.is_dir():
    sys.path.insert(0,str(modules));site.addsitedir(str(modules))
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from ruster.core import settings,mcp_config
from ruster import __version__
from ruster.assets import CONVERTER_VERSION
from ruster.vendor.blender_mcp_client import BlenderConnection


async def run():
    directory=Path(os.environ['RUSTER_MCP_TEST_STATE'])
    config=settings.load();port=mcp_config.port(config);token=config['mcp_token']
    params=StdioServerParameters(command=sys.executable,args=[str(APP_ROOT/'mcp_server.py')],env={'RUSTER_USER_DIR':str(settings.user_root()),'PYTHONIOENCODING':'utf-8'})
    async with stdio_client(params) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            async def call(rpc_tool_name,**args):
                result=await session.call_tool(rpc_tool_name,args)
                assert not result.isError,result
                return result.structuredContent or json.loads(result.content[0].text)
            exposed={tool.name for tool in (await session.list_tools()).tools}
            assert len(exposed)==61,sorted(exposed)
            assert not {'paint_terrain','sample_surface','snap_objects_to_terrain','generate_map','get_generation_status','cancel_generation','create_path','update_path','get_path_info','execute_code'} & exposed
            assert {'get_objects_info','get_prefabs_details','get_selection','array_objects','align_objects','export_models','import_map_prefabs','get_io_settings','set_io_settings'}<=exposed
            assert (await call('get_scene_info'))['mode']=='PREFAB'
            assert (await call('get_blender_context'))['geometry_read_only']
            state=await call('get_viewport_state')
            updated=await call('set_viewport_state',settings={'projection':'ORTHO','distance':20.,'show_overlays':False})
            assert updated['projection']=='ORTHO' and updated['distance']==20.
            await call('set_viewport_state',settings=state)
            await call('set_cursor',position=[2,3,4],rotation_degrees=[0,0,45])
            assert (await call('get_blender_context'))['cursor']['position']==[2,3,4]
            await call('set_cursor',position=[0,0,0])
            assert (await call('search_prefabs',query=''))['prefabs'][0]['id']==123456
            status=await call('get_editor_status')
            assert status['catalog_ready'] and status['version']==__version__ and status['converter_version']==CONVERTER_VERSION
            assert isinstance(status['restart_required'],bool) and status['visible_prefabs']==0 and status['unloaded_prefabs']==0
            assert (await call('list_prefab_categories'))['total_prefabs']==1
            assert (await call('get_prefab_details',uid=123456))['cached']
            obj=await call('place_prefab',uid=123456,position=[1,2,25])
            for _ in range(600):
                if not (await call('get_editor_status'))['busy']:break
                await asyncio.sleep(.1)
            else:raise AssertionError('Placed model preview did not finish loading')
            name=obj['name'];assert obj['geometry_read_only']
            ring=await call('radial_array_objects',names=[name],count=3,center=[0,0,25],angle_degrees=90)
            await call('distribute_objects',names=ring['objects'],spacing=3,axis='X',mode='BOUNDS_GAP')
            assert (await call('measure_objects',first=ring['objects'][0],second=ring['objects'][1]))['bounds_distance']>=2.99
            await call('transform_objects_relative',names=ring['objects'],offset=[0,0,2])
            await call('snap_objects_to_grid',names=ring['objects'],step=1)
            await call('delete_objects',names=ring['objects'])
            await call('select_objects',names=[name])
            assert (await call('get_selection'))['total']==1
            assert len((await call('get_objects_info',names=[name]))['objects'])==1
            assert len((await call('get_prefabs_details',uids=[123456]))['prefabs'])==1
            copies=await call('array_objects',names=[name],count=2,offset=[4,0,0])
            assert copies['new_prefab_count']==2
            await call('align_objects',names=copies['objects'],axis='Z',mode='MIN',target=0)
            await call('delete_objects',names=copies['objects'])
            assert (await call('get_selection'))['total']==1
            assert (await call('list_objects'))['total']==1
            assert 'GLB' in {item['id'] for item in (await call('get_export_formats'))['formats']}
            await call('export_models',names=[name],path=str(directory/'stdio.glb'),format='GLB')
            await call('export_prefab',names=[name],path=str(directory/'stdio.prefab'))
            await call('transform_object',name=name,position=[10,20,30],rotation_degrees=[0,0,90],scale=[2,2,2])
            assert (await call('get_object_info',name=name))['position']==[10,20,30]
            await call('undo')
            assert (await call('get_object_info',name=name))['position']==[1,2,25]
            await call('redo')
            assert (await call('get_object_info',name=name))['position']==[10,20,30]
            composition=await call('place_prefabs',placements=[{'uid':123456,'position':[0,0,20]},{'uid':123456,'position':[3,0,20]}],group_name='SDK composition')
            group=composition['group']['name']
            await call('transform_objects',transforms=[{'name':group,'position':[0,0,22],'scale':[2,2,2]}])
            await call('focus_view',names=[group],axis='TOP')
            await call('focus_view',names=[group],axis='OBLIQUE')
            await call('focus_view',names=[group],rotation_degrees=[65,0,35])
            image=await session.call_tool('get_viewport_image',{})
            assert not image.isError and any(c.type=='image' and c.mimeType=='image/png' for c in image.content),image
            image_data=base64.b64decode(next(c.data for c in image.content if c.type=='image'))
            assert image_data[:8]==b'\x89PNG\r\n\x1a\n' and struct.unpack('>II',image_data[16:24])==(1280,720)
            (directory/'viewport.png').write_bytes(image_data)
            with_guides=await session.call_tool('get_viewport_image',{'include_overlays':True})
            assert not with_guides.isError and any(c.type=='image' for c in with_guides.content)
            await call('export_assembly',names=[group],path=str(directory/'composition.rusterprefab'))
            imported=await call('import_assembly',path=str(directory/'composition.rusterprefab'),position=[5,5,20],name='Imported SDK composition')
            assert imported['prefab_count']==2
            await call('delete_object',name=imported['group']['name'])
            await call('delete_object',name=group)
            await call('snap_objects_to_plane',names=[name],target=0)
            assert abs((await call('get_object_info',name=name))['world_bounds']['min'][2])<.001
            duplicate=(await call('duplicate_object',name=name))['objects'][0]['name']
            await call('delete_object',name=duplicate)
            assert (await call('validate_map'))['valid']
            await call('save_project',path=str(directory/'ai.ruster'))
            await call('export_map',path=str(directory/'ai.map'))
            from ruster.core.rust_map import RustMap
            exported=RustMap.load(directory/'ai.map')
            assert len(exported.prefabs)==1 and not exported.paths and not exported.layers
            for output in ('stdio.glb','stdio.prefab','ai.ruster','ai.map'):
                assert (directory/output).stat().st_size>0
            assert Path((await call('get_project_status'))['path']).samefile(directory/'ai.ruster')
            assert Path((await call('list_recent_projects'))['projects'][0]['path']).samefile(directory/'ai.ruster')
            assert not (await call('get_live_preview_status',log_lines=0))['active']
            assert (await call('new_project'))['prefab_count']==0
            assert (await call('open_project',path=str(directory/'ai.ruster')))['prefab_count']==1
            assert (await call('get_object_info',name=name))['name']==name
            assert Path((await call('get_editor_status'))['project']['path']).samefile(directory/'ai.ruster')
            for test_token,kind,values,expected_error in [('wrong-token','get_scene_info',{},'authentication failed'),(token,'execute_code',{'code':'raise Exception("must not execute")'},'Unsupported')]:
                client=BlenderConnection('127.0.0.1',port,test_token)
                try:
                    try:client.send_command(kind,values)
                    except Exception as error:assert expected_error in str(error),str(error)
                    else:raise AssertionError('Unsafe/unauthenticated command succeeded')
                finally:client.disconnect()
            (directory/'ready.json').write_text(json.dumps({'object':name}))
            for _ in range(300):
                if (directory/'disabled').exists():break
                await asyncio.sleep(.1)
            else:raise AssertionError('GUI did not disable MCP')
            result=await session.call_tool('get_scene_info',{})
            assert result.isError and 'Enable MCP' in result.content[0].text
            client=BlenderConnection('127.0.0.1',port,token)
            try:assert not client.connect(),'Disabled MCP still accepts connections'
            finally:client.disconnect()
    print('RUSTER_MCP_STDIO_ROUNDTRIP_OK',flush=True)


asyncio.run(run())
