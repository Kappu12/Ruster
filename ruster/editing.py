"""Terrain state, native brush tool, path authoring and map construction.

Immutable Text datablocks hold full-resolution edit snapshots. The scene points
at the active snapshot, so Blender undo/redo and .blend/.ruster saving retain the
same authoritative data as the viewport. The reduced mesh is always a preview.
"""
import base64
import hashlib
import math
from pathlib import Path
import time
import uuid

import bpy
import numpy as np
from bpy.app.handlers import persistent
from bpy.props import (BoolProperty,EnumProperty,FloatProperty,IntProperty,
                       StringProperty,FloatVectorProperty)
from bpy_extras import view3d_utils
from bpy_extras.io_utils import ImportHelper,ExportHelper
from mathutils import Vector
from . import scene
from .core import paths,wire
from .core.terrain import Terrain,empty_world,SPLATS,BIOMES,TOPOLOGIES,resample
from .core.rust_map import RustMap
from .core.project import atomic_write

_cache = {}
_classes = []
_tool_registered = False
stroke_active = False


class RUSTER_PG_brush(bpy.types.PropertyGroup):
    layer: EnumProperty(name='Layer',items=[('terrain','Terrain Height',''),('water','Water Height',''),
        ('splat','Ground Texture',''),('biome','Biome',''),('topology','Topology',''),('alpha','Terrain Holes','')])
    tool: EnumProperty(name='Tool',items=[(x,x.title(),'') for x in
        ('RAISE','LOWER','FLATTEN','SMOOTH','ERODE','SHARPEN','TERRACE','NOISE','CLONE','PINCH','TWIST','SLOPE','STAMP')])
    radius: FloatProperty(name='Radius',default=30,min=.1,max=3000,subtype='DISTANCE')
    strength: FloatProperty(name='Strength',default=.35,min=0,max=1,subtype='FACTOR')
    height: FloatProperty(name='Height',default=20,min=-500,max=500,subtype='DISTANCE')
    terrace: FloatProperty(name='Terrace Step',default=5,min=.1,max=500)
    falloff: FloatProperty(name='Falloff',default=.6,min=0,max=1,subtype='FACTOR')
    shape: EnumProperty(name='Shape',items=[('CIRCLE','Circle',''),('SQUARE','Square','')])
    splat: EnumProperty(name='Texture',items=[(str(i),n,'') for i,n in enumerate(SPLATS)],default='4')
    biome: EnumProperty(name='Biome',items=[(str(i),n,'') for i,n in enumerate(BIOMES)],default='1')
    topology: EnumProperty(name='Topology',items=[(str(i),n,'') for i,n in enumerate(TOPOLOGIES)])
    remove: BoolProperty(name='Remove / Cut Hole',default=False)
    use_mask: BoolProperty(name='Limit by Height / Slope')
    minimum: FloatProperty(name='Minimum Height',default=-500,min=-500,max=500)
    maximum: FloatProperty(name='Maximum Height',default=500,min=-500,max=500)
    min_slope: FloatProperty(name='Minimum Slope',default=0,min=0,max=90)
    max_slope: FloatProperty(name='Maximum Slope',default=90,min=0,max=90)
    seed: IntProperty(name='Seed',default=1)
    source: FloatVectorProperty(name='Clone Source',size=3)
    source_set: BoolProperty(default=False)
    stamp_path:StringProperty(name='Stamp Image',subtype='FILE_PATH')
    rotation:FloatProperty(name='Heading (degrees)',default=0,min=-360,max=360)
    slope:FloatProperty(name='Slope (degrees)',default=15,min=-85,max=85)
    bridge_start:FloatVectorProperty(size=3)
    bridge_set:BoolProperty(default=False)
    display: EnumProperty(name='Overlay',items=[('splat','Ground Textures',''),('biome','Biomes',''),
        ('topology','Selected Topology',''),('alpha','Terrain Holes','')],default='splat')


