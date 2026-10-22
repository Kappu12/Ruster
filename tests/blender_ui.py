"""Validate the UI against the exact bundled Blender, including theme preservation."""
import os
import subprocess
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
from ruster import app,ui,ui_style,editing,painting,browser,scene,preferences
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
            old_navigation=bpy.types.USERPREF_PT_navigation_bar.draw
            old_scene_poll=bpy.types.SCENE_PT_scene.__dict__.get('poll')
            ruster.register()
            pref_state=bpy.context.window_manager.ruster_preferences
            pref_state.section='RUSTER_MCP'
            assert preferences.is_rust(bpy.context) and preferences.RUSTER_PT_preferences_mcp.poll(bpy.context)
            assert not bpy.types.USERPREF_PT_interface_display.poll(bpy.context)
            pref_state.section='THEMES'
            assert bpy.context.preferences.active_section=='THEMES' and not preferences.is_rust(bpy.context)
            pref_state.section='RUSTER_ASSETS'
            bpy.context.preferences.active_section='INTERFACE';preferences.native_changed()
            assert pref_state.section=='INTERFACE' and bpy.types.USERPREF_PT_interface_display.poll(bpy.context)
            game=Path(directory)/'Rust';(game/'Bundles').mkdir(parents=True,exist_ok=True);(game/'RustClient.exe').touch()
            from ruster.core import settings
            previous=app.start_job;jobs=[];original_config=settings.load()
            try:
                app.start_job=lambda action,*_args:jobs.append(action)
                pref_state.directory=str(game)
                assert bpy.ops.ruster.setup('EXEC_DEFAULT')=={'FINISHED'}
                assert jobs==['index']
                assert settings.load()['rust_install']==str(game.resolve())
            finally:
                app.start_job=previous;settings.save(original_config)
            for name in ui_style.ACTIONS:
                group,operator=name.split('.')
                getattr(getattr(bpy.ops,group),operator).get_rna_type()
            # Adding enum icons must preserve numeric values in existing projects.
            assert [(item.identifier,item.value) for item in editing.RUSTER_PG_brush.bl_rna.properties['layer'].enum_items]==[
                ('terrain',0),('water',1),('splat',2),('biome',3),('topology',4),('alpha',5)]
            app.open_path(source)
            assert ui.is_map(bpy.context)
            assert all(o.rotation_mode=='XYZ' for o in scene.prefab_roots())
            from contextlib import closing
            from ruster.assets import catalog
            with closing(catalog.connect(scene.cache_dir())) as db:
                db.executemany('INSERT OR REPLACE INTO names VALUES(?,?)',[(i,f'assets/test/item_{i}.prefab') for i in range(30)])
                db.commit()
            state=bpy.context.scene.ruster;state.available_only=False;state.query_page=100
            assert bpy.ops.ruster.catalog_page(delta=-1)=={'FINISHED'} and state.query_page==1
            state.available_only=True
            assert state.query_page==0
            assert 'assets/test/item_1.prefab' in browser.prefab_description('1','Place')
            assert bpy.ops.ruster.copy_prefab(uid='1')=={'FINISHED'}
            # Rotations should retain their orientation through Blender's native mode picker.
            obj=scene.prefab_roots()[0];bpy.context.view_layer.update();before_matrix=obj.matrix_world.copy()
            for mode in ('QUATERNION','AXIS_ANGLE','XYZ'):
                obj.rotation_mode=mode;bpy.context.view_layer.update()
                assert max(abs(obj.matrix_world[i][j]-before_matrix[i][j]) for i in range(4) for j in range(4))<1e-5
            assert theme_snapshot(bpy.context.preferences.themes[0])==before
            assert bpy.ops.ruster.new('EXEC_DEFAULT')=={'FINISHED'}
            assert not ui.is_map(bpy.context)
            assert bpy.context.scene.ruster.mode=='PREFAB' and not list(bpy.context.scene.objects)
            assert theme_snapshot(bpy.context.preferences.themes[0])==before
            # A background worker inherits the log handle. Unregister must reap
            # the process and release both handles, including on Windows.
            log=(Path(directory)/'cleanup-worker.log').open('w')
            child=subprocess.Popen([app.worker_python(),'-c','import time; time.sleep(30)'],stdout=log,stderr=subprocess.STDOUT)
            app._job,app._job_log=child,log
            ruster.unregister()
            assert child.poll() is not None and log.closed and app._job is None and app._job_log is None
            assert bpy.types.USERPREF_PT_navigation_bar.draw==old_navigation
            assert bpy.types.VIEW3D_HT_header.draw==old_header
            assert bpy.types.SCENE_PT_scene.__dict__.get('poll')==old_scene_poll
            assert theme_snapshot(bpy.context.preferences.themes[0])==before
    print('RUSTER_BLENDER_UI_THEME_ICONS_OK',flush=True)


try:run()
except Exception:
    traceback.print_exc();os._exit(1)
