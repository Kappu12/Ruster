# Ruster

Ruster **0.9.0** is a Blender-based desktop editor for custom Rust prefab
compositions. Build with whole original models from your installed game, then
save a `.ruster` project or export a native `.prefab`, model file, or prefab-only
`.map`. Blender 5.2 LTS supplies the viewport, native controls, selection,
transforms and undo. [FEATURES.md](FEATURES.md) describes the supported scope.

## Start and install assets

Launch `Ruster.exe` on Windows or `Ruster.sh` on Linux. Packaged apps include their
Blender and Python runtime. Startup opens an empty **Prefab** workspace. The
**New / Open** popup provides New Prefab, Open Map/Prefab/Project, Import `.map`,
recent projects and recovery. New Prefab returns to an empty composition.

Open **Edit → Preferences**. **Assets** and **MCP** appear in the same left-hand
navigation as Blender's interface, theme and navigation preferences. Theme and
UI scale survive New Prefab.

Ruster detects validated Steam Rust installations, including secondary libraries.
If discovery fails, choose **Preferences → Assets**, select the folder containing
`Bundles`, and click **Apply Installation**, for example:

```text
C:\Program Files (x86)\Steam\steamapps\common\Rust
```

The catalog reads the game's `AssetSceneManifest.json` and a locally installed
RustEdit `stringpool.txt`. RustEdit's folder is detected or selected in Assets
preferences. Ruster reads these local files without launching Rust or RustEdit;
no game binaries or game assets are distributed in this repository.

## Compose and save

Use **Shift+A** or the Prefab Browser to search categories and place models at the
3D cursor. Searches accept descriptive words in any order; favorites, local
availability, full-path/ID tooltips and paginated results help locate assets.
Use Blender's navigation, selection, `G`, `R`, `S`, snapping and undo. Placements
can be grouped, duplicated, replaced and removed. The authoring plane is Z=0.

Original mesh and material data remain protected linked libraries. Transform
whole placements or groups; model exports use temporary realized copies. A
wireframe box identifies a placement awaiting its model and disappears when the
original linked model attaches. IDs, transforms and interchange data remain
independent of that display box. Errors and cancellation appear in asset status.

**Shift+A → Hidden & IO Helpers** and **Search All Assets (Including Hidden)**
expose internal assets. Search `cyan tube` or `glowing hose` for **IO Hose Tube
Pending (Cyan Glow)**. Its original Rust renderer is a small cyan emissive Cube;
authored placement scaling creates the long Maze strips. All eight IO hose/wire
handle variants were checked against their original local geometry and materials.
Sound, terrain-stamp and other geometry-free prefabs receive explicit helper
markers. Runtime-generated IO lines have no static mesh to reconstruct.

Textured Solid mode gives lightweight base texture/color feedback. Material
Preview and supported model exporters also use converted source emission,
metallic/smoothness masks and transparency. Shadow-only proxies stay hidden.
These are Blender previews; Rust's shader effects, bloom, animation, collisions
and gameplay are not reproduced exactly.

| File/action | Behavior |
| --- | --- |
| Save Project (`Ctrl+S`) | `.ruster` stores the scene and packed linked previews for reopening without the conversion cache. |
| Import/Export Prefab | Native RustEdit `.prefab` with supported imported metadata and existing IO settings. |
| Open/Import `.map` | Imports prefab IDs and world transforms only; Import appends to the composition. |
| Export `.map` | Writes current prefab placements in empty space, with no terrain or path layers. This is not a complete playable world. |
| Import/Export Assembly | `.rusterprefab` stores reusable prefab references and relative transforms. |
| Export Models | Offers available GLB/glTF, FBX, OBJ, PLY, STL, USD, Alembic and Blender-library exporters; loaded geometry is required. |

Native `.prefab` interchange was verified against installed RustEdit 1.2.19 and
the supplied 1,730-placement Maze: unchanged import/export preserves the complete
file byte-for-byte, including IO metadata. Existing IO scalar settings can be
edited. Supported IO endpoints follow moved placements when identity/order stays
valid; ambiguous edits are blocked. See [the compatibility contract](docs/rustedit-prefabs.md).
This does not establish server behavior or support creating new wiring.

Recovery saves atomically every two minutes while idle. Use **Recover Autosaved
Session** in New / Open after a crash. Recovery preserves the regular save target.
Opening legacy map projects recovers their prefab composition; the active product
does not expose terrain, path editing or seed generation. That source remains
inactive for compatibility work.

## On-demand loading and bounds

Catalog browsing never starts a full game-object index or bulk conversion.
Models resolve their named asset scene, required dependencies and referenced
visual prefabs only when requested. **Assets → Load Selected Models** accepts up
to 100 different IDs per request and can refresh an existing composition. Loaded
instances share models. Imports queue missing visuals; cached visuals recover
incrementally. If an installed update changes the worker during an open session,
save and restart before loading more models.

