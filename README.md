# Ruster

A Blender-based desktop editor for Rust worlds. Ruster uses Blender's native UI
widgets, theme, viewport, selection tools, transforms and undo system. It has its
own launcher and `.ruster` project format.

**Status: 0.8 development preview on Blender 5.2, with native RustEdit prefab interchange.**
Rust asset compatibility and exported game behavior still require testing against
a current local game installation and server. There are no game assets in this
repository. [FEATURES.md](FEATURES.md) tracks implemented workflows and the remaining
work toward RustEdit parity.

## Start

On first launch, Ruster checks standard Steam locations, Windows Steam registry
entries and Steam's secondary library folders for Rust. It validates the game
executable and `Bundles` folder, remembers the location and reads the prefab catalog.
Your saved valid location takes priority. If discovery fails, choose **Preferences → Rust Assets** from the Ruster start
screen. Choose the folder and click **Apply Installation**,
for example:

```text
C:\Program Files (x86)\Steam\steamapps\common\Rust
```

Choose the game folder containing `Bundles`, rather than the Steam directory.
Ruster remembers this location. Change it later with **Edit → Preferences → Rust Assets**.
Browsing reads the game's `AssetSceneManifest.json` and your installed RustEdit's
`stringpool.txt`; there is no full-bundle object index. RustEdit's standard install
folder is detected automatically, or can be selected in Preferences. These local
metadata files are never bundled with Ruster. A cold catalog on this installation
loaded 17,140 IDs in about 0.24 seconds. Models load only on demand, from their
named asset scene and required dependencies. Catalog refresh and map opening do
not start bulk conversion. **Load Selected Models** accepts up to 100 different
model IDs per request. A requested prefab runs in its own short-lived child process. On Windows each
asset child has a 768 MiB allocation limit and its supervisor tree has a 1 GiB
limit. The editor process tree has a 4 GiB allocation limit. Limits apply to
private committed process memory, not GPU allocations or shared system pages.
Oversized/unsupported assets stay as placeholders with an error report. Worker
watchdogs and Windows jobs stop child work if the owning editor exits or crashes.

The native Blender splash artwork appears above Ruster's start buttons. The Ruster
sidebar keeps the start controls available after dismissing the splash. Empty
executables from development fixtures are rejected by automatic install selection.

The start screen offers:

- **Open Map, Prefab or Project** — open `.map`, RustEdit `.prefab`, or `.ruster`.
- **New Prefab** — start an empty Rust composition with only placement tools.

The workspace exposes Rust actions, the viewport, placement hierarchy and Ruster
sidebar. General Blender workspaces, Properties, animation timeline, modeling
menus and unrelated sidebar tabs are hidden. Map mode adds terrain and path tools.
Use Blender's navigation, `G`, `R`, `S`, snapping and selection tools.
**Shift+A** opens broad Rust prefab categories; choose a category and type to
search. It reads catalog names without loading models. Models load on demand.
Dev cubes are under **Development & Primitives**, named **Dev Cube Tiled 01**
and similar; search `dev cube` in Shift+A or the sidebar. Both searches match
words in any order. Display names use spaces instead of dots and underscores.
Sound-only prefabs are labeled and use small spherical
markers because the game contains no visible mesh for them.
The browser starts with locally available prefabs and hides internal tests,
sounds and helper effects. Enable **Effects & Helpers** to include them; choosing
the Effects or Gameplay category also includes that category's helpers. Browser
redraws reuse their current page. Loading progress and cancellation stay beside
the search controls. Model completion follows prefab IDs, so renaming or deleting
a placement while loading cannot lose or redirect its model.
Opening a prefab remembers the bundle directories and root locations encountered
for that request. Later requests reuse those small metadata records; a changed
game installation invalidates them. This never starts a full asset index.
Blender's normal toolbar is visible, with Rust brushes added in map mode. New
prefabs start in textured Solid view so loaded textures appear promptly with
Blender's lightweight studio lighting. Material Preview remains available from
the viewport shading controls. Texture previews
read a source mip up to 2048px without decoding larger levels. Space and F3
open Rust commands; Space does not start Blender animation playback.
Menus, dialogs, section headers and tools share Blender's bundled icon pack.
Terrain and prefab paint have distinct toolbar icons; advanced options live in
native collapsible sections. Ruster follows the selected dark/light theme and UI
scale, and New Prefab preserves those preferences. Rust installation and MCP
settings live in the same Preferences window under **Rust Assets** and **Rust MCP**
in the left-hand navigation; there is no separate Ruster settings dialog.
The prefab browser places objects at the 3D cursor. Its duplicate/delete actions
also handle prefab groups and shared model instances.

