"""Typed AI composition tools; all geometry remains original Rust prefab data."""
import base64
import gzip
import json
import math
from pathlib import Path
import tempfile
import bpy
from mathutils import Matrix,Vector,Quaternion
from . import app,scene,editing,placement
from .assets import catalog
from .core import paths,prefabs,wire
from .core.project import atomic_write

READ={'get_editor_status','list_prefab_categories','get_prefab_details','get_viewport_image'}
EDIT={'request_prefab_assets','place_prefabs','transform_objects','group_objects','ungroup_object','rename_object','focus_view','export_assembly','import_assembly'}


def bounded_int(value,lo,hi,label):
    if type(value)!=int or not lo<=value<=hi:raise ValueError(f'{label} must be an integer from {lo} to {hi}')
    return value


def object_names(values,bridge):
    if not isinstance(values,list) or not 1<=len(values)<=200 or any(not isinstance(n,str) for n in values):raise ValueError('Provide 1–200 object names')
    if len(set(values))!=len(values):raise ValueError('Object names must be unique')
    return [bridge.map_object(n) for n in values]


def independent(objects):
    selected=set(objects)
    if any(any(p in selected for p in placement.parent_chain(o)) for o in objects):raise ValueError('Choose a group or its children, not both')


def checked_name(value):
    if not isinstance(value,str) or not value.strip() or len(value.encode('utf8'))>63:raise ValueError('Use a nonempty name of at most 63 UTF-8 bytes')
    return value.strip()


def bounds(points):
    if not points:return None
    low=[min(p[i] for p in points) for i in range(3)];high=[max(p[i] for p in points) for i in range(3)]
    return {'min':low,'max':high,'dimensions':[b-a for a,b in zip(low,high)]}


def hierarchy():
    children={}
    for obj in bpy.context.scene.objects:children.setdefault(obj.parent,[]).append(obj)
    return children


def object_bounds(obj,children=None,cache=None):
    # Cache subtree world bounds for this read only. One scene pass avoids
    # Object.children's repeated whole-scene scans on large imported groups.
    children=hierarchy() if children is None else children
    cache={} if cache is None else cache
    pending=[(obj,False)]
    while pending:
        root,visited=pending.pop()
        if root in cache:continue
        if not visited:
            pending.append((root,True));pending.extend((child,False) for child in children.get(root,()))
            continue
        low=[math.inf]*3;high=[-math.inf]*3;found=False
        collection=root.instance_collection
        if collection:
            matrix=root.matrix_world@Matrix.Translation(-collection.instance_offset)
            models=((model,matrix@model.matrix_world) for model in collection.all_objects if model.type=='MESH')
        elif root.type=='MESH':models=((root,root.matrix_world),)
        else:models=()
        for model,matrix in models:
            for corner in model.bound_box:
                point=matrix@Vector(corner);found=True
                for i in range(3):low[i]=min(low[i],point[i]);high[i]=max(high[i],point[i])
        for child in children.get(root,()):
            box=cache[child]
            if box:
                found=True
                for i in range(3):low[i]=min(low[i],box['min'][i]);high[i]=max(high[i],box['max'][i])
        cache[root]={'min':low,'max':high,'dimensions':[b-a for a,b in zip(low,high)]} if found else None
    return cache[obj]


def object_infos(server,objects,bridge,include_bounds=True):
    children=hierarchy();cache={}
    return [bridge.object_info(server,obj.name,include_bounds,children,cache) for obj in objects]


