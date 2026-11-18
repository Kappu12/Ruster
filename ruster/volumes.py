"""Source collider overlays. These boundaries are never Rust geometry."""
import json
import math
import time
from functools import lru_cache
import bpy
from bpy.app.handlers import persistent
from bpy.props import BoolProperty,StringProperty
from mathutils import Matrix, Quaternion, Vector
from mathutils.bvhtree import BVHTree
from bpy_extras import view3d_utils
from . import scene
from .core import volume_picking,volume_style

_draw_handle=None
_keymaps=[]
_geometry={}
_hover={}
_cycle=None
_last_press=None
_hover_generation=0
_pending_hover={}


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
    root['ruster_volume_type']=volume_style.classify(asset['path'])
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
    sources={obj.get('ruster_uid'):(obj.get('ruster_volume_shapes'),semantic_type(obj)) for obj in context_scene.objects
        if obj.get('ruster_marker')=='VOLUME' and obj.get('ruster_volume_shapes','[]')!='[]'}
    for obj in context_scene.objects:
        if (obj.get('ruster_kind')=='PREFAB' and not obj.get('ruster_visual') and
                not obj.get('ruster_marker') and not obj.instance_collection and obj.get('ruster_uid') in sources):
            obj['ruster_marker']='VOLUME'
            obj['ruster_volume_shapes'],obj['ruster_volume_type']=sources[obj['ruster_uid']]
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
    global _cycle,_last_press
    _geometry.clear();_hover.clear();_cycle=None;_last_press=None
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


def semantic_type(obj):
    kind=obj.get('ruster_volume_type')
    return kind if kind in volume_style.COLORS else volume_style.classify(obj.get('ruster_generated_name',''))


def boundary(obj):
    key=obj.as_pointer()
    signature=(obj.get('ruster_volume_shapes','[]'),tuple(tuple(row) for row in obj.matrix_world))
    cached=_geometry.get(key)
    if cached is None or cached['signature']!=signature:
        shapes=meshes(obj)
        lines=[vertices[i] for vertices,_faces,edges in shapes for edge in edges for i in edge]
        triangles=[vertices[i] for vertices,faces,_edges in shapes for face in faces for i in face]
        cached={'signature':signature,'lines':lines,'triangles':triangles,'batch':None,'surface_batch':None,'bvh':None}
        extents=[max(v[i] for v in triangles)-min(v[i] for v in triangles) for i in range(3)] if triangles else (0,0,0)
        cached['size']=math.prod(extents)
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
    hits=[];faces=[]
    origin=view3d_utils.region_2d_to_origin_3d(context.region,context.region_data,point,clamp=context.space_data.clip_end)
    direction=view3d_utils.region_2d_to_vector_3d(context.region,context.region_data,point)
    for obj in visible_volumes(context):
        if obj.hide_select:continue
        cached=boundary(obj);lines=cached['lines']
        clips=[matrix @ v.to_4d() for v in lines]
        segments=[segment for a,b in zip(clips[::2],clips[1::2])
            if (segment:=volume_picking.project_segment(a,b,width,height)) is not None]
        hit=volume_picking.wire_hit(point,segments,radius)
        if hit:hits.append((*hit,obj));continue
        if not cached['triangles']:continue
        if cached['bvh'] is None:
            vertices=cached['triangles']
            cached['bvh']=BVHTree.FromPolygons(vertices,[(i,i+1,i+2) for i in range(0,len(vertices),3)],all_triangles=True)
        _location,_normal,_index,distance=cached['bvh'].ray_cast(origin,direction,context.space_data.clip_end*2)
        if distance is not None:faces.append((cached['size'],distance,obj))
    # Edges have first priority. Interior clicks prefer the most specific volume;
    # repeated clicks still reach enclosing boxes and coincident surfaces.
    return [obj for _distance,_depth,obj in sorted(hits,key=lambda h:(h[0],h[1],h[2].name))]+[
        obj for _size,_distance,obj in sorted(faces,key=lambda h:(h[0],h[1],h[2].name))]


