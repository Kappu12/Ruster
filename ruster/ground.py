"""Optional native Rust ground beneath a prefab composition."""
from pathlib import Path
import math
import bpy
from bpy.props import EnumProperty, FloatProperty, IntProperty
from . import app, editing, scene
from .core import ground as data
from .core.terrain import BIOMES, SPLATS, TOPOLOGIES
from .core.project import atomic_write
from .ui_style import properties, wrapped, invoke_dialog

_classes=[]
READ={'get_ground_status'}
EDIT={'add_ground','paint_ground'}


def enabled(context_scene=None):
    state=(context_scene or bpy.context.scene).ruster
    return bool(state.native_ground and state.mode=='MAP')


def add(size=512.,height=0.,biome='Temperate',splat='Grass',world_size=1000):
    if enabled():raise ValueError('This composition already has Rust ground; paint its existing layers')
    world=data.flat_ground(size,height,biome,splat,world_size)
    data.validate_ground(world)
    source=app.session_dir()/'ground.map';atomic_write(source,world.write())
    state=bpy.context.scene.ruster
    old=(state.mode,state.map_size,state.source_map,state.terrain_state,state.native_ground,state.ground_size)
    before=set(bpy.context.scene.objects)
    try:
        state.mode='MAP';state.map_size=world_size;state.source_map=str(source)
        state.native_ground=True;state.ground_size=size;state.terrain_state=None
        editing.clear_cache()
        obj=scene.create_terrain(world)
        brush=bpy.context.scene.ruster_brush
        brush.display='splat';brush.layer='biome';brush.height=height
        brush.biome=str(BIOMES.index(biome));brush.splat=str(SPLATS.index(splat))
        editing.refresh()
        for item in bpy.context.scene.objects:
            if item.get('ruster_kind') in {'TERRAIN','WATER'}:item['ruster_ground_preview']=True
        return obj
    except Exception:
        for obj in set(bpy.context.scene.objects)-before:
            mesh=obj.data;bpy.data.objects.remove(obj,do_unlink=True)
            if isinstance(mesh,bpy.types.Mesh) and not mesh.users:bpy.data.meshes.remove(mesh)
        state.mode,state.map_size,state.source_map,state.terrain_state,state.native_ground,state.ground_size=old
        editing.clear_cache();raise


def status():
    if not enabled():return {'present':False,'coordinates':'World XYZ metres, Z up'}
    doc=editing.terrain()
    from . import live_preview
    return {'present':True,'size':bpy.context.scene.ruster.ground_size,'world_size':doc.size,
        'height_resolution':doc.grid('terrain').shape[-1],
        'paint_resolution':doc.grid('alpha').shape[-1],
        'biome_channels_stored':len(doc.grid('biome')),'biomes':list(BIOMES),'splats':list(SPLATS),
        'native_terrain':True,'preview_requires_restart':live_preview.ground_changed(),
        'coordinates':'World XYZ metres, Z up'}


def paint(layer,center,radius,channel=0,strength=.5,falloff=.6,shape='CIRCLE',tool='PAINT',height=0.,invert=False):
    if not enabled():raise ValueError('Add Rust ground before painting')
    if layer not in {'terrain','water','splat','biome','topology','alpha'}:raise ValueError('Unsupported ground layer')
    if not isinstance(center,(list,tuple)) or len(center)!=2 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in center):
        raise ValueError('Brush centre must contain two finite world coordinates')
    for value,low,high,label in ((radius,.1,2000,'Radius'),(strength,0,1,'Strength'),(falloff,0,1,'Falloff'),(height,-500,500,'Height')):
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not low<=value<=high:raise ValueError(f'{label} is out of range')
    if shape not in {'CIRCLE','SQUARE'} or type(invert)!=bool:raise ValueError('Invalid brush shape or invert flag')
    if tool not in {'PAINT','RAISE','LOWER','FLATTEN','SMOOTH'}:raise ValueError('Unsupported ground brush tool')
    choices={'biome':BIOMES,'splat':SPLATS,'topology':TOPOLOGIES}.get(layer)
    if choices and isinstance(channel,str):
        if channel not in choices:raise ValueError('Unknown paint channel')
        channel=choices.index(channel)
    if type(channel)!=int or channel<0 or (choices and channel>=len(choices)):raise ValueError('Invalid paint channel')
    if layer in {'terrain','water'} and tool=='PAINT':raise ValueError('Choose a height brush tool')
    doc=editing.terrain(fresh=True)
    changed=doc.brush(tool if layer in {'terrain','water'} else 'PAINT',*center,radius,
        layer=layer,channel=channel,strength=strength,falloff=falloff,shape=shape,height=height,invert=invert)
    if changed:editing.commit(doc)
    return {'changed':changed,**status()}


