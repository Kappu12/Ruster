"""Entry point executed by Blender inside the isolated Ruster process."""
import os
from pathlib import Path
import sys
import bpy

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
if sys.platform == 'win32':
    from ruster.core.process_limits import protect_process, EDITOR_MEMORY
    protect_process(EDITOR_MEMORY, int(os.environ['RUSTER_LAUNCHER_PID'])
                    if os.environ.get('RUSTER_LAUNCHER_PID') else None, allow_breakaway=True)
modules = ROOT / 'python_modules'
if modules.exists():
    sys.path.insert(0, str(modules))
    os.environ['RUSTER_PYTHON_MODULES'] = str(modules)

import ruster
from ruster import app
ruster.register()
print(f'RUSTER_READY {ruster.__version__} / Blender {bpy.app.version_string}', flush=True)
if '--' in sys.argv:
    args = sys.argv[sys.argv.index('--') + 1:]
    if args:
        app._pending_project = args[0]
if bpy.app.background and os.environ.get('RUSTER_HEADLESS') == '1':
    from ruster.headless import run
    run(app._pending_project)
elif not bpy.app.background:
    bpy.app.timers.register(app.startup, first_interval=.5)
