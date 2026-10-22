"""Native read-only model data, export guards, offline packing and repair."""
import gzip,json,os,shutil,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
if '--' in sys.argv and sys.argv[sys.argv.index('--')+1:]:sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import bpy
import ruster
from ruster import app,scene,placement,protection,editing
from tests.fixtures import sample_world,triangle_asset


def run():
    with tempfile.TemporaryDirectory(prefix='ruster-protected-') as tmp:
        root=Path(tmp);os.environ['RUSTER_USER_DIR']=str(root/'user')
        ruster.register()
        source=root/'source.map';source.write_bytes(sample_world().write());app.open_path(source)
        prefab=scene.prefab_roots()[0];uid=int(prefab['ruster_uid'])
        cache=scene.cache_dir()/'prefabs';cache.mkdir(parents=True)
        texture_dir=cache/'textures';texture_dir.mkdir()
        image=bpy.data.images.new('Original test texture',2,2)
        image.pixels[:]=[.2,.5,.8,1]*4
        image.filepath_raw=str(texture_dir/'test.png');image.file_format='PNG';image.save()
        bpy.data.images.remove(image)
        asset=triangle_asset(uid);asset['materials']['mat']['texture']='textures/test.png'
        (cache/f'{uid}.json.gz').write_bytes(gzip.compress(json.dumps(asset).encode()))
        assert scene.attach_visual(prefab)
        library=prefab.instance_collection.library
        visual=prefab.instance_collection.objects[0]
        assert library and not prefab.instance_collection.is_editable
        assert not visual.is_editable and not visual.data.is_editable
        # Blender's own native geometry operators must reject the linked source.
        with bpy.context.temp_override(object=visual,active_object=visual,selected_objects=[visual],selected_editable_objects=[]):
            assert not bpy.ops.object.modifier_add.poll(),'Native modifiers can edit the prefab model'
            assert not bpy.ops.object.mode_set.poll(),'Native mesh/sculpt modes can edit the prefab model'
        placement.select([prefab])
        try:result=bpy.ops.object.mode_set(mode='EDIT')
        except (RuntimeError,TypeError):result={'CANCELLED'}
        assert result!={'FINISHED'} and prefab.mode=='OBJECT','A placement handle entered mesh edit mode'
        assert bpy.ops.ruster.duplicate()=={'FINISHED'}
        duplicate=bpy.context.object
        assert duplicate.instance_collection==prefab.instance_collection
        duplicate.location.x+=10
        assert not scene.validate()[0]
        # Terrain holes affect terrain only, never the model's topology.
        vertices=len(visual.data.vertices);faces=len(visual.data.polygons)
        brush=bpy.context.scene.ruster_brush;brush.layer='alpha';brush.remove=True;brush.radius=100
        assert bpy.ops.ruster.terrain_apply()=={'FINISHED'}
        assert (len(visual.data.vertices),len(visual.data.polygons))==(vertices,faces)
        # Exercise cross-drive packing even on Linux by making the source path
        # non-relative; staging must work and leave cwd/library references intact.
        previous_cwd=Path.cwd();absolute=str(Path(bpy.path.abspath(library.filepath)).resolve())
        native_relpath=bpy.path.relpath
        bpy.path.relpath=lambda path,*args,**kwargs: absolute if str(path)==absolute else native_relpath(path,*args,**kwargs)
        try:protection.pack_models()
        finally:bpy.path.relpath=native_relpath
        assert library.packed_file and Path.cwd()==previous_cwd
        assert library.filepath==absolute
        # Make-local/override-style data must be rejected, including after reopen.
        editable=prefab.instance_collection.copy()
        prefab.instance_collection=editable
        assert protection.model_error(prefab)
        assert any('read-only' in e for e in scene.validate()[0])
        try:scene.export_map(root/'invalid.map')
        except ValueError:pass
        else:raise AssertionError('Editable prefab geometry exported')
        invalid=root/'editable.ruster';app.save_project(invalid)
        app.open_path(invalid)
        prefab=next(o for o in scene.prefab_roots() if o.instance_collection and not o.instance_collection.library)
        assert protection.model_error(prefab),'Reopening blessed editable geometry as a valid original'
        placement.select([prefab]);assert bpy.ops.ruster.restore_models()=={'FINISHED'}
        assert not protection.model_error(prefab)
        # Unsupported unpacked parts block export and can be removed by repair.
        piece=prefab.instance_collection.objects[0].copy()
        bpy.context.scene.collection.objects.link(piece)
        assert any('unpacked prefab' in e for e in scene.validate()[0])
        assert bpy.ops.ruster.restore_models()=={'FINISHED'}
        assert not any(o.get('ruster_kind')=='VISUAL' for o in bpy.context.scene.objects)
        target=root/'protected.ruster';app.save_project(target)
        shutil.rmtree(scene.cache_dir());source.unlink()
        app.open_path(target)
        restored=[o for o in scene.prefab_roots() if o.get('ruster_visual')]
        assert restored and all(not protection.model_error(o) for o in restored)
        assert all(o.instance_collection.library.packed_file for o in restored)
        assert all(len(o.instance_collection.objects[0].data.polygons)==1 for o in restored)
        image=next(node.image for node in restored[0].instance_collection.objects[0].material_slots[0].material.node_tree.nodes if node.type=='TEX_IMAGE')
        assert image.packed_file and len(image.pixels)==16,'Packed prefab texture was lost with its cache'
        scene.export_map(root/'valid.map')
        # Legacy local previews become read-only immediately, but an old edited
        # preview must never be blessed as the original without source assets.
        from ruster.core import wire
        oldmesh=bpy.data.meshes.new('Old preview');oldmesh.from_pydata([(0,0,0),(1,0,0),(0,1,0)],[],[(0,1,2)])
        oldobj=bpy.data.objects.new('Old model',oldmesh);oldobj['ruster_kind']='VISUAL'
        oldcol=bpy.data.collections.new('Old asset');oldcol.objects.link(oldobj)
        legacy=scene.root_object([wire.encode(2,0,999999)],bpy.data.collections['Prefabs'])
        legacy.instance_type='COLLECTION';legacy.instance_collection=oldcol;legacy['ruster_visual']=True
        other=legacy.copy();bpy.data.collections['Prefabs'].objects.link(other)
        protection.protect_root(legacy)
        assert legacy.instance_collection==other.instance_collection and legacy.instance_collection.library
        assert 'Legacy' in protection.model_error(legacy)
        assert 'Legacy' in protection.model_error(other)
        cache=scene.cache_dir()/'prefabs';cache.mkdir(parents=True)
        (cache/'999999.json.gz').write_bytes(gzip.compress(json.dumps(triangle_asset(999999)).encode()))
        scene.restore_map_tools()
        assert not protection.model_error(legacy) and not protection.model_error(other)
        # Missing extraction prerequisites must not cancel an already-created placement.
        from ruster.assets import catalog
        db=catalog.connect(scene.cache_dir())
        with db:db.execute('INSERT INTO names VALUES(?,?)',(333333,'assets/test/unconverted.prefab'))
        db.close()
        from ruster import browser
        assert any(item[0]=='assets/test' for item in browser.category_items(None,None))
        bpy.context.scene.ruster.category='assets/test'
        db=catalog.connect(scene.cache_dir())
        with db:db.execute('INSERT INTO names VALUES(?,?)',(333334,'assets/aaa/earlier-category.prefab'))
        db.close()
        assert bpy.context.scene.ruster.category=='assets/test','Adding a category changed the active filter'
        count=len(scene.prefab_roots())
        assert bpy.ops.ruster.place(uid='333333')=={'FINISHED'}
        assert len(scene.prefab_roots())==count+1 and not bpy.context.object.get('ruster_visual')
        assert 'Could not start asset loading' in bpy.context.scene.ruster.asset_status
        # A normal Blender project retains ordinary editable custom meshes.
        assert bpy.ops.ruster.new('EXEC_DEFAULT')=={'FINISHED'}
        cube=bpy.data.objects['Cube'];placement.select([cube])
        assert bpy.ops.object.mode_set(mode='EDIT')=={'FINISHED'}
        assert bpy.ops.mesh.subdivide()=={'FINISHED'}
        assert bpy.ops.object.mode_set(mode='OBJECT')=={'FINISHED'}
        assert not bpy.ops.ruster.commands.poll()
        ruster.unregister()
    print('RUSTER_PREFAB_PROTECTION_OK',flush=True)


try:run()
except Exception:
    import traceback
    traceback.print_exc();os._exit(1)