class RUSTER_PG_path(bpy.types.PropertyGroup):
    enabled: BoolProperty(default=False)
    kind: EnumProperty(name='Path Type',items=[(n,n,'') for n in ('Road','River','Rail','Powerline')])
    width: FloatProperty(name='Width',default=8,min=.1,max=500)
    inner_padding: FloatProperty(name='Inner Padding',default=1,min=0,max=500)
    outer_padding: FloatProperty(name='Outer Padding',default=1,min=0,max=500)
    inner_fade: FloatProperty(name='Inner Fade',default=1,min=0,max=500)
    outer_fade: FloatProperty(name='Outer Fade',default=1,min=0,max=500)
    random_scale: FloatProperty(name='Random Scale',default=0,min=0,max=10)
    mesh_offset: FloatProperty(name='Mesh Offset',default=0,min=-100,max=100)
    terrain_offset: FloatProperty(name='Terrain Offset',default=0,min=-100,max=100)
    spline: BoolProperty(name='Spline',default=False)
    start: BoolProperty(name='Start Connection',default=False)
    end: BoolProperty(name='End Connection',default=False)
    splat: IntProperty(name='Splat Mask',default=0,min=0)
    topology: IntProperty(name='Topology Mask',default=0,min=0)


def clear_cache():
    _cache.clear()


def terrain(context_scene=None,fresh=False):
    state=(context_scene or bpy.context.scene).ruster
    if state.mode!='MAP' or not state.source_map:
        raise ValueError('Open or create a Rust map first')
    path=Path(state.source_map)
    stat=path.stat()
    snapshot=state.terrain_state
    key=(str(path),stat.st_mtime_ns,stat.st_size,snapshot.name if snapshot else '')
    if fresh or key not in _cache:
        world=RustMap.load(path)
        document=Terrain.restore(world,snapshot.as_string()) if snapshot else Terrain(world)
        if fresh:
            return document
        if len(_cache)>2:
            _cache.clear()
        _cache[key]=document
    return _cache[key]


def commit(document):
    snapshot=bpy.data.texts.new('Ruster Terrain '+uuid.uuid4().hex[:12])
    snapshot.write(document.snapshot())
    bpy.context.scene.ruster.terrain_state=snapshot
    clear_cache()
    refresh(document)


def refresh(document=None,holes=True,water=True):
    document=document or terrain()
    obj=next((o for o in bpy.context.scene.objects if o.get('ruster_kind')=='TERRAIN'),None)
    if not obj:
        return
    # Coordinates in the mesh remain fixed; update only samples on its regular grid.
    count=len(obj.data.vertices)
    coordinates=np.empty(count*3,dtype=np.float32)
    obj.data.vertices.foreach_get('co',coordinates)
    coordinates=coordinates.reshape(-1,3)
    coordinates[:,2]=document.sample_height(coordinates[:,0],coordinates[:,1])
    obj.data.vertices.foreach_set('co',coordinates.ravel())
    if holes:
        try:
            alpha=document.grid('alpha')[0]
            m=math.isqrt(count)
            if m*m==count:
                centres=(coordinates.reshape(m,m,3)[:-1,:-1,:2]+coordinates.reshape(m,m,3)[1:,1:,:2])/2
                px=np.clip(np.rint((centres[...,0]/document.size+.5)*(alpha.shape[1]-1)).astype(int),0,alpha.shape[1]-1)
                pz=np.clip(np.rint((centres[...,1]/document.size+.5)*(alpha.shape[0]-1)).astype(int),0,alpha.shape[0]-1)
                visible=alpha[pz,px]>0
                token=hashlib.sha256(visible.tobytes()).hexdigest()
                if obj.get('ruster_alpha_preview')!=token:
                    faces=[(z*m+x,z*m+x+1,(z+1)*m+x+1,(z+1)*m+x)
                           for z in range(m-1) for x in range(m-1) if visible[z,x]]
                    obj.data.clear_geometry()
                    obj.data.from_pydata(coordinates.tolist(),[],faces)
                    obj['ruster_alpha_preview']=token
        except ValueError:
            pass
    overlay=bpy.context.scene.ruster_brush.display
    try:
        grid=document.grid(overlay)
        n=grid.shape[-1]
        ix=np.clip(np.rint((coordinates[:,0]/document.size+.5)*(n-1)).astype(int),0,n-1)
        iz=np.clip(np.rint((coordinates[:,1]/document.size+.5)*(n-1)).astype(int),0,n-1)
        values=grid[:,iz,ix]
        if overlay=='splat':
            palette=np.array([(0.34,.24,.15),(.85,.89,.93),(.65,.55,.32),(.29,.30,.29),
                              (.22,.35,.12),(.11,.22,.08),(.4,.39,.35),(.37,.34,.29)])
            colors=values.T/255@palette
        elif overlay=='biome':
            palette=np.array([(.72,.45,.18),(.2,.5,.14),(.54,.5,.3),(.86,.92,1.),(.07,.24,.12)])
            colors=values.T/255@palette[:grid.shape[0]]
        else:
            active=(values[0]&(1<<int(bpy.context.scene.ruster_brush.topology))!=0) if overlay=='topology' else values[0]>0
            colors=np.where(active[:,None],np.array([.2,.7,.25]),np.array([.55,.12,.12]))
        colors=np.column_stack((colors,np.ones(count)))
        attr=obj.data.color_attributes.get('RustGround') or obj.data.color_attributes.new(name='RustGround',type='FLOAT_COLOR',domain='POINT')
        attr.data.foreach_set('color',colors.ravel())
        mat=scene.material('Rust ground preview',(.3,.4,.2,1))
        mat.use_nodes=True
        node=mat.node_tree.nodes.get('RustGround') or mat.node_tree.nodes.new('ShaderNodeVertexColor')
        node.name='RustGround';node.layer_name='RustGround'
        mat.node_tree.links.new(node.outputs['Color'],mat.node_tree.nodes.get('Principled BSDF').inputs['Base Color'])
        if not obj.data.materials or obj.data.materials[0]!=mat:
            obj.data.materials.clear();obj.data.materials.append(mat)
    except ValueError:
        pass
    obj.data.update()
    if water:
        refresh_water(document)
    from .app import redraw
    redraw()


