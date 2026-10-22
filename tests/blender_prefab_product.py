"""Small native fixtures prove the prefab product never constructs world editors."""
import math
import os
from pathlib import Path
import sys
import tempfile
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if '--' in sys.argv and sys.argv[sys.argv.index('--')+1:]:
    sys.path.insert(0, sys.argv[sys.argv.index('--')+1])
import bpy
import ruster
from ruster import app, scene, studio, map_prefabs, preferences, ui_style
from ruster.core import project, wire
from ruster.core.rust_map import RustMap, prefab_transform
from tests.fixtures import sample_world


def run():
    with tempfile.TemporaryDirectory(prefix='ruster-prefab-product-') as tmp:
        directory = Path(tmp)
        os.environ['RUSTER_USER_DIR'] = str(directory / 'user')
        ruster.register()
        original_request = app.request_missing_visuals
        requested = []
        app.request_missing_visuals = lambda objects: requested.append(len(objects))
        def no_world(*args, **kwargs):
            raise AssertionError('Prefab workflow invoked the world editor')
        old = [scene.import_map, scene.create_terrain, scene.create_paths, scene.restore_map_tools]
        scene.import_map = scene.create_terrain = scene.create_paths = scene.restore_map_tools = no_world
        try:
            studio.new_prefab()
            # Every registered command in the active product vocabulary exists.
            for name in ui_style.ACTIONS:
                group, operator = name.split('.')
                getattr(getattr(bpy.ops, group), operator).get_rna_type()
            for name in ('new_map','generate_map','generate_island','terrain_stroke','path_add','generator_install','height_import','mask_import','map_view','surface_snap','scatter','paint_asset'):
                try:
                    getattr(bpy.ops.ruster, name).get_rna_type()
                except KeyError:
                    pass
                else:
                    raise AssertionError('World command remains registered: ' + name)
            assert dict((item[0], item[1]) for item in preferences.SECTIONS if item)['RUSTER_ASSETS'] == 'Assets'
            assert dict((item[0], item[1]) for item in preferences.SECTIONS if item)['RUSTER_MCP'] == 'MCP'
            # Empty New Prefab is an immediate dismissal without a scene reset.
            state = bpy.context.scene.ruster
            state.title = 'Already empty'
            assert bpy.ops.ruster.new('INVOKE_DEFAULT') == {'FINISHED'}
            assert state.title == 'Already empty'
            for version in (9, 10):
                source = directory / f'world-{version}.map'
                source.write_bytes(sample_world(version).write())
                app.open_path(source)
                assert state.mode == 'PREFAB' and state.source_map == ''
                assert {obj.get('ruster_kind') for obj in bpy.context.scene.objects} == {'PREFAB'}
                assert len(scene.prefab_roots()) == 2 and state.terrain_state is None
                output = RustMap.load(map_prefabs.export_map(directory / f'clean-{version}.map'))
                assert output.prefabs == sample_world(version).prefabs
                assert {field.number for field in output.fields} == {1, 3}
                assert not output.layers and not output.paths
            # Import appends in world space even with a nonzero editor cursor.
            first = scene.prefab_roots()[0]
            first.location.x += 7
            bpy.context.scene.cursor.location = (30, 40, 50)
            created = map_prefabs.import_map(source)
            assert len(scene.prefab_roots()) == 4
            assert (created[0].location - scene.to_blender((0, 116, 0))).length < 1e-5
            group = __import__('ruster.placement', fromlist=['group']).group([first])
            group.location.z += 9
            bpy.context.view_layer.update()
            output = RustMap.load(map_prefabs.export_map(directory / 'moved.map'))
            assert any(abs(prefab_transform(fields)[0][0] - 7) < 1e-5 and abs(prefab_transform(fields)[0][1] - 125) < 1e-5 for fields in output.prefabs)
            assert all(wire.get(fields, 47) == b'unknown prefab extension' for fields in output.prefabs)
            # Bad records and count bounds must preserve the complete composition.
            before = list(bpy.context.scene.objects)
            invalid = sample_world()
            records = invalid.prefabs
            records[-1] = wire.replace(records[-1], 3, 2, wire.set_vector(None, (math.nan, 0, 0)))
            invalid.replace_prefabs(records)
            broken = directory / 'broken.map'
            broken.write_bytes(invalid.write())
            for path, kwargs in ((broken, {'replace': True}), (source, {'replace': True, 'max_prefabs': 1})):
                try:
                    map_prefabs.import_map(path, **kwargs)
                except ValueError:
                    pass
                else:
                    raise AssertionError('Invalid import accepted')
                assert list(bpy.context.scene.objects) == before
            # Legacy MAP saves recover their edited placements and discard editors.
            state.mode = 'MAP'
            state.source_map = str(source)
            terrain = bpy.data.objects.new('Legacy terrain', bpy.data.meshes.new('Legacy terrain'))
            bpy.context.scene.collection.objects.link(terrain)
            terrain['ruster_kind'] = 'TERRAIN'
            state.terrain_state = bpy.data.texts.new('Legacy map edits')
            legacy = directory / 'legacy.ruster'
            app.save_project(legacy)
            app.open_path(legacy)
            state = bpy.context.scene.ruster
            assert state.mode == 'PREFAB' and not state.source_map and state.terrain_state is None
            assert not any(obj.get('ruster_kind') in {'TERRAIN','PATH','WATER'} for obj in bpy.context.scene.objects)
            assert bpy.data.meshes.get('Legacy terrain') is None
            assert bpy.data.texts.get('Legacy map edits') is None
            assert len(scene.prefab_roots()) == 4
            assert RustMap.load(map_prefabs.export_map(directory / 'recovered.map')).prefabs == output.prefabs
            # Re-saving the recovered file produces a standalone prefab project.
            recovered = directory / 'recovered.ruster'
            app.save_project(recovered)
            manifest = project.unpack(recovered, directory / 'unpacked')
            assert manifest['mode'] == 'PREFAB' and 'source.map' not in manifest['files']
            # Corrupt legacy source is rejected before replacing this scene.
            blend = directory / 'scene.blend'
            bpy.ops.wm.save_as_mainfile(filepath=str(blend), copy=True, check_existing=False)
            corrupt_project = directory / 'corrupt.ruster'
            project.save(corrupt_project, blend, 'MAP', broken)
            before = list(bpy.context.scene.objects)
            try:
                app.open_path(corrupt_project)
            except ValueError:
                pass
            else:
                raise AssertionError('Corrupt source accepted')
            assert list(bpy.context.scene.objects) == before
            assert requested == [2, 2, 2]
            # Large imports stay as cheap placement markers; loading remains
            # an explicit bounded selection instead of a mass asset request.
            many = RustMap(10, b'\0'*8, [wire.encode(1, 0, 1000)])
            many.replace_prefabs([wire.replace(sample_world().prefabs[0], 2, 0, uid) for uid in range(101)])
            large = directory / 'many.map'
            large.write_bytes(many.write())
            app.request_missing_visuals = original_request
            assert len(map_prefabs.import_map(large, replace=True)) == 101
            assert len(scene.prefab_roots()) == 101 and not app._visual_queue and app._job is None
            assert '100 different models at a time' in bpy.context.scene.ruster.asset_status
            cache = scene.cache_dir() / 'prefabs'
            cache.mkdir(parents=True, exist_ok=True)
            (cache / '123456.json.gz').touch()
            original_assets = app.request_assets
            extracted = []
            try:
                app.request_assets = lambda ids: extracted.append(set(ids))
                map_prefabs.import_map(source, replace=True)
                assert app._visual_queue == [123456]
                assert extracted == [{234567}], 'Cached models were requested from the worker again'
            finally:
                app.request_assets = original_assets
                app._visual_queue.clear()
        finally:
            app.request_missing_visuals = original_request
            scene.import_map, scene.create_terrain, scene.create_paths, scene.restore_map_tools = old
            ruster.unregister()
    print('RUSTER_PREFAB_PRODUCT_OK', flush=True)


try:
    run()
except Exception:
    traceback.print_exc()
    os._exit(1)
