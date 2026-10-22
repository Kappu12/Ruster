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
  "app_version": "0.1.0",
  "title": "My World",
  "mode": "MAP",
  "files": {
    "scene.blend": "<sha256>",
    "source.map": "<sha256>"
  }
}
```

The Blender scene stores editable placement roots, with source protobuf records
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

## Rust `.map` adapter

Version 9 uses a 4-byte little-endian version followed by the legacy LZ4Stream.
Version 10 also carries 8 header bytes before that stream. They are preserved.
The payload is a protobuf world with size, named map layers, prefab records and
paths. Unknown protobuf fields retain their original wire bytes.

The writer emits valid uncompressed chunks in the legacy LZ4Stream framing.
This is deliberately different from modern LZ4 frames and may produce larger
`.map` exports. No compression library is needed in Blender for map reading.

Only prefab placement records are changed. Original world/layer/path bytes stay
unchanged; untouched prefab transforms keep their original records. Exporting
does not bake arbitrary Blender meshes or the viewport terrain back into Rust.
