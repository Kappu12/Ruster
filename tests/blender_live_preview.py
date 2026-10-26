"""Blender controls with synthetic client discovery; no game processes touched."""
import os
from pathlib import Path
import sys
import tempfile
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if '--' in sys.argv:
    target = Path(sys.argv[sys.argv.index('--')+1]);sys.path.insert(0, str(target))
    if (target/'python_modules').is_dir():sys.path.insert(0, str(target/'python_modules'))

import bpy
import ruster
from ruster import live_preview
from ruster.core import settings, preview_client


def run():
    with tempfile.TemporaryDirectory(prefix='ruster-live-ui-') as folder:
        root = Path(folder);os.environ['RUSTER_USER_DIR'] = str(root/'user')
        settings.save({'preview_port': 29100, 'preview_owner': '76561198000000000'})
        called = []
        original = preview_client.discover
        preview_client.discover = lambda installation: called.append('synthetic-discovery') or []
        live_preview.installation = lambda: root
        try:
            ruster.register()
            state = bpy.context.window_manager.ruster_live_preview
            assert state.port == 29100 and state.owner == '76561198000000000'
            assert called == [], 'Registration inspected the real client'
            assert live_preview.placements() == []
            # Capture original prefab IDs and absolute world transforms without
            # requiring a game model, client process, or injected code.
            from ruster import scene
            from ruster.assets import catalog
            from ruster.core import wire
            db = catalog.connect(scene.cache_dir())
            db.execute('INSERT INTO names VALUES(?,?)', (123456, 'assets/test/source.prefab'));db.commit();db.close()
            fields = [wire.encode(1, 2, b'Decor'), wire.encode(2, 0, 123456),
                wire.encode(3, 2, wire.set_vector(None, (1, 2, 3))),
                wire.encode(4, 2, wire.set_vector(None, (0, 90, 0))),
                wire.encode(5, 2, wire.set_vector(None, (2, 3, 4)))]
            obj = scene.root_object(fields, scene.new_collection('Preview fixture'))
            rows = live_preview.placements();assert len(rows) == 1
            row = rows[0]
            assert row['uid'] == 123456 and row['path'] == 'assets/test/source.prefab'
            assert all(abs(a-b) < 1e-5 for a,b in zip(row['position'], (1, 2, 3)))
            assert all(abs(a-b) < 1e-5 for a,b in zip(row['scale'], (2, 3, 4)))
            from math import sqrt
            assert abs(abs(row['rotation'][1])-sqrt(.5)) < 1e-5
            key = row['key'];obj.name = 'Renamed placement'
            assert live_preview.placements()[0]['key'] == key
            duplicate = obj.copy();bpy.context.scene.collection.objects.link(duplicate)
            rows = live_preview.placements();assert len({r['key'] for r in rows}) == 2
            bpy.data.objects.remove(duplicate, do_unlink=True);bpy.data.objects.remove(obj, do_unlink=True)
            assert bpy.types.RUSTER_PT_live_preview.bl_space_type == 'PROPERTIES'
            assert bpy.types.RUSTER_PT_live_preview.bl_region_type == 'WINDOW'
            from types import SimpleNamespace
            synthetic = SimpleNamespace(window_manager=SimpleNamespace(ruster_live_preview=state, clipboard=''))
            operator = SimpleNamespace(report=lambda *args: None)
            assert live_preview.RUSTER_OT_preview_copy_ip.execute(operator, synthetic) == {'FINISHED'}
            assert synthetic.window_manager.clipboard == '127.0.0.1:29100'
            from concurrent.futures import Future
            # Background discovery must never erase an injection failure or
            # silently replace an unconsumed completed operation.
            future = Future();future.set_exception(ValueError('synthetic injection failure'))
            live_preview._future = future;live_preview._future_kind = 'inject'
            live_preview._next_probe = time.monotonic()+60
            live_preview.tick()
            assert live_preview._error == 'synthetic injection failure'
            future = Future();future.set_result(([], False, False, 'synthetic Rust is not running'))
            live_preview._future = future;live_preview._future_kind = 'probe'
            try:live_preview.submit('launch', lambda: None)
            except ValueError:pass
            else:raise AssertionError('Unconsumed result was overwritten')
            live_preview.tick()
            assert live_preview._error == 'synthetic injection failure'
            assert live_preview._probe_message == 'synthetic Rust is not running'
            class FakeJob:
                active = True;status = 'RUNNING';port = 29100;directory = root
                stopped = False
                def info(self):return {'status': self.status, 'message': 'Synthetic preview'}
                def log_tail(self, count):return ['synthetic log']
                def update(self, rows):raise ValueError('synthetic snapshot rejection')
                def request_stop(self):self.stopped = True;self.status = 'STOPPING'
                def close(self):self.active = False
            job = FakeJob();live_preview._job = job;live_preview._last_snapshot = None
            live_preview.scene_changed(None)
            live_preview.capture_snapshot()
            assert live_preview._snapshot_error == 'synthetic snapshot rejection'
            job.update = lambda rows: None;live_preview.scene_changed(None)
            live_preview.capture_snapshot()
            assert not live_preview._snapshot_error
            # Draw only cached data. Any filesystem/probe/status call during
            # draw fails this fixture; a real UI draw is tested separately.
            class Layout:
                def __init__(self):self.labels = []
                def column(self, **kwargs):return self
                row = box = column
                def separator(self):pass
                def label(self, **kwargs):self.labels.append(kwargs.get('text', ''))
                def prop(self, *args, **kwargs):pass
                def operator(self, *args, **kwargs):self.labels.append(kwargs.get('text', ''));return SimpleNamespace()
                def panel(self, *args, **kwargs):return self, self
            (root/'server.status').write_text('ERROR\nSynthetic missing asset-scene dependency\n')
            layout = Layout();live_preview.refresh_status()
            saved_install, saved_read = live_preview.installation, live_preview.backend.read_bounded
            def no_io(*args, **kwargs):raise AssertionError('Preview draw performed I/O')
            live_preview.installation = live_preview.backend.read_bounded = no_io
            job.info = job.log_tail = no_io
            draw_context = SimpleNamespace(window_manager=SimpleNamespace(ruster_live_preview=state),
                preferences=bpy.context.preferences, region=SimpleNamespace(width=320))
            try:
                for clients, allowed, loaded in (([], False, False), ([SimpleNamespace()], True, False), ([SimpleNamespace()], False, True)):
                    live_preview._clients = clients;live_preview._client_allowed = allowed;live_preview._module_loaded = loaded
                    live_preview.RUSTER_PT_live_preview.draw(SimpleNamespace(layout=layout), draw_context)
                live_preview._client_status = 'ERROR · Synthetic compatibility failure'
                live_preview.RUSTER_PT_live_preview.draw(SimpleNamespace(layout=layout), draw_context)
                assert 'Preview Unavailable' in layout.labels
                assert 'preview could not start' in ' '.join(layout.labels)
                live_preview._client_status = 'WAITING · Waiting for a fresh local server heartbeat'
                live_preview.RUSTER_PT_live_preview.draw(SimpleNamespace(layout=layout), draw_context)
                assert 'Preview Paused' in layout.labels and 'updates resume' in ' '.join(layout.labels)
                live_preview._client_status = 'STOPPED · Synthetic session ended'
                live_preview.RUSTER_PT_live_preview.draw(SimpleNamespace(layout=layout), draw_context)
                assert 'Preview Stopped' in layout.labels and 'Close Rust fully' in ' '.join(layout.labels)
                live_preview._client_status = ''
            finally:
                live_preview.installation, live_preview.backend.read_bounded = saved_install, saved_read
            assert 'restart your computer' in ' '.join(layout.labels)
            assert 'Server: ERROR' in ' '.join(layout.labels) and 'Synthetic missing asset-scene dependency' in ' '.join(layout.labels)
            live_preview.document_replaced();assert job.stopped
            assert live_preview._last_snapshot is None and live_preview._capture is None
            job.active = False;state.port = 29200
            live_preview.RUSTER_OT_preview_copy_ip.execute(operator, synthetic)
            assert synthetic.window_manager.clipboard == '127.0.0.1:29200', 'Stopped preview copied an obsolete port'
            # Timers/handlers survive document loading and reset on unregister.
            assert live_preview.after_load in bpy.app.handlers.load_post
            assert live_preview.scene_changed in bpy.app.handlers.depsgraph_update_post
            live_preview._job = None;live_preview._clients = []
            project = root/'preview-lifecycle.blend'
            bpy.ops.wm.save_as_mainfile(filepath=str(project), check_existing=False)
            bpy.ops.wm.open_mainfile(filepath=str(project), load_ui=False, use_scripts=False)
            assert bpy.app.timers.is_registered(live_preview.tick), 'Preview timer was lost on document load'
            assert bpy.context.window_manager.ruster_live_preview.port == 29100
            # The action is present independently from its disabled UI state,
            # so execute must also reject requests before any remote operation.
            try:bpy.ops.ruster.inject_preview()
            except RuntimeError as error:assert 'server' in str(error)
            else:raise AssertionError('Injection ran without an active preview')
            assert not called
            ruster.unregister()
            assert not hasattr(bpy.types.WindowManager, 'ruster_live_preview')
            assert not bpy.app.timers.is_registered(live_preview.tick)
            assert live_preview.after_load not in bpy.app.handlers.load_post
            assert live_preview.scene_changed not in bpy.app.handlers.depsgraph_update_post
            assert not live_preview._error and not live_preview._logs
        finally:preview_client.discover = original
    print('RUSTER_LIVE_PREVIEW_UI_OK', flush=True)


try:run()
except Exception:traceback.print_exc();os._exit(1)
