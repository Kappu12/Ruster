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
    CREATE INDEX IF NOT EXISTS assets_path_nocase ON assets(path COLLATE NOCASE);
    CREATE INDEX IF NOT EXISTS names_path_nocase ON names(path COLLATE NOCASE,uid);
    CREATE TABLE IF NOT EXISTS failures(bundle TEXT PRIMARY KEY, error TEXT);
    CREATE TABLE IF NOT EXISTS serialized_files(name TEXT PRIMARY KEY, bundle TEXT);
    CREATE TABLE IF NOT EXISTS roots(name TEXT, bundle TEXT, file TEXT, path_id INTEGER,
                                     PRIMARY KEY(bundle,file,path_id));
    ''')
    return db


def literal(value):
    return value.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')


AVAILABLE="EXISTS(SELECT 1 FROM assets a WHERE a.path=n.path COLLATE NOCASE AND a.bundle IS NOT NULL)"


def filters(query='',category='',favorites=None,available_only=False):
    conditions=["n.path LIKE ? ESCAPE char(92)"]
    args=['%'+literal(query)+'%']
    if category:
        conditions.append("n.path LIKE ? ESCAPE char(92)")
        args.append(literal(category.rstrip('/')+'/')+'%')
    if favorites is not None:
        ids=list(favorites)
        if len(ids)>512:raise ValueError('A favorite palette supports at most 512 prefabs')
        conditions.append('n.uid IN ('+','.join('?' for _ in ids)+')' if ids else '0')
        args.extend(ids)
    if available_only:conditions.append(AVAILABLE)
    return ' AND '.join(conditions),args


def read_connection(cache):
    return sqlite3.connect((Path(cache)/'catalog.sqlite3').resolve().as_uri()+'?mode=ro',uri=True,timeout=1)


def rows(db,where,args,limit,offset):
    return db.execute('SELECT n.uid,n.path,'+AVAILABLE+' FROM names n WHERE '+where+
        ' ORDER BY n.path COLLATE NOCASE,n.uid LIMIT ? OFFSET ?',(*args,limit,max(0,offset))).fetchall()


def search(cache, query='', limit=100, offset=0, category='', favorites=None, available_only=False):
    if not (Path(cache)/'catalog.sqlite3').exists():return []
    where,args=filters(query,category,favorites,available_only)
    with closing(read_connection(cache)) as db:
        return rows(db,where,args,limit,offset)


def page(cache,query='',page_index=0,page_size=12,category='',favorites=None,available_only=False):
    """Return counts and a valid browser page from one consistent read snapshot."""
    if page_size<1:raise ValueError('Page size must be positive')
    if not (Path(cache)/'catalog.sqlite3').exists():return {'rows':[],'total':0,'page':0,'pages':0}
    where,args=filters(query,category,favorites,available_only)
    with closing(read_connection(cache)) as db:
        db.execute('BEGIN')
        total=db.execute('SELECT COUNT(*) FROM names n WHERE '+where,args).fetchone()[0]
        pages=(total+page_size-1)//page_size
        current=min(max(0,page_index),max(0,pages-1))
        return {'rows':rows(db,where,args,page_size,current*page_size),'total':total,'page':current,'pages':pages}


def categories(cache):
    path=Path(cache)/'catalog.sqlite3'
    if not path.exists():return []
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=1)) as db:
        names=db.execute('SELECT path FROM names').fetchall()
    counts={}
    for (name,) in names:
        parts=name.split('/')[:-1]
        index=(parts.index('prefabs')+2) if 'prefabs' in parts else min(3,len(parts))
        prefix='/'.join(parts[:index])
        if prefix:counts[prefix]=counts.get(prefix,0)+1
    return sorted(counts.items())


def find(cache, uid):
    if not (Path(cache)/'catalog.sqlite3').exists():return None
    with closing(sqlite3.connect((Path(cache)/'catalog.sqlite3').resolve().as_uri()+'?mode=ro',uri=True,timeout=1)) as db:
        return db.execute('''SELECT n.path, a.bundle, a.file, a.path_id FROM names n
            LEFT JOIN assets a ON a.path=n.path COLLATE NOCASE WHERE n.uid=?
            ORDER BY a.bundle IS NOT NULL DESC,(a.path=n.path) DESC,a.path LIMIT 1''', (uid,)).fetchone()


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
