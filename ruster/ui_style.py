"""Shared UI vocabulary using only Blender's bundled, theme-aware icon set.

No image previews, external icon fonts, fixed UI colors or theme overrides.
Toolbar .dat handles also come from the pinned Blender runtime.
"""
import textwrap

ICONS={
    'none':'NONE','project':'FILE_BLEND','world':'WORLD','start':'HOME',
    'new':'FILE_NEW','open':'FILE_FOLDER','save':'FILE_TICK','save_as':'FILE_BLEND',
    'import':'IMPORT','export':'EXPORT','settings':'PREFERENCES','quit':'QUIT',
    'undo':'LOOP_BACK','redo':'LOOP_FORWARDS','duplicate':'DUPLICATE','delete':'TRASH',
    'group':'GROUP','ungroup':'UNLINKED','snap':'SNAP_FACE','select_same':'SELECT_EXTEND',
    'replace':'ARROW_LEFTRIGHT','scatter':'PARTICLES','restore':'FILE_REFRESH',
    'prefab':'OUTLINER_OB_GROUP_INSTANCE','terrain':'MESH_GRID','terrain_brush':'BRUSH_DATA',
    'prefab_brush':'PARTICLE_DATA','path':'CURVE_PATH','edit_path':'EDITMODE_HLT',
    'finish_path':'CHECKMARK','validate':'CHECKMARK','locked':'LOCKED','info':'INFO',
    'error':'ERROR','busy':'TIME','cancel':'CANCEL','refresh':'FILE_REFRESH','report':'TEXT',
    'recover':'RECOVER_LAST','search':'VIEWZOOM','favorite_on':'SOLO_ON','favorite_off':'SOLO_OFF',
    'previous':'TRIA_LEFT','next':'TRIA_RIGHT','cursor':'CURSOR','clone':'EYEDROPPER',
    'bridge':'IPO_LINEAR','generate':'WORLD','overlay':'OVERLAY','detail':'MESH_GRID',
    'move':'EMPTY_ARROWS','rotate':'ORIENTATION_GIMBAL','scale':'FULLSCREEN_ENTER',
    'select':'RESTRICT_SELECT_OFF','water':'MOD_OCEAN','splat':'TEXTURE','biome':'WORLD',
    'topology':'GROUP_VERTEX','alpha':'IMAGE_ALPHA','blank':'BLANK1','snapping':'SNAP_ON',
}

TOOL_ICONS={
    'terrain':'ops.sculpt.mesh_filter',
    'prefab':'brush.particle.add',
}

# One action has the same name and icon in sidebars, menus and command popups.
ACTIONS={
    'ruster.welcome':('Start','start'),
    'ruster.new':('New Project','new'),
    'ruster.new_map':('New Rust Map','world'),
    'ruster.generate_map':('Generate Rust Map…','generate'),
    'ruster.random_seed':('Random Seed','generate'),
    'ruster.cancel_generation':('Cancel Generation','cancel'),
    'ruster.open':('Open Map or Project…','open'),
    'ruster.save':('Save Project','save'),
    'ruster.export_map':('Export Rust Map…','export'),
    'ruster.setup':('Rust Installation…','settings'),
    'ruster.preferences':('Preferences…','settings'),
    'ruster.mcp_config':('Copy MCP Client Configuration','duplicate'),
    'ruster.mcp_retry':('Retry MCP Connection','refresh'),
    'wm.quit_blender':('Quit Ruster','quit'),
    'ed.undo':('Undo','undo'),'ed.redo':('Redo','redo'),
    'ruster.duplicate':('Duplicate Prefabs','duplicate'),
    'ruster.delete':('Delete Prefabs','delete'),
    'ruster.group':('Group Prefabs','group'),
    'ruster.ungroup':('Ungroup Prefabs','ungroup'),
    'ruster.surface_snap':('Snap to Terrain…','snap'),
    'ruster.select_same':('Select Same Prefab','select_same'),
    'ruster.replace':('Replace Prefabs…','replace'),
    'ruster.scatter':('Scatter Prefabs…','scatter'),
    'ruster.assembly_import':('Import Prefab Group…','import'),
    'ruster.assembly_export':('Export Prefab Group…','export'),
    'ruster.restore_models':('Restore Original Models','restore'),
    'ruster.path_add':('Add Path','path'),
    'ruster.path_snap':('Snap Path to Terrain','snap'),
    'ruster.path_grade':('Grade Terrain Along Path','bridge'),
    'ruster.height_import':('Import Heightmap…','import'),
    'ruster.height_export':('Export Heightmap…','export'),
    'ruster.mask_import':('Import Layer Mask…','import'),
    'ruster.mask_export':('Export Layer Mask…','export'),
    'ruster.validate':('Validate Map','validate'),
    'ruster.assets':('Load Map Assets','import'),
    'ruster.cancel_assets':('Cancel Asset Loading','cancel'),
    'ruster.asset_report':('Asset Report','report'),
    'ruster.terrain_apply':('Apply Brush at Cursor','cursor'),
    'ruster.clone_source':('Set Clone Source at Cursor','clone'),
    'ruster.terrain_bridge':('Grade Bridge to Cursor','bridge'),
    'ruster.generate_island':('Generate Island…','generate'),
    'ruster.terrain_overlay':('Refresh Terrain Overlay','refresh'),
    'ruster.terrain_detail':('Update Terrain Detail','detail'),
    'transform.translate':('Move','move'),
    'transform.rotate':('Rotate','rotate'),
    'transform.resize':('Scale','scale'),
}


def action(layout,operator,*,text=None,icon=None,**kwargs):
    label,semantic=ACTIONS[operator]
    return layout.operator(operator,text=label if text is None else text,
        icon=ICONS[semantic if icon is None else icon],**kwargs)


def properties(layout):
    layout.use_property_split=True
    layout.use_property_decorate=False
    return layout


def section(layout,identifier,title,icon,*,closed=True):
    header,body=layout.panel(identifier,default_closed=closed)
    header.label(text=title,icon=ICONS[icon])
    if body is not None:properties(body)
    return body


def wrapped(layout,context,text,*,icon=None,width=None):
    """Wrap full-width hints using region width and the user's UI scale."""
    region=getattr(context,'region',None)
    scale=context.preferences.system.ui_scale
    available=width*scale if width is not None else getattr(region,'width',320)
    columns=max(12,min(64,int((available-48*scale)/(7*max(scale,.5)))))
    lines=textwrap.wrap(str(text),width=columns,break_long_words=True,break_on_hyphens=False) or ['']
    for index,line in enumerate(lines):
        layout.label(text=line,icon=ICONS[icon] if index==0 and icon else ICONS['blank' if icon else 'none'])


def tool_button(layout,context,tool,label,icon):
    active=None
    if context.workspace:
        active=context.workspace.tools.from_space_view3d_mode(context.mode,create=False)
    return layout.operator('wm.tool_set_by_id',text=label,icon=ICONS[icon],
        depress=bool(active and active.idname==tool))
