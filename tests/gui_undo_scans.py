"""Undo a packed project while the save-status timer holds a partial scan."""
import gzip
import json
import os
from pathlib import Path
import sys
import tempfile
import traceback
from contextlib import closing

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if '--' in sys.argv:sys.path.insert(0, sys.argv[sys.argv.index('--')+1])
os.environ['RUSTER_PREVIEW_TEST_NO_DISCOVERY'] = '1'
temporary = tempfile.TemporaryDirectory(prefix='ruster-undo-scans-')
directory = Path(temporary.name);os.environ['RUSTER_USER_DIR'] = str(directory/'user')

import bpy
import ruster
from ruster import app, live_preview, quitting, scene, studio
from ruster.assets import catalog
from ruster.core import wire
from tests.fixtures import triangle_asset

app.startup = lambda: None
ruster.register()
if bpy.app.timers.is_registered(quitting.status_tick):bpy.app.timers.unregister(quitting.status_tick)
state = {'phase': 0}


def pause_scan():
    quitting._status_scan = quitting.fingerprint_steps()
    for _ in range(8):next(quitting._status_scan)


def pause_all_scans():
    pause_scan()
    live_preview._capture = live_preview.placement_rows();next(live_preview._capture)
    app._visual_iterator = iter(scene.prefab_roots());app._visual_uid = 123456


def check_scans_released():
    assert quitting._status_scan is None, 'Undo retained the document scan'
    assert live_preview._capture is None, 'Undo retained the live-preview capture'
    assert app._visual_iterator is None, 'Undo retained the model-linking iterator'


def check_status(expected):
    for _ in range(1000):
        if quitting.status_tick() == 1.:break
    else:raise AssertionError('Save status never finished')
    assert quitting.save_status() == expected, quitting.save_status()
    assert quitting.has_unsaved_changes() == (expected == 'Unsaved changes')


def tick():
    try:
        window = bpy.context.window_manager.windows[0]
        area = next(a for a in window.screen.areas if a.type == 'VIEW_3D')
        region = next(r for r in area.regions if r.type == 'WINDOW')
        with bpy.context.temp_override(window=window, area=area, region=region):
            phase = state['phase']
            if phase == 0:
                studio.new_prefab()
                cache = scene.cache_dir()
                with closing(catalog.connect(cache)) as db:
                    db.execute('INSERT INTO names VALUES(?,?)', (123456, 'assets/test/triangle.prefab'));db.commit()
                (cache/'prefabs').mkdir(parents=True, exist_ok=True)
                (cache/'prefabs/123456.json.gz').write_bytes(gzip.compress(json.dumps(triangle_asset()).encode()))
                roots = [scene.root_object([wire.encode(2, 0, 123456)], bpy.context.scene.collection) for _ in range(128)]
                scene.attach_visual(roots[0], prepared=True);linked = roots[0].instance_collection
                for root in roots[1:]:root.instance_collection = linked;root.instance_type = 'COLLECTION';scene.model_attached(root)
                state['root'] = roots[0].name
                app.save_project(directory/'undo.ruster')
            elif phase == 1:
                app.open_path(directory/'undo.ruster')
                assert all(root.instance_collection.library.packed_file for root in scene.prefab_roots())
            elif phase == 2:
                bpy.ops.ed.undo_push(message='Before timer undo')
                bpy.context.scene.objects[state['root']].location.x = 5
                bpy.ops.ed.undo_push(message='Moved before timer undo')
                pause_all_scans()
                bpy.ops.ed.undo()
                check_scans_released()
                print('RUSTER_UNDO_SCAN_RESUME', flush=True)
                check_status('Saved')
                assert bpy.context.scene.objects[state['root']].location.x == 0
            elif phase == 3:
                pause_all_scans();bpy.ops.ed.redo();check_scans_released();check_status('Unsaved changes')
                assert bpy.context.scene.objects[state['root']].location.x == 5
            elif phase == 4:
                pause_all_scans()
                x, y = region.x+region.width//2, region.y+region.height//2
                window.event_simulate(type='MOUSEMOVE', value='NOTHING', x=x, y=y)
                window.event_simulate(type='Z', value='PRESS', ctrl=True, x=x, y=y)
                window.event_simulate(type='Z', value='RELEASE', ctrl=True, x=x, y=y)
            elif phase == 5:
                check_scans_released()
                check_status('Saved')
                assert bpy.context.scene.objects[state['root']].location.x == 0
            elif phase == 6:
                for _ in range(12):
                    pause_all_scans();bpy.ops.ed.redo();check_scans_released();check_status('Unsaved changes')
                    pause_all_scans();bpy.ops.ed.undo();check_scans_released();check_status('Saved')
            elif phase == 7:
                pause_scan()
                # Remove the exact scene-list node at which the timer yielded.
                # This does not dispatch undo_pre, so snapshot iteration must
                # also tolerate ordinary native/scripted deletion.
                bpy.data.objects.remove(list(bpy.context.scene.objects)[7], do_unlink=True)
                # A completed scan can contain records copied before deletion;
                # the following cycle compares the complete current document.
                for _ in range(1000):
                    if quitting.status_tick() == 1.:break
                check_status('Unsaved changes')
            elif phase == 8:
                parent = scene.new_collection('Scan lifetime fixture')
                for i in range(6):scene.new_collection('Scan child '+str(i), parent)
                scan = quitting.collection_steps(parent);next(scan)
                bpy.data.collections.remove(parent.children[0])
                for _ in scan:pass
            elif phase == 9:
                text = bpy.data.texts.new('Scan source fixture');text.write(('x'*262144+'\n')*3)
                scene.prefab_roots()[0]['ruster_prefab_source'] = text.name
                quitting._status_scan = quitting.fingerprint_steps()
                for _ in range(len(bpy.context.scene.objects)+3):next(quitting._status_scan)
                text.clear();text.write('Updated while the status scan yielded')
                check_status('Unsaved changes')
            elif phase == 10:
                pause_all_scans();app.open_path(directory/'undo.ruster');check_scans_released()
                check_status('Saved')
            elif phase == 11:
                pause_all_scans();studio.new_prefab();check_scans_released()
                assert not bpy.context.scene.objects
            else:
                ruster.unregister()
                for handlers in (bpy.app.handlers.undo_pre, bpy.app.handlers.redo_pre, bpy.app.handlers.load_pre):
                    assert quitting.invalidate_scan not in handlers
                    assert live_preview.invalidate_capture not in handlers
                    assert app.before_scene_replace not in handlers
                print('RUSTER_GUI_UNDO_SCANS_OK', flush=True)
                bpy.ops.wm.quit_blender();return None
            state['phase'] += 1
        return .3
    except Exception:traceback.print_exc();os._exit(1)


bpy.app.timers.register(tick, first_interval=.5, persistent=True)
