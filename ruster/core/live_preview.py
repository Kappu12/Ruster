"""Owned local Rust server installation and preview-session lifecycle."""
from collections import deque
from contextlib import contextmanager
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
import re
from pathlib import Path, PurePosixPath
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
import zipfile

from .project import atomic_write
from .preview_protocol import write_snapshot, preview_map, canonical_placements, composition_origin, centered_placements
from .process_limits import OwnedProcessJob

STEAMCMD_URL = 'https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip'
CARBON_RELEASE = 'https://api.github.com/repos/CarbonCommunity/Carbon/releases/latest'
STOPPED = {'STOPPED', 'FAILED'}
SERVER_LEASE_SECONDS = 15.
STEAM_SUCCESS = "Success! App '258550' fully installed."


def steam_installation_ready(installation):
    """Check Steam's completed app state independently of its bootstrap exit."""
    from .steam import read_vdf
    installation = Path(installation)
    try:
        state = read_vdf(installation/'steamapps/appmanifest_258550.acf')['appstate']
        return (state.get('appid') == '258550' and state.get('stateflags') == '4'
            and state.get('updateresult') == '0' and int(state.get('sizeondisk', 0)) > 0
            and all((installation/name).is_file() and (installation/name).stat().st_size > 0 for name in
                ('RustDedicated.exe', 'UnityPlayer.dll', 'RustDedicated_Data/Managed/Assembly-CSharp.dll')))
    except (OSError, ValueError, KeyError, TypeError):return False


def steam_progress(text):
    """Return phase, overall estimate and current phase fraction from SteamCMD."""
    if STEAM_SUCCESS in text:return 'Rust server installed', .9, 1.
    updates = re.findall(r'Update state \([^\r\n]*?\) ([^,\r\n]+), progress: (\d+(?:\.\d+)?)', text)
    for phase, value in reversed(updates):
        phase = phase.casefold();fraction = max(0., min(1., float(value)/100))
        if phase == 'downloading':return 'Downloading Rust server', .10+.72*fraction, fraction
        if phase in ('verifying update', 'validating'):return 'Verifying Rust server', .82+.05*fraction, fraction
        if phase == 'committing':return 'Installing Rust server files', .87+.03*fraction, fraction
        if phase in ('reconfiguring', 'preallocating', 'running'):return 'Preparing Rust server download', .10, None
    updates = re.findall(r'\[\s*(\d+)%\]', text)
    if updates:
        fraction = min(1., int(updates[-1])/100)
        return 'Updating SteamCMD', .05+.05*fraction, fraction
    return 'Starting SteamCMD', .05, None


