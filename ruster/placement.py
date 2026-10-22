"""Prefab grouping, surface placement, replacements and reusable assemblies."""
import base64
import math
from pathlib import Path
import random
import uuid
import bpy
from bpy.props import BoolProperty,FloatProperty,IntProperty,StringProperty
from bpy_extras.io_utils import ImportHelper,ExportHelper
from mathutils import Matrix,Quaternion,Vector
from . import scene,editing
from .core import prefabs,wire
from .core.project import atomic_write
from .core.rust_map import prefab_transform,update_transform
from .ui_style import properties,wrapped

_classes=[]


def select(objects):
    for obj in bpy.context.selected_objects:obj.select_set(False)
    for obj in objects:obj.select_set(True)
    if objects:bpy.context.view_layer.objects.active=objects[-1]


def selected_prefabs():
    result=set()
    for obj in bpy.context.selected_objects:
        if obj.get('ruster_kind')=='PREFAB':result.add(obj)
        elif obj.get('ruster_kind')=='GROUP':
            result.update(child for child in obj.children_recursive if child.get('ruster_kind')=='PREFAB')
    return sorted(result,key=lambda obj:obj.name)


def selected_roots():
    selected={o for o in bpy.context.selected_objects if o.get('ruster_kind') in {'PREFAB','GROUP','PATH'}}
    return [o for o in selected if not any(parent in selected for parent in parent_chain(o))]


def parent_chain(obj):
    while obj.parent:
        obj=obj.parent
        yield obj


def world_record(obj,origin=None):
    fields=wire.parse(base64.b64decode(obj['ruster_record']))
    location,rotation,scale=obj.matrix_world.decompose()
    if origin is not None:location-=origin
    return update_transform(fields,scene.to_unity(location),scene.blender_euler(rotation),scene.to_unity(scale))


def group(objects,name='Custom Prefab',origin=None):
    if not objects:raise ValueError('Select prefab placements first')
    bpy.context.view_layer.update()
    matrices=[(obj,obj.matrix_world.copy()) for obj in objects]
    root=bpy.data.objects.new(name,None)
    (bpy.data.collections.get('Prefabs') or scene.new_collection('Prefabs')).objects.link(root)
    root['ruster_kind']='GROUP'
    root.empty_display_type='PLAIN_AXES'
    root.empty_display_size=5
    root.location=(sum((matrix.translation for _obj,matrix in matrices),Vector())/len(objects)
                   if origin is None else origin)
    bpy.context.view_layer.update()
    for obj,matrix in matrices:
        obj.parent=root;obj.matrix_world=matrix
    select([root])
    return root


class RUSTER_OT_group(bpy.types.Operator):
    bl_idname='ruster.group'
    bl_label='Group Prefabs'
    bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        try:group(selected_prefabs());return {'FINISHED'}
        except Exception as error:self.report({'ERROR'},str(error));return {'CANCELLED'}


class RUSTER_OT_ungroup(bpy.types.Operator):
    bl_idname='ruster.ungroup'
    bl_label='Ungroup Prefabs'
    bl_options={'REGISTER','UNDO'}
    def execute(self,context):
        context.view_layer.update()
        result=[]
        for obj in list(context.selected_objects):
            if obj.get('ruster_kind')!='GROUP':continue
            for child in list(obj.children):
                matrix=child.matrix_world.copy();child.parent=obj.parent;child.matrix_world=matrix;result.append(child)
            bpy.data.objects.remove(obj,do_unlink=True)
        select(result);return {'FINISHED'}


class RUSTER_OT_surface_snap(bpy.types.Operator):
    bl_idname='ruster.surface_snap'
    bl_label='Snap to Terrain'
    bl_options={'REGISTER','UNDO'}
    offset:FloatProperty(name='Height Offset',default=0)
    align:BoolProperty(name='Align to Surface',default=False)
    def invoke(self,context,event):return context.window_manager.invoke_props_dialog(self)
    def draw(self,context):
        fields=properties(self.layout)
        fields.prop(self,'offset');fields.prop(self,'align')
    def execute(self,context):
        try:
            doc=editing.terrain()
            for obj in selected_prefabs():
                location,rotation,scale=obj.matrix_world.decompose()
                location.z=float(doc.sample_height(location.x,location.y))+self.offset
                if self.align:
                    d=doc.size/(doc.grid('terrain').shape[-1]-1)
                    dx=(float(doc.sample_height(location.x+d,location.y))-float(doc.sample_height(location.x-d,location.y)))/(2*d)
                    dy=(float(doc.sample_height(location.x,location.y+d))-float(doc.sample_height(location.x,location.y-d)))/(2*d)
                    normal=Vector((-dx,-dy,1)).normalized()
                    rotation=Vector((0,0,1)).rotation_difference(normal)@Quaternion((0,0,1),rotation.to_euler().z)
                obj.matrix_world=Matrix.LocRotScale(location,rotation,scale)
            return {'FINISHED'}
        except Exception as error:self.report({'ERROR'},str(error));return {'CANCELLED'}