Save your work with **Ruster → Save Project** (`Ctrl+S`). A `.ruster` file contains
the Blender scene, packed preview assets and the original map data. It can be
reopened without the original `.map` file. **Export Rust Map** writes prefab
placements, terrain layers and paths to a separate `.map`; validation blocks unsupported custom meshes.
**Export RustEdit Prefab** writes the current native `.prefab` format, independently
verified against installed RustEdit 1.2.19. Unchanged imports retain every original
byte. IO positions and connection targets follow placement movements when their
identities and order remain intact. Ambiguous or unsupported linked-data edits
are blocked. Existing IO entities expose **Rust IO Settings** in Placement.
See [the compatibility contract](docs/rustedit-prefabs.md) for exact limits.

**Export Models** offers GLB, glTF, FBX, OBJ, PLY, STL, USD, USDA, USDC, Alembic
and a Blender model library when those exporters are present. Exports use temporary
realized mesh copies; the source Rust libraries remain protected. Geometry must
be loaded before model export. Large selections exceeding the bounded copy budget
must be exported in smaller parts.

Use **Ruster → New Rust Map** to begin with editable flat terrain. In the Terrain
panel, select a layer and tool, then click **Paint Terrain in Viewport** and drag on the
terrain. Alt inverts a brush; Shift temporarily smooths height. Each stroke is one
undo step. The panel also offers stamping, cloning, bridge grading, island
generation, 16-bit height import/export, height/slope masks and terrain detail.
Viewport detail is independent of the full-resolution samples saved to the map.

Use **Terrain → Layer Image Masks** or **Map → Import/Export Layer Mask** to
round-trip a ground texture, biome, topology bit or terrain-hole mask through an
image editor. Export is 8-bit grayscale PNG; import accepts single-channel 8/16-bit
PNG or TIFF and resizes to the layer's full resolution. The image's top row maps
to +Y in the editor; **Flip Vertically** reverses this. Weights resize smoothly;
topology and holes use nearest samples with a midpoint threshold. White enables
a topology bit or solid terrain; black clears that bit or cuts terrain holes.
Weight imports set the chosen channel exactly, balancing the other channels to
255 while keeping their proportions as closely as integer rounding permits.
Other topology bits, layers and prefab models are preserved. Imports support
undo/redo and persist in `.ruster` projects and exported maps.

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

The Prefab Browser has categories, persistent favorite stars, an available-local
filter, exact result counts and page totals. Hover a prefab to inspect its full
asset path and Rust ID; use the copy icon to copy that ID. Empty searches and
catalog read errors have distinct messages. New placements use Blender’s normal
XYZ rotation angles; the Placement panel also exposes Blender’s rotation mode
selector for older quaternion projects. Click the brush icon beside a prefab to choose it for **Prefab Paint**.
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

## Rust-native seed generation

Use **Generate Rust Map** on the welcome screen or Map menu. Ruster auto-detects
an installed RustDedicated, runs a headless background job, and stops it once a
new valid map is ready. Progress, Cancel, logs and Open Generated Map are in the
Ruster sidebar. Your current project stays open until you choose to open the result.
Manual backend selection is in the normal **Preferences → Rust Assets** section.

