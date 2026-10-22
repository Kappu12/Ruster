# Ruster

A Blender-based desktop editor for Rust worlds. Ruster uses Blender's native UI
widgets, theme, viewport, selection tools, transforms and undo system. It has its
own launcher and `.ruster` project format.

**Status: 0.3.1 development preview, with protected prefab models and terrain/path editing.**
Rust asset compatibility and exported game behavior still require testing against
a current local game installation and server. There are no game assets in this
repository. [FEATURES.md](FEATURES.md) tracks implemented workflows and the remaining
work toward RustEdit parity.

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
Menus, dialogs, section headers and tools share Blender's bundled icon pack.
Terrain and prefab paint have distinct toolbar icons; advanced options live in
native collapsible sections. Ruster follows the selected dark/light theme and UI
scale, and New Project preserves those preferences.
The prefab browser places objects at the 3D cursor. Its duplicate/delete actions
also handle prefab groups and shared model instances.

Save your work with **Ruster → Save Project** (`Ctrl+S`). A `.ruster` file contains
the Blender scene, packed preview assets and the original map data. It can be
reopened without the original `.map` file. **Export Rust Map** writes prefab
placements, terrain layers and paths to a separate `.map`; validation blocks unsupported custom meshes.
New Blender projects can contain arbitrary geometry and save it in `.ruster`.

Use **Ruster → New Rust Map** to begin with editable flat terrain. In the Terrain
panel, select a layer and tool, then click **Paint Terrain in Viewport** and drag on the
terrain. Alt inverts a brush; Shift temporarily smooths height. Each stroke is one
undo step. The panel also offers stamping, cloning, bridge grading, island
generation, 16-bit height import/export, height/slope masks and terrain detail.
Viewport detail is independent of the full-resolution samples saved to the map.

The Paths panel creates roads, rivers, rails and powerlines. Select a path, click
**Edit Path Nodes**, and use Blender's `G`, `E` and `X` controls. Finish node editing
before exporting. Width, padding/fades and grading are available in that panel.

The Placement panel groups/ungroups monuments, snaps and aligns objects to terrain,
scatters selected prefab types, replaces selected types and imports/exports
`.rusterprefab` assemblies. Assemblies store game prefab references and transforms.

Rust prefab models are **read-only linked libraries**. Move, rotate, scale,
replace, group, duplicate or delete the placement; edit terrain with the terrain
brushes. Mesh editing, sculpting and geometry modifiers cannot edit the linked
model through Blender's normal operators. Terrain holes never cut prefab meshes.
The map-mode command and Outliner menus expose supported placement actions.
Export rejects editable/unpacked model parts, detached previews and mismatched
models. **Restore Original Models** repairs the selected placements.

The Prefab Browser now has categories, persistent favorite stars and a favorites
filter. Click the brush icon beside a prefab to choose it for **Prefab Paint**.
Drag in the viewport to paint a spaced line of placements. The paint panel also
supports random favorite/selected-type palettes, rotation, scale, surface
alignment, slope limits and avoiding terrain holes. Spacing measures placement
origins; it is not a game-collider collision test. Each stroke is one undo step;
Esc cancels the entire stroke. Missing asset conversions queue behind active work.

Protected libraries and their textures pack into `.ruster` and reopen without the
conversion cache. Older projects with editable previews lock those previews on
open; their geometry must be rebuilt from the original local assets before export.
Normal New Project mode retains Blender's ordinary mesh editing tools.

Ruster saves an atomic recovery project every two minutes when the editor is idle.
Use **Recover Autosaved Session** on the start screen after a crash. Recovery does
not replace the normal project save destination. Recent projects are listed there
as well. Native file drops support `.map` and `.ruster`.

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

- Rust `.map` serialization versions 9 and 10 are supported; unknown versions are rejected.
- Terrain editing uses full-resolution data with native undo/redo. Untouched layers
  and unknown fields are retained. Brushes support height, water, ground textures,
  biomes, topology and alpha holes. Four- and five-channel biome layouts are recognized.
- The map viewport is an approximation: Rust-specific terrain shading, animated
  vegetation, particles, colliders, skinned-mesh deformation and gameplay are not
  reproduced by Blender. Increase Terrain Detail to inspect smaller terrain edits.
- Missing/unsupported assets remain labeled placement boxes. Their original IDs and
  transforms remain available; asset reports explain conversion problems.
- Asset IDs come from embedded lookup/manifest data, not guessed name hashes. A game
  update with an unsupported manifest layout needs an adapter update.
- IO/puzzles, loot/vending profiles, NPC/vehicle spawning configuration, special
  patrol paths and server extension compatibility are not implemented. Preserving
  existing opaque extension data does not guarantee cloned/deleted links remain valid.
- Seeded island generation is Ruster's own terrain algorithm; it does not recreate
  Rust's native procedural seed generation. Road/river previews and grading are
  authoring approximations pending in-game comparison tests.
- Existing Blender shortcuts and advanced editor switching remain available. Map
  mode is a focused authoring workspace, not a restricted Blender sandbox.
- The source customizes pinned Blender through its Python API. It does not maintain
  a divergent C/C++ tree. [FEATURES.md](FEATURES.md) records the full remaining backlog.

## Validation

```bash
python -m pip install pytest lz4 numpy -r requirements-assets.txt
python -m pytest -q
/path/to/blender -b --factory-startup --disable-autoexec --python tests/blender_smoke.py
/path/to/blender -b --factory-startup --disable-autoexec --python tests/blender_editing.py
/path/to/blender -b --factory-startup --disable-autoexec --python tests/blender_placement.py
/path/to/blender -b --factory-startup --disable-autoexec --python tests/blender_protection.py
```

The Blender test checks real terrain construction, coordinate/rotation conversion,
placement edits, grouping/scatter, terrain and path editing, native undo/redo, lossless unchanged export, preservation of
unknown fields, `.ruster` save/reopen with embedded source data, and restoration of
the normal Blender workspace. Format tests also cover malformed inputs, archive
integrity, path traversal, and independently compressed legacy LZ4 blocks.

The graphical test (`tests/gui_interaction.py`, `--enable-event-simulate`) exercises
actual mouse-driven terrain and prefab strokes, one-step undo, redo and cancel.
Model protection tests also remove the source map, cache and texture files before
reopening the packed project, and reject editable preview copies.

These tests use synthetic map data and original test geometry. They do **not**
establish compatibility with every Rust asset or confirm a map in a running Rust
server. See [architecture](docs/architecture.md) and [format](docs/ruster-format.md).

## License

Ruster is GPL-3.0-or-later. Blender and bundled libraries retain their respective
licenses and notices. A private development repository is compatible with this;
distributing the application requires complying with the corresponding source
requirements. Rust assets remain Facepunch's content and are not covered by
Ruster's source license. See `THIRD_PARTY_NOTICES.md`.