class RUSTER_OT_assembly_export(bpy.types.Operator,ExportHelper):
    bl_idname='ruster.assembly_export'
    bl_label='Export Prefab Group'
    filename_ext='.rusterprefab'
    filter_glob:StringProperty(default='*.rusterprefab',options={'HIDDEN'})
    def execute(self,context):
        try:
            objects=selected_prefabs()
            if not objects:raise ValueError('Select a prefab group or placements to export')
            context.view_layer.update()
            origin=context.object.matrix_world.translation if context.object and context.object.get('ruster_kind')=='GROUP' else sum((o.matrix_world.translation for o in objects),Vector())/len(objects)
            records=[world_record(o,origin) for o in objects]
            atomic_write(self.filepath,prefabs.encode_assembly(records,Path(self.filepath).stem))
            return {'FINISHED'}
        except Exception as error:self.report({'ERROR'},str(error));return {'CANCELLED'}


class RUSTER_OT_assembly_import(bpy.types.Operator,ImportHelper):
    bl_idname='ruster.assembly_import'
    bl_label='Import Prefab Group'
    bl_options={'REGISTER','UNDO'}
    filter_glob:StringProperty(default='*.rusterprefab',options={'HIDDEN'})
    def execute(self,context):
        try:
            path=Path(self.filepath)
            if path.stat().st_size>32*1024*1024:raise ValueError('Custom prefab is too large')
            title,records=prefabs.decode_assembly(path.read_bytes())
            collection=bpy.data.collections.get('Prefabs') or scene.new_collection('Prefabs')
            created=[]
            for fields in records:
                position,rotation,scale=prefab_transform(fields)
                position=Vector(position)+Vector(scene.to_unity(context.scene.cursor.location))
                obj=scene.root_object(update_transform(fields,position,rotation,scale),collection)
                scene.attach_visual(obj);created.append(obj)
            group(created,title)
            from . import app
            app.request_missing_visuals(created)
            return {'FINISHED'}
        except Exception as error:self.report({'ERROR'},str(error));return {'CANCELLED'}


class RUSTER_OT_scatter(bpy.types.Operator):
    bl_idname='ruster.scatter'
    bl_label='Scatter Prefabs'
    bl_options={'REGISTER','UNDO'}
    radius:FloatProperty(name='Radius',default=50,min=.1,max=3000)
    count:IntProperty(name='Count',default=30,min=1,max=5000)
    spacing:FloatProperty(name='Minimum Spacing',default=4,min=0,max=1000)
    seed:IntProperty(name='Seed',default=1)
    min_scale:FloatProperty(name='Minimum Scale',default=.8,min=.01,max=100)
    max_scale:FloatProperty(name='Maximum Scale',default=1.2,min=.01,max=100)
    max_slope:FloatProperty(name='Maximum Slope',default=45,min=0,max=90)
    def invoke(self,context,event):return context.window_manager.invoke_props_dialog(self,width=400)
    def draw(self,context):
        wrapped(self.layout,context,'Scatter the selected prefab around the 3D cursor.',icon='scatter')
        fields=properties(self.layout.column())
        for prop in ('radius','count','spacing','seed','min_scale','max_scale','max_slope'):fields.prop(self,prop)
    def execute(self,context):
        try:
            objects=selected_prefabs()
            if not objects:raise ValueError('Select an existing prefab to scatter')
            if self.min_scale>self.max_scale:raise ValueError('Minimum scale must not exceed maximum scale')
            template=objects[0]
            doc=editing.terrain()
            context.view_layer.update()
            source=world_record(template)
            _,rotation,scale=prefab_transform(source)
            occupied=[tuple(o.matrix_world.translation[:2]) for o in scene.prefab_roots()]
            points=prefabs.scatter_points(context.scene.cursor.location[:2],self.radius,self.count,self.spacing,self.seed,occupied)
            rng=random.Random(self.seed)
            created=[]
            collection=template.users_collection[0]
            step=doc.size/(doc.grid('terrain').shape[-1]-1)
            for x,y in points:
                if abs(x)>doc.size/2 or abs(y)>doc.size/2:continue
                dx=(float(doc.sample_height(x+step,y))-float(doc.sample_height(x-step,y)))/(2*step)
                dy=(float(doc.sample_height(x,y+step))-float(doc.sample_height(x,y-step)))/(2*step)
                if math.degrees(math.atan(math.hypot(dx,dy)))>self.max_slope:continue
                position=(x,float(doc.sample_height(x,y)),y)
                rotation_=(rotation[0],rotation[1]+rng.uniform(0,360),rotation[2])
                factor=rng.uniform(self.min_scale,self.max_scale)
                fields=update_transform(source,position,rotation_,[v*factor for v in scale])
                obj=scene.root_object(fields,collection);scene.attach_visual(obj);created.append(obj)
            select(created)
            from . import app
            app.request_missing_visuals(created)
            self.report({'INFO'},f'Placed {len(created)} prefabs within spacing and slope limits')
            return {'FINISHED'}
        except Exception as error:self.report({'ERROR'},str(error));return {'CANCELLED'}


