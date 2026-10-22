"""Opt-in verification of the eight original IO slot assets from a local cache.

Usage: blender --background --factory-startup --python tests/blender_hidden_assets.py
       -- PATH_TO_ASSET_CACHE
No game scan, extraction or normal-profile writes; libraries use a temporary copy.
"""
import gzip
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import bpy
import ruster
from ruster import protection, scene
from ruster.core import wire

UIDS = (147092032, 451084045, 777221329, 955834086,
        1755192769, 2240347312, 2998914636, 4153457039)


def run():
    source = Path(sys.argv[sys.argv.index('--') + 1]).resolve() / 'prefabs'
    with tempfile.TemporaryDirectory(prefix='ruster-hidden-assets-') as directory:
        os.environ['RUSTER_USER_DIR'] = directory
        ruster.register()
        cache = scene.cache_dir() / 'prefabs'
        cache.mkdir(parents=True)
        for uid in UIDS:
            filename = f'{uid}.json.gz'
            asset = json.loads(gzip.decompress((source / filename).read_bytes()))
            shutil.copyfile(source / filename, cache / filename)
            # Only referenced buffers/textures are copied; never a whole game cache.
            references = [spec['buffer'] for spec in asset['meshes'].values() if spec.get('buffer')]
            references += [spec[key] for spec in asset['materials'].values()
                           for key in ('texture', 'emission_texture', 'metallic_gloss_texture') if spec.get(key)]
            for relative in references:
                original = (source / relative).resolve()
                target = (cache / relative).resolve()
                assert original.is_relative_to(source) and target.is_relative_to(cache)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(original, target)
            assert asset['meshes'] and asset['materials'] and not asset.get('marker')
            root = scene.root_object([wire.encode(2, 0, uid)], bpy.context.scene.collection)
            record = root['ruster_record']
            assert root.empty_display_type == 'CUBE'
            assert scene.attach_visual(root) and not protection.model_error(root), uid
            assert root['ruster_record'] == record and root.empty_display_size < .001
            originals = {spec['name']: spec for spec in asset['materials'].values()}
            for obj in root.instance_collection.objects:
                if obj.type != 'MESH':
                    continue
                for slot in obj.material_slots:
                    material = slot.material
                    # Each linked slot retains its source material's own color,
                    # transparency and HDR emission; Solid reads diffuse_color.
                    spec = next(spec for spec in originals.values()
                                if all(abs(a-b) < 1e-5 for a, b in zip(material.diffuse_color, spec['color'])))
                    bsdf = material.node_tree.nodes.get('Principled BSDF')
                    assert all(abs(a-b) < 1e-5 for a, b in zip(bsdf.inputs['Base Color'].default_value, spec['color']))
                    assert all(abs(a-b) < 1e-5 for a, b in zip(bsdf.inputs['Emission Color'].default_value, spec['emission']))
                    assert bsdf.inputs['Emission Strength'].default_value == 1
                    if spec.get('alpha_blend'):
                        assert material.surface_render_method == 'DITHERED'
                        assert abs(bsdf.inputs['Alpha'].default_value-spec['color'][3]) < 1e-5
            print('RUSTER_ORIGINAL_IO_ASSET_OK', uid, flush=True)
        ruster.unregister()
    print('RUSTER_ORIGINAL_HIDDEN_ASSETS_OK', flush=True)


try:
    run()
except Exception:
    traceback.print_exc()
    os._exit(1)