def details(uid):
    bounded_int(uid,0,0xffffffff,'Prefab ID')
    found=catalog.find(scene.cache_dir(),uid)
    if not found:raise ValueError('Prefab ID is not in the local catalog; search_prefabs first')
    result={'id':uid,'path':found[0],'available':bool(found[1]),'geometry_read_only':True,'cached':False,'local_bounds':None}
    path=scene.cache_dir()/'prefabs'/f'{uid}.json.gz'
    if not path.is_file():
        result['next_step']='Call request_prefab_assets, then poll get_editor_status and retry get_prefab_details.';return result
    with gzip.open(path,'rt') as stream:asset=json.load(stream)
    if asset.get('schema')!=1:raise ValueError('Cached model uses an unsupported schema; refresh its assets')
    transforms=[];points=[];mesh_boxes={}
    for node in asset['nodes']:
        parent=node['parent']
        transform=Matrix.Identity(4) if parent is None else transforms[parent]@Matrix.LocRotScale(
            Vector(scene.to_blender(node['position'])),(scene.BASIS@Quaternion(node['rotation']).to_matrix()@scene.BASIS).to_quaternion(),Vector(scene.to_blender(node['scale'])))
        transforms.append(transform)
        mesh=asset['meshes'].get(node.get('mesh'))
        if mesh and mesh['vertices']:
            # Enclosing mesh boxes keep metadata small even for large monuments.
            ident=node['mesh']
            if ident not in mesh_boxes:
                if mesh.get('buffer'):
                    from .assets import geometry
                    source=(path.parent/mesh['buffer']).resolve()
                    if not source.is_relative_to(path.parent.resolve()):raise ValueError('Invalid mesh buffer path')
                    limits=geometry.bounds(source)
                    box={'min':limits[0],'max':limits[1]} if limits else None
                else:box=bounds(mesh['vertices'])
                mesh_boxes[ident]=box
            box=mesh_boxes[ident]
            if not box:continue
            from itertools import product
            points.extend(transform@Vector(scene.to_blender(p)) for p in product(*zip(box['min'],box['max'])))
    result.update(cached=True,mesh_count=len(asset['meshes']),material_count=len(asset['materials']),node_count=len(asset['nodes']),
        triangle_count=sum(m['faces'] if m.get('buffer') else sum(len(s) for s in m['submeshes']) for m in asset['meshes'].values()),
        local_bounds=bounds(points),bounds_kind='enclosing mesh boxes',coordinates='Editor local metres; Z up')
    return result


def viewport():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type=='VIEW_3D':return window,area,next(r for r in area.regions if r.type=='WINDOW')
    raise ValueError('Open a 3D viewport first')


def path_info(obj):
    if obj.get('ruster_kind')!='PATH':raise ValueError('Choose a Rust path')
    record=paths.read(editing.path_record(obj))
    record['nodes']=[list(scene.to_blender(n)) for n in record['nodes']]
    return {'object':obj.name,**record,'coordinates':'Editor world metres; Z up'}


def path_values(values,bridge):
    if not isinstance(values,dict):raise ValueError('Path settings must be an object')
    allowed=set(paths.FLOATS)|set(paths.INTS)|set(paths.BOOLS)
    if set(values)-allowed:raise ValueError('Unsupported path settings: '+', '.join(sorted(set(values)-allowed)))
    for key,value in values.items():
        if key in paths.BOOLS:
            if type(value)!=bool:raise ValueError(key+' must be boolean')
        elif key in paths.INTS:bounded_int(value,0,0xffffffff,key)
        else:
            prop=editing.RUSTER_PG_path.bl_rna.properties[key]
            if isinstance(value,bool) or not isinstance(value,(float,int)) or not math.isfinite(value) or not prop.hard_min-1e-6<=value<=prop.hard_max+1e-6:raise ValueError('Invalid path '+key)
    return values


def set_nodes(obj,nodes,bridge):
    if not isinstance(nodes,list) or not 2<=len(nodes)<=4096:raise ValueError('Provide 2–4096 world-space nodes')
    checked=[bridge.vector(n,'Path node') for n in nodes]
    if any(abs(v)>1e7 for n in checked for v in n):raise ValueError('Path node exceeds supported map coordinates')
    curve=bpy.data.curves.new(obj.name,'CURVE');curve.dimensions='3D';curve.bevel_depth=.3
    spline=curve.splines.new('POLY');spline.points.add(len(checked)-1)
    inverse=obj.matrix_world.inverted()
    for point,position in zip(spline.points,checked):point.co=(*(inverse@Vector(position)),1)
    old=obj.data;obj.data=curve
    if old.users==0:bpy.data.curves.remove(old)