def validate():
    from .map_prefabs import _validated_records
    errors,notes,_=_validated_records()
    try:data.validate_ground(editing.terrain().export_world())
    except (OSError,ValueError) as error:errors.append(str(error))
    return errors,notes+['Native Rust terrain, biome, splat, alpha and topology layers included']


def export_map(path, *, overwrite=True):
    from .map_prefabs import _validated_records
    errors,notes,records=_validated_records()
    if errors:raise ValueError('; '.join(errors[:5]))
    world=data.native_world(editing.terrain().export_world())
    world.replace_prefabs(records)
    path=Path(path)
    if path.resolve()==Path(bpy.context.scene.ruster.source_map).resolve():raise ValueError('Export to a new map filename')
    atomic_write(path,world.write(),overwrite=overwrite)
    return path


def dispatch(server,kind,p,bridge):
    from .mcp_session import checked_params
    if kind=='get_ground_status':checked_params(p,());return status()
    bridge.require_idle();bridge.require_editor()
    if kind=='add_ground':
        checked_params(p,('size','height','biome','splat','world_size'))
        add(**p);result=status()
    elif kind=='paint_ground':
        checked_params(p,('layer','center','radius','channel','strength','falloff','shape','tool','height','invert'))
        result=paint(**p)
    else:raise ValueError('Unsupported ground command')
    if bpy.context.preferences.edit.use_global_undo:bpy.ops.ed.undo_push(message='MCP: '+kind.replace('_',' ').title())
    app.redraw();return result


class RUSTER_OT_add_ground(bpy.types.Operator):
    bl_idname='ruster.add_ground'
    bl_label='Add Rust Ground'
    bl_description='Add flat native Rust terrain below the composition, preserving prefab placements'
    bl_options={'REGISTER','UNDO'}
    size:FloatProperty(name='Ground Width',default=512,min=16,max=2000,subtype='DISTANCE')
    height:FloatProperty(name='Ground Height',default=0,min=-500,max=500,subtype='DISTANCE')
    world_size:IntProperty(name='World Size',default=1000,min=1000,max=2000)
    biome:EnumProperty(name='Biome',items=[(x,x,'') for x in BIOMES],default='Temperate')
    splat:EnumProperty(name='Ground Texture',items=[(x,x,'') for x in SPLATS],default='Grass')
    @classmethod
    def poll(cls,context):return bool(context.scene and not enabled(context.scene))
    def invoke(self,context,event):return invoke_dialog(self,context,event,width=380)
    def draw(self,context):
        fields=properties(self.layout.column())
        for name in ('size','height','world_size','biome','splat'):fields.prop(self,name)
    def execute(self,context):
        try:add(self.size,self.height,self.biome,self.splat,self.world_size);return {'FINISHED'}
        except Exception as error:self.report({'ERROR'},str(error));return {'CANCELLED'}


class RUSTER_PT_ground(bpy.types.Panel):
    bl_label='Rust Ground'
    bl_space_type='VIEW_3D';bl_region_type='UI';bl_category='Rustmatics'
    def draw(self,context):
        layout=self.layout
        if not enabled():layout.operator('ruster.add_ground',icon='MESH_PLANE');return
        layout.label(text=f'{context.scene.ruster.ground_size:g} m ground')
        layout.operator('ruster.export_map',text='Export Ground and Prefabs…',icon='EXPORT')
        brush=context.scene.ruster_brush;fields=properties(layout.column())
        fields.prop(brush,'layer')
        if brush.layer in {'terrain','water'}:
            fields.prop(brush,'tool');fields.prop(brush,'height')
        elif brush.layer=='splat':fields.prop(brush,'splat')
        elif brush.layer=='biome':fields.prop(brush,'biome')
        elif brush.layer=='topology':fields.prop(brush,'topology')
        for prop in ('radius','strength','falloff','shape','remove'):fields.prop(brush,prop)
        layout.operator('wm.tool_set_by_id',text='Brush Ground in Viewport',icon='BRUSH_DATA').name='ruster.terrain_brush'
        layout.operator('ruster.terrain_apply')
        fields.prop(brush,'display');layout.operator('ruster.terrain_overlay',text='Refresh Ground View')
        wrapped(layout,context,'Ground brushes are saved in the map. Restart Live Preview after editing terrain layers.')


def register():
    for cls in (RUSTER_OT_add_ground,RUSTER_PT_ground):bpy.utils.register_class(cls);_classes.append(cls)


def unregister():
    for cls in reversed(_classes):bpy.utils.unregister_class(cls)
    _classes.clear()