This uses the installed server runtime, **not a stripped standalone generator**.
Real-game compatibility and speed benchmarking are pending; no Rust binaries are
bundled or downloaded. See [backend setup and limitations](docs/map-generation.md).

## 2D map views

The top bar has **3D Map** and **Maps** workspace tabs. Maps uses Blender's native
Image Editor to inspect height, water, spawn height, slope, splat, biome, topology
and terrain-hole data as flat images. Choose a composite or an individual channel,
zoom/pan normally, and use Frame Map to fit the image. Previews are capped at
512/1024/2048 pixels independently of the authoritative map resolution. They are
read-only and follow committed edits and undo. A missing source layer is reported
explicitly. Editing the preview image does not edit the map; use terrain brushes
or import a full-resolution layer mask.

## MCP / AI editor connection

Open **Edit → Preferences → Rust MCP** and turn on **Enable MCP**. It is off by default.
Click **Copy MCP Client Configuration** and add the JSON to your MCP client's
configuration. Keep Ruster open. The packaged app includes the stdio adapter and
its Python dependencies; there is no separate community addon or `uv` install.
For a source checkout, run `tools/setup_assets.py` to install both asset and MCP
dependencies into the local `python_modules` directory.

The integration adapts the MIT-licensed community
[MCP for Blender](https://github.com/ahujasid/mcp-for-blender) bridge at revision
`5a3618fccb2d982d0dd61e7a1879912c3100073b`. Ruster exposes **35 typed MCP tools**, two resource guides and two reusable prompts. Open/create a map in the app first (generation itself does not require an open map).

| AI workflow | Tools |
| --- | --- |
| Discover assets | `get_editor_status`, `list_prefab_categories`, `search_prefabs`, `get_prefab_details`, `request_prefab_assets` |
| Inspect the build | `get_scene_info`, `list_map_objects`, `get_object_info`, `sample_surface` |
| Compose Rust models | `place_prefab`, `place_prefabs`, `transform_object`, `transform_objects`, `duplicate_object`, `delete_object`, `group_objects`, `ungroup_object`, `rename_object`, `snap_objects_to_terrain` |
| See the result | `focus_view` (current/front/back/left/right/top/bottom), `get_viewport_image` (PNG image for vision-capable clients) |
| Terrain and paths | `paint_terrain`, `get_path_info`, `create_path`, `update_path` |
| Reuse and finish | `import_assembly`, `export_assembly`, `validate_map`, `save_project`, `export_map`, `undo`, `redo` |

The AI can enumerate **every indexed prefab**: browse categories or call
`search_prefabs` with an empty query, following `next_offset` until it is null. Use `available_only=True` to exclude
entries missing from the local bundles.
Asset details include cached local dimensions/bounds and mesh/material/triangle
counts. Uncached models return instructions to preload them and poll extraction
status (including queued viewport visuals). Failed worker starts return an MCP
error and preserve pending IDs for retry. IDs always come from the local catalog; they must never be invented.
Catalog coverage depends on the installed game's index and supported extraction.

Modeling means composing **whole original Rust prefabs**, including scaled and
rotated parts, into named reusable groups. Batch placement (up to 100) and batch
transforms (up to 200) roll back completely on failure and create one undo step.
Nonuniform transforms that would introduce shear are rejected. Paths support
2–4096 world nodes with typed width, masks, offsets and connection settings.
Compositions export/import as `.rusterprefab` (MCP import limit: 1000 placements).
The map exporter flattens composition groups into original prefab records.

The server's initialization instructions describe discovery, sizing, terrain
sampling, building and visual inspection. Resources `ruster://guide/building`
and `ruster://guide/terrain` provide detailed conventions; prompts
`build_rust_composition` and `audit_rust_map` guide creation and inspection.
Positions use editor world metres, with Z as height; rotations are XYZ degrees.
Surface snapping moves the object's origin, so use model bounds for bottom
clearance. Bounds enclose meshes; they do not certify game collisions. Viewport
images require the desktop app. Actual current-game assets/server behavior still
need real-game validation.

The listener is local-only (`127.0.0.1`, default port `9877`), with a per-user token
read automatically by the bundled adapter. The toggle stops active connections;
stop it before changing ports. Existing save/export destinations require an
explicit overwrite request, and source maps cannot be overwritten. Edits wait
until brush strokes and path node editing have finished.

Ruster uses the community transport and inspection code, not its unrestricted
Python execution or external model-generation/download tools. Prefab models stay
read-only through MCP as well as the UI. No community telemetry or consent prompts
are bundled. Port, token and enablement belong to user settings, not projects.
Connect it in an MCP-compatible client using the copied configuration.

## Run from source

Requires Blender **5.2 LTS** (tested against the pinned 5.2.3 runtime). Python
3.13 is used by Blender. Your ordinary Blender settings are isolated from Ruster.

```powershell
# Windows: launch.py also accepts --blender "C:\path\to\blender.exe"
$env:RUSTER_BLENDER = 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe'
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

Run on Windows x64 or Linux x64, using Python 3.13:

```bash
python tools/package.py --archive
```

This downloads the official Blender archive pinned in `engine.lock.json`, verifies
its SHA256, bundles Ruster and asset-reader dependencies, and runs the Blender
integration test. Windows packaging creates `Ruster.exe`. Linux uses `Ruster.sh`.
No separate Blender or Python installation is needed to use the packaged app.
Use `--output-name Ruster-windows-x64-5.2` for a separate build folder while
keeping an older app folder. Startup errors are recorded in
`%LOCALAPPDATA%\Ruster\logs\startup.log` on Windows.
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
  Rust's native procedural seed generation. The separate RustDedicated backend
  runs Rust's own generator, but has not been verified against an installed game here.
  Road/river previews and grading are
  authoring approximations pending in-game comparison tests.
- Existing Blender shortcuts and advanced editor switching remain available. Map
  mode is a focused authoring workspace, not a restricted Blender sandbox.
- The source customizes pinned Blender through its Python API. It does not maintain
  a divergent C/C++ tree. [FEATURES.md](FEATURES.md) records the full remaining backlog.

## Validation

```bash
python -m pip install pytest lz4 numpy -r requirements-assets.txt -r requirements-mcp.txt
python -m pytest -q
/path/to/blender -b --factory-startup --disable-autoexec --python tests/blender_smoke.py
/path/to/blender -b --factory-startup --disable-autoexec --python tests/blender_editing.py
/path/to/blender -b --factory-startup --disable-autoexec --python tests/blender_placement.py
/path/to/blender -b --factory-startup --disable-autoexec --python tests/blender_protection.py
/path/to/blender -b --factory-startup --disable-autoexec --python tests/blender_ui.py
/path/to/blender -b --factory-startup --disable-autoexec --python tests/blender_mcp.py
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
The graphical MCP test (`tests/gui_mcp.py`) uses a real stdio SDK client through
the local bridge, checks typed edits and undo, rejects unauthenticated/Python
commands, and verifies disable/restart and automatic Steam discovery. Packaging
also checks the stdio entry point with its own bundled Python and dependencies.

These tests use synthetic map data and original test geometry. They do **not**
establish compatibility with every Rust asset or confirm a map in a running Rust
server. See [architecture](docs/architecture.md) and [format](docs/ruster-format.md).

## License

Ruster is GPL-3.0-or-later. Blender and bundled libraries retain their respective
licenses and notices. A private development repository is compatible with this;
distributing the application requires complying with the corresponding source
requirements. Rust assets remain Facepunch's content and are not covered by
Ruster's source license. See `THIRD_PARTY_NOTICES.md`.
