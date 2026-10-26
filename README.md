# Ruster

Ruster is a desktop prefab editor for Rust, built on Blender 5.2 LTS. It lets you assemble structures and scenes from the game's original prefabs, using models and textures read from your own Rust installation.

The editor works with whole prefab placements: choose assets, arrange them in the viewport, and export their IDs and transforms for Rust. Blender supplies the viewport, navigation, object tools, and undo history.

## Start with a packaged build

Open [Releases](https://github.com/Kappu12/Ruster/releases) and download the Windows or Linux ZIP from the version you want. Extract the ZIP into its own application folder.

- **Windows x64:** open `Ruster.exe`.
- **Linux x64:** run `./Ruster.sh` from the extracted application folder. If needed, run `chmod +x Ruster.sh` first.

Keep the application folder together. The package includes its Blender runtime and Python dependencies; a separate Blender installation is unnecessary. Packaging currently targets Windows and Linux on x64.

### Make your first composition

1. Open **Preferences > Assets**. Let Ruster find your Steam installation, or select the Rust game folder containing `Bundles`, then click **Apply Installation**.
2. Create a new prefab composition from the welcome screen.
3. Press **Shift+A** to browse Rust prefabs. The browser supports search, categories, favorites, and recently used assets. Enable **Hidden Assets** when looking for helpers such as volumes or spawners.
4. Add a prefab and arrange it in the viewport. Models and materials load on demand, with progress shown in **Model Loading**.
5. Save a `.ruster` project, then export a `.prefab` when the composition is ready for RustEdit.

If you have RustEdit installed, its folder can also be selected in **Preferences > Assets** as a source for prefab names through its local `stringpool.txt`.

## Build in the viewport

Use Blender's object controls to move, rotate, and scale placements. **G**, **R**, and **S** start transforms; axis constraints and numeric input work as usual. **Shift+D** duplicates a placement, and **F3** opens command search. The Outliner provides another way to select and organize the composition.

For repeated structures, use the layout tools:

- Linear and radial arrays.
- Alignment by model bounds and distribution by spacing.
- Grid snapping and placement on a plane.
- Radial symmetry sets that update together while symmetry is enabled.
- Vertex, edge, and face snapping, plus stepped rotation.

Group placements to move an assembly as a unit. **Composition Checks** helps locate overlapping copies, mirrored transforms, and other export issues.

Original prefab geometry stays read-only in the composition. Shape changes come from choosing and arranging whole assets. **Export Blender File** creates a separate scene with editable models and packed textures for rendering or further work in Blender.

## Choose an output

| Format | Purpose |
| --- | --- |
| `.ruster` | Save a Ruster project and resume editing it later. |
| `.prefab` | Import or export a RustEdit prefab composition. |
| `.map` | Import or export prefab placements. This workflow does not edit or export map terrain and paths. |
| `.blend` | Export a standalone Blender scene for rendering and model work. |
| Other model formats | Export selected models through the exporters available in the bundled Blender build, including glTF, FBX, and OBJ. |

Rust exports describe original prefab IDs and placement transforms. Model exports produce geometry for use in other applications. For imported RustEdit prefabs with IO data, the editor also exposes supported IO settings on the selected placement.

**Export Prefab** exports highlighted prefabs/groups. With nothing highlighted,
it exports the whole composition as a RustEdit `.prefab`.

Save your working project before testing an export in RustEdit or Rust. Viewport previews show assets and placement; gameplay behavior is determined by the game.

## Local live preview

The **Live Preview** editor below **Placements** on the right provides a private
local server, configurable port, owner Steam ID, console, and an explicit client-module action.
It downloads the server on first use. Client injection requires verified inactive
EAC and is experimental; see [setup, checks and current limits](docs/live-preview.md).

## Connect an MCP client

Ruster includes an optional local MCP connection for inspecting the editor and authoring prefab compositions with an AI client.

1. Open **Preferences > MCP** and enable MCP.
2. Click **Copy MCP Client Configuration**.
3. Add the copied configuration to your client's MCP settings, then connect while Ruster remains open.

The copied configuration uses the application's Python and `mcp_server.py` entry point. The editor bridge listens on `127.0.0.1`, uses a per-user authentication token, and defaults to port `9877`.

Start an automation session by reading `ruster://guide/building` and calling `get_editor_status`. Tools can search the local catalog, request models, place and transform prefabs, organize groups, inspect the viewport, and export compositions. They operate on whole placements while preserving the original assets.

Project tools expose the current path and unsaved state, recent projects, and
`open_project`/`new_project`. Save current work first; discarding changes requires
`discard_unsaved=True`. Stop an active preview before switching projects.
`start_live_preview`, `stop_live_preview` and `get_live_preview_status` control the
owned server and report progress, logs, connection details and client errors.
Console and owner-ID tools queue commands on that server. Launch and Inject use
the Live Preview panel's explicit client actions and EAC verification.
After updating Ruster, refresh the MCP client's tool list/reconnect the adapter.

## Run from source

Use Python 3.13 and the Blender version pinned in [engine.lock.json](engine.lock.json), currently Blender 5.2.3. Set `RUSTER_BLENDER` to that Blender executable, or make `blender` available on your `PATH`.

Install the asset and MCP dependencies into the application's `python_modules` directory using Blender's bundled Python:

```sh
python tools/setup_assets.py
python launch.py
```

You can also select the executable for a single launch:

```sh
python launch.py --blender "/path/to/blender"
```

Pass an existing project or import file as the positional argument:

```sh
python launch.py "/path/to/composition.ruster"
```

The launcher uses a separate Blender process and a Ruster-specific configuration directory. Startup output is written to `logs/startup.log` in the user data folder.

### Check changes

In a Python 3.13 development environment:

```sh
python -m pip install pytest lz4 numpy -r requirements-assets.txt -r requirements-mcp.txt
python -m pytest -q
python -m compileall -q ruster tools bootstrap.py launch.py
```

Run the native editor fixtures against the pinned Blender executable:

```sh
python tools/native_checks.py --engine "/path/to/blender" --suite background
python tools/native_checks.py --engine "/path/to/blender" --suite graphical
```

On Linux, `--xvfb` gives the graphical suite a disposable virtual display when Xvfb is installed.

### Create an application package

On the target operating system, using Python 3.13:

```sh
python tools/package.py --archive
```

The packager downloads the pinned Blender archive, verifies its SHA256, installs application dependencies, runs the package checks, and writes the application and ZIP into `dist/`. Use `--output-name` to choose a different distribution folder name.

### Publish a version

Ordinary branch pushes and pull requests run the unit, native Blender, and graphical tests without uploading application artifacts. To publish a version, update the application version in `ruster/__init__.py`, commit the changes, then push a new version tag such as `v1.2.3`:

```sh
git tag v1.2.3
git push origin v1.2.3
```

The tag workflow runs the same tests, creates a draft GitHub Release, and builds and tests the Windows and Linux packages. Each ZIP uploads directly to the draft release, without intermediate Actions artifacts. The workflow publishes only after both downloads are complete, then removes the old Ruster Actions artifacts. A failed test or build leaves existing downloads intact. Tags such as `v1.2.3-rc.1` create prereleases.

## Local files

Ruster reads the installed game files without changing them. Its settings, asset cache, recovery files, and logs live separately:

| Platform | Default user data folder |
| --- | --- |
| Windows | `%LOCALAPPDATA%\Ruster` |
| Linux | `$XDG_DATA_HOME/ruster`, or `~/.local/share/ruster` when unset |

Set `RUSTER_USER_DIR` to choose another user data folder. Projects and exports are saved to the locations you select.

## Further reading

- [Project container format](docs/ruster-format.md)
- [RustEdit prefab format and interoperability](docs/rustedit-prefabs.md)
- [Architecture](docs/architecture.md)
- [Third-party notices](THIRD_PARTY_NOTICES.md)

Ruster's application code is licensed under GPL-3.0-or-later. See [LICENSE](LICENSE). Rust game assets remain the property of their respective owners and are supplied by your local installation. Ruster is an independent community project.
