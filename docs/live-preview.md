# Local live preview (experimental, Windows x64)

MCP clients can use `start_live_preview`, `get_live_preview_status`,
`stop_live_preview`, `send_live_preview_command` and `grant_live_preview_owner`.
Startup and shutdown are asynchronous; poll status for readiness or completion.
Status includes the current placement count, connection command, setup progress,
server/client errors and bounded log output. Console responses confirm queuing;
read the logs for Rust's result. Launch and Inject stay explicit panel actions.
`open_project` and `new_project` protect unsaved work. In the same Ruster window,
an active preview server and client bridge stay running across project switches.
The previous scene is cleared and the new composition is synchronized and
recentered without relaunching the server or reinjecting the client. Explicit
Stop, closing Ruster and failed safety checks still end the preview session.

The **Live Preview** panel has its own editor below **Placements** on the right,
outside the viewport extension sidebar. The preview uses the actual Rust client
and a separate local dedicated server. It does not emulate Rust or bundle the
game/server in Ruster's executable.

1. Set **Game Port** (28015 by default). The server also reserves the next two
   ports for local RCON and queries. Enter an optional 17-digit **Steam ID**.
2. Click **Start Live Preview**. First use downloads official SteamCMD, installs
   Rust dedicated server app 258550 anonymously, and installs Carbon and Ruster's
   companion plugin. Allow several GB for the server. Later starts reuse this
   separate installation. After a Rust update or server version mismatch, enable
   **Update Server on Start** under **Setup and EAC Checks** before starting.
   Setup shows an approximate overall percentage and the SteamCMD, download,
   verification and plugin-loader phases. A completed Rust download is reused
   if a later setup stage fails, including SteamCMD's first-run self-relaunch.
   The generated map also includes one hidden preload marker for **every** asset
   scene listed in the installed client and server manifests, including auto-load
   and monument packs. The panel displays the pack count. Setup fails with the
   pack name if it cannot select a shared, valid prefab ID; it never silently skips
   a pack. Loading all monument packs increases startup time and memory use.
