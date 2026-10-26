"""Choose one map-only preload marker for every installed Rust asset scene."""
import json
from pathlib import Path
import re
import sqlite3

MAX_MANIFEST = 8*1024*1024
WARMUP_CATEGORY = b'RusterPreviewWarmup'


def scenes(path):
    path = Path(path)
    if path.stat().st_size > MAX_MANIFEST:raise ValueError('Prefab pack manifest exceeds 8 MiB')
    rows = json.loads(path.read_text(encoding='utf-8-sig')).get('Scenes')
    if not isinstance(rows, list) or not 0 < len(rows) <= 4096:raise ValueError('Invalid prefab pack manifest')
    result = {}
    for row in rows:
        if not isinstance(row, dict):raise ValueError('Invalid prefab pack entry')
        name = row.get('Name');assets = row.get('IncludedAssets')
        if not isinstance(name, str) or not re.fullmatch(r'AssetScene-[\w.\-]+', name) or name in result:
            raise ValueError('Invalid or duplicate prefab pack name')
        if not isinstance(assets, list) or len(assets) > 100000:raise ValueError('Invalid prefab pack asset list')
        paths = set()
        for asset in assets:
            if not isinstance(asset, str):raise ValueError('Invalid prefab pack asset path')
            asset = asset.lower()
            if not asset.startswith('assets/') or '..' in asset or '\\' in asset or '\0' in asset:
                raise ValueError('Invalid prefab pack asset path')
            if not asset.endswith('.prefab'):continue
            paths.add(asset)
        if not paths:raise ValueError('Prefab pack has no preload asset: '+name)
        result[name] = paths
    return result


def representative(path):
    """Prefer simple props/effects over system managers where a choice exists."""
    name = Path(path).stem
    preferred = bool(re.search(r'(?:^|[_ .-])(cube|wall|floor|rock|pipe|pallet|crate|bowl|debris)(?:$|[_ .-])', name))
    system = '/system/' in path or '/monument/' in path
    return (path != 'assets/bundled/prefabs/modding/cubes/concrete_cube.prefab', system, not preferred, len(path), path)


def plan(client_manifest, server_manifest, catalog):
    client, server = scenes(client_manifest), scenes(server_manifest)
    with sqlite3.connect(Path(catalog).resolve().as_uri()+'?mode=ro', uri=True, timeout=1) as db:
        rows = db.execute('SELECT uid,path FROM names LIMIT 100001').fetchall()
    if len(rows) > 100000:raise ValueError('Prefab catalog exceeds preload limits')
    names = {path.lower(): uid for uid, path in rows if isinstance(path, str) and type(uid) is int and 0 < uid < 2**32}
    markers = []
    for name in sorted(client.keys() | server.keys()):
        candidates = client.get(name, set()) & server.get(name, set()) & names.keys()
        if not candidates:
            raise ValueError('Cannot preload every prefab pack: '+name+' has no shared catalog prefab. Update Rust, its local server and the asset catalog.')
        path = min(candidates, key=representative)
        markers.append({'scene': name, 'path': path, 'uid': names[path]})
    return markers
