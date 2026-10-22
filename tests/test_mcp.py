import asyncio
import json
from pathlib import Path
import sys
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
from ruster.core import settings,mcp_config


def test_mcp_settings_are_opt_in_and_token_is_stable(tmp_path,monkeypatch):
    monkeypatch.setenv('RUSTER_USER_DIR',str(tmp_path))
    settings.save({'rust_install':'game'})
    assert not mcp_config.enabled(settings.load())
    assert not mcp_config.enabled({'mcp_enabled':'true'})
    assert mcp_config.port({'mcp_port':True})==9877
    assert mcp_config.port({'mcp_port':65536})==9877
    token=mcp_config.token()
    assert len(token)>=32 and token==mcp_config.token()
    assert settings.load()['rust_install']=='game'


def test_real_stdio_mcp_handshake_and_tool_schema(tmp_path,monkeypatch):
    monkeypatch.setenv('RUSTER_USER_DIR',str(tmp_path))
    async def run():
        params=StdioServerParameters(command=sys.executable,args=[str(Path(__file__).resolve().parents[1]/'mcp_server.py')],env={'RUSTER_USER_DIR':str(tmp_path)})
        async with stdio_client(params) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                listing=await session.list_tools();tools={tool.name:tool for tool in listing.tools}
                assert {'search_prefabs','place_prefab','transform_object','paint_terrain','get_scene_info','export_map'}<=tools.keys()
                assert 'execute_code' not in tools
                assert tools['get_scene_info'].annotations.readOnlyHint
                assert tools['get_generation_status'].annotations.readOnlyHint
                assert {'generate_map','cancel_generation'}<=tools.keys()
                assert set(tools['generate_map'].inputSchema['properties'])=={'seed','size'}
                assert tools['delete_object'].annotations.destructiveHint
                assert {'get_prefab_details','list_prefab_categories','place_prefabs','transform_objects','group_objects','get_viewport_image','create_path','export_assembly'}<=tools.keys()
                schema=tools['place_prefabs'].inputSchema
                assert 'PrefabPlacement' in schema['$defs'] and 'position' in schema['$defs']['PrefabPlacement']['required']
                resources=(await session.list_resources()).resources
                assert {str(r.uri) for r in resources}=={'ruster://guide/building','ruster://guide/terrain'}
                guide=await session.read_resource('ruster://guide/building')
                assert 'Never guess IDs' in guide.contents[0].text
                prompts=(await session.list_prompts()).prompts
                assert {p.name for p in prompts}=={'build_rust_composition','audit_rust_map'}
                prompt=await session.get_prompt('build_rust_composition',{'description':'A Rust watchtower'})
                assert 'watchtower' in prompt.messages[0].content.text
                result=await session.call_tool('get_scene_info',{})
                assert result.isError and 'Enable MCP' in result.content[0].text
    asyncio.run(run())