Each requested model uses a short-lived asset process. Windows limits each worker
to **768 MiB** private committed memory, its supervisor tree to **1 GiB**, and the
editor tree to **8 GiB**, including Material Preview driver/compiler headroom.
These are ceilings, not expected use; GPU allocations/shared pages are separate.
Jobs and watchdogs stop orphaned work. Unsupported assets remain labeled
placeholders with reports. Mesh buffers, streamed metadata and bounded texture
previews avoid accumulating an entire monument's source data in Python.

## MCP / AI editor connection

Open **Preferences → MCP**, enable MCP, and use **Copy MCP Client Configuration**
in your MCP client. Keep Ruster open. MCP is disabled by default; the packaged
stdio adapter includes its dependencies. A source checkout installs them with
`tools/setup_assets.py`.

There are **43 typed tools**, one resource guide, and two reusable prompts:

| Workflow | Representative tools |
| --- | --- |
| Discover and size | `get_editor_status`, `list_prefab_categories`, `search_prefabs`, `get_prefab_details`, `get_prefabs_details`, `request_prefab_assets` |
| Inspect and select | `list_objects`, `get_objects_info`, `get_selection`, `select_objects`, `focus_view`, `get_viewport_image` |
| Compose | `place_prefabs`, `transform_objects`, `group_objects`, `duplicate_objects`, `array_objects`, `align_objects`, `snap_objects_to_plane`, `delete_objects` |
| Interchange and finish | `import_prefab`, `export_prefab`, `import_map_prefabs`, `export_map`, `get_io_settings`, `set_io_settings`, `get_export_formats`, `export_models`, `save_project`, `validate_map`, `undo`, `redo` |

Read `ruster://guide/building` first; its source is
[BUILDING_GUIDE in the adapter](ruster/mcp_server.py). The prompts
`build_rust_composition` and `audit_rust_composition` guide creation and inspection.
Use actual catalog IDs and follow `next_offset` to discover every result. Request
uncached models and poll status before relying on visible geometry/bounds.

Coordinates are world XYZ metres with Z up; rotations are XYZ Euler degrees.
Atomic placement batches allow 100 items, transforms 200; array/duplicate requests
allow at most 2,000 new placements. Bounds alignment and plane snapping use loaded
render geometry, not collision certification. MCP native-prefab and map imports
are limited to 2,000 placements; assembly imports to 1,000. Model exports have a
bounded copy budget and may require smaller selections. After a timed-out
mutation, inspect the scene before repeating it.

The authenticated listener uses `127.0.0.1:9877` by default and a per-user token.
Port and enablement belong to preferences. Existing output files require explicit
`overwrite=True`. There is no arbitrary Python execution, terrain/path editing,
map generation or external model download API. The transport adapts MIT-licensed
[MCP for Blender](https://github.com/ahujasid/mcp-for-blender); see
[third-party notices](THIRD_PARTY_NOTICES.md).

## Source, packaging and checks

Use Blender **5.2 LTS**; the pinned runtime is **5.2.3**, with Python **3.13**.
Ruster uses an isolated Blender configuration.

```powershell
$env:RUSTER_BLENDER = 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe'
py -3 tools/setup_assets.py
py -3 launch.py
```

Linux/macOS source launch uses `RUSTER_BLENDER=/path/to/blender` and
`python3 tools/setup_assets.py`, then `python3 launch.py`. A project path may be
passed to the launcher. Setup uses Blender's Python and leaves Rust unchanged.

On Windows x64 or Linux x64, package using Python 3.13:

```text
python tools/package.py --archive --output-name Ruster-windows-x64-5.2
```

Use a platform-appropriate output name. Packaging verifies the pinned official
Blender archive, bundles dependencies, and runs prefab-product, protection, UI,
MCP, linked-library and transform checks plus the actual packaged stdio entry
point. Build outputs are under `dist`; macOS standalone packaging is pending.
Windows startup errors are logged in `%LOCALAPPDATA%\Ruster\logs\startup.log`.

```text
python -m pip install pytest lz4 numpy -r requirements-assets.txt -r requirements-mcp.txt
python -m pytest -q
blender -b --factory-startup --disable-autoexec --python-exit-code 1 --python tests/blender_prefab_product.py
blender -b --factory-startup --disable-autoexec --python-exit-code 1 --python tests/blender_placeholders.py
blender -b --factory-startup --disable-autoexec --python-exit-code 1 --python tests/blender_prefab_transforms.py
blender -b --factory-startup --disable-autoexec --python-exit-code 1 --python tests/blender_mcp.py
python tests/mcp_stdio_smoke.py /absolute/path/to/packaged/Ruster
```

Run the last command with the package's Python/dependencies available. The
opt-in `tests/blender_hidden_assets.py -- PATH_TO_ASSET_CACHE` checks all eight
previously converted original IO variants in an isolated temporary profile; it
does not scan or redistribute game assets. Legacy world-editor tests remain in
source and do not describe the active product. Current-game asset coverage,
engine shader parity and live-server compatibility remain separate validation
work. See [format notes](docs/ruster-format.md) and [feature coverage](FEATURES.md).

## License

Ruster is GPL-3.0-or-later. Blender and bundled libraries retain their licenses;
distributions must meet corresponding-source requirements. Rust assets remain
Facepunch's content. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
