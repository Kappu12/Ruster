# Architecture

`launch.py` starts a pinned or user-selected Blender 5.2 executable in its own
process with isolated user configuration, factory startup and automatic scripts
disabled. `bootstrap.py` registers the Ruster application. Packaged builds ship
Blender's runtime; users do not install an add-on manually.

| Module | Responsibility |
|---|---|
| `ruster/app.py` | Operators, startup, project lifecycle, worker management |
| `ruster/headless.py` | Persistent background host, main-thread command/asset pump and orderly shutdown |
| `ruster/core/headless.py` | Shared CLI profile selection and process-owned profile lock |
| `ruster/ui.py` | Native UI menus, panels, workspace configuration |
| `ruster/scene.py` | Scene construction, shared model instances, validation and export |
| `ruster/editing.py` | Full-resolution terrain state, brushes, paths, height images and generation |
| `ruster/protection.py` | Read-only model libraries, packing, restoration and geometry export guards |
| `ruster/browser.py` | Categories, native catalog filters and local favorite palettes |
| `ruster/painting.py` | Native continuous prefab placement tool, palettes, stroke undo/cancel |
| `ruster/core/palettes.py` | Validated persistent favorite IDs |
| `ruster/placement.py` | Groups, prefab assemblies, scatter, snap and replacement |
| `ruster/construction.py` | Live radial sets, frame-aware group transforms and snapping |
| `ruster/layout.py` | Native array, alignment, distribution, grid and composition-check UI |
| `ruster/map_prefabs.py` | Prefab-only map interchange and shared placement export validation |
| `ruster/core/terrain.py` | Terrain algorithms, layer snapshots, normalization and sampling |
| `ruster/core/paths.py` | Lossless path records and polyline sampling |
| `ruster/core/wire.py` | Lossless protobuf fields |
| `ruster/core/legacy_lz4.py` | Dependency-free legacy LZ4Stream reader/writer |
| `ruster/core/rust_map.py` | Rust map header, world, layers and prefab records |
| `ruster/core/project.py` | Versioned `.ruster` archive and atomic saving |
| `ruster/assets/catalog.py` | SQLite local prefab, bundle and dependency catalog |
| `ruster/assets/worker.py` | UnityPy indexing and mesh/material conversion |

## Headless sessions

`launch.py --headless` sets an explicit host mode and starts Blender with
`--background`. Bootstrap registers the same application and enters
`ruster.headless.run`. Background Blender does not service application timers:
the host drains the authenticated command queue, polls asset workers, attaches
prepared models and ticks the owned preview session on the main thread. Socket
threads only enqueue work. Each drain is bounded so clients cannot indefinitely
starve asset loading. No arbitrary Python RPC is exposed.

The headless bridge dispatches without a window context. Its status advertises
unsupported viewport/undo tools, which fail explicitly before mutation. Global
undo is disabled; the existing atomic operations and save/overwrite/unsaved-work
guards are shared with the desktop. Saved projects can be reopened in either mode.

The default profile and port are separate from the desktop. An OS file lock
protects a headless profile for the entire host lifetime, including cleanup.
Signals stop the main loop, listener, asset workers and owned preview session.
Readiness includes the stdio adapter configuration; the adapter reads the token
from that profile rather than exposing it in process arguments or logs.

## Coordinates

Rust/Unity is Y-up; Blender is Z-up. The adapter uses `(x,y,z) → (x,z,y)` and
conjugates rotation matrices by that basis. This reflects handedness, so triangle
winding reverses. Unity Euler angles are interpreted as Z-X-Y order. Source
Euler values are preserved when an object's transform has not changed.

## Asset pipeline

1. Validate the selected game folder, then scan only Unity AssetBundle files in
   its `Bundles` directory. Do not launch/inject into the game or modify files.
2. Store prefab container pointers and explicit prefab ID lookup tables. Support
   `Prefabs.txt` CSV and recognizable embedded GameManifest string/ID pairs.
3. Catalog serialized file names so cross-bundle mesh/material/texture references
   can load the correct dependency lazily.
4. Export requested prefab hierarchies and triangle meshes through UnityPy into
   local compressed JSON plus PNG textures. Report partial failures explicitly.
5. Build a fresh preview collection from conversion data; never reuse editable
   legacy meshes/materials as source geometry. Write a cached `.blend` library,
   then link the collection read-only. Model materials, images and meshes belong
   to that library; do not create dependencies on another model's fallback material.
6. Attach these collections incrementally. Placements share a linked collection
   behind editable empty handles. Native edit/sculpt/modifier operators reject
   linked source IDs. Library IDs and textures are packed when saving `.ruster`.
7. Validate that models are linked, unoverridden, from original conversion data
   and match the placement ID. Reject unpacked/localized copies. Lock old local
   previews on load but rebuild from original local assets before trusting them.

Asset indexing stores bundle size and nanosecond modification time for updates.
Extracted meshes are cache entries, not the authoritative map model. Unsupported
assets retain their map IDs and visible placeholders. The conversion approximates
materials in Blender; it does not implement Rust's rendering engine or gameplay.

Bounds and model exports derive linked model matrices from each object's local
basis and parent-inverse chain, then apply the collection offset and placement
world transform once. Library objects outside the active scene can retain stale
`matrix_world` values even when their evaluated instances render correctly. No
asset-cache rebuild is needed for this calculation. Model exports bake internal
hierarchy shear into disposable mesh copies, counted against the export budget;
source libraries and native prefab placement records stay unchanged.

## Terrain state and undo

A scene's `terrain_state` points at an immutable Text datablock containing a
compressed snapshot of every changed layer. An in-progress stroke edits a fresh
NumPy document and updates the viewport; release commits one snapshot. Cancel
restores the prior document. Native Blender undo/redo restores the ID pointer;
handlers rebuild previews from it. `.ruster` stores both the scene and source map.

Viewport resolution can be adjusted independently. Alpha changes remove preview
faces; heightfield ray intersection still allows users to paint holes closed.
Terrain-height changes update the derived spawn-height layer by the same delta,
retaining the previous offset from prefab relief. Water has a separate preview.

## Prefab painting

A stroke captures a validated local catalog palette and a spacing hash populated
from existing placement origins. Terrain sampling applies slope/hole/bounds
filters. New objects contain only Rust placement records and linked visual
instances. Mouse movement interpolates stamps; release creates one native undo
step. Cancel removes every created placement. Recovery skips both terrain and
prefab strokes. Background extraction requests are queued rather than cancelling
placements when an asset worker is occupied or the installation is unavailable.

These are authoring constraints through the supported UI and native operators,
not a security sandbox against arbitrary scripts or edits to cache files.

## Remaining work

See `FEATURES.md` for the maintained parity inventory. Current-game asset and
server validation remain necessary before claiming full compatibility. IO,
loot/vending/spawners and special patrol/server extension formats need dedicated,
verified serializers and runtime tests rather than a decorative configuration UI.