def refresh_water(document):
    try:
        grid=document.grid('water')[0]
    except ValueError:
        return
    n=grid.shape[0]
    indices=np.unique(np.linspace(0,n-1,min(n,129),dtype=int))
    pos=indices/(n-1)*document.size-document.size/2
    xx,yy=np.meshgrid(pos,pos)
    heights=grid[np.ix_(indices,indices)]/32766*1000-500
    visible=heights>document.sample_height(xx,yy)+.05
    m=len(indices)
    vertices=np.column_stack((xx.ravel(),yy.ravel(),heights.ravel()))
    faces=[(z*m+x,z*m+x+1,(z+1)*m+x+1,(z+1)*m+x)
           for z in range(m-1) for x in range(m-1) if visible[z:z+2,x:x+2].any()]
    obj=next((o for o in bpy.context.scene.objects if o.get('ruster_kind')=='WATER'),None)
    if obj is None:
        obj=bpy.data.objects.new('Water',bpy.data.meshes.new('Water'))
        (bpy.data.collections.get('Terrain') or scene.new_collection('Terrain')).objects.link(obj)
        obj['ruster_kind']='WATER';obj.hide_select=True
        obj.data.materials.append(scene.material('Rust Water',(.08,.28,.4,1)))
    obj.data.clear_geometry()
    obj.data.from_pydata(vertices.tolist(),[],faces)
    obj.data.update()


def brush_at(document,x,y,invert=False,smooth=False):
    brush=bpy.context.scene.ruster_brush
    if brush.use_mask and (brush.minimum>brush.maximum or brush.min_slope>brush.max_slope):
        raise ValueError('The mask minimum must not exceed its maximum')
    layer=brush.layer
    channel=int(brush.splat if layer=='splat' else brush.biome if layer=='biome' else brush.topology if layer=='topology' else '0')
    stamp=None
    if brush.tool=='STAMP' and layer in ('terrain','water'):
        if not hasattr(document,'_stamp_image'):
            from PIL import Image
            with Image.open(bpy.path.abspath(brush.stamp_path)) as image:
                if image.width>4096 or image.height>4096:
                    image.thumbnail((4096,4096))
                stamp=np.asarray(image)
                if stamp.ndim!=2:raise ValueError('Use a grayscale stamp image')
                maximum=65535 if stamp.dtype.itemsize>1 else 255
                document._stamp_image=np.clip(stamp.astype(float)/maximum,0,1)
        stamp=document._stamp_image
    return document.brush('SMOOTH' if smooth and layer in ('terrain','water') else brush.tool,
        x,y,brush.radius,strength=brush.strength,height=brush.height,channel=channel,
        layer=layer,falloff=brush.falloff,shape=brush.shape,invert=(invert!=brush.remove),
        minimum=brush.minimum if brush.use_mask else -500,
        maximum=brush.maximum if brush.use_mask else 500,
        min_slope=brush.min_slope if brush.use_mask else 0,
        max_slope=brush.max_slope if brush.use_mask else 90,
        seed=brush.seed,source=brush.source[:2] if brush.source_set else None,terrace=brush.terrace,
        stamp=stamp,rotation=brush.rotation,slope=brush.slope)


