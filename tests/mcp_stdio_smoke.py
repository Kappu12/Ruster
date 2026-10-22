"""Check the actual packaged stdio entry point using its bundled SDK/Python."""
import asyncio,json,os,sys,tempfile
from pathlib import Path
root=Path(sys.argv[1]).resolve()
sys.path.insert(0,str(root/'python_modules'))
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client


async def run():
    with tempfile.TemporaryDirectory(prefix='ruster-stdio-') as directory:
        params=StdioServerParameters(command=sys.executable,args=[str(root/'mcp_server.py')],env={'RUSTER_USER_DIR':directory})
        async with stdio_client(params) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                tools=(await session.list_tools()).tools
                assert len(tools)==14 and all(t.name!='execute_code' for t in tools)
                result=await session.call_tool('get_scene_info',{})
                assert result.isError and 'Enable MCP' in result.content[0].text
    print('RUSTER_PACKAGED_MCP_STDIO_OK',flush=True)


asyncio.run(run())
