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
The startup popup opens in the center of the app window, independently of the
mouse position; reopening Start uses the same placement.

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

Press **Shift+A** for a compact native Add menu with prefab category submenus.
Start typing immediately, or choose **Search All Prefabs…**, to search the entire
catalog across all categories. Press Enter once to place a result at the 3D
cursor. Names and IO aliases match regardless of capitalization or word order.
The Add menu prepares a shared metadata index in small idle-time batches and
reuses it across categories/search. Catalog and favorite changes refresh it;
typing does not repeatedly scan the catalog or load game models.
The Prefab Browser also offers categories, favorites, local availability,
full-path/ID tooltips and paginated results.
Its **Recent** filter lists the last 48 distinct prefabs placed, newest first.
The information button inspects an asset's full path, ID, local availability and
cache status before placement, with Copy ID / Copy Path actions. **Reset Filters**
shows all locally available assets, including hidden helpers.
Use Blender's navigation, selection, `G`, `R`, `S`, snapping and undo. Placements
can be grouped, duplicated, replaced and removed. **Shift+F** enters Walk
Navigation. The authoring plane is Z=0.

The viewport header's **Perspective** icon toggles perspective/orthographic
projection (also **Numpad 5**); its pressed state indicates perspective. The
**Overlays** toggle sits immediately beside it and controls viewport guides.

The **left toolbar** includes **Object Snap** (magnet) and **Radial Symmetry**
(array) toggles, each with a settings popover below it. Snap Settings offers
vertex, edge or face snapping to loaded original models and **45° / 90°** steps
for native `R` rotation. **Align Rotation to Step** rounds an existing selection
to the chosen world angles. `Ctrl` temporarily toggles native snapping.

Enable Radial Symmetry before adding a prefab to create **2–16 sides** (including
the original), rotated around the vertical Z axis through the world center
`(0, 0, 0)` by default. Set another center numerically or with **Center at 3D
Cursor**. While symmetry is enabled, move, rotate or scale **any member** and the
other members follow radially. Deleting any member removes that entire set.
Turn symmetry off to edit or delete individual placements, or use **Make
Symmetry Set Independent** to unlink them permanently. Settings apply to new
sets; existing sets retain their center and side count. Placement is one undo
step, and saved `.ruster` projects retain the symmetry sets.

Original mesh and material data remain protected linked libraries. Transform
whole placements or groups; model exports use temporary realized copies. A
wireframe box identifies a placement awaiting its model and disappears when the
original linked model attaches. IDs, transforms and interchange data remain
independent of that display box. Errors and cancellation appear in asset status.
The header's **Models** popover and **Model Loading** panel show loaded, loading,
unloaded, issue and helper counts. Use **Select Unloaded** or **Select Issues**,
then **Load / Retry Selected Models**. **View Asset Report** displays readable
errors and offers a copy of the complete report.

**Shift+A** includes hidden helpers and unavailable catalog entries, regardless
of the sidebar's current filters. Search `cyan tube` or `glowing hose` for **IO Hose Tube
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
| Export Blender File (.blend) | In the top-left Ruster menu and Prefab Studio panel. Exports the whole composition by default, with optional selected-only export, as a regular Blender scene with editable meshes, local materials and packed textures. Open in normal Blender to add cameras/lights and render; loaded geometry is required. |
| Export Models | Offers available GLB/glTF, FBX, OBJ, PLY, STL, USD, Alembic and Blender scene exporters; loaded geometry is required. |

Native `.prefab` interchange was verified against installed RustEdit 1.2.19 and
the supplied 1,730-placement Maze: unchanged import/export preserves the complete
file byte-for-byte, including IO metadata. Existing IO scalar settings can be
edited. Supported IO endpoints follow moved placements when identity/order stays
valid; ambiguous edits are blocked. See [the compatibility contract](docs/rustedit-prefabs.md).
This does not establish server behavior or support creating new wiring.

Recovery saves atomically every two minutes while idle. Use **Recover Autosaved
Session** in New / Open after a crash. Recovery preserves the regular save target.
Quit Ruster (`Ctrl+Q`, or the Windows close button / `Alt+F4`) checks the saved
`.ruster` document. Unchanged projects close directly; unsaved changes offer
Save, Don't Save and Cancel using the project filename. Save opens the `.ruster`
picker for untitled projects. Cancelling or a failed save keeps the editor open.
New and Open use the same save choices before replacing unsaved work. The header,
Prefab Studio panel and Windows window caption show the project's save state.
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