def draw_bounds():
    """Faint semantic fills and x-ray wires, independent of input/gizmo picking."""
    context=bpy.context
    if not overlay_enabled(context):return
    import gpu
    from gpu_extras.batch import batch_for_shader
    shader=gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    fill_shader=gpu.shader.from_builtin('UNIFORM_COLOR')
    hover=_hover.get(region_key(context))
    blend,depth,mask=gpu.state.blend_get(),gpu.state.depth_test_get(),gpu.state.depth_mask_get()
    try:
        gpu.state.blend_set('ALPHA');gpu.state.depth_test_set('NONE');gpu.state.depth_mask_set(False)
        entries=[(obj,boundary(obj),volume_style.state(semantic_type(obj),obj.select_get(),hover==obj.get('ruster_instance')))
            for obj in visible_volumes(context)]
        # Finish all fills before any outlines, so enclosing tint cannot wash
        # out a nested boundary. Picking is analytical, never a GPU/modal gizmo.
        fill_shader.bind()
        for _obj,cached,style in entries:
            if not cached['triangles']:continue
            if cached['surface_batch'] is None:
                cached['surface_batch']=batch_for_shader(fill_shader,'TRIS',{'pos':cached['triangles']})
            fill_shader.uniform_float('color',(*style['fill_color'],style['fill_alpha']))
            cached['surface_batch'].draw(fill_shader)
        shader.bind();shader.uniform_float('viewportSize',gpu.state.viewport_get()[2:])
        for _obj,cached,style in entries:
            if not cached['lines']:continue
            if cached['batch'] is None:cached['batch']=batch_for_shader(shader,'LINES',{'pos':cached['lines']})
            width=style['width']*context.preferences.system.ui_scale
            shader.uniform_float('lineWidth',width+2)
            shader.uniform_float('color',style['halo'])
            cached['batch'].draw(shader)
            shader.uniform_float('lineWidth',width)
            shader.uniform_float('color',(*style['color'],style['line_alpha']))
            cached['batch'].draw(shader)
    finally:
        gpu.state.blend_set(blend);gpu.state.depth_test_set(depth);gpu.state.depth_mask_set(mask)


class RUSTER_OT_hover_volume(bpy.types.Operator):
    bl_idname='ruster.hover_volume'
    bl_label='Highlight Volume Boundary'
    bl_options={'INTERNAL'}

    def invoke(self,context,event):
        if hover_watch_present(context.window):return {'PASS_THROUGH'}
        if not overlay_enabled(context):return {'PASS_THROUGH'}
        hits=candidates(context,(event.mouse_region_x,event.mouse_region_y))
        key=region_key(context);instance=hits[0].get('ruster_instance') if hits else None
        if _hover.get(key)!=instance:
            _hover[key]=instance;context.area.tag_redraw()
        return {'PASS_THROUGH'}


def hover_watch_present(window):
    if window is None:return False
    for op in window.modal_operators:
        if op is None:continue
        try:
            if op.bl_idname in {'ruster.watch_volume_hover','RUSTER_OT_watch_volume_hover'}:return True
        except ReferenceError:
            # Closing/loading a project can leave a removed RNA operator in
            # Blender's modal list until the next event-loop iteration.
            continue
    return False


class RUSTER_OT_watch_volume_hover(bpy.types.Operator):
    """Observe hover before native gizmos consume mouse-move keymap events."""
    bl_idname='ruster.watch_volume_hover'
    bl_label='Watch Volume Hover'
    bl_options={'INTERNAL'}

    def invoke(self,context,event):
        if hover_watch_present(context.window):return {'CANCELLED'}
        self.generation=_hover_generation
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self,context,event):
        if self.generation!=_hover_generation:return {'CANCELLED'}
        if event.type=='MOUSEMOVE':
            _pending_hover[context.window.as_pointer()]=(event.mouse_x,event.mouse_y)
        # Never consume a button, wheel, navigation event or gizmo drag.
        return {'PASS_THROUGH'}


def refresh_pending_hover():
    pending=dict(_pending_hover);_pending_hover.clear()
    for window in bpy.context.window_manager.windows:
        point=pending.get(window.as_pointer())
        if point is None:continue
        x,y=point
        for area in window.screen.areas:
            if area.type!='VIEW_3D' or not (area.x<=x<area.x+area.width and area.y<=y<area.y+area.height):continue
            region=next((r for r in area.regions if r.type=='WINDOW'),None)
            if region is None:continue
            over_ui=any(r.type not in {'WINDOW','TOOL_PROPS'} and r.width>1 and r.height>1 and
                r.x<=x<r.x+r.width and r.y<=y<r.y+r.height for r in area.regions)
            with bpy.context.temp_override(window=window,area=area,region=region):
                context=bpy.context
                key=region_key(context)
                hits=[] if over_ui else candidates(context,(x-region.x,y-region.y))
                instance=hits[0].get('ruster_instance') if hits else None
                if _hover.get(key)!=instance:_hover[key]=instance;area.tag_redraw()
    # Coalesce motion without losing the final event when the mouse stops.
    return .03


