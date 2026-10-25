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
| Browser | Compact native Shift+A category menu with Search All Prefabs and immediate typing across the complete catalog; one shared, incrementally warmed metadata index prevents repeated category scans. Descriptive tokens in any order and prioritized IO/glow aliases; sidebar categories, favorites, 48 recent placements, local availability, filter reset, inspect-before-place details with Copy ID/Path, and paginated counts. |
| Placement | Native selection, translation, rotation, scale, groups, duplicate/delete, same-type selection and replacement; shared model instances; perspective/orthographic toggle in the viewport header. |
| Snapping | Left-toolbar object snap and settings; vertices, edges or faces of loaded instances; 15°/30°/45°/60°/90°/180° native rotation increments and world-angle alignment. |
| Symmetry | 2–16 sides around configurable X/Y/Z axes and centers; rotating or fixed-orientation copies; creation from existing selections; explicit updates to existing sets; select/release sets; any-member transforms/deletion while enabled. Complete group transforms carry the set center/axis. Undo and project persistence. |
| Layout UI | Linear/radial arrays, active-object bounds alignment, origin/bounds-gap distribution, axis-selective grid snapping and plane placement. Whole placements/groups only, shared with the bounded MCP implementation and one undo step. |
| Loading | Wireframe placement boxes until original linked models attach; shared header/sidebar/preferences status with scene counts, selection of unloaded/issues, retry, cancellation and readable/copyable failure reports; bounded incremental cache recovery; installed-version mismatch/restart guidance. |
| Protected originals | Linked read-only meshes/materials, original-model restoration, export guards against editable/unpacked previews; placement TRS remains editable. |
| Materials | Source base colors/textures and UV transforms, supported metallic/smoothness masks, emission, alpha blending/cutouts; Solid color/texture feedback and native shader-node previews. Shadow-only surfaces excluded. |
| Hidden IO assets | All eight real hose/wire slot variants verified, including cyan pending hose. The source is a Cube renderer scaled by placements, not generated replacement geometry. Geometry-free sounds, terrain stamps, volumes and runtime IO lines remain explicit helpers. |
| LOD and meshes | First nonempty authored LOD; compact binary mesh buffers and streamed metadata; one requested model at a time; bounded preview textures. |
| Projects | `.ruster` atomic saves and packed linked model previews; reopening without the original conversion cache; two-minute idle recovery; visible save state; project-aware New/Open, Quit/Ctrl+Q and Windows titlebar close, with Save/Don't Save/Cancel for unsaved changes. |
| Native `.prefab` | RustEdit version-1 format and installed 1.2.19 checksum; unknown-field retention; byte-exact unchanged imports; metadata-preserving group export. |
| Existing IO | Verified imported access, door, timer, frequency, turret, branch, counter, camera, elevator and phone scalar settings; supported endpoint movement with identity/order guards. New wiring is unsupported. |
| `.map` interchange | Reads versions 9/10 and imports only prefab placements. Export writes current prefab IDs/TRS in a minimal version-10 file without terrain or paths. Import appends; opening starts a composition. |
| Assemblies | Reusable `.rusterprefab` references/transforms; group import/export with preserved cursor pivot and rollback on import failure. |
| Model formats | Available GLB/glTF, FBX, OBJ, PLY, STL, USD variants and Alembic; direct Export Blender File (.blend) creates a regular standalone scene with editable meshes/materials and packed textures. Disposable copies preserve protected originals. |
| MCP | 52 typed tools; authenticated local listener and bundled stdio adapter; paginated discovery/selection; batch placement/transforms/inspection; linear and radial arrays, pivot transforms, ordered origin/bounds spacing, grid/plane snapping and measurements; native prefab, assembly, model and prefab-only map interchange; existing IO settings; Blender context, cursor and native viewport state/shading controls; clean viewport images, explicit assembly anchors, validation and undo/redo. |
| MCP guidance | `ruster://guide/building`, `ruster://guide/design` (dedicated docs/design.md resource file), `build_rust_composition` and `audit_rust_composition`; sourced Rust building rules, no arbitrary Python or mesh editing API. |
| Validation | Shared `.map`/`.prefab`/assembly guards for finite/nonzero transforms, original identity, parents, constraints and grouped shear. Composition checks and selection of overlapping copies, mirrors and scaled imported IO. Selection/batch limits, safe destinations and bounded model-export copies. Long thin native IO placements retain exact unchanged records. |
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
