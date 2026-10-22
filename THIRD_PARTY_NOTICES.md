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

## UnityPy and dependencies

Asset conversion uses UnityPy 1.25.4 (MIT), installed from PyPI, with its dependency
licenses retained in the packaged `python_modules` metadata directories.

- https://github.com/K0lb3/UnityPy
- https://pypi.org/project/UnityPy/1.25.4/

The map adapter is independently written using the published Rust.World SDK
format and the documented lz4net legacy stream framing. It does not bundle their
compiled libraries or copy their implementation.

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
