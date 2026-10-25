from contextlib import closing
import pytest
from ruster.assets import catalog


def test_volumes_are_one_category_and_visible_without_hidden_filter(tmp_path):
    from ruster.core.asset_categories import is_volume
    paths=['assets/bundled/prefabs/modding/volumes_and_triggers/prevent_building_cube.prefab',
           'assets/bundled/prefabs/modding/volumes_and_triggers/safezonesphere.prefab',
           'assets/monuments/volumes/water.prefab','assets/rust.ai/npcpreventbuildingvolume.prefab']
    with closing(catalog.connect(tmp_path)) as db:
        db.executemany('INSERT INTO names VALUES(?,?)',enumerate(paths,1));db.commit()
    assert all(is_volume(p) for p in paths)
    assert not is_volume('assets/prefabs/ui/menuui2_component_popup_safezonewarning.prefab')
    assert not is_volume('assets/bundled/prefabs/fx/impacts/stab/concrete/concrete1.prefab')
    assert not is_volume('assets/prefabs/tea/radiationremovetea/radiationremovetea.item.prefab')
    assert len(catalog.search(tmp_path,category='@VOLUMES',include_helpers=False))==4
    assert not catalog.search(tmp_path,category='@DEVELOPMENT')
    assert not catalog.search(tmp_path,category='@MONUMENTS')


def test_broad_categories_partition_catalog_and_keep_filters(tmp_path):
    rows=[(1,'assets/bundled/prefabs/autospawn/monument/harbor.prefab'),
          (2,'assets/bundled/prefabs/autospawn/resource/trees/oak.prefab'),
          (3,'assets/content/vehicles/car.prefab'),
          (4,'assets/unknown/prefab.prefab')]
    with closing(catalog.connect(tmp_path)) as db:
        db.executemany('INSERT INTO names VALUES(?,?)',rows)
        db.execute('INSERT INTO assets VALUES(?,?,?,?)',(rows[2][1],'bundle','file',1))
        db.commit()
    for category,uid in [('MONUMENTS',1),('NATURE',2),('VEHICLES',3),('OTHER',4)]:
        assert [row[0] for row in catalog.search(tmp_path,category='@'+category)]==[uid]
    assert catalog.search(tmp_path,category='@NATURE',available_only=True)==[]
    assert [row[0] for row in catalog.search(tmp_path,category='@VEHICLES',available_only=True,favorites=[3])]==[3]
    with pytest.raises(ValueError,match='Unknown'):
        catalog.search(tmp_path,category="@OTHER' OR 1=1")


def test_hidden_category_and_all_assets_bypass_helper_filter(tmp_path):
    rows=[(147092032,'assets/prefabs/tools/hose/ioslothandles/ioslothandlehose_pending.prefab'),
          (2,'assets/prefabs/effects/hidden/beam.prefab'),
          (3,'assets/prefabs/test/example.prefab'),
          (4,'assets/prefabs/deployable/chair.prefab')]
    with closing(catalog.connect(tmp_path)) as db:
        db.executemany('INSERT INTO names VALUES(?,?)',rows);db.commit()
    assert {row[0] for row in catalog.search(tmp_path,include_helpers=False)}=={147092032,4}
    assert {row[0] for row in catalog.search(tmp_path,category='@HIDDEN',include_helpers=False)}=={147092032,2,3}
    assert {row[0] for row in catalog.search(tmp_path,category='@ALL_ASSETS',include_helpers=False)}=={row[0] for row in rows}
