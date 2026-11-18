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
                assert {'search_prefabs','place_prefab','transform_object','get_scene_info','export_map'}<=tools.keys()
                assert 'execute_code' not in tools
                assert tools['get_scene_info'].annotations.readOnlyHint
                assert len(tools)==65
                assert {'add_ground','paint_ground','get_ground_status'}<=tools.keys()
                assert tools['get_ground_status'].annotations.readOnlyHint
                assert {'get_project_status','list_recent_projects','new_project','open_project','get_live_preview_status',
                    'start_live_preview','stop_live_preview','send_live_preview_command','grant_live_preview_owner'}<=tools.keys()
                assert tools['get_project_status'].annotations.readOnlyHint
                assert tools['get_live_preview_status'].annotations.readOnlyHint
                assert tools['open_project'].annotations.destructiveHint and tools['stop_live_preview'].annotations.destructiveHint
                assert tools['open_project'].inputSchema['properties']['discard_unsaved']['default'] is False
                assert {'get_blender_context','get_viewport_state','set_viewport_state','set_cursor','measure_objects','transform_objects_relative','radial_array_objects','distribute_objects','snap_objects_to_grid'}<=tools.keys()
                assert tools['measure_objects'].annotations.readOnlyHint
                assert not tools['radial_array_objects'].annotations.destructiveHint
                viewport=tools['set_viewport_state'].inputSchema['$defs']['ViewportSettings']
                assert viewport['additionalProperties'] is False and 'projection' in viewport['properties']
                assert not {'execute_code','paint_terrain','sample_surface','snap_objects_to_terrain','create_path','update_path','get_path_info','generate_map','get_generation_status','cancel_generation'} & tools.keys()
                assert tools['delete_object'].annotations.destructiveHint
                assert {'get_prefab_details','list_prefab_categories','place_prefabs','transform_objects','group_objects','get_viewport_image','export_assembly','get_objects_info','get_prefabs_details','list_objects','get_selection','select_objects','duplicate_objects','delete_objects','array_objects','align_objects','snap_objects_to_plane','get_export_formats','export_prefab','import_prefab','export_models','import_map_prefabs','get_io_settings','set_io_settings'}<=tools.keys()
                schema=tools['place_prefabs'].inputSchema
                assert 'PrefabPlacement' in schema['$defs'] and 'position' in schema['$defs']['PrefabPlacement']['required']
                assert tools['get_viewport_image'].inputSchema['properties']['include_overlays']['default'] is False
                view=tools['focus_view'].inputSchema['properties']
                assert 'OBLIQUE' in view['axis']['enum'] and 'rotation_degrees' in view
                assert 'origin' in tools['export_assembly'].inputSchema['properties']
                assert '2000-placement' in tools['import_assembly'].description
                resources=(await session.list_resources()).resources
                assert {str(r.uri) for r in resources}=={'ruster://guide/building','ruster://guide/design','ruster://guide/headless'}
                headless=await session.read_resource('ruster://guide/headless')
                assert '--export-map' in headless.contents[0].text and 'export_project_report' in headless.contents[0].text
                assert tools['export_project_report'].annotations.destructiveHint
                assert tools['export_map'].inputSchema['properties']['require_ground']['default'] is False
                design=await session.read_resource('ruster://guide/design')
                assert design.contents[0].text==(Path(__file__).resolve().parents[1]/'docs'/'design.md').read_text(encoding='utf-8')
                assert 'Do not create a new triangle mesh' in design.contents[0].text
                guide=await session.read_resource('ruster://guide/building')
                assert 'Never guess IDs' in guide.contents[0].text
                prompts=(await session.list_prompts()).prompts
                assert {p.name for p in prompts}=={'build_rust_composition','audit_rust_composition'}
                prompt=await session.get_prompt('build_rust_composition',{'description':'A Rust watchtower'})
                assert 'watchtower' in prompt.messages[0].content.text
                result=await session.call_tool('get_scene_info',{})
                assert result.isError and 'Enable MCP' in result.content[0].text
    asyncio.run(run())
