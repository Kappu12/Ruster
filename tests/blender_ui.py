"""Validate the UI against the exact bundled Blender, including theme preservation."""
import os
from pathlib import Path
import sys
import tempfile
import traceback
import bpy

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
if '--' in sys.argv and sys.argv[sys.argv.index('--')+1:]:
    sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import ruster
from ruster import app,ui,ui_style,editing,painting
from tests.fixtures import sample_world


def theme_snapshot(data):
    result={}
    for prop in data.bl_rna.properties:
        if prop.identifier=='rna_type':continue
        value=getattr(data,prop.identifier)
        if prop.type=='POINTER':result[prop.identifier]=theme_snapshot(value) if value else None
        elif prop.type=='COLLECTION':result[prop.identifier]=[theme_snapshot(item) for item in value]
        else:result[prop.identifier]=tuple(value) if getattr(prop,'is_array',False) else value
    return result


def run():
    icons=set(bpy.types.UILayout.bl_rna.functions['operator'].parameters['icon'].enum_items.keys())
    assert set(ui_style.ICONS.values())<=icons, 'Unknown Blender UI icon'
    icon_root=Path(bpy.utils.system_resource('DATAFILES'))/'icons'
    assert len(set(ui_style.TOOL_ICONS.values()))==2
    for name in ui_style.TOOL_ICONS.values():
        assert (icon_root/(name+'.dat')).is_file(),f'Missing bundled toolbar icon: {name}'
    assert editing.RUSTER_WST_terrain.bl_icon==ui_style.TOOL_ICONS['terrain']
    assert painting.RUSTER_WST_prefab.bl_icon==ui_style.TOOL_ICONS['prefab']
    with tempfile.TemporaryDirectory(prefix='ruster-ui-') as directory:
        os.environ['RUSTER_USER_DIR']=str(Path(directory)/'user')
        source=Path(directory)/'ui.map';source.write_bytes(sample_world().write())
        for preset in ('Blender_Dark.xml','Blender_Light.xml'):
            theme=next(Path(path)/preset for path in bpy.utils.preset_paths('interface_theme') if (Path(path)/preset).exists())
            bpy.ops.script.execute_preset(filepath=str(theme),menu_idname='USERPREF_MT_interface_theme_presets')
            before=theme_snapshot(bpy.context.preferences.themes[0])
            old_header=bpy.types.VIEW3D_HT_header.draw
            ruster.register()
            for name in ui_style.ACTIONS:
                group,operator=name.split('.')
                getattr(getattr(bpy.ops,group),operator).get_rna_type()
            # Adding enum icons must preserve numeric values in existing projects.
            assert [(item.identifier,item.value) for item in editing.RUSTER_PG_brush.bl_rna.properties['layer'].enum_items]==[
                ('terrain',0),('water',1),('splat',2),('biome',3),('topology',4),('alpha',5)]
            app.open_path(source)
            assert ui.is_map(bpy.context)
            assert theme_snapshot(bpy.context.preferences.themes[0])==before
            assert bpy.ops.ruster.new('EXEC_DEFAULT')=={'FINISHED'}
            assert not ui.is_map(bpy.context)
            assert bpy.data.objects.get('Cube') and 'Modeling' in bpy.data.workspaces
            assert theme_snapshot(bpy.context.preferences.themes[0])==before
            ruster.unregister()
            assert bpy.types.VIEW3D_HT_header.draw==old_header
            assert theme_snapshot(bpy.context.preferences.themes[0])==before
    print('RUSTER_BLENDER_UI_THEME_ICONS_OK',flush=True)


try:run()
except Exception:
    traceback.print_exc();os._exit(1)
