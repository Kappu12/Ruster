"""Fast catalog from shipped manifests; no game geometry or bundle scan."""
import json
import os
from pathlib import Path
import re
import time
from contextlib import closing
from . import catalog

MAX_METADATA=8*1024*1024


def rustedit_root(configured=None):
    if configured:
        path=Path(configured)
        return path if (path/'stringpool.txt').is_file() else None
    candidates=[]
    for key,default in [('ProgramFiles(x86)','C:/Program Files (x86)'),('ProgramFiles','C:/Program Files')]:
        candidates.append(Path(os.environ.get(key,default))/'RustEdit')
    return next((path for path in candidates if (path/'stringpool.txt').is_file()),None)


def read_text(path):
    if path.stat().st_size>MAX_METADATA:raise ValueError('Catalog metadata exceeds 8 MiB')
    return path.read_text(encoding='utf-8-sig')


def pool_records(text):
    for line in text.splitlines():
        match=re.fullmatch(r'(\d+) - (assets/.+\.prefab)',line,re.IGNORECASE)
        if match:
            uid=int(match[1])
            if 0<uid<=0xffffffff:yield uid,match[2].lower()


def refresh(install,cache,rustedit=None):
    started=time.monotonic();install=Path(install).resolve()
    manifest=install/'Bundles/AssetSceneManifest.json'
    editor=rustedit_root(rustedit)
    pool=editor/'stringpool.txt' if editor else install/'stringpool.txt'
    if not manifest.is_file() or not pool.is_file():
        raise ValueError('Fast catalog requires Rust Bundles/AssetSceneManifest.json and a local RustEdit stringpool.txt. Set the RustEdit folder in Preferences.')
    signature=json.dumps([(str(p),p.stat().st_size,p.stat().st_mtime_ns) for p in (manifest,pool)],separators=(',',':'))
    with closing(catalog.connect(cache)) as db:
        db.execute('CREATE TABLE IF NOT EXISTS catalog_metadata(key TEXT PRIMARY KEY,value TEXT)')
        old=db.execute("SELECT value FROM catalog_metadata WHERE key='signature'").fetchone()
        if old and old[0]==signature:
            count=db.execute('SELECT COUNT(*) FROM names').fetchone()[0]
            available=db.execute('SELECT COUNT(*) FROM assets').fetchone()[0]
            return {'ids':count,'assets':available,'cached':True,'seconds':time.monotonic()-started,'source':str(pool),'install':str(install)}
        data=json.loads(read_text(manifest))
        scenes=data.get('Scenes')
        if not isinstance(scenes,list) or len(scenes)>4096:raise ValueError('Invalid asset scene manifest')
        rows=list(pool_records(read_text(pool)))
        if not rows or len(rows)>100000:raise ValueError('Invalid prefab string pool')
        known={path for _,path in rows};assets=[]
        bundle=install/'Bundles/shared/assetscenes.bundle'
        if bundle.is_file():
            for scene in scenes:
                name=scene.get('Name');paths=scene.get('IncludedAssets',[])
                if not isinstance(name,str) or not re.fullmatch(r'AssetScene-[\w.\-]+',name):
                    raise ValueError('Invalid asset scene name')
                if not isinstance(paths,list):raise ValueError('Invalid scene asset list')
                for path in paths:
                    if isinstance(path,str) and path.lower() in known:
                        assets.append((path.lower(),'Bundles/shared/assetscenes.bundle','@scene:'+name,0))
        with db:
            # These tables are generated metadata, never project or game data.
            for table in ('names','assets','bundles','roots','serialized_files','failures'):
                db.execute('DELETE FROM '+table)
            db.executemany('INSERT OR REPLACE INTO names VALUES(?,?)',rows)
            db.executemany('INSERT OR REPLACE INTO assets VALUES(?,?,?,?)',assets)
            db.execute("INSERT OR REPLACE INTO catalog_metadata VALUES('signature',?)",(signature,))
        return {'ids':len(rows),'assets':len(assets),'cached':False,'seconds':time.monotonic()-started,
                'source':str(pool),'install':str(install)}
