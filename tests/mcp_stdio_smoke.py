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
        params=StdioServerParameters(command=sys.executable,args=['-B',str(root/'mcp_server.py')],env={'RUSTER_USER_DIR':directory,'PYTHONIOENCODING':'utf-8'})
        async with stdio_client(params) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                design=await session.read_resource('ruster://guide/design')
                assert 'Do not create a new triangle mesh' in design.contents[0].text
                result=await session.call_tool('get_scene_info',{})
                assert result.isError and 'Enable MCP' in result.content[0].text
    print('RUSTER_PACKAGED_MCP_STDIO_OK',flush=True)


asyncio.run(run())
