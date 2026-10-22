from contextlib import closing
from ruster.assets import catalog
from ruster.core import palettes,settings


def populated(cache):
    with closing(catalog.connect(cache)) as db:
        for uid,path in [(1,'assets/prefabs/rocks/a.prefab'),(2,'assets/prefabs/rocks_big/b.prefab'),
                         (3,'assets/prefabs/rocks/under_score.prefab'),(4,'assets/content/trees/tree.prefab')]:
            db.execute('INSERT INTO names VALUES(?,?)',(uid,path))
            db.execute('INSERT INTO assets VALUES(?,?,?,?)',(path,'bundle','file',uid))
        db.commit()


def test_favorites_persist_without_replacing_other_preferences(tmp_path,monkeypatch):
    monkeypatch.setenv('RUSTER_USER_DIR',str(tmp_path))
    config={'rust_install':'game','last_project':'project'}
    config=palettes.toggle(config,4294967295)
    settings.save(config)
    assert palettes.favorite_ids(settings.load())==[4294967295]
    assert settings.load()['rust_install']=='game'
    assert palettes.favorite_ids(palettes.toggle(settings.load(),4294967295))==[]


def test_catalog_combines_category_search_favorites_and_paging(tmp_path):
    populated(tmp_path)
    assert [r[0] for r in catalog.search(tmp_path,category='assets/prefabs/rocks')]==[1,3]
    assert [r[0] for r in catalog.search(tmp_path,category='assets/prefabs/rocks',favorites=[3])]==[3]
    assert catalog.search(tmp_path,favorites=[])==[]
    assert [r[0] for r in catalog.search(tmp_path,'under_')]==[3]
    assert [r[0] for r in catalog.search(tmp_path,limit=1,offset=1,category='assets/prefabs/rocks')]==[3]
    assert ('assets/prefabs/rocks',2) in catalog.categories(tmp_path)


def test_malformed_favorite_settings_do_not_break_the_browser():
    assert palettes.favorite_ids({'favorite_prefabs':{'bad':3}})==[]
    assert palettes.favorite_ids({'favorite_prefabs':[True,{},'bad',-1,'4294967296','42',42]})==[42]
