"""Type reordered queries into Blender's actual prefab search popup."""
import os,sys,tempfile,traceback
from pathlib import Path
from contextlib import closing
import bpy
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
if '--' in sys.argv:sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
temporary=tempfile.TemporaryDirectory(prefix='ruster-search-')
os.environ['RUSTER_USER_DIR']=temporary.name
import ruster
from ruster import app,scene,studio
from ruster.assets import catalog
ruster.register()
app.request_assets=lambda ids:True  # This exercises search, not bundle extraction.
with closing(catalog.connect(scene.cache_dir())) as db:
    db.executemany('INSERT INTO names VALUES(?,?)',[
        (42,'assets/bundled/prefabs/modding/cubes/tiled/cube_tiled_dev_01.prefab'),
        (43,'assets/bundled/prefabs/modding/cubes/tiled/cube_tiled_dev_07.prefab'),
        (44,'assets/prefabs/building/wall.external_high.stone.prefab')]);db.commit()
    db.execute('INSERT INTO assets SELECT path,?,?,uid FROM names',('bundle','file'));db.commit()
queries=[('dev cube 01',42),('01 cube dev',42),('stone wall high external',44)]
state={'step':0,'query':0}


def step():
    try:
        window=bpy.context.window_manager.windows[0]
        area=next(a for a in window.screen.areas if a.type=='VIEW_3D')
        region=next(r for r in area.regions if r.type=='WINDOW')
        with bpy.context.temp_override(window=window,area=area,region=region):
            phase=state['step']
            if phase==0:
                window.event_simulate(type='ESC',value='PRESS')
                scene.clear_scene()
            elif phase==1:
                bpy.ops.ruster.add_prefab('INVOKE_DEFAULT')
            elif phase==2:
                window.event_simulate(type='A',value='PRESS',ctrl=True)
                digits={'0':'ZERO','1':'ONE'}
                for char in queries[state['query']][0]:
                    kind='SPACE' if char==' ' else digits.get(char,char.upper())
                    window.event_simulate(type=kind,value='PRESS',unicode=char)
                    window.event_simulate(type=kind,value='RELEASE')
            elif phase==3:
                window.event_simulate(type='RET',value='PRESS')
            else:
                roots=scene.prefab_roots()
                query,uid=queries[state['query']]
                assert len(roots)==1 and roots[0]['ruster_uid']==str(uid),(query,[o.name for o in roots])
                assert '.' not in roots[0].name and '_' not in roots[0].name
                print('NATIVE_PREFAB_SEARCH_QUERY_OK',query,uid,flush=True)
                bpy.data.objects.remove(roots[0],do_unlink=True)
                state['query']+=1
                if state['query']==len(queries):
                    ruster.unregister();temporary.cleanup()
                    print('RUSTER_GUI_ANY_ORDER_PREFAB_SEARCH_OK',flush=True)
                    bpy.ops.wm.quit_blender();return None
                state['step']=1;return .6
            state['step']+=1
        return .8
    except Exception:
        traceback.print_exc();os._exit(1)


bpy.app.timers.register(step,first_interval=2)
