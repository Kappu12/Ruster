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


def test_recent_prefabs_are_bounded_unique_and_keep_other_settings():
    config={'favorite_prefabs':['8'],'rust_install':'game'}
    for uid in range(60):config=palettes.remember(config,uid)
    assert palettes.recent_ids(config)==list(range(59,11,-1))
    config=palettes.remember(config,30)
    assert palettes.recent_ids(config)[0]==30
    assert len(palettes.recent_ids(config))==48
    assert config['favorite_prefabs']==['8'] and config['rust_install']=='game'
    assert palettes.recent_ids({'recent_prefabs':[False,{},'bad',1,'1','2',-1]})==[1,2]


def test_catalog_pages_count_filter_and_recover_from_stale_offsets(tmp_path):
    populated(tmp_path)
    with closing(catalog.connect(tmp_path)) as db:
        db.execute('DELETE FROM assets WHERE path=?',('assets/prefabs/rocks/a.prefab',));db.commit()
    page=catalog.page(tmp_path,page_index=100,page_size=2)
    assert page['page']==1 and page['pages']==2 and page['total']==4 and len(page['rows'])==2
    page=catalog.page(tmp_path,category='assets/prefabs/rocks',page_index=100,page_size=1,available_only=True)
    assert page['total']==1 and page['page']==0 and page['rows'][0][0]==3
    assert catalog.page(tmp_path,favorites=[],page_index=100)['pages']==0
    assert catalog.page(tmp_path,query='not-a-prefab')['rows']==[]
    assert len(catalog.search(tmp_path,available_only=True))==3


def test_case_variant_assets_do_not_duplicate_prefab_pages(tmp_path):
    populated(tmp_path)
    with closing(catalog.connect(tmp_path)) as db:
        db.execute('INSERT INTO assets VALUES(?,?,?,?)',('ASSETS/PREFABS/ROCKS/A.PREFAB','variant','file',99));db.commit()
    assert [r[0] for r in catalog.search(tmp_path,category='assets/prefabs/rocks')]==[1,3]
    assert catalog.find(tmp_path,1)[1]=='bundle'
    with closing(catalog.connect(tmp_path)) as db:
        db.execute('DELETE FROM assets WHERE path=?',('assets/prefabs/rocks/a.prefab',));db.commit()
    assert catalog.search(tmp_path,'rocks/a',available_only=True)[0][0]==1
    assert catalog.find(tmp_path,1)[1]=='variant'


def test_helpers_are_opt_in_for_composition_but_explicit_categories_show_them(tmp_path):
    with closing(catalog.connect(tmp_path)) as db:
        db.executemany('INSERT INTO names VALUES(?,?)',[
            (1,'assets/props/crate.prefab'),(2,'assets/props/sound/crate.prefab'),
            (3,'assets/effects/fire.prefab'),(4,'assets/bundled/testscenario_building.prefab'),
            (5,'assets/modding/cubes/cube_tiled_dev_01.prefab')]);db.commit()
    assert {row[0] for row in catalog.search(tmp_path,include_helpers=False)}=={1,5}
    assert catalog.page(tmp_path,include_helpers=False)['total']==2
    assert len(catalog.search(tmp_path))==5
    assert catalog.search(tmp_path,category='@EFFECTS',include_helpers=False)[0][0]==3
