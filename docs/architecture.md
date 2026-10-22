# Architecture

`launch.py` starts a pinned or user-selected Blender 4.5 executable in its own
process with isolated user configuration, factory startup and automatic scripts
disabled. `bootstrap.py` registers the Ruster application. Packaged builds ship
Blender's runtime; users do not install an add-on manually.

| Module | Responsibility |
|---|---|
| `ruster/app.py` | Operators, startup, project lifecycle, worker management |
| `ruster/ui.py` | Native UI menus, panels, workspace configuration |
| `ruster/scene.py` | Terrain/path preview, placement objects, asset attachment, validation and export |
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
5. Attach visuals incrementally in Blender. Multiple placements share mesh data.
   Model children are unselectable; users edit the placement root.

Asset indexing stores bundle size and nanosecond modification time for updates.
Extracted meshes are cache entries, not the authoritative map model. Unsupported
assets retain their map IDs and visible placeholders. The conversion approximates
materials in Blender; it does not implement Rust's rendering engine or gameplay.

## Extension priorities

Before broadening the UI, validate against a current real Rust installation and
server. Next add complete LOD selection/material fidelity, terrain editing with
full-resolution data, path editing/serialization, terrain layers, and RustEdit
extension data. Engine source changes should stay small and be isolated from the
Rust data adapter. The repo pins upstream rather than copying Blender's history.
