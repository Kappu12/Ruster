# Rustmatics interface

## Product scope

Rustmatics is a prefab composition editor built on Blender 5.2 LTS. Its active
workspace is **Prefab Studio**. Users compose whole original Rust assets, save
editable `.ruster` projects, and export native RustEdit `.prefab` files,
prefab-only `.map` files, assemblies or standalone models.

Opening a `.map` reads prefab placements only. Exporting `.map` writes those
placements into empty space without terrain or paths. This is not a complete
playable world. Retained terrain, path, painting and generation source is dormant
and must not appear as supported authoring UI. Legacy map projects recover their
prefab composition. See [FEATURES.md](FEATURES.md) for verification limits.

## Native visual language

Use Blender's native theme and UI components: typography, spacing, icons, panel
hierarchy, selection colors, fields, tooltips and keyboard conventions. All
Rustmatics menus, dialogs and panels share semantic icons and action labels in
`ruster/ui_style.py`. Toolbar tools use distinct `.dat` icons from the pinned
runtime. Do not introduce an external icon font or a fixed UI palette.

Keep advanced options in native collapsible sections and retain normal row
heights. Hints wrap for sidebar width and UI scale. Use a progress bar only when
the worker supplies a real total; otherwise show the current phase. Both dark
and light themes must work. New Prefab preserves user preferences. Rustmatics uses an
isolated configuration and never changes an ordinary Blender installation's
preferences.

Live Preview occupies its own native editor below Placements on the right,
outside the viewport's extension sidebar. Keep that editor when removing the
timeline and restore it for older projects whose saved layouts lack it. Its
status, no-EAC launch/injection controls and console use the shared UI vocabulary.
Installation displays measured phase progress and an explicitly approximate
overall percentage. Preview compositions are centered in a void without moving
the authored objects. Keep viewport Overlays and Volumes as icon-only toggles,
and place the app identity before the Rustmatics menu in the far-left corner.

## Entry and discovery

Start with an empty Prefab Studio workspace. The centered **New / Open** popup
offers New Prefab, Open Map/Prefab/Project, recent projects and recovery. Its
placement is independent of the pointer. Keep project actions accessible in the
Rustmatics menu and sidebar after dismissal.

Discover validated Rust installations from the saved folder, standard Steam
paths, the Windows registry and secondary Steam libraries. Do not recursively
scan drives or modify Steam files. Manual installation and local RustEdit
string-pool selection belong in **Preferences → Assets**. These paths are user
settings, separate from project data.

**Shift+A** opens compact native category menus. Immediate typing or **Search All
Prefabs** searches the entire catalog, including hidden and unavailable entries,
independently of sidebar filters. Reuse one incrementally warmed metadata index;
searching must not load models or repeatedly scan the catalog.

The sidebar browser combines search, categories, favorites, recently used
prefabs, local availability and hidden-asset filters. Recent placements are
stored per user, deduplicated and bounded to 48 IDs, newest first. Favorites stay
independent. Preserve pagination after filtering; stale page indices must return
a valid page. Reset Filters clears search, category, favorites and recents and
shows all locally available assets, including hidden helpers.

Each browser entry offers inspection without placement: full asset path, ID,
local availability, conversion-cache presence, Copy ID and Copy Path. Empty
favorites and recents explain how to populate them. Missing assets explain what
needs attention rather than appearing as an unexplained disabled action.

## Composition and originals

Use native viewport navigation, selection, transforms, snapping and undo. A
prefab root is an editable placement; its source mesh/material hierarchy remains
a protected linked library. Transform, group, duplicate, replace or remove whole
placements. Never present mesh editing, sculpting, make-local or library
overrides as Rust prefab authoring. Model exports operate on disposable copies.

Keep Blender's interaction conventions: F3 opens searchable prefab commands,
Space retains the user's native Spacebar Action, and F9 adjusts the last
operation. Shift+D (and Alt+D for the shared originals) duplicates in place and
starts native Move with axis constraints, numeric input and snapping. Escape
cancels movement while keeping the duplicate; undo removes the complete action.
Outliner and top-bar duplication stays in place without invoking a viewport
transform. X confirms deletion; Delete acts immediately. Orientation and pivot
controls use Blender's own scene settings. Layout and symmetry actions belong
in the Object menu and right-click menu as well as the sidebar.

