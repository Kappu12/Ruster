# Third-party software and content

## Blender

Ruster is built on Blender. Packaged distributions retain Blender's `license`
directory, copyright notices and runtime dependencies. Blender is GPL software;
Ruster's code is licensed GPL-3.0-or-later. See `LICENSE`.
The interface uses Blender's bundled RNA icons and toolbar `.dat` icon pack;
these remain part of the licensed Blender runtime, with no external icon font.

- Upstream: https://projects.blender.org/blender/blender
- Exact source reference: `v4.5.14` (`engine.lock.json`)
- Source archive: https://projects.blender.org/blender/blender/archive/v4.5.14.tar.gz
- License: https://www.blender.org/about/license/

When distributing binaries, provide the corresponding Ruster and Blender source
in a GPL-compliant manner. An upstream URL alone is not a substitute for complying
with source-distribution requirements. This repository and its private build
artifacts are a development workflow, not a public binary/source release process.

## Community Blender MCP

Ruster adapts selected bridge/inspection methods from `addon.py` and the
`BlenderConnection` class from `src/blender_mcp/server.py` of
https://github.com/ahujasid/mcp-for-blender at commit
`5a3618fccb2d982d0dd61e7a1879912c3100073b` (MIT, Copyright 2025 Siddharth Ahuja).
The retained license is `ruster/vendor/BLENDER_MCP_LICENSE`; the pinned origin and
edits are recorded in `ruster/vendor/upstream.json`. These files remain MIT code
within the GPL-compatible application. Ruster's command policy, settings and
MCP tool registration are its own implementation. Upstream telemetry, arbitrary
code execution, external asset services and addon installers are not included.

The adapter uses the official Python MCP SDK, pinned to `mcp==1.30.0` (MIT).
Its distribution metadata and dependency licenses remain in `python_modules`.
Source: https://github.com/modelcontextprotocol/python-sdk

## UnityPy and dependencies

Asset conversion uses UnityPy 1.25.4 (MIT), installed from PyPI, with its dependency
licenses retained in the packaged `python_modules` metadata directories.

- https://github.com/K0lb3/UnityPy
- https://pypi.org/project/UnityPy/1.25.4/

The map adapter is independently written using the published Rust.World SDK
format and the documented lz4net legacy stream framing. It does not bundle their
compiled libraries or copy their implementation.
The reader optionally uses `python-lz4` (already supplied by UnityPy's
dependencies) for native block decompression. Its Python bindings and bundled
LZ4 library notices are retained in `python_modules` distribution metadata.
Legacy stream framing, size checks and the Python fallback remain Ruster code.

- https://github.com/python-lz4/python-lz4

- https://github.com/Facepunch/Rust.World (MIT SDK reference)
- https://github.com/MiloszKrajewski/lz4net (legacy framing reference)
- https://wiki.facepunch.com/rust/Map_Data

## Rust content

Rust and its assets belong to Facepunch and their respective rights holders.
Ruster is an independent community tool, not an official Facepunch product.
The repository and application package contain no Rust game models/textures/maps.
The user supplies a local installation. Generated caches and saved projects may
contain game assets and must not be treated as redistributable open-source art.

- https://facepunch.com/legal/tos
- https://facepunch.com/legal/modding
