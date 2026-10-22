"""Stdio MCP adapter for the bundled, authenticated community Blender bridge."""
import base64
import threading
from pydantic import BaseModel,Field,ConfigDict
from mcp.server.fastmcp import FastMCP,Image
from mcp.types import ToolAnnotations
from .core import settings,mcp_config
from .vendor.blender_mcp_client import BlenderConnection

_connection=None
_lock=threading.Lock()
mcp=FastMCP('Ruster',instructions='Build Rust maps and custom prefab compositions with original local game assets. First read ruster://guide/building and get_editor_status. Discover the complete catalog using list_prefab_categories and paginated search_prefabs (empty query browses everything; follow next_offset). Inspect dimensions with get_prefab_details; preload missing models with request_prefab_assets and poll status. Use sample_surface before placement, place_prefabs for atomic batches, group_objects for assemblies, and focus_view/get_viewport_image for visual feedback. Editor world metres: Z up; XYZ rotations in degrees. Geometry and materials are immutable; composition is the modeling workflow. Validate before export. Open a map and enable MCP in Ruster Settings. Inspect the scene before retrying a timed-out mutation.')
READ=ToolAnnotations(readOnlyHint=True,destructiveHint=False,openWorldHint=False)
EDIT=ToolAnnotations(readOnlyHint=False,destructiveHint=False,openWorldHint=False)
DESTRUCTIVE=ToolAnnotations(readOnlyHint=False,destructiveHint=True,openWorldHint=False)


def command(rpc_kind,**params):
    global _connection
    with _lock:
        config=settings.load()
        if not mcp_config.enabled(config):raise ValueError('Enable MCP in Ruster Settings first')
        token=config.get('mcp_token','')
        if not isinstance(token,str) or len(token)<32:raise ValueError('Start MCP in Ruster Settings first')
        port=mcp_config.port(config)
        if _connection and (_connection.port!=port or _connection.token!=token):_connection.disconnect();_connection=None
        if _connection is None:_connection=BlenderConnection('127.0.0.1',port,token)
        return _connection.send_command(rpc_kind,params)


@mcp.tool(annotations=READ)
def get_scene_info()->dict:
    """Inspect active project mode, map size, prefab count and scene objects."""
    return command('get_scene_info')


@mcp.tool(annotations=READ)
def get_object_info(name:str)->dict:
    """Inspect world position, XYZ degree rotation and scale of an object."""
    return command('get_object_info',name=name)


@mcp.tool(annotations=READ)
def list_map_objects(limit:int=100,offset:int=0,query:str='',kind:str='',prefab_id:int|None=None)->dict:
    """Page through placements, groups and paths with world bounds/hierarchy; limit 1–200. Filter by name substring, kind PREFAB/GROUP/PATH, or prefab ID. Follow next_offset."""
    return command('list_map_objects',limit=limit,offset=offset,query=query,kind=kind,prefab_id=prefab_id)


@mcp.tool(annotations=READ)
def search_prefabs(query:str='',category:str='',limit:int=20,offset:int=0)->dict:
    """Browse/search every indexed Rust prefab by path substring and optional category prefix. Empty query lists all. Returns IDs, paths, local availability, next_offset. Follow pages until next_offset=null; limit 1–100. Never invent prefab IDs."""
    return command('search_prefabs',query=query,category=category,limit=limit,offset=offset)


@mcp.tool(annotations=EDIT)
def place_prefab(uid:int,position:list[float],rotation_degrees:list[float]|None=None,scale:list[float]|None=None)->dict:
    """Place an available local prefab. Three-component world vectors: position/metres with Z height, rotation XYZ degrees, scale factors. Original model stays read-only."""
    return command('place_prefab',uid=uid,position=position,rotation_degrees=rotation_degrees,scale=scale)


@mcp.tool(annotations=EDIT)
def transform_object(name:str,position:list[float]|None=None,rotation_degrees:list[float]|None=None,scale:list[float]|None=None)->dict:
    """Set absolute world placement/group/path transforms. Rotations are XYZ degrees. Rejects group shear and zero scale; cannot change prefab meshes."""
    return command('transform_object',name=name,position=position,rotation_degrees=rotation_degrees,scale=scale)


@mcp.tool(annotations=EDIT)
def duplicate_object(name:str)->dict:
    """Duplicate a whole placement, group or path using native Ruster operations."""
    return command('duplicate_object',name=name)


@mcp.tool(annotations=DESTRUCTIVE)
def delete_object(name:str)->dict:
    """Delete a whole placement, group or path. Supports undo; never deletes model parts."""
    return command('delete_object',name=name)


