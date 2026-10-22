from contextlib import closing
from ruster.assets import catalog
from ruster.core.asset_names import display_name


def test_dev_cube_is_named_and_searchable_in_either_order(tmp_path):
    path='assets/bundled/prefabs/modding/cubes/tiled/cube_tiled_dev_01.prefab'
    with closing(catalog.connect(tmp_path)) as db:
        db.execute('INSERT INTO names VALUES(?,?)',(3560857504,path));db.commit()
    assert display_name(path)=='Dev Cube Tiled 01'
    for query in ('dev cube','cube dev','01 dev cube','cube 01 dev','cube_tiled_dev_01'):
        assert catalog.search(tmp_path,query)[0][0]==3560857504
    assert catalog.search(tmp_path,category='@DEVELOPMENT')[0][0]==3560857504
    assert not catalog.search(tmp_path,category='@GAMEPLAY')


def test_sound_effect_names_are_distinct_from_mesh_models():
    path='assets/prefabs/target/sound/target_deploy.prefab'
    assert display_name(path)=='target deploy (Sound effect)'


def test_display_names_replace_separators_without_losing_dotted_words():
    assert display_name('assets/prefabs/wall.external_high.stone.prefab')=='wall external high stone'
    assert display_name('wall.external_high.stone')=='wall external high stone'
    assert display_name('assets/a/wall.external_high.stone.PREFAB')=='wall external high stone'
