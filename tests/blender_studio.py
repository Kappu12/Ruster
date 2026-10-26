"""Prefab composition, native interchange and real model exporters; no game assets."""
import base64
import gzip
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
if '--' in sys.argv and sys.argv[sys.argv.index('--')+1:]:
    sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
from ruster.core.process_limits import protect_process, EDITOR_MEMORY
protect_process(EDITOR_MEMORY)
import bpy
from mathutils import Vector
import ruster
from ruster import app, scene, placement, studio, model_export
from ruster.assets import catalog
from ruster.core import wire
from ruster.core.rustedit_prefab import RustEditPrefab
from tests.fixtures import sample_world, triangle_asset


def run():
    with tempfile.TemporaryDirectory(prefix='ruster-studio-') as tmp:
        directory=Path(tmp);os.environ['RUSTER_USER_DIR']=str(directory/'user')
        ruster.register();studio.new_prefab()
        assert bpy.context.scene.ruster.mode=='PREFAB' and not list(bpy.context.scene.objects)
        records=sample_world().prefabs
        # Large nonuniform scales and 315-degree rotations must retain original
        # wire bytes despite float32 matrix decomposition noise.
        from ruster.core.rust_map import update_transform
        records[0]=update_transform(records[0],(.123,30.76397,-.43124),(0,315,0),(139.6563,1.05814,57.85211))
        native=RustEditPrefab.create(records)
        source=directory/'original.prefab';source.write_bytes(native.write())
        bpy.context.scene.cursor.location=(12,34,56)
        group=studio.import_prefab(source)
        assert len(scene.prefab_roots())==2
        target=directory/'unchanged.prefab';studio.export_prefab(target)
        assert target.read_bytes()==source.read_bytes(),'Unchanged prefab did not retain its exact bytes'
        first=scene.prefab_roots()[0];first.location.x+=7
        studio.export_prefab(directory/'changed.prefab')
        edited=RustEditPrefab.load(directory/'changed.prefab')
        assert edited.write()!=source.read_bytes()
        assert wire.get(edited.prefabs[0],47)==b'unknown prefab extension'
        if os.environ.get('RUSTER_INTEROP_OUT'):
            Path(os.environ['RUSTER_INTEROP_OUT']).write_bytes(edited.write())
        # Project save/reopen must retain native metadata and group pivot.
        app.save_project(directory/'studio.ruster');app.open_path(directory/'studio.ruster')
        assert bpy.context.scene.ruster.mode=='PREFAB'
        group=next(o for o in bpy.context.scene.objects if o.get('ruster_prefab_source'))
        placement.select([group]);studio.export_prefab(directory/'reopened.prefab')
        assert RustEditPrefab.load(directory/'reopened.prefab').prefabs==edited.prefabs
        # The document export button falls back to the whole composition when
        # nothing is highlighted. An explicit selection still limits the file.
        placement.select([])
        assert bpy.ops.ruster.prefab_export(filepath=str(directory/'all-unselected.prefab'))=={'FINISHED'}
        assert RustEditPrefab.load(directory/'all-unselected.prefab').prefabs==edited.prefabs
        placement.select([scene.prefab_roots()[0]])
        with bpy.context.temp_override(selected_objects=[],active_object=None,object=None):
            assert bpy.ops.ruster.prefab_export(filepath=str(directory/'one-selected.prefab'))=={'FINISHED'}
        assert len(RustEditPrefab.load(directory/'one-selected.prefab').prefabs)==1
        placement.select([group])
        first=scene.prefab_roots()[0]
        cache=scene.cache_dir()/'prefabs';cache.mkdir(parents=True,exist_ok=True)
        uid=int(first['ruster_uid'])
        (cache/'textures').mkdir()
        image=bpy.data.images.new('Test export texture',2,2)
        image.pixels[:]=[.2,.5,.8,1]*4
        image.filepath_raw=str(cache/'textures/test.png');image.file_format='PNG';image.save()
        bpy.data.images.remove(image)
        asset=triangle_asset(uid);asset['materials']['mat']['texture']='textures/test.png'
        (cache/f'{uid}.json.gz').write_bytes(gzip.compress(json.dumps(asset).encode()))
        assert scene.attach_visual(first)
        placement.select([first]);bpy.context.view_layer.update()
        original_scene=bpy.context.scene
        original_mesh=first.instance_collection.objects[0].data
        counts=(len(bpy.data.scenes),len(bpy.data.objects),len(bpy.data.meshes))
        expected=first.matrix_world.translation.copy()
        with model_export.realized_scene([first]) as temporary:
            assert len(temporary.objects)==1
            assert (temporary.objects[0].matrix_world.translation-expected).length<1e-5
            assert temporary.objects[0].data!=original_mesh
        formats=[item[0] for item in model_export.available_formats()]
        assert {'GLB','GLTF','FBX','OBJ','PLY','STL','USD','USDA','USDC','ABC','BLEND'}<=set(formats)
        for format_ in formats:
            path=model_export.export_models(directory/('model-'+format_),format_,[first])
            assert path.stat().st_size>0
            if format_=='OBJ':
                material_text=path.with_suffix('.mtl').read_text()
                texture_paths=[line.partition(' ')[2] for line in material_text.splitlines() if line.startswith('map_Kd ')]
                assert texture_paths and all((path.parent/name).is_file() for name in texture_paths),material_text
            assert bpy.context.scene==original_scene
            assert counts==(len(bpy.data.scenes),len(bpy.data.objects),len(bpy.data.meshes)),format_+' leaked data'
        # The direct menu export defaults to the whole composition and offers
        # selected-only export. Opening the result needs no Ruster/cache/addon.
        assert not bpy.ops.ruster.blend_export.get_rna_type().properties['selected_only'].default
        selected_before = [obj.name for obj in bpy.context.selected_objects]
        target = directory/'direct.blend'
        assert bpy.ops.ruster.blend_export(filepath=str(target), selected_only=True) == {'FINISHED'}
        assert [obj.name for obj in bpy.context.selected_objects] == selected_before
        assert bpy.context.scene == original_scene
        assert counts==(len(bpy.data.scenes),len(bpy.data.objects),len(bpy.data.meshes))
        completed = subprocess.run([bpy.app.binary_path, '-b', '-t', '2', '--factory-startup', '--disable-autoexec',
            str(target), '--python-exit-code', '1', '--python', str(ROOT/'tests/blender_open_export.py'),
            '--', str(directory/'render.png')], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='replace', creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0), timeout=90)
        assert completed.returncode==0, completed.stdout
        assert 'RUSTER_EXPORTED_BLEND_OPENS_AND_RENDERS_OK' in completed.stdout, completed.stdout
        assert 'Library file, loading empty scene' not in completed.stdout
        # A failed isolated save must preserve an existing destination and source.
        original_run = model_export.subprocess.run
        target.write_bytes(b'preserve destination')
        def failed_save(*args, **kwargs):raise RuntimeError('Synthetic Blender save failure')
        model_export.subprocess.run = failed_save
        try:
            try:model_export.export_models(target, 'BLEND', [first])
            except RuntimeError as error:assert 'Synthetic Blender save failure' in str(error)
            else:raise AssertionError('Expected export failure')
        finally:model_export.subprocess.run = original_run
        assert target.read_bytes()==b'preserve destination' and bpy.context.scene==original_scene
        assert counts==(len(bpy.data.scenes),len(bpy.data.objects),len(bpy.data.meshes))
        with bpy.data.libraries.load(str(directory/'model-BLEND.blend'),link=False) as (source_, destination):
            destination.scenes=list(source_.scenes)
        library_scene=destination.scenes[0]
        for obj in library_scene.objects:
            assert obj.data.library is None
            for slot in obj.material_slots:
                assert slot.material.library is None,'Model library still depends on the private asset cache'
                if slot.material.use_nodes:
                    for node in slot.material.node_tree.nodes:
                        if node.type=='TEX_IMAGE' and node.image:
                            assert node.image.library is None and node.image.packed_file
        # Remove the test import as well as its local dependencies.
        imported_objects=list(library_scene.objects)
        imported_meshes={obj.data for obj in imported_objects}
        imported_materials={slot.material for obj in imported_objects for slot in obj.material_slots if slot.material}
        bpy.data.batch_remove(ids=[library_scene,*imported_objects,*imported_meshes,*imported_materials])
        assert original_mesh.library and not original_mesh.is_editable
        # Search reads only catalog metadata, including broad categories.
        from contextlib import closing
        with closing(catalog.connect(scene.cache_dir())) as db:
            db.executemany('INSERT INTO names VALUES(?,?)',[
                (42,'assets/bundled/prefabs/autospawn/monument/large/harbor.prefab'),
                (43,'assets/bundled/prefabs/autospawn/resource/trees/oak.prefab')])
            db.execute('INSERT INTO assets VALUES(?,?,?,?)',('assets/bundled/prefabs/autospawn/monument/large/harbor.prefab','bundle','file',1))
            db.commit()
        class Search:category='@MONUMENTS'
        assert [item[0] for item in studio.search_items(Search(),None)]==['42']
        # Exporter failure still releases its temporary scene and mesh copies.
        try:
            with model_export.realized_scene([first]):raise RuntimeError('synthetic failure')
        except RuntimeError:pass
        assert bpy.context.scene==original_scene
        assert counts==(len(bpy.data.scenes),len(bpy.data.objects),len(bpy.data.meshes))
        # Native per-entity settings retain opaque fields and survive movements.
        studio.new_prefab()
        native=RustEditPrefab.create(records)
        from ruster.core.rust_map import prefab_transform
        entity=[wire.encode(1,2,b'assets/test/io.prefab'),
                wire.encode(2,2,wire.set_vector(None,prefab_transform(records[0])[0])),
                wire.encode(99,2,b'future IO data')]
        native.fields=wire.replace(native.fields,5,2,wire.serialize([wire.encode(1,2,wire.serialize(entity))]))
        source.write_bytes(native.write());group=studio.import_prefab(source)
        first=next(o for o in scene.prefab_roots() if o['ruster_prefab_index']==0)
        placement.select([first])
        assert bpy.ops.ruster.io_settings(timer_length=30,frequency=42,door_effect=-1)=={'FINISHED'}
        found=studio.io_source(first)
        assert studio.io_value(found[-1],'timer_length')==30
        assert studio.io_value(found[-1],'door_effect')==-1
        assert wire.get(found[-1],99)==b'future IO data'
        first.location.x+=3;placement.select([group]);studio.export_prefab(directory/'io.prefab')
        result=RustEditPrefab.load(directory/'io.prefab')
        io=wire.parse(wire.get(wire.parse(wire.get(result.fields,5)),1))
        assert studio.io_value(io,'frequency')==42
        assert wire.get(io,99)==b'future IO data'
        assert abs(wire.vector(wire.get(io,2))[0]-prefab_transform(records[0])[0][0]-3)<1e-5
        from ruster.mcp_bridge import RusterMCPServer
        server=RusterMCPServer(0,'synthetic-token')
        result=server.dispatch('transform_object',{'name':first.name,'position':[1,2,3]})
        assert result['position']==[1,2,3]
        result=server.dispatch('rename_object',{'name':first.name,'new_name':'IO test placement'})
        assert bpy.data.objects.get('IO test placement')
        try:server.dispatch('paint_terrain',{'layer':'terrain'})
        except ValueError as error:assert 'Unsupported' in str(error)
        else:raise AssertionError('Terrain operation was allowed without a map')
        ruster.unregister()
    print('RUSTER_BLENDER_STUDIO_EXPORTS_OK',flush=True)


try:run()
except Exception:
    import traceback
    traceback.print_exc();os._exit(1)
