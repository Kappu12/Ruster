"""Native layout, all-export guardrails, diagnostics and duplication regressions."""
import base64
import gzip
import json
import math
import os
from pathlib import Path
import sys
import tempfile
from contextlib import closing

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if '--' in sys.argv:sys.path.insert(0, sys.argv[sys.argv.index('--')+1])
import bpy
from mathutils import Vector
import ruster
from ruster import scene, studio, placement, map_prefabs, mcp_prefab_ops
from ruster.assets import catalog
from ruster.core import wire, prefabs
from tests.fixtures import triangle_asset


def near(actual, expected):
    assert (Vector(actual)-Vector(expected)).length < 2e-4, (actual, expected)


def rejected(callback, message):
    try:callback()
    except (ValueError, RuntimeError) as error:assert message in str(error), str(error)
    else:raise AssertionError('Expected rejection: '+message)


def run():
    with tempfile.TemporaryDirectory(prefix='ruster-layout-') as temporary:
        directory = Path(temporary)
        os.environ['RUSTER_USER_DIR'] = str(directory/'user')
        ruster.register();studio.new_prefab()
        uid = 123456
        cache = scene.cache_dir()
        with closing(catalog.connect(cache)) as db:
            db.execute('INSERT INTO names VALUES(?,?)', (uid, 'assets/test/triangle.prefab'));db.commit()
        (cache/'prefabs').mkdir(parents=True, exist_ok=True)
        (cache/'prefabs'/f'{uid}.json.gz').write_bytes(gzip.compress(json.dumps(triangle_asset(uid)).encode()))
        bpy.ops.ruster.place(uid=str(uid));source = bpy.context.object
        source.location = (2, 0, 1);bpy.context.view_layer.update()
        model = source.instance_collection
        assert bpy.ops.ruster.layout(operation='LINEAR', count=2, offset=(3, 0, 0)) == {'FINISHED'}
        roots = sorted(scene.prefab_roots(), key=lambda obj: obj.matrix_world.translation.x)
        assert len(roots) == 3
        for obj, x in zip(roots, (2, 5, 8)):
            near(obj.matrix_world.translation, (x, 0, 1))
            assert obj.instance_collection == model and model.library
        placement.select(roots)
        assert bpy.ops.ruster.layout(operation='DISTRIBUTE', axis='X', spacing=4) == {'FINISHED'}
        for obj, x in zip(roots, (2, 6, 10)):near(obj.matrix_world.translation, (x, 0, 1))
        assert bpy.ops.ruster.layout(operation='DISTRIBUTE', axis='X', mode='BOUNDS_GAP', spacing=1) == {'FINISHED'}
        from ruster.mcp_blender import loaded_bounds
        boxes = loaded_bounds(roots)
        for a, b in zip(boxes, boxes[1:]):assert abs(b['min'][0]-a['max'][0]-1) < 1e-4
        roots[0].location = (-.5, .5, 1);bpy.context.view_layer.update()
        placement.select([roots[0]])
        bpy.ops.ruster.layout(operation='GRID', axes='XY', step=1)
        near(roots[0].matrix_world.translation, (-1, 1, 1))
        placement.select(roots)
        bpy.ops.ruster.layout(operation='PLANE', axis='Z', target=3)
        assert all(abs(box['min'][2]-3) < 1e-4 for box in loaded_bounds(roots))
        # Align to the active object, not whichever happens to sort first.
        bpy.context.view_layer.objects.active = roots[1]
        target = loaded_bounds([roots[1]])[0]['max'][0]
        bpy.ops.ruster.layout(operation='ALIGN', axis='X', bound='MAX')
        assert all(abs(box['max'][0]-target) < 1e-4 for box in loaded_bounds(roots))
        placement.select([source])
        before = source.matrix_world.copy()
        bpy.ops.ruster.layout(operation='RADIAL', axis='Y', count=3, angle=90, center=(0, 0, 0))
        assert len(scene.prefab_roots()) == 6
        assert all(not obj.get('ruster_symmetry_source') for obj in bpy.context.selected_objects)
        near(source.matrix_world.translation, before.translation)
        # Bound errors leave all placements unchanged.
        placement.select(roots)
        roots[-1].instance_collection = None;roots[-1].instance_type = 'NONE'
        before = {obj: obj.matrix_world.copy() for obj in roots}
        rejected(lambda: bpy.ops.ruster.layout(operation='ALIGN'), 'Load original model')
        for obj, matrix in before.items():assert obj.matrix_world == matrix
        roots[-1].instance_type = 'COLLECTION';roots[-1].instance_collection = model
        # Copies of parented prefabs offset in WORLD space, with unique identity.
        studio.new_prefab()
        bpy.ops.ruster.place(uid=str(uid));source = bpy.context.object
        parent = placement.group([source]);parent.rotation_euler.z = math.pi/2;parent.scale = (2, 2, 2)
        bpy.context.view_layer.update();placement.select([source])
        before = source.matrix_world.translation.copy()
        duplicate = placement.duplicate_selected()[0]
        near(duplicate.matrix_world.translation, before+Vector((2, 0, 0)))
        assert duplicate['ruster_instance'] != source['ruster_instance']
        # Duplicating imported groups must not share editable IO source text.
        text = bpy.data.texts.new('Test source');text.write('independent metadata')
        parent['ruster_prefab_source'] = text.name
        placement.select([parent]);copy = placement.duplicate_selected()[0]
        assert copy['ruster_prefab_source'] != text.name
        bpy.data.texts[copy['ruster_prefab_source']].write(' changed')
        assert text.as_string() == 'independent metadata'
        # Every format rejects the same metadata and non-TRS errors, including
        # untouched byte-preservation paths and the UI assembly exporter.
        studio.new_prefab();bpy.ops.ruster.place(uid=str(uid));source = bpy.context.object
        placement.select([source]);source.name = 'Spaces are valid editor labels'
        original = base64.b64decode(source['ruster_record'])
        assert wire.serialize(studio.prefab_records([source], Vector())[0]) == original
        def check_all(message):
            placement.select([source])
            rejected(lambda: studio.prefab_records([source], Vector()), message)
            rejected(lambda: placement.world_record(source), message)
            errors, _notes = map_prefabs.validate();assert any(message in error for error in errors), errors
            rejected(lambda: studio.export_prefab(directory/'blocked.prefab'), message)
            rejected(lambda: bpy.ops.ruster.assembly_export(filepath=str(directory/'blocked.rusterprefab')), message)
            assert not (directory/'blocked.prefab').exists() and not (directory/'blocked.rusterprefab').exists()
        source['ruster_uid'] = str(uid+1);check_all('prefab ID differs');source['ruster_uid'] = str(uid)
        source.scale = (0, 1, 1);check_all('zero scale');source.scale = (1, 1, 1)
        constraint = source.constraints.new('COPY_LOCATION');check_all('constraints');source.constraints.remove(constraint)
        parent = placement.group([source]);parent['ruster_kind'] = 'OTHER';check_all('parent must');parent['ruster_kind'] = 'GROUP'
        parent.scale = (2, 1, 1);source.rotation_euler.z = .5;check_all('shear')
        parent.scale = (1, 1, 1);source.rotation_euler.z = 0
        # Diagnostics only select, never silently remove or repair a placement.
        bpy.context.view_layer.update();placement.select([source])
        duplicate = placement.duplicate_selected()[0]
        duplicate.matrix_world = source.matrix_world.copy();bpy.context.view_layer.update()
        warnings = map_prefabs.placement_warnings(scene.prefab_roots())
        assert any(code == 'DUPLICATES' and len(objects) == 1 for code, objects, _message in warnings)
        bpy.ops.ruster.select_composition_issue(issue='DUPLICATES')
        assert len(bpy.context.selected_objects) == 1 and len(scene.prefab_roots()) == 2
        duplicate.scale = (-2, 2, 2);duplicate['ruster_has_io'] = True;bpy.context.view_layer.update()
        codes = {code for code, _objects, _message in map_prefabs.placement_warnings(scene.prefab_roots())}
        assert {'MIRRORED', 'SCALED_IO'} <= codes
        # UI assembly import uses the requested cursor as its retained pivot.
        assembly = directory/'off-center.rusterprefab'
        assembly.write_bytes(prefabs.encode_assembly(studio.prefab_records([source], Vector((-8, 0, 0))), 'Offset'))
        bpy.context.scene.cursor.location = (12, -4, 3)
        assert bpy.ops.ruster.assembly_import(filepath=str(assembly)) == {'FINISHED'}
        near(bpy.context.object.matrix_world.translation, (12, -4, 3))
        before = set(bpy.context.scene.objects)
        selected = list(bpy.context.selected_objects);active = bpy.context.object
        attach = scene.attach_visual
        try:
            def fail_attach(_obj):raise ValueError('Injected model attachment failure')
            scene.attach_visual = fail_attach
            rejected(lambda: bpy.ops.ruster.assembly_import(filepath=str(assembly)), 'Injected')
        finally:scene.attach_visual = attach
        assert set(bpy.context.scene.objects) == before
        assert list(bpy.context.selected_objects) == selected and bpy.context.object == active
        ruster.unregister()
    print('Prefab layout, diagnostics and export consistency checks passed', flush=True)


run()
