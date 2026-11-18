"""Native ground preserves a composition and survives paint, save and reload."""
import os
import sys
import tempfile
import traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
if '--' in sys.argv and sys.argv[sys.argv.index('--')+1:]:sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import bpy
import numpy as np
import ruster
from ruster import app,scene,studio,ground,editing,map_prefabs,mcp_bridge,live_preview
from ruster.core import wire,project,rustedit_terrain
from ruster.core.rustedit_prefab import RustEditPrefab
from ruster.core.rust_map import RustMap
from ruster.core.ground import validate_ground


def run():
    with tempfile.TemporaryDirectory(prefix='ruster-ground-') as tmp:
        root=Path(tmp);os.environ['RUSTER_USER_DIR']=str(root/'user')
        ruster.register();studio.new_prefab()
        fields=[wire.encode(1,2,b'Decor'),wire.encode(2,0,123456)]
        obj=scene.root_object(fields,bpy.data.collections['Prefabs']);obj.location=(3,4,0)
        bpy.context.view_layer.update();matrix=obj.matrix_world.copy()
        server=mcp_bridge.RusterMCPServer(9877,'fixture-token')
        result=server.dispatch('add_ground',{'size':384,'height':0,'biome':'Jungle','splat':'Forest'})
        assert result['present'] and result['biome_channels_stored']==5
        assert bpy.ops.ruster.export_map.poll()
        assert (obj.matrix_world.translation-matrix.translation).length<1e-6
        assert len(scene.prefab_roots())==1
        assert len([o for o in bpy.context.scene.objects if o.get('ruster_kind')=='TERRAIN'])==1
        before=list(bpy.context.scene.objects)
        try:ground.add()
        except ValueError:pass
        else:raise AssertionError('Duplicate native ground replaced the scene')
        assert list(bpy.context.scene.objects)==before
        baseline=editing.terrain().snapshot()
        server.dispatch('paint_ground',{'layer':'biome','center':[0,0],'radius':20,'channel':'Temperate','strength':1})
        assert editing.terrain().grid('biome')[1,256,256]==255
        assert baseline!=editing.terrain().snapshot()
        server.dispatch('paint_ground',{'layer':'splat','center':[0,0],'radius':12,'channel':'Dirt','strength':.8})
        assert editing.terrain().grid('splat')[0,256,256]>190
        edited=editing.terrain().snapshot()
        output=map_prefabs.export_map(root/'ground.map')
        world=RustMap.load(output);validate_ground(world)
        assert len(world.prefabs)==1 and 'terrain' in world.layers
        assert not map_prefabs.validate()[0]
        # The normal export command includes painted masks in a native map.
        prefab=root/'ground.prefab'
        assert bpy.ops.ruster.prefab_export(filepath=str(prefab))=={'FINISHED'}
        assert len(RustEditPrefab.load(prefab).prefabs)==1
        companions=rustedit_terrain.read_companions(prefab)
        assert set(companions)==set(rustedit_terrain.TERRAIN_SUFFIXES)
        thumbnail=root/'thumbnail.png';thumbnail.write_bytes(companions['.biome'])
        mcp_prefab=root/'mcp-ground.prefab'
        exported=server.dispatch('export_prefab',{'path':str(mcp_prefab),'names':[obj.name],
                                                   'preview_png':str(thumbnail)})
        assert len(exported['companions'])==7
        assert rustedit_terrain.read_companions(mcp_prefab)==dict(companions,**{'.png':thumbnail.read_bytes()})
        result=server.dispatch('export_prefab',{'path':str(prefab),'names':[obj.name],
                                               'include_terrain':False,'overwrite':True})
        assert not result['companions'] and not rustedit_terrain.read_companions(prefab)
        extra=bpy.data.objects.new('Unrelated custom mesh',bpy.data.meshes.new('Custom mesh'))
        bpy.context.scene.collection.objects.link(extra)
        assert any('custom objects' in error for error in map_prefabs.validate()[0])
        bpy.data.objects.remove(extra,do_unlink=True)
        app.save_project(root/'ground.ruster')
        manifest=project.unpack(root/'ground.ruster',root/'unpacked')
        assert manifest['mode']=='MAP' and 'source.map' in manifest['files']
        app.open_path(root/'ground.ruster')
        assert ground.enabled() and editing.terrain().snapshot()==edited
        assert Path(bpy.context.scene.ruster.source_map).is_file()
        assert not map_prefabs.validate()[0]
        assert len(scene.prefab_roots())==1
        assert ground.status()['size']==384
        # Source/snapshot changes require a restart of the native server map.
        class Job:
            active=True
        previous=live_preview._job
        live_preview._job=Job();live_preview._ground_state=live_preview.ground_state()
        assert not live_preview.ground_changed()
        ground.paint('splat',[0,0],10,'Grass',.5)
        assert live_preview.ground_changed()
        live_preview._job=previous
        studio.new_prefab()
        assert not ground.enabled() and not bpy.context.scene.ruster.source_map
        studio.import_prefab(mcp_prefab)
        app.save_project(root/'imported.ruster');app.open_path(root/'imported.ruster')
        saved=root/'saved-prefab.prefab';studio.export_prefab(saved)
        assert saved.read_bytes()==mcp_prefab.read_bytes()
        assert rustedit_terrain.read_companions(saved)==rustedit_terrain.read_companions(mcp_prefab)
        ruster.unregister()
    print('RUSTER_NATIVE_GROUND_OK',flush=True)


try:run()
except Exception:traceback.print_exc();os._exit(1)
