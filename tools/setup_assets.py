"""Install local asset-reading dependencies using Blender's bundled Python."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from launch import find_blender

base = Path(find_blender()).parent
candidates = list(base.glob('*/python/bin/python*'))
if sys.platform == 'darwin':
    candidates += list(base.glob('../Resources/*/python/bin/python*'))
candidates = [p for p in candidates if p.is_file() and '-config' not in p.name]
if not candidates:
    raise SystemExit('Blender bundled Python was not found')
python = str(sorted(candidates)[0].resolve())
subprocess.run([python,'-m','ensurepip'],check=True)
subprocess.run([python,'-m','pip','install','--only-binary=:all:','--no-binary=tpk_ar',
                '--target',str(ROOT/'python_modules'),'-r',str(ROOT/'requirements-assets.txt'),
                '-r',str(ROOT/'requirements-mcp.txt')],check=True)
print('Asset reader ready. Launch Rustmatics with launch.py.')
