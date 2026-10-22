"""Native Blender file selectors for full-resolution terrain layer masks."""
from pathlib import Path
import bpy
from bpy.props import EnumProperty,BoolProperty,StringProperty
from bpy_extras.io_utils import ImportHelper,ExportHelper
from . import editing
from .core import layer_images
from .core.terrain import SPLATS,BIOMES,TOPOLOGIES
from .ui_style import ICONS as I,properties,wrapped

_classes=[]
LAYER_ITEMS=[('splat','Ground Texture','',I['splat'],0),('biome','Biome','',I['biome'],1),
    ('topology','Topology','',I['topology'],2),('alpha','Terrain Holes','',I['alpha'],3)]
CHANNEL_ITEMS={
    'splat':[(str(i),name,'',i) for i,name in enumerate(SPLATS)],
    'biome':[(str(i),name,'',i) for i,name in enumerate(BIOMES)],
    'biome4':[(str(i),name,'',i) for i,name in enumerate(BIOMES[:4])],
    'topology':[(str(i),name,'',i) for i,name in enumerate((*TOPOLOGIES,'Bit 31 (Unknown)'))],
    'alpha':[('0','Solid Ground','White is solid ground; black cuts terrain holes',0)],
}


def channel_items(operator,context):
    key=operator.layer
    if key=='biome' and context and context.scene and context.scene.ruster.mode=='MAP':
        try:
            if editing.terrain().grid('biome').shape[0]==4:key='biome4'
        except (OSError,ValueError):pass
    return CHANNEL_ITEMS[key]


def layer_changed(operator,_context):operator.channel='0'


def preset_from_brush(operator,context):
    brush=context.scene.ruster_brush
    if brush.layer in layer_images.LAYERS:
        operator.layer=brush.layer
        channel=getattr(brush,brush.layer) if brush.layer!='alpha' else '0'
        operator.channel=channel if any(item[0]==channel for item in channel_items(operator,context)) else '0'


def mask_properties():
    return {'layer':EnumProperty(name='Layer',items=LAYER_ITEMS,update=layer_changed),
        'channel':EnumProperty(name='Channel',items=channel_items,default=0),
        'flip_y':BoolProperty(name='Flip Vertically',description='Reverse the image top-to-bottom map direction',default=False)}


class MaskOptions:
    @classmethod
    def poll(cls,context):
        from . import painting
        return bool(context.scene and context.scene.ruster.mode=='MAP' and context.mode=='OBJECT'
            and not editing.stroke_active and not painting.stroke_active)

    def defaults(self,context):
        if not self.properties.is_property_set('layer'):
            preset_from_brush(self,context)

    def draw(self,context):
        fields=properties(self.layout.column())
        fields.prop(self,'layer')
        if self.layer!='alpha':fields.prop(self,'channel')
        fields.prop(self,'flip_y')
        if self.layer in {'splat','biome'}:
            hint='Black is zero weight; white is full weight. Import sets this channel and balances the others to a total of 255.'
        elif self.layer=='topology':hint='White enables this topology; black clears it. Other topology bits stay unchanged.'
        else:hint='White is solid ground; black cuts terrain holes. Prefab models stay read-only.'
        wrapped(self.layout,context,hint,icon='info')
        wrapped(self.layout,context,'Top image row maps to +Y in the editor. Flip Vertically reverses this.')
        wrapped(self.layout,context,'Masks use the full layer resolution. Imported images resize to the existing layer.')


class RUSTER_OT_mask_import(MaskOptions,bpy.types.Operator,ImportHelper):
    bl_idname='ruster.mask_import'
    bl_label='Import Layer Mask'
    bl_description='Replace one full-resolution terrain layer channel from a grayscale PNG or TIFF'
    bl_options={'REGISTER','UNDO'}
    __annotations__=mask_properties()
    filter_glob:StringProperty(default='*.png;*.tif;*.tiff',options={'HIDDEN'})

    def invoke(self,context,event):
        self.defaults(context)
        return ImportHelper.invoke(self,context,event)

    def execute(self,context):
        try:
            document=editing.terrain(fresh=True)
            changed=layer_images.import_image(document,self.filepath,self.layer,int(self.channel),self.flip_y)
            if changed:editing.commit(document)
            self.report({'INFO'},'Layer mask imported' if changed else 'Layer mask already matches; no changes needed')
            return {'FINISHED'}
        except Exception as error:
            self.report({'ERROR'},str(error));return {'CANCELLED'}


class RUSTER_OT_mask_export(MaskOptions,bpy.types.Operator,ExportHelper):
    bl_idname='ruster.mask_export'
    bl_label='Export Layer Mask'
    bl_description='Export one full-resolution terrain layer channel as an 8-bit grayscale PNG'
    __annotations__=mask_properties()
    filename_ext='.png'
    filter_glob:StringProperty(default='*.png',options={'HIDDEN'})

    def invoke(self,context,event):
        self.defaults(context)
        if not self.filepath:
            label=next(label for identifier,label,_tip,_number in channel_items(self,context) if identifier==self.channel)
            self.filepath=f'{context.scene.ruster.title}-{self.layer}-{label}.png'
        return ExportHelper.invoke(self,context,event)

    def execute(self,context):
        try:
            layer_images.export_image(editing.terrain(),self.filepath,self.layer,int(self.channel),self.flip_y)
            self.report({'INFO'},f'Exported {Path(self.filepath).name}')
            return {'FINISHED'}
        except Exception as error:
            self.report({'ERROR'},str(error));return {'CANCELLED'}


def register():
    for cls in (RUSTER_OT_mask_import,RUSTER_OT_mask_export):bpy.utils.register_class(cls);_classes.append(cls)


def unregister():
    for cls in reversed(_classes):bpy.utils.unregister_class(cls)
    _classes.clear()
