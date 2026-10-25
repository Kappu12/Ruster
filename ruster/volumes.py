"""Source collider previews. These viewport gizmos are never Rust geometry."""
import json
import math
from functools import lru_cache
import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty,StringProperty
from mathutils import Matrix, Quaternion, Vector
from . import scene

_revision=0


def attach(root, asset, base):
    """Persist small collider descriptions so saved projects also work offline."""
    global _revision
    from .assets import geometry
    transforms=[]
    for node in asset['nodes']:
        parent=node['parent']
        local=Matrix.Identity(4) if parent is None else Matrix.LocRotScale(
            scene.to_blender(node['position']),
            (scene.BASIS @ Quaternion(node['rotation']).to_matrix() @ scene.BASIS).to_quaternion(),
            scene.to_blender(node['scale']))
        transforms.append(local if parent is None else transforms[parent] @ local)
    shapes=[]
    for collider in asset.get('colliders', []):
        shape=dict(collider)
        shape['matrix']=[list(row) for row in transforms[shape.pop('node')]]
        shape['center']=list(scene.to_blender(shape['center']))
        if shape['type']=='BoxCollider':shape['size']=list(scene.to_blender(shape['size']))
        elif shape['type']=='CapsuleCollider':shape['direction']=(0,2,1)[shape['direction']]
        elif shape['type']=='MeshCollider':
            mesh=asset['meshes'][shape.pop('mesh')]
            if 'buffer' in mesh:vertices, _uv, faces, _counts=geometry.read(base/mesh['buffer'])
            else:vertices,faces=mesh['vertices'],mesh['faces']
            if len(vertices)>20000 or len(faces)>40000:continue
            shape.update(vertices=[list(scene.to_blender(v)) for v in vertices], faces=[[int(i) for i in f] for f in faces])
        shapes.append(shape)
    root.instance_type='NONE';root.instance_collection=None
    root['ruster_visual']=False
    root['ruster_marker']='VOLUME'
    root['ruster_volume_shapes']=json.dumps(shapes,separators=(',',':'))
    root['ruster_model_status']=('Volume · source collider preview' if shapes else
        'Volume · collider bounds unavailable; showing an origin marker')
    scene.name_prefab(root,asset['path'])
    root.empty_display_type='SPHERE'
    root.show_name=False
    refresh_marker(root,bpy.context.scene.ruster_show_volumes)
    _revision+=1


def refresh_markers(context_scene):
    shown=context_scene.ruster_show_volumes
    for obj in context_scene.objects:
        if obj.get('ruster_marker')=='VOLUME':
            # Accurate shapes are selectable gizmos. Unknown bounds get a small
            # origin marker, never an invented cube presented as game bounds.
            refresh_marker(obj,shown)


def refresh_marker(obj,shown):
    obj.empty_display_size=(.0001 if obj.get('ruster_volume_shapes','[]')!='[]' else .25) if shown else 0


def visibility_changed(_self,context):
    refresh_markers(context.scene)
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type=='VIEW_3D':area.tag_redraw()


@persistent
def restore_markers(*_args):
    global _revision
    _revision+=1
    for context_scene in bpy.data.scenes:refresh_markers(context_scene)


@lru_cache(maxsize=128)
def descriptions(raw):return json.loads(raw)


