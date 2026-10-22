from contextlib import closing
import pytest
from ruster.assets import catalog


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
