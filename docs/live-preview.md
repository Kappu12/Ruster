# Local live preview (experimental, Windows x64)

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
   applies editor snapshots to static scene objects. The server companion updates
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

The module applies placements only when the client's current world URL matches
the random loopback map URL and the companion reports a connected local player.
All game object operations run through a callback on the Unity window thread.
IL2CPP methods are found through their exported reflection API and checked
signatures. Missing or ambiguous methods produce a compatibility error; there
are no guessed offsets or fallback game-code patches.

The dedicated server starts with its native `-insecure` switch. The companion
checks `Network.Net.sv.secure` before advertising readiness and on every update.
Ruster validates a fresh heartbeat with the matching server PID and session
identity before injection. A secure or non-loopback server is refused and
stopped; no EAC setting is bypassed or patched.

The editor checks for scene changes about twice per second; capture batches yield
to keep editing responsive. The server and client poll at 4 Hz. The intended edit
delay is roughly 0.5–1 second, depending on scene size and server load. This is
placement synchronization, independent of Rust's rendering frame rate; the delay
has not been measured in a running Rust client.

## Current limits and validation

This is an experimental implementation, not a claim of verified current-game
compatibility. Build checks, offline EAC rejection tests, binary protocol tests,
and Blender lifecycle tests do not prove that a particular Rust release can run
the injected module. No client injection or gameplay testing was performed during
development, at the user's request. Runtime errors appear in the panel and logs.
The local dedicated server has been booted successfully with an empty void map,
the companion loaded, and runtime EAC-disabled readiness verified. Client-side
prefab rendering and injected gameplay remain untested.

The composition is centered in a 1,000 metre void map. Terrain is entirely holes,
the ocean is moved out of view through Rust's replicated environment setting,
and no extra scenery or platform is added. The initial composition's placement
center is translated to the origin in the preview snapshots; the project itself
stays unchanged. That translation stays fixed during edits. Starting empty uses
the first composition's center instead. Load the composition before starting so
the map can preload its original asset scenes. The companion supplies a spawn
point above available prefab colliders. Use owner permissions and Rust's F1
`noclip` for free movement when the composition has no walkable surface.

Both companions claim the baked placements instead of adding
duplicates. A newly introduced asset that Rust cannot load dynamically reports
an error; restart preview with that asset in the initial composition. There is a
2,000 placement limit. Updates stage replacements before removing previous
objects; a failed creation preserves the previous scene. Both readers use the
same bounded binary snapshot format. Terrain, paths, navmesh rebuilding, puzzle
serialization and full monument gameplay configuration are outside this preview.
Rust's instanced rendering and special prefabs still need in-game validation.

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
