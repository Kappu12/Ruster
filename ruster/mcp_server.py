"""Stdio MCP adapter for the bundled, authenticated community Blender bridge."""
import base64
import threading
from typing import Literal
from pydantic import BaseModel,Field,ConfigDict
from mcp.server.fastmcp import FastMCP,Image
from mcp.types import ToolAnnotations
from .core import settings,mcp_config
from .vendor.blender_mcp_client import BlenderConnection

_connection=None
_lock=threading.Lock()
mcp=FastMCP('Ruster',instructions='Author custom prefab compositions using original local Rust assets. Read ruster://guide/building and get_editor_status first. Discover assets with paginated search_prefabs including hidden helpers. Inspect cached model bounds; request missing assets and poll status. Use atomic placement/transform batches, groups, arrays, bounds alignment and plane snapping. Export native prefab, model formats or prefab-only map files. World metres: Z up, XYZ Euler degrees. Original geometry/materials remain linked and read-only. Enable Preferences MCP. Inspect the scene before retrying timed-out mutations.')
READ=ToolAnnotations(readOnlyHint=True,destructiveHint=False,openWorldHint=False)
EDIT=ToolAnnotations(readOnlyHint=False,destructiveHint=False,openWorldHint=False)
DESTRUCTIVE=ToolAnnotations(readOnlyHint=False,destructiveHint=True,openWorldHint=False)


def command(rpc_kind,**params):
    global _connection
    with _lock:
        config=settings.load()
        if not mcp_config.enabled(config):raise ValueError('Enable MCP in Preferences → MCP first')
        token=config.get('mcp_token','')
        if not isinstance(token,str) or len(token)<32:raise ValueError('Start MCP in Preferences → MCP first')
        port=mcp_config.port(config)
        if _connection and (_connection.port!=port or _connection.token!=token):_connection.disconnect();_connection=None
        if _connection is None:_connection=BlenderConnection('127.0.0.1',port,token)
        return _connection.send_command(rpc_kind,params)


@mcp.tool(annotations=READ)
def get_scene_info()->dict:
    """Inspect active prefab composition mode, prefab count and scene objects."""
    return command('get_scene_info')


@mcp.tool(annotations=READ)
def get_object_info(name:str)->dict:
    """Inspect world position, XYZ degree rotation and scale of an object."""
    return command('get_object_info',name=name)


@mcp.tool(annotations=READ)
def list_map_objects(limit:int=100,offset:int=0,query:str='',kind:str='',prefab_id:int|None=None,include_bounds:bool=False)->dict:
    """Legacy alias for list_objects. Page placements/groups; bounds are opt-in for large scenes. Filter names, kind PREFAB/GROUP, or ID; limit 1–200."""
    return command('list_map_objects',limit=limit,offset=offset,query=query,kind=kind,prefab_id=prefab_id,include_bounds=include_bounds)


@mcp.tool(annotations=READ)
def search_prefabs(query:str='',category:str='',limit:int=20,offset:int=0,available_only:bool=False)->dict:
    """Browse/search every indexed Rust prefab by descriptive tokens in any word order (with aliases) and optional category prefix; hidden assets are included. Empty query lists all. Returns IDs, paths, local availability, next_offset. Follow pages until next_offset=null; limit 1–100. Never invent prefab IDs."""
    return command('search_prefabs',query=query,category=category,limit=limit,offset=offset,available_only=available_only)


@mcp.tool(annotations=EDIT)
def place_prefab(uid:int,position:list[float],rotation_degrees:list[float]|None=None,scale:list[float]|None=None)->dict:
    """Place an available local prefab. Three-component world vectors: position/metres with Z height, rotation XYZ degrees, scale factors. Original model stays read-only."""
    return command('place_prefab',uid=uid,position=position,rotation_degrees=rotation_degrees,scale=scale)


@mcp.tool(annotations=EDIT)
def transform_object(name:str,position:list[float]|None=None,rotation_degrees:list[float]|None=None,scale:list[float]|None=None)->dict:
    """Set absolute world placement/group transforms. Rotations are XYZ degrees. Rejects group shear and zero scale; cannot change prefab meshes."""
    return command('transform_object',name=name,position=position,rotation_degrees=rotation_degrees,scale=scale)