def open_status(path):
    """Allow the companion to atomically replace a status file during a read."""
    if sys.platform != 'win32':return Path(path).open('rb')
    import ctypes
    from ctypes import wintypes as W
    import msvcrt
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [W.LPCWSTR, W.DWORD, W.DWORD, ctypes.c_void_p,
        W.DWORD, W.DWORD, W.HANDLE]
    kernel.CreateFileW.restype = W.HANDLE
    kernel.CloseHandle.argtypes = [W.HANDLE];kernel.CloseHandle.restype = W.BOOL
    # GENERIC_READ, FILE_SHARE_READ|WRITE|DELETE, OPEN_EXISTING. Python's
    # ordinary file open does not share delete access on Windows.
    handle = kernel.CreateFileW(str(Path(path)), 0x80000000, 7, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:raise ctypes.WinError(ctypes.get_last_error())
    try:descriptor = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except Exception:
        kernel.CloseHandle(handle);raise
    try:return os.fdopen(descriptor, 'rb')
    except Exception:
        os.close(descriptor);raise


def read_bounded(path, limit=4096):
    with open_status(path) as handle:data = handle.read(limit+1)
    if len(data) > limit:raise ValueError('Preview status exceeds size limits')
    return data.decode('utf8')


def owner_id(value):
    value = value.strip()
    if value and (len(value) != 17 or not value.isascii() or not value.isdigit()
                  or not 76561197960265728 <= int(value) < 2**64):
        raise ValueError('Enter a 17-digit SteamID64, or leave Owner Steam ID blank')
    return value


def port_number(port):
    if type(port) is not int or not 1024 <= port <= 65533:
        raise ValueError('Game port must be between 1024 and 65533')
    return port


def verify_server_ready(path, *, expected_pid=None, expected_token=None, now=None):
    report = json.loads(read_bounded(path))
    if report.get('protocol') != 1 or report.get('secure') is not False or report.get('ip') != '127.0.0.1':
        raise ValueError('The server did not verify inactive EAC and a loopback-only listener')
    if report.get('client_protocol') != 2:
        raise ValueError('Restart Live Preview to load the updated map-object bridge')
    timestamp = report.get('timestamp')
    if (type(timestamp) not in (int, float) or not math.isfinite(timestamp)
            or not -2 <= (time.time() if now is None else now)-timestamp <= SERVER_LEASE_SECONDS):
        raise ValueError('The local server readiness report is stale; wait for its heartbeat')
    if type(report.get('pid')) is not int or report['pid'] <= 0 or not isinstance(report.get('token'), str):
        raise ValueError('The local server readiness report has no session identity')
    if expected_pid is not None and report['pid'] != expected_pid:raise ValueError('Preview server process changed')
    if expected_token is not None and not hmac.compare_digest(report['token'], expected_token):raise ValueError('Preview server session changed')
    return report


def verify_session(directory):
    directory = Path(directory)
    if not (directory/'active.flag').is_file() or (directory/'stop.flag').exists() or (directory/'server.blocked').exists():
        raise ValueError('The local preview server is not active')
    config = json.loads(read_bounded(directory/'config.json'))
    token = config.get('token')
    if not isinstance(token, str) or len(token) != 64:raise ValueError('Invalid preview session identity')
    return verify_server_ready(directory/'server.ready', expected_pid=int(read_bounded(directory/'server.pid')), expected_token=token)


@contextmanager
def installation_lease(root):
    """Do not update shared Carbon files while another preview owns them."""
    path = Path(root)/'server.lock'
    with path.open('a+b') as handle:
        if not path.stat().st_size:handle.write(b'0');handle.flush()
        handle.seek(0)
        try:
            if sys.platform == 'win32':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:raise ValueError('Another Ruster preview is using this local server; stop it first') from error
        try:yield
        finally:
            handle.seek(0)
            if sys.platform == 'win32':msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def check_ports(port):
    handles = []
    try:
        for number, kind in ((port, socket.SOCK_DGRAM), (port+1, socket.SOCK_STREAM), (port+2, socket.SOCK_DGRAM)):
            handle = socket.socket(socket.AF_INET, kind);handles.append(handle)
            if sys.platform == 'win32':handle.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            handle.bind(('127.0.0.1', number))
    except OSError as error:raise ValueError(f'Preview port range {port}–{port+2} is in use; choose another game port') from error
    finally:
        for handle in handles:handle.close()


def extract_zip(archive, destination, limit=512*1024*1024):
    """Validate the complete archive before extracting any member."""
    destination = Path(destination).resolve()
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        if len(members) > 20000 or sum(m.file_size for m in members) > limit:
            raise ValueError('Installation archive exceeds size limits')
        for member in members:
            path = PurePosixPath(member.filename.replace('\\', '/'))
            if (path.is_absolute() or '..' in path.parts or ':' in str(path)
                    or (member.external_attr >> 16) & 0xf000 == 0xa000
                    or not (destination/str(path)).resolve().is_relative_to(destination)):
                raise ValueError('Unsafe installation archive path')
        bundle.extractall(destination)


def download(url, path, cancel, *, maximum=128*1024*1024, digest=None, progress=None):
    path = Path(path);temporary = path.with_suffix(path.suffix+'.download')
    request = urllib.request.Request(url, headers={'User-Agent': 'Ruster-Live-Preview', 'Accept': 'application/octet-stream'})
    checksum = hashlib.sha256();total = 0
    try:
        with urllib.request.urlopen(request, timeout=30) as response, temporary.open('wb') as out:
            try:expected = int(response.headers.get('Content-Length', 0))
            except (AttributeError, ValueError, TypeError):expected = 0
            while chunk := response.read(256*1024):
                if cancel.is_set():raise InterruptedError('Preview setup cancelled')
                total += len(chunk)
                if total > maximum:raise ValueError('Download exceeds installation size limit')
                checksum.update(chunk);out.write(chunk)
                if progress:progress(total, expected)
        if digest and checksum.hexdigest() != digest:raise ValueError('Download SHA256 does not match the published release')
        temporary.replace(path)
    finally:temporary.unlink(missing_ok=True)
    return checksum.hexdigest()


def command(binary, identity, port, url, log):
    port_number(port)
    return [str(binary), '-batchmode', '-nographics', '-insecure', '-logfile', str(log),
        '+server.identity', identity, '+server.ip', '127.0.0.1', '+server.port', str(port),
        '+server.queryport', str(port+2), '+rcon.ip', '127.0.0.1', '+rcon.port', str(port+1),
        '+rcon.password', secrets.token_hex(32), '+server.maxplayers', '1',
        '+server.encryption', '1',
        '+server.hostname', 'Ruster Local Live Preview', '+server.levelurl', url,
        '+server.saveinterval', '86400', '+app.listenip', '127.0.0.1', '+app.port', '0']


class PreviewSession:
    def __init__(self, root, port=28015, owner='', placements=(), *, update_server=False, client_install=None, catalog_path=None):
        if sys.platform != 'win32':raise ValueError('Live client preview currently requires Windows x64')
        self.port = port_number(port);self.owner = owner_id(owner);check_ports(port)
        self.root = Path(root).resolve();self.root.mkdir(parents=True, exist_ok=True)
        self.install = self.root/'server';self.install.mkdir(exist_ok=True)
        self.identity = 'ruster_preview_'+uuid.uuid4().hex
        self.update_server = bool(update_server)
        if bool(client_install) != bool(catalog_path):raise ValueError('Prefab pack preload needs the Rust installation and catalog')
        self.client_install = Path(client_install) if client_install else None
        self.catalog_path = Path(catalog_path) if catalog_path else None
        self.preload = []
        self.directory = self.root/'sessions'/self.identity;self.directory.mkdir(parents=True)
        self.log = self.directory/'server.log'
        self.status = 'STARTING';self.message = 'Preparing local preview'
        self.progress = None;self.phase_progress = None;self.phase = ''
        self.process = None;self.http = None;self.thread = None
        self.cancel = threading.Event();self.lock = threading.Lock();self.events = deque(maxlen=80)
        self.revision = 1;self.url = '';initial = canonical_placements(placements)
        self.origin = composition_origin(initial);self._initial = centered_placements(initial, self.origin)
        self._origin_chosen = bool(initial)
        self._map = preview_map(self._initial);self.token = secrets.token_hex(32)
        self.process_lock = threading.Lock();self.owned_job = None
        self.pending = None
        self._ready_until = 0.
        write_snapshot(self.directory, self.revision, self._initial)
        shutil.copyfile(self.directory/'scene.bin', self.directory/'initial.bin')
        atomic_write(self.directory/'initial.json', (self.directory/'scene.json').read_bytes())

    @property
    def active(self):return self.thread.is_alive() if self.thread else self.status not in STOPPED

    def note(self, status, message):
        with self.lock:
            self.status, self.message = status, message;self.events.append(message)
            self.progress = None;self.phase_progress = None;self.phase = ''
        self._save_status()

    def installation_progress(self, phase, overall, fraction=None):
        if self.cancel.is_set():return
        overall = max(0., min(1., overall))
        if fraction is not None:fraction = max(0., min(1., fraction))
        with self.lock:
            if self.progress is not None and overall < self.progress:return
            if self.phase != phase:self.events.append(phase)
            self.status = 'DOWNLOADING';self.phase = phase;self.progress = overall;self.phase_progress = fraction
            self.message = phase+(f' · {fraction:.0%}' if fraction is not None else '')

    def _save_status(self):
        try:atomic_write(self.directory/'session.status.json', json.dumps(self.info(), indent=2).encode())
        except OSError:pass

    def start(self):
        if self.thread is not None:raise ValueError('This preview session has already been started')
        self.thread = threading.Thread(target=self._run, name='Ruster live preview', daemon=True)
        self.thread.start();return self

    def _serve_map(self):
        payload, route = self._map, '/'+secrets.token_hex(20)+'/preview.map'
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path != route:self.send_error(404);return
                self.send_response(200);self.send_header('Content-Type', 'application/octet-stream')
                self.send_header('Content-Length', str(len(payload)));self.send_header('Cache-Control', 'no-store');self.end_headers()
                self.wfile.write(payload)
            def log_message(self, *args):pass
        self.http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.http.daemon_threads = True
        self.url = f'http://127.0.0.1:{self.http.server_port}{route}'
        atomic_write(self.directory/'map.url', self.url.encode())
        threading.Thread(target=self.http.serve_forever, name='Ruster local preview map', daemon=True).start()

    def _install(self):
        binary = self.install/'RustDedicated.exe'
        stamp = self.install/'ruster-preview-install.json'
        if not self.update_server and steam_installation_ready(self.install) and stamp.is_file() and (self.install/'carbon/managed/Carbon.dll').is_file():return binary
        self.note('DOWNLOADING', 'Updating the local Rust server with SteamCMD' if binary.is_file() else 'Downloading SteamCMD and the official Rust dedicated server (several GB)')
        steam = self.root/'steamcmd';steam.mkdir(exist_ok=True)
        if self.update_server or not steam_installation_ready(self.install):
            if not (steam/'steamcmd.exe').is_file():
                self.installation_progress('Downloading SteamCMD', 0.)
                archive = self.root/'steamcmd.zip'
                download(STEAMCMD_URL, archive, self.cancel, maximum=16*1024*1024,
                    progress=lambda done, total: self.installation_progress('Downloading SteamCMD', .04*done/total, done/total) if total else None)
                self.installation_progress('Extracting SteamCMD', .04)
                extract_zip(archive, steam, 64*1024*1024)
            log = self.directory/'installation.log'
            with log.open('wb') as output:
                self._spawn([str(steam/'steamcmd.exe'), '+force_install_dir', str(self.install),
                    '+login', 'anonymous', '+app_update', '258550', 'validate', '+quit'], cwd=steam,
                    stdout=output, stderr=subprocess.STDOUT)
                self._wait_process(7200, descendants=True, progress_log=log)
            # SteamCMD updates/relaunches itself on first use. The original
            # bootstrap process can report a nonzero exit after its child has
            # successfully installed the app. Verify the completed app and this
            # attempt's success message, after all owned descendants finish.
            tail = self._log_text(log)
            if not steam_installation_ready(self.install) or (self.process.returncode and STEAM_SUCCESS not in tail):
                raise RuntimeError(f'SteamCMD exited ({self.process.returncode}) before Rust installation completed. See installation.log')
        else:self.installation_progress('Rust server already installed; resuming setup', .9, 1.)
        if self.cancel.is_set():raise InterruptedError()
        self.note('DOWNLOADING', 'Installing the Carbon server plugin loader')
        self.installation_progress('Checking Carbon server plugin loader', .9)
        request = urllib.request.Request(CARBON_RELEASE, headers={'User-Agent': 'Ruster-Live-Preview', 'Accept': 'application/vnd.github+json'})
        with urllib.request.urlopen(request, timeout=30) as response:release = json.loads(response.read(2*1024*1024))
        asset = next((a for a in release['assets'] if a['name'] == 'Carbon.Windows.Release.zip'), None)
        if asset is None:raise ValueError('The official Carbon release has no Windows server archive')
        url = asset['browser_download_url'];digest = asset.get('digest') or ''
        if not url.startswith('https://github.com/CarbonCommunity/Carbon/releases/download/') or not digest.startswith('sha256:'):
            raise ValueError('Carbon release has no trusted URL and SHA256 digest')
        archive = self.root/'carbon.zip'
        download(url, archive, self.cancel, digest=digest[7:], progress=lambda done, total:
            self.installation_progress('Downloading Carbon server plugin loader', .91+.06*done/total, done/total) if total else None)
        self.installation_progress('Installing Carbon server plugin loader', .97)
        extract_zip(archive, self.install)
        atomic_write(stamp, json.dumps({'carbon': release['tag_name'], 'sha256': digest[7:]}, indent=2).encode())
        self.installation_progress('Server installation complete', 1., 1.)
        return binary

    @staticmethod
    def _log_text(path):
        try:
            with Path(path).open('rb') as handle:
                handle.seek(max(0, Path(path).stat().st_size-32768))
                return handle.read(32768).decode('utf8', errors='replace')
        except OSError:return ''

    def _wait_process(self, timeout, *, descendants=False, progress_log=None):
        deadline = time.monotonic()+timeout
        while True:
            running = self.process.poll() is None
            if descendants:running = bool(self.owned_job.active_processes) or running
            if progress_log:self.installation_progress(*steam_progress(self._log_text(progress_log)))
            if not running:return
            if self.cancel.wait(.2):raise InterruptedError()
            if time.monotonic() > deadline:raise TimeoutError('Preview process timed out')

    def _check_readiness(self):
        try:
            report = verify_server_ready(self.directory/'server.ready', expected_pid=self.process.pid, expected_token=self.token)
        except (FileNotFoundError, PermissionError) as error:
            # Replacement can briefly leave the old Windows file delete-pending.
            # A missed read must not renew the last verified heartbeat lease.
            # Injection always reads and verifies the current report separately.
            if self.status != 'RUNNING' or time.monotonic() < self._ready_until:return False
            raise RuntimeError('Cannot read the local server heartbeat; its last verified report expired. Restart Live Preview.') from error
        self._ready_until = time.monotonic()+max(0., SERVER_LEASE_SECONDS-(time.time()-report['timestamp']))
        if self.status != 'RUNNING':self.note('RUNNING', 'Local server ready · EAC disabled')
        return True

    def _prepare_map(self):
        if not self.client_install:return
        from .preview_preload import plan
        self.note('STARTING', 'Preparing one preload marker for every prefab pack')
        self.preload = plan(self.client_install/'Bundles/AssetSceneManifest.json', self.install/'Bundles/AssetSceneManifest.json', self.catalog_path)
        self._map = preview_map(self._initial, preload=self.preload)
        atomic_write(self.directory/'preload.json', json.dumps({'packs': self.preload}, indent=2).encode())

    def _run(self):
        final_status, final_message = 'STOPPED', 'Local preview stopped'
        lease = installation_lease(self.root);leased = False
        try:
            lease.__enter__();leased = True
            self.owned_job = OwnedProcessJob()
            binary = self._install()
            if self.cancel.is_set():raise InterruptedError()
            self._prepare_map()
            check_ports(self.port)
            plugins = self.install/'carbon/plugins';plugins.mkdir(parents=True, exist_ok=True)
            source = Path(__file__).resolve().parents[1]/'preview_native/RusterPreview.cs'
            atomic_write(plugins/'RusterPreview.cs', source.read_bytes()+b'\n'+source.with_name('PreviewProtocol.cs').read_bytes())
            self._serve_map()
            atomic_write(self.directory/'config.json', json.dumps({'owner': self.owner, 'url': self.url, 'token': self.token, 'origin': self.origin}).encode())
            atomic_write(self.directory/'session.token', self.token.encode('ascii'))
            atomic_write(self.directory/'active.flag', b'Ruster local preview\n')
            env = {**os.environ, 'RUSTER_PREVIEW_DIR': str(self.directory)}
            self.note('STARTING', 'Starting the private Rust server; waiting for the preview plugin')
            self._spawn(command(binary, self.identity, self.port, self.url, self.log),
                cwd=self.install, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            atomic_write(self.directory/'server.pid', str(self.process.pid).encode())
            deadline = time.monotonic()+900;next_lease = 0.
            while not self.cancel.wait(.2):
                if self.process.poll() is not None:
                    if self.status == 'RUNNING' and self.process.returncode == 0:break
                    raise RuntimeError(f'Preview server exited ({self.process.returncode}); see server.log')
                if (self.directory/'server.blocked').exists():
                    raise RuntimeError((self.directory/'server.blocked').read_text()[:4096])
                with self.lock:
                    pending, self.pending = self.pending, None
                if pending is not None:
                    self.revision += 1;write_snapshot(self.directory, self.revision, pending)
                if time.monotonic() >= next_lease:
                    verified = self._check_readiness()
                    next_lease = time.monotonic()+(1. if verified else .2)
                if self.status != 'RUNNING' and time.monotonic() > deadline:
                    raise TimeoutError('The preview plugin did not become ready within 15 minutes. See server.log')
                if self.status != 'RUNNING' and any('PlayerPrefsException' in line for line in self.log_tail(12)):
                    raise RuntimeError('Rust server startup could not write its preferences. See server.log')
                if self.status != 'RUNNING' and 'at World.GetCachedHeightMapResolution' in self._log_text(self.log):
                    raise RuntimeError('Rust could not read the preview map height layer. See server.log')
        except InterruptedError:final_message = 'Preview setup cancelled'
        except Exception as error:final_status, final_message = 'FAILED', str(error)
        finally:
            self._stop_marker()
            cleanups = [self._stop_process]
            if self.owned_job:cleanups.append(self.owned_job.close)
            if self.http:cleanups.extend((self.http.shutdown, self.http.server_close))
            if leased:cleanups.append(lambda: lease.__exit__(None, None, None))
            for cleanup in cleanups:
                try:cleanup()
                except Exception as error:
                    final_status, final_message = 'FAILED', final_message+'; cleanup: '+str(error)
            self.note(final_status, final_message)

    def _spawn(self, arguments, **kwargs):
        with self.process_lock:
            if self.cancel.is_set():raise InterruptedError()
            self.process = subprocess.Popen(arguments, creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_BREAKAWAY_FROM_JOB, **kwargs)
            try:self.owned_job.assign(self.process)
            except Exception:
                self.process.terminate();self.process.wait(timeout=5);raise

    def _stop_process(self):
        with self.process_lock:
            if self.process and self.process.poll() is None:
                self.process.terminate()
                try:self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=5)

    def update(self, placements):
        if not self.active:return
        source = canonical_placements(placements)
        with self.lock:
            if source and not self._origin_chosen:
                self.origin = composition_origin(source);self._origin_chosen = True
            self.pending = centered_placements(source, self.origin)

    def send_command(self, value):
        if self.status != 'RUNNING':raise ValueError('Wait for the local server to become ready')
        value = value.strip()
        if not value or len(value) > 4096 or '\n' in value or '\r' in value or '\0' in value:
            raise ValueError('Enter one console command (up to 4,096 characters)')
        queue = self.directory/'commands';queue.mkdir(exist_ok=True)
        if len(list(queue.glob('*.json'))) >= 64:raise ValueError('The local console queue is full')
        atomic_write(queue/(uuid.uuid4().hex+'.json'), json.dumps({'command': value}).encode())

    def close(self):
        self.request_stop()
        self._stop_process()
        if self.thread:self.thread.join(timeout=7)

    def request_stop(self):
        if self.active:self.note('STOPPING', 'Stopping the local preview')
        self.cancel.set()
        self._stop_marker()

    def _stop_marker(self):
        # Stop uses an independent marker as well as removing active.flag.
        # Concurrent Windows deletion can report ACCESS_DENIED while a file is
        # delete-pending. That must never skip owned-process cleanup.
        try:atomic_write(self.directory/'stop.flag', b'Stop Ruster preview\n')
        except OSError:pass
        try:(self.directory/'active.flag').unlink(missing_ok=True)
        except OSError:pass

    def info(self):
        with self.lock:
            return {'status': self.status, 'message': self.message, 'address': f'127.0.0.1:{self.port}',
                'directory': str(self.directory), 'revision': self.revision, 'events': list(self.events),
                'progress': self.progress, 'phase_progress': self.phase_progress, 'phase': self.phase, 'pack_count': len(self.preload)}

    def log_tail(self, lines=8):
        values = []
        for path in (self.root/'steamcmd/logs/console_log.txt', self.directory/'installation.log', self.log,
                     self.directory/'server.status', self.directory/'client.status'):
            try:
                with path.open('rb') as handle:handle.seek(max(0, path.stat().st_size-8192));value = handle.read(8192)
                values.extend(value.decode('utf8', errors='replace').splitlines()[-lines:])
            except OSError:pass
        return values[-lines:]
