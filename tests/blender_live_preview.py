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
