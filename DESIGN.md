# Ruster interface

## Visual rule

Use Blender's native theme and UI components. Do not invent a second visual
system. Keep its normal typography, spacing, icons, panel hierarchy, selection
colors, input fields, tooltips and keyboard conventions. Do not modify the user's
ordinary Blender configuration.

## Entry and modes

First launch asks for the Rust game installation folder. Store this per user,
outside project files. Indexing is visible and runs outside the UI process.

The start screen has two primary actions: Open Map or Project, and New Project.
Opening `.map` selects Rust map mode; opening `.ruster` restores its saved mode.
New Project restores the standard Blender startup scene and full workspaces.

Map mode uses one Rust Map workspace, with the 3D viewport, Outliner, native
property panels and the Ruster sidebar. Replace unrelated top-level authoring
menus with project, edit, map and asset actions. Retain normal viewport navigation,
selection, transforms, snapping, shading, undo and redo. Expose only implemented
Rust workflows. Do not add nonfunctional brushes or decorative controls.

## Editing contract

Terrain brushes edit full-resolution layer data; the viewport mesh is a disposable
preview at adjustable detail. Paths use native curve node editing and retain
source metadata. Each brush stroke is one undo step. A prefab root is an editable placement; its model hierarchy is
read-only linked library data. The root supports placement transforms and whole-
instance operations; never expose mesh editing, sculpting, booleans, make-local
or library-override actions as map editing. Terrain holes affect only terrain.
Duplicate/delete operate on complete instances; reject editable/unpacked model
copies at export and offer original-model restoration. Legacy editable previews
must not be treated as verified originals without rebuilding from asset sources. Missing
visuals are clearly represented as placement boxes, with a report explaining why.
Unsupported custom mesh data may be stored in `.ruster` but blocks `.map` export.
Prefab painting uses whole instances, native strokes and local favorite palettes.
Esc removes the whole pending stroke; placement spacing is not collider testing.

## Saving

`.ruster` means the editable project, not a renamed `.map` or `.blend`. Saving
packs scene previews and source map data and full-resolution edit snapshots. Export writes a separate game map and
preserves unedited/unknown data. Opening or creating a project prompts the user
to save existing work before replacing it. Do not silently overwrite a source map.

## Performance

Catalog and extract game bundles in a separate worker process. Cache using source
bundle identity and timestamps, share Blender mesh datablocks for repeated
prefabs, and attach converted visuals incrementally. Keep the original terrain
samples separately from the reduced viewport mesh. Report unsupported assets
without hiding their placement data.