def mouse_hit(context,event,document=None):
    coordinate=(event.mouse_region_x,event.mouse_region_y)
    origin=view3d_utils.region_2d_to_origin_3d(context.region,context.region_data,coordinate)
    direction=view3d_utils.region_2d_to_vector_3d(context.region,context.region_data,coordinate)
    obj=next((o for o in context.scene.objects if o.get('ruster_kind')=='TERRAIN'),None)
    if obj:
        hit,location,normal,index=obj.ray_cast(origin,direction,distance=100000)
        if hit:
            return location
    hit=(document or terrain()).ray_intersect(origin,direction)
    return Vector(hit) if hit is not None else None


class RUSTER_OT_terrain_stroke(bpy.types.Operator):
    bl_idname='ruster.terrain_stroke'
    bl_label='Paint Rust Terrain'
    bl_options={'REGISTER','UNDO','BLOCKING'}

    @classmethod
    def poll(cls,context):
        return context.scene.ruster.mode=='MAP' and context.area and context.area.type=='VIEW_3D'

    def invoke(self,context,event):
        global stroke_active
        try:
            self.document=terrain(fresh=True)
            self.last=None
            self.changed=False
            self.last_preview=0
            self.draw_handle=None
            self.stamp(context,event)
            self.draw_handle=bpy.types.SpaceView3D.draw_handler_add(self.draw_cursor,(context,),'WINDOW','POST_VIEW')
            stroke_active=True
            context.window_manager.modal_handler_add(self)
            context.workspace.status_text_set('Paint: drag LMB · Alt: invert · Shift: smooth · Esc: cancel stroke')
            return {'RUNNING_MODAL'}
        except Exception as error:
            self.report({'ERROR'},str(error));return {'CANCELLED'}

    def stamp(self,context,event):
        hit=mouse_hit(context,event,self.document)
        if hit is None:
            return
        point=np.array(hit[:2])
        # Fill gaps in fast drags. One stroke is one native Blender undo step.
        spacing=max(context.scene.ruster_brush.radius*.15,self.document.size/(self.document.grid('terrain').shape[-1]-1))
        count=max(1,min(64,int(np.linalg.norm(point-self.last)/spacing))) if self.last is not None else 1
        start=self.last if self.last is not None else point
        for t in np.linspace(1/count,1,count):
            position=start+(point-start)*t
            self.changed |= brush_at(self.document,*position,invert=event.alt,smooth=event.shift)
        self.last=point
        if time.monotonic()-self.last_preview>.06:
            refresh(self.document,holes=False,water=False);self.last_preview=time.monotonic()

    def draw_cursor(self,context):
        if self.last is None:return
        import gpu
        from gpu_extras.batch import batch_for_shader
        brush=context.scene.ruster_brush
        if brush.shape=='SQUARE':
            x=np.array([-1,1,1,-1,-1])*brush.radius+self.last[0]
            y=np.array([-1,-1,1,1,-1])*brush.radius+self.last[1]
        else:
            angle=np.linspace(0,2*math.pi,65)
            x=np.cos(angle)*brush.radius+self.last[0]
            y=np.sin(angle)*brush.radius+self.last[1]
        positions=np.column_stack((x,y,self.document.sample_height(x,y)+.15))
        shader=gpu.shader.from_builtin('UNIFORM_COLOR')
        batch=batch_for_shader(shader,'LINE_STRIP',{'pos':positions})
        blend=gpu.state.blend_get();depth=gpu.state.depth_test_get()
        try:
            gpu.state.blend_set('ALPHA');gpu.state.depth_test_set('NONE')
            shader.bind();shader.uniform_float('color',(*context.preferences.themes[0].view_3d.object_active,1))
            batch.draw(shader)
        finally:
            gpu.state.blend_set(blend);gpu.state.depth_test_set(depth)

    def cleanup(self,context):
        if self.draw_handle:
            bpy.types.SpaceView3D.draw_handler_remove(self.draw_handle,'WINDOW');self.draw_handle=None
        context.workspace.status_text_set(None)

    def modal(self,context,event):
        global stroke_active
        try:
            if event.type in {'ESC','RIGHTMOUSE'}:
                stroke_active=False
                refresh();self.cleanup(context);return {'CANCELLED'}
            if event.type=='LEFTMOUSE' and event.value=='RELEASE':
                stroke_active=False
                if self.changed:
                    commit(self.document)
                self.cleanup(context)
                return {'FINISHED'}
            if event.type=='MOUSEMOVE':
                self.stamp(context,event)
            return {'RUNNING_MODAL'}
        except Exception as error:
            stroke_active=False
            refresh();self.cleanup(context)
            self.report({'ERROR'},str(error));return {'CANCELLED'}


