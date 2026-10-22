"""Type into the actual ranked Add dialog; metadata only, isolated test scene."""
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
requests=[]
app.request_assets=lambda ids:requests.append(tuple(ids)) or True
with closing(catalog.connect(scene.cache_dir())) as db:
    rows=[(42,'assets/bundled/prefabs/modding/cubes/tiled/cube_tiled_dev_01.prefab'),
          (43,'assets/bundled/prefabs/modding/cubes/tiled/cube_tiled_dev_07.prefab'),
          (44,'assets/prefabs/building/wall.external_high.stone.prefab'),
          (147092032,'assets/prefabs/tools/hose/ioslothandles/ioslothandlehose_pending.prefab'),
          (4153457039,'assets/prefabs/tools/wire/ioslothandles/ioslothandle.prefab'),
          (46,'assets/prefabs/gloweyes/gloweyes.item.prefab'),
          (47,'assets/prefabs/gloweyes/gloweyes.wearable.prefab'),
          (50,'assets/prefabs/target/sound/target_deploy.prefab'),
          (55,'assets/prefabs/test/under_score.prefab'),
          (56,'assets/prefabs/props/percent%cube.prefab'),
          (57,'assets/prefabs/props/percentXcube.prefab')]
    rows += [(200+i,f'assets/prefabs/props/page_item_{i:02}.prefab') for i in range(16)]
    db.executemany('INSERT INTO names VALUES(?,?)',rows)
    db.execute('INSERT INTO assets SELECT path,?,?,uid FROM names',('bundle','file'));db.commit()
queries=[('dev',42,'add',''),('dev cube',42,'add',''),('DEV',42,'add',''),
         ('CuBe DeV',42,'add',''),('01 cube dev',42,'add',''),
         ('stone wall high external',44,'add',''),('io',147092032,'add',''),
         ('IO',147092032,'add',''),('io',4153457039,'select',''),
         ('glow',147092032,'add',''),('GLOW',147092032,'add',''),
         ('cyan glow',147092032,'add',''),('glow cyan',147092032,'add',''),
         ('(CYAN glow)',147092032,'add',''),('glowing hose',147092032,'add',''),
         ('fluid pipe',147092032,'add',''),('neon',147092032,'add',''),
         ('ioslothandlehose_pending',147092032,'add',''),
         ('page item',210,'page',''),('effect sound',None,'empty',''),
         ('EFFECT SOUND',50,'add','@HIDDEN'),('dev cube',42,'add',''),
         ('under_',55,'add','@ALL_ASSETS'),('%cube',56,'add',''),
         ('zzzxnotfound',None,'empty',''),('glow',None,'cancel','')]
state={'step':0,'query':0}
latest={}
native_results=studio.search_results

def observed_results(operator,context):
    data=native_results(operator,context)
    latest.update(operator=operator,query=getattr(operator,'query',''),data=data)
    return data

studio.search_results=observed_results


def step():
    try:
        window=bpy.context.window_manager.windows[0]
        area=next(a for a in window.screen.areas if a.type=='VIEW_3D')
        region=next(r for r in area.regions if r.type=='WINDOW')
        query,uid,operation,category=queries[state['query']]
        with bpy.context.temp_override(window=window,area=area,region=region):
            phase=state['step']
            if phase==0:
                window.event_simulate(type='ESC',value='PRESS')
                scene.clear_scene()
                window.event_simulate(type='MOUSEMOVE',value='NOTHING',x=window.width//2,y=window.height//2)
            elif phase==1:
                state['requests']=len(requests)
                bpy.ops.ruster.add_prefab('INVOKE_DEFAULT',category=category)
            elif phase==2:
                window.event_simulate(type='A',value='PRESS',ctrl=True)
                digits=dict(zip('0123456789',('ZERO','ONE','TWO','THREE','FOUR','FIVE','SIX','SEVEN','EIGHT','NINE')))
                punctuation={'_':'MINUS','(':'NINE',')':'ZERO','%':'FIVE'}
                for char in query:
                    kind='SPACE' if char==' ' else punctuation.get(char,digits.get(char,char.upper()))
                    window.event_simulate(type=kind,value='PRESS',unicode=char)
                    window.event_simulate(type=kind,value='RELEASE')
            elif phase==3:
                assert latest['query']==query,(query,latest.get('query'))
                items=latest['data']['items']
                expected='NONE' if operation=='empty' else '147092032' if operation in {'select','cancel'} else '200' if operation=='page' else str(uid)
                assert items[0][0]==expected,(query,items)
                assert not scene.prefab_roots(),'Typing placed a model'
                assert len(requests)==state['requests'],'Typing extracted assets'
                assert len(studio._search_cache)<=studio.SEARCH_CACHE_LIMIT
                assert all(len(page['items'])<=studio.SEARCH_PAGE_SIZE for page in studio._search_cache.values())
                key='ESC' if operation=='cancel' else 'RET'
                window.event_simulate(type=key,value='PRESS');window.event_simulate(type=key,value='RELEASE')
            elif phase==4:
                if operation=='select':
                    assert latest['data']['items'][1][0]==str(uid)
                    latest['operator'].prefab=str(uid)
                if operation=='page':
                    assert latest['data']['pages']==2
                    latest['operator'].page=2
                    assert latest['data']['page']==1
                    assert latest['data']['items'][0][0]==str(uid)
                key='ESC' if operation=='cancel' else 'RET'
                window.event_simulate(type=key,value='PRESS');window.event_simulate(type=key,value='RELEASE')
            else:
                roots=scene.prefab_roots()
                assert (not roots if uid is None else len(roots)==1 and roots[0]['ruster_uid']==str(uid)),(query,[o.name for o in roots])
                print('RANKED_PREFAB_SEARCH_QUERY_OK',query,uid,operation,flush=True)
                if roots:bpy.data.objects.remove(roots[0],do_unlink=True)
                state['query']+=1
                if state['query']==len(queries):
                    studio.search_results=native_results
                    ruster.unregister();temporary.cleanup()
                    print('RUSTER_GUI_RANKED_PREFAB_SEARCH_OK',flush=True)
                    bpy.ops.wm.quit_blender();return None
                state['step']=1;return .3
            state['step']+=1
        return .4
    except Exception:
        traceback.print_exc();os._exit(1)


bpy.app.timers.register(step,first_interval=2)