3. Close any running Rust client. Click **Launch Rust Without EAC**, or run
   `RustClient.exe` directly from your Rust installation. Keep Steam running, but
   do not use Steam's Play button or `Rust.exe` to start this preview session.
   [Facepunch documents this direct executable route as EAC-disabled](https://support.facepunchstudios.com/hc/en-us/articles/15041503601437-Launching-Rust-with-EAC-disabled-RustClient-exe).
4. Once Rust is detected, the launch button becomes **Inject**. Wait for the main
   menu and the local server to be ready, then click it. This is the only action
   that loads the preview DLL into the game. Detection and server startup do not
   inject, patch the game, or launch a client automatically.
   Passed EAC checks alone do not enable Inject; the server must also be Ready.
5. Click **Copy IP**. In Rust's F1 console, enter `connect ` followed by that
   address. After joining, the module claims the original map placements and
   applies editor snapshots to static scene objects. New placements go through
   the client's typed bootstrap asset-loading callback, then Unity's original
   instantiation API. The server companion updates
   its matching objects and colliders. Networked root entities use normal Rust
   replication.
6. Use the small console to send commands to the owned local server. **Grant Owner
   ID** applies the Steam ID field; reconnect if an already connected player
   needs its new administrator level.
7. **Stop Live Preview** stops the owned server and disables the client bridge.
   **After injecting, restart your computer before launching Rust again.** This
   notice remains visible in the panel. Stopping preview leaves the DLL mapped
   in the current client until that process exits; it does not unload the module.

## EAC checks

Injection is fail-closed. It checks the selected installation's executable,
process creation identity, launch command, parent process, complete loaded-module
enumeration, EAC processes, and active EAC services/drivers. An EAC wrapper,
protected/unreadable process, incomplete inspection, multiple clients, or active
EAC blocks injection. A missing command-line flag by itself never enables it.
The checks run again before remote memory writes and thread creation. The DLL
also checks modules, processes, and services before registering its main-thread
callback and during the session. It does not disable, stop, patch, hide from, or
bypass EAC. If the original launcher cannot be verified, restart Rust with the
panel's direct-executable button.

When inspection is incomplete, the panel names the missing launch command line,
original launcher or loaded-module evidence. This means EAC could not be verified;
it is not a positive detection of EAC. Injection stays disabled until every check
passes.

The server verifies its current world URL against the random loopback map URL.
Its connection report contains the session token, server PID, map URL, observed
loopback peer port and timestamp. The DLL verifies these values and requires the
peer UDP port to belong to its own process through
[Windows' UDP endpoint table](https://learn.microsoft.com/en-us/windows/win32/api/iphlpapi/nf-iphlpapi-getextendedudptable).
Missing, foreign or older-than-1.5-second connection reports pause edits. The
server refreshes the report four times a second and removes it on disconnect.
All game object operations run through a callback on the Unity window thread.
IL2CPP methods are found through their exported reflection API and checked
signatures. Missing or ambiguous methods produce a compatibility error; there
are no guessed offsets or fallback game-code patches.

The bridge uses the genuine `Bootstrap.<>c` callback registered during
`Init_Tier0` to find client prefabs, together with Unity's typed `Instantiate`
overload. It does not require the obfuscated GameManager creation methods or
WorldSerialization fields that made the first implementation fail. Initialization
only scans the relevant API types. Duplicate or missing bindings fail explicitly,
and the worker exits after a compatibility failure. The panel shows **Preview
Unavailable** when a loaded module reports an error.

The Unity 6 bridge stores object-retention handles as opaque pointers, matching
the [IL2CPP API handle definition](https://github.com/MlgmXyysd/libil2cpp/blob/master/libil2cpp/Unity_6000.0/6000.0.5f1/il2cpp-api-types.h).
The earlier 32-bit handle declarations caused a native crash on the first
retained-object poll after a successful spawn. The crash dump identified that
lookup and a truncated pointer; standalone tests now use handles above 4 GiB
through creation, storage, polling, rollback, deletion and world cleanup. The
module manifest records 64-bit handles, and the loader refuses older modules.

The dedicated server starts with its native `-insecure` switch. The companion
checks `Network.Net.sv.secure` before advertising readiness and on every update.
Ruster validates a fresh heartbeat with the matching server PID and session
identity before injection. A secure or non-loopback server is refused and
stopped; no EAC setting is bypassed or patched.

Status reads allow the companion to replace its heartbeat file concurrently using
[Windows file-sharing flags](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew).
A brief locked or missing heartbeat is retried while the previous verified report
remains fresh. A failed read never extends that report's 15-second lease, and
injection still requires a fresh read. A prolonged failure stops the owned server.
Inside an already injected client, a missing, locked or expired heartbeat pauses
edits and clears the queued snapshot. The worker keeps checking EAC and session
stop markers, and resumes after fresh heartbeat and connection proof checks pass.
A temporary editor snapshot lock also pauses polling. The panel distinguishes
**Preview Paused** and **Preview Stopped** from a merely loaded module. Status
transitions are timestamped in `client.log` (bounded to about 1 MiB), so later
cleanup cannot erase an earlier interruption reason.

The editor checks for scene changes about twice per second; capture batches yield
to keep editing responsive. The server and client poll at 4 Hz. The intended edit
delay is roughly 0.5–1 second, depending on scene size and server load. This is
placement synchronization, independent of Rust's rendering frame rate; the delay
has not been measured in a running Rust client.

Large client updates use a queue instead of applying the whole revision in one
callback. A callback checks at most 512 records and performs at most four scene
mutations within a four-millisecond target. Unchanged placements bypass prefab
loading and Unity calls. Staging, activation, collider retirement and rollback
all yield between slices. Only the latest pending snapshot is retained while a
revision finishes, so intermediate drag/agent edits cannot form an unbounded
backlog. One expensive native prefab initialization or physics synchronization
can exceed the target; Unity does not expose a way to interrupt that call.

Only one client callback message may wait for the game thread. Active work is
scheduled roughly every 16 ms; heartbeat, EAC and snapshot checks retain their
250 ms cadence, and every callback still verifies the owned connection before
mutating the scene. Idle callbacks no longer copy an already applied snapshot;
retained-root polling runs in bounded slices once a second. Status and history
file writes run on the worker thread, including waiting/ready transitions while
idle. These changes reduce bridge work; they do not impose Rust render settings
or prove a particular gameplay frame rate.

The server companion uses the same four-millisecond / four-mutation target,
with short scheduled slices instead of one long main-thread update. A linear
placement diff skips unchanged prefab validation and recursive component scans;
map-only prefab classifications are cached by their verified ID and path.
Only the newest waiting revision is kept. Heartbeats and the console continue
between slices, and the revision is acknowledged after collider retirement and
physics synchronization. Creation/transform failures restore prior transforms
and remove staged roots through the bounded rollback queue.

## Current limits and validation

This is an experimental implementation, not a claim of verified current-game
compatibility. Build checks, offline EAC rejection tests, binary protocol tests,
and Blender lifecycle tests do not prove that a particular Rust release can run
the injected module. No client injection or gameplay testing was performed during
development, at the user's request. Runtime errors appear in the panel and logs.
The local dedicated server has been booted successfully with an empty void map,
the companion loaded, and runtime EAC-disabled readiness verified. Client-side
prefab rendering and injected gameplay remain untested by development tooling.
The all-pack preview map has also been booted in a separate dedicated server
with all 29 installed pack markers. A concrete cube absent from the initial
composition was then created successfully through a live update. The test server
was stopped afterwards; no running game client was launched or injected by these
checks. Pack/template availability on the actual client still needs visual
verification.
The revised loader, all required Unity signatures and the bootstrap singleton
match the installed client's offline metadata. Standalone synthetic IL2CPP
fixtures cover adding previously absent assets, failed loads and transforms,
rollback, ambiguous/missing APIs and owned UDP endpoints. These checks do not
prove that a specific prefab can render or initialize inside the running game.

The composition is centered in a 1,000 metre void map. Terrain is entirely holes,
the ocean is moved out of view through Rust's replicated environment setting,
and no platform is added. Pack preload markers are tiny and placed at least
10,000 metres from the origin and 10,000 metres underground, in their own
`RusterPreviewWarmup` map category. The server removes its hidden instances before
players join while retaining the loaded asset-scene templates. These markers
never enter the authoring scene, exported composition, or live snapshots.
Some monument scripts detach children while initializing. The server also
removes those detached roots and cancels their scheduled callbacks inside the
reserved underground preload area, preserving authored roots and players.
During its initial scene claim, the native client deactivates unused preload
roots in bounded slices; hidden lights and scripts otherwise remain active even
when their parent marker is tiny and far away.

Before accepting players, the companion replaces the native procedural and
fallback spawn caches with a live, session-owned spawn point. This avoids
first-player spawn resolution dereferencing cached objects removed during pack
cleanup. The exact field names, array types and writable status are checked
against the installed server; publicized Carbon fields are supported. An
unsupported server build reports a startup error. Session-only developer logging
records the underlying exception if a client is disconnected during readiness,
and the companion writes disconnect reasons to `client.disconnect`. A successful
server boot verifies cache installation, but a real first connection is still
needed to confirm a reported first-join kick is resolved.
The initial composition's placement
center is translated to the origin in the preview snapshots; the project itself
stays unchanged. That translation stays fixed during edits and resets when a
different project is opened or started. Starting empty uses the first composition's
center instead. Load the composition before starting so
the map can preload its original asset scenes. The companion supplies a spawn
point above available prefab colliders. Use owner permissions and Rust's F1
`noclip` for free movement when the composition has no walkable surface.

Both companions claim the authored baked placements instead of adding
duplicates. Initial client claiming searches active scene instances through
Unity's unsorted `FindObjectsByType` API. It excludes asset templates and inactive
preload hierarchies rather than enumerating every loaded asset with
`Resources.FindObjectsOfTypeAll`. The latter can return over a million objects
after all prefab packs load; retrying that global allocation on the game thread
caused periodic stalls before the old guard rejected the result.

The scene-only result retains the one-million-object bound and is cached across
matching callbacks. Matching processes at most 8,192 objects or four milliseconds
per callback, and retains only expected placement matches. The initial native
Unity enumeration is one call, not part of that matching time budget. A missing
placement retains matched roots and waits one second before searching for the
remaining placements; an error backs off for five seconds. Brief gaps in the
connection proof pause claiming without discarding progress. A different proven
server/session/map/peer port releases old claims, and all matched roots are
checked again before the initial scene is committed. No edit is applied while
connection verification is unavailable. Regular lifetime checks also use slices of
at most 256 retained roots or four milliseconds. Connection/EAC validation still
runs before game-thread work. No full asset scan runs every 250 milliseconds.

A rebuilt DLL cannot replace an already loaded preview module safely. Keep the
owned server running, restart the Rust client through the explicit no-EAC setup,
and use Inject for the new build; Ruster never hot-patches or unloads the old DLL.

A newly introduced asset that Rust cannot load dynamically reports
an error; restart preview with that asset in the initial composition. There is no
fixed placement-count cap. The binary snapshot size guard remains 16 MiB, and
actual scene performance depends on memory and Rust's update work. Readers
validate the count against the bytes present before allocating record arrays.
Updates stage replacements before removing previous
objects; a failed creation preserves the previous scene. Retired objects are
deactivated before Unity's deferred destruction, and both sides synchronize
physics before acknowledging the revision. This prevents old movement/no-build
colliders from participating until frame-end destruction. Volume visibility is
an editor overlay setting; snapshots still carry the original native prefab ID,
position, rotation and scale, including deletion and undo/redo snapshots.

Static compound prefabs whose children stay under their root can use ordinary
placement updates. Whole monuments can also depend on terrain, navmeshes,
map-time entity spawners and children that detach during `Awake`. Those cannot
be synchronized by moving or destroying just the root. The server detects
`DetachMonumentChildren` and populated `SceneToPrefabSpawner` hierarchies before
staging live additions. It reports that these require map initialization.
Such monuments present in the initial map stay fixed during that session;
moving, resizing, replacing or deleting one rejects the snapshot before mutation.
Save the desired layout and restart preview to rebuild the native map, or export
the composition as a map for normal Rust loading. This does not promise complete
monument gameplay: terrain, paths, navmesh rebuilding, puzzle
serialization and full monument gameplay configuration are outside this preview.
Rust's instanced rendering and special prefabs still need in-game validation.

The volume update regressions exercise native snapshot capture, high unsigned
prefab IDs, transform/rotation/scale replay, deletion, undo/redo, collider
deactivation order and failed-retirement rollback using offline fixtures. The
companion also compiles against the installed server assemblies. These checks
do not prove player movement blocking or building denial in a running client.

Sessions, downloads, logs, and the managed server live under Ruster's user-data
`live-preview` folder. Existing Rust installations, maps, server profiles and saves
are not changed. The client DLL is loaded in memory only after the explicit
action. The server, map HTTP service, RCON and query listeners use loopback.
Only owned child processes are stopped. Server processes have their own cleanup
job and do not share the editor's 8 GB memory cap. Multiple Ruster instances
cannot use or update the same managed server installation concurrently. Opening
or creating another composition stops its current preview.

## Build from source

Run `python tools/build_preview_client.py` on Windows. It uses `zig` from PATH,
or downloads the pinned official Zig 0.15.2 portable compiler and checks its SHA256.
`--zig PATH` selects an already installed compiler. Output is
`ruster/preview_native/bin/RusterPreview.dll` (ignored by Git). Packaging builds
and includes this DLL from the checked-in C++ source. Rust, SteamCMD and Carbon
remain first-run downloads. The server plugin source is shipped and compiled by
Carbon against the installed server.

For offline server validation, run
`python tools/check_preview_server.py --server PATH_TO_DEDICATED_SERVER`.
This compiles the companion against the downloaded server and Carbon assemblies
and tests the managed decoder against the native decoder's valid and malformed
snapshot fixtures. It does not start a game or inspect a client process.

For a static API report already generated from the installed files with Cpp2IL,
run `python tools/check_preview_api.py --metadata-report PATH_TO_REPORT`.
The checker reads the binding contract directly from the native bridge source
and rejects missing or ambiguous signatures. This audit never launches Rust.