class RUSTER_OT_terrain_sample(bpy.types.Operator):
    bl_idname='ruster.terrain_sample'
    bl_label='Sample Terrain Height'
    def invoke(self,context,event):
        hit=mouse_hit(context,event)
        if hit:
            context.scene.ruster_brush.height=hit.z
        return {'FINISHED'}


class RUSTER_WST_terrain(bpy.types.WorkSpaceTool):
    bl_space_type='VIEW_3D'
    bl_context_mode='OBJECT'
    bl_idname='ruster.terrain_brush'
    bl_label='Rust Terrain Brush'
    bl_description='Paint full-resolution Rust height, ground, biome, topology and alpha layers'
    bl_icon='brush.generic'
    bl_cursor='CROSSHAIR'
    bl_keymap=(('ruster.terrain_stroke',{'type':'LEFTMOUSE','value':'PRESS'},{}),
               ('ruster.terrain_sample',{'type':'RIGHTMOUSE','value':'PRESS','ctrl':True},{}))
    @staticmethod
    def draw_settings(context,layout,tool):
        brush=context.scene.ruster_brush
        layout.prop(brush,'radius');layout.prop(brush,'strength')


class RUSTER_OT_terrain_apply(bpy.types.Operator):
    bl_idname='ruster.terrain_apply'
    bl_label='Apply Brush at 3D Cursor'
    bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        try:
            document=terrain(fresh=True)
            brush_at(document,*context.scene.cursor.location[:2])
            commit(document)
            return {'FINISHED'}
        except Exception as error:
            self.report({'ERROR'},str(error));return {'CANCELLED'}


class RUSTER_OT_clone_source(bpy.types.Operator):
    bl_idname='ruster.clone_source'
    bl_label='Set Clone Source at Cursor'
    def execute(self,context):
        context.scene.ruster_brush.source=context.scene.cursor.location
        context.scene.ruster_brush.source_set=True
        return {'FINISHED'}


class RUSTER_OT_bridge(bpy.types.Operator):
    bl_idname='ruster.terrain_bridge'
    bl_label='Grade Bridge to Cursor'
    bl_options={'REGISTER','UNDO'}
    set_start:BoolProperty(default=False,options={'HIDDEN'})
    def execute(self,context):
        brush=context.scene.ruster_brush
        if self.set_start:
            brush.bridge_start=context.scene.cursor.location;brush.bridge_set=True
            return {'FINISHED'}
        try:
            if not brush.bridge_set:raise ValueError('Set a bridge start at the 3D cursor first')
            document=terrain(fresh=True)
            document.bridge(brush.bridge_start,context.scene.cursor.location,brush.radius*2,brush.strength)
            commit(document);return {'FINISHED'}
        except Exception as error:self.report({'ERROR'},str(error));return {'CANCELLED'}


