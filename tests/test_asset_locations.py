from contextlib import closing
from ruster.assets import catalog,locations


def test_incremental_locations_are_reused_and_invalidated_on_game_change(tmp_path):
    path='assets/modding/cube.prefab'
    with closing(catalog.connect(tmp_path)) as db,db:
        db.execute('INSERT INTO names VALUES(?,?)',(42,path))
        db.execute('INSERT INTO assets VALUES(?,?,?,?)',(path,'Bundles/scene.bundle','@scene:AssetScene-props',0))
    assert locations.prepare(tmp_path,'revision-1')=={}
    locations.remember(tmp_path,{'cab-texture':'Bundles/texture.bundle'},[
        ('BuildPlayer-AssetScene-props',1234,path,'Bundles/scene.bundle')])
    assert catalog.find(tmp_path,42)[2:]==('BuildPlayer-AssetScene-props',1234)
    assert locations.prepare(tmp_path,'revision-1')=={'cab-texture':'Bundles/texture.bundle'}
    assert locations.prepare(tmp_path,'revision-2')=={}
    assert catalog.find(tmp_path,42)[2:]==('@scene:AssetScene-props',0)
