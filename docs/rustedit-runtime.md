# Installed RustEdit runtime findings

Inspected the user's installed RustEdit 1.2.19 on 2026-10-22. Local decompiler
outputs stay in the ignored build directory; no RustEdit code, assemblies, string
pools or game assets are distributed with Rustmatics.

## Prefab discovery

RustEdit's loader uses Unity's native AssetBundle APIs and the game's
`Bundles/AssetSceneManifest.json`. That JSON maps prefab paths to asset scenes;
the loader resolves prefab objects from those scenes. Its browser also reads
prefab properties from `GameManifest`. These are existing catalogs, so a Python
walk of every GameObject in every bundle is unnecessary.

The installed RustEdit folder additionally contains `stringpool.txt`, with
numeric ID/path pairs. Rustmatics now combines that local file with the current game
scene manifest. On this installation a cold refresh read 17,140 prefab IDs and
located 16,762 in asset scenes in approximately 0.24 seconds. This measures catalog
creation only, not model conversion or loading. Missing/new IDs need an updated
local string pool; unmatched entries are not represented as available models.

Models resolve on request. The worker opens the named scene node, resolves only
required serialized dependencies, and skips unused AssetBundle container tables.
Current Rust's large uncompressed UnityFS blocks are read with seeks and bounded
reads; they are never copied whole into RAM. Compressed blocks retain their
16 MiB limit, individual reads their 32 MiB limit, and isolated model workers their
768 MiB allocation cap. Directory lookup reads headers, not model data.

Verified one real strobe-light model (UID 699083235): 25 hierarchy nodes, two
meshes, 410 vertices, with a successful conversion report. Browser refresh does
not trigger scene-wide conversion. Explicit selections are limited to 100 unique
model IDs per request, converted sequentially.

## Procedural generation

RustEdit's `Chaos.Utilities.ProceduralManager.Initialize` builds an ordered set
of `Rust.Procedural.ProceduralComponent` instances using the game world-setup
prefab. `GenerateSelectedRoutine` reads the seed and runs selected components,
with pre/post processing, map-layer updates and path rebuilding inside Unity.
This inspected workflow does not launch RustDedicated.

Rustmatics's existing RustDedicated backend is a separate optional implementation.
It is not how RustEdit performs generation. The installed Unity procedural runtime
cannot be called directly as Blender Python; a supported Unity host/interface or
an independent implementation of the required stages is still needed. No such
interface has been established by this inspection. Rustmatics's existing island
terrain generator is not equivalent to RustEdit's complete seed/world pipeline.
