# Rust map generation

Choose **Generate Rust Map** from the welcome screen, File/Map menu or Ruster
sidebar. Set a seed (0–2147483647) and world size (1000–6000 metres). The sidebar
shows elapsed time, cancellation, logs and **Open Generated Map** when ready.
Completion never replaces your current project; opening uses the ordinary
unsaved-work confirmation.

## Backend and installation

Ruster looks for **Rust Dedicated Server**, Steam app 258550, in standard Steam
libraries and their app manifests. A custom/SteamCMD installation can be selected
in the existing **Blender Preferences → Rust Assets → Procedural Map Generator**
section. Choose `RustDedicated.exe` on Windows or `RustDedicated` on Linux and
click Apply Generator. The Rust client installation used for assets is separate.
No binaries/assets are bundled, extracted, modified or automatically downloaded.
Install/update the official server separately and retain its required runtime,
data and bundle directories.

This is **not a stripped/recompiled server** or an independent Rust generator.
It launches the installed Unity dedicated runtime with `-batchmode -nographics`,
seed and size, watches its map output, and stops its owned process as soon as
a complete map validates. It does not wait for `Server startup complete`.
There is no evidence-based speed claim yet: native terrain/monument generation,
runtime initialization and validation still cost time. No real RustDedicated is
available in the automated test environment. Generation compatibility and peak
memory/elapsed time must be measured on an actual current installation before
calling it production-ready.

## Isolation and output

- Each job gets a random `ruster_gen_…` server identity. Existing server profiles
  are never selected or deleted. Generated server identity directories can remain
  in the installation; no broad cleanup of user server files is attempted.
- Game/query/RCON addresses are loopback; ephemeral ports and zero player slots
  are requested. A random RCON password is supplied. This is process configuration,
  **not an OS network sandbox**; Rust can still make its own outbound requests.
- Only exact seed-and-size filenames in bounded known map locations are considered.
  A new/changed file must stabilize, decompress, parse and have valid terrain/water
  grids of the requested world size before being accepted.
- Unchanged old caches are deliberately rejected, since matching filenames alone
  cannot establish current game-build compatibility. If Rust reuses a cache without
  rewriting it, this job can fail with a clear log message. It never deletes or
  overwrites the cache to force regeneration. Current-build cache reuse is future work.
- The exact validated map bytes and logs are retained in Ruster's user-data
  `generated/ruster_gen_…` job folder. Originals in Rust's map cache are retained.
- Cancel, timeout (30 minutes by default) and app shutdown terminate/reap only the
  owned child. Blender does not wait for generation on its UI thread.

MCP exposes `generate_map(seed, size)`, `get_generation_status()` and
`cancel_generation()`. These use the same backend. AI cannot supply executable
paths, command-line flags or server identities, and cannot silently open a result.

## Verification

Synthetic process tests cover partial writes, byte-exact output, early termination
before simulated server startup, cancellation, timeout, stale caches, discovery
and profile preservation. Blender tests verify shared settings, controls, separate
opening and shutdown. These do not replace a current-game end-to-end test.

Reference: [Facepunch server setup](https://wiki.facepunch.com/rust/Creating-a-server).