Use Z-up metres in the editor. The authoring plane is Z=0. View projection and
overlays are adjacent header controls; Shift+F enters native Walk Navigation.
The adjacent Volumes toggle controls only viewport collider previews. Keep
volumes in one browser category and preserve their placement records when hidden.
Use source collider data, persist it for offline projects, and draw selectable
translucent bounds with native theme/selection colors. Unknown bounds get an
explicit origin marker. Effects use arrows and descriptive labels, not volume
spheres. Crate previews retain their spawner identity and explain runtime limits.
Large native prefab imports create placements before loading models; repeated
placements must yield within a bounded linking batch. Never rescan every prior
copy to allocate a display name or recompute model counts on every viewport draw.
Build missing Blender preview libraries in a hidden, owned background process;
cancel that process with asset loading and on shutdown. Its native profile is
isolated from the user's normal Blender preferences. Keep failures retryable and
retain placement records even when a preview cannot be prepared.
Object Snap and Radial Symmetry have toolbar toggles and settings popovers.
Explain when editing or deleting a symmetry member affects its complete set.
Symmetry settings support world axes, copy orientation and centers from the
cursor or selection. Editing existing sets requires an explicit Apply Settings
action. Keep the original and surviving copy identities when changing side
counts. Complete group transforms carry the symmetry frame with them.

Expose whole-prefab layout actions in a collapsible Prefab Layout panel. Reuse
the typed layout backend and native undo. Diagnostics may select placements for
inspection; never silently delete overlapping copies or normalize transforms.
Editor labels may contain spaces; game identity remains the original prefab ID.

Pending models use wireframe placement boxes. Geometry-free sounds, terrain
stamps and other helpers have explicit markers and descriptions. Their placement
records remain intact. Do not label intentional helpers as model failures.

## Loading and diagnostics

Catalog browsing never triggers bulk conversion. Request original models on
demand, share models between repeated placements, and link cached models
incrementally. Keep conversion outside the UI process and enforce worker,
memory and batch bounds documented in [README.md](README.md).

Use one shared status presentation in the header popover, Model Loading sidebar
panel and Assets preferences. Show the current phase and counts of placements
loaded, loading, not loaded, with issues and represented by helpers. Counts refer
to placements; conversion requests are bounded by unique prefab IDs.

Select Unloaded and Select Issues locate placements needing attention. Load /
Retry Selected Models uses that selection; Cancel stops pending work. Surface
linking separately from conversion so "ready" does not imply models are already
visible. Asset Report displays readable issue details and copies the complete
diagnostics, including errors retained in offline projects. Keep long reports
bounded in the dialog and preserve the complete text for copying.

## Saving and replacing a document

`.ruster` is the editable project. It packs linked previews for reopening without
the conversion cache and saves atomically. Export creates a separate interchange
file; never silently overwrite a source map.

Show Saved, Unsaved changes or Not saved yet in the header and Prefab Studio
panel. Windows window captions include the same state. Compare the editable
document to the successful `.ruster` savepoint; preview loading, selection and
viewport changes do not mark it dirty. UI drawing reads cached state rather than
hashing the document on every redraw.

Incremental scans must release Blender data references before undo, redo or file
loading replaces the document. Never retain a native Blender collection iterator
across timer yields; native deletion can invalidate its current node without a
Python exception.

Quit, New and Open protect unsaved work with Save, Don't Save and Cancel. Clean
saved projects proceed without a warning. Save uses the current `.ruster` target
or opens the project picker for untitled work. Continue only after a successful
save; cancelling a picker or a failed write retains the current document. Let a
save picker close before continuing to another document or file picker.

Recovery writes atomically every two minutes while idle and preserves the manual
save target. Offer recovery in New / Open. Recovery does not replace the manual
savepoint.

## MCP and preferences

Assets and MCP share Blender's native Preferences navigation with its standard
interface, theme and navigation sections. Preserve native shortcuts and restore
original registrations when unloading the app.

MCP is off by default, bound to loopback and authenticated per user. Port, token
and enablement belong to preferences. Copy client configuration for the bundled
stdio adapter. Typed discovery, placement, layout, inspection and interchange
operations run through the main-thread queue and preserve undo and original
models. There is no arbitrary Python or custom mesh authoring endpoint. Stop
closes connections and drops queued work. The maintained workflow and Rust
composition rules are in `ruster://guide/building` and `ruster://guide/design`.