class RUSTER_OT_generate(bpy.types.Operator):
    bl_idname='ruster.generate_island'
    bl_label='Generate Island Terrain'
    bl_options={'REGISTER','UNDO'}
    seed:IntProperty(name='Seed',default=1,min=0)
    amplitude:FloatProperty(name='Relief',default=160,min=0,max=500)
    frequency:IntProperty(name='Detail Frequency',default=4,min=1,max=32)
    octaves:IntProperty(name='Detail Octaves',default=5,min=1,max=8)
    def invoke(self,context,event):return context.window_manager.invoke_props_dialog(self,width=400)
    def draw(self,context):
        self.layout.label(text='Replaces terrain heights. Undo restores the previous terrain.',icon='INFO')
        for prop in ('seed','amplitude','frequency','octaves'):self.layout.prop(self,prop)
    def execute(self,context):
        try:
            doc=terrain(fresh=True);doc.generate_island(self.seed,self.amplitude,self.frequency,self.octaves)
            commit(doc);return {'FINISHED'}
        except Exception as error:self.report({'ERROR'},str(error));return {'CANCELLED'}


class RUSTER_OT_terrain_overlay(bpy.types.Operator):
    bl_idname='ruster.terrain_overlay'
    bl_label='Refresh Terrain Overlay'
    def execute(self,context):
        try:
            refresh();return {'FINISHED'}
        except Exception as error:
            self.report({'ERROR'},str(error));return {'CANCELLED'}


class RUSTER_OT_terrain_detail(bpy.types.Operator):
    bl_idname='ruster.terrain_detail'
    bl_label='Update Terrain Detail'
    def execute(self,context):
        try:
            doc=terrain()
            obj=next(o for o in context.scene.objects if o.get('ruster_kind')=='TERRAIN')
            mesh=obj.data;bpy.data.objects.remove(obj,do_unlink=True)
            if not mesh.users:bpy.data.meshes.remove(mesh)
            scene.create_terrain(doc.export_world());refresh(doc)
            return {'FINISHED'}
        except Exception as error:self.report({'ERROR'},str(error));return {'CANCELLED'}


class RUSTER_OT_new_map(bpy.types.Operator):
    bl_idname='ruster.new_map'
    bl_label='New Rust Map'
    size: IntProperty(name='Size (metres)',default=1000,min=100,max=6000)
    height: FloatProperty(name='Land Height',default=20,min=-500,max=500)
    def invoke(self,context,event):
        return context.window_manager.invoke_props_dialog(self,width=400)
    def draw(self,context):
        self.layout.label(text='Save your current project before creating a new map.',icon='INFO')
        self.layout.prop(self,'size');self.layout.prop(self,'height')
    def execute(self,context):
        try:
            from .app import session_dir
            path=session_dir()/'Untitled.map'
            atomic_write(path,empty_world(self.size,self.height).write())
            scene.import_map(path)
            from .ui import map_workspace
            map_workspace()
            return {'FINISHED'}
        except Exception as error:
            self.report({'ERROR'},str(error));return {'CANCELLED'}


def configure_path(obj,fields):
    record=paths.read(fields)
    state=obj.ruster_path
    state.enabled=True
    state.kind=record['name'] if record['name'] in {'Road','River','Rail','Powerline'} else 'Road'
    for key in (*paths.FLOATS,*paths.INTS,*paths.BOOLS):
        value=record[key]
        if key in paths.INTS and value>0x7FFFFFFF:
            obj['ruster_path_'+key]=str(value)
        else:
            setattr(state,key,value)
    obj['ruster_record']=base64.b64encode(wire.serialize(fields)).decode()
    obj['ruster_kind']='PATH'
    obj.hide_select=False
    return obj


def path_record(obj):
    original=wire.parse(base64.b64decode(obj['ruster_record']))
    state=obj.ruster_path
    if obj.type!='CURVE' or len(obj.data.splines)!=1:
        raise ValueError(f'{obj.name}: a path requires one curve spline')
    spline=obj.data.splines[0]
    if spline.type=='BEZIER':
        raise ValueError(f'{obj.name}: convert Bezier curves to a polyline before exporting')
    values={k:getattr(state,k) for k in (*paths.FLOATS,*paths.INTS,*paths.BOOLS)}
    for key in paths.INTS:
        if 'ruster_path_'+key in obj:
            values[key]=int(obj['ruster_path_'+key])
    old=paths.read(original)
    values['name']=state.kind if old['name'] in {'Road','River','Rail','Powerline'} else old['name']
    values['nodes']=[scene.to_unity(obj.matrix_world@Vector(point.co[:3])) for point in spline.points]
    return paths.update(original,values)


