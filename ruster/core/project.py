"""Versioned .ruster ZIP container. Never extracts arbitrary archive paths."""
from pathlib import Path
import hashlib
import json
import os
import tempfile
import zipfile
from .wire import FormatError

SCHEMA = 1
MAX_MEMBER = 1024 * 1024 * 1024
MAX_TOTAL = 2 * MAX_MEMBER


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=f'.{path.name}.', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def save(path, blend_path, mode, source_map=None, title='Untitled'):
    if mode not in ('BLENDER', 'MAP'):
        raise FormatError('Invalid project mode')
    files = {'scene.blend': Path(blend_path)}
    if source_map:
        files['source.map'] = Path(source_map)
    if mode == 'MAP' and 'source.map' not in files:
        raise FormatError('Map projects require their source map')
    manifest = {'format': 'ruster', 'schema': SCHEMA, 'app_version': '0.1.0',
                'title': title, 'mode': mode, 'files': {}}
    for name, file in files.items():
        if file.stat().st_size > MAX_MEMBER:
            raise FormatError('Project member exceeds the size limit')
        with file.open('rb') as stream:
            manifest['files'][name] = hashlib.file_digest(stream, 'sha256').hexdigest()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=f'.{path.name}.', dir=path.parent)
    os.close(fd)
    try:
        with zipfile.ZipFile(temp, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=3) as archive:
            archive.writestr('manifest.json', json.dumps(manifest, indent=2))
            for name, file in files.items():
                archive.write(file, name)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def unpack(path, destination):
    """Validate the whole project before writing anything to its private cache."""
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        allowed = {'manifest.json', 'scene.blend', 'source.map'}
        if len(names) != len(set(names)) or set(names) - allowed:
            raise FormatError('Unexpected or duplicate project members')
        if not {'manifest.json', 'scene.blend'} <= set(names):
            raise FormatError('Missing project manifest or scene')
        if any(i.file_size > MAX_MEMBER for i in archive.infolist()) or sum(i.file_size for i in archive.infolist()) > MAX_TOTAL:
            raise FormatError('Project exceeds the size limit')
        if archive.getinfo('manifest.json').file_size > 65536:
            raise FormatError('Manifest is too large')
        manifest = json.loads(archive.read('manifest.json'))
        if manifest.get('format') != 'ruster' or manifest.get('schema') != SCHEMA:
            raise FormatError('Unsupported .ruster project version')
        if manifest.get('mode') not in ('BLENDER', 'MAP'):
            raise FormatError('Invalid project mode')
        hashes = manifest.get('files', {})
        expected = set(names) - {'manifest.json'}
        if set(hashes) != expected or (manifest['mode'] == 'MAP' and 'source.map' not in expected):
            raise FormatError('Project file list does not match its manifest')
        content = {name: archive.read(name) for name in expected}
        for name, data in content.items():
            if hashlib.sha256(data).hexdigest() != hashes[name]:
                raise FormatError(f'Project integrity check failed: {name}')
        if not content['scene.blend'].startswith((b'BLENDER', b'\x28\xb5\x2f\xfd', b'\x1f\x8b')):
            raise FormatError('Invalid Blender scene')
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for name, data in content.items():
        atomic_write(destination / name, data)
    return manifest
