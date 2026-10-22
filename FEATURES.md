# RustEdit feature coverage

Goal: a polished Blender-based Rust world editor covering RustEdit's workflows.
This is a maintained implementation checklist, **not a claim of complete parity**.
Statuses refer to code and automated tests. Current Rust assets and server behavior
still need validation against an installed game and a live test server.

## Implemented

| Area | Ruster support |
|---|---|
| Application | Separate Windows/Linux app package; isolated Blender configuration; native Blender styling and bundled icon pack; shared action labels, collapsible sections, distinct terrain/prefab toolbar icons; preserve dark/light theme on New Project |
| Startup | Blender 5.2; native splash; automatic validated Rust discovery; manual fallback; open `.map` / `.prefab` / `.ruster`, empty prefab compositions, new Rust maps, recent files |
| Rust workspace | Rust menus and sidebar, viewport and placement hierarchy; hidden general Properties, timeline, modeling menus, workspace tabs and unrelated sidebar tabs; Shift+A broad categories with typed prefab search |
| MCP | Optional built-in community Blender MCP adaptation; shared Blender Preferences section and native toggle, bundled stdio client adapter, 35 typed tools; complete paginated catalog discovery, cached model dimensions, atomic composition batches, groups, reusable assemblies, terrain samples, typed paths, viewport PNG feedback, asynchronous generation/status/cancel, two resource guides and two workflow prompts, local-only authenticated connection; no arbitrary Python or prefab mesh commands |
| Projects | Self-contained `.ruster`, atomic saves, source map retention, packed model previews, integrity checks |
| Terrain | Full-resolution edits; independent adjustable viewport detail; height and slope masks |
| 2D Maps | Native Image Editor workspace; height, water, spawn height, slope, splat, biome, topology and holes; composite/channel views, bounded previews, pan/zoom and edit/undo refresh |
| Height tools | Raise, lower, flatten, smooth, erode, sharpen, terrace, noise, pinch, twist, slope plane |
| Clone | Fixed-source clone brush; other RustEdit clone movement modes remain below |
| Stamps | Grayscale image stamp, brush rotation, positive/negative stamp, radius, strength and falloff |
| Bridge | Grade between two cursor positions |
| Height images | Import 16-bit PNG/TIFF/RAW, resize by bilinear sampling, export 16-bit PNG |
| Layer image masks | Export grayscale PNG; import 8/16-bit grayscale PNG/TIFF for ground textures, 4/5-channel biomes, individual topology bits and terrain holes; native-resolution resize, orientation control, exact selected weights, unrelated-bit preservation, undo and project persistence |
| Procedural terrain | Seeded fractal island generator; this is Ruster generation, not Rust's native seed generator |
| Rust-native generation backend | Optional installed RustDedicated, seed/size controls, Steam discovery, headless background job, isolated identity, loopback settings, validated map detection, early process stop, cancellation/timeout and logs; synthetic lifecycle tested, actual game integration/performance pending |
| Ground textures | Eight-channel paint, blending and exact weight normalization; `ground`/`splat` layer names |
| Biomes | Four- and five-channel layouts, including Jungle where present |
| Topology | Add/remove individual topology bits, retain unrelated and unknown bits |
| Alpha | Cut and restore terrain holes, visible preview holes and heightfield picking through holes |
| Water | Water-height painting and surface preview; river bed/water grading |
| Prefab placement | Native selection, XYZ angle controls with rotation mode picker, transforms, snapping, duplicate/delete, shared geometry instances |
| Prefab protection | Read-only linked model/mesh/material IDs, placement-only handles, original-model restore, export guards for editable/unpacked models |
| Prefab browser | Indexed case-insensitive lookup; category, available-local and favorite filters; literal search; result/page counts; full-path/ID tooltips; copy-ID action; stale-page recovery |
| Prefab paint | Continuous placement, single/favorite/selected-type palettes, random scale/rotation, alignment, origin spacing, slope and alpha-hole filters; stroke undo/cancel |
| Prefab assemblies | Group/ungroup, group transforms, `.rusterprefab` import/export |
| RustEdit prefabs | Current installed 1.2.19 serializer interoperability, native version-1 `.prefab` import/export, current checksum, byte-exact unchanged round trips, unknown-field retention, IO endpoint movement with identity/order checks; validated locally with 1,730-placement Maze |
| IO settings | Edit existing imported card access, door effect, timer, frequency, turret, branch, counter, camera, elevator and phone settings; preserve unknown fields and connections |
| Model export | GLB, glTF, FBX, OBJ, PLY, STL, USD/USDA/USDC, Alembic and Blender model library; actual exporter checks, temporary realized copies and cleanup, protected originals |
| Placement tools | Terrain snap, surface alignment, seeded scatter, spacing/slope filters, select same type, replacement |
| Paths | Create/edit road, river, rail and powerline polylines; extend/delete nodes with Blender curve tools |
| Path settings | Width, padding, fades, offsets, flags, splat/topology masks; preserve unknown fields |
| Path grading | Grade terrain, road splat/topology, river bed/water, terrain snapping |
| Local assets | Unity bundle catalog, explicit prefab IDs, dependency resolution, hierarchy and triangle mesh conversion |
| Materials | Base color/textures, UV tiling/offset, common metallic/roughness/alpha properties |
| LOD | Select the first nonempty authored LOD rather than drawing overlapping LOD meshes |
| Asset updates | Bundle/dependency cache invalidation, refresh existing visuals, cancel background work, reports |
| Recovery | Two-minute atomic recovery save, start-screen recovery, skip active terrain and prefab strokes |
| Undo | Native Blender undo/redo retains full-resolution terrain snapshots and prefab/path edits |
| Export | `.map` versions 9/10, modified terrain/path/prefab records, preserve unedited and unknown fields |
| Validation | Non-finite/invalid transforms, unsupported custom geometry, group shear, invalid paths, source protection |

