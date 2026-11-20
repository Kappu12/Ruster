"""Real native draws and Save/Don't Save/Cancel across New and Open."""
import os,sys,tempfile,traceback,json
from pathlib import Path
from contextlib import closing
import bpy
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import ruster
from ruster import app,scene,studio,quitting,ui,loading
from ruster.core import wire
from ruster.assets import catalog

temporary=tempfile.TemporaryDirectory(prefix='ruster-polish-ui-')
os.environ['RUSTER_USER_DIR']=temporary.name
ruster.register()
state={'phase':0,'draws':set()}
target=Path(temporary.name)/'Saved.ruster'


class RUSTER_PT_polish_test(bpy.types.Panel):
    bl_label='Polish Verification'
    bl_space_type='VIEW_3D'
    bl_region_type='UI'
    bl_category='Rustmatics'
    bl_order=-100
    def draw(self,context):
        try:
            ui.RUSTER_PT_prefabs.draw(self,context)
            loading.draw_status(self.layout,context)
            state['draws'].add(state['phase'])
        except Exception:traceback.print_exc();os._exit(1)


bpy.utils.register_class(RUSTER_PT_polish_test)


def key(window,value):
    window.event_simulate(type=value,value='PRESS')
    window.event_simulate(type=value,value='RELEASE')


def cancel_picker():
    window=next(w for w in bpy.context.window_manager.windows if any(a.type=='FILE_BROWSER' for a in w.screen.areas))
    area=next(a for a in window.screen.areas if a.type=='FILE_BROWSER')
    with bpy.context.temp_override(window=window,area=area):bpy.ops.file.cancel()


