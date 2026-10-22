"""Exercise native panel branches and dialogs in a real Blender UI.

Use --enable-event-simulate in a graphical session. Forces advanced sections open
to catch RNA/layout failures hidden by default-collapsed controls.
"""
import os
from pathlib import Path
import sys
import tempfile
import traceback
from types import SimpleNamespace
import bpy

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import ruster
from ruster import app,ui,editing,placement,protection,painting,layers
from ruster.assets import catalog
from tests.fixtures import sample_world

temporary=tempfile.TemporaryDirectory(prefix='ruster-ui-draw-')
os.environ['RUSTER_USER_DIR']=str(Path(temporary.name)/'user')
ruster.register()
state={'stage':0,'draws':set(),'dialogs':set()}


def property_guard(original):
    def draw(self,context):
        if ui.is_map(context):
            print('Unrelated Blender properties leaked into map mode',type(self).__name__,flush=True)
            os._exit(1)
        original(self,context)
    return draw


# Panels with no original poll need a fresh RNA callback registration.
for name in ('SCENE_PT_scene','SCENE_PT_unit','SCENE_PT_keying_sets'):
    cls=getattr(bpy.types,name)
    cls.draw=property_guard(cls.draw)
native_section=ui.section
def open_section(layout,identifier,title,icon,**_kwargs):
    return native_section(layout,'test_'+identifier,title,icon,closed=False)
ui.section=open_section


class RUSTER_PT_ui_contract(bpy.types.Panel):
    bl_label='UI Contract'
    bl_space_type='VIEW_3D'
    bl_region_type='UI'
    bl_category='Item'
    def draw(self,context):
        try:
            proxy=SimpleNamespace(layout=self.layout)
            for cls in (ui.RUSTER_PT_map,ui.RUSTER_PT_prefabs,ui.RUSTER_PT_selection,ui.RUSTER_PT_assets,
                        ui.RUSTER_PT_properties,ui.RUSTER_PT_terrain,ui.RUSTER_PT_paint,ui.RUSTER_PT_paths,
                        ui.RUSTER_MT_file,ui.RUSTER_MT_edit,ui.RUSTER_MT_map,ui.RUSTER_MT_assets,
                        protection.RUSTER_MT_commands):
                cls.draw(proxy,context)
            ui.view_header(proxy,context)
            ui.readonly_source_menu(proxy,context)
            ui.properties_header(proxy,context)
            editing.RUSTER_WST_terrain.draw_settings(context,self.layout,None)
            painting.RUSTER_WST_prefab.draw_settings(context,self.layout,None)
            state['draws'].add(state['stage'])
        except Exception:
            traceback.print_exc();os._exit(1)


dialogs=[app.RUSTER_OT_setup,app.RUSTER_OT_welcome,editing.RUSTER_OT_new_map,
         editing.RUSTER_OT_generate,placement.RUSTER_OT_surface_snap,
         placement.RUSTER_OT_scatter,placement.RUSTER_OT_replace]


def mask_dialog(layer):
    def invoke(self,context,event):
        self.layer=layer
        self.channel=layers.channel_items(self,context)[-1][0]
        return context.window_manager.invoke_props_dialog(self,width=440)
    def execute(self,context):return {'FINISHED'}
    cls=type('RUSTER_OT_test_mask_'+layer,(bpy.types.Operator,),{
        '__module__':__name__,'__annotations__':layers.mask_properties(),
        'bl_idname':'ruster.test_mask_'+layer,'bl_label':'Layer Mask Options',
        'invoke':invoke,'execute':execute,'draw':layers.MaskOptions.draw})
    bpy.utils.register_class(cls)
    return cls


# Exercise the actual file-selector options on real RNA data/UILayout, including
# the old four-channel biome layout, without automating OS file picker windows.
dialogs.extend(mask_dialog(layer) for layer in ('splat','biome','topology','alpha'))
def checked_draw(original,name):
    def draw(self,context):
        try:
            original(self,context);state['dialogs'].add(name)
        except Exception:
            traceback.print_exc();os._exit(1)
    return draw

