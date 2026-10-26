"""Check the actual packaged stdio entry point using its bundled SDK/Python."""
import asyncio,site,sys,tempfile
from pathlib import Path
root=Path(sys.argv[1]).resolve()
sys.path.insert(0,str(root))
if (root/'python_modules').is_dir():
    sys.path.insert(0,str(root/'python_modules'))
    site.addsitedir(str(root/'python_modules'))
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client


async def run():
    with tempfile.TemporaryDirectory(prefix='ruster-stdio-') as directory:
        params=StdioServerParameters(command=sys.executable,args=[str(root/'mcp_server.py')],env={'RUSTER_USER_DIR':directory,'PYTHONIOENCODING':'utf-8'})
        async with stdio_client(params) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                tools=(await session.list_tools()).tools
                exposed={tool.name for tool in tools}
                assert len(exposed)==61,sorted(exposed)
                assert {'get_project_status','list_recent_projects','new_project','open_project','get_live_preview_status',
                    'start_live_preview','stop_live_preview','send_live_preview_command','grant_live_preview_owner'}<=exposed
                assert {'get_editor_status','get_objects_info','get_prefabs_details','array_objects','align_objects','export_models','export_prefab','import_map_prefabs','get_io_settings','set_io_settings'}<=exposed
                assert not {'execute_code','paint_terrain','sample_surface','snap_objects_to_terrain','generate_map','get_generation_status','cancel_generation','create_path','update_path','get_path_info'} & exposed
                resources=(await session.list_resources()).resources
                assert {str(resource.uri) for resource in resources}=={'ruster://guide/building','ruster://guide/design'}
                design=await session.read_resource('ruster://guide/design')
                assert 'Do not create a new triangle mesh' in design.contents[0].text
                result=await session.call_tool('get_scene_info',{})
                assert result.isError and 'Enable MCP' in result.content[0].text
    print('RUSTER_PACKAGED_MCP_STDIO_OK',flush=True)


asyncio.run(run())
