import json
from ruster.assets import catalog,metadata


def source(tmp_path):
    game=tmp_path/'Rust';editor=tmp_path/'RustEdit';editor.mkdir()
    (game/'Bundles/shared').mkdir(parents=True)
    # No valid bundle is needed or opened when building the browser catalog.
    (game/'Bundles/shared/assetscenes.bundle').write_bytes(b'not a parsed bundle')
    (game/'Bundles/AssetSceneManifest.json').write_text(json.dumps({'Scenes':[
        {'Name':'AssetScene-props.common','IncludedAssets':['Assets/test/props/crate.prefab']}]}))
    (editor/'stringpool.txt').write_text('42 - assets/test/props/crate.prefab\n43 - assets/test/unmapped.prefab\n99 - child_name\n')
    return game,editor


def test_catalog_uses_only_shipped_metadata_and_retains_ids(tmp_path):
    game,editor=source(tmp_path);cache=tmp_path/'cache'
    result=metadata.refresh(game,cache,editor)
    assert result['ids']==2 and result['assets']==1
    assert catalog.find(cache,42)==('assets/test/props/crate.prefab','Bundles/shared/assetscenes.bundle','@scene:AssetScene-props.common',0)
    assert [row[0] for row in catalog.search(cache,available_only=True)]==[42]
    assert metadata.refresh(game,cache,editor)['cached']
    (editor/'stringpool.txt').write_text('44 - assets/test/props/crate.prefab\n')
    assert not metadata.refresh(game,cache,editor)['cached']
    assert catalog.find(cache,42) is None and catalog.find(cache,44)


def test_invalid_source_does_not_destroy_existing_catalog(tmp_path):
    import pytest
    game,editor=source(tmp_path);cache=tmp_path/'cache';metadata.refresh(game,cache,editor)
    (game/'Bundles/AssetSceneManifest.json').write_text('{broken')
    with pytest.raises(ValueError):metadata.refresh(game,cache,editor)
    assert catalog.find(cache,42)
