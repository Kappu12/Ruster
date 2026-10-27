"""Source collider overlays. These boundaries are never Rust geometry."""
import json
import math
import time
from functools import lru_cache
import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty,StringProperty
from mathutils import Matrix, Quaternion, Vector
from . import scene
from .core import volume_picking

_draw_handle=None
_keymaps=[]
_geometry={}
_hover={}
_cycle=None


def attach(root, asset, base):
    """Persist small collider descriptions so saved projects also work offline."""
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


def refresh_markers(context_scene):
    shown=context_scene.ruster_show_volumes
    # Saving can happen partway through the asynchronous preview queue. Recover
    # unresolved copies from a loaded peer of the SAME native prefab, offline.
    sources={obj.get('ruster_uid'):obj.get('ruster_volume_shapes') for obj in context_scene.objects
        if obj.get('ruster_marker')=='VOLUME' and obj.get('ruster_volume_shapes','[]')!='[]'}
    for obj in context_scene.objects:
        if (obj.get('ruster_kind')=='PREFAB' and not obj.get('ruster_visual') and
                not obj.get('ruster_marker') and not obj.instance_collection and obj.get('ruster_uid') in sources):
            obj['ruster_marker']='VOLUME'
            obj['ruster_volume_shapes']=sources[obj['ruster_uid']]
            obj['ruster_model_status']='Volume · source collider preview'
            obj.empty_display_type='SPHERE'
        if obj.get('ruster_marker')=='VOLUME':
            # Accurate shapes have selectable outlines. Unknown bounds get a small
            # origin marker, never an invented cube presented as game bounds.
            refresh_marker(obj,shown)


def refresh_marker(obj,shown):
    obj.empty_display_size=(.0001 if obj.get('ruster_volume_shapes','[]')!='[]' else .25) if shown else 0


def visibility_changed(_self,context):
    _hover.clear()
    refresh_markers(context.scene)
    for window in context.window_manager.windows:
        for area in window.screen.areas:
            if area.type=='VIEW_3D':area.tag_redraw()


@persistent
def restore_markers(*_args):
    global _cycle
    _geometry.clear();_hover.clear();_cycle=None
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


def overlay_enabled(context):
    return (context.area is not None and context.area.type=='VIEW_3D' and
        context.region is not None and context.region.type=='WINDOW' and context.region_data is not None and
        context.mode=='OBJECT' and context.scene.ruster_show_volumes and context.space_data.overlay.show_overlays)


def visible_volumes(context):
    return (obj for obj in context.view_layer.objects if obj.get('ruster_marker')=='VOLUME' and
        obj.visible_get(view_layer=context.view_layer,viewport=context.space_data))


def boundary(obj):
    key=obj.as_pointer()
    signature=(obj.get('ruster_volume_shapes','[]'),tuple(tuple(row) for row in obj.matrix_world))
    cached=_geometry.get(key)
    if cached is None or cached['signature']!=signature:
        lines=[vertices[i] for vertices,_faces,edges in meshes(obj) for edge in edges for i in edge]
        cached={'signature':signature,'lines':lines,'batch':None}
        if len(_geometry)>4096:_geometry.clear()
        _geometry[key]=cached
    return cached


def region_key(context):
    return (context.window.as_pointer(),context.area.as_pointer(),context.region.as_pointer())


def candidates(context,point):
    if not overlay_enabled(context):return []
    matrix=context.region_data.perspective_matrix
    width,height=context.region.width,context.region.height
    radius=8*context.preferences.system.ui_scale
    hits=[]
    for obj in visible_volumes(context):
        if obj.hide_select:continue
        lines=boundary(obj)['lines']
        clips=[matrix @ v.to_4d() for v in lines]
        segments=[segment for a,b in zip(clips[::2],clips[1::2])
            if (segment:=volume_picking.project_segment(a,b,width,height)) is not None]
        hit=volume_picking.wire_hit(point,segments,radius)
        if hit:hits.append((*hit,obj))
    # Keep every nearby wire reachable, including coincident/nested bounds.
    return [obj for _distance,_depth,obj in sorted(hits,key=lambda h:(h[0],h[1],h[2].name))]


def draw_bounds():
    """Persistent, unfilled x-ray wires, independent of gizmo hover and depth."""
    context=bpy.context
    if not overlay_enabled(context):return
    import gpu
    from gpu_extras.batch import batch_for_shader
    shader=gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    theme=context.preferences.themes[0].view_3d
    hover=_hover.get(region_key(context))
    blend,depth=gpu.state.blend_get(),gpu.state.depth_test_get()
    try:
        gpu.state.blend_set('ALPHA');gpu.state.depth_test_set('NONE')
        shader.bind();shader.uniform_float('viewportSize',gpu.state.viewport_get()[2:])
        for obj in visible_volumes(context):
            cached=boundary(obj)
            if not cached['lines']:continue
            if cached['batch'] is None:cached['batch']=batch_for_shader(shader,'LINES',{'pos':cached['lines']})
            selected=obj.select_get();highlight=hover==obj.get('ruster_instance')
            color=theme.object_active if obj==context.view_layer.objects.active and selected else (
                theme.object_selected if selected else ((.8,.95,1.) if highlight else (.28,.72,.82)))
            width=(2.5 if selected or highlight else 1.25)*context.preferences.system.ui_scale
            shader.uniform_float('lineWidth',width+2)
            shader.uniform_float('color',(.015,.025,.035,.65))
            cached['batch'].draw(shader)
            shader.uniform_float('lineWidth',width)
            shader.uniform_float('color',(*color,1. if selected or highlight else .65))
            cached['batch'].draw(shader)
    finally:
        gpu.state.blend_set(blend);gpu.state.depth_test_set(depth)