@mcp.tool(annotations=EDIT)
def paint_terrain(layer:str,tool:str,x:float,y:float,radius:float,strength:float=.3,height:float=0.,channel:int=0,invert:bool=False)->dict:
    """Apply a full-resolution brush at editor X/Y. Layers: terrain/water/splat/biome/topology/alpha. Height tools: RAISE/LOWER/FLATTEN/SMOOTH/ERODE/SHARPEN/TERRACE/NOISE; PAINT for other layers. Inverted alpha cuts terrain holes only. Radius/metres; strength 0–1."""
    return command('paint_terrain',layer=layer,tool=tool,x=x,y=y,radius=radius,strength=strength,height=height,channel=channel,invert=invert)


@mcp.tool(annotations=READ)
def validate_map()->dict:
    """Report export errors and missing assets without exporting."""
    return command('validate_map')


@mcp.tool(annotations=DESTRUCTIVE)
def save_project(path:str,overwrite:bool=False)->dict:
    """Save to an absolute .ruster destination. Existing files require explicit overwrite=True."""
    return command('save_project',path=path,overwrite=overwrite)


@mcp.tool(annotations=DESTRUCTIVE)
def export_map(path:str,overwrite:bool=False)->dict:
    """Validate/export to an absolute .map destination; never overwrites the source. Existing files require explicit overwrite=True."""
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


class PathSettings(BaseModel):
    model_config=ConfigDict(extra='forbid')
    width:float|None=Field(default=None,ge=.1,le=500)
    inner_padding:float|None=Field(default=None,ge=0,le=500)
    outer_padding:float|None=Field(default=None,ge=0,le=500)
    inner_fade:float|None=Field(default=None,ge=0,le=500)
    outer_fade:float|None=Field(default=None,ge=0,le=500)
    random_scale:float|None=Field(default=None,ge=0,le=10)
    mesh_offset:float|None=Field(default=None,ge=-100,le=100)
    terrain_offset:float|None=Field(default=None,ge=-100,le=100)
    splat:int|None=Field(default=None,ge=0,le=4294967295)
    topology:int|None=Field(default=None,ge=0,le=4294967295)
    spline:bool|None=None
    start:bool|None=None
    end:bool|None=None


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
    """Atomically transform 1–200 placements/groups/paths in one undo step. Absolute world transforms. On error restores all transforms. Choose parent group OR descendants, not both."""
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
    """Name a placement/group/path for subsequent AI operations. Returns actual Blender name (uniqueness suffix may be added)."""
    return command('rename_object',name=name,new_name=new_name)


@mcp.tool(annotations=READ)
def sample_surface(positions:list[list[float]])->dict:
    """Sample terrain heights, normals and slopes at 1–200 world [x,y] positions. Use before placing compositions; height is Z. Samples outside the map are rejected."""
    return command('sample_surface',positions=positions)


@mcp.tool(annotations=EDIT)
def snap_objects_to_terrain(names:list[str],offset:float=0)->dict:
    """Set 1–200 placement/group/path world origins to terrain height plus offset metres. Preserves orientation/scale; no automatic mesh-bottom alignment. Atomic and undoable."""
    return command('snap_objects_to_terrain',names=names,offset=offset)


@mcp.tool(annotations=READ)
def get_path_info(name:str)->dict:
    """Inspect Road/River/Rail/Powerline world-space nodes and all Rust path settings."""
    return command('get_path_info',name=name)


@mcp.tool(annotations=EDIT)
def create_path(kind:str,nodes:list[list[float]],settings:PathSettings|None=None)->dict:
    """Create Road/River/Rail/Powerline from 2–4096 XYZ world nodes in metres. Configure width, padding, fades, masks and flags using typed settings. Undo supported."""
    return command('create_path',kind=kind,nodes=nodes,settings=settings.model_dump(exclude_none=True) if settings else {})


@mcp.tool(annotations=EDIT)
def update_path(name:str,nodes:list[list[float]]|None=None,settings:PathSettings|None=None)->dict:
    """Replace a path's world nodes and/or update typed Rust settings, preserving unknown source metadata. Undo supported."""
    return command('update_path',name=name,nodes=nodes,settings=settings.model_dump(exclude_none=True) if settings else {})


@mcp.tool(annotations=EDIT)
def focus_view(names:list[str],axis:str='CURRENT')->dict:
    """Select and frame placements/groups/paths in Blender's native viewport for visual inspection. Does not change geometry."""
    return command('focus_view',names=names,axis=axis)


@mcp.tool(annotations=READ)
def get_viewport_image()->Image:
    """Return a PNG image of the current 3D viewport for vision-capable AI. Focus the composition first. Requires the desktop app; renders the current viewport without altering models."""
    result=command('get_viewport_image')
    return Image(data=base64.b64decode(result['data']),format='png')


