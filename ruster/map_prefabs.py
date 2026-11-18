"""Prefab-only native Rust .map interchange; world layers stay out of the scene."""
import base64
import math
from pathlib import Path
import struct

import bpy
from mathutils import Vector

from . import scene
from .core import wire
from .core.project import atomic_write
from .core.rust_map import RustMap, prefab_id, prefab_transform


def read_map(path, *, max_prefabs=None):
    """Validate every placement before a scene can be changed, without height grids."""
    world = RustMap.load(path)
    records = world.prefabs
    if max_prefabs is not None and len(records) > max_prefabs:
        raise ValueError(f'Map contains {len(records):,} prefabs; limit is {max_prefabs:,}')
    for fields in records:
        prefab_id(fields)
        if not all(math.isfinite(v) for values in prefab_transform(fields) for v in values):
            raise ValueError('Prefab transform contains non-finite values')
    return world, records


def import_map(path, *, replace=False, max_prefabs=None):
    """Append existing placements at their world transforms, or start a composition."""
    from . import app, studio
    path = Path(path).resolve()
    world, records = read_map(path, max_prefabs=max_prefabs)
    # Stage only empty placement roots. A malformed record or failed object
    # creation must not discard the user's current composition.
    staging = bpy.data.collections.new('Ruster map import')
    staging.use_fake_user = True
    created = []
    try:
        for fields in records:
            created.append(scene.root_object(fields, staging))
        if replace:
            studio.new_prefab()
        collection = bpy.data.collections.get('Prefabs') or scene.new_collection('Prefabs')
        for obj in created:
            collection.objects.link(obj)
            staging.objects.unlink(obj)
    except Exception:
        for obj in created:
            bpy.data.objects.remove(obj, do_unlink=True)
        raise
    finally:
        bpy.data.collections.remove(staging)
    state = bpy.context.scene.ruster
    if not state.native_ground:
        state.mode = 'PREFAB'
        state.source_map = ''
        state.terrain_state = None
    if replace:
        state.title = path.stem
        state.map_size = world.size
    # Import stays cheap even for large maps. Cache recovery and missing models
    # use the bounded asynchronous queue; placement roots need no asset reads.
    try:
        app.request_missing_visuals(created)
    except Exception as error:
        # Placements are complete; an optional preview failure must not turn a
        # successful import into an error after the scene has already changed.
        state.asset_status = f'Prefab placements imported. Could not queue models: {error}'
    bpy.context.view_layer.update()
    return created


def validate_placements(roots):
    """Shared guards for map, native prefab and assembly serialization."""
    from .placement import parent_chain
    from .protection import model_error

    bpy.context.view_layer.update()
    errors, notes = [], []
    checked_models = {}
    missing = 0
    for root in roots:
        try:
            if root.get('ruster_kind') != 'PREFAB':
                raise ValueError('Only whole prefab placements can be exported')
            problem = model_error(root, checked_models)
            if problem:
                errors.append(f'{root.name}: {problem}')
            uid = int(root['ruster_uid'])
            if not 0 <= uid <= 0xFFFFFFFF:
                raise ValueError('Invalid prefab ID')
            fields = wire.parse(base64.b64decode(root['ruster_record'], validate=True))
            if prefab_id(fields) != uid:
                errors.append(f'{root.name}: prefab ID differs from the source record')
            if not all(math.isfinite(v) for values in prefab_transform(fields) for v in values):
                raise ValueError('Invalid source transform')
            baseline = root.get('ruster_prefab_matrix')
            if baseline is not None and (len(baseline) != 16 or not all(math.isfinite(v) for v in baseline)):
                raise ValueError('Invalid source transform matrix')
            parents = list(parent_chain(root))
            if any(parent.get('ruster_kind') != 'GROUP' for parent in parents):
                errors.append(f'{root.name}: parent must be a Ruster prefab group')
            if any(obj.constraints or obj.modifiers or obj.animation_data for obj in (root, *parents)):
                errors.append(f'{root.name}: bake constraints/modifiers/animation before exporting')
            matrix = root.matrix_world
            if not all(math.isfinite(v) for row in matrix for v in row):
                errors.append(f'{root.name}: invalid transform')
            else:
                location, rotation, scale = matrix.decompose()
                if not all(math.isfinite(v) for v in (*location, *rotation, *scale)):
                    errors.append(f'{root.name}: invalid transform')
                if any(abs(v) < 1e-7 for v in scale):
                    errors.append(f'{root.name}: zero scale')
                if scene.matrix_has_shear(matrix):
                    errors.append(f'{root.name}: group transforms introduce shear; use uniform group scale')
            missing += not bool(root.get('ruster_visual'))
        except (KeyError, ValueError, TypeError, IndexError, OverflowError, struct.error):
            errors.append(f'{root.name}: invalid prefab metadata')
    if missing:
        notes.append(f'{missing} prefab placements have no loaded visual; IDs and transforms still export')
    return errors, notes