class RUSTER_OT_path_add(bpy.types.Operator):
    bl_idname='ruster.path_add'
    bl_label='Add Rust Path'
    bl_options={'REGISTER','UNDO'}
    kind: EnumProperty(name='Type',items=[(n,n,'') for n in ('Road','River','Rail','Powerline')])
    def execute(self,context):
        collection=bpy.data.collections.get('Paths') or scene.new_collection('Paths')
        curve=bpy.data.curves.new(self.kind,'CURVE');curve.dimensions='3D'
        spline=curve.splines.new('POLY');spline.points.add(1)
        point=context.scene.cursor.location.copy()
        for i,node in enumerate(spline.points):
            node.co=(*point+Vector((i*30,0,0)),1)
        curve.bevel_depth=.3
        obj=bpy.data.objects.new(self.kind,curve);collection.objects.link(obj)
        fields=[wire.encode(1,2,self.kind.encode())]
        configure_path(obj,fields)
        for item in context.selected_objects:
            item.select_set(False)
        obj.select_set(True);context.view_layer.objects.active=obj
        return {'FINISHED'}


class RUSTER_OT_path_snap(bpy.types.Operator):
    bl_idname='ruster.path_snap'
    bl_label='Snap Path to Terrain'
    bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        try:
            doc=terrain()
            obj=context.object
            if obj is None or obj.get('ruster_kind')!='PATH':
                raise ValueError('Select a Rust path')
            inverse=obj.matrix_world.inverted()
            for point in obj.data.splines[0].points:
                position=obj.matrix_world@Vector(point.co[:3])
                position.z=float(doc.sample_height(position.x,position.y))+obj.ruster_path.terrain_offset
                point.co=(*(inverse@position),1)
            return {'FINISHED'}
        except Exception as error:
            self.report({'ERROR'},str(error));return {'CANCELLED'}


class RUSTER_OT_path_grade(bpy.types.Operator):
    bl_idname='ruster.path_grade'
    bl_label='Apply Path to Terrain'
    bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        try:
            obj=context.object
            record=paths.read(path_record(obj))
            document=terrain(fresh=True)
            for x,height,z in paths.sample_polyline(record['nodes'],spacing=max(.5,record['width']*.2)):
                radius=record['width']/2+record['outer_padding']+record['outer_fade']
                river=record['name']=='River'
                document.brush('FLATTEN',x,z,radius,strength=1.,height=height+record['terrain_offset']-(3 if river else 0),falloff=.5)
                if river:
                    document.brush('FLATTEN',x,z,record['width']/2,layer='water',strength=1.,height=height,falloff=.3)
                mask=record['topology'] or {'Road':1<<11,'River':1<<14,'Powerline':1<<19}.get(record['name'],0)
                for bit in range(32):
                    if mask&(1<<bit):
                        document.brush('PAINT',x,z,record['width']/2,layer='topology',channel=bit,strength=1.)
                if record['name']=='Road':
                    splat=int(math.log2(record['splat']&-record['splat'])) if record['splat'] else 7
                    if splat<8:document.brush('PAINT',x,z,record['width']/2,layer='splat',channel=splat,strength=1.)
            commit(document)
            return {'FINISHED'}
        except Exception as error:
            self.report({'ERROR'},str(error));return {'CANCELLED'}


class RUSTER_OT_height_export(bpy.types.Operator,ExportHelper):
    bl_idname='ruster.height_export'
    bl_label='Export 16-bit Heightmap'
    filename_ext='.png'
    filter_glob:StringProperty(default='*.png',options={'HIDDEN'})
    def execute(self,context):
        try:
            # PNG uses unsigned normalized 16-bit samples; Rust stores signed /32766.
            from PIL import Image
            samples=terrain().grid('terrain')[0].astype(np.float64)
            Image.fromarray(np.rint(samples/32766*65535).clip(0,65535).astype('uint16')).save(self.filepath)
            return {'FINISHED'}
        except Exception as error:
            self.report({'ERROR'},str(error));return {'CANCELLED'}