class RUSTER_OT_select_same(bpy.types.Operator):
    bl_idname='ruster.select_same'
    bl_label='Select Same Prefab'
    def execute(self,context):
        obj=context.object
        if not obj or obj.get('ruster_kind')!='PREFAB':return {'CANCELLED'}
        select([o for o in scene.prefab_roots() if o['ruster_uid']==obj['ruster_uid']])
        return {'FINISHED'}


class RUSTER_OT_replace(bpy.types.Operator):
    bl_idname='ruster.replace'
    bl_label='Replace Prefabs'
    bl_options={'REGISTER','UNDO'}
    uid:StringProperty(name='Replacement Prefab ID')
    def invoke(self,context,event):return context.window_manager.invoke_props_dialog(self)
    def draw(self,context):
        properties(self.layout).prop(self,'uid')
    def execute(self,context):
        try:
            from .assets.catalog import find
            uid=int(self.uid)
            if not 0<=uid<=0xFFFFFFFF or not find(scene.cache_dir(),uid):
                raise ValueError('Replacement prefab ID is not in the local catalog')
            objects=selected_prefabs()
            for obj in objects:
                fields=wire.parse(base64.b64decode(obj['ruster_record']))
                fields=wire.replace(fields,2,0,uid)
                obj['ruster_record']=base64.b64encode(wire.serialize(fields)).decode()
                obj['ruster_uid']=str(uid)
                obj.instance_collection=None;obj.instance_type='NONE'
                obj['ruster_visual']=False
                for key in ('ruster_marker','ruster_helper_bounds','ruster_model_error','ruster_model_error_kind'):
                    if key in obj:del obj[key]
                scene.attach_visual(obj)
            from . import app
            app.request_missing_visuals(objects)
            return {'FINISHED'}
        except Exception as error:self.report({'ERROR'},str(error));return {'CANCELLED'}


def duplicate_selected():
    roots=selected_roots()
    created=[]
    for root in roots:
        originals=[root]+[o for o in root.children_recursive if o.get('ruster_kind') in {'PREFAB','GROUP'}]
        copies={}
        for obj in originals:
            new=obj.copy();obj.users_collection[0].objects.link(new)
            if new.get('ruster_kind')=='PREFAB':scene.name_prefab(new,obj.name)
            if new.type=='CURVE':new.data=obj.data.copy()
            new['ruster_instance']=uuid.uuid4().hex
            copies[obj]=new
        for old,new in copies.items():
            if old.parent in copies:new.parent=copies[old.parent]
            from .construction import clear_copy_link
            clear_copy_link(new)
        copies[root].location.x+=2
        created.append(copies[root])
    select(created)
    return created


def delete_selected():
    roots=selected_roots()
    from .construction import deletion_roots
    roots=deletion_roots(roots)
    for root in roots:
        for child in list(root.children_recursive):bpy.data.objects.remove(child,do_unlink=True)
        bpy.data.objects.remove(root,do_unlink=True)


def register():
    for cls in (RUSTER_OT_group,RUSTER_OT_ungroup,RUSTER_OT_assembly_export,
                RUSTER_OT_assembly_import,RUSTER_OT_select_same,RUSTER_OT_replace):
        bpy.utils.register_class(cls);_classes.append(cls)
    from . import construction
    construction.register()


def unregister():
    from . import construction
    construction.unregister()
    for cls in reversed(_classes):bpy.utils.unregister_class(cls)
    _classes.clear()