@mcp.tool(annotations=EDIT)
def duplicate_object(name:str)->dict:
    """Duplicate a whole placement or group using native Ruster operations."""
    return command('duplicate_object',name=name)


@mcp.tool(annotations=DESTRUCTIVE)
def delete_object(name:str)->dict:
    """Delete a whole placement or group. Supports undo; never deletes model parts."""
    return command('delete_object',name=name)


@mcp.tool(annotations=READ)
def validate_map()->dict:
    """Report composition export errors and unloaded assets without exporting."""
    return command('validate_map')


@mcp.tool(annotations=DESTRUCTIVE)
def save_project(path:str,overwrite:bool=False)->dict:
    """Save to an absolute .ruster destination. Existing files require explicit overwrite=True."""
    return command('save_project',path=path,overwrite=overwrite)


@mcp.tool(annotations=DESTRUCTIVE)
def export_map(path:str,overwrite:bool=False)->dict:
    """Export ONLY prefab placements floating in void to an absolute .map destination. No terrain or paths. Existing files require explicit overwrite=True."""
    return command('export_map',path=path,overwrite=overwrite)


@mcp.tool(annotations=DESTRUCTIVE)
def undo()->dict:
    """Undo the latest native editing action, including manual edits."""
    return command('undo')


@mcp.tool(annotations=DESTRUCTIVE)
def redo()->dict:
    """Redo the latest undone native editing action."""
    return command('redo')


class PrefabPlacement(BaseModel):
    model_config=ConfigDict(extra='forbid')
    uid:int=Field(ge=0,le=4294967295,description='Rust prefab ID returned by search_prefabs')
    position:list[float]=Field(min_length=3,max_length=3,description='World XYZ metres, Z up')
    rotation_degrees:list[float]|None=Field(default=None,min_length=3,max_length=3)
    scale:list[float]|None=Field(default=None,min_length=3,max_length=3)