@mcp.tool(annotations=DESTRUCTIVE)
def export_assembly(names:list[str],path:str,overwrite:bool=False)->dict:
    """Export selected placements/groups as reusable .rusterprefab composition, using original prefab IDs. Absolute destination; existing file requires overwrite=True. Positions become relative to the composition center."""
    return command('export_assembly',names=names,path=path,overwrite=overwrite)


@mcp.tool(annotations=EDIT)
def import_assembly(path:str,position:list[float],name:str|None=None)->dict:
    """Load a .rusterprefab composition at a world XYZ origin, as an editable placement group. Uses only available local original prefabs; 1000-placement limit. Rolls back on failure; supports undo. Does not import arbitrary meshes."""
    return command('import_assembly',path=path,position=position,name=name)


BUILDING_GUIDE="""Ruster AI building workflow
1. Call get_editor_status. The desktop must have a Rust map open and MCP enabled. Wait for catalog/asset loading to finish.
2. list_prefab_categories discovers the catalog taxonomy. search_prefabs with empty query browses ALL indexed prefab IDs. Follow next_offset until null; use category and descriptive substrings to narrow results. Never guess IDs. Local availability is not proof an extracted model will render.
3. get_prefab_details provides cached model bounds and size in metres. request_prefab_assets preloads missing models; poll status then retry details. Do not repeatedly queue requests while busy.
4. sample_surface measures terrain height/normal/slope. World coordinates use X/Y horizontally and Z up, centered around zero; map bounds are +/- map_size/2. Rotations are XYZ Euler degrees. Scale is a nonzero factor, not metres.
5. Model with whole original Rust assets: place_prefabs accepts up to 100 typed placements and optional group_name. Use dimensions to plan walls/roofs/props and offsets. Native groups may be moved, rotated, duplicated and uniformly scaled. Geometry/materials cannot be edited, subdivided, boolean-cut or sculpted. Holes are terrain-only. Do not add arbitrary Blender meshes for Rust export.
6. list_map_objects pages every root with bounds, parent and child names; filters locate named parts/IDs. Use returned actual names in subsequent calls. transform_objects applies an atomic multi-object edit; group_objects makes an assembly. Do not target a group and its child in the same batch. snap_objects_to_terrain moves origins; use local bounds for bottom clearance.
7. focus_view followed by get_viewport_image supplies real visual feedback. Inspect and iterate; bounds are enclosing boxes, not collision meshes. sample_surface does not certify flatness/collision gameplay.
8. create_path/update_path edit typed Rust roads, rivers, rails, powerlines. paint_terrain changes map layers only. Read ruster://guide/terrain for brush conventions.
9. validate_map before export; fix errors, inspect notes. Save absolute .ruster paths; export_map .map and export_assembly .rusterprefab require explicit overwrite=True to replace a destination. Source map overwrites are prohibited. Exported groups flatten to original prefab records.
10. Each composition/transform batch is one native undo action. undo/redo also affect manual edits. After timeout, inspect the scene before retrying a mutation to avoid duplicates. No automatic retries of edits.
"""


@mcp.resource('ruster://guide/building',mime_type='text/plain')
def building_guide()->str:
    return BUILDING_GUIDE


@mcp.resource('ruster://guide/terrain',mime_type='text/plain')
def terrain_guide()->str:
    return 'Use sample_surface before placement. paint_terrain uses X/Y world metres, radius metres, strength 0..1. Height tools RAISE/LOWER/FLATTEN/SMOOTH/ERODE/SHARPEN/TERRACE/NOISE act on terrain or water. FLATTEN height is world Z metres. Other layers require PAINT: splat channels 0..7; biome channel layout depends on the source map; topology channel is a bit index; alpha invert=True cuts terrain holes only. Use get_editor_status for map bounds. Preserve original prefab geometry. Validate the final map before exporting.'


@mcp.prompt()
def build_rust_composition(description:str)->str:
    """Plan and build a custom Rust model from the local prefab library."""
    return BUILDING_GUIDE+'\nUser composition request: '+description+'\nDiscover suitable real assets, report any missing models, plan dimensions, build and visually inspect the composition, then validate. Do not claim server-tested compatibility.'


@mcp.prompt()
def audit_rust_map()->str:
    """Inspect an existing Rust map and propose evidence-based repairs."""
    return 'Read ruster://guide/building. Inspect editor status, paginate list_map_objects, sample relevant terrain, inspect suspicious object bounds, and call validate_map. Return concrete issues and affected object names. Do not modify or overwrite files during this audit.'


def main():
    try:mcp.run(transport='stdio')
    finally:
        if _connection:_connection.disconnect()
