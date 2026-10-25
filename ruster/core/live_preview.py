"""Owned local Rust server installation and preview-session lifecycle."""
from collections import deque
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
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
from .preview_protocol import write_snapshot, preview_map

STEAMCMD_URL = 'https://steamcdn-a.akamaihd.net/client/installer/steamcmd.zip'
CARBON_RELEASE = 'https://api.github.com/repos/CarbonCommunity/Carbon/releases/latest'
STOPPED = {'STOPPED', 'FAILED'}


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


def verify_server_ready(path):
    path = Path(path)
    if path.stat().st_size > 4096:raise ValueError('Invalid preview server readiness report')
    report = json.loads(path.read_text())
    if report.get('protocol') != 1 or report.get('secure') is not False or report.get('ip') != '127.0.0.1':
        raise ValueError('The server did not verify inactive EAC and a loopback-only listener')


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


def download(url, path, cancel, *, maximum=128*1024*1024, digest=None):
    path = Path(path);temporary = path.with_suffix(path.suffix+'.download')
    request = urllib.request.Request(url, headers={'User-Agent': 'Ruster-Live-Preview', 'Accept': 'application/octet-stream'})
    checksum = hashlib.sha256();total = 0
    try:
        with urllib.request.urlopen(request, timeout=30) as response, temporary.open('wb') as out:
            while chunk := response.read(256*1024):
                if cancel.is_set():raise InterruptedError('Preview setup cancelled')
                total += len(chunk)
                if total > maximum:raise ValueError('Download exceeds installation size limit')
                checksum.update(chunk);out.write(chunk)
        if digest and checksum.hexdigest() != digest:raise ValueError('Download SHA256 does not match the published release')
        temporary.replace(path)
    finally:temporary.unlink(missing_ok=True)
    return checksum.hexdigest()


def command(binary, identity, port, url, log):
    port_number(port)
    return [str(binary), '-batchmode', '-nographics', '-insecure', '-logfile', str(log),
        '+server.identity', identity, '+server.ip', '127.0.0.1', '+server.port', str(port),
        '+server.queryport', str(port+2), '+rcon.ip', '127.0.0.1', '+rcon.port', str(port+1),
        '+rcon.password', secrets.token_urlsafe(32), '+server.maxplayers', '1',
        '+server.encryption', '1',
        '+server.hostname', 'Ruster Local Live Preview', '+server.levelurl', url,
        '+server.saveinterval', '86400', '+app.listenip', '127.0.0.1', '+app.port', '0']