class RUSTER_OT_hover_volume(bpy.types.Operator):
    bl_idname='ruster.hover_volume'
    bl_label='Highlight Volume Boundary'
    bl_options={'INTERNAL'}

    def invoke(self,context,event):
        if not overlay_enabled(context):return {'PASS_THROUGH'}
        hits=candidates(context,(event.mouse_region_x,event.mouse_region_y))
        key=region_key(context);instance=hits[0].get('ruster_instance') if hits else None
        if _hover.get(key)!=instance:
            _hover[key]=instance;context.area.tag_redraw()
        return {'PASS_THROUGH'}


class RUSTER_OT_select_volume(bpy.types.Operator):
    bl_idname='ruster.select_volume'
    bl_label='Select Volume'
    bl_options={'INTERNAL'}
    instance:StringProperty(options={'SKIP_SAVE'})

    def invoke(self,context,event):
        global _cycle
        if not overlay_enabled(context):return {'PASS_THROUGH'}
        if self.instance:
            root=next((obj for obj in visible_volumes(context) if obj.get('ruster_instance')==self.instance),None)
        else:
            point=(event.mouse_region_x,event.mouse_region_y)
            hits=candidates(context,point)
            if not hits:
                _cycle=None;return {'PASS_THROUGH'}
            ids=tuple(obj.get('ruster_instance') for obj in hits)
            now=time.monotonic();index=0;key=region_key(context)
            if (_cycle and _cycle[0]==key and _cycle[1]==ids and now-_cycle[2]<3. and
                    math.dist(point,_cycle[3])<=4 and not event.shift):index=(_cycle[4]+1)%len(hits)
            _cycle=(key,ids,now,point,index)
            root=hits[index]
        if root is None or root.hide_select:return {'PASS_THROUGH'}
        selected=root.select_get()
        if not event.shift:
            for obj in context.selected_objects:obj.select_set(False)
        root.select_set(not selected if event.shift else True)
        if root.select_get():context.view_layer.objects.active=root
        _hover[region_key(context)]=root.get('ruster_instance')
        context.area.tag_redraw()
        return {'FINISHED'}


def register():
    global _draw_handle
    bpy.types.Scene.ruster_show_volumes=BoolProperty(name='Volumes',default=True,
        description='Show native volume bounds. Click edges to select; repeat to cycle overlaps. Visibility does not affect saving/export',
        update=visibility_changed)
    for cls in (RUSTER_OT_select_volume,RUSTER_OT_hover_volume):bpy.utils.register_class(cls)
    _draw_handle=bpy.types.SpaceView3D.draw_handler_add(draw_bounds,(),'WINDOW','POST_VIEW')
    config=bpy.context.window_manager.keyconfigs.addon
    if config:
        km=config.keymaps.new(name='3D View',space_type='VIEW_3D')
        for shift in (False,True):
            # The active Select Box tool may consume PRESS while deciding
            # whether a drag begins. CLICK runs after that decision, and leaves
            # native transform gizmos first refusal of their own press/drag.
            for value in ('CLICK','DOUBLE_CLICK'):
                item=km.keymap_items.new('ruster.select_volume','LEFTMOUSE',value,shift=shift,head=True)
                _keymaps.append((km,item))
        item=km.keymap_items.new('ruster.hover_volume','MOUSEMOVE','ANY',any=True)
        _keymaps.append((km,item))
    for handlers in (bpy.app.handlers.load_post,bpy.app.handlers.undo_post,bpy.app.handlers.redo_post):
        handlers.append(restore_markers)


def unregister():
    global _draw_handle,_cycle
    for km,item in _keymaps:km.keymap_items.remove(item)
    _keymaps.clear()
    if _draw_handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handle,'WINDOW');_draw_handle=None
    for handlers in (bpy.app.handlers.load_post,bpy.app.handlers.undo_post,bpy.app.handlers.redo_post):
        if restore_markers in handlers:handlers.remove(restore_markers)
    for cls in (RUSTER_OT_hover_volume,RUSTER_OT_select_volume):bpy.utils.unregister_class(cls)
    del bpy.types.Scene.ruster_show_volumes
    descriptions.cache_clear()
    _geometry.clear();_hover.clear();_cycle=None
