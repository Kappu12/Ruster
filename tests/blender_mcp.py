"""Typed MCP commands run against real Blender data; no game install needed."""
import base64,gzip,json,os,sys,tempfile,time,traceback
from pathlib import Path
from contextlib import closing
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
if '--' in sys.argv and sys.argv[sys.argv.index('--')+1:]:sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import bpy
import ruster
from ruster import app,scene,editing,placement,protection,mcp_bridge,studio
from ruster.core import settings,prefabs
from ruster.core.terrain import empty_world
from ruster.assets import catalog
from tests.fixtures import triangle_asset


def viewport_capture_restore(server,call):
    """Exercise native viewport/render properties even in a background fixture."""
    from types import SimpleNamespace
    from ruster import mcp_building
    _window,area,_region=mcp_building.viewport()
    overlay=area.spaces.active.overlay;render=bpy.context.scene.render
    original=(overlay.show_overlays,render.image_settings.file_format,
              render.resolution_x,render.resolution_y,render.resolution_percentage)
    real_bpy=mcp_building.bpy;captured=[]
    def capture(**_kwargs):captured.append(overlay.show_overlays)
    fake_render=SimpleNamespace(opengl=capture)
    mcp_building.bpy=SimpleNamespace(app=SimpleNamespace(background=False),context=bpy.context,
        ops=SimpleNamespace(render=fake_render),data=SimpleNamespace(images={
            'Render Result':SimpleNamespace(save_render=lambda path:Path(path).write_bytes(b'fixture PNG'))}))
    def unchanged(expected):
        assert (overlay.show_overlays,render.image_settings.file_format,
                render.resolution_x,render.resolution_y,render.resolution_percentage)==expected
    try:
        render.image_settings.file_format='JPEG'
        render.resolution_x,render.resolution_y,render.resolution_percentage=640,480,50
        overlay.show_overlays=True
        expected=(True,'JPEG',640,480,50)
        call('get_viewport_image');unchanged(expected)
        assert captured==[False]
        overlay.show_overlays=False
        expected=(False,'JPEG',640,480,50)
        call('get_viewport_image',include_overlays=True);unchanged(expected)
        assert captured==[False,True]
        def failed_capture(**_kwargs):raise RuntimeError('Synthetic viewport capture failure')
        fake_render.opengl=failed_capture
        result=server.execute_command({'token':server.token,'type':'get_viewport_image','params':{'include_overlays':True}})
        assert result['status']=='error' and 'Synthetic viewport capture failure' in result['message']
        unchanged(expected)
        result=server.execute_command({'token':server.token,'type':'get_viewport_image','params':{'include_overlays':'false'}})
        assert result['status']=='error' and 'boolean' in result['message']
        unchanged(expected)
    finally:
        mcp_building.bpy=real_bpy
        (overlay.show_overlays,render.image_settings.file_format,
         render.resolution_x,render.resolution_y,render.resolution_percentage)=original


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
        matrix=bpy.data.objects[name].matrix_world.copy()
        call('focus_view',names=[name],axis='OBLIQUE')
        area=next(area for area in bpy.context.window.screen.areas if area.type=='VIEW_3D')
        assert area.spaces.active.region_3d.view_perspective=='PERSP'
        rotation=area.spaces.active.region_3d.view_rotation.copy()
        call('focus_view',names=[name],rotation_degrees=[65,0,25])
        assert area.spaces.active.region_3d.view_rotation.rotation_difference(rotation).angle>.01
        assert bpy.data.objects[name].matrix_world==matrix,'View rotation changed a model'
        for params in ({'rotation_degrees':[0,float('nan'),0]}, {'axis':'TOP','rotation_degrees':[1,2,3]}):
            old_view=area.spaces.active.region_3d.view_rotation.copy()
            failed=server.execute_command({'token':server.token,'type':'focus_view','params':{'names':[name],**params}})
            assert failed['status']=='error' and area.spaces.active.region_3d.view_rotation==old_view
        call('focus_view',names=[name],axis='TOP')
        viewport_capture_restore(server,call)
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
        pivot=bpy.data.objects[group]
        worlds={bpy.data.objects[n]:bpy.data.objects[n].matrix_world.copy() for n in children}
        pivot.location.x+=8;bpy.context.view_layer.update()
        for obj,matrix in worlds.items():obj.matrix_world=matrix
        bpy.context.view_layer.update()
        exported_assembly=call('export_assembly',names=[group],path=str(root/'build.rusterprefab'))
        assert exported_assembly['origin']==list(pivot.matrix_world.translation)
        call('export_prefab',names=[group],path=str(root/'same-pivot.prefab'))
        from ruster.core.rustedit_prefab import RustEditPrefab
        from ruster.core.rust_map import prefab_transform
        _title,assembly_records=prefabs.decode_assembly((root/'build.rusterprefab').read_bytes())
        native_records=RustEditPrefab.load(root/'same-pivot.prefab').prefabs
        assert sorted(prefab_transform(r)[0] for r in assembly_records)==sorted(prefab_transform(r)[0] for r in native_records)
        explicit=call('export_assembly',names=[group],path=str(root/'explicit.rusterprefab'),origin=[9,8,7])
        assert explicit['origin']==[9,8,7]
        mean=call('export_assembly',names=children,path=str(root/'mean.rusterprefab'))
        assert mean['origin']==list(sum((obj.matrix_world.translation for obj in worlds),__import__('mathutils').Vector())/2)
        for origin in ([0,float('nan'),0],[1e300,0,0]):
            failed=server.execute_command({'token':server.token,'type':'export_assembly','params':{'names':[group],'path':str(root/'invalid-origin.rusterprefab'),'origin':origin}})
            assert failed['status']=='error' and not (root/'invalid-origin.rusterprefab').exists()
        assert (root/'build.rusterprefab').is_file()
        imported=call('import_assembly',path=str(root/'build.rusterprefab'),position=[10,10,20],name='Imported Composition')
        assert imported['prefab_count']==2
        assert imported['group']['position']==[10,10,20]
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
        # Assemblies authored within the existing 2000-placement operation
        # budget must reload, including compositions larger than the old 1000 cap.
        from ruster.core import wire
        records=[[wire.encode(2,0,123456)] for _ in range(1001)]
        records[0].append(wire.encode(77,2,b'keep assembly metadata'))
        large=root/'large.rusterprefab';large.write_bytes(prefabs.encode_assembly(records,'Large synthetic assembly'))
        before=len(scene.prefab_roots())
        old_attach=scene.attach_visual
        def no_sync_model(*_args,**_kwargs):raise AssertionError('Assembly imported a model synchronously')
        scene.attach_visual=no_sync_model
        started=time.monotonic()
        try:imported=call('import_assembly',path=str(large),position=[4,5,6])
        finally:scene.attach_visual=old_attach
        print('Synthetic1001 assembly import seconds',round(time.monotonic()-started,3),flush=True)
        assert imported['prefab_count']==1001 and len(scene.prefab_roots())==before+1001
        assert imported['group']['position']==[4,5,6]
        assert any(wire.get(wire.parse(base64.b64decode(obj['ruster_record'])),77)==b'keep assembly metadata'
                   for obj in bpy.data.objects[imported['group']['name']].children)
        assert all(not protection.model_error(obj) for obj in scene.prefab_roots())
        call('delete_objects',names=[imported['group']['name']])
        assert len(scene.prefab_roots())==before
        too_many=root/'too-many.rusterprefab'
        too_many.write_bytes(prefabs.encode_assembly(records*2,'Too many placements'))
        failed=server.execute_command({'token':server.token,'type':'import_assembly','params':{'path':str(too_many),'position':[0,0,0]}})
        assert failed['status']=='error' and '2000' in failed['message']
        assert len(scene.prefab_roots())==before,'Rejected assembly changed the composition'
        # Distinct uncached IDs remain placeholders and do not bypass the
        # existing100-unique asynchronous loading limit.
        distinct_ids=range(5000,5101)
        with closing(catalog.connect(scene.cache_dir())) as db:
            for uid in distinct_ids:
                path=f'assets/test/assembly_{uid}.prefab'
                db.execute('INSERT INTO names VALUES(?,?)',(uid,path))
                db.execute('INSERT INTO assets VALUES(?,?,?,?)',(path,'bundle','file',uid))
            db.commit()
        distinct=root/'distinct.rusterprefab'
        distinct.write_bytes(prefabs.encode_assembly([[wire.encode(2,0,uid)] for uid in distinct_ids]))
        scene.attach_visual=no_sync_model
        try:imported=call('import_assembly',path=str(distinct),position=[0,0,0])
        finally:scene.attach_visual=old_attach
        imported_children=bpy.data.objects[imported['group']['name']].children
        assert len(imported_children)==101 and all(not obj.get('ruster_visual') for obj in imported_children)
        assert app._job is None and not set(distinct_ids)&set(app._visual_queue)
        assert '100 different models' in bpy.context.scene.ruster.asset_status
        call('delete_objects',names=[imported['group']['name']])
        # A grouping failure after creating its root must roll back that root,
        # every placement, and the prior selection without queuing any models.
        before_objects=set(bpy.data.objects);before_selection=set(bpy.context.selected_objects)
        before_active=bpy.context.view_layer.objects.active
        old_group=placement.group
        def failed_group(*args,**kwargs):
            old_group(*args,**kwargs)
            raise RuntimeError('Synthetic grouping failure')
        placement.group=failed_group
        try:failed=server.execute_command({'token':server.token,'type':'import_assembly','params':{'path':str(root/'build.rusterprefab'),'position':[0,0,0]}})
        finally:placement.group=old_group
        assert failed['status']=='error' and 'Synthetic grouping failure' in failed['message']
        assert set(bpy.data.objects)==before_objects and set(bpy.context.selected_objects)==before_selection
        assert bpy.context.view_layer.objects.active==before_active
        # Invalid later records are rejected before even the first root exists.
        invalid=root/'invalid-assembly.rusterprefab'
        invalid.write_bytes(prefabs.encode_assembly([records[0],[wire.encode(2,0,123456),wire.encode(5,2,wire.set_vector(None,(0,1,1)))]]))
        old_root=scene.root_object
        def no_creation(*_args,**_kwargs):raise AssertionError('Created placements before validation')
        scene.root_object=no_creation
        try:failed=server.execute_command({'token':server.token,'type':'import_assembly','params':{'path':str(invalid),'position':[0,0,0]}})
        finally:scene.root_object=old_root
        assert failed['status']=='error' and 'Scale must be nonzero' in failed['message']
        assert set(bpy.data.objects)==before_objects
        # Preview queuing is optional after the placement transaction commits.
        old_request=app.request_missing_visuals
        def failed_queue(_objects):raise OSError('Synthetic queue failure')
        app.request_missing_visuals=failed_queue
        try:imported=call('import_assembly',path=str(root/'build.rusterprefab'),position=[0,0,0])
        finally:app.request_missing_visuals=old_request
        assert imported['prefab_count']==2 and 'Synthetic queue failure' in bpy.context.scene.ruster.asset_status
        call('delete_objects',names=[imported['group']['name']])
        ruster.unregister()
    print('RUSTER_BLENDER_MCP_TYPED_COMMANDS_OK',flush=True)


try:run()
except Exception:traceback.print_exc();os._exit(1)
