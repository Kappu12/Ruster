"""Development-only GUI snapshots from the actual Blender window."""
import os
from pathlib import Path
import sys
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ['RUSTER_USER_DIR'] = '/tmp/ruster-gui-profile'
import ruster
from ruster import app, scene, ui
from tests.fixtures import sample_world

ruster.register()
mode = os.environ.get('RUSTER_PREVIEW', 'setup')


def start():
    if mode == 'setup':
        app.startup()
    else:
        path = Path('/tmp/ruster-preview.map')
        path.write_bytes(sample_world().write())
        scene.import_map(path)
        ui.map_workspace()
    return None


def capture():
    bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=2)
    bpy.ops.screen.screenshot(filepath=f'/tmp/ruster-{mode}.png')
    bpy.ops.wm.quit_blender()
    return None


bpy.app.timers.register(start,first_interval=2)
bpy.app.timers.register(capture,first_interval=8)
