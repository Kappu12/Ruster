"""Blender controls with synthetic client discovery; no game processes touched."""
import os
from pathlib import Path
import sys
import tempfile
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
            assert bpy.types.RUSTER_PT_live_preview.bl_category == 'Ruster'
            from types import SimpleNamespace
            synthetic = SimpleNamespace(window_manager=SimpleNamespace(ruster_live_preview=state, clipboard=''))
            operator = SimpleNamespace(report=lambda *args: None)
            assert live_preview.RUSTER_OT_preview_copy_ip.execute(operator, synthetic) == {'FINISHED'}
            assert synthetic.window_manager.clipboard == '127.0.0.1:29100'
            # The action is present independently from its disabled UI state,
            # so execute must also reject requests before any remote operation.
            try:bpy.ops.ruster.inject_preview()
            except RuntimeError as error:assert 'server' in str(error)
            else:raise AssertionError('Injection ran without an active preview')
            assert not called
            ruster.unregister()
            assert not hasattr(bpy.types.WindowManager, 'ruster_live_preview')
            assert not bpy.app.timers.is_registered(live_preview.tick)
        finally:preview_client.discover = original
    print('RUSTER_LIVE_PREVIEW_UI_OK', flush=True)


try:run()
except Exception:traceback.print_exc();os._exit(1)