def dispatch(server,kind,p,bridge):
    if kind=='get_editor_status':
        from . import __version__
        from .assets import CONVERTER_VERSION
        state=bpy.context.scene.ruster
        roots=scene.prefab_roots()
        return {'version':__version__,'converter_version':CONVERTER_VERSION,'restart_required':bool(app.updated_version()),
            'prefab_count':len(roots),'visible_prefabs':sum(bool(obj.get('ruster_visual')) for obj in roots),
            'unloaded_prefabs':sum(not obj.get('ruster_visual') and not obj.get('ruster_marker') for obj in roots),
            'mode':state.mode,'busy':state.busy or bool(app._visual_queue),'worker_busy':state.busy,'pending_visuals':len(app._visual_queue),
            'queued_prefabs':len(app._pending_asset_ids),'asset_status':state.asset_status,'asset_progress':state.asset_progress,
            'catalog_ready':(scene.cache_dir()/'catalog.sqlite3').is_file(),'coordinates':{'units':'metres','up_axis':'Z','rotation':'XYZ Euler degrees','ground_plane_z':0},
            'capabilities':['catalog discovery','original asset metadata','batch prefab composition','grouping','placement transforms','bounded duplication and arrays','bounds alignment','ground plane snapping','viewport images','RustEdit prefab and model exports','prefab-only map interchange','imported IO scalar settings','assemblies','save/export','undo/redo'],
            'limitations':['Prefab meshes and materials are immutable. Build models by composing whole Rust prefabs.','Catalog availability means a local bundle exists, not guaranteed successful model extraction.','Validation does not simulate Rust server gameplay or collisions.']}
    if kind=='list_prefab_categories':
        rows=catalog.categories(scene.cache_dir());offset=bounded_int(p.get('offset',0),0,2**31-1,'Offset');limit=bounded_int(p.get('limit',100),1,200,'Limit')
        return {'total_categories':len(rows),'total_prefabs':sum(c for _,c in rows),'categories':[{'path':path,'count':count} for path,count in rows[offset:offset+limit]],'next_offset':offset+limit if offset+limit<len(rows) else None}
    if kind=='get_prefab_details':return details(**p)
    if kind=='get_viewport_image':
        bridge.require_idle()
        if bpy.app.background:raise ValueError('Viewport images require the desktop app')
        window,area,region=viewport();render=bpy.context.scene.render
        old_format=render.image_settings.file_format
        old_size=(render.resolution_x,render.resolution_y,render.resolution_percentage)
        try:
            render.image_settings.file_format='PNG'
            render.resolution_x=1280;render.resolution_y=720;render.resolution_percentage=100
            with tempfile.TemporaryDirectory(prefix='ruster-viewport-') as directory:
                target=Path(directory)/'viewport.png'
                with bpy.context.temp_override(window=window,area=area,region=region):bpy.ops.render.opengl(view_context=True)
                bpy.data.images['Render Result'].save_render(str(target))
                data=target.read_bytes()
                if len(data)>5*1024*1024:raise ValueError('Viewport image is too large; reduce viewport complexity')
                return {'data':base64.b64encode(data).decode(),'format':'png'}
        finally:
            render.image_settings.file_format=old_format
            render.resolution_x,render.resolution_y,render.resolution_percentage=old_size
    bridge.require_idle();bridge.require_editor()
    if kind=='request_prefab_assets':
        ids=p['uids']
        if not isinstance(ids,list) or not 1<=len(ids)<=100:raise ValueError('Request 1–100 prefab IDs')
        for uid in ids:
            bounded_int(uid,0,0xffffffff,'Prefab ID')
            found=catalog.find(scene.cache_dir(),uid)
            if not found or not found[1]:raise ValueError(f'Prefab {uid} is not available locally')
        if not app.request_assets(ids):raise ValueError(bpy.context.scene.ruster.asset_status)
        return {'requested':ids,'next_step':'Poll get_editor_status until busy is false, then get_prefab_details.'}
    if kind=='import_assembly':
        path=bridge.file_target(p['path'],'.rusterprefab',True)
        if not path.is_file() or path.stat().st_size>32*1024*1024:raise ValueError('Choose an existing assembly of at most 32 MiB')
        title,records=prefabs.decode_assembly(path.read_bytes())
        if len(records)>1000:raise ValueError('MCP imports support at most 1000 prefab placements per assembly')
        title=checked_name(p.get('name') or title)
        offset=Vector(bridge.vector(p['position'],'Assembly position'))
        from .core.rust_map import prefab_id,prefab_transform
        specs=[]
        for record in records:
            uid=prefab_id(record);location,rotation,scale=prefab_transform(record)
            rot=scene.unity_euler(rotation)
            specs.append((record,uid,list(Vector(scene.to_blender(location))+offset),[math.degrees(v) for v in rot.to_euler('XYZ')],list(scene.to_blender(scale))))
        created=[]
        try:
            for record,uid,position,rotation,scale in specs:
                obj=bridge.place_prefab(uid,position,rotation,scale)
                created.append(obj);obj['ruster_record']=base64.b64encode(wire.serialize(record)).decode()
            root=placement.group(created,title)
        except Exception:
            placement.select(created);placement.delete_selected();raise
        result={'group':bridge.object_info(server,root.name),'prefab_count':len(created)}
    elif kind=='place_prefabs':
        items=p['placements']
        if not isinstance(items,list) or not 1<=len(items)<=100:raise ValueError('Provide 1–100 prefab placements')
        group_name=checked_name(p['group_name']) if p.get('group_name') is not None else None
        created=[]
        try:
            for item in items:
                if not isinstance(item,dict) or set(item)-{'uid','position','rotation_degrees','scale'}:raise ValueError('Invalid placement fields')
                created.append(bridge.place_prefab(**item))
            root=placement.group(created,group_name) if group_name else None
        except Exception:
            placement.select(created);placement.delete_selected();raise
        info=object_infos(server,created+([root] if root else []),bridge)
        result={'objects':info[:len(created)],'group':info[-1] if root else None}
    elif kind=='transform_objects':
        items=p['transforms']
        if not isinstance(items,list) or not 1<=len(items)<=200 or any(not isinstance(i,dict) for i in items):raise ValueError('Provide 1–200 object transforms')
        objects=object_names([i.get('name') for i in items],bridge);independent(objects)
        before={o:o.matrix_basis.copy() for o in objects}
        try:
            for obj,item in zip(objects,items):bridge.set_transform(obj,**{k:v for k,v in item.items() if k!='name'})
        except Exception:
            for obj,matrix in before.items():obj.matrix_basis=matrix
            bpy.context.view_layer.update();raise
        result={'objects':object_infos(server,objects,bridge)}
    elif kind=='group_objects':
        objects=object_names(p['names'],bridge);independent(objects)
        if any(o.get('ruster_kind') not in {'PREFAB','GROUP'} for o in objects):raise ValueError('Only prefabs and groups can form a composition')
        root=placement.group(objects,checked_name(p.get('name','AI Composition')));result=bridge.object_info(server,root.name)
    elif kind=='ungroup_object':
        obj=bridge.map_object(p['name'])
        if obj.get('ruster_kind')!='GROUP':raise ValueError('Choose a prefab group')
        children=[o.name for o in obj.children];placement.select([obj]);bpy.ops.ruster.ungroup();result={'objects':children[:200],'child_count':len(children),'objects_truncated':len(children)>200}
    elif kind=='rename_object':
        obj=bridge.map_object(p['name']);obj.name=checked_name(p['new_name']);result=bridge.object_info(server,obj.name)
    elif kind=='focus_view':
        axis=p.get('axis','CURRENT')
        if axis not in {'CURRENT','TOP','BOTTOM','FRONT','BACK','LEFT','RIGHT'}:raise ValueError('Invalid view axis')
        objects=object_names(p['names'],bridge);window,area,region=viewport();placement.select(objects)
        with bpy.context.temp_override(window=window,area=area,region=region):
            if axis!='CURRENT':bpy.ops.view3d.view_axis(type=axis,align_active=False)
            bpy.ops.view3d.view_selected(use_all_regions=False)
        result={'focused':[o.name for o in objects]}
    elif kind=='export_assembly':
        target=bridge.file_target(p['path'],'.rusterprefab',p.get('overwrite') is True)
        from . import mcp_prefab_ops
        objects=object_names(p['names'],bridge);independent(objects)
        prefab_objects=mcp_prefab_ops.prefabs_in(objects)
        if not prefab_objects:raise ValueError('Choose prefab placements or groups')
        origin=sum((o.matrix_world.translation for o in prefab_objects),Vector())/len(prefab_objects)
        atomic_write(target,prefabs.encode_assembly([placement.world_record(o,origin) for o in prefab_objects],target.stem))
        return {'path':str(target),'prefab_count':len(prefab_objects),'origin':list(origin)}
    else:raise ValueError('Unsupported composition tool')
    if kind!='focus_view' and bpy.context.preferences.edit.use_global_undo:bpy.ops.ed.undo_push(message='MCP: '+kind.replace('_',' ').title())
    app.redraw();return result
