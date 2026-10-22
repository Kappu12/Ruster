"""Stdio MCP adapter for the bundled, authenticated community Blender bridge."""
import threading
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from .core import settings,mcp_config
from .vendor.blender_mcp_client import BlenderConnection

_connection=None
_lock=threading.Lock()
mcp=FastMCP('Ruster',instructions='Edit Rust maps using typed placement/terrain tools. Editor world metres: Z up; XYZ rotations in degrees. Prefab geometry is read-only. Open a map and enable MCP in Ruster Settings. Inspect the scene before retrying any timed-out mutation.')
READ=ToolAnnotations(readOnlyHint=True,destructiveHint=False,openWorldHint=False)
EDIT=ToolAnnotations(readOnlyHint=False,destructiveHint=False,openWorldHint=False)
DESTRUCTIVE=ToolAnnotations(readOnlyHint=False,destructiveHint=True,openWorldHint=False)


def command(kind,**params):
    global _connection
    with _lock:
        config=settings.load()
        if not mcp_config.enabled(config):raise ValueError('Enable MCP in Ruster Settings first')
        token=config.get('mcp_token','')
        if not isinstance(token,str) or len(token)<32:raise ValueError('Start MCP in Ruster Settings first')
        port=mcp_config.port(config)
        if _connection and (_connection.port!=port or _connection.token!=token):_connection.disconnect();_connection=None
        if _connection is None:_connection=BlenderConnection('127.0.0.1',port,token)
        return _connection.send_command(kind,params)


@mcp.tool(annotations=READ)
def get_scene_info()->dict:
    """Inspect active project mode, map size, prefab count and scene objects."""
    return command('get_scene_info')


@mcp.tool(annotations=READ)
def get_object_info(name:str)->dict:
    """Inspect world position, XYZ degree rotation and scale of an object."""
    return command('get_object_info',name=name)


@mcp.tool(annotations=READ)
def list_map_objects(limit:int=100,offset:int=0)->dict:
    """Page through placements, groups and paths; limit 1–200."""
    return command('list_map_objects',limit=limit,offset=offset)


@mcp.tool(annotations=READ)
def search_prefabs(query:str='',category:str='',limit:int=20,offset:int=0)->dict:
    """Search local Rust prefabs, returning IDs, asset paths and availability; limit 1–100."""
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


def main():
    try:mcp.run(transport='stdio')
    finally:
        if _connection:_connection.disconnect()
