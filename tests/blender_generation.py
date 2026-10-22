"""Native controls, shared settings, and asynchronous results without Rust."""
import os,sys,tempfile,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
if '--' in sys.argv and sys.argv[sys.argv.index('--')+1:]:sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import bpy
import ruster
from ruster import generation,app
from ruster.core import settings
from tests.fixtures import sample_world


def run():
    with tempfile.TemporaryDirectory(prefix='ruster-generation-ui-') as directory:
        root=Path(directory);os.environ['RUSTER_USER_DIR']=str(root/'user');ruster.register()
        state=bpy.context.window_manager.ruster_generation
        assert state.size==4000 and state.seed==12345
        bpy.ops.ruster.random_seed();assert 0<=state.seed<=2147483647
        prefs=bpy.context.window_manager.ruster_preferences
        binary=root/('RustDedicated.exe' if sys.platform=='win32' else 'RustDedicated');binary.touch();binary.chmod(0o700)
        prefs.dedicated=str(binary)
        assert bpy.ops.ruster.generator_install()=={'FINISHED'}
        assert settings.load()['rust_dedicated']==str(binary)
        source=root/'generated.map';source.write_bytes(sample_world().write())
        original=bpy.context.scene;names=set(bpy.data.objects)
        class FakeJob:
            directory=root;active=False
            def info(self):return {'status':'READY','result':str(source),'message':'Map ready','elapsed_seconds':.5}
            def close(self):self.closed=True
        fake=FakeJob();generation._job=fake
        from ruster.mcp_bridge import RusterMCPServer
        server=RusterMCPServer(9877,'test-token-not-used-for-direct-dispatch')
        assert server.dispatch('get_generation_status',{})['status']=='READY'
        try:server.dispatch('generate_map',{'seed':1,'size':1000,'binary':'untrusted'})
        except ValueError as error:assert 'only seed and size' in str(error)
        else:raise AssertionError('MCP accepted an executable override')
        generation.tick()
        assert bpy.context.scene==original and names==set(bpy.data.objects),'Generation completion replaced current project'
        # Opening the result is a separate normal user action, not an async side effect.
        assert bpy.ops.ruster.open(filepath=str(source))=={'FINISHED'}
        assert bpy.context.scene.ruster.mode=='MAP'
        assert any(o.get('ruster_kind')=='TERRAIN' for o in bpy.data.objects)
        ruster.unregister();assert fake.closed
        assert not hasattr(bpy.types.WindowManager,'ruster_generation')
    print('RUSTER_GENERATION_UI_LIFECYCLE_OK',flush=True)


try:run()
except Exception:traceback.print_exc();os._exit(1)
