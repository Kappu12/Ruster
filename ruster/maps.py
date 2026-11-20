"""Native Image Editor workspace for authoritative Rust map-layer previews."""
from pathlib import Path
import bpy
from bpy.props import EnumProperty,PointerProperty,StringProperty
from . import editing
from .core import map_images
from .core.terrain import SPLATS,BIOMES,TOPOLOGIES
from .ui_style import ICONS as I,properties,wrapped

_classes=[]
_keys={}
CHANNELS={
    'splat':[('-1','Composite','Weighted ground colors',0)]+[(str(i),n,'',i+1) for i,n in enumerate(SPLATS)],
    'biome':[('-1','Composite','Weighted biome colors',0)]+[(str(i),n,'',i+1) for i,n in enumerate(BIOMES)],
    'biome4':[('-1','Composite','Weighted biome colors',0)]+[(str(i),n,'',i+1) for i,n in enumerate(BIOMES[:4])],
    'topology':[('-1','All Topology','All active bits in distinct colors',0)]+[(str(i),n,'',i+1) for i,n in enumerate((*TOPOLOGIES,'Bit 31 (Unknown)'))],
    'single':[('-1','Full Map','',0)],
}


def channels(state,context):
    key=state.layer
    if key=='biome' and context and context.scene.ruster.mode=='MAP':
        try:
            if editing.terrain().grid('biome').shape[0]==4:key='biome4'
        except (OSError,ValueError):pass
    return CHANNELS.get(key,CHANNELS['single'])


def changed(state,_context):state.channel='-1';_keys.clear()


class RUSTER_PG_maps(bpy.types.PropertyGroup):
    layer:EnumProperty(name='Map',items=[(key,label,'',i) for i,(key,label) in enumerate([
        ('terrain','Heightmap'),('splat','Splat Map'),('biome','Biome Map'),('topology','Topology Map'),
        ('alpha','Terrain Holes'),('water','Water Height'),('height','Spawn Height'),('slope','Slope Map')])],update=changed)
    channel:EnumProperty(name='Channel',items=channels,default=0)
    resolution:EnumProperty(name='Preview Detail',items=[('512','512',''),('1024','1024',''),('2048','2048','')],default='1024')
    status:StringProperty(options={'SKIP_SAVE'})


def is_maps(context):return bool(context.workspace and context.workspace.get('ruster_workspace')=='MAPS')


def ensure_workspace():
    if any(w.get('ruster_workspace')=='MAPS' for w in bpy.data.workspaces):return
    window=next((w for w in bpy.context.window_manager.windows if any(a.type=='VIEW_3D' for a in w.screen.areas)),None)
    if not window:return
    previous=window.workspace
    with bpy.context.temp_override(window=window):
        previous['ruster_workspace']='3D'
        existing={w.as_pointer() for w in bpy.data.workspaces}
        bpy.ops.workspace.duplicate()
        workspace=next(w for w in bpy.data.workspaces if w.as_pointer() not in existing)
        workspace.name='Maps';workspace['ruster_workspace']='MAPS'
        window.workspace=previous


def update_image(context,force=False):
    if context.scene.ruster.mode!='MAP':raise ValueError('Open or create a Rust map first')
    state=context.scene.ruster_maps
    source=Path(context.scene.ruster.source_map).stat()
    key=(context.scene.as_pointer(),context.scene.ruster.source_map,source.st_mtime_ns,source.st_size,
        context.scene.ruster.terrain_state.as_pointer() if context.scene.ruster.terrain_state else 0,state.layer,state.channel,state.resolution)
    stored=_keys.get(context.scene.as_pointer())
    image=bpy.data.images.get(stored[1]) if stored else None
    if force or not stored or stored[0]!=key or not image:
        pixels,meta=map_images.preview(editing.terrain(),state.layer,int(state.channel),int(state.resolution))
        size=meta['preview_resolution']
        image_name=f'Rustmatics Map Preview: {context.scene.name}:{size}'
        image=bpy.data.images.get(image_name)
        if image and not image.get('ruster_map_preview'):raise ValueError('An unrelated image uses the map preview name; rename it first')
        if image is None:image=bpy.data.images.new(image_name,width=size,height=size,alpha=True)
        image['ruster_map_preview']=True;image.colorspace_settings.name='Non-Color';image.use_view_as_render=False
        image.pixels.foreach_set(pixels.ravel());image.update()
        state.status=f"{meta['source_resolution']} × {meta['source_resolution']} source · {size} × {size} preview · North = +Y"
        _keys[context.scene.as_pointer()]=(key,image.name)
    if context.area and context.area.type=='IMAGE_EDITOR':
        first=context.space_data.image!=image;context.space_data.image=image
        if first and not bpy.app.background:
            region=next((r for r in context.area.regions if r.type=='WINDOW'),None)
            if region:
                with bpy.context.temp_override(region=region):bpy.ops.image.view_all(fit_view=True)
    return image