def step():
    try:
        phase=state['phase']
        window=bpy.context.window_manager.windows[0]
        area=next(a for a in window.screen.areas if a.type=='VIEW_3D')
        region=next(r for r in area.regions if r.type=='WINDOW')
        with bpy.context.temp_override(window=window,area=area,region=region):
            if phase==0:
                studio.new_prefab()
                root=scene.root_object([wire.encode(2,0,42)],bpy.context.scene.collection)
                root['ruster_model_error']='Synthetic missing mesh; use Load / Retry Selected Models.'
                app.save_project(target)
                with closing(catalog.connect(scene.cache_dir())) as db:
                    db.executemany('INSERT INTO names VALUES(?,?)',[(42,'assets/props/example.prefab'),(43,'assets/props/unavailable.prefab')])
                    db.execute('INSERT INTO assets VALUES(?,?,?,?)',('assets/props/example.prefab','bundle','file',1));db.commit()
                scene.prefab_roots()[0].location.x=7
                bpy.ops.ruster.new('INVOKE_DEFAULT')
            elif phase==1:
                assert quitting._dialog_open
                key(window,'ESC')
            elif phase==2:
                assert not quitting._dialog_open and scene.prefab_roots()[0].location.x==7
                bpy.ops.ruster.new('INVOKE_DEFAULT')
            elif phase==3:
                assert quitting._dialog_open
                key(window,'RET')
            elif phase==4:
                assert not bpy.context.scene.objects,'Save then New failed'
                assert not quitting.has_unsaved_changes()
                scene.root_object([wire.encode(2,0,43)],bpy.context.scene.collection)
                bpy.ops.ruster.new('INVOKE_DEFAULT')
            elif phase==5:
                key(window,'RET')
            elif phase==6:
                assert scene.prefab_roots(),'Untitled Save replaced the project before choosing a file'
                cancel_picker()
            elif phase==7:
                assert scene.prefab_roots() and not quitting._continuation
                bpy.ops.ruster.open('INVOKE_DEFAULT',filepath=str(target))
            elif phase==8:
                assert quitting._dialog_open
                key(window,'ESC')
            elif phase==9:
                assert int(scene.prefab_roots()[0]['ruster_uid'])==43
                bpy.ops.ruster.open('INVOKE_DEFAULT',filepath=str(target))
            elif phase==10:
                assert quitting._dialog_open
                bpy.ops.ruster.discard_changes(action='OPEN',filepath=str(target))
            elif phase==11:
                assert not quitting.has_unsaved_changes()
                assert scene.prefab_roots()[0].location.x==7
                scene.prefab_roots()[0].location.x=9
                bpy.ops.ruster.open('INVOKE_DEFAULT',filepath=str(target))
            elif phase==12:key(window,'RET')
            elif phase==13:
                assert not quitting.has_unsaved_changes() and scene.prefab_roots()[0].location.x==9
                assert state['draws'],'Native polish controls did not draw'
                bpy.ops.ruster.prefab_details(uid='43')
            elif phase==14:key(window,'ESC')
            elif phase==15:
                (scene.cache_dir()/'asset-report.json').write_text(json.dumps([{'uid':42,'error':'Synthetic missing mesh'}]))
                bpy.ops.ruster.asset_report('INVOKE_DEFAULT')
            elif phase==16:
                key(window,'RET')
            elif phase==17:
                # Closing the report must finish, rather than reopen the dialog.
                assert not any(op.bl_idname=='RUSTER_OT_report' for op in window.modal_operators)
                assert bpy.ops.ruster.copy_asset_report()=={'FINISHED'}
                assert 'Synthetic missing mesh' in bpy.context.window_manager.clipboard
                assert bpy.ops.ruster.copy_prefab(uid='42',value='PATH')=={'FINISHED'}
                assert bpy.context.window_manager.clipboard=='assets/props/example.prefab'
                if directory:=os.environ.get('RUSTER_POLISH_SCREENSHOTS'):
                    Path(directory).mkdir(parents=True,exist_ok=True)
                    bpy.ops.screen.screenshot(filepath=str(Path(directory)/'polish.png'))
                studio.new_prefab()
                scene.root_object([wire.encode(2,0,43)],bpy.context.scene.collection)
                bpy.ops.ruster.new('INVOKE_DEFAULT')
            elif phase==18:
                assert quitting._dialog_open
                key(window,'RET')
            elif phase==19:
                # A successful untitled save closes its temporary browser
                # window before New continues in the surviving editor window.
                picker=next(w for w in bpy.context.window_manager.windows if any(a.type=='FILE_BROWSER' for a in w.screen.areas))
                browser=next(a for a in picker.screen.areas if a.type=='FILE_BROWSER')
                browser.spaces.active.params.directory=os.fsencode(temporary.name+os.sep)
                browser.spaces.active.params.filename='Untitled Saved.ruster'
                with bpy.context.temp_override(window=picker,area=browser):bpy.ops.file.execute()
            elif phase==20:
                assert (Path(temporary.name)/'Untitled Saved.ruster').is_file()
                assert not bpy.context.scene.objects and not quitting._continuation
                scene.root_object([wire.encode(2,0,42)],bpy.context.scene.collection)
                # The confirmation must open centrally even when invoked with
                # the pointer near the top-right window controls.
                window.cursor_warp(window.width-10,window.height-10)
                bpy.ops.ruster.new('INVOKE_DEFAULT')
            elif phase==21:
                assert quitting._dialog_open
                if directory:=os.environ.get('RUSTER_POLISH_SCREENSHOTS'):
                    bpy.ops.screen.screenshot(filepath=str(Path(directory)/'save-choices.png'))
                # Click the native Don't Save button, so the test covers closing
                # the parent popup as well as the document continuation.
                x=window.width//2
                y=window.height//2-int(34*bpy.context.preferences.system.ui_scale)
                window.event_simulate(type='MOUSEMOVE',value='NOTHING',x=x,y=y)
                window.event_simulate(type='LEFTMOUSE',value='PRESS',x=x,y=y)
                window.event_simulate(type='LEFTMOUSE',value='RELEASE',x=x,y=y)
            elif phase==22:
                assert not bpy.context.scene.objects and not quitting._dialog_open
                assert not any(op.bl_idname=='RUSTER_OT_save_changes' for op in window.modal_operators)
                if directory:=os.environ.get('RUSTER_POLISH_SCREENSHOTS'):
                    bpy.ops.screen.screenshot(filepath=str(Path(directory)/'discard-completed.png'))
            elif phase==23:
                bpy.utils.unregister_class(RUSTER_PT_polish_test)
                ruster.unregister()
                print('RUSTER_GUI_PREFAB_POLISH_OK',flush=True)
                bpy.ops.wm.quit_blender();return None
        state['phase']+=1
        area.tag_redraw()
        return .7
    except Exception:traceback.print_exc();os._exit(1)


bpy.app.timers.register(step,first_interval=.7,persistent=True)
