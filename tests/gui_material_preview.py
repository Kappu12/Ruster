"""Draw Material Preview under the editor's Windows allocation limit.

Pass an optional .ruster path after -- to exercise a local crash reproduction.
The supplied project is read only; test settings and unpacked files are isolated.
"""
import gzip
import json
import os
from pathlib import Path
import sys
import tempfile
import traceback

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ruster.core.process_limits import EDITOR_MEMORY, protect_process

if sys.platform == 'win32':
    protect_process(EDITOR_MEMORY)

import ruster
from ruster import scene
from ruster.core import project
from tests.fixtures import sample_world, triangle_asset

temporary = tempfile.TemporaryDirectory(prefix='ruster-material-preview-')
directory = Path(temporary.name)
os.environ['RUSTER_USER_DIR'] = str(directory / 'user')
ruster.register()
arguments = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
if arguments:
    project.unpack(arguments[0], directory / 'project')
    bpy.ops.wm.open_mainfile(filepath=str(directory / 'project/scene.blend'),
                             load_ui=False, use_scripts=False)
else:
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
    path = directory / 'preview.map'
    path.write_bytes(sample_world().write())
    scene.import_map(path)

state = {'stage': 0, 'draws': 0, 'previous_draws': 0}


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
                    assert any(obj.type == 'MESH' for obj in bpy.context.scene.objects)
                    area.spaces.active.clip_end = 100000
                    bpy.ops.view3d.view_all(center=False)
                    shading.type = 'MATERIAL'
                else:
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
