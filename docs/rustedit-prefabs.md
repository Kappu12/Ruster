# RustEdit custom prefab interchange

The target is the installed RustEdit 1.2.19 serializer, inspected locally in
October 2026. The old public RustEdit source is not the compatibility reference.
The implementation is independent; no RustEdit assemblies or game assets ship
with Ruster.

Files start with little-endian uint32 version 1, followed by the legacy LZ4Stream
envelope around protobuf data. The top-level fields are options (1), terrain
textures (2), prefab placements (3), paths (4), IO (5), anchored paths (6), NPC
spawners (7), APC paths (8), vehicles (9), building grades (10), and checksum (11).
Placement records use the same ID and Unity transforms as Rust world files.

The checksum is lowercase MD5 over each ordered placement's little-endian uint32
ID, then its position, Euler rotation and scale. Each float32 contributes its
high three bytes, dropping the least significant byte. Existing checksums are
preserved for unchanged inputs, including older prefabs with different hashes.

An unchanged import/export preserves the entire original file byte-for-byte.
Unknown fields remain intact. IO entity positions and both connection ends follow
placement movements when IDs and ordering remain intact and positions identify
unique placements. Ambiguous references, IO-linked replacement/deletion, and
changes with other populated extension families are rejected to avoid corrupting
links. New placement-only compositions can be edited and exported normally.
This is not yet complete RustEdit feature parity.

Validation uses synthetic fixtures plus the locally supplied Maze prefab. To
check an export against RustEdit's actual protobuf deserializer and checksum
without starting RustEdit or loading game bundles:

```powershell
.\tools\check_rustedit_interop.ps1 `
  -RustEditPath 'C:\Program Files (x86)\RustEdit' `
  -Prefab '.\build\example.prefab' -RequireChecksum
```

The optional check reads installed assemblies and the prefab without changing
either. Local reverse-engineering outputs and user fixtures are not distributed.
Reader budgets are 32 MiB compressed, 64 MiB decompressed, and 100,000 placements.