class PreviewSession:
    def __init__(self, root, port=28015, owner='', placements=()):
        if sys.platform != 'win32':raise ValueError('Live client preview currently requires Windows x64')
        self.port = port_number(port);self.owner = owner_id(owner);check_ports(port)
        self.root = Path(root).resolve();self.root.mkdir(parents=True, exist_ok=True)
        self.install = self.root/'server';self.install.mkdir(exist_ok=True)
        self.identity = 'ruster_preview_'+uuid.uuid4().hex
        self.directory = self.root/'sessions'/self.identity;self.directory.mkdir(parents=True)
        self.log = self.directory/'server.log'
        self.status = 'STARTING';self.message = 'Preparing local preview'
        self.process = None;self.http = None;self.thread = None
        self.cancel = threading.Event();self.lock = threading.Lock();self.events = deque(maxlen=80)
        self.revision = 1;self.url = '';self._map = preview_map(list(placements))
        self.pending = None
        self._initial = list(placements)
        write_snapshot(self.directory, self.revision, self._initial)
        shutil.copyfile(self.directory/'scene.bin', self.directory/'initial.bin')
        atomic_write(self.directory/'initial.json', (self.directory/'scene.json').read_bytes())

    @property
    def active(self):return self.status not in STOPPED

    def note(self, status, message):
        with self.lock:
            self.status, self.message = status, message;self.events.append(message)

    def start(self):
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
        if binary.is_file() and stamp.is_file() and (self.install/'carbon/managed/Carbon.dll').is_file():return binary
        self.note('DOWNLOADING', 'Downloading SteamCMD and the official Rust dedicated server (several GB)')
        steam = self.root/'steamcmd';steam.mkdir(exist_ok=True)
        if not (steam/'steamcmd.exe').is_file():
            archive = self.root/'steamcmd.zip';download(STEAMCMD_URL, archive, self.cancel, maximum=16*1024*1024)
            extract_zip(archive, steam, 64*1024*1024)
        with (self.directory/'installation.log').open('wb') as output:
            self.process = subprocess.Popen([str(steam/'steamcmd.exe'), '+force_install_dir', str(self.install),
                '+login', 'anonymous', '+app_update', '258550', 'validate', '+quit'], cwd=steam,
                stdout=output, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
            self._wait_process(7200)
            if self.process.returncode or not binary.is_file():raise RuntimeError('SteamCMD could not install Rust. See installation.log')
        if self.cancel.is_set():raise InterruptedError()
        self.note('DOWNLOADING', 'Installing the Carbon server plugin loader')
        request = urllib.request.Request(CARBON_RELEASE, headers={'User-Agent': 'Ruster-Live-Preview', 'Accept': 'application/vnd.github+json'})
        with urllib.request.urlopen(request, timeout=30) as response:release = json.loads(response.read(2*1024*1024))
        asset = next((a for a in release['assets'] if a['name'] == 'Carbon.Windows.Release.zip'), None)
        if asset is None:raise ValueError('The official Carbon release has no Windows server archive')
        url = asset['browser_download_url'];digest = asset.get('digest') or ''
        if not url.startswith('https://github.com/CarbonCommunity/Carbon/releases/download/') or not digest.startswith('sha256:'):
            raise ValueError('Carbon release has no trusted URL and SHA256 digest')
        archive = self.root/'carbon.zip';download(url, archive, self.cancel, digest=digest[7:])
        extract_zip(archive, self.install)
        atomic_write(stamp, json.dumps({'carbon': release['tag_name'], 'sha256': digest[7:]}, indent=2).encode())
        return binary

    def _wait_process(self, timeout):
        deadline = time.monotonic()+timeout
        while self.process.poll() is None:
            if self.cancel.wait(.2):raise InterruptedError()
            if time.monotonic() > deadline:raise TimeoutError('Preview process timed out')

    def _run(self):
        try:
            binary = self._install()
            if self.cancel.is_set():raise InterruptedError()
            check_ports(self.port)
            plugins = self.install/'carbon/plugins';plugins.mkdir(parents=True, exist_ok=True)
            source = Path(__file__).resolve().parents[1]/'preview_native/RusterPreview.cs'
            atomic_write(plugins/'RusterPreview.cs', source.read_bytes())
            self._serve_map()
            atomic_write(self.directory/'config.json', json.dumps({'owner': self.owner, 'url': self.url}).encode())
            atomic_write(self.directory/'active.flag', b'Ruster local preview\n')
            import os
            env = {**os.environ, 'RUSTER_PREVIEW_DIR': str(self.directory)}
            self.note('STARTING', 'Starting the private Rust server; waiting for the preview plugin')
            self.process = subprocess.Popen(command(binary, self.identity, self.port, self.url, self.log),
                cwd=self.install, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW)
            deadline = time.monotonic()+900
            while not self.cancel.wait(.2):
                if self.process.poll() is not None:raise RuntimeError(f'Preview server exited ({self.process.returncode}); see server.log')
                if (self.directory/'server.blocked').exists():
                    raise RuntimeError((self.directory/'server.blocked').read_text()[:4096])
                with self.lock:
                    pending, self.pending = self.pending, None
                if pending is not None:
                    self.revision += 1;write_snapshot(self.directory, self.revision, pending)
                if (self.directory/'server.ready').is_file() and self.status != 'RUNNING':
                    verify_server_ready(self.directory/'server.ready')
                    self.note('RUNNING', 'Local server ready · EAC disabled')
                if self.status != 'RUNNING' and time.monotonic() > deadline:
                    raise TimeoutError('The preview plugin did not become ready within 15 minutes. See server.log')
                if self.status != 'RUNNING' and any('PlayerPrefsException' in line for line in self.log_tail(12)):
                    raise RuntimeError('Rust server startup could not write its preferences. See server.log')
            self.note('STOPPED', 'Local preview stopped')
        except InterruptedError:self.note('STOPPED', 'Preview setup cancelled')
        except Exception as error:self.note('FAILED', str(error))
        finally:
            self._stop_marker()
            if self.process and self.process.poll() is None:
                self.process.terminate()
                try:self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:self.process.kill();self.process.wait(timeout=5)
            if self.http:self.http.shutdown();self.http.server_close()

    def update(self, placements):
        if not self.active:return
        from .preview_protocol import validate_placements
        validate_placements(placements)
        with self.lock:self.pending = placements

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
                'directory': str(self.directory), 'revision': self.revision, 'events': list(self.events)}

    def log_tail(self, lines=8):
        values = []
        for path in (self.root/'steamcmd/logs/console_log.txt', self.directory/'installation.log', self.log,
                     self.directory/'server.status', self.directory/'client.status'):
            try:
                with path.open('rb') as handle:handle.seek(max(0, path.stat().st_size-8192));value = handle.read(8192)
                values.extend(value.decode('utf8', errors='replace').splitlines()[-lines:])
            except OSError:pass
        return values[-lines:]
