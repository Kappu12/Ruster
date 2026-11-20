# Native Rust ground

**Add Rust Ground** adds a flat, centred terrain patch below an existing prefab
composition. Width is 16–2,000 m, in a containing 1,000–2,000 m world. Height is in
editor Z metres. Prefab meshes and transforms are preserved. The generated mesh
is only a view of authoritative Rust terrain data.

The Rust Ground panel exposes biome, splat, height, water, alpha and topology
brushes. Click **Brush Ground in Viewport** to select the brush tool, or apply a
stamp at the 3D cursor. Each stroke has one undo step. Layer snapshots are kept
in immutable Text datablocks, including full-resolution data omitted by the
viewport preview. Saved ground projects retain their original `source.map` and
edited snapshots; reopening restores native ground instead of stripping it.

`add_ground`, `paint_ground` and `get_ground_status` expose the same workflow
through MCP. Brush centres are world XY coordinates; height is Z. The maximum
ground width is deliberately bounded independently of general Rust map limits.

## Game data

Exports contain actual native terrain/height/water maps, eight splat channels,
five biome channels, alpha and topology. Alpha shows the ground patch
while hiding terrain outside its edges. Water starts below the ground. The
initial solid patch has Field, Forest, Clutter, Tier0 and Mainland topology;
these can be painted or erased.

Current Rust map files store five planar biome channels, including Jungle;
their weights sum to 255. Rust's RGBA biome **textures** reconstruct Jungle
from the other four channels, which is different from the native map byte
layout. Rustmatics reads legacy four-channel data and expands it to five channels
when exporting ground or baking a preview map, preserving other layers.
The layout and explicit fifth channel were checked against the installed
server's `TerrainBiomeMap.Setup`, `TerrainMap<T>.FromByteArray` and
`TerrainBiome.COUNT`, then verified by sampling biome weights in the server.

Export `.map` for ground, painted layers and prefab placements. Export `.prefab`
or `.rusterprefab` for placements alone. The `.ruster` project stores both.
Ordinary `.map` import continues to import prefab placements only.

## Test server

Ground-aware Live Preview bakes the current terrain layers into its native map,
keeps world origin fixed so the prefabs align with the terrain, and adds its
ordinary asset-pack preload markers. Prefab-only scenes retain their existing
centred void preview. Terrain edits after startup are reported as requiring a
server restart; they are not silently represented as live terrain changes.
The owned loopback server uses its existing `-insecure` startup and checks.

Ground colors in the editor are a biome/splat preview. Rust's own terrain shader,
grass/clutter, object collisions and resource spawning run in the game, not in
Blender. Native layers, paint normalization, persistence, preview map baking and
composition preservation have unit and real-Blender regression checks. Actual
server startup and client visuals should be checked separately for each release.