class ObjectTransform(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name:str
    position:list[float]|None=Field(default=None,min_length=3,max_length=3)
    rotation_degrees:list[float]|None=Field(default=None,min_length=3,max_length=3)
    scale:list[float]|None=Field(default=None,min_length=3,max_length=3)


@mcp.tool(annotations=READ)
def get_editor_status()->dict:
    """Start here: project mode, catalog readiness, asset extraction progress, coordinate system and supported modeling workflow."""
    return command('get_editor_status')


@mcp.tool(annotations=READ)
def list_prefab_categories(limit:int=100,offset:int=0)->dict:
    """Discover catalog category paths and prefab counts. Page 1–200 categories; pass a path to search_prefabs(category=...)."""
    return command('list_prefab_categories',limit=limit,offset=offset)


@mcp.tool(annotations=READ)
def get_prefab_details(uid:int)->dict:
    """Inspect a catalog prefab's local dimensions/bounds, mesh/material/node/triangle counts and cached availability. Bounds enclose the original model; useful for sizing compositions. Uncached assets return a preload next step."""
    return command('get_prefab_details',uid=uid)


@mcp.tool(annotations=EDIT)
def request_prefab_assets(uids:list[int])->dict:
    """Queue extraction of 1–100 locally available prefab models without placing objects. Poll get_editor_status until idle, then inspect details/place."""
    return command('request_prefab_assets',uids=uids)


@mcp.tool(annotations=EDIT)
def place_prefabs(placements:list[PrefabPlacement],group_name:str|None=None)->dict:
    """Build a model from 1–100 whole Rust prefabs in one undo step. Every position/rotation/scale is absolute WORLD space. Optionally create a named composition group. Entire batch rolls back if any placement fails. Geometry remains original."""
    return command('place_prefabs',placements=[p.model_dump() for p in placements],group_name=group_name)


@mcp.tool(annotations=EDIT)
def transform_objects(transforms:list[ObjectTransform])->dict:
    """Atomically transform 1–200 placements/groups in one undo step. Absolute world transforms. On error restores all transforms. Choose parent group OR descendants, not both."""
    return command('transform_objects',transforms=[p.model_dump(exclude_none=True) for p in transforms])


@mcp.tool(annotations=EDIT)
def group_objects(names:list[str],name:str='AI Composition')->dict:
    """Combine 1–200 independent whole prefabs/groups into a reusable model. Preserves world transforms. Use uniform scale when rotating grouped components."""
    return command('group_objects',names=names,name=name)


@mcp.tool(annotations=EDIT)
def ungroup_object(name:str)->dict:
    """Remove a composition group while keeping its children and world transforms. Undo supported."""
    return command('ungroup_object',name=name)


@mcp.tool(annotations=EDIT)
def rename_object(name:str,new_name:str)->dict:
    """Name a placement/group for subsequent AI operations. Returns actual Blender name (uniqueness suffix may be added)."""
    return command('rename_object',name=name,new_name=new_name)


@mcp.tool(annotations=EDIT)
def focus_view(names:list[str],axis:Literal['CURRENT','TOP','BOTTOM','FRONT','BACK','LEFT','RIGHT','OBLIQUE']='CURRENT',rotation_degrees:list[float]|None=None)->dict:
    """Select and frame placements/groups without transforming models. Native axes or OBLIQUE (60,0,45 degrees); alternatively pass finite XYZ viewport Euler rotation_degrees with axis=CURRENT. Oblique/custom views use perspective."""
    return command('focus_view',names=names,axis=axis,rotation_degrees=rotation_degrees)


@mcp.tool(annotations=READ)
def get_viewport_image(include_overlays:bool=False)->Image:
    """Return a clean PNG of the current 3D viewport. Overlays (grids, relationships and selection outlines) are hidden by default; include_overlays=True includes them. Restores viewport/render settings on success or failure. Requires the desktop app."""
    result=command('get_viewport_image',include_overlays=include_overlays)
    return Image(data=base64.b64decode(result['data']),format='png')


@mcp.tool(annotations=DESTRUCTIVE)
def export_assembly(names:list[str],path:str,overwrite:bool=False,origin:list[float]|None=None)->dict:
    """Export reusable .rusterprefab using original prefab IDs. Positions are relative to explicit world XYZ origin, the pivot of a single selected group, or the mean placement position for other selections. Absolute destination; existing file requires overwrite=True."""
    return command('export_assembly',names=names,path=path,overwrite=overwrite,origin=origin)


@mcp.tool(annotations=EDIT)
def import_assembly(path:str,position:list[float],name:str|None=None)->dict:
    """Load a .rusterprefab composition at a world XYZ origin, preserving that group pivot. Uses only available local original prefabs; 2000-placement limit. Rolls back on failure; supports undo. Does not import arbitrary meshes."""
    return command('import_assembly',path=path,position=position,name=name)


BUILDING_GUIDE="""Ruster prefab authoring workflow
1. get_editor_status reports actual version, converter_version, restart_required, visible and unloaded placements. Enable Preferences MCP and open a prefab composition. Wait for extraction/visual loading before requesting more assets.
2. list_prefab_categories discovers taxonomy. search_prefabs includes hidden/IO helpers and supports descriptive tokens in any word order and aliases. Empty query browses all; follow next_offset. Never guess IDs. Local availability does not guarantee successful model extraction.
3. get_prefab_details/get_prefabs_details inspect original cached model dimensions and enclosing bounds. request_prefab_assets queues up to 100 real IDs; poll status then retry details. No full-engine scan is needed.
4. Coordinates are world XYZ metres, Z up. Rotation is XYZ Euler degrees; scale is a finite nonzero factor. Ground is an authoring plane at Z=0. snap_objects_to_plane moves true loaded model bottoms to a plane. align_objects uses MIN/CENTER/MAX bounds on X/Y/Z; omitted target uses the first object's bound.
5. Compose whole prefabs using atomic place_prefabs (up to 100) and transform_objects (up to 200). Groups preserve world transforms. Select parent groups OR descendants per batch. Prefer uniform group scale to avoid shear. Original meshes/materials remain linked and read-only.
6. list_objects/get_selection paginate lightweight metadata. include_bounds opts into model world bounds; get_objects_info batches up to 200 objects, get_prefabs_details up to 20 IDs. Child and mutation names are capped at 200; list_objects locates more without returning huge groups.
7. duplicate_objects makes one translated copy. array_objects makes count NEW copies using per-step world offset and XYZ rotation about the chosen roots' mean origin. Requests roll back on failure and allow at most 2000 new prefab placements/4000 hierarchy objects. delete_objects validates all targets before deletion. Undo/redo also affects manual edits.
8. focus_view frames native axes, OBLIQUE, or explicit XYZ rotation_degrees without transforming models. get_viewport_image defaults to a clean image; include_overlays=True includes guides. Viewport/render settings are restored after capture. Bounds enclose render geometry, not collision shapes; they do not certify server gameplay.
9. export_prefab/import_prefab exchange native RustEdit .prefab while preserving supported imported metadata. get_io_settings/set_io_settings expose only verified EXISTING imported IO scalar fields; wiring creation is unsupported. export_assembly uses explicit world origin when supplied, otherwise the single selected group's pivot or the mean placement position. import_assembly supports 2000 placements and preserves its requested position as group pivot. get_export_formats lists available GLB/FBX/OBJ and other model exporters; export_models uses bounded disposable copies and preserves source scene and selection.
10. import_map_prefabs appends ONLY prefab placements from .map, ignoring terrain/paths. export_map writes ONLY current placements floating in void, with no terrain/path layers. validate_map checks compositions, save_project writes .ruster. Destinations are absolute; existing files require overwrite=True. Source models and selection survive exports.
11. After timeout inspect the scene before replaying a mutation. No arbitrary Python execution, mesh edits, terrain tools, path tools or map generation are exposed.
"""

@mcp.resource('ruster://guide/building',mime_type='text/plain')
def building_guide()->str:
    return BUILDING_GUIDE


@mcp.prompt()
def build_rust_composition(description:str)->str:
    """Plan and build a custom Rust model from the local prefab library."""
    return BUILDING_GUIDE+'\nUser composition request: '+description+'\nDiscover suitable real assets, report any missing models, plan dimensions, build and visually inspect the composition, then validate. Do not claim server-tested compatibility.'


@mcp.prompt()
def audit_rust_composition()->str:
    """Inspect a prefab composition for concrete export and original-asset issues without changes."""
    return 'Read ruster://guide/building. Inspect status, paginate list_objects, inspect relevant original model details/world bounds and validate_map. Report concrete issues and names. Do not modify or overwrite files.'


@mcp.tool(annotations=READ)
def list_objects(limit:int=100,offset:int=0,query:str='',kind:str='',prefab_id:int|None=None,include_bounds:bool=False)->dict:
    """Page 1–200 placements/groups; bounds are opt-in. Filter names, kind PREFAB/GROUP or ID. Follow next_offset."""
    return command('list_objects',limit=limit,offset=offset,query=query,kind=kind,prefab_id=prefab_id,include_bounds=include_bounds)

@mcp.tool(annotations=READ)
def get_objects_info(names:list[str],include_bounds:bool=True)->dict:
    """Inspect 1–200 named roots in one request, with optional loaded model world bounds. Child names capped at 200."""
    return command('get_objects_info',names=names,include_bounds=include_bounds)

@mcp.tool(annotations=READ)
def get_prefabs_details(uids:list[int])->dict:
    """Read original cached dimensions and metadata for 1–20 real prefab IDs. Does not extract or scan game bundles."""
    return command('get_prefabs_details',uids=uids)

@mcp.tool(annotations=READ)
def get_selection(limit:int=100,offset:int=0)->dict:
    """Read active object and paginate selected prefab placements/groups; limit 1–200."""
    return command('get_selection',limit=limit,offset=offset)

@mcp.tool(annotations=EDIT)
def select_objects(names:list[str])->dict:
    """Select 1–200 independent whole placements/groups without changing transforms."""
    return command('select_objects',names=names)

@mcp.tool(annotations=EDIT)
def duplicate_objects(names:list[str],offset:list[float]|None=None)->dict:
    """Atomically copy roots/groups with world translation (default [2,0,0]). At most 2000 new placements. Preserves source selection."""
    return command('duplicate_objects',names=names,offset=offset if offset is not None else [2,0,0])

@mcp.tool(annotations=DESTRUCTIVE)
def delete_objects(names:list[str])->dict:
    """Validate then delete 1–200 independent roots/groups in one undo step. Rejects group and descendant targets together."""
    return command('delete_objects',names=names)

@mcp.tool(annotations=EDIT)
def array_objects(names:list[str],count:int,offset:list[float],rotation_degrees:list[float]|None=None)->dict:
    """Make count NEW copies. Each step adds world offset and XYZ rotation around roots' mean origin. Atomic; at most 2000 new placements/4000 hierarchy objects. Preserves source selection."""
    return command('array_objects',names=names,count=count,offset=offset,rotation_degrees=rotation_degrees if rotation_degrees is not None else [0,0,0])

@mcp.tool(annotations=EDIT)
def align_objects(names:list[str],axis:str='Z',mode:str='MIN',target:float|None=None)->dict:
    """Align loaded model world MIN/CENTER/MAX bounds on X/Y/Z. target is world coordinate; omitted uses first root's bound. Atomic with undo."""
    return command('align_objects',names=names,axis=axis,mode=mode,target=target)

@mcp.tool(annotations=EDIT)
def snap_objects_to_plane(names:list[str],target:float=0,axis:str='Z')->dict:
    """Place loaded model/group MIN bounds on world plane (default ground Z=0), accounting for rotations, scales and pivots. Atomic with undo."""
    return command('snap_objects_to_plane',names=names,target=target,axis=axis,mode='MIN')

@mcp.tool(annotations=READ)
def get_export_formats()->dict:
    """List model formats available in this runtime, placement interchange formats and bounded geometry budgets."""
    return command('get_export_formats')

@mcp.tool(annotations=DESTRUCTIVE)
def export_prefab(names:list[str],path:str,overwrite:bool=False)->dict:
    """Export native RustEdit .prefab preserving supported imported metadata. Absolute destination; overwrite=True replaces existing files. Preserves selection/source."""
    return command('export_prefab',names=names,path=path,overwrite=overwrite)

@mcp.tool(annotations=EDIT)
def import_prefab(path:str,position:list[float]|None=None)->dict:
    """Append native RustEdit .prefab at world position (default origin), preserving supported metadata. At most 2000 placements, validated first. Undo supported."""
    return command('import_prefab',path=path,position=position if position is not None else [0,0,0])

@mcp.tool(annotations=DESTRUCTIVE)
def export_models(names:list[str],path:str,format:str='GLB',overwrite:bool=False)->dict:
    """Export loaded original render geometry in a format from get_export_formats. Uses bounded disposable copies and preserves original scene/selection."""
    return command('export_models',names=names,path=path,format=format,overwrite=overwrite)

@mcp.tool(annotations=EDIT)
def import_map_prefabs(path:str)->dict:
    """Append ONLY prefab placements from absolute .map path; ignore terrain/paths. At most 2000 placements/256MiB. Preserves existing composition. Undo supported."""
    return command('import_map_prefabs',path=path)

class IOSettings(BaseModel):
    model_config=ConfigDict(extra='forbid')
    access_level:int|None=Field(default=None,ge=0,le=3)
    door_effect:int|None=Field(default=None,ge=-1,le=3)
    timer_length:float|None=Field(default=None,ge=0,le=86400)
    frequency:int|None=Field(default=None,ge=0,le=9999999)
    unlimited_ammo:bool|None=None
    peacekeeper:bool|None=None
    weapon:str|None=Field(default=None,max_length=256)
    branch_amount:int|None=Field(default=None,ge=0,le=2147483647)
    counter_target:int|None=Field(default=None,ge=0,le=2147483647)
    camera_identifier:str|None=Field(default=None,max_length=256)
    counter_passthrough:bool|None=None
    floors:int|None=Field(default=None,ge=1,le=100)
    phone_name:str|None=Field(default=None,max_length=256)

@mcp.tool(annotations=READ)
def get_io_settings(name:str)->dict:
    """Read verified existing RustEdit IO scalar fields on an imported placement. Wiring creation is unsupported."""
    return command('get_io_settings',name=name)

@mcp.tool(annotations=EDIT)
def set_io_settings(name:str,settings:IOSettings)->dict:
    """Update supplied verified EXISTING imported IO scalar fields; preserves other fields. One undo step; does not fabricate wiring."""
    return command('set_io_settings',name=name,settings=settings.model_dump(exclude_none=True))

def main():
    try:mcp.run(transport='stdio')
    finally:
        if _connection:_connection.disconnect()