def _validated_records():
    """Enforce placement-only authoring before native record serialization."""
    from .studio import prefab_records
    roots = scene.prefab_roots()
    errors, notes = validate_placements(roots)
    objects = list(bpy.context.scene.objects)
    unpacked = [obj for obj in objects if obj.get('ruster_kind') == 'VISUAL']
    if unpacked:
        errors.append(f'{len(unpacked)} unpacked prefab model parts cannot export; restore the original prefab models')
    custom = [obj for obj in objects if obj.type in {'MESH','CURVE','FONT'} and obj.get('ruster_kind') != 'VISUAL'
              and not (bpy.context.scene.ruster.native_ground and obj.get('ruster_ground_preview')
                       and obj.get('ruster_kind') in {'TERRAIN','WATER'})]
    if custom:
        errors.append(f'{len(custom)} custom objects cannot be embedded in a Rust .map; save them in .ruster instead')
    if errors:
        return errors, notes, []
    try:
        # Keep the native serializer's byte-exact path for untouched records,
        # including long thin IO pieces and metadata that Rust adds later.
        records = prefab_records(roots, Vector())
        for fields in records:
            prefab_id(fields)
            if not all(math.isfinite(v) for values in prefab_transform(fields) for v in values):
                raise ValueError('Prefab transform contains non-finite values')
    except Exception as error:
        return [str(error)], notes, []
    notes.append(f'{len(records):,} prefab placements ready to export')
    notes.extend(message for _code, _objects, message in placement_warnings(roots))
    return [], notes, records


def placement_warnings(roots):
    """Actionable observations, not claims of universal gameplay compatibility."""
    mirrored, scaled_io, duplicates = [], [], []
    seen = {}
    for root in roots:
        matrix = root.matrix_world
        if not all(math.isfinite(v) for row in matrix for v in row):continue
        if matrix.determinant() < 0:mirrored.append(root)
        if root.get('ruster_has_io') and any(abs(v-1) > 1e-5 for v in matrix.to_scale()):scaled_io.append(root)
        # Compare the transform matrix, so equivalent Euler rotations match.
        key = (root.get('ruster_uid'), tuple(round(v, 5) for row in matrix for v in row))
        if key in seen:
            duplicates.append(root)
        else:seen[key] = root
    result = []
    if duplicates:
        result.append(('DUPLICATES', duplicates, f'{len(duplicates)} overlapping copies of the same prefab share a transform; inspect before deleting'))
    if mirrored:
        result.append(('MIRRORED', mirrored, f'{len(mirrored)} mirrored placements need collision and lighting verification in Rust'))
    if scaled_io:
        result.append(('SCALED_IO', scaled_io, f'{len(scaled_io)} imported IO placements are scaled; Rust networked entities use unit scale'))
    return result


def validate():
    """Validate protected prefab records and world transforms without world data."""
    if bpy.context.scene.ruster.native_ground:
        from . import ground
        return ground.validate()
    errors, notes, _records = _validated_records()
    return errors, notes


def validation_status(*, require_ground=False):
    errors, notes = validate()
    if require_ground and not bpy.context.scene.ruster.native_ground:
        errors.append('This project has no native Rust ground')
    return {'valid': not errors, 'errors': errors, 'notes': notes}


def export_map(path, *, overwrite=True, require_ground=False):
    """Write prefab IDs and world TRS, retaining unknown inner record fields."""
    if bpy.context.scene.ruster.native_ground:
        from . import ground
        return ground.export_map(path, overwrite=overwrite)
    if require_ground:
        raise ValueError('This project has no native Rust ground')
    errors, _notes, records = _validated_records()
    if errors:
        raise ValueError('; '.join(errors[:5]))
    size = max(1, min(32768, bpy.context.scene.ruster.map_size))
    world = RustMap(10, b'\0' * 8, [wire.encode(1, 0, size)])
    world.replace_prefabs(records)
    path = Path(path)
    if path.suffix.lower() != '.map':
        path = Path(str(path) + '.map')
    atomic_write(path, world.write(), overwrite=overwrite)
    return path