def poll_views():
    from . import painting
    if editing.stroke_active or painting.stroke_active:return .3
    for window in list(bpy.context.window_manager.windows):
        if window.workspace.get('ruster_workspace')!='MAPS' or window.scene.ruster.mode!='MAP':continue
        if not any(a.type=='IMAGE_EDITOR' for a in window.screen.areas):
            candidates=[a for a in window.screen.areas if a.type=='VIEW_3D']
            if candidates:
                area=max(candidates,key=lambda a:a.width*a.height)
                with bpy.context.temp_override(window=window,area=area):area.type='IMAGE_EDITOR'
        for area in window.screen.areas:
            if area.type=='IMAGE_EDITOR' and area.spaces.active.type=='IMAGE_EDITOR':
                try:
                    area.spaces.active.mode='VIEW';area.spaces.active.show_region_ui=True
                    with bpy.context.temp_override(window=window,area=area):update_image(bpy.context)
                except Exception as error:
                    area.spaces.active.image=None;window.scene.ruster_maps.status=str(error)
    return .5


class RUSTER_OT_map_view(bpy.types.Operator):
    bl_idname='ruster.map_view'
    bl_label='Open Map View'
    view:EnumProperty(items=[('3D','3D Map',''),('MAPS','Maps','')])
    def execute(self,context):
        if context.scene.ruster.mode!='MAP':return {'CANCELLED'}
        ensure_workspace()
        target=next((w for w in bpy.data.workspaces if w.get('ruster_workspace')==self.view),None)
        if not target:self.report({'ERROR'},'Map workspace is unavailable');return {'CANCELLED'}
        context.window.workspace=target
        return {'FINISHED'}


class RUSTER_OT_map_refresh(bpy.types.Operator):
    bl_idname='ruster.map_refresh'
    bl_label='Refresh Map View'
    def execute(self,context):
        try:update_image(context,True);return {'FINISHED'}
        except Exception as error:self.report({'ERROR'},str(error));return {'CANCELLED'}


class RUSTER_PT_maps(bpy.types.Panel):
    bl_label='Rust Maps'
    bl_space_type='IMAGE_EDITOR'
    bl_region_type='UI'
    bl_category='Rustmatics'
    @classmethod
    def poll(cls,context):return is_maps(context) and context.scene.ruster.mode=='MAP'
    def draw(self,context):
        state=context.scene.ruster_maps;fields=properties(self.layout.column())
        fields.prop(state,'layer')
        if state.layer in {'splat','biome','topology'}:fields.prop(state,'channel')
        fields.prop(state,'resolution')
        self.layout.operator('ruster.map_refresh',icon=I['refresh'])
        self.layout.operator('image.view_all',text='Frame Map',icon=I['search'])
        wrapped(self.layout,context,state.status)
        wrapped(self.layout,context,'Read-only map preview. Edit terrain in 3D or import a layer mask. Views refresh after edits and undo.',icon='info')
        if state.layer in {'splat','biome'} and state.channel=='-1':
            names=SPLATS if state.layer=='splat' else BIOMES
            colors=map_images.SPLAT_COLORS if state.layer=='splat' else map_images.BIOME_COLORS
            for name,color in zip(names,colors):
                row=self.layout.row(align=True);row.template_node_socket(color=(*color,1));row.label(text=name)
        if state.layer in {'terrain','water','height'}:wrapped(self.layout,context,'Black = −500 m. White = +500 m.')
        elif state.layer=='alpha':wrapped(self.layout,context,'White = solid terrain. Black = holes.')


def header(self,context):
    if not is_maps(context) or context.scene.ruster.mode!='MAP':return
    row=self.layout.row(align=True);row.prop(context.scene.ruster_maps,'layer',text='')
    if context.scene.ruster_maps.layer in {'splat','biome','topology'}:row.prop(context.scene.ruster_maps,'channel',text='')
    row.operator('ruster.map_refresh',text='',icon=I['refresh'])


def register():
    for cls in (RUSTER_PG_maps,RUSTER_OT_map_view,RUSTER_OT_map_refresh,RUSTER_PT_maps):bpy.utils.register_class(cls);_classes.append(cls)
    bpy.types.Scene.ruster_maps=PointerProperty(type=RUSTER_PG_maps)
    bpy.types.IMAGE_HT_header.append(header)
    if not bpy.app.background:bpy.app.timers.register(poll_views,first_interval=.5,persistent=True)


def unregister():
    if bpy.app.timers.is_registered(poll_views):bpy.app.timers.unregister(poll_views)
    bpy.types.IMAGE_HT_header.remove(header)
    del bpy.types.Scene.ruster_maps
    for cls in reversed(_classes):bpy.utils.unregister_class(cls)
    _classes.clear();_keys.clear()
