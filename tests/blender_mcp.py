"""Typed MCP commands run against real Blender data; no game install needed."""
import gzip,json,os,sys,tempfile,traceback
from pathlib import Path
from contextlib import closing
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
if '--' in sys.argv and sys.argv[sys.argv.index('--')+1:]:sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import bpy
import ruster
from ruster import app,scene,editing,placement,protection,mcp_bridge,studio
from ruster.core import settings
from ruster.core.terrain import empty_world
from ruster.assets import catalog
from tests.fixtures import triangle_asset


def run():
    with tempfile.TemporaryDirectory(prefix='ruster-mcp-') as temp:
        root=Path(temp);os.environ['RUSTER_USER_DIR']=str(root/'user')
        ruster.register()
        assert not mcp_bridge.running() and not bpy.context.window_manager.ruster_mcp.enabled
        source=root/'base.map';source.write_bytes(empty_world(100,20).write())
        bpy.context.preferences.edit.use_global_undo=True
        studio.new_prefab()
        bpy.ops.ed.undo_push(message='MCP test initial composition')
        cache=scene.cache_dir()/'prefabs';cache.mkdir(parents=True,exist_ok=True)
        asset=triangle_asset(123456);path=asset['path']
        with closing(catalog.connect(scene.cache_dir())) as db:
            db.execute('INSERT OR REPLACE INTO names VALUES(?,?)',(123456,path))
            db.execute('INSERT OR REPLACE INTO assets VALUES(?,?,?,?)',(path,'bundle','file',123456));db.commit()
        (cache/'123456.json.gz').write_bytes(gzip.compress(json.dumps(asset).encode()))
        server=mcp_bridge.RusterMCPServer(9877,'test-token-123456789012345678901234567890')
        def call(rpc_kind,**params):
            result=server.execute_command({'token':server.token,'type':rpc_kind,'params':params})
            assert result['status']=='success',result
            return result['result']
        assert server.execute_command({'type':'place_prefab','params':{}})['status']=='error'
        assert server.execute_command({'token':server.token,'type':'execute_code','params':{'code':'raise Exception()'}})['status']=='error'
        assert call('search_prefabs',query='') ['prefabs'][0]['id']==123456
        assert call('search_prefabs',query='')['next_offset'] is None
        assert call('get_editor_status')['catalog_ready']
        assert call('list_prefab_categories')['total_prefabs']==1
        details=call('get_prefab_details',uid=123456)
        assert details['cached'] and details['local_bounds']['dimensions']==[2,1,2] and details['triangle_count']==1
        # The current converter stores mesh counts in JSON and coordinates in RMS1.
        from ruster.assets import geometry
        spec=asset['meshes']['mesh'];buffer=cache/'meshes/triangle.mesh.gz'
        asset['meshes']['mesh']=geometry.write(buffer,spec['vertices'],[],spec['submeshes'])
        asset['meshes']['mesh']['buffer']='meshes/triangle.mesh.gz'
        (cache/'123456.json.gz').write_bytes(gzip.compress(json.dumps(asset).encode()))
        binary_details=call('get_prefab_details',uid=123456)
        assert binary_details['local_bounds']==details['local_bounds'] and binary_details['triangle_count']==1
        placed=call('place_prefab',uid=123456,position=[1,2,25],rotation_degrees=[0,0,45],scale=[2,2,2]);name=placed['name']
        assert placed['geometry_read_only'] and abs(placed['rotation_degrees'][2]-45)<.001
        assert not protection.model_error(bpy.data.objects[name])
        call('undo');assert len(scene.prefab_roots())==0
        call('redo');assert len(scene.prefab_roots())==1
        call('transform_object',name=name,position=[10,20,30],rotation_degrees=[0,0,90],scale=[2,3,4])
        assert tuple(round(v,3) for v in bpy.data.objects[name].location)==(10,20,30)
        before=bpy.data.objects[name].matrix_world.copy()
        failed=server.execute_command({'token':server.token,'type':'transform_object','params':{'name':name,'scale':[0,1,1]}})
        assert failed['status']=='error' and bpy.data.objects[name].matrix_world==before
        failed=server.execute_command({'token':server.token,'type':'transform_object','params':{'name':name,'position':[1e300,0,0]}})
        assert failed['status']=='error' and bpy.data.objects[name].matrix_world==before
        assert server.execute_command({'token':server.token,'type':'paint_terrain','params':{}})['status']=='error'
        assert all(abs(a-b)<1e-5 for a,b in zip(call('get_object_info',name=name)['world_scale'],[2,3,4]))
        count=len(scene.prefab_roots())
        failed=server.execute_command({'token':server.token,'type':'place_prefabs','params':{'placements':[{'uid':123456,'position':[0,0,20]},{'uid':99,'position':[0,0,20]}]}})
        assert failed['status']=='error' and len(scene.prefab_roots())==count,'Partial composition leaked'
        batch=call('place_prefabs',placements=[{'uid':123456,'position':[0,0,20]},{'uid':123456,'position':[3,0,20]}],group_name='Test Composition')
        group=batch['group']['name'];children=[o['name'] for o in batch['objects']]
        assert batch['group']['kind']=='GROUP' and len(batch['group']['children'])==2
        assert batch['group']['world_bounds']['dimensions'][0]>=5
        old=[bpy.data.objects[n].matrix_world.copy() for n in children]
        failed=server.execute_command({'token':server.token,'type':'transform_objects','params':{'transforms':[{'name':children[0],'position':[9,0,20]},{'name':children[1],'scale':[0,1,1]}]}})
        assert failed['status']=='error' and all(bpy.data.objects[n].matrix_world==m for n,m in zip(children,old)),'Batch transforms did not roll back'
        call('transform_objects',transforms=[{'name':group,'position':[1,1,21],'scale':[2,2,2]}])
        call('rename_object',name=group,new_name='AI Composition');group='AI Composition'
        call('snap_objects_to_plane',names=[group],target=2)
        assert abs(call('get_object_info',name=group)['world_bounds']['min'][2]-2)<.001
        assert call('list_map_objects',query='AI Composition',kind='GROUP')['total']==1
        assert call('list_map_objects',prefab_id=123456)['total']==3
        call('export_assembly',names=[group],path=str(root/'build.rusterprefab'))
        assert (root/'build.rusterprefab').is_file()
        imported=call('import_assembly',path=str(root/'build.rusterprefab'),position=[10,10,20],name='Imported Composition')
        assert imported['prefab_count']==2
        call('delete_object',name=imported['group']['name'])
        call('ungroup_object',name=group)
        assert not bpy.data.objects.get(group)
        regrouped=call('group_objects',names=children,name='Rebuilt')['name']
        call('delete_object',name=regrouped)
        assert not protection.model_error(bpy.data.objects[name])
        assert not call('validate_map')['errors']
        target=root/'out.map';call('export_map',path=str(target));assert target.is_file()
        from ruster.core.rust_map import RustMap
        exported=RustMap.load(target);assert not exported.layers and not exported.paths and len(exported.prefabs)==1
        assert call('import_map_prefabs',path=str(target))['prefab_count']==1
        assert len(scene.prefab_roots())==2
        assert server.execute_command({'token':server.token,'type':'export_map','params':{'path':str(target)}})['status']=='error'
        # Batch inspection remains bounded, and selection survives export success/failure.
        call('select_objects',names=[name]);selection=[o.name for o in bpy.context.selected_objects]
        assert call('get_selection')['total']==1
        assert len(call('get_objects_info',names=[name])['objects'])==1
        assert len(call('get_prefabs_details',uids=[123456])['prefabs'])==1
        assert call('list_objects')['objects'][0]['world_bounds'] is None
        assert 'GLB' in {f['id'] for f in call('get_export_formats')['formats']}
        before_names={o.name for o in bpy.context.scene.objects}
        repeated=call('array_objects',names=[name],count=3,offset=[5,0,0],rotation_degrees=[0,0,15])
        assert repeated['new_prefab_count']==3 and len(repeated['objects'])==3
        assert [o.name for o in bpy.context.selected_objects]==selection
        matrices={n:bpy.data.objects[n].matrix_world.copy() for n in before_names}
        assert server.execute_command({'token':server.token,'type':'array_objects','params':{'names':[name],'count':2001,'offset':[1,0,0]}})['status']=='error'
        assert server.execute_command({'token':server.token,'type':'array_objects','params':{'names':[name],'count':2,'offset':[1e300,0,0]}})['status']=='error'
        assert {o.name for o in bpy.context.scene.objects}==before_names|set(repeated['objects'])
        assert all(bpy.data.objects[n].matrix_world==m for n,m in matrices.items())
        call('align_objects',names=repeated['objects'],axis='X',mode='MAX',target=15)
        assert all(abs(call('get_object_info',name=n)['world_bounds']['max'][0]-15)<.001 for n in repeated['objects'])
        nested=call('group_objects',names=repeated['objects'][:2],name='Reject overlapping batch')['name']
        assert server.execute_command({'token':server.token,'type':'delete_objects','params':{'names':[nested,repeated['objects'][0]]}})['status']=='error'
        assert bpy.data.objects.get(nested) and bpy.data.objects.get(repeated['objects'][0])
        call('delete_objects',names=[nested,repeated['objects'][2]])
        assert len(scene.prefab_roots())==2
        call('select_objects',names=[name]);selection=[o.name for o in bpy.context.selected_objects]
        call('export_prefab',names=[name],path=str(root/'native.prefab'))
        assert [o.name for o in bpy.context.selected_objects]==selection
        assert server.execute_command({'token':server.token,'type':'export_prefab','params':{'names':[name],'path':str(root/'native.prefab')}})['status']=='error'
        assert [o.name for o in bpy.context.selected_objects]==selection
        call('export_models',names=[name],path=str(root/'model.glb'),format='GLB')
        assert (root/'model.glb').is_file() and [o.name for o in bpy.context.selected_objects]==selection
        # Rotated nested groups duplicate world transforms and stay linked/read-only.
        composition=call('place_prefabs',placements=[{'uid':123456,'position':[0,0,0]},{'uid':123456,'position':[3,4,0]}],group_name='Array source')
        array_source=composition['group']['name']
        call('transform_object',name=array_source,rotation_degrees=[0,0,40],scale=[2,2,2])
        source_children=call('get_object_info',name=array_source)['children']
        source_positions=[bpy.data.objects[n].matrix_world.translation.copy() for n in source_children]
        group_copies=call('duplicate_objects',names=[array_source],offset=[7,8,9])
        group_copy=group_copies['objects'][0]
        copy_positions=[bpy.data.objects[n].matrix_world.translation.copy() for n in call('get_object_info',name=group_copy)['children']]
        assert all(any((a+__import__('mathutils').Vector((7,8,9))-b).length<.001 for b in copy_positions) for a in source_positions),(source_positions,copy_positions)
        assert all(not protection.model_error(bpy.data.objects[n]) for n in call('get_object_info',name=group_copy)['children'])
        bpy.data.objects[array_source].scale=[2,1,1]
        bpy.data.objects[source_children[0]].rotation_euler.z=.5
        bpy.context.view_layer.update();existing_names={obj.name for obj in bpy.context.scene.objects}
        rejected=server.execute_command({'token':server.token,'type':'duplicate_objects','params':{'names':[array_source]}})
        assert rejected['status']=='error' and {obj.name for obj in bpy.context.scene.objects}==existing_names
        call('delete_objects',names=[array_source,group_copy])
        call('select_objects',names=[name])
        # Companion-file conflicts and partial exporter failures preserve files/scene.
        from ruster import model_export
        original_export=model_export.export_models
        original_scene=bpy.context.scene
        try:
            def sidecar_export(destination,_format,_roots):
                destination.write_bytes(b'new model');destination.with_suffix('.bin').write_bytes(b'new buffer');return destination
            model_export.export_models=sidecar_export
            (root/'blocked.bin').write_bytes(b'existing buffer')
            failed=server.execute_command({'token':server.token,'type':'export_models','params':{'names':[name],'path':str(root/'blocked.gltf'),'format':'GLTF'}})
            assert failed['status']=='error' and not (root/'blocked.gltf').exists()
            assert (root/'blocked.bin').read_bytes()==b'existing buffer'
            (root/'folder.bin').mkdir();(root/'folder.bin'/'keep').write_bytes(b'user data')
            failed=server.execute_command({'token':server.token,'type':'export_models','params':{'names':[name],'path':str(root/'folder.gltf'),'format':'GLTF','overwrite':True}})
            assert failed['status']=='error' and not (root/'folder.gltf').exists()
            assert (root/'folder.bin'/'keep').read_bytes()==b'user data'
            def failed_export(destination,_format,_roots):
                destination.write_bytes(b'incomplete model');raise ValueError('Synthetic exporter failure')
            model_export.export_models=failed_export
            (root/'preserve.glb').write_bytes(b'existing model')
            failed=server.execute_command({'token':server.token,'type':'export_models','params':{'names':[name],'path':str(root/'preserve.glb'),'format':'GLB','overwrite':True}})
            assert failed['status']=='error' and (root/'preserve.glb').read_bytes()==b'existing model'
            assert bpy.context.scene==original_scene and [o.name for o in bpy.context.selected_objects]==selection
        finally:model_export.export_models=original_export
        native=call('import_prefab',path=str(root/'native.prefab'),position=[100,0,0])
        assert native['prefab_count']==1
        call('delete_objects',names=[native['group']['name']])
        # Imported RustEdit IO fields are typed scalar edits, retaining unknown data.
        from ruster.core import wire
        from ruster.core.rustedit_prefab import RustEditPrefab
        record=placement.world_record(bpy.data.objects[name])
        native_data=RustEditPrefab.create([record])
        from ruster.core.rust_map import prefab_transform
        entity=[wire.encode(2,2,wire.set_vector(None,prefab_transform(record)[0])),wire.encode(8,0,1234),wire.encode(99,2,b'keep IO extension')]
        native_data.fields=wire.replace(native_data.fields,5,2,wire.serialize([wire.encode(1,2,wire.serialize(entity))]))
        (root/'io.prefab').write_bytes(native_data.write())
        imported_io=call('import_prefab',path=str(root/'io.prefab'))
        io_child=imported_io['group']['children'][0]
        assert call('get_io_settings',name=io_child)['settings']['frequency']==1234
        assert call('set_io_settings',name=io_child,settings={'frequency':5678,'phone_name':'MCP test'})['settings']['frequency']==5678
        assert server.execute_command({'token':server.token,'type':'set_io_settings','params':{'name':io_child,'settings':{'frequency':-1}}})['status']=='error'
        assert call('get_io_settings',name=io_child)['settings']['frequency']==5678
        clone=call('duplicate_objects',names=[imported_io['group']['name']],offset=[10,0,0])
        copied_root=clone['objects'][0];copied_child=call('get_object_info',name=copied_root)['children'][0]
        call('set_io_settings',name=copied_child,settings={'frequency':9999})
        assert call('get_io_settings',name=io_child)['settings']['frequency']==5678
        assert call('get_io_settings',name=copied_child)['settings']['frequency']==9999
        call('delete_objects',names=[copied_root])
        call('export_prefab',names=[imported_io['group']['name']],path=str(root/'io-out.prefab'))
        assert b'keep IO extension' in wire.serialize(RustEditPrefab.load(root/'io-out.prefab').fields)
        call('delete_objects',names=[imported_io['group']['name']])
        call('save_project',path=str(root/'out.ruster'))
        assert not settings.load().get('mcp_enabled',False),'Project saving enabled MCP'
        with closing(catalog.connect(scene.cache_dir())) as db:
            db.executemany('INSERT INTO names VALUES(?,?)',[(i,f'assets/prefabs/discovery/part_{i}.prefab') for i in range(200,405)]);db.commit()
        seen=[];offset=0
        while True:
            page=call('search_prefabs',category='assets/prefabs/discovery',limit=100,offset=offset)
            seen.extend(p['id'] for p in page['prefabs'])
            if page['next_offset'] is None:break
            offset=page['next_offset']
        assert len(seen)==205 and len(set(seen))==205,'Catalog pagination omitted or repeated assets'
        assert len(call('search_prefabs',query='part_20')['prefabs'])==10
        assert len(call('search_prefabs',available_only=True)['prefabs'])==1
        previous=app.start_job
        def failed_worker(*_args,**_kwargs):raise ValueError('Test worker could not start')
        try:
            app.start_job=failed_worker
            failure=server.execute_command({'token':server.token,'type':'request_prefab_assets','params':{'uids':[123456]}})
            assert failure['status']=='error' and 'could not start' in failure['message']
            assert 123456 not in app._pending_asset_ids
            status=call('get_editor_status');assert status['queued_prefabs']==0
        finally:
            app.start_job=previous;app._pending_asset_ids.clear()
        app._visual_queue.append(name)
        try:assert call('get_editor_status')['busy'] and call('get_editor_status')['pending_visuals']>0
        finally:app._visual_queue.clear()
        ruster.unregister()
    print('RUSTER_BLENDER_MCP_TYPED_COMMANDS_OK',flush=True)


try:run()
except Exception:traceback.print_exc();os._exit(1)
