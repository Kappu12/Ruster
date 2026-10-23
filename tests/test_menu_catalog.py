from contextlib import closing
import sqlite3

import pytest

from ruster.assets import catalog, menu_catalog
from ruster.core.asset_categories import GROUPS
from ruster.core.asset_names import display_name


def finish(builder):
    while True:
        try:next(builder)
        except StopIteration as complete:return complete.value


def test_shared_index_preserves_category_coverage_names_favorites_and_availability(tmp_path):
    paths = [
        'assets/prefabs/monument/harbor.prefab',
        'assets/prefabs/trees/oak.prefab',
        'assets/prefabs/building/wall.prefab',
        'assets/prefabs/industrial/pipe.prefab',
        'assets/prefabs/roads/bridge.prefab',
        'assets/prefabs/deployable/bed.prefab',
        'assets/prefabs/furniture/chair.prefab',
        'assets/prefabs/props/crate.prefab',
        'assets/prefabs/triggers/zone.prefab',
        'assets/prefabs/vehicles/car.prefab',
        'assets/prefabs/effects/steam.prefab',
        'assets/prefabs/modding/cube_tiled_dev_01.prefab',
        'assets/prefabs/tools/hose/ioslothandles/ioslothandlehose_pending.prefab',
        'assets/prefabs/sound/quiet.prefab',
        'assets/prefabs/unusual/unknown.prefab',
    ]
    with closing(catalog.connect(tmp_path)) as db:
        db.executemany('INSERT INTO names VALUES(?,?)', enumerate(paths, 1))
        db.execute('INSERT INTO assets SELECT path,?,?,uid FROM names WHERE uid%2=0', ('bundle', 'file'))
        db.commit()
    favorites = {3, 13}
    snapshot = finish(menu_catalog.build(tmp_path, favorites))
    assert snapshot[''] is snapshot['@ALL_ASSETS']
    by_id = {item[0]: item for item in snapshot['']['items']}
    assert len(by_id) == len(paths)
    assert by_id['3'][4] == 'SOLO_ON' and by_id['2'][4] == 'MESH_CUBE' and by_id['1'][4] == 'QUESTION'
    assert 'Cyan Glow' in by_id['13'][1] and 'neon' in by_id['13'][1] and by_id['13'][3] == 1000
    for key, _label, _patterns in GROUPS:
        expected = catalog.search(tmp_path, category='@'+key, limit=-1)
        expected.sort(key=lambda row: (row[0] not in favorites, display_name(row[1]).casefold(), row[0]))
        actual = snapshot['@'+key]['items']
        assert [item[0] for item in actual] == [str(row[0]) for row in expected], key
        assert all(item is by_id[item[0]] for item in actual), 'Categories copied shared metadata'


def test_partial_index_can_be_cancelled_without_leaving_a_database_lock(tmp_path):
    with closing(catalog.connect(tmp_path)) as db:
        db.executemany('INSERT INTO names VALUES(?,?)', [(i, f'assets/props/item_{i}.prefab') for i in range(1000)])
        db.commit()
    builder = menu_catalog.build(tmp_path, set())
    next(builder)  # A small slice, not the complete catalog.
    with closing(sqlite3.connect(tmp_path/'catalog.sqlite3', timeout=.02)) as writer:
        writer.execute('INSERT INTO names VALUES(?,?)', (1001, 'assets/props/new.prefab'))
        with pytest.raises(sqlite3.OperationalError, match='locked'):writer.commit()
        writer.rollback()
        builder.close()
        writer.execute('INSERT INTO names VALUES(?,?)', (1001, 'assets/props/new.prefab'))
        writer.commit()
    assert finish(menu_catalog.build(tmp_path, set()))['']['total'] == 1001
