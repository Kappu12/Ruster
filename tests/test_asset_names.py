from contextlib import closing
from ruster.assets import catalog
from ruster.core.asset_names import display_name,menu_label,IO_NAMES
import pytest


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


@pytest.mark.parametrize('query', ['io','IO','Io','glow','GLOW','glowing','neon','cyan glow','GLOW CYAN','(cyan glow)'])
def test_maze_handles_rank_before_broad_path_matches_and_paging(tmp_path,query):
    from ruster.core.asset_names import IO_NAMES
    ids={'ioslothandlehose_pending':147092032,'ioslothandle':4153457039}
    with closing(catalog.connect(tmp_path)) as db:
        rows=[(10,'assets/prefabs/gloweyes/gloweyes.item.prefab'),
              (11,'assets/prefabs/construction/generic.prefab')]
        for index,stem in enumerate(IO_NAMES,100):
            tool='hose' if 'hose' in stem else 'wire'
            rows.append((ids.get(stem,index),f'assets/prefabs/tools/{tool}/ioslothandles/{stem}.prefab'))
        db.executemany('INSERT INTO names VALUES(?,?)',rows)
        db.execute('INSERT INTO assets SELECT path,?,?,uid FROM names',('bundle','file'))
        db.commit()
    assert catalog.search(tmp_path,query,limit=1,available_only=True)[0][0]==147092032
    first=catalog.page(tmp_path,query=query,page_size=1,available_only=True,include_helpers=False)
    assert first['rows'][0][0]==147092032
    if query.casefold()=='io':
        assert catalog.search(tmp_path,query,limit=2)[1][0]==4153457039
        assert catalog.page(tmp_path,query=query,page_size=1,page_index=1)['rows'][0][0]==4153457039
    else:
        assert all(row[0]!=4153457039 for row in catalog.search(tmp_path,query)), 'Plain gray wire is not a glow alias'


def test_every_displayed_sound_word_matches_in_any_order_and_case(tmp_path):
    path='assets/prefabs/target/sound/target_deploy.prefab'
    with closing(catalog.connect(tmp_path)) as db:
        db.execute('INSERT INTO names VALUES(?,?)',(1188595389,path))
        db.commit()
    assert 'effect' not in path and 'effect' in display_name(path)
    for query in ('sound effect','effect sound','EFFECT SOUND','(Sound effect)','effect deploy target'):
        assert [row[0] for row in catalog.search(tmp_path,query)]==[1188595389],query


def test_native_menu_labels_keep_names_and_compact_readable_aliases():
    for stem,(_name,aliases) in IO_NAMES.items():
        path=f'assets/prefabs/tools/wire/ioslothandles/{stem}.prefab'
        label=menu_label(path)
        assert label.startswith(display_name(path))
        assert all(word.casefold() in label.casefold() for word in aliases.split())
        assert '_' not in label and '/' not in label and '.prefab' not in label
        assert len(label)<100
    path='assets/bundled/prefabs/modding/cubes/tiled/cube_tiled_dev_01.prefab'
    assert menu_label(path)=='Dev Cube Tiled 01'
