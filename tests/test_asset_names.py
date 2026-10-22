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


def test_maze_hose_has_a_readable_name_and_word_aliases(tmp_path):
    hose='assets/prefabs/tools/hose/ioslothandles/ioslothandlehose_pending.prefab'
    wire='assets/prefabs/tools/wire/ioslothandles/ioslothandle.prefab'
    with closing(catalog.connect(tmp_path)) as db:
        db.executemany('INSERT INTO names VALUES(?,?)',[(147092032,hose),(4153457039,wire)])
        db.commit()
    assert display_name(hose)=='IO Hose Tube Pending (Cyan Glow)'
    for query in ('io tube cyan','glowing hose','tube hose','maze neon','ioslothandlehose_pending'):
        assert [row[0] for row in catalog.search(tmp_path,query)]==[147092032],query
    assert [row[0] for row in catalog.search(tmp_path,'tube wire')]==[4153457039]
