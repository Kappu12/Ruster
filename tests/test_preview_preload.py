"""Map-only preload coverage; never inspect or launch a game client."""
import json
from pathlib import Path
import sqlite3
import sys

import pytest

from ruster.core import live_preview, preview_preload as preload, preview_protocol as protocol, wire
from ruster.core.rust_map import RustMap, prefab_id, prefab_transform


def fixture(tmp_path):
    rows = [
        {'Name': 'AssetScene-bootstrap', 'AutoLoad': True, 'IncludedAssets': ['Assets/fx/small.prefab','Assets/meshes/source.fbx']},
        {'Name': 'AssetScene-props.common', 'AutoLoad': False, 'IncludedAssets': ['Assets/bundled/prefabs/modding/cubes/concrete_cube.prefab', 'Assets/props/large.prefab']},
        {'Name': 'AssetScene-monument.1', 'AutoLoad': False, 'IncludedAssets': ['Assets/monuments/large.prefab']},
    ]
    client = tmp_path/'client/Bundles/AssetSceneManifest.json';client.parent.mkdir(parents=True)
    server = tmp_path/'runtime/server/Bundles/AssetSceneManifest.json';server.parent.mkdir(parents=True)
    for path in (client, server):path.write_text(json.dumps({'Scenes': rows}))
    catalog = tmp_path/'catalog.sqlite3'
    with sqlite3.connect(catalog) as db:
        db.execute('CREATE TABLE names(uid INTEGER,path TEXT)')
        db.executemany('INSERT INTO names VALUES(?,?)', [(1,'assets/fx/small.prefab'),
            (3471408108,'assets/bundled/prefabs/modding/cubes/concrete_cube.prefab'),
            (3,'assets/props/large.prefab'),(4,'assets/monuments/large.prefab')])
    return client, server, catalog


def test_one_marker_per_pack_includes_autoload_and_full_monument(tmp_path):
    client, server, catalog = fixture(tmp_path)
    markers = preload.plan(client, server, catalog)
    assert len(markers) == 3
    assert {m['scene'] for m in markers} == {'AssetScene-bootstrap','AssetScene-props.common','AssetScene-monument.1'}
    assert next(m for m in markers if m['scene']=='AssetScene-props.common')['uid'] == 3471408108
    assert preload.plan(server,client,catalog) == markers


def assert_complete_coverage(markers, client, server):
    selected={m['path'] for m in markers}
    for manifest, key in ((client,'client_scenes'),(server,'server_scenes')):
        packs=preload.scenes(manifest)
        assert all(paths & selected for paths in packs.values())
        for marker in markers:
            assert marker[key]==sorted(name for name,paths in packs.items() if marker['path'] in paths)
    assert len(selected)==len(markers)


def test_client_split_pack_can_be_merged_into_server_bootstrap(tmp_path):
    client,server,catalog=fixture(tmp_path)
    path='assets/deepsea/island.prefab'
    rows=json.loads(client.read_text());rows['Scenes'].append({'Name':'AssetScene-deepsea.1','IncludedAssets':[path]})
    client.write_text(json.dumps(rows))
    rows=json.loads(server.read_text());rows['Scenes'][0]['IncludedAssets'].append(path)
    server.write_text(json.dumps(rows))
    with sqlite3.connect(catalog) as db:db.execute('INSERT INTO names VALUES(?,?)',(5,path))
    markers=preload.plan(client,server,catalog)
    assert_complete_coverage(markers,client,server)
    marker=next(m for m in markers if m['uid']==5)
    assert marker['client_scenes']==['AssetScene-deepsea.1']
    assert marker['server_scenes']==['AssetScene-bootstrap']


def test_same_named_packs_with_repartitioned_assets_cover_both_sides(tmp_path):
    client,server,catalog=fixture(tmp_path)
    rows=json.loads(client.read_text());rows['Scenes'][0]['IncludedAssets'].append('assets/props/large.prefab')
    rows['Scenes'][1]['IncludedAssets']=['assets/bundled/prefabs/modding/cubes/concrete_cube.prefab']
    client.write_text(json.dumps(rows))
    rows=json.loads(server.read_text());rows['Scenes'][0]['IncludedAssets'].append('assets/bundled/prefabs/modding/cubes/concrete_cube.prefab')
    rows['Scenes'][1]['IncludedAssets']=['assets/props/large.prefab']
    server.write_text(json.dumps(rows))
    markers=preload.plan(client,server,catalog)
    assert_complete_coverage(markers,client,server)
    assert {3471408108,3}<={m['uid'] for m in markers}


@pytest.mark.parametrize('missing', ['server','catalog'])
def test_missing_pack_never_silently_reduces_coverage(tmp_path, missing):
    client, server, catalog = fixture(tmp_path)
    if missing == 'server':
        rows = json.loads(server.read_text());rows['Scenes'] = rows['Scenes'][:-1]
        server.write_text(json.dumps(rows))
    else:
        with sqlite3.connect(catalog) as db:db.execute('DELETE FROM names WHERE uid=4')
    with pytest.raises(ValueError,match='AssetScene-monument.1'):preload.plan(client, server, catalog)


def test_map_markers_stay_separate_from_editable_placements(tmp_path):
    markers = preload.plan(*fixture(tmp_path))
    row = {'key':17,'uid':99,'path':'assets/test/user.prefab','position':(0,0,0),'euler':(0,0,0),
        'rotation':(0,0,0,1),'scale':(1,1,1)}
    world = RustMap.read(protocol.preview_map([row],preload=markers))
    assert len(world.prefabs) == 4
    assert prefab_id(world.prefabs[0]) == 99
    assert wire.get(world.prefabs[0],1,2) == b'RusterPreview'
    assert {prefab_id(p) for p in world.prefabs[1:]} == {m['uid'] for m in markers}
    for p in world.prefabs[1:]:
        assert wire.get(p,1,2) == preload.WARMUP_CATEGORY
        position,rotation,scale = prefab_transform(p)
        assert position[0] >= 10000 and position[1] <= -10000 and position[2] >= 10000
        assert scale == pytest.approx((.001,.001,.001))
    assert row['position'] == (0,0,0) and not world.paths


@pytest.mark.skipif(sys.platform != 'win32',reason='Windows preview session')
def test_session_prepares_complete_preload_map_without_adding_snapshot_objects(tmp_path, monkeypatch):
    client, server, catalog = fixture(tmp_path)
    monkeypatch.setattr(live_preview,'check_ports',lambda port:None)
    session = live_preview.PreviewSession(tmp_path/'runtime',client_install=client.parent.parent,catalog_path=catalog)
    session._prepare_map()
    assert session.info()['pack_count'] == 3
    assert json.loads((session.directory/'scene.json').read_text())['placements'] == []
    assert json.loads((session.directory/'initial.json').read_text())['placements'] == []
    assert len(json.loads((session.directory/'preload.json').read_text())['packs']) == 3
    assert len(RustMap.read(session._map).prefabs) == 3


@pytest.mark.parametrize('rows', [None,[],[None], [{'Name':'../bad','IncludedAssets':['assets/a.prefab']}],
    [{'Name':'AssetScene-test','IncludedAssets':['assets/../../bad.prefab']}],
    [{'Name':'AssetScene-test','IncludedAssets':[]}]])
def test_malformed_pack_manifests_are_rejected(tmp_path, rows):
    path=tmp_path/'manifest.json';path.write_text(json.dumps({'Scenes':rows}))
    with pytest.raises(ValueError):preload.scenes(path)
