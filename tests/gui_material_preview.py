"""Draw an instanced prefab in Material Preview, within the editor's memory limit.

Pass an optional .ruster path after -- to exercise a local crash reproduction.
The supplied project is read only; test settings and unpacked files are isolated.
"""
import gzip
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import traceback

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ruster.core.process_limits import EDITOR_MEMORY, protect_process

if sys.platform == 'win32':
    protect_process(EDITOR_MEMORY)

import ruster
from ruster import app, scene, studio
from ruster.core import wire
from tests.fixtures import triangle_asset

temporary = tempfile.TemporaryDirectory(prefix='ruster-material-preview-')
directory = Path(temporary.name)
os.environ['RUSTER_USER_DIR'] = str(directory / 'user')
ruster.register()
arguments = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
if arguments:
    app.open_path(arguments[0])
else:
    studio.new_prefab()
    cache = scene.cache_dir() / 'prefabs'
    cache.mkdir(parents=True)
    image = bpy.data.images.new('Preview texture', 2, 2)
    image.pixels[:] = [.2, .7, .8, .8] * 4
    image.filepath_raw = str(cache / 'preview.png')
    image.file_format = 'PNG'
    image.save()
    bpy.data.images.remove(image)
    asset = triangle_asset()
    asset['materials']['mat'].update(texture='preview.png',
        metallic_gloss_texture='preview.png', emission=[0, .4, .7, 1], alpha_blend=True)
    (cache / '123456.json.gz').write_bytes(gzip.compress(json.dumps(asset).encode()))
    root = scene.root_object([wire.encode(2,0,123456)], bpy.data.collections['Prefabs'])
    assert scene.attach_visual(root), 'Synthetic prefab model did not attach'

state = {'stage': 0, 'draws': 0, 'previous_draws': 0, 'started': time.monotonic(),
         'compiling': False}


def drawn():
    state['draws'] += 1


handle = bpy.types.SpaceView3D.draw_handler_add(drawn, (), 'WINDOW', 'POST_PIXEL')


def step():
    try:
        window = bpy.context.window_manager.windows[0]
        with bpy.context.temp_override(window=window):
            area = next(area for area in window.screen.areas if area.type == 'VIEW_3D')
            region = next(region for region in area.regions if region.type == 'WINDOW')
            with bpy.context.temp_override(area=area, region=region):
                shading = area.spaces.active.shading
                if state['stage'] == 0:
                    assert bpy.app.version[:2] == (5, 2), 'Use the pinned Blender 5.2 runtime'
                    assert bpy.context.scene.ruster.mode == 'PREFAB'
                    assert not bpy.context.scene.ruster.source_map
                    roots = scene.prefab_roots()
                    collections = {root.instance_collection for root in roots if root.get('ruster_visual')}
                    assert collections, 'Material Preview has no loaded prefab model to draw'
                    assert all(collection and collection.library and not collection.is_editable
                               for collection in collections), 'Prefab models lost their read-only instancing'
                    assert any(obj.type == 'MESH' and obj.data.vertices and obj.data.polygons
                               for collection in collections for obj in collection.all_objects)
                    assert not any(obj.get('ruster_kind') in {'TERRAIN','WATER','PATH','PATH_PREVIEW'}
                                   for obj in bpy.context.scene.objects)
                    area.spaces.active.clip_end = 100000
                    bpy.ops.view3d.view_all(center=False)
                    shading.use_scene_world = False
                    shading.use_scene_lights = False
                    shading.type = 'MATERIAL'
                else:
                    elapsed = time.monotonic() - state['started']
                    assert elapsed < 125, f'Material Preview did not become ready within 125 seconds: {state}'
                    if state['stage'] in {1, 3}:
                        if bpy.app.is_job_running('SHADER_COMPILATION'):
                            if not state['compiling']:
                                print('Waiting for Material Preview shader compilation', state, flush=True)
                            state['compiling'] = True
                            area.tag_redraw()
                            return 2.
                        if state['compiling']:
                            state['compiling'] = False
                            area.tag_redraw()
                            return 2.
                    assert state['draws'] > state['previous_draws'], 'Viewport stopped drawing'
                    if state['stage'] == 1:
                        assert shading.type == 'MATERIAL'
                        shading.type = 'SOLID'
                    elif state['stage'] == 2:
                        shading.type = 'MATERIAL'
                    else:
                        assert shading.type == 'MATERIAL'
                        if output := os.environ.get('RUSTER_PREVIEW_SCREENSHOT'):
                            bpy.ops.screen.screenshot(filepath=output)
                        print('RUSTER_MATERIAL_PREVIEW_OK', state, flush=True)
                        bpy.types.SpaceView3D.draw_handler_remove(handle, 'WINDOW')
                        bpy.ops.wm.quit_blender()
                        return None
                area.tag_redraw()
                state['previous_draws'] = state['draws']
                state['stage'] += 1
                print('Material preview stage', state, flush=True)
        return 12.
    except Exception:
        traceback.print_exc()
        os._exit(1)


bpy.app.timers.register(step, first_interval=2.)
