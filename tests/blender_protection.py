"""Native read-only model data, export guards, offline packing and repair."""
import gzip,json,os,shutil,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
if '--' in sys.argv and sys.argv[sys.argv.index('--')+1:]:sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import bpy
import ruster
from ruster import app,scene,placement,protection,map_prefabs
from ruster.core import wire
from ruster.core.rust_map import RustMap
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
        assert not map_prefabs.validate()[0]
        assert any('no loaded visual' in note for note in map_prefabs.validate()[1])
        # The guarded .map serializer keeps untouched long thin IO records exact,
        # even when no Rust model or source-map data is available for that root.
        io_record=[wire.encode(2,0,147092032),wire.encode(3,2,wire.set_vector(None,(12,3,5))),
            wire.encode(4,2,wire.set_vector(None,(0,23.3,17.2))),
            wire.encode(5,2,wire.set_vector(None,(772.099,1,.821408))),
            wire.encode(77,2,b'preserve hidden IO extension')]
        io_root=scene.root_object(io_record,bpy.data.collections['Prefabs'])
        assert not map_prefabs.validate()[0]
        exported=RustMap.load(map_prefabs.export_map(root/'long-io.map'))
        actual=next(fields for fields in exported.prefabs if wire.get(fields,2)==147092032)
        assert wire.serialize(actual)==wire.serialize(io_record),'Guarded export rewrote untouched IO data'
        bpy.data.objects.remove(io_root,do_unlink=True)
        # World tools stay inactive; native model edit modes are rejected above.
        vertices=len(visual.data.vertices);faces=len(visual.data.polygons)
        for name in ('terrain_apply','terrain_stroke','generate_map','new_map','path_add'):
            try:getattr(bpy.ops.ruster,name).get_rna_type()
            except KeyError:pass
            else:raise AssertionError('World operator remains active: '+name)
        assert (len(visual.data.vertices),len(visual.data.polygons))==(vertices,faces)

        # The active .map path must enforce authoring guards before touching an
        # existing output file, even though it no longer has terrain/source data.
        guarded=root/'guarded.map';guarded.write_bytes(b'preserve existing output')
        def rejected(message):
            errors,_notes=map_prefabs.validate()
            assert any(message in error for error in errors),(message,errors)
            before=guarded.read_bytes()
            try:map_prefabs.export_map(guarded)
            except ValueError:pass
            else:raise AssertionError('Invalid scene exported: '+message)
            assert guarded.read_bytes()==before,'Rejected export overwrote an existing file'

        original_uid=duplicate['ruster_uid'];duplicate['ruster_uid']=str(uid+1)
        rejected('prefab ID differs from the source record')
        duplicate['ruster_uid']=original_uid
        original_record=duplicate['ruster_record'];duplicate['ruster_record']='invalid base64!'
        rejected('invalid prefab metadata')
        duplicate['ruster_record']=original_record
        duplicate['ruster_prefab_matrix']=[1.,2.]
        rejected('invalid prefab metadata')
        del duplicate['ruster_prefab_matrix']
        constraint=duplicate.constraints.new('LIMIT_LOCATION')
        rejected('constraints/modifiers/animation')
        duplicate.constraints.remove(constraint)
        modifier=duplicate.modifiers.new('Unsupported modifier',type='NODES')
        rejected('constraints/modifiers/animation')
        duplicate.modifiers.remove(modifier)
        duplicate.keyframe_insert(data_path='location',frame=1)
        rejected('constraints/modifiers/animation')
        duplicate.animation_data_clear()
        matrix=duplicate.matrix_world.copy()
        parent=bpy.data.objects.new('Unsupported parent',None)
        bpy.context.scene.collection.objects.link(parent)
        duplicate.parent=parent;duplicate.matrix_world=matrix
        rejected('parent must be a Ruster prefab group')
        parent['ruster_kind']='GROUP'
        constraint=parent.constraints.new('LIMIT_LOCATION')
        rejected('constraints/modifiers/animation')
        parent.constraints.remove(constraint)
        assert not map_prefabs.validate()[0]
        parent.scale=(2,1,1);duplicate.rotation_euler.z+=.5
        rejected('shear')
        duplicate.parent=None;duplicate.matrix_world=matrix
        bpy.data.objects.remove(parent,do_unlink=True)
        scale=duplicate.scale.copy();duplicate.scale=(0,1,1)
        rejected('zero scale');duplicate.scale=scale
        location=duplicate.location.copy();duplicate.location.x=float('nan')
        rejected('invalid transform');duplicate.location=location
        for kind in ('MESH','CURVE','FONT'):
            data=bpy.data.meshes.new('Unsupported mesh') if kind=='MESH' else bpy.data.curves.new('Unsupported curve',kind)
            obj=bpy.data.objects.new('Unsupported '+kind,data)
            bpy.context.scene.collection.objects.link(obj)
            obj['ruster_kind']='GROUP'  # A custom tag must not bypass geometry checks.
            rejected('custom objects cannot be embedded')
            bpy.data.objects.remove(obj,do_unlink=True)
            if kind=='MESH':bpy.data.meshes.remove(data)
            else:bpy.data.curves.remove(data)
        assert not map_prefabs.validate()[0]
        # Exercise cross-drive packing even on Linux by making the source path
        # non-relative; staging must work and leave cwd/library references intact.
        previous_cwd=Path.cwd();absolute=str(Path(bpy.path.abspath(library.filepath)).resolve())
        native_relpath=bpy.path.relpath
        bpy.path.relpath=lambda path,*args,**kwargs: absolute if str(path)==absolute else native_relpath(path,*args,**kwargs)
        try:protection.pack_models()
        finally:bpy.path.relpath=native_relpath
        assert library.packed_file and Path.cwd()==previous_cwd
        assert library.filepath==absolute
        # A reopened project can retain an already-packed absolute library while
        # a newly loaded model still needs packing. Native Blender validates both
        # paths, even if the packed model's original cache has gone offline.
        extra_uid=uid+100000
        (cache/f'{extra_uid}.json.gz').write_bytes(gzip.compress(json.dumps(triangle_asset(extra_uid)).encode()))
        extra=scene.root_object([wire.encode(2,0,extra_uid)],bpy.data.collections['Prefabs'])
        assert scene.attach_visual(extra)
        extra_library=extra.instance_collection.library
        assert not extra_library.packed_file
        original_paths={lib:lib.filepath for lib in bpy.data.libraries}
        packed_data=bytes(library.packed_file.data)
        original_file=Path(absolute).read_bytes();Path(absolute).unlink()
        bpy.path.relpath=lambda path,*args,**kwargs:str(path)  # Force cross-drive staging for every library.
        native_copy=shutil.copyfile
        def failed_copy(_source,_destination):raise OSError('Simulated library staging failure')
        try:
            shutil.copyfile=failed_copy
            try:protection.pack_models()
            except OSError as error:assert 'Simulated library staging failure' in str(error)
            else:raise AssertionError('Library staging failure was swallowed')
            finally:shutil.copyfile=native_copy
            assert all(lib.filepath==path for lib,path in original_paths.items())
            assert Path.cwd()==previous_cwd and not extra_library.packed_file
            protection.pack_models()
        finally:
            shutil.copyfile=native_copy
            bpy.path.relpath=native_relpath
            Path(absolute).write_bytes(original_file)
        assert library.packed_file and extra_library.packed_file
        assert bytes(library.packed_file.data)==packed_data,'Offline packed model data changed'
        assert all(lib.filepath==path for lib,path in original_paths.items())
        assert Path.cwd()==previous_cwd
        assert not protection.model_error(extra)
        bpy.data.objects.remove(extra,do_unlink=True)
        # Make-local/override-style data must be rejected, including after reopen.
        editable=prefab.instance_collection.copy()
        prefab.instance_collection=editable
        assert protection.model_error(prefab)
        assert any('read-only' in e for e in map_prefabs.validate()[0])
        try:map_prefabs.export_map(root/'invalid.map')
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
        rejected('unpacked prefab')
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
        map_prefabs.export_map(root/'valid.map')
        # Legacy local previews become read-only immediately, but an old edited
        # preview must never be blessed as the original without source assets.
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
        placement.select([legacy,other]);assert bpy.ops.ruster.restore_models()=={'FINISHED'}
        assert not protection.model_error(legacy) and not protection.model_error(other)
        # Missing extraction prerequisites must not cancel an already-created placement.
        from ruster.assets import catalog
        db=catalog.connect(scene.cache_dir())
        with db:db.execute('INSERT INTO names VALUES(?,?)',(333333,'assets/test/unconverted.prefab'))
        db.close()
        from ruster import browser
        assert any(item[0]=='@OTHER' for item in browser.category_items(None,None))
        bpy.context.scene.ruster.category='@OTHER'
        db=catalog.connect(scene.cache_dir())
        with db:db.execute('INSERT INTO names VALUES(?,?)',(333334,'assets/aaa/earlier-category.prefab'))
        db.close()
        assert bpy.context.scene.ruster.category=='@OTHER','Adding a category changed the active filter'
        count=len(scene.prefab_roots())
        assert bpy.ops.ruster.place(uid='333333')=={'FINISHED'}
        assert len(scene.prefab_roots())==count+1 and not bpy.context.object.get('ruster_visual')
        assert 'Could not start asset loading' in bpy.context.scene.ruster.asset_status
        # New starts a Rust composition and retains Rust command routing.
        assert bpy.ops.ruster.new('EXEC_DEFAULT')=={'FINISHED'}
        assert not list(bpy.context.scene.objects)
        assert bpy.ops.ruster.commands.poll()
        ruster.unregister()
    print('RUSTER_PREFAB_PROTECTION_OK',flush=True)


try:run()
except Exception:
    import traceback
    traceback.print_exc();os._exit(1)
