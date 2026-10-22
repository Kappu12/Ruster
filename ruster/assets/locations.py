"""Incremental locations learned while opening one requested prefab."""
from contextlib import closing
from .catalog import connect


def prepare(cache,signature):
    with closing(connect(cache)) as db,db:
        db.execute('CREATE TABLE IF NOT EXISTS lookup_state(key TEXT PRIMARY KEY,value TEXT)')
        old=db.execute("SELECT value FROM lookup_state WHERE key='signature'").fetchone()
        if not old or old[0]!=signature:
            db.execute('DELETE FROM serialized_files')
            # Only locators learned from shipped asset scenes are reset here.
            db.execute("UPDATE assets SET file='@scene:'||substr(file,13),path_id=0 WHERE file LIKE 'BuildPlayer-%'")
            db.execute("INSERT OR REPLACE INTO lookup_state VALUES('signature',?)",(signature,))
        return dict(db.execute('SELECT name,bundle FROM serialized_files'))


def remember(cache,cabs,roots):
    if not cabs and not roots:return
    with closing(connect(cache)) as db,db:
        db.executemany('INSERT OR REPLACE INTO serialized_files VALUES(?,?)',cabs.items())
        db.executemany('UPDATE assets SET file=?,path_id=? WHERE path=? COLLATE NOCASE AND bundle=?',roots)
