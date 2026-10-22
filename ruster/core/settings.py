"""Per-user settings and cache, isolated from regular Blender preferences."""
from pathlib import Path
import json
import os
import sys
from .project import atomic_write
from .wire import FormatError


def user_root():
    if override := os.environ.get('RUSTER_USER_DIR'):
        return Path(override)
    if sys.platform == 'win32':
        return Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'Ruster'
    if sys.platform == 'darwin':
        return Path.home() / 'Library/Application Support/Ruster'
    return Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'ruster'


def load():
    try:
        value = json.loads((user_root() / 'settings.json').read_text())
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def save(settings):
    atomic_write(user_root() / 'settings.json', json.dumps(settings, indent=2).encode())


def validate_install(path):
    root = Path(path).expanduser().resolve()
    if root.name == 'Bundles':
        root = root.parent
    bundles = root / 'Bundles'
    if not bundles.is_dir():
        raise FormatError('Choose the Rust game folder containing the Bundles directory')
    # Steam's native macOS layout, and the standard Windows/Linux layout.
    if not any((root / name).exists() for name in ('RustClient.exe', 'Rust.exe', 'RustClient', 'Rust', 'Rust.app')):
        raise FormatError('This folder does not look like a Rust installation (game executable missing)')
    return root
