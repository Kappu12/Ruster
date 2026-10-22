"""Run in a separate Python process: no bpy, no UI thread work, no game injection.

Reads Unity AssetBundles using UnityPy. Catalogs prefab containers and the
official embedded ID lookup. Exports hierarchy, triangle meshes, UVs and base
color textures. Unity shaders/behaviours are not executed.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
if os.environ.get('RUSTER_PYTHON_MODULES'):
    sys.path.insert(0, os.environ['RUSTER_PYTHON_MODULES'])

from ruster.assets.catalog import connect, find, parse_lookup, parse_manifest
from ruster.core.settings import validate_install
from ruster.core.project import atomic_write


def status(cache, **values):
    atomic_write(Path(cache) / 'progress.json', json.dumps(values).encode())


def bundle_files(root):
    for path in sorted((Path(root) / 'Bundles').rglob('*')):
        if not path.is_file():
            continue
        try:
            with path.open('rb') as stream:
                if stream.read(8).startswith((b'UnityFS', b'UnityWeb', b'UnityRaw')):
                    yield path
        except OSError:
            continue


def component_pointers(gameobject):
    for entry in gameobject.m_Component:
        yield entry[1] if isinstance(entry, tuple) else entry.component


def run_child(action, install, cache, **options):
    command = [sys.executable, str(Path(__file__).resolve()), action,
               '--install', str(install), '--cache', str(cache), '--parent-pid', str(os.getpid())]
    for key, value in options.items():
        command += ['--' + key.replace('_', '-'), str(value)]
    kwargs = {'creationflags': subprocess.CREATE_NO_WINDOW} if sys.platform == 'win32' else {}
    try:
        result = subprocess.run(command, timeout=120, **kwargs)
    except subprocess.TimeoutExpired as error:
        raise RuntimeError('Asset operation exceeded its 120 second limit') from error
    if result.returncode:
        raise RuntimeError('Asset worker failed or reached its 768 MiB memory limit; see worker.log')


def index_bundle(install, cache, key):
    from ruster.assets.streaming import streamed_bundles
    root = validate_install(install)
    path = (root / key).resolve()
    if not path.is_relative_to(root.resolve()):raise ValueError('Bundle path escapes the Rust installation')
    stat = path.stat()
    db = connect(cache)
    try:
        with streamed_bundles() as UnityPy:
            env = UnityPy.load(str(path))
            entries, names, roots = [], [], []
            for asset_path, pointer in env.container.items():
                if asset_path.lower().endswith('.prefab'):
                    reader = pointer.deref()
                    if reader and reader.type.name == 'GameObject':
                        entries.append((asset_path.lower(), key, reader.assets_file.name, reader.path_id))
                elif asset_path.lower().endswith('manifest.asset'):
                    names.extend(parse_manifest(pointer.deref().read_typetree()))
            for obj in env.objects:
                if obj.type.name == 'TextAsset':
                    data = obj.read()
                    name = data.m_Name.lower()
                    if 'prefab' in name or 'stringpool' in name:
                        script = data.m_Script
                        text = script.decode('utf8', errors='replace') if isinstance(script, bytes) else script
                        names.extend(parse_lookup(text))
            # Keep scene roots for a second pass after all lookup tables are read.
            for obj in env.objects:
                if obj.type.name != 'GameObject':
                    continue
                go = obj.read()
                for pointer in component_pointers(go):
                    if not pointer.path_id:
                        continue
                    component = pointer.deref()
                    if component.type.name == 'Transform' and not component.read().m_Father.path_id:
                        roots.append((go.m_Name.lower(), key, obj.assets_file.name, obj.path_id))
                        break
            with db:
                db.execute('DELETE FROM assets WHERE bundle=?', (key,))
                db.executemany('INSERT OR REPLACE INTO assets VALUES(?,?,?,?)', entries)
                db.executemany('INSERT OR REPLACE INTO names VALUES(?,?)', names)
                db.execute('DELETE FROM roots WHERE bundle=?', (key,))
                db.executemany('INSERT OR REPLACE INTO roots VALUES(?,?,?,?)', roots)
                db.execute('DELETE FROM serialized_files WHERE bundle=?', (key,))
                db.executemany('INSERT OR REPLACE INTO serialized_files VALUES(?,?)',
                               [(asset.name.rsplit('/',1)[-1].lower(), key) for asset in env.assets])
                db.execute('INSERT OR REPLACE INTO bundles VALUES(?,?,?)', (key, stat.st_size, stat.st_mtime_ns))
                db.execute('DELETE FROM failures WHERE bundle=?', (key,))
    finally:
        db.close()


def index(install, cache):
    root = validate_install(install)
    files = list(bundle_files(root))
    if not files:
        raise ValueError('No Unity AssetBundles found in this Rust installation')
    db = connect(cache)
    known = set()
    try:
        for i, path in enumerate(files):
            key = str(path.relative_to(root))
            known.add(key)
            stat = path.stat()
            old = db.execute('SELECT size, mtime FROM bundles WHERE path=?', (key,)).fetchone()
            if old == (stat.st_size, stat.st_mtime_ns):continue
            status(cache, state='INDEXING', current=i + 1, total=len(files), item=path.name)
            try:
                # One short-lived child per bundle releases UnityPy object graphs
                # and native decompression buffers even if cyclic references remain.
                run_child('index-bundle', root, cache, bundle=key)
            except Exception as error:
                with db:
                    db.execute('INSERT OR REPLACE INTO failures VALUES(?,?)', (key, str(error)))
        # Remove records for bundles removed by a Rust update.
        with db:
            for (key,) in db.execute('SELECT path FROM bundles').fetchall():
                if key not in known:
                    db.execute('DELETE FROM assets WHERE bundle=?', (key,))
                    db.execute('DELETE FROM roots WHERE bundle=?', (key,))
                    db.execute('DELETE FROM serialized_files WHERE bundle=?', (key,))
                    db.execute('DELETE FROM bundles WHERE path=?', (key,))
            by_name = {}
            for uid, asset_path in db.execute('SELECT uid,path FROM names'):
                by_name.setdefault(Path(asset_path).stem.lower(), []).append(asset_path)
            for name, matching in by_name.items():
                if len(matching) != 1:
                    continue
                roots = db.execute('SELECT bundle,file,path_id FROM roots WHERE name=?',(name,)).fetchall()
                if len(roots) == 1:
                    db.execute('INSERT OR IGNORE INTO assets VALUES(?,?,?,?)',(matching[0],*roots[0]))
        count = db.execute('SELECT count(*) FROM assets').fetchone()[0]
        ids = db.execute('SELECT count(*) FROM names').fetchone()[0]
        failures = db.execute('SELECT count(*) FROM failures').fetchone()[0]
        if not ids:
            raise ValueError('No embedded prefab ID lookup was found. This Rust build needs an updated lookup adapter.')
        status(cache, state='READY', assets=count, ids=ids, failures=failures,
               install=str(root), current=len(files), total=len(files))
    finally:
        db.close()


def xyz(value):
    return [float(value.x), float(value.y), float(value.z)]


def quaternion(value):
    return [float(value.w), float(value.x), float(value.y), float(value.z)]


def deref(pointer):
    return pointer.read() if pointer and pointer.path_id else None


def export_prefab(env, root_reader, output, uid, asset_path, cache_signature=''):
    from UnityPy.helpers.MeshHelper import MeshHandler
    meshes, materials, nodes, warnings = {}, {}, [], []
    excluded_renderers=set()
    seen = set()
    base = Path(output).parent
    texture_dir = base / 'textures'
    texture_dir.mkdir(parents=True, exist_ok=True)

    def key(reader):
        return f'{reader.assets_file.name}:{reader.path_id}'

    def material(pointer):
        if not pointer or not pointer.path_id:
            return None
        reader = pointer.deref()
        ident = key(reader)
        if ident in materials:
            return ident
        data = reader.read()
        entry = {'name': data.m_Name, 'color': [0.55, 0.55, 0.55, 1.], 'texture': None}
        materials[ident] = entry
        floats=dict(data.m_SavedProperties.m_Floats)
        entry['roughness']=max(0.,min(1.,1-floats.get('_Smoothness',floats.get('_Glossiness',.2))))
        entry['metallic']=max(0.,min(1.,floats.get('_Metallic',0.)))
        entry['alpha_clip']=bool(floats.get('_AlphaClip',0) or floats.get('_Mode',0))
        colors = dict(data.m_SavedProperties.m_Colors)
        color = colors.get('_BaseColor', colors.get('_Color'))
        if color:
            entry['color'] = [color.r, color.g, color.b, color.a]
        textures = dict(data.m_SavedProperties.m_TexEnvs)
        texenv = textures.get('_BaseMap', textures.get('_MainTex'))
        if texenv and texenv.m_Texture.path_id:
            entry['uv_scale']=[texenv.m_Scale.x,texenv.m_Scale.y]
            entry['uv_offset']=[texenv.m_Offset.x,texenv.m_Offset.y]
            try:
                tex_reader = texenv.m_Texture.deref()
                token = hashlib.sha256((key(tex_reader)+':'+cache_signature).encode()).hexdigest()[:24]
                texture = texture_dir / f'{token}.png'
                if not texture.exists():
                    tex_reader.read().image.save(texture)
                entry['texture'] = str(texture.relative_to(base))
            except Exception as error:
                warnings.append(f'{data.m_Name}: texture unavailable: {error}')
        return ident

    def mesh(pointer):
        reader = pointer.deref()
        ident = key(reader)
        if ident not in meshes:
            handler = MeshHandler(reader.read())
            handler.process()
            triangles = handler.get_triangles()
            meshes[ident] = {'vertices': handler.m_Vertices or [],
                             'uv': handler.m_UV0 or [], 'submeshes': triangles}
        return ident

    def walk(reader, parent=None, depth=0,lod_managed=False):
        if depth > 128 or len(nodes) > 20000:
            raise ValueError('Prefab hierarchy exceeds the supported limit')
        ident = key(reader)
        if ident in seen:
            return
        seen.add(ident)
        go = reader.read()
        if parent is not None and not go.m_IsActive:
            return
        # Prefab instances retain one visible LOD, not all overlapping LOD meshes.
        if not lod_managed and re.search(r'(?:_|\b)lod[1-9]\d*(?:_|\b)', go.m_Name.lower()):
            return
        components = {}
        component_keys={}
        for pointer in component_pointers(go):
            component_reader = pointer.deref()
            if component_reader:
                components[component_reader.type.name] = component_reader.read()
                component_keys[component_reader.type.name]=key(component_reader)
        lods=getattr(components.get('LODGroup'),'m_LODs',None)
        if lods:
            first=set()
            later=set()
            first_nonempty=next((i for i,lod in enumerate(lods) if any(r.renderer.path_id for r in lod.renderers)),0)
            for index,lod in enumerate(lods):
                for renderer in lod.renderers:
                    pointer=renderer.renderer
                    if pointer and pointer.path_id:
                        (first if index==first_nonempty else later).add(key(pointer.deref()))
            excluded_renderers.update(later-first)
        transform = components.get('Transform') or components.get('RectTransform')
        if transform is None:
            return
        index = len(nodes)
        node = {'name': go.m_Name, 'parent': parent,
                'position': xyz(transform.m_LocalPosition),
                'rotation': quaternion(transform.m_LocalRotation),
                'scale': xyz(transform.m_LocalScale), 'mesh': None, 'materials': []}
        nodes.append(node)
        renderer = components.get('MeshRenderer') or components.get('SkinnedMeshRenderer')
        filter_ = components.get('MeshFilter') or components.get('SkinnedMeshRenderer')
        renderer_key=component_keys.get('MeshRenderer',component_keys.get('SkinnedMeshRenderer'))
        if renderer and filter_ and renderer_key not in excluded_renderers and getattr(renderer, 'm_Enabled', True):
            try:
                if filter_.m_Mesh.path_id:
                    node['mesh'] = mesh(filter_.m_Mesh)
                    node['materials'] = [material(p) for p in renderer.m_Materials]
            except Exception as error:
                warnings.append(f'{go.m_Name}: geometry unavailable: {error}')
        for child in transform.m_Children:
            child_transform = deref(child)
            if child_transform:
                walk(child_transform.m_GameObject.deref(), index, depth + 1,lod_managed or bool(lods))

    walk(root_reader)
    if not meshes:
        raise ValueError('Prefab has no readable triangle meshes; ' + '; '.join(warnings[:3]))
    result = {'schema': 1, 'uid': uid, 'path': asset_path, 'nodes': nodes,
              'meshes': meshes, 'materials': materials, 'warnings': warnings}
    atomic_write(output, gzip.compress(json.dumps(result).encode(), compresslevel=3))
    return warnings


def extract_one(install, cache, uid):
    from ruster.assets.streaming import streamed_bundles
    with streamed_bundles() as UnityPy:
        return extract_batch(UnityPy, install, cache, [uid])


def extract_batch(UnityPy, install, cache, ids):
    root = validate_install(install)
    cache = Path(cache)
    target = cache / 'prefabs'
    target.mkdir(parents=True, exist_ok=True)
    failures, done = [], 0
    current_bundle, env = None, None
    with connect(cache) as db:
        cab_bundles = dict(db.execute('SELECT name,bundle FROM serialized_files'))
        catalog_signature=hashlib.sha256(repr(db.execute('SELECT path,size,mtime FROM bundles ORDER BY path').fetchall()).encode()).hexdigest()

    class LocalEnvironment(UnityPy.Environment):
        def find_file(self, name, is_dependency=True):
            clean = name.rsplit('/',1)[-1].lower()
            existing = self.get_cab(clean)
            if existing:
                return existing
            bundle = cab_bundles.get(clean)
            if bundle:
                self.load_file(str(root/bundle), is_dependency=True)
                existing = self.get_cab(clean)
                if existing:
                    return existing
            return super().find_file(name, is_dependency)
    # Group by bundle to avoid reloading it for every prefab in the same batch.
    jobs = []
    for uid in sorted(set(ids)):
        entry = find(cache, uid)
        if entry and entry[1]:
            jobs.append((entry[1], uid, entry))
        else:
            failures.append({'uid': uid, 'error': 'No matching prefab in the local asset catalog'})
    for bundle, uid, (asset_path, _, file_name, path_id) in sorted(jobs):
        status(cache, state='EXTRACTING', current=done, total=len(jobs), item=asset_path)
        try:
            path = root / bundle
            stat = path.stat()
            signature = f'converter-2:{stat.st_size}:{stat.st_mtime_ns}:{catalog_signature}'
            stamp = target / f'{uid}.stamp'
            output = target / f'{uid}.json.gz'
            if not (output.exists() and stamp.exists() and stamp.read_text() == signature):
                if bundle != current_bundle:
                    env = LocalEnvironment(str(path))
                    current_bundle = bundle
                reader = next((o for o in env.objects if o.path_id == path_id and o.assets_file.name == file_name), None)
                if reader is None:
                    raise ValueError('Prefab object is no longer in the indexed bundle; rebuild the catalog')
                warnings = export_prefab(env, reader, output, uid, asset_path,signature)
                atomic_write(stamp, signature.encode())
                if warnings:
                    failures.append({'uid': uid, 'error': '; '.join(warnings)})
            done += 1
        except Exception as error:
            failures.append({'uid': uid, 'error': str(error)})
    return {'failures': failures, 'done': done}


def extract(install, cache, ids):
    from tempfile import TemporaryDirectory
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    failures, done = [], 0
    ids = sorted(set(ids))
    for uid in ids:
        entry = find(cache, uid)
        status(cache, state='EXTRACTING', current=done, total=len(ids),
               item=entry[0] if entry else str(uid))
        # The child writes its own report; retain aggregate progress in the parent.
        with TemporaryDirectory(prefix='asset-report-', dir=cache) as directory:
            report = Path(directory) / 'report.json'
            try:
                run_child('extract-one', install, cache, uid=uid, report=report)
                result = json.loads(report.read_text())
                failures.extend(result['failures'])
                done += result['done']
            except Exception as error:
                failures.append({'uid': uid, 'error': str(error)})
    atomic_write(cache / 'asset-report.json', json.dumps(failures, indent=2).encode())
    status(cache, state='READY', extracted=done, failures=len(failures), current=len(ids), total=len(ids))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['index', 'extract', 'index-bundle', 'extract-one'])
    parser.add_argument('--install', required=True)
    parser.add_argument('--cache', required=True)
    parser.add_argument('--ids-file')
    parser.add_argument('--bundle')
    parser.add_argument('--uid', type=int)
    parser.add_argument('--report')
    parser.add_argument('--parent-pid', type=int)
    args = parser.parse_args()
    try:
        from ruster.core.process_limits import protect_process, ASSET_MEMORY, MIB
        child = args.action in ('index-bundle', 'extract-one')
        protect_process(ASSET_MEMORY if child else 1024 * MIB, args.parent_pid)
        # Avoid BLAS thread pools/reservations in metadata and conversion workers.
        os.environ['OPENBLAS_NUM_THREADS'] = '1'
        os.environ['OMP_NUM_THREADS'] = '1'
        if args.action == 'index-bundle':
            index_bundle(args.install, args.cache, args.bundle)
        elif args.action == 'extract-one':
            result = extract_one(args.install, args.cache, args.uid)
            atomic_write(args.report, json.dumps(result).encode())
        elif args.action == 'index':
            index(args.install, args.cache)
        else:
            ids = json.loads(Path(args.ids_file).read_text())
            extract(args.install, args.cache, ids)
    except Exception as error:
        status(args.cache, state='ERROR', error=str(error))
        traceback.print_exc()
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
