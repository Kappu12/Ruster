from types import SimpleNamespace as S
from contextlib import closing
import json
from ruster.assets import references,catalog,locations


def test_guid_lookup_reads_one_manifest_and_adds_current_prefab_ids(tmp_path):
    root=tmp_path/'Rust';(root/'Bundles').mkdir(parents=True)
    path='assets/content/tree_model.prefab'
    (root/'Bundles/AssetSceneManifest.json').write_text(json.dumps({'Scenes':[
        {'Name':'AssetScene-prefabs','IncludedAssets':[path]}]}))
    manifest={'prefabProperties':[{'hash':42,'name':path,'guid':'model-guid'}],
              'guidPaths':[{'name':'assets/other.prefab','guid':'other-guid'}]}
    file=S(types=[S(node=S(m_Children=[S(m_Name='guidPaths')]))],
           objects={1:S(type_id=0,parse_as_dict=lambda:manifest)})
    calls=[]
    env=S(load_file=lambda *args,**kwargs:calls.append(args[0]) or S(files={'CAB-manifest':file}))
    cache=tmp_path/'cache'
    assert references.guid_path(env,cache,root,'model-guid')==path
    assert references.guid_path(env,cache,root,'other-guid')=='assets/other.prefab'
    assert references.guid_path(env,cache,root,'missing-guid') is None
    assert len(calls)==1,'A GUID miss decoded the manifest again'
    assert catalog.find(cache,42)==(path,'Bundles/shared/assetscenes.bundle','@scene:AssetScene-prefabs',0)
    # A game update invalidates names learned from its old GUID manifest.
    locations.prepare(cache,'changed-game-inventory')
    with closing(catalog.connect(cache)) as db:
        assert not db.execute('SELECT 1 FROM guid_paths').fetchone()
