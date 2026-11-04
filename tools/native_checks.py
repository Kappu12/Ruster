"""Run the active prefab editor fixtures against an actual pinned Blender.

Packaging and CI share the background suite. Dormant map-editor fixtures stay in
tests/ for the retained world code, but are not the prefab product's contract.
Each graphical fixture gets its own process and disposable display/profile.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BACKGROUND_TESTS = (
    'blender_prefab_product.py', 'blender_project_close.py', 'blender_polish.py', 'blender_protection.py', 'blender_ui.py',
    'blender_mcp.py', 'blender_studio.py', 'blender_catalog.py',
    'blender_placeholders.py', 'blender_prefab_transforms.py',
    'blender_materials.py', 'blender_construction.py', 'blender_layout.py', 'blender_volumes.py', 'blender_loading_budget.py',
    'blender_live_preview.py', 'blender_volume_preview.py', 'blender_model_bounds.py', 'blender_mcp_session.py',
)
GRAPHICAL_TESTS = (
    'gui_startup.py', 'gui_prefab_welcome.py', 'gui_project_close.py', 'gui_undo_scans.py', 'gui_prefab_polish.py', 'gui_prefab_search.py',
    'gui_material_preview.py', 'gui_construction.py', 'gui_prefab_layout.py', 'gui_blender_controls.py', 'gui_volumes.py', 'gui_volume_interaction.py',
    'gui_preview_loading.py', 'gui_mcp.py',
    'gui_live_preview.py',
)


def run_suite(executable, suite='background', app_root=None, xvfb=False):
    graphical = suite == 'graphical'
    if graphical and app_root is not None:
        raise ValueError('Staged app roots are supported by the background suite only')
    tests = GRAPHICAL_TESTS if graphical else BACKGROUND_TESTS
    for test in tests:
        print(f'Running {suite} fixture: {test}', flush=True)
        command = [str(executable), '-t', '2', '--factory-startup',
                   '--disable-autoexec', '--python-exit-code', '1']
        if graphical:
            command += ['--gpu-backend', 'opengl', '--enable-event-simulate',
                        '--window-geometry', '0', '0', '1240', '900']
        else:
            command += ['-b']
        command += ['--python', str(ROOT/'tests'/test)]
        if app_root is not None:
            command += ['--', str(app_root)]
        if xvfb:
            command = ['xvfb-run', '-a', '-s', '-screen 0 1600x1000x24', *command]
        with tempfile.TemporaryDirectory(prefix='ruster-native-profile-') as profile:
            config=Path(profile)/'config';config.mkdir()
            env={**os.environ,'BLENDER_USER_CONFIG':str(config),'RUSTER_PREVIEW_TEST_NO_DISCOVERY':'1'}
            subprocess.run(command, cwd=ROOT, env=env, check=True, timeout=150 if graphical else 120)
    if not graphical:
        import sys
        print('Running persistent headless MCP round trip', flush=True)
        subprocess.run([sys.executable, str(ROOT/'tests/headless_roundtrip.py'), str(executable), str(app_root or ROOT)],
                       cwd=ROOT, check=True, timeout=150)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engine', type=Path, required=True,
                        help='Blender executable, or directory containing the pinned extracted Linux runtime')
    parser.add_argument('--suite', choices=('background', 'graphical'), default='background')
    parser.add_argument('--xvfb', action='store_true', help='Give each fixture a disposable X display')
    args = parser.parse_args()
    executable = args.engine.resolve()
    if executable.is_dir():
        lock = json.loads((ROOT/'engine.lock.json').read_text())
        folder = lock['archives']['linux-x64']['file'].removesuffix('.tar.xz')
        executable = executable/folder/'blender'
    if not executable.is_file():
        parser.error(f'Blender executable does not exist: {executable}')
    if args.suite == 'graphical':
        os.environ.setdefault('LIBGL_ALWAYS_SOFTWARE', '1')
    run_suite(executable, args.suite, xvfb=args.xvfb)


if __name__ == '__main__':
    main()
