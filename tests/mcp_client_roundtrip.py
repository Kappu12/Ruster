"""External MCP SDK client used by the native GUI integration test."""
import asyncio,base64,json,os,struct,sys
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from ruster.core import settings,mcp_config
from ruster.vendor.blender_mcp_client import BlenderConnection


async def run():
    directory=Path(os.environ['RUSTER_MCP_TEST_STATE'])
    config=settings.load();port=mcp_config.port(config);token=config['mcp_token']
    params=StdioServerParameters(command=sys.executable,args=[str(ROOT/'mcp_server.py')],env={'RUSTER_USER_DIR':str(settings.user_root())})
    async with stdio_client(params) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            async def call(rpc_tool_name,**args):
                result=await session.call_tool(rpc_tool_name,args)
                assert not result.isError,result
                return result.structuredContent or json.loads(result.content[0].text)
            assert (await call('get_scene_info'))['mode']=='MAP'
            assert (await call('search_prefabs',query=''))['prefabs'][0]['id']==123456
            assert (await call('get_editor_status'))['catalog_ready']
            assert (await call('list_prefab_categories'))['total_prefabs']==1
            assert (await call('get_prefab_details',uid=123456))['cached']
            obj=await call('place_prefab',uid=123456,position=[1,2,25])
            name=obj['name'];assert obj['geometry_read_only']
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
            image=await session.call_tool('get_viewport_image',{})
            assert not image.isError and any(c.type=='image' and c.mimeType=='image/png' for c in image.content),image
            image_data=base64.b64decode(next(c.data for c in image.content if c.type=='image'))
            assert image_data[:8]==b'\x89PNG\r\n\x1a\n' and struct.unpack('>II',image_data[16:24])==(1280,720)
            (directory/'viewport.png').write_bytes(image_data)
            await call('export_assembly',names=[group],path=str(directory/'composition.rusterprefab'))
            imported=await call('import_assembly',path=str(directory/'composition.rusterprefab'),position=[5,5,20],name='Imported SDK composition')
            assert imported['prefab_count']==2
            await call('delete_object',name=imported['group']['name'])
            await call('delete_object',name=group)
            surface=await call('sample_surface',positions=[[0,0]])
            assert abs(surface['samples'][0]['position'][2]-20)<.1
            road=await call('create_path',kind='Road',nodes=[[0,0,20],[5,0,20]],settings={'width':10})
            assert (await call('get_path_info',name=road['object']))['width']==10
            await call('delete_object',name=road['object'])
            duplicate=(await call('duplicate_object',name=name))['objects'][0]['name']
            await call('delete_object',name=duplicate)
            await call('paint_terrain',layer='alpha',tool='PAINT',x=0,y=0,radius=20,strength=1,invert=True)
            assert (await call('validate_map'))['valid']
            await call('save_project',path=str(directory/'ai.ruster'))
            await call('export_map',path=str(directory/'ai.map'))
            for test_token,kind,values in [('wrong-token','get_scene_info',{}),(token,'execute_code',{'code':'raise Exception("must not execute")'})]:
                client=BlenderConnection('127.0.0.1',port,test_token)
                try:
                    try:client.send_command(kind,values)
                    except Exception:pass
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
