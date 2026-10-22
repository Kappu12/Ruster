# Architecture

`launch.py` starts a pinned or user-selected Blender 4.5 executable in its own
process with isolated user configuration, factory startup and automatic scripts
disabled. `bootstrap.py` registers the Ruster application. Packaged builds ship
Blender's runtime; users do not install an add-on manually.

| Module | Responsibility |
|---|---|
| `ruster/app.py` | Operators, startup, project lifecycle, worker management |
| `ruster/ui.py` | Native UI menus, panels, workspace configuration |
| `ruster/scene.py` | Scene construction, shared model instances, validation and export |
| `ruster/editing.py` | Full-resolution terrain state, brushes, paths, height images and generation |
| `ruster/protection.py` | Read-only model libraries, packing, restoration and geometry export guards |
| `ruster/browser.py` | Categories, native catalog filters and local favorite palettes |
| `ruster/painting.py` | Native continuous prefab placement tool, palettes, stroke undo/cancel |
| `ruster/core/palettes.py` | Validated persistent favorite IDs |
| `ruster/placement.py` | Groups, prefab assemblies, scatter, snap and replacement |
| `ruster/core/terrain.py` | Terrain algorithms, layer snapshots, normalization and sampling |
| `ruster/core/paths.py` | Lossless path records and polyline sampling |
| `ruster/core/wire.py` | Lossless protobuf fields |
| `ruster/core/legacy_lz4.py` | Dependency-free legacy LZ4Stream reader/writer |
| `ruster/core/rust_map.py` | Rust map header, world, layers and prefab records |
| `ruster/core/project.py` | Versioned `.ruster` archive and atomic saving |
| `ruster/assets/catalog.py` | SQLite local prefab, bundle and dependency catalog |
| `ruster/assets/worker.py` | UnityPy indexing and mesh/material conversion |

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