for cls in dialogs:cls.draw=checked_draw(cls.draw,cls.bl_idname)
# Isolate each dialog; setup normally opens the welcome popup when cancelled.
app.RUSTER_OT_setup.cancel=lambda self,context:None
bpy.utils.register_class(RUSTER_PT_ui_contract)


def perform():
    stage=state['stage']
    window=bpy.context.window
    if stage==0:
        window.event_simulate(type='ESC',value='PRESS')
        path=Path(temporary.name)/'ui.map';path.write_bytes(sample_world().write())
        app.open_path(path)
        area=next(a for a in window.screen.areas if a.type=='VIEW_3D')
        state['area']=area
        area.spaces.active.show_region_ui=True
        with bpy.context.temp_override(area=area):bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP',iterations=1)
        from contextlib import closing
        with closing(catalog.connect(app.scene.cache_dir())) as db:
            for uid in range(20):
                path=f'assets/test/prefab_{uid}.prefab'
                db.execute('INSERT OR REPLACE INTO names VALUES(?,?)',(uid,path))
                db.execute('INSERT OR REPLACE INTO assets VALUES(?,?,?,?)',(path,'bundle','file',uid))
            db.commit()
        window.event_simulate(type='MOUSEMOVE',value='NOTHING',x=600,y=500)
        state['prefab']=app.scene.prefab_roots()[0]
        state['path']=next(o for o in bpy.context.scene.objects if o.get('ruster_kind')=='PATH')
    elif 1<=stage<=6:
        if stage==1:
            region=next(r for r in state['area'].regions if r.type=='UI')
            if region.active_panel_category!='Ruster' or bpy.app.timers.is_registered(ui.close_map_timeline):
                state['focus_attempts']=state.get('focus_attempts',0)+1
                assert state['focus_attempts']<25,'Map did not focus its Rust controls'
                return .2
            region.active_panel_category='Item'
        else:assert stage in state['draws'],f'UI did not draw in stage {stage}'
        brush=bpy.context.scene.ruster_brush
        brush.layer=('terrain','water','splat','biome','topology','alpha')[stage-1]
        brush.tool=('STAMP','CLONE','SLOPE','FLATTEN','TERRACE','NOISE')[stage-1]
        obj=state['path'] if stage==6 else state['prefab']
        bpy.context.view_layer.objects.active=obj
        bpy.context.scene.ruster.busy=stage==3
        bpy.context.scene.ruster.asset_progress_known=True
        bpy.context.scene.ruster.asset_progress=.6
        bpy.context.scene.ruster.query_page=1 if stage==4 else 0
        bpy.context.scene.ruster_paint.palette=('SINGLE','FAVORITES','SELECTED')[stage%3]
    elif stage==7:
        assert 7 in state['draws']
        region=next(r for r in state['area'].regions if r.type=='WINDOW')
        with bpy.context.temp_override(area=state['area'],region=region):
            bpy.ops.object.mode_set(mode='EDIT')
    elif stage==8:
        assert 8 in state['draws']
        with bpy.context.temp_override(area=state['area']):bpy.ops.object.mode_set(mode='OBJECT')
    elif 9<=stage<9+len(dialogs)*2:
        index=(stage-9)//2
        if (stage-9)%2==0:
            group,name=dialogs[index].bl_idname.split('.')
            print('Opening UI dialog',group+'.'+name,flush=True)
            region=next(r for r in state['area'].regions if r.type=='WINDOW')
            with bpy.context.temp_override(area=state['area'],region=region):getattr(getattr(bpy.ops,group),name)('INVOKE_DEFAULT')
        else:
            assert dialogs[index].bl_idname in state['dialogs']
            window.event_simulate(type='ESC',value='PRESS')
    else:
        assert len(state['dialogs'])==len(dialogs)
        print('RUSTER_GUI_UI_PANELS_DIALOGS_OK',flush=True)
        bpy.ops.wm.quit_blender();return None
    state['stage']=stage+1
    state['area'].tag_redraw()
    return .6


def step():
    try:
        with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):return perform()
    except Exception:
        traceback.print_exc();os._exit(1)

bpy.app.timers.register(step,first_interval=2.)
