# Rustmatics headless workflows

Use the one-shot command for a saved input and a known output. Use a persistent
MCP session when an agent needs to inspect or edit the scene across calls.
Both run the bundled Blender engine in background mode.

## Validate or export a saved project

From the Windows package directory, run one operation per command. On Linux,
substitute `./Rustmatics.sh` and use absolute Linux paths.

```bat
Rustmatics.cmd "C:\maps\Project.ruster" --validate-map --require-ground
Rustmatics.cmd "C:\maps\Project.ruster" --export-map "C:\maps\Project.map" --require-ground
Rustmatics.cmd "C:\maps\Project.ruster" --export-report "C:\maps\Project Report.docx"
```

From source, substitute `python launch.py` and point `--blender` at the pinned
Blender executable or set `RUSTER_BLENDER`. For Word export from source, install
the bundled-Python dependencies with `python tools/setup_assets.py`.

The one-shot commands use a temporary profile and accept saved `.ruster` and
RustEdit `.prefab` inputs. Saved prefab IDs and transforms can be serialized
without the Rust client or a populated asset cache. An ordinary `.map` import
reads placements only. Use the original `.ruster` project to preserve native ground.

- Use `--require-ground` for validation or export when the server map needs
  native ground. Omit it if a prefab-only map is intended.
- Pass `--overwrite` to replace an existing output. Exports normally refuse
  existing files.
- Parse the line beginning with `RUSTER_BATCH_RESULT ` as JSON. Blender can print
  other log lines. Success exits with code 0. Invalid input, failed validation
  and failed export exit nonzero. Validation returns `valid`, `errors` and
  `notes`. A successful export returns its absolute `path`.
- The Word report contains map validation findings, terrain status and prefab
  counts, with up to 50 prefab IDs listed by placement count. A report can
  describe validation errors and still export successfully. Its `valid` field
  reflects map validation.

## Edit through MCP

1. Run `Rustmatics.cmd --headless "C:\maps\Project.ruster"` on Windows or
   `./Rustmatics.sh --headless /maps/Project.ruster` on Linux. For catalog work,
   add `--rust-install` with the local Rust game directory if Steam discovery is
   insufficient.
2. Wait for `RUSTER_HEADLESS_READY`. Use the MCP client configuration in its
   JSON to connect to that exact session. The default headless port is 9878.
   Concurrent hosts need unique `--user-dir` and `--mcp-port` values.
3. Call `get_editor_status` and check `headless`, `busy` and `unavailable_tools`.
   Refresh the client tool list if the adapter was recently updated.
4. For ongoing work, use `open_project`, `search_prefabs`, `request_prefab_assets`,
   bounded placement and transform tools, and `get_ground_status`. Save a
   `.ruster` checkpoint with `save_project` before changing projects or stopping.
5. Call `validate_map(require_ground=True)` for a native-ground deliverable,
   then `export_map(path, require_ground=True)`. For Word use
   `export_project_report(path)`. MCP output paths must be absolute and files
   are replaced only with `overwrite=True`.

Headless mode has no interactive viewport, viewport captures, or undo/redo.
Use bounds, transforms, validation and saved checkpoints. Use the desktop
editor for visual review, or export loaded models with `export_models` and
arrange cameras or render in background Blender.

## Hand off the map to Rust

For an existing dedicated server, make the exported `.map` available at a URL
the server can read and set `server.levelurl` in that server's startup
configuration. Verify startup and gameplay separately.

For Rustmatics's owned Windows Live Preview server, use `start_live_preview`,
`get_live_preview_status` and `stop_live_preview`. It bakes its own preview map
from the open project. Restart the preview after changing terrain. Joining from
the Rust client and inspecting in-game visuals require a client session.
