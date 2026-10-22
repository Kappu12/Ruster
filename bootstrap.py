"""Entry point executed by Blender inside the isolated Ruster process."""
import os
from pathlib import Path
import sys
import bpy

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
modules = ROOT / 'python_modules'
if modules.exists():
    sys.path.insert(0, str(modules))
    os.environ['RUSTER_PYTHON_MODULES'] = str(modules)

import ruster
from ruster import app
ruster.register()
if '--' in sys.argv:
    args = sys.argv[sys.argv.index('--') + 1:]
    if args:
        app._pending_project = args[0]
if not bpy.app.background:
    bpy.app.timers.register(app.startup, first_interval=.5)
