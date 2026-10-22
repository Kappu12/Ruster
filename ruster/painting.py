"""Continuous, placement-only prefab painting with a whole-stroke undo boundary."""
import math
import random
import numpy as np
import bpy
from bpy.props import BoolProperty,EnumProperty,FloatProperty,IntProperty,PointerProperty,StringProperty
from mathutils import Quaternion,Vector
from . import scene,editing,placement
from .core import wire,prefabs,palettes,settings
from .assets import catalog
from .ui_style import ICONS as I,TOOL_ICONS

_classes=[]
_tool_registered=False
stroke_active=False


class RUSTER_PG_paint(bpy.types.PropertyGroup):
    palette:EnumProperty(name='Palette',items=[('SINGLE','Single Prefab','',I['prefab'],0),
        ('FAVORITES','Favorites','',I['favorite_on'],1),('SELECTED','Selected Prefab Types','',I['select_same'],2)])
    uid:StringProperty(name='Prefab ID')
    spacing:FloatProperty(name='Minimum Spacing',default=4,min=.5,max=1000,subtype='DISTANCE')
    seed:IntProperty(name='Random Seed',default=1,min=0,max=2147483000)
    min_scale:FloatProperty(name='Minimum Scale',default=1,min=.01,max=100)
    max_scale:FloatProperty(name='Maximum Scale',default=1,min=.01,max=100)
    random_yaw:BoolProperty(name='Random Rotation',default=True)
    align:BoolProperty(name='Align to Terrain',default=False)
    offset:FloatProperty(name='Height Offset',default=0,min=-500,max=500,subtype='DISTANCE')
    max_slope:FloatProperty(name='Maximum Slope',default=50,min=0,max=90)
    respect_holes:BoolProperty(name='Avoid Terrain Holes',default=True)


def palette_ids(context):
    brush=context.scene.ruster_paint
    if brush.palette=='SINGLE':
        try:ids=[int(brush.uid)]
        except ValueError:ids=[]
    elif brush.palette=='FAVORITES':ids=palettes.favorite_ids(settings.load())
    else:ids=sorted({int(o['ruster_uid']) for o in placement.selected_prefabs()})
    if len(ids)>512:raise ValueError('Use at most 512 different prefab types in one paint palette')
    if not ids:raise ValueError('Choose a prefab in the browser, add favorites, or select prefab placements first')
    ids=[uid for uid in ids if 0<=uid<=0xFFFFFFFF]
    available={uid for uid,_path,ready in catalog.search(scene.cache_dir(),limit=512,favorites=ids[:512]) if ready}
    ids=[uid for uid in ids if uid in available]
    if not ids:raise ValueError('This palette has no available local Rust assets; refresh the prefab catalog')
    return ids


