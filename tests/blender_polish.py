"""Loading feedback identifies actionable placements and keeps full diagnostics."""
import json,os,sys,tempfile,traceback
from pathlib import Path
import bpy
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
if '--' in sys.argv:sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import ruster
from ruster import app,scene,studio,loading,browser,placement,quitting
from ruster.core import wire,settings
from ruster.assets import catalog
from contextlib import closing


def run():
    with tempfile.TemporaryDirectory(prefix='ruster-polish-') as directory:
        os.environ['RUSTER_USER_DIR']=directory
        ruster.register();studio.new_prefab()
        roots=[scene.root_object([wire.encode(2,0,uid)],bpy.context.scene.collection) for uid in range(6)]
        roots[0]['ruster_visual']=True
        roots[1]['ruster_model_error']='Missing source mesh'
        roots[2]['ruster_marker']='SOUND'
        roots[3]['ruster_visual']=True;roots[3]['ruster_model_error']='Material conversion warning'
        app._pending_asset_ids.add(4)
        assert loading.model_summary()=={'READY':1,'ISSUE':2,'HELPER':1,'LOADING':1,'MISSING':1}
        bpy.context.scene.ruster.busy=True
        assert loading.header_label(bpy.context.scene.ruster,loading.model_summary())=='Loading assets…'
        bpy.context.scene.ruster.busy=False
        assert '2 with issues' in loading.header_label(bpy.context.scene.ruster,loading.model_summary())
        app.save_project(Path(directory)/'Saved.ruster')
        assert bpy.ops.ruster.select_model_status(status='ISSUE')=={'FINISHED'}
        assert set(placement.selected_prefabs())=={roots[1],roots[3]}
        assert bpy.ops.ruster.select_model_status(status='MISSING')=={'FINISHED'}
        assert placement.selected_prefabs()==[roots[5]]
        app._pending_asset_ids.clear()
        # Reports combine the last worker batch and errors retained by offline
        # projects. A long message remains available in full on the clipboard.
        error='Missing source mesh '+('diagnostic '*100)
        scene.cache_dir().mkdir(parents=True,exist_ok=True)
        (scene.cache_dir()/'asset-report.json').write_text(json.dumps([{'uid':1,'error':error}]))
        assert bpy.ops.ruster.asset_report()=={'FINISHED'}
        assert bpy.ops.ruster.copy_asset_report()=={'FINISHED'}
        report=bpy.data.texts['Rustmatics Asset Report'].as_string()
        assert error in report and 'Material conversion warning' in report
        assert not quitting.has_unsaved_changes(),'Inspection changed the editable document'
        with closing(catalog.connect(scene.cache_dir())) as db:
            db.executemany('INSERT INTO names VALUES(?,?)',[(uid,f'assets/props/item_{uid}.prefab') for uid in range(48)])
            db.commit()
        settings.save({'recent_prefabs':[str(uid) for uid in reversed(range(48))]})
        state=bpy.context.scene.ruster;state.recent_only=True;state.available_only=False
        page=browser.prefab_page(state)
        assert page['total']==48 and page['pages']==4 and [row[0] for row in page['rows']]==list(range(47,35,-1))
        state.query_page=100
        page=browser.prefab_page(state)
        assert page['page']==3 and [row[0] for row in page['rows']]==list(range(11,-1,-1))
        state.query='item_47'
        assert browser.prefab_page(state)['total']==1 and state.query_page==0
        ruster.unregister()
    print('RUSTER_PREFAB_POLISH_STATE_OK',flush=True)


try:run()
except Exception:traceback.print_exc();os._exit(1)
