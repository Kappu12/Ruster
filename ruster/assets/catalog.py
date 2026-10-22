from pathlib import Path
import sqlite3
from contextlib import closing


def connect(cache):
    Path(cache).mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(Path(cache) / 'catalog.sqlite3', timeout=30)
    db.executescript('''
    CREATE TABLE IF NOT EXISTS bundles(path TEXT PRIMARY KEY, size INTEGER, mtime INTEGER);
    CREATE TABLE IF NOT EXISTS assets(path TEXT PRIMARY KEY, bundle TEXT, file TEXT, path_id INTEGER);
    CREATE TABLE IF NOT EXISTS names(uid INTEGER PRIMARY KEY, path TEXT);
    CREATE TABLE IF NOT EXISTS failures(bundle TEXT PRIMARY KEY, error TEXT);
    CREATE TABLE IF NOT EXISTS serialized_files(name TEXT PRIMARY KEY, bundle TEXT);
    CREATE TABLE IF NOT EXISTS roots(name TEXT, bundle TEXT, file TEXT, path_id INTEGER,
                                     PRIMARY KEY(bundle,file,path_id));
    ''')
    return db


def search(cache, query='', limit=100, offset=0):
    if not (Path(cache) / 'catalog.sqlite3').exists():
        return []
    with closing(sqlite3.connect((Path(cache)/'catalog.sqlite3').resolve().as_uri()+'?mode=ro',uri=True,timeout=1)) as db:
        query=query.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
        return db.execute('''SELECT n.uid, n.path, a.bundle IS NOT NULL FROM names n
            LEFT JOIN assets a ON lower(a.path)=lower(n.path)
            WHERE n.path LIKE ? ESCAPE '\\' ORDER BY n.path LIMIT ? OFFSET ?''',
            ('%' + query + '%', limit, max(0,offset))).fetchall()


def find(cache, uid):
    if not (Path(cache)/'catalog.sqlite3').exists():return None
    with closing(sqlite3.connect((Path(cache)/'catalog.sqlite3').resolve().as_uri()+'?mode=ro',uri=True,timeout=1)) as db:
        return db.execute('''SELECT n.path, a.bundle, a.file, a.path_id FROM names n
            LEFT JOIN assets a ON lower(a.path)=lower(n.path) WHERE n.uid=?''', (uid,)).fetchone()


def parse_lookup(text):
    """Rust SDK Prefabs.txt: Unity GUID, numeric Rust UID, asset path."""
    for line in text.splitlines():
        parts = [p.strip() for p in line.split(',', 2)]
        if len(parts) == 3 and parts[1].isdigit() and parts[2].lower().endswith('.prefab'):
            uid = int(parts[1])
            if 0 <= uid <= 0xFFFFFFFF:
                yield uid, parts[2].lower()


def parse_manifest(tree):
    """Read explicit string/ID pairs from an embedded GameManifest type tree."""
    if isinstance(tree, dict):
        path = next((tree[k] for k in ('str', 'path', 'string', 'assetPath')
                     if isinstance(tree.get(k), str) and tree[k].lower().endswith('.prefab')), None)
        uid = next((tree[k] for k in ('hash', 'id', 'uid')
                    if isinstance(tree.get(k), int) and 0 <= tree[k] <= 0xFFFFFFFF), None)
        if path is not None and uid is not None:
            yield uid, path.lower()
        for value in tree.values():
            yield from parse_manifest(value)
    elif isinstance(tree, list):
        for value in tree:
            yield from parse_manifest(value)
