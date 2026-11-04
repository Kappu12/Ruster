"""Profile selection and exclusive ownership shared by the CLI and MCP adapter."""
import os
from pathlib import Path
from . import settings

DEFAULT_PORT = 9878


def configure_user_dir(directory=None, *, headless=False):
    if directory:
        root = Path(directory).expanduser()
    else:
        root = settings.user_root()
        if headless and not os.environ.get('RUSTER_USER_DIR'):
            root = root / 'headless'
    root = root.resolve()
    os.environ['RUSTER_USER_DIR'] = str(root)
    return root


class ProfileLock:
    """OS-owned lock: a crash releases it, and another session cannot steal it."""
    def __init__(self, directory):
        self.path = Path(directory) / 'headless.lock'
        self.stream = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.path.open('a+b')
        self.stream.seek(0, 2)
        if not self.stream.tell():
            self.stream.write(b'\0'); self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.stream.close(); self.stream = None
            raise ValueError('A headless session already owns this profile. Use another --user-dir and --mcp-port.') from error
        return self

    def __exit__(self, *_args):
        if self.stream:
            if os.name == 'nt':
                import msvcrt
                self.stream.seek(0)
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
            self.stream.close(); self.stream = None
