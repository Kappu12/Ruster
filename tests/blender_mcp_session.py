"""Project replacement and preview RPCs with synthetic jobs; never launch Rust."""
import json,os,sys,tempfile,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
if '--' in sys.argv:sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
os.environ['RUSTER_PREVIEW_TEST_NO_DISCOVERY']='1'
import bpy,ruster
from ruster import scene,studio,app,mcp_bridge,live_preview
from ruster.assets import catalog
from ruster.core import wire


def run():
    with tempfile.TemporaryDirectory(prefix='ruster-mcp-session-') as folder:
        root=Path(folder);os.environ['RUSTER_USER_DIR']=str(root/'user')
        ruster.register();studio.new_prefab()
        server=mcp_bridge.RusterMCPServer(9877,'test-token-123456789012345678901234567890')
        def rpc(kind,**params):return server.execute_command({'token':server.token,'type':kind,'params':params})
        def call(kind,**params):
            result=rpc(kind,**params);assert result['status']=='success',result
            return result['result']
        def refused(kind,text,**params):
            names=set(bpy.context.scene.objects);result=rpc(kind,**params)
            assert result['status']=='error' and text in result['message'],result
            assert set(bpy.context.scene.objects)==names
        db=catalog.connect(scene.cache_dir());db.execute('INSERT INTO names VALUES(?,?)',(123456,'assets/test/source.prefab'));db.commit();db.close()
        assert not call('get_project_status')['unsaved_changes']
        assert not call('get_live_preview_status',log_lines=0)['active']
        scene.root_object([wire.encode(2,0,123456)],bpy.context.scene.collection)
        assert call('get_project_status')['unsaved_changes']
        refused('new_project','unsaved changes')
        refused('new_project','boolean',discard_unsaved='true')
        project=root/'first.ruster';call('save_project',path=str(project))
        assert call('get_project_status')['path']==str(project) and not call('get_project_status')['unsaved_changes']
        assert call('new_project')['prefab_count']==0
        # This actual file load must not retain a Window context override, old
        # selection RNA, or disconnect the authenticated command executor.
        assert call('open_project',path=str(project))['prefab_count']==1
        assert call('get_project_status')['path']==str(project)
        assert call('ping')['pong'] and server.token.startswith('test-token-')
        first=scene.prefab_roots()[0];first.location.x+=3;bpy.context.view_layer.update()
        refused('open_project','unsaved changes',path=str(project))
        refused('open_project','existing .ruster',path=str(root/'missing.ruster'),discard_unsaved=True)
        refused('open_project','absolute',path='relative.ruster',discard_unsaved=True)
        refused('open_project','Unknown parameters',path=str(project),discard_unsaved=True,execute_code='bad')
        bpy.context.scene.ruster.busy=True
        refused('new_project','asset extraction',discard_unsaved=True)
        bpy.context.scene.ruster.busy=False
        assert call('list_recent_projects')['projects'][0]['path']==str(project)
        assert call('open_project',path=str(project),discard_unsaved=True)['prefab_count']==1
        assert scene.prefab_roots()[0].location.x==0
        saved=(live_preview.backend.PreviewSession,live_preview.preview_client.verify_module,live_preview.installation,live_preview.preview_client.discover)
        jobs=[]
        class FakeSession:
            def __init__(self,base,port,owner,rows,**kwargs):
                self.directory=root/'synthetic-preview';self.directory.mkdir()
                self.port,self.owner,self.rows=port,owner,rows;self.options=kwargs
                self.active=True;self.status='STARTING';jobs.append(self)
            def start(self):return self
            def info(self):return {'status':self.status,'message':'Synthetic server','revision':1,'progress':.5 if self.status=='STARTING' else None}
            def log_tail(self,count):return ['synthetic console result'][-count:]
            def request_stop(self):self.status='STOPPING'
            def close(self):raise AssertionError('MCP blocked waiting for server cleanup')
            send_command=live_preview.backend.PreviewSession.send_command
        def no_client(*args):raise AssertionError('MCP launched or inspected the real game client')
        try:
            live_preview.backend.PreviewSession=FakeSession
            live_preview.preview_client.verify_module=lambda *_:None
            live_preview.installation=lambda:root/'synthetic-game'
            live_preview.preview_client.discover=no_client
            refused('start_live_preview','Game port',port=True)
            started=call('start_live_preview',port=29720,owner_id='76561198000000000')
            assert started['active'] and started['status']=='STARTING' and started['progress']==.5
            assert jobs[0].port==29720 and jobs[0].owner=='76561198000000000' and len(jobs[0].rows)==1
            assert not jobs[0].options['update_server'] and started['connect_command']=='connect 127.0.0.1:29720'
            refused('start_live_preview','already running')
            refused('send_live_preview_command','become ready',command='status')
            refused('open_project','Stop live preview',path=str(project),discard_unsaved=True)
            jobs[0].status='RUNNING'
            (jobs[0].directory/'client.status').write_text('ERROR\nSynthetic client initialization failure\n')
            status=call('get_live_preview_status',log_lines=3)
            assert 'Synthetic client initialization failure' in status['client'] and status['logs']==['synthetic console result']
            refused('get_live_preview_status','Log line count',log_lines=101)
            refused('send_live_preview_command','one console command',command='status\nquit')
            assert call('send_live_preview_command',command='status')['queued']
            refused('grant_live_preview_owner','SteamID64',steam_id='invalid')
            assert call('grant_live_preview_owner',steam_id='76561198000000000')['queued']
            commands=[json.loads(p.read_text())['command'] for p in (jobs[0].directory/'commands').glob('*.json')]
            assert 'status' in commands and any(value.startswith('ownerid 76561198000000000') for value in commands)
            assert call('stop_live_preview')['status']=='STOPPING'
            refused('new_project','Stop live preview',discard_unsaved=True)
            jobs[0].active=False;jobs[0].status='STOPPED'
            assert call('new_project',discard_unsaved=True)['prefab_count']==0
        finally:
            live_preview._job=None
            live_preview.backend.PreviewSession,live_preview.preview_client.verify_module,live_preview.installation,live_preview.preview_client.discover=saved
        ruster.unregister()
    print('RUSTER_MCP_PROJECT_AND_PREVIEW_OK',flush=True)


try:run()
except Exception:traceback.print_exc();os._exit(1)