## Remaining for RustEdit parity

- [ ] Confirm real current-game asset coverage: monuments, nested prefabs, foliage,
  skinned meshes, terrain materials, shaders and changing manifests.
- [ ] Confirm exports in current Rust dedicated server and maintain real-map fixtures.
- [ ] Remaining `.prefab` extension authoring and reference remapping, monument breaking/unpacking and monument
  terrain/splat/topology/biome stamps and placement masks.
- [ ] Prefab thumbnails, palette presets and game-collider placement collision checks.
- [ ] Clone follow/snap modes, ridge erosion, additional terrain processing and
  custom brush libraries; improve adaptive terrain detail for large worlds.
- [ ] Dedicated splat mixer, bulk multi-channel layer image sets, automatic biome/splat/
  topology generation rules and spawn-condition visualizations.
- [ ] Road/river/rail surface geometry previews and exact game generation behavior;
  path-specific placement constraints and monument integration.
- [ ] Validate RustDedicated generation with current game builds; investigate a
  compatible standalone generation-only runtime. Selectable RustEdit-style passes,
  presets and customization of the existing world's generation pipeline are not implemented.
- [ ] New IO connection authoring and complete puzzle configuration beyond imported scalar settings.
- [ ] Loot profiles, vending profiles, NPC/vehicle spawners and spawn settings.
- [ ] Cargo ship ocean paths, Bradley APC patrols and server extension integration.
- [ ] Resolve extension references correctly when linked entities are cloned,
  replaced or deleted. Preserving opaque bytes alone does not establish this.
- [ ] Map resize/rotate/merge, monuments and railroad/subway generation workflows.
- [ ] Server launch/playtest workflow, screenshot/minimap tools and packaging polish.
- [ ] macOS app packaging and signed/notarized releases.

## Reference inventory

Current custom-prefab contracts are verified by inspecting the user's installed
RustEdit 1.2.19 assemblies and invoking its serializer locally, rather than relying
on the obsolete 2019 repository. The wider inventory also uses the editor's own
documentation and public SDK, checked 2026-10-22. Comparison testing must continue
for undocumented and version-specific behavior.

- https://github.com/k1lly0u/RustEdit_Docs
- https://rustedit.rusthq.com/terrain/height-tools
- https://rustedit.rusthq.com/terrain/paint-tools
- https://rustedit.rusthq.com/terrain/brushes
- https://rustedit.rusthq.com/terrain/filters
- https://rustedit.rusthq.com/terrain/clone-and-stamp
- https://rustedit.rusthq.com/procedural/procedural-panel
- https://wiki.facepunch.com/rust/Creating-a-server
- https://github.com/k1lly0u/RustEdit_Docs/blob/master/TerrainTools.md
- https://wiki.facepunch.com/rust/Map_Editors
- https://wiki.facepunch.com/rust/Map_Data
- https://wiki.facepunch.com/rust/Terrain
- https://github.com/k1lly0u/Oxide.Ext.RustEdit
