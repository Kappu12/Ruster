# Ruster interface

## Visual rule

Use Blender's native theme and UI components. Do not invent a second visual
system. Keep its normal typography, spacing, icons, panel hierarchy, selection
colors, input fields, tooltips and keyboard conventions. Do not modify the user's
ordinary Blender configuration.

All Ruster menus, dialogs and panels use the bundled Blender icon pack, with
semantic names and shared action labels in `ruster/ui_style.py`. Toolbar tools
use distinct `.dat` icons shipped with the pinned Blender runtime. Do not add a
second icon font, emoji, external raster button graphics or fixed color palette.
The runtime and its icon licenses remain in the app distribution.

Use native property splits without animation decorators for map authoring
controls. Group advanced options in native collapsible sections, retain normal
row heights, and indicate the active viewport tool with Blender's pressed state.
Hints wrap according to sidebar width and UI scale. Busy asset jobs use Blender's
progress bar only when the worker reports a real total; otherwise show status.
Dark and light themes must both work, and New Project must preserve preferences.

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
Select the Ruster sidebar after the first map draw. Native Properties panels
without an existing poll need their RNA registration refreshed when installing
map-mode filtering; restore their original registrations on app unload.

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

Layer masks are grayscale PNG/TIFF, with a visible layer/channel choice and image
orientation hint in the native file selector. Images map their top row to +Y by
default. Weight masks resize bilinearly and set one channel exactly; redistribute
the remaining weight proportionally with integer rounding to a total of 255.
Topology and terrain-hole masks use nearest samples and a midpoint threshold;
editing one topology bit must preserve all the others, including unknown bits.
Validate and compute the complete result before committing an undoable terrain
snapshot. No-op imports must not create redundant snapshots. Never touch prefab
geometry or unrelated layers, and never export a mask at reduced preview detail.

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
