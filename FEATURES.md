# RustEdit feature coverage

Goal: a polished Blender-based Rust world editor covering RustEdit's workflows.
This is a maintained implementation checklist, **not a claim of complete parity**.
Statuses refer to code and automated tests. Current Rust assets and server behavior
still need validation against an installed game and a live test server.

## Implemented

| Area | Ruster support |
|---|---|
| Application | Separate Windows/Linux app package; isolated Blender configuration; native Blender styling |
| Startup | First-launch game location, open `.map` / `.ruster`, normal Blender projects, new Rust maps, recent files |
| Projects | Self-contained `.ruster`, atomic saves, source map retention, packed model previews, integrity checks |
| Terrain | Full-resolution edits; independent adjustable viewport detail; height and slope masks |
| Height tools | Raise, lower, flatten, smooth, erode, sharpen, terrace, noise, pinch, twist, slope plane |
| Clone | Fixed-source clone brush; other RustEdit clone movement modes remain below |
| Stamps | Grayscale image stamp, brush rotation, positive/negative stamp, radius, strength and falloff |
| Bridge | Grade between two cursor positions |
| Height images | Import 16-bit PNG/TIFF/RAW, resize by bilinear sampling, export 16-bit PNG |
| Procedural terrain | Seeded fractal island generator; this is Ruster generation, not Rust's native seed generator |
| Ground textures | Eight-channel paint, blending and exact weight normalization; `ground`/`splat` layer names |
| Biomes | Four- and five-channel layouts, including Jungle where present |
| Topology | Add/remove individual topology bits, retain unrelated and unknown bits |
| Alpha | Cut and restore terrain holes, visible preview holes and heightfield picking through holes |
| Water | Water-height painting and surface preview; river bed/water grading |
| Prefab placement | Native selection, transforms, snapping, duplicate/delete, shared geometry instances |
| Prefab assemblies | Group/ungroup, group transforms, `.rusterprefab` import/export |
| Placement tools | Terrain snap, surface alignment, seeded scatter, spacing/slope filters, select same type, replacement |
| Paths | Create/edit road, river, rail and powerline polylines; extend/delete nodes with Blender curve tools |
| Path settings | Width, padding, fades, offsets, flags, splat/topology masks; preserve unknown fields |
| Path grading | Grade terrain, road splat/topology, river bed/water, terrain snapping |
| Local assets | Unity bundle catalog, explicit prefab IDs, dependency resolution, hierarchy and triangle mesh conversion |
| Materials | Base color/textures, UV tiling/offset, common metallic/roughness/alpha properties |
| LOD | Select the first nonempty authored LOD rather than drawing overlapping LOD meshes |
| Asset updates | Bundle/dependency cache invalidation, refresh existing visuals, cancel background work, reports |
| Recovery | Two-minute atomic recovery save, start-screen recovery, skip active strokes/modal terrain state |
| Undo | Native Blender undo/redo retains full-resolution terrain snapshots and prefab/path edits |
| Export | `.map` versions 9/10, modified terrain/path/prefab records, preserve unedited and unknown fields |
| Validation | Non-finite/invalid transforms, unsupported custom geometry, group shear, invalid paths, source protection |

## Remaining for RustEdit parity

- [ ] Confirm real current-game asset coverage: monuments, nested prefabs, foliage,
  skinned meshes, terrain materials, shaders and changing manifests.
- [ ] Confirm exports in current Rust dedicated server and maintain real-map fixtures.
- [ ] RustEdit `.prefab` compatibility, monument breaking/unpacking and monument
  terrain/splat/topology/biome stamps and placement masks.
- [ ] Prefab thumbnails, category browsing, favorite palettes, continuous prefab
  painting, random multi-prefab palettes and placement collision checks.
- [ ] Clone follow/snap modes, ridge erosion, additional terrain processing and
  custom brush libraries; improve adaptive terrain detail for large worlds.
- [ ] Dedicated splat mixer, layer image import/export, automatic biome/splat/
  topology generation rules and spawn-condition visualizations.
- [ ] Road/river/rail surface geometry previews and exact game generation behavior;
  path-specific placement constraints and monument integration.
- [ ] Native Rust procedural world generation from size/seed/customization settings.
- [ ] IO connection authoring, puzzle configuration and compatible per-entity data.
- [ ] Loot profiles, vending profiles, NPC/vehicle spawners and spawn settings.
- [ ] Cargo ship ocean paths, Bradley APC patrols and server extension integration.
- [ ] Resolve extension references correctly when linked entities are cloned,
  replaced or deleted. Preserving opaque bytes alone does not establish this.
- [ ] Map resize/rotate/merge, monuments and railroad/subway generation workflows.
- [ ] Server launch/playtest workflow, screenshot/minimap tools and packaging polish.
- [ ] macOS app packaging and signed/notarized releases.

## Reference inventory

The inventory is based on the editor's own documentation and public SDK, checked
2026-10-22. RustEdit also has undocumented and version-specific behavior, so this
list must grow when comparison testing finds gaps.

- https://github.com/k1lly0u/RustEdit_Docs
- https://github.com/k1lly0u/RustEdit_Docs/blob/master/TerrainTools.md
- https://wiki.facepunch.com/rust/Map_Editors
- https://wiki.facepunch.com/rust/Map_Data
- https://wiki.facepunch.com/rust/Terrain
- https://github.com/k1lly0u/Oxide.Ext.RustEdit