def ensure_hover_watch():
    for window in bpy.context.window_manager.windows:
        area=next((a for a in window.screen.areas if a.type=='VIEW_3D'),None)
        if area and not hover_watch_present(window):
            region=next((r for r in area.regions if r.type=='WINDOW'),None)
            if region:
                with bpy.context.temp_override(window=window,area=area,region=region):bpy.ops.ruster.watch_volume_hover('INVOKE_DEFAULT')
    return 1.


class RUSTER_OT_select_volume(bpy.types.Operator):
    bl_idname='ruster.select_volume'
    bl_label='Select Volume'
    bl_options={'INTERNAL'}
    instance:StringProperty(options={'SKIP_SAVE'})

    def invoke(self,context,event):
        global _cycle,_last_press
        if not overlay_enabled(context):return {'PASS_THROUGH'}
        point=(event.mouse_region_x,event.mouse_region_y);now=time.monotonic();key=region_key(context)
        if event.value=='CLICK' and _last_press and _last_press[0]==key and now-_last_press[1]<1. and math.dist(point,_last_press[2])<=4:
            return {'FINISHED'}
        if self.instance:
            root=next((obj for obj in visible_volumes(context) if obj.get('ruster_instance')==self.instance),None)
        else:
            hits=candidates(context,point)
            if not hits:
                _cycle=None;_last_press=None;return {'PASS_THROUGH'}
            ids=tuple(obj.get('ruster_instance') for obj in hits)
            index=0
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
        if event.value in {'PRESS','DOUBLE_CLICK'}:_last_press=(key,now,point)
        context.area.tag_redraw()
        return {'FINISHED'}


def register():
    global _draw_handle
    bpy.types.Scene.ruster_show_volumes=BoolProperty(name='Volumes',default=True,
        description='Show native volume bounds. Click edges or filled faces; repeat to cycle overlaps. Visibility does not affect saving/export',
        update=visibility_changed)
    for cls in (RUSTER_OT_select_volume,RUSTER_OT_hover_volume,RUSTER_OT_watch_volume_hover):bpy.utils.register_class(cls)
    _draw_handle=bpy.types.SpaceView3D.draw_handler_add(draw_bounds,(),'WINDOW','POST_VIEW')
    config=bpy.context.window_manager.keyconfigs.addon
    if config:
        km=config.keymaps.new(name='3D View',space_type='VIEW_3D')
        for shift in (False,True):
            # Native gizmos get first refusal. Handle selection on press, with
            # a click fallback for tools that reserve the initial press.
            for value in ('PRESS','CLICK','DOUBLE_CLICK'):
                item=km.keymap_items.new('ruster.select_volume','LEFTMOUSE',value,shift=shift,head=True)
                _keymaps.append((km,item))
        item=km.keymap_items.new('ruster.hover_volume','MOUSEMOVE','ANY',any=True)
        _keymaps.append((km,item))
    for handlers in (bpy.app.handlers.load_post,bpy.app.handlers.undo_post,bpy.app.handlers.redo_post):
        handlers.append(restore_markers)
    if not bpy.app.background:
        bpy.app.timers.register(ensure_hover_watch,first_interval=.1,persistent=True)
        bpy.app.timers.register(refresh_pending_hover,first_interval=.03,persistent=True)


def unregister():
    global _draw_handle,_cycle,_last_press,_hover_generation
    _hover_generation+=1
    if bpy.app.timers.is_registered(ensure_hover_watch):bpy.app.timers.unregister(ensure_hover_watch)
    if bpy.app.timers.is_registered(refresh_pending_hover):bpy.app.timers.unregister(refresh_pending_hover)
    for km,item in _keymaps:km.keymap_items.remove(item)
    _keymaps.clear()
    if _draw_handle is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handle,'WINDOW');_draw_handle=None
    for handlers in (bpy.app.handlers.load_post,bpy.app.handlers.undo_post,bpy.app.handlers.redo_post):
        if restore_markers in handlers:handlers.remove(restore_markers)
    for cls in (RUSTER_OT_watch_volume_hover,RUSTER_OT_hover_volume,RUSTER_OT_select_volume):bpy.utils.unregister_class(cls)
    del bpy.types.Scene.ruster_show_volumes
    descriptions.cache_clear()
    _geometry.clear();_hover.clear();_pending_hover.clear();_cycle=None;_last_press=None
