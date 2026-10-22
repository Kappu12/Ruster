# Ruster 0.9.0 feature coverage

Ruster is a **prefab composition editor** built on Blender 5.2 LTS. This checklist
covers the active product and its verification limits, not complete RustEdit or
Rust-engine parity.

## Available workflows

| Area | Support |
| --- | --- |
| Startup | Empty Prefab workspace; New / Open popup; recent projects and recovery; original Ruster branding; isolated Blender preferences. |
| Preferences | Assets and MCP in the same native preferences navigation as Interface, Themes and other Blender settings; theme/UI scale retained across New Prefab. |
| Local Rust assets | Validated Steam install discovery and manual fallback; game scene manifest and local RustEdit string pool; on-demand dependency/GUID resolution without launching either program. No shipped game assets. |
| Browser | Shift+A categories, descriptive tokens in any order, favorites, local-availability filter, full-path/ID tooltips, paginated counts, Hidden & IO Helpers and all-assets search. |
| Placement | Native selection, translation, rotation, scale, groups, duplicate/delete, same-type selection and replacement; shared model instances. |
| Loading | Wireframe placement boxes until original linked models attach; progress, cancellation and failure reports; bounded incremental cache recovery; installed-version mismatch/restart guidance. |
| Protected originals | Linked read-only meshes/materials, original-model restoration, export guards against editable/unpacked previews; placement TRS remains editable. |
| Materials | Source base colors/textures and UV transforms, supported metallic/smoothness masks, emission, alpha blending/cutouts; Solid color/texture feedback and native shader-node previews. Shadow-only surfaces excluded. |
| Hidden IO assets | All eight real hose/wire slot variants verified, including cyan pending hose. The source is a Cube renderer scaled by placements, not generated replacement geometry. Geometry-free sounds, terrain stamps, volumes and runtime IO lines remain explicit helpers. |
| LOD and meshes | First nonempty authored LOD; compact binary mesh buffers and streamed metadata; one requested model at a time; bounded preview textures. |
| Projects | `.ruster` atomic saves and packed linked model previews; reopening without the original conversion cache; two-minute idle recovery. |
| Native `.prefab` | RustEdit version-1 format and installed 1.2.19 checksum; unknown-field retention; byte-exact unchanged imports; metadata-preserving group export. |
| Existing IO | Verified imported access, door, timer, frequency, turret, branch, counter, camera, elevator and phone scalar settings; supported endpoint movement with identity/order guards. New wiring is unsupported. |
| `.map` interchange | Reads versions 9/10 and imports only prefab placements. Export writes current prefab IDs/TRS in a minimal version-10 file without terrain or paths. Import appends; opening starts a composition. |
| Assemblies | Reusable `.rusterprefab` references/transforms; group import/export. |
| Model formats | Available GLB/glTF, FBX, OBJ, PLY, STL, USD variants, Alembic and Blender-library exporters; disposable copies preserve protected originals. |
| MCP | 43 typed tools; authenticated local listener and bundled stdio adapter; paginated discovery/selection; batch placement/transforms/inspection; arrays, alignment and plane snapping; native prefab, assembly, model and prefab-only map interchange; existing IO settings; viewport feedback, validation and undo/redo. |
| MCP guidance | `ruster://guide/building`, `build_rust_composition` and `audit_rust_composition`; no arbitrary Python or mesh editing API. |
| Validation | Finite/nonzero transforms, original asset identity, actual grouped shear, selection/batch limits, safe output destinations and bounded model-export copies. Long thin native IO placements retain exact unchanged records. |
| Packaging | Windows/Linux x64 runtime bundles, pinned archive checksum verification and prefab-product/MCP integration checks; macOS source launch with a compatible Blender, standalone package pending. |

## Verification and limits

The supplied **1,730-placement Maze** was imported through the actual native
prefab workflow and exported byte-for-byte unchanged, including IO metadata.
Its 787 cyan hose handles and 216 wire handles preserve their original models,
colors and placement data. Additional local checks confirmed 536 original black
cubes, 124 glass models, and explicit helpers for 32 invisible colliders and four
building-prevention volumes. All eight IO variants passed linked-library material
checks; Solid and native shader renders verified their converted colors/emission.
These checks used bounded, targeted local asset reads, not a full Rust scan.

Windows asset workers have a 768 MiB private-memory ceiling, their supervisor tree
1 GiB, and the editor tree 8 GiB including shader/driver headroom. Requested-model
batches allow at most 100 unique IDs. Geometry export and MCP batch/import limits
also bound work; see [README.md](README.md). GPU/shared allocations are separate.
Unsupported models remain reported placeholders and retain placement records.

Active UI/MCP workflows do not register terrain editing, world/path tools or seed
generation. Their source and legacy tests remain inactive; prefab-only `.map`
exports do not preserve a complete world's layers or create a playable world.
Legacy `.ruster` map projects recover their prefab composition.

Further work includes broader current-game asset coverage, exact engine shaders,
particles/animation and collision behavior, live-server validation, new wiring and
complete extension reference remapping, thumbnails/palette presets, and signed
macOS distributions. Preserving unknown bytes does not prove cloned or deleted
linked entities remain valid. Blender render bounds are not game collision bounds.

For exact interchange behavior, read [the native-prefab contract](docs/rustedit-prefabs.md).
The in-app MCP resource's maintained text is
[BUILDING_GUIDE](ruster/mcp_server.py). Current tests and launch commands are in
[README.md](README.md).