class RUSTER_OT_height_import(bpy.types.Operator,ImportHelper):
    bl_idname='ruster.height_import'
    bl_label='Import 16-bit Heightmap'
    bl_options={'REGISTER','UNDO'}
    filter_glob:StringProperty(default='*.png;*.tif;*.tiff;*.raw',options={'HIDDEN'})
    def execute(self,context):
        try:
            document=terrain(fresh=True)
            grid=document.grid('terrain')
            if Path(self.filepath).suffix.lower()=='.raw':
                source=np.fromfile(self.filepath,dtype='<u2')
                n=math.isqrt(len(source))
                if n*n!=len(source):
                    raise ValueError('RAW heightmap must contain a square of little-endian uint16 samples')
                source=source.reshape(n,n)
            else:
                from PIL import Image
                with Image.open(self.filepath) as image:
                    source=np.asarray(image)
                if source.ndim!=2 or source.dtype.itemsize<2:
                    raise ValueError('Use a single-channel 16-bit height image')
            if not np.isfinite(source).all() or source.min()<0 or source.max()>65535:
                raise ValueError('Height image must contain normalized values from 0 to 65535')
            n=grid.shape[-1]
            x,z=np.meshgrid(np.linspace(0,source.shape[1]-1,n),np.linspace(0,source.shape[0]-1,n))
            before=grid[0].astype(np.int32)
            grid[0]=np.rint(resample(source.astype(float),x,z)/65535*32766).astype('<i2')
            document.changed('terrain')
            if 'height' in document.base_layers:
                derived=document.grid('height')
                if derived.shape==grid.shape:
                    derived[0]=np.clip(derived[0].astype(np.int32)+grid[0].astype(np.int32)-before,0,32766)
                    document.changed('height')
            commit(document)
            return {'FINISHED'}
        except Exception as error:
            self.report({'ERROR'},str(error));return {'CANCELLED'}


@persistent
def after_undo(_dummy):
    clear_cache()
    if hasattr(bpy.context.scene,'ruster') and bpy.context.scene.ruster.mode=='MAP':
        try:
            refresh()
        except (OSError,ValueError):
            pass


def register():
    global _tool_registered
    for cls in (RUSTER_PG_brush,RUSTER_PG_path,RUSTER_OT_terrain_stroke,RUSTER_OT_terrain_sample,
        RUSTER_OT_terrain_apply,RUSTER_OT_clone_source,RUSTER_OT_terrain_overlay,RUSTER_OT_new_map,
        RUSTER_OT_path_add,RUSTER_OT_path_snap,RUSTER_OT_path_grade,RUSTER_OT_height_export,RUSTER_OT_height_import):
        bpy.utils.register_class(cls);_classes.append(cls)
    for cls in (RUSTER_OT_bridge,RUSTER_OT_generate,RUSTER_OT_terrain_detail):
        bpy.utils.register_class(cls);_classes.append(cls)
    from bpy.props import PointerProperty
    bpy.types.Scene.ruster_brush=PointerProperty(type=RUSTER_PG_brush)
    bpy.types.Object.ruster_path=PointerProperty(type=RUSTER_PG_path)
    if not bpy.app.background:
        bpy.utils.register_tool(RUSTER_WST_terrain,after={'builtin.cursor'},separator=True,group=True)
        _tool_registered=True
    bpy.app.handlers.undo_post.append(after_undo)
    bpy.app.handlers.redo_post.append(after_undo)


def unregister():
    global _tool_registered,stroke_active
    stroke_active=False
    if _tool_registered:
        bpy.utils.unregister_tool(RUSTER_WST_terrain);_tool_registered=False
    for handlers in (bpy.app.handlers.undo_post,bpy.app.handlers.redo_post):
        if after_undo in handlers:
            handlers.remove(after_undo)
    del bpy.types.Scene.ruster_brush
    del bpy.types.Object.ruster_path
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
    _classes.clear();clear_cache()
