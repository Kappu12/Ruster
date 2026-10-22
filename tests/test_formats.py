import hashlib
import json
import struct
import zipfile
import pytest
import lz4.block
from ruster.core import wire, legacy_lz4, project, settings
from ruster.core.rust_map import RustMap, prefab_transform, update_transform
from ruster.assets.catalog import parse_lookup, parse_manifest, connect, search
from ruster.assets.worker import component_pointers, bundle_files
from types import SimpleNamespace
from tests.fixtures import sample_world


@pytest.mark.parametrize('version',[9,10])
def test_map_roundtrip_preserves_all_fields(version):
    world = sample_world(version)
    result = RustMap.read(world.write())
    assert result.version == version
    assert result.timestamp == world.timestamp
    assert wire.serialize(result.fields) == wire.serialize(world.fields)
    assert result.height_grid()[0] == 33


def test_prefab_edit_preserves_other_layers_and_unknown_fields():
    world = sample_world()
    original = [f.raw for f in world.fields if f.number != 3]
    prefabs = world.prefabs
    prefabs[0] = update_transform(prefabs[0],(10,20,30),(0,45,0),(2,2,2))
    world.replace_prefabs(prefabs[:1])
    result = RustMap.read(world.write())
    assert [f.raw for f in result.fields if f.number != 3] == original
    assert prefab_transform(result.prefabs[0])[0] == (10,20,30)
    assert wire.get(result.prefabs[0],47) == b'unknown prefab extension'
    assert len(result.prefabs) == 1


def test_reads_independently_compressed_lz4net_chunks():
    data = b'Rust prefab terrain '*5000
    compressed = lz4.block.compress(data,store_size=False)
    framing = wire.varint(1)+wire.varint(len(data))+wire.varint(len(compressed))+compressed
    assert legacy_lz4.decompress(framing) == data
    # Mixed raw/compressed blocks are valid in the legacy format.
    assert legacy_lz4.decompress(legacy_lz4.compress(b'abc')+framing) == b'abc'+data


@pytest.mark.parametrize('data', [b'\x80', b'\x80'*11, b'\x00', b'\x0a\xff\xff', b'\x0f'])
def test_corrupt_protobuf_fails(data):
    with pytest.raises(wire.FormatError):
        wire.parse(data)


@pytest.mark.parametrize('data', [b'\x04\x01a', b'\x01\x10\x03abc', b'\x00\x05abc'])
def test_corrupt_lz4_fails(data):
    with pytest.raises(wire.FormatError):
        legacy_lz4.decompress(data)


def test_map_rejects_future_version():
    with pytest.raises(wire.FormatError,match='Unsupported'):
        RustMap.read(struct.pack('<I',999)+b'x'*20)


@pytest.mark.parametrize('mode',['BLENDER','MAP'])
def test_project_roundtrip(tmp_path,mode):
    blend = tmp_path/'original.blend'
    blend.write_bytes(b'BLENDER-v304scene payload')
    source = tmp_path/'source.map'
    source.write_bytes(sample_world().write())
    path = tmp_path/'test.ruster'
    project.save(path,blend,mode,source if mode=='MAP' else None,'Test')
    manifest = project.unpack(path,tmp_path/'opened')
    assert manifest['mode'] == mode
    assert (tmp_path/'opened/scene.blend').read_bytes() == blend.read_bytes()
    if mode == 'MAP':
        assert (tmp_path/'opened/source.map').read_bytes() == source.read_bytes()


def test_project_rejects_traversal_and_unsupported_version(tmp_path):
    path = tmp_path/'bad.ruster'
    with zipfile.ZipFile(path,'w') as archive:
        archive.writestr('../outside',b'no')
        archive.writestr('manifest.json','{}')
        archive.writestr('scene.blend',b'BLENDER')
    with pytest.raises(wire.FormatError):
        project.unpack(path,tmp_path/'opened')
    assert not (tmp_path/'outside').exists()


def test_project_integrity_failure_writes_nothing(tmp_path):
    path = tmp_path/'bad.ruster'
    manifest = {'format':'ruster','schema':1,'mode':'BLENDER','files':{'scene.blend':'incorrect'}}
    with zipfile.ZipFile(path,'w') as archive:
        archive.writestr('manifest.json',json.dumps(manifest))
        archive.writestr('scene.blend',b'BLENDER')
    with pytest.raises(wire.FormatError,match='integrity'):
        project.unpack(path,tmp_path/'opened')
    assert not (tmp_path/'opened').exists()


def test_settings_require_a_real_install_layout(tmp_path,monkeypatch):
    monkeypatch.setenv('RUSTER_USER_DIR',str(tmp_path/'user'))
    with pytest.raises(wire.FormatError):
        settings.validate_install(tmp_path)
    (tmp_path/'Bundles').mkdir()
    (tmp_path/'RustClient.exe').touch()
    assert settings.validate_install(tmp_path) == tmp_path
    settings.save({'rust_install':str(tmp_path)})
    assert settings.load()['rust_install'] == str(tmp_path)


def test_asset_ids_come_from_lookup_not_guessed_hashes(tmp_path):
    text = 'guid,4294967295,assets/prefabs/rock.prefab\nbad,wrong,assets/false.prefab\n'
    rows = list(parse_lookup(text))
    assert rows == [(4294967295,'assets/prefabs/rock.prefab')]
    with connect(tmp_path) as db:
        db.executemany('INSERT INTO names VALUES(?,?)',rows)
    assert search(tmp_path,'rock')[0][:2] == rows[0]


def test_modern_and_legacy_unity_components_are_supported():
    pointer = object()
    modern = SimpleNamespace(m_Component=[SimpleNamespace(component=pointer)])
    legacy = SimpleNamespace(m_Component=[(4,pointer)])
    assert list(component_pointers(modern)) == [pointer]
    assert list(component_pointers(legacy)) == [pointer]


def test_bundle_discovery_checks_file_content(tmp_path):
    bundles = tmp_path/'Bundles'
    bundles.mkdir()
    (bundles/'shared.bundle').write_bytes(b'UnityFS\0data')
    (bundles/'not-a-bundle.txt').write_text('text')
    assert [p.name for p in bundle_files(tmp_path)] == ['shared.bundle']


def test_manifest_only_accepts_explicit_prefab_id_pairs():
    tree = {'pooledStrings':[{'str':'assets/a.prefab','hash':123},
                             {'str':'assets/b.prefab','hash':4294967295},
                             {'str':'assets/no.prefab'},
                             {'str':'assets/icon.png','hash':999}]}
    assert list(parse_manifest(tree)) == [(123,'assets/a.prefab'),(4294967295,'assets/b.prefab')]
