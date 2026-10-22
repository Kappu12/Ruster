# `.ruster` project format — schema 1

A `.ruster` file is a ZIP archive with these exact permitted members:

| Member | Requirement | Purpose |
|---|---|---|
| `manifest.json` | Required | Format version, mode, title, application version, SHA256s |
| `scene.blend` | Required | Blender scene with project metadata and packed preview resources |
| `source.map` | Required in MAP mode | Original Rust map, retained independently of viewport approximations |

```json
{
  "format": "ruster",
  "schema": 1,
  "app_version": "0.3.0",
  "title": "My World",
  "mode": "MAP",
  "files": {
    "scene.blend": "<sha256>",
    "source.map": "<sha256>"
  }
}
```

The Blender scene stores editable placement roots and path curves, with source protobuf records
in base64 custom properties. This retains fields the editor does not understand.
Rust IDs are stored as decimal strings because Blender integer custom properties
cannot represent every uint32 prefab ID as a positive signed 32-bit integer.

The archive is built beside the target and atomically replaces the saved project.
Opening validates the manifest, supported schema, exact file list, duplicate
members, size limits and SHA256s before writing files to a private session cache.
No arbitrary ZIP paths are extracted. Embedded scene Python is not auto-executed.
SHA256s detect accidental corruption, not authenticity of untrusted projects.

The original map remains embedded rather than referenced by an absolute game path.
The local Rust install and asset catalog live in per-user settings/cache, not in
the `.ruster` file. Cached assets attached to the scene are packed into `.blend`;
the project should therefore be treated as containing game content when shared.
From 0.3, model previews are linked read-only libraries packed inside `scene.blend`.
They retain read-only IDs when reopened, including textures, without external
model-cache paths. This does not change the ZIP schema. Legacy editable previews
are locked and require original asset data for verified replacement before export.

## Rust `.map` adapter

Version 9 uses a 4-byte little-endian version followed by the legacy LZ4Stream.
Version 10 also carries 8 header bytes before that stream. They are preserved.
The payload is a protobuf world with size, named map layers, prefab records and
paths. Unknown protobuf fields retain their original wire bytes.

The writer emits valid uncompressed chunks in the legacy LZ4Stream framing.
This is deliberately different from modern LZ4 frames and may produce larger
`.map` exports. No compression library is needed in Blender for map reading.

Terrain changes live in immutable compressed Text datablocks inside `scene.blend`.
The scene holds an ID pointer to the active snapshot. Blender's undo restores that
pointer together with scene changes. A snapshot contains the complete modified
layers, never reduced viewport samples. Snapshot data are base85-encoded zlib
protobuf records containing layer names and raw sample bytes.

Export applies modified full-resolution layers, placement transforms and path
records to the source world. Unedited layer/world/record fields retain their
original bytes. The viewport terrain mesh and arbitrary custom meshes are never
used as the authoritative game terrain. Group transforms are baked into placement
transforms; shear is rejected because it cannot be represented in Rust prefab data.
