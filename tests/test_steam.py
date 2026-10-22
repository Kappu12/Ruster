from pathlib import Path
from ruster.core import steam
from types import SimpleNamespace
from contextlib import contextmanager


def game(path):
    path.mkdir(parents=True);(path/'Bundles').mkdir();(path/'RustClient.exe').touch();return path.resolve()


def test_standard_steam_path_is_validated(tmp_path,monkeypatch):
    monkeypatch.delenv('RUST_INSTALL_PATH',raising=False)
    root=tmp_path/'Steam';expected=game(root/'steamapps/common/Rust')
    assert steam.detect_install([root])==expected
    (expected/'RustClient.exe').unlink()
    assert steam.detect_install([root]) is None


def test_preview_fixture_never_masks_a_real_install(tmp_path,monkeypatch):
    monkeypatch.delenv('RUST_INSTALL_PATH',raising=False)
    preview=game(tmp_path/'preview')
    real=game(tmp_path/'Steam/steamapps/common/Rust')
    (real/'RustClient.exe').write_bytes(b'MZ-installed-game')
    assert steam.resolve_install(str(preview),[tmp_path/'Steam'])==real
    assert steam.resolve_install(str(real),[])==real


def test_secondary_steam_library_and_manifest_name(tmp_path,monkeypatch):
    monkeypatch.delenv('RUST_INSTALL_PATH',raising=False)
    root=tmp_path/'Steam';apps=root/'steamapps';apps.mkdir(parents=True)
    library=tmp_path/'Other library';expected=game(library/'steamapps/common/Rust Custom')
    (apps/'libraryfolders.vdf').write_text('"libraryfolders" { "0" { "path" "'+str(root)+'" } "1" { "path" "'+str(library)+'" "apps" { "252490" "1" } } }')
    (library/'steamapps/appmanifest_252490.acf').write_text('"AppState" { "appid" "252490" "installdir" "Rust Custom" }')
    assert steam.detect_install([root,root])==expected


def test_old_library_layout_and_malformed_metadata_fallback(tmp_path):
    root=tmp_path/'Steam';(root/'steamapps').mkdir(parents=True)
    library=tmp_path/'library';expected=game(library/'steamapps/common/Rust')
    path=root/'steamapps/libraryfolders.vdf'
    path.write_text('"LibraryFolders" { "TimeNextStatsReport" "0" "1" "'+str(library)+'" }')
    assert steam.detect_install([root])==expected
    path.write_text('"LibraryFolders" { "1" {')
    assert steam.detect_install([root]) is None
    local=game(root/'steamapps/common/Rust')
    assert steam.detect_install([root])==local


def test_explicit_environment_path_and_manifest_traversal(tmp_path,monkeypatch):
    root=tmp_path/'Steam';(root/'steamapps').mkdir(parents=True)
    outside=game(tmp_path/'Outside')
    (root/'steamapps/appmanifest_252490.acf').write_text('"AppState" { "installdir" "../../../Outside" }')
    monkeypatch.delenv('RUST_INSTALL_PATH',raising=False)
    assert steam.detect_install([root]) is None
    monkeypatch.setenv('RUST_INSTALL_PATH',str(outside))
    assert steam.detect_install([root])==outside


def test_vdf_quoted_windows_paths_comments_and_unicode(tmp_path):
    path=tmp_path/'libraryfolders.vdf'
    path.write_text('// comment\n"LibraryFolders" { "1" { "path" "D:\\\\Steam Library\\\\äö" } }',encoding='utf-8-sig')
    assert steam.read_vdf(path)['libraryfolders']['1']['path']=='D:\\Steam Library\\äö'


def test_windows_registry_and_program_files_roots(tmp_path,monkeypatch):
    import sys
    @contextmanager
    def open_key(hive,key):
        if hive!='current':raise OSError('No machine-wide Steam key')
        yield key
    fake=SimpleNamespace(HKEY_CURRENT_USER='current',HKEY_LOCAL_MACHINE='machine',OpenKey=open_key,
        QueryValueEx=lambda _handle,_value:(str(tmp_path/'Steam Registry'),1))
    monkeypatch.setitem(sys.modules,'winreg',fake)
    monkeypatch.setattr(steam,'sys',SimpleNamespace(platform='win32'))
    monkeypatch.setenv('ProgramFiles(x86)',str(tmp_path/'Program Files (x86)'))
    monkeypatch.setenv('ProgramFiles',str(tmp_path/'Program Files'))
    roots=steam.steam_roots()
    assert roots[0]==tmp_path/'Steam Registry'
    assert tmp_path/'Program Files (x86)/Steam' in roots
    assert tmp_path/'Program Files/Steam' in roots