There are **52 typed tools**, two resource guides, and two reusable prompts:

| Workflow | Representative tools |
| --- | --- |
| Discover and size | `get_editor_status`, `list_prefab_categories`, `search_prefabs`, `get_prefab_details`, `get_prefabs_details`, `request_prefab_assets` |
| Inspect and select | `list_objects`, `get_objects_info`, `get_selection`, `select_objects`, `focus_view`, `get_viewport_image` |
| Compose | `place_prefabs`, `transform_objects`, `group_objects`, `duplicate_objects`, `array_objects`, `align_objects`, `snap_objects_to_plane`, `delete_objects` |
| Native Blender and layout | `get_blender_context`, `get_viewport_state`, `set_viewport_state`, `set_cursor`, `measure_objects`, `transform_objects_relative`, `radial_array_objects`, `distribute_objects`, `snap_objects_to_grid` |
| Interchange and finish | `import_prefab`, `export_prefab`, `import_map_prefabs`, `export_map`, `get_io_settings`, `set_io_settings`, `get_export_formats`, `export_models`, `save_project`, `validate_map`, `undo`, `redo` |

Read `ruster://guide/design` ([docs/design.md](docs/design.md)) and
`ruster://guide/building` first; the workflow source is
[BUILDING_GUIDE in the adapter](ruster/mcp_server.py). The prompts
`build_rust_composition` and `audit_rust_composition` guide creation and inspection.
Use actual catalog IDs and follow `next_offset` to discover every result. Request
uncached models and poll status before relying on visible geometry/bounds.

Coordinates are world XYZ metres with Z up; rotations are XYZ Euler degrees.
Atomic placement batches allow 100 items, transforms 200; array/duplicate requests
allow at most 2,000 new placements. Bounds alignment and plane snapping use loaded
render geometry, not collision certification. MCP native-prefab, map and assembly
imports are limited to 2,000 placements. Model exports have a
bounded copy budget and may require smaller selections. After a timed-out
mutation, inspect the scene before repeating it.

`focus_view` supports native axes, `OBLIQUE`, or explicit `rotation_degrees`
without moving the composition. Viewport images hide overlays by default and
restore the user's display settings after capture. Assembly exports preserve a
single group's pivot; `origin` can explicitly set the world XYZ export anchor.
Importing an assembly preserves its requested position as the group pivot.

Native viewport controls expose target, distance, rotation, projection, shading,
overlays, X-ray, lens and clipping without moving models. Relative transforms
scale on world axes, rotate around a shared pivot, then translate; shear is
rejected. Radial arrays use an explicit center and axis: seven new copies at a
45 degree step make eight parts including the source. Distribution respects the
supplied name order and offers origin spacing or gaps between loaded bounds.
Grid snapping rounds origins on chosen axes. Measurements report origin distance
and optionally render-bounds separation. Turn off live Radial Symmetry before
batch layout of linked set members. Viewport and cursor settings are UI state
without an undo step; placement layout edits support undo.

Build with whole Rust assets: custom mesh primitives (including a new triangle),
mesh edits and material replacement cannot become game prefabs. Existing
triangular Rust parts and triangular arrangements are allowed. Whole placements
can rotate freely. Static decoration scaling needs verification; networked doors,
IO and deployables ignore scaling in Rust. See the sourced rules in [docs/design.md](docs/design.md).

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
python tools/native_checks.py --engine /absolute/path/to/blender --suite background
python tools/native_checks.py --engine /absolute/path/to/blender --suite graphical
python tests/mcp_stdio_smoke.py /absolute/path/to/packaged/Ruster
```

CI and packaging share the background suite. Graphical checks use disposable
Blender processes and synthetic assets; Linux CI adds `--xvfb` for a virtual
display. Set `RUSTER_TEST_PYTHON` to the interpreter with `requirements-mcp.txt`
installed for the graphical MCP client. Run the last command with the package's
Python/dependencies available. The
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
