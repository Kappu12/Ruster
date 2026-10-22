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
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
        bpy.context.window.event_simulate(type='ESC',value='PRESS')
        bpy.context.window.event_simulate(type='MOUSEMOVE',value='NOTHING',x=600,y=500)
        if mode != 'setup':
            path = Path('/tmp/ruster-preview.map')
            path.write_bytes(sample_world().write())
            scene.import_map(path)
            ui.map_workspace()
            if mode=='browser':
                from contextlib import closing
                from ruster.assets import catalog
                with closing(catalog.connect(scene.cache_dir())) as db:
                    for uid in range(25):
                        asset=f'assets/prefabs/construction/prefab_{uid:02d}.prefab'
                        db.execute('INSERT OR REPLACE INTO names VALUES(?,?)',(uid,asset))
                        if uid%3:db.execute('INSERT OR REPLACE INTO assets VALUES(?,?,?,?)',(asset,'bundle','file',uid))
                    db.commit()
    return None


def prepare():
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
        area=next(a for a in bpy.context.screen.areas if a.type=='VIEW_3D')
        region=next(r for r in area.regions if r.type=='WINDOW')
        with bpy.context.temp_override(area=area,region=region):
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP',iterations=1)
            if mode=='setup':bpy.ops.ruster.setup('INVOKE_DEFAULT')
            elif mode=='settings':bpy.ops.ruster.preferences('INVOKE_DEFAULT',section='RUSTER_MCP')
            else:
                next(r for r in area.regions if r.type=='UI').active_panel_category='Ruster'
                area.tag_redraw()
                bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP',iterations=2)
    return None


def capture():
    with bpy.context.temp_override(window=bpy.context.window_manager.windows[0]):
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=2)
        bpy.ops.screen.screenshot(filepath=f'/tmp/ruster-{mode}.png')
        bpy.ops.wm.quit_blender()
    return None


bpy.app.timers.register(start,first_interval=2)
bpy.app.timers.register(prepare,first_interval=4)
bpy.app.timers.register(capture,first_interval=12)