class RUSTER_OT_prefab_stroke(bpy.types.Operator):
    bl_idname='ruster.prefab_stroke'
    bl_label='Paint Rust Prefabs'
    bl_options={'REGISTER','UNDO','BLOCKING'}
    @classmethod
    def poll(cls,context):
        return bool(context.scene and context.scene.ruster.mode=='MAP' and context.area and
            context.area.type=='VIEW_3D' and context.mode=='OBJECT')
    def invoke(self,context,event):
        global stroke_active
        self.created=[];self.handle=None;self.last=None;self.models={}
        self.previous=[o.name for o in context.selected_objects]
        try:
            brush=context.scene.ruster_paint
            if brush.min_scale>brush.max_scale:raise ValueError('Minimum scale must not exceed maximum scale')
            self.ids=palette_ids(context)
            self.rng=random.Random(brush.seed)
            self.document=editing.terrain()
            context.view_layer.update()
            self.spacing=prefabs.SpacingIndex(brush.spacing,[o.matrix_world.translation[:2] for o in scene.prefab_roots()])
            self.collection=bpy.data.collections.get('Prefabs') or scene.new_collection('Prefabs')
            self.stamp(context,event)
            self.handle=bpy.types.SpaceView3D.draw_handler_add(self.draw_cursor,(context,),'WINDOW','POST_VIEW')
            stroke_active=True
            context.window_manager.modal_handler_add(self)
            context.workspace.status_text_set('Paint prefabs: drag LMB · Esc: cancel stroke · Minimum spacing is between placement origins')
            return {'RUNNING_MODAL'}
        except Exception as error:
            self.cancel_stroke(context);self.report({'ERROR'},str(error));return {'CANCELLED'}
    def stamp(self,context,event):
        hit=editing.mouse_hit(context,event,self.document)
        if hit is None:return
        point=np.asarray(hit[:2],dtype=float)
        brush=context.scene.ruster_paint
        start=self.last if self.last is not None else point
        count=max(1,min(256,int(math.ceil(np.linalg.norm(point-start)/(brush.spacing*.5)))))
        for t in np.linspace(1/count,1,count):
            x,y=start+(point-start)*t
            if len(self.created)>=2000:break
            if not self.spacing.available((x,y)):continue
            sampled=prefabs.surface(self.document,x,y,brush.max_slope,brush.respect_holes)
            if sampled is None:continue
            height,normal=sampled
            uid=self.rng.choice(self.ids)
            fields=[wire.encode(1,2,b'Decor'),wire.encode(2,0,uid)]
            obj=scene.root_object(fields,self.collection)
            try:
                obj.location=(x,y,height+brush.offset)
                angle=self.rng.uniform(0,2*math.pi) if brush.random_yaw else 0.
                rotation=Quaternion((0,0,1),angle)
                if brush.align:rotation=Vector((0,0,1)).rotation_difference(Vector(normal))@rotation
                obj.rotation_euler=rotation.to_euler(obj.rotation_mode)
                factor=self.rng.uniform(brush.min_scale,brush.max_scale)
                obj.scale=(factor,factor,factor)
                model=self.models.get(uid)
                if model:
                    obj.instance_type='COLLECTION';obj.instance_collection=model
                    obj['ruster_visual']=True;obj.empty_display_type='PLAIN_AXES';obj.empty_display_size=.15
                    scene.name_prefab(obj,model.get('ruster_asset_name',obj.name))
                else:
                    scene.attach_visual(obj)
                    if obj.instance_collection:self.models[uid]=obj.instance_collection
            except Exception:
                bpy.data.objects.remove(obj,do_unlink=True);raise
            self.created.append(obj);self.spacing.add((x,y))
        self.last=point
        context.area.tag_redraw()
    def draw_cursor(self,context):
        if self.last is None:return
        import gpu
        from gpu_extras.batch import batch_for_shader
        angle=np.linspace(0,2*math.pi,65)
        radius=context.scene.ruster_paint.spacing*.5
        x=self.last[0]+np.cos(angle)*radius;y=self.last[1]+np.sin(angle)*radius
        positions=np.column_stack((x,y,self.document.sample_height(x,y)+.2))
        shader=gpu.shader.from_builtin('UNIFORM_COLOR')
        batch=batch_for_shader(shader,'LINE_STRIP',{'pos':positions})
        blend=gpu.state.blend_get();depth=gpu.state.depth_test_get()
        try:
            gpu.state.blend_set('ALPHA');gpu.state.depth_test_set('NONE')
            shader.bind();shader.uniform_float('color',(*context.preferences.themes[0].view_3d.object_active,1))
            batch.draw(shader)
        finally:gpu.state.blend_set(blend);gpu.state.depth_test_set(depth)
    def cleanup(self,context):
        global stroke_active
        stroke_active=False
        if self.handle:
            bpy.types.SpaceView3D.draw_handler_remove(self.handle,'WINDOW');self.handle=None
        context.workspace.status_text_set(None)
    def cancel_stroke(self,context):
        for obj in self.created:
            if obj.name in bpy.data.objects:bpy.data.objects.remove(obj,do_unlink=True)
        self.created=[]
        placement.select([bpy.data.objects[name] for name in self.previous if name in bpy.data.objects])
        self.cleanup(context)
    def modal(self,context,event):
        try:
            if event.type in {'ESC','RIGHTMOUSE'}:
                self.cancel_stroke(context);return {'CANCELLED'}
            if event.type=='MOUSEMOVE':self.stamp(context,event)
            if event.type=='LEFTMOUSE' and event.value=='RELEASE':
                placement.select(self.created)
                if self.created:
                    context.scene.ruster_paint.seed=(context.scene.ruster_paint.seed+1)%2147483000
                    from .app import request_assets
                    request_assets({int(o['ruster_uid']) for o in self.created if not o.get('ruster_visual')})
                if len(self.created)>=2000:self.report({'INFO'},'Placed 2,000 prefabs; release and start a new stroke to continue')
                self.cleanup(context)
                return {'FINISHED'} if self.created else {'CANCELLED'}
            return {'RUNNING_MODAL'}
        except Exception as error:
            self.cancel_stroke(context);self.report({'ERROR'},str(error));return {'CANCELLED'}


class RUSTER_WST_prefab(bpy.types.WorkSpaceTool):
    bl_space_type='VIEW_3D'
    bl_context_mode='OBJECT'
    bl_idname='ruster.prefab_brush'
    bl_label='Rust Prefab Paint'
    bl_description='Paint whole Rust prefabs onto terrain with spacing and randomized placement'
    bl_icon=TOOL_ICONS['prefab']
    bl_cursor='CROSSHAIR'
    bl_keymap=(('ruster.prefab_stroke',{'type':'LEFTMOUSE','value':'PRESS'},{}),)
    @staticmethod
    def draw_settings(context,layout,_tool):
        brush=context.scene.ruster_paint
        layout.prop(brush,'palette');layout.prop(brush,'spacing')


def register():
    global _tool_registered
    for cls in (RUSTER_PG_paint,RUSTER_OT_prefab_stroke):bpy.utils.register_class(cls);_classes.append(cls)
    bpy.types.Scene.ruster_paint=PointerProperty(type=RUSTER_PG_paint)
    if not bpy.app.background:
        bpy.utils.register_tool(RUSTER_WST_prefab,after={'ruster.terrain_brush'},separator=True,group=True)
        _tool_registered=True


def unregister():
    global _tool_registered,stroke_active
    stroke_active=False
    if _tool_registered:bpy.utils.unregister_tool(RUSTER_WST_prefab);_tool_registered=False
    del bpy.types.Scene.ruster_paint
    for cls in reversed(_classes):bpy.utils.unregister_class(cls)
    _classes.clear()
