# Rust building rules

## Building rules for people and MCP clients

Build compositions from **whole original Rust prefabs** discovered in the local
catalog. Keep their geometry, materials and prefab identity intact. Read this
document before building; MCP exposes this dedicated resource file at
`ruster://guide/design`. The repository-wide `DESIGN.md` defines interface style.

| Operation | Rule |
| --- | --- |
| Move and rotate | Allowed on whole placements and groups. Ruster uses world XYZ metres, Z up, and XYZ Euler degrees; interchange converts to Rust's coordinate system. Free angles are allowed, including tilt; 45/90 degree snapping is optional. |
| Duplicate, group, array, align and snap | Allowed using whole original instances. Groups are editor organization; exports flatten their world transforms into prefab placements. |
| Editor names | Spaces are allowed in placement/group labels. Exported Rust placement identity comes from the numeric prefab ID; renaming a Blender object does not change the asset path or create a game prefab. |
| Scale | Rust's map data stores scale. Static decorations can use placement scaling, including nonuniform factors where representable without shear. **Networked entities such as doors, IO and deployables ignore scaling in Rust**; keep those at unit scale for game designs. Ruster does not yet classify every ID as networked, so preview scaling is not proof of support. Mirrored/negative scale and extreme proportions require in-game verification. |
| Make a triangle | **Do not create a new triangle mesh**, extrude/edit vertices, or cut another model into a triangle. An existing triangular Rust prefab, or a triangular arrangement made from original parts, is allowed. The same rule applies to cubes and every other custom primitive. |
| Modify models/materials | Do not sculpt, boolean, bevel, remesh, deform, replace textures/materials, make linked models local, or add library overrides. Native model export makes disposable copies; it does not make custom geometry usable in Rust. |
| Arbitrary Blender Python or operators | Not exposed through this MCP. Use typed Blender observation, viewport/cursor and whole-prefab layout tools so model protection and export validation remain effective. |
| Terrain, paths and wiring | Add Rust Ground creates native terrain data below a composition; its brushes edit height, splat, biome, alpha and topology layers. The terrain preview is generated from those layers, not exported as a mesh prefab. Ground is saved in `.map` and `.ruster`, not `.prefab`. Path authoring and new wiring remain outside this workflow; existing verified imported IO scalar settings can be changed. |

Rust's standard custom-map prefab records contain an ID, position, rotation and
scale, rather than arbitrary Blender mesh vertices or material graphs. Therefore
a shape that looks correct in Blender is exportable to Rust only when built from
real prefab references. Do not invent prefab IDs or substitute a placeholder box
for missing game geometry. Request the original model and inspect actual bounds.

Plan dimensions and repeated modules before placing parts. Prefer uniform group
scale; a nonuniformly scaled group with rotated children can introduce shear,
which Rust placement transforms cannot represent. Relative transforms apply
world-axis scale, then rotation around a shared pivot, then translation. These
operations reject shear instead of silently changing the intended shape.

Use multiple viewport angles and a clean viewport image to inspect the result.
Verify every placement's orientation and intended facing direction using its
loaded model. Do not assume the model's forward axis or the sign of a rotation.
Confirm it faces the correct way and is not reversed, inverted or upside down
before duplicating it or finishing the composition.
Spacing and distance tools use world axis-aligned render bounds; empty space
between those boxes is not a gameplay clearance or collision guarantee. Keep
networked parts at unit scale and verify doors, routes and interactions in Rust.
Some construction inserts need stability disabled to spawn; decorative deployed
objects can decay. Server settings and testing are the map author's responsibility.
Do not change a server's settings automatically. A prefab-only `.map` export has
no terrain or paths and is not a complete playable world.

### Verified references and scope

Checked on 2026-10-25 against Facepunch's documentation and this repository's
export/protection code:

- [Facepunch Map Data](https://wiki.facepunch.com/rust/Map_Data) documents prefab
  IDs and world position, rotation and scale. The restriction on custom Blender
  meshes follows from these record fields and Ruster's reference-only exporter.
- [Facepunch Custom Maps](https://wiki.facepunch.com/rust/Custom_Maps) documents
  networked entity scaling, construction stability and deployable decay limits.
  Its world-design documentation is marked work in progress; verify behavior on
  the target game/server version rather than treating the preview as certification.
- [MCP for Blender](https://github.com/ahujasid/mcp-for-blender) provides general
  Blender code execution and external asset workflows. Ruster expands typed native
  Blender controls while keeping Rust prefab compositions within the rules above.
- [Native prefab compatibility](rustedit-prefabs.md) describes the verified
  interchange contract; [FEATURES.md](../FEATURES.md) records active product scope.

The shared placement validator runs for `.map`, `.prefab` and `.rusterprefab`
exports, including unchanged source-record preservation. Invalid metadata,
unsupported parents/constraints/animation, zero scale and shear stop export.
Composition diagnostics also flag overlapping copies, mirrored transforms and
scaled placements known to have imported IO metadata. These are advisory;
unclassified IDs are not certified as static or safe to scale. No models or
materials are rewritten by these checks.