def round_mesh(radius, half_length=0., axis=2):
    """Sphere/capsule with sparse latitude/longitude outlines."""
    vertices=[];faces=[];edges=[]
    segments=32;rings=16
    rows=list(range(rings+1))
    if half_length:rows.insert(rings//2+1,rings//2)
    for index,row in enumerate(rows):
        angle=math.pi*row/rings
        z=radius*math.cos(angle)+(half_length if index<=rings//2 else -half_length)
        for column in range(segments):
            theta=math.tau*column/segments
            point=[radius*math.sin(angle)*math.cos(theta),radius*math.sin(angle)*math.sin(theta),z]
            point[axis],point[2]=point[2],point[axis]
            vertices.append(Vector(point))
    for row in range(len(rows)-1):
        for column in range(segments):
            a=row*segments+column;b=row*segments+(column+1)%segments
            faces.extend(((a,b,b+segments),(a,b+segments,a+segments)))
            if column%8==0:edges.append((a,a+segments))
            if row in (rings//4,rings//2,3*rings//4):edges.append((a,b))
    return vertices,faces,edges


def shape_mesh(shape, root_matrix):
    matrix=root_matrix @ Matrix(shape['matrix'])
    center=matrix @ Vector(shape['center'])
    kind=shape['type']
    if kind in ('SphereCollider','CapsuleCollider'):
        scale=matrix.to_scale()
        radius=shape['radius']*max(abs(s) for s in scale)
        half_length=0.;axis=shape.get('direction',2)
        if kind=='CapsuleCollider':
            radius=shape['radius']*max(abs(scale[i]) for i in range(3) if i!=axis)
            half_length=max(0.,shape['height']*abs(scale[axis])/2-radius)
        vertices,faces,edges=round_mesh(radius,half_length,axis)
        rotation=matrix.to_quaternion().to_matrix()
        return [rotation @ v+center for v in vertices],faces,edges
    if kind=='BoxCollider':
        vertices=[Vector((x*shape['size'][0]/2,y*shape['size'][1]/2,z*shape['size'][2]/2))
                  for x,y,z in ((-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),
                                (-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1))]
        quads=((0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7))
        faces=[tri for a,b,c,d in quads for tri in ((a,b,c),(a,c,d))]
        edges=((0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7))
    else:
        vertices=[Vector(v) for v in shape['vertices']]
        faces=shape['faces']
        edges=sorted({tuple(sorted((face[i],face[(i+1)%3]))) for face in faces for i in range(3)})
    return [matrix.to_3x3() @ v+center for v in vertices],faces,edges


def meshes(root):
    return [shape_mesh(shape,root.matrix_world) for shape in descriptions(root.get('ruster_volume_shapes','[]'))]


class RUSTER_GT_volume(bpy.types.Gizmo):
    bl_idname='RUSTER_GT_volume'
    __slots__=('root','signature','surface','outline')

    def setup(self):
        self.root=None;self.signature=None
        self.surface=None;self.outline=None
        self.use_draw_scale=False
        self.use_select_background=True

    def prepare(self,context):
        obj=self.root
        try:
            if not obj or not obj.visible_get(view_layer=context.view_layer,viewport=context.space_data):return False
            key=(obj.get('ruster_volume_shapes','[]'),tuple(tuple(row) for row in obj.matrix_world))
            if key!=self.signature:
                triangles=[];lines=[]
                for vertices,faces,edges in meshes(obj):
                    triangles.extend(vertices[i] for face in faces for i in face)
                    lines.extend(vertices[i] for edge in edges for i in edge)
                self.surface=self.new_custom_shape('TRIS',triangles) if triangles else None
                self.outline=self.new_custom_shape('LINES',lines) if lines else None
                self.signature=key
            theme=context.preferences.themes[0].view_3d
            self.color=theme.object_active if obj==context.view_layer.objects.active else (
                theme.object_selected if obj.select_get() else theme.space.text)
            self.color_highlight=theme.object_active
            return self.surface is not None
        except ReferenceError:return False

    def draw(self,context):
        if not self.prepare(context):return
        self.alpha=.07;self.alpha_highlight=.14
        self.draw_custom_shape(self.surface)
        self.alpha=.75;self.alpha_highlight=1.
        self.line_width=1.5
        self.draw_custom_shape(self.outline)

    def draw_select(self,context,select_id):
        if self.prepare(context) and not self.root.hide_select:self.draw_custom_shape(self.surface,select_id=select_id)


class RUSTER_OT_select_volume(bpy.types.Operator):
    bl_idname='ruster.select_volume'
    bl_label='Select Volume'
    bl_options={'INTERNAL'}
    instance:StringProperty(options={'SKIP_SAVE'})

    def invoke(self,context,event):
        root=next((obj for obj in context.scene.objects if obj.get('ruster_instance')==self.instance),None)
        if root is None:return {'CANCELLED'}
        if root.hide_select:return {'CANCELLED'}
        selected=root.select_get()
        if not event.shift:
            for obj in context.selected_objects:obj.select_set(False)
        root.select_set(not selected if event.shift else True)
        if root.select_get():context.view_layer.objects.active=root
        context.area.tag_redraw()
        return {'FINISHED'}


class RUSTER_GGT_volumes(bpy.types.GizmoGroup):
    bl_idname='RUSTER_GGT_volumes'
    bl_label='Rust Volumes'
    bl_space_type='VIEW_3D'
    bl_region_type='WINDOW'
    bl_options={'3D','PERSISTENT','DEPTH_3D','SHOW_MODAL_ALL'}

    @classmethod
    def poll(cls,context):
        return context.mode=='OBJECT' and context.scene.ruster_show_volumes and context.space_data.overlay.show_overlays

    def setup(self,context):
        self.signature=None
        self.refresh(context)

    def refresh(self,context):
        signature=(context.scene.as_pointer(),len(context.scene.objects),_revision)
        if signature==self.signature:return
        self.signature=signature
        self.gizmos.clear()
        for obj in context.view_layer.objects:
            if obj.get('ruster_marker')=='VOLUME' and obj.get('ruster_volume_shapes','[]')!='[]':
                gizmo=self.gizmos.new(RUSTER_GT_volume.bl_idname)
                gizmo.root=obj
                gizmo.target_set_operator('ruster.select_volume').instance=obj['ruster_instance']


def register():
    bpy.types.Scene.ruster_show_volumes=BoolProperty(name='Volumes',default=True,
        description='Show Rust volume bounds in the viewport. Volumes remain included when saving and exporting',
        update=visibility_changed)
    for cls in (RUSTER_OT_select_volume,RUSTER_GT_volume,RUSTER_GGT_volumes):bpy.utils.register_class(cls)
    for handlers in (bpy.app.handlers.load_post,bpy.app.handlers.undo_post,bpy.app.handlers.redo_post):
        handlers.append(restore_markers)


def unregister():
    for handlers in (bpy.app.handlers.load_post,bpy.app.handlers.undo_post,bpy.app.handlers.redo_post):
        if restore_markers in handlers:handlers.remove(restore_markers)
    for cls in (RUSTER_GGT_volumes,RUSTER_GT_volume,RUSTER_OT_select_volume):bpy.utils.unregister_class(cls)
    del bpy.types.Scene.ruster_show_volumes
    descriptions.cache_clear()
