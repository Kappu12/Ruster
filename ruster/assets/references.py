"""Resolve Rust's separate visual prefabs through its shipped GameManifest."""
from contextlib import closing
from .catalog import connect


def guid_path(env,cache,root,guid):
    with closing(connect(cache)) as db:
        db.execute('CREATE TABLE IF NOT EXISTS guid_paths(guid TEXT PRIMARY KEY,path TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS lookup_state(key TEXT PRIMARY KEY,value TEXT)')
        version=db.execute("SELECT value FROM lookup_state WHERE key='guid_schema'").fetchone()
        if not version or version[0]!='2':
            with db:
                db.execute('DELETE FROM guid_paths')
                db.execute("INSERT OR REPLACE INTO lookup_state VALUES('guid_schema','2')")
        row=db.execute('SELECT path FROM guid_paths WHERE guid=?',(guid,)).fetchone()
        if row:return row[0]
        if db.execute('SELECT 1 FROM guid_paths LIMIT 1').fetchone():return None
        # One small manifest object, using compact CAB metadata. No meshes or
        # textures are indexed/decoded to obtain these GUID/name pairs.
        bundle=env.load_file(str(root/'Bundles/shared/content.bundle'),is_dependency=True)
        for name,file in list(bundle.files.items()):
            if name.lower().endswith(('.ress','.resource')):continue
            matching={index for index,typ in enumerate(file.types) if typ.node and
                any(child.m_Name=='guidPaths' for child in typ.node.m_Children)}
            if not matching:continue
            objects=file.objects
            readers=objects.of_type('MonoBehaviour') if hasattr(objects,'of_type') else objects.values()
            for reader in readers:
                if reader.type_id not in matching:continue
                data=reader.parse_as_dict()
                rows=[(item['guid'],item['name'].lower()) for key in ('prefabProperties','guidPaths')
                      for item in data.get(key,[]) if item.get('guid') and item.get('name')]
                prefabs=[(item['hash'],item['name'].lower()) for item in data.get('prefabProperties',[])
                         if isinstance(item.get('hash'),int) and 0<item['hash']<=0xffffffff
                         and item.get('name','').lower().endswith('.prefab')]
                from .metadata import read_text
                import json
                scenes=json.loads(read_text(root/'Bundles/AssetSceneManifest.json'))['Scenes']
                locations={path.lower():scene['Name'] for scene in scenes for path in scene['IncludedAssets']}
                assets=[(path,'Bundles/shared/assetscenes.bundle','@scene:'+locations[path],0)
                        for _uid,path in prefabs if path in locations]
                with db:
                    db.executemany('INSERT OR IGNORE INTO guid_paths VALUES(?,?)',rows)
                    db.executemany('INSERT OR REPLACE INTO names VALUES(?,?)',prefabs)
                    db.executemany('INSERT OR IGNORE INTO assets VALUES(?,?,?,?)',assets)
                row=db.execute('SELECT path FROM guid_paths WHERE guid=?',(guid,)).fetchone()
                return row[0] if row else None
    return None
