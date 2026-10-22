# Ruster

A Blender-based desktop editor for Rust worlds. Ruster uses Blender's native UI
widgets, theme, viewport, selection tools, transforms and undo system. It has its
own launcher and `.ruster` project format.

**Status: development preview, not full RustEdit parity.** The implemented map
editing workflow is prefab placement. Terrain and paths are visible, protected
previews; their original data are retained on export. Rust asset compatibility
requires testing against a current local game installation. There are no game
assets in this repository.

## Start

On the first launch, select your Rust installation folder, for example:

```text
C:\Program Files (x86)\Steam\steamapps\common\Rust
```

Choose the game folder containing `Bundles`, rather than the Steam directory.
Ruster remembers this location and indexes the installed Unity AssetBundles in a
separate process. Change it later with **Ruster → Rust Installation**.

The start screen offers:

- **Open Map or Project** — open a Rust `.map` in 3D, or resume a `.ruster` project.
- **New Project** — start with the standard Blender scene, workspaces and tools.

Map mode switches to a Rust-focused workspace with a prefab browser, placement
properties, local asset status and map validation. It keeps Blender's standard
styling. Use Blender's navigation, `G`, `R`, `S`, snapping and selection tools.
The prefab browser places objects at the 3D cursor. Its duplicate/delete actions
also handle the visual children of a prefab.

Save your work with **Ruster → Save Project** (`Ctrl+S`). A `.ruster` file contains
the Blender scene, packed preview assets and the original map data. It can be
reopened without the original `.map` file. **Export Rust Map** writes prefab
placements to a separate `.map`; validation blocks unsupported custom meshes.
New Blender projects can contain arbitrary geometry and save it in `.ruster`.

## Run from source

Requires Blender **4.5 LTS** (tested against the pinned 4.5.14 runtime). Python
3.11 is used by Blender. Your ordinary Blender settings are isolated from Ruster.

```powershell
# Windows: launch.py also accepts --blender "C:\path\to\blender.exe"
$env:RUSTER_BLENDER = 'C:\Program Files\Blender Foundation\Blender 4.5\blender.exe'
py -3 tools/setup_assets.py
py -3 launch.py
```

```bash
# Linux or macOS with a compatible Blender installation
export RUSTER_BLENDER=/path/to/blender
python3 tools/setup_assets.py
python3 launch.py
python3 launch.py /path/to/project.ruster
```

`tools/setup_assets.py` installs the pinned asset reader and its dependencies into
Ruster's `python_modules` directory using Blender's own Python. It does not modify
the Rust installation. Reading Rust assets does not require launching the game.

## Build a standalone app

Run on Windows x64 or Linux x64, using Python 3.11:

```bash
python tools/package.py --archive
```

This downloads the official Blender archive pinned in `engine.lock.json`, verifies
its SHA256, bundles Ruster and asset-reader dependencies, and runs the Blender
integration test. Windows packaging creates `Ruster.exe`. Linux uses `Ruster.sh`.
No separate Blender or Python installation is needed to use the packaged app.
Optional Windows file associations: run `tools/install_associations.ps1` from
source with `-Executable` pointing to the packaged `Ruster.exe`.

GitHub Actions includes **Check Ruster** and **Build Ruster App** workflows. App
builds run on pushes to main and can also be started manually. Packaged ZIPs are build artifacts on that workflow, not committed
to the source repository. macOS standalone packaging is not implemented yet.

## Current boundaries

- Reads `.map` serialization versions 9 and 10; rejects unknown versions.
- Imports terrain height and ground color previews, prefab placements, and path
  overlays. Original terrain/biome/topology/water/path bytes are preserved.
- Loads local prefab hierarchies, triangle meshes, UVs, base colors and common
  base-color textures. Shared bundle dependencies are resolved through a local
  catalog. Game-specific shaders, vegetation animation, colliders, particles and
  gameplay logic are not reproduced by Blender.
- Missing or unsupported assets remain labeled orange placement boxes. Their
  original prefab IDs/transforms are preserved; they are not presented as loaded
  models. **Assets → Asset Report** exposes extraction failures.
- Asset IDs come from embedded prefab lookup/manifest data. Ruster does not guess
  IDs from names. A game build with an unsupported manifest layout will report an
  error and needs an adapter update.
- Terrain/path editing, terrain sculpt export, IO/puzzles/loot editing, procedural
  generation from seed, and server playtesting are not implemented.
- Native Blender shortcuts and advanced editor switching are still available.
  Map mode is a focused authoring UI, not a restricted Blender sandbox.
- Current source customizes the pinned Blender runtime through its Python UI
  API. It does not maintain a divergent C/C++ engine tree. This keeps upstream
  updates manageable; deeper engine changes can be added when required.

## Validation

```bash
python -m pip install pytest lz4 -r requirements-assets.txt
python -m pytest -q
/path/to/blender -b --factory-startup --disable-autoexec --python tests/blender_smoke.py
```

The Blender test checks real terrain construction, coordinate/rotation conversion,
placement edits, duplication/deletion, lossless unchanged export, preservation of
unknown fields, `.ruster` save/reopen with embedded source data, and restoration of
the normal Blender workspace. Format tests also cover malformed inputs, archive
integrity, path traversal, and independently compressed legacy LZ4 blocks.

These tests use synthetic map data and original test geometry. They do **not**
establish compatibility with every Rust asset or confirm a map in a running Rust
server. See [architecture](docs/architecture.md) and [format](docs/ruster-format.md).

## License

Ruster is GPL-3.0-or-later. Blender and bundled libraries retain their respective
licenses and notices. A private development repository is compatible with this;
distributing the application requires complying with the corresponding source
requirements. Rust assets remain Facepunch's content and are not covered by
Ruster's source license. See `THIRD_PARTY_NOTICES.md`.
