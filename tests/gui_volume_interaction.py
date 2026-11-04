"""Nested-volume native input regression, with optional read-only maze project.

Use RUSTER_VOLUME_PROJECT for the maze and RUSTER_VOLUME_OUTPUT for screenshots.
Pass a packaged app root after -- to test its installed code.
"""
import hashlib,json,os,sys,tempfile,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
if '--' in sys.argv:
    package=Path(sys.argv[sys.argv.index('--')+1]);sys.path.insert(0,str(package))
    sys.path.insert(0,str(package/'python_modules'))
import bpy,ruster
from mathutils import Quaternion,Vector
from bpy_extras.view3d_utils import location_3d_to_region_2d
from ruster import studio,scene,volumes,app,quitting,placement
from ruster.core import wire
from tests.blender_volumes import asset

temporary=tempfile.TemporaryDirectory(prefix='ruster-volume-gui-')
os.environ['RUSTER_USER_DIR']=temporary.name
output=Path(os.environ.get('RUSTER_VOLUME_OUTPUT',temporary.name));output.mkdir(parents=True,exist_ok=True)
project=os.environ.get('RUSTER_VOLUME_PROJECT');draws=[];original=volumes.draw_bounds


def checked():
    try:
        import gpu
        before=(gpu.state.blend_get(),gpu.state.depth_test_get(),gpu.state.depth_mask_get())
        original()
        assert before==(gpu.state.blend_get(),gpu.state.depth_test_get(),gpu.state.depth_mask_get()),'Volume fill leaked GPU state'
        if volumes.overlay_enabled(bpy.context):draws.append(tuple(o.name for o in volumes.visible_volumes(bpy.context)))
    except Exception:traceback.print_exc();os._exit(1)


volumes.draw_bounds=checked
ruster.register()
if project:
    source_hash=hashlib.sha256(Path(project).read_bytes()).hexdigest();app.open_path(Path(project))
else:
    studio.new_prefab()
    for uid,scale in ((1,133.25),(2,12),(3,12),(4,12)):
        data=asset(uid,'BoxCollider');data['colliders'][0].update(center=[0,0,0],size=[1,1,1])
        data['path']='assets/modding/volumes_and_triggers/'+('prevent_building_cube' if uid==1 else
            ('safezoneoverridebox' if uid==4 else 'prevent_movment_volume'))+'.prefab'
        root=scene.root_object([wire.encode(2,0,uid)],bpy.context.scene.collection)
        volumes.attach(root,data,Path(temporary.name));root.scale=(scale,scale,64.25 if uid==1 else scale)
        if uid==4:root.location=(-22,0,0)
bpy.context.window_manager.keyconfigs.update()
state={};capture={'points':None,'pixels':None}


def capture_pixels():
    """Read the drawn region, not an undefined window front buffer in a timer.

    screen.screenshot can return black under Xvfb/software OpenGL. POST_PIXEL
    has the actual viewport framebuffer bound and works on the desktop too.
    """
    if not capture['points'] or 'context' not in state:return
    window,area,region=state['context']
    if bpy.context.window!=window or bpy.context.area!=area or bpy.context.region!=region:return
    try:
        import gpu
        framebuffer=gpu.state.active_framebuffer_get()
        x,y,width,height=gpu.state.viewport_get();pixels=[]
        for px,py in capture['points']:
            assert 0<=px<width and 0<=py<height,('Pixel sample outside viewport',px,py,width,height)
            buffer=framebuffer.read_color(x+int(px),y+int(py),1,1,3,0,'UBYTE')
            buffer.dimensions=3
            pixels.append(tuple(int(c) for c in buffer))
        capture['pixels']=pixels;capture['points']=None
    except Exception:traceback.print_exc();os._exit(1)


capture_handle=bpy.types.SpaceView3D.draw_handler_add(capture_pixels,(),'WINDOW','POST_PIXEL')


def records():return [wire.serialize(r).hex() for r in studio.prefab_records(scene.prefab_roots(),Vector())]


def run():
    window,area,region=state['context'];space=area.spaces.active;view=space.region_3d
    def event(kind,value='PRESS',point=None,**kwargs):
        x,y=point or (region.width//2,region.height//2)
        window.event_simulate(type=kind,value=value,x=region.x+int(x),y=region.y+int(y),**kwargs)
    def key(kind,**kwargs):
        event(kind,**kwargs);kwargs.pop('unicode',None);event(kind,'RELEASE',**kwargs)
    def point(v):
        p=location_3d_to_region_2d(region,view,Vector(v));assert p is not None
        return tuple(p)
    def click(p,**kwargs):
        event('MOUSEMOVE','NOTHING',p);event('LEFTMOUSE','PRESS',p,**kwargs);event('LEFTMOUSE','RELEASE',p,**kwargs)
    def shot(name):
        path=output/(name+'.png');bpy.ops.screen.screenshot(filepath=str(path));return path
    def pixels(points):
        capture.update(points=points,pixels=None)
        for _ in range(50):
            area.tag_redraw();yield .1
            if capture['pixels'] is not None:return capture['pixels']
        raise AssertionError('Viewport did not draw the requested pixel samples')
    def resolve(instance):return next(o for o in scene.prefab_roots() if o['ruster_instance']==instance)
    event('ESC');yield .4
    space.show_gizmo=False
    view.view_rotation=Quaternion((1,0,0,0));view.view_location=(0,0,0)
    view.view_distance=180;view.view_perspective='ORTHO';space.clip_start=.1;space.clip_end=1000
    bpy.context.scene.ruster_show_volumes=True;space.overlay.show_overlays=True;bpy.context.view_layer.update()
    roots=list(volumes.visible_volumes(bpy.context))
    assert len(roots)==(118 if project else 4),[(o.name,o.get('ruster_uid')) for o in roots]
    assert all(volumes.boundary(o)['lines'] for o in roots),'Missing native collider descriptions'
    state['baseline']=records();state['fingerprint']=quitting.fingerprint()
    placement.select([]);event('MOUSEMOVE','NOTHING',(10,10));draws.clear();area.tag_redraw();yield .5
    assert draws and len(draws[-1])==len(roots),'Bounds did not draw without hover/gizmos'
    shot('volumes-outside-unhovered')
    assert all(volumes.boundary(o)['surface_batch'] is not None for o in roots),'Persistent fills did not draw'
    if not project:
        assert {volumes.semantic_type(o) for o in roots}=={'SAFE_ZONE','NO_BUILD','NO_ENTRY'}
        sample=point((-21,1,0))
        tinted,enclosing=yield from pixels([sample,point((-13,1,0))])
        bpy.context.scene.ruster_show_volumes=False;yield .3
        shot('volumes-fill-comparison-disabled')
        clear,=yield from pixels([sample])
        assert sum(abs(a-b) for a,b in zip(tinted,clear))>6,('Persistent fill was not visible',tinted,clear)
        assert tinted[1]-tinted[0]>enclosing[1]-enclosing[0]+3,('Nested safe-zone fill lost its type colour',tinted,enclosing)
        bpy.context.scene.ruster_show_volumes=True;yield .3
    inner=next(o for o in roots if o.get('ruster_uid')==('3521578167' if project else '2') and
        max(o.scale)<100 and (not project or o.matrix_world.translation.x<0))
    instance=inner['ruster_instance'];lines=volumes.boundary(inner)['lines'];hit=None
    for a,b in zip(lines[::2],lines[1::2]):
        p=point((a+b)/2)
        if 20<p[0]<region.width-20 and 20<p[1]<region.height-20 and inner in volumes.candidates(bpy.context,p):hit=p;break
    assert hit,'No pickable projected inner boundary'
    space.show_gizmo=True;yield .3
    assert volumes.hover_watch_present(window),'Passive hover observer was not installed'
    event('MOUSEMOVE','NOTHING',hit);yield .3
    assert volumes._hover.get(volumes.region_key(bpy.context)) in {o['ruster_instance'] for o in volumes.candidates(bpy.context,hit)},'Native gizmos swallowed volume edge hover'
    event('MOUSEMOVE','NOTHING',(10,10));event('MOUSEMOVE','NOTHING',hit);yield .1
    assert volumes._hover.get(volumes.region_key(bpy.context)) in {o['ruster_instance'] for o in volumes.candidates(bpy.context,hit)},'Coalescing dropped the final edge hover'
    if not project:
        body=point((0,0,0));volumes._cycle=None;volumes._last_press=None;click(body);yield .3
        assert bpy.context.object['ruster_uid']=='2','Clicking the filled middle did not select the inner volume'
        volumes._cycle=None;volumes._last_press=None
    click(hit);yield .3
    hits=volumes.candidates(bpy.context,hit)
    shot('volume-pick-result')
    assert bpy.context.object in hits and bpy.context.object.select_get(),'Boundary click missed native placement'
    if not project:
        assert bpy.context.object['ruster_uid']=='2','Enclosing box swallowed inner click'
        click(hit);yield .3
        assert bpy.context.object['ruster_uid']=='3','Repeated click did not cycle coincident bounds'
        click(hit);yield .3
        assert bpy.context.object['ruster_uid']=='1','Overlap cycling did not reach the enclosing face'
        click(hit);yield .3
        assert bpy.context.object['ruster_uid']=='2'
        body_hits=volumes.candidates(bpy.context,point((0,0,0)))
        assert body_hits[0]['ruster_uid'] in {'2','3'} and body_hits[-1]['ruster_uid']=='1','Enclosing fill swallowed nested volumes'
    placement.select([]);volumes._cycle=None;click(hit,shift=True);yield .3
    chosen=bpy.context.object['ruster_instance'];assert resolve(chosen).select_get()
    click(hit,shift=True);yield .3
    assert not resolve(chosen).select_get(),'Shift-click did not toggle selection'
    placement.select([resolve(instance)])
    original_location=tuple(resolve(instance).location);original_scale=tuple(resolve(instance).scale)
    bpy.ops.ed.undo_push(message='Before volume transform')
    key('G');yield .2
    key('X');key('THREE',unicode='3');key('RET');yield .4
    assert abs(resolve(instance).location.x-original_location[0]-3)<1e-4,'Native move failed'
    key('S');yield .2
    key('TWO',unicode='2');key('RET');yield .4
    assert all(abs(a-b*2)<1e-4 for a,b in zip(resolve(instance).scale,original_scale)),'Native scale failed'
    key('Z',ctrl=True);yield .4
    assert all(abs(a-b)<1e-4 for a,b in zip(resolve(instance).scale,original_scale)),'Scale undo failed'
    key('Z',ctrl=True);yield .4
    assert all(abs(a-b)<1e-4 for a,b in zip(resolve(instance).location,original_location)),'Move undo failed'
    key('Z',ctrl=True,shift=True);yield .4
    assert abs(resolve(instance).location.x-original_location[0]-3)<1e-4,'Move redo failed'
    key('Z',ctrl=True,shift=True);yield .4
    assert all(abs(a-b*2)<1e-4 for a,b in zip(resolve(instance).scale,original_scale)),'Scale redo failed'
    key('Z',ctrl=True);yield .3
    key('Z',ctrl=True);yield .3
    assert records()==state['baseline'],'Native transforms did not restore exactly'
    # The native tool can draw its handles over the volume overlay. Blender's
    # event_simulate does not hit native gizmos even in a volume-free control;
    # G/S above exercise the same native transform operators and undo stack.
    space.show_gizmo=True
    view.view_location=resolve(instance).matrix_world.translation;view.view_distance=50
    bpy.ops.wm.tool_set_by_id(name='builtin.move');yield .5
    shot('volumes-move-gizmo')
    bpy.ops.wm.tool_set_by_id(name='builtin.select_box');space.show_gizmo=True
    view.view_perspective='PERSP';view.view_location=(0,0,0);view.view_distance=20
    center=(region.width//2,region.height//2)
    event('MOUSEMOVE','NOTHING',center);draws.clear();yield .4
    assert draws;shot('volumes-inside-unhovered');distance=view.view_distance
    event('WHEELUPMOUSE');yield .3
    assert view.view_distance<distance,'Wheel zoom swallowed inside enclosing volume'
    rotation=view.view_rotation.copy()
    event('MIDDLEMOUSE','PRESS',center);yield .2
    event('MOUSEMOVE','NOTHING',(center[0]+70,center[1]+40));yield .2
    event('MIDDLEMOUSE','RELEASE',(center[0]+70,center[1]+40));yield .3
    assert rotation.rotation_difference(view.view_rotation).angle>.01,'Orbit was captured'
    target=view.view_location.copy()
    event('MIDDLEMOUSE','PRESS',center,shift=True);yield .2
    event('MOUSEMOVE','NOTHING',(center[0]+50,center[1]),shift=True);yield .2
    event('MIDDLEMOUSE','RELEASE',(center[0]+50,center[1]),shift=True);yield .3
    assert (view.view_location-target).length>.01,'Pan was captured'
    view.view_rotation=Quaternion((1,0,0,0));view.view_location=resolve(instance).matrix_world.translation
    view.view_distance=20;yield .3
    inside_hit=None;lines=volumes.boundary(resolve(instance))['lines']
    for a,b in zip(lines[::2],lines[1::2]):
        projected=volumes.volume_picking.project_segment(view.perspective_matrix @ a.to_4d(),view.perspective_matrix @ b.to_4d(),region.width,region.height)
        if projected:
            p=tuple((projected[0][i]+projected[1][i])/2 for i in range(2))
            if resolve(instance) in volumes.candidates(bpy.context,p):inside_hit=p;break
    assert inside_hit,'Bounds not pickable while camera inside enclosing volume'
    volumes._cycle=None;click(inside_hit);yield .3
    assert bpy.context.object in volumes.candidates(bpy.context,inside_hit)
    shot('volumes-inside-selected')
    if not project:
        view.view_location=(0,0,0);view.view_distance=3;yield .3
        body=(region.width//2,region.height//2);volumes._cycle=None;volumes._last_press=None
        click(body);yield .3
        assert bpy.context.object['ruster_uid']=='2','Face selection failed with the eye inside the volume itself'
        inside_hit=body
    bpy.context.scene.ruster_show_volumes=False;draws.clear();yield .4
    assert not draws and not volumes.candidates(bpy.context,inside_hit)
    assert records()==state['baseline'] and quitting.fingerprint()==state['fingerprint']
    bpy.context.scene.ruster_show_volumes=True;space.overlay.show_overlays=False;draws.clear();yield .4
    assert not draws and not volumes.candidates(bpy.context,inside_hit)
    space.overlay.show_overlays=True;draws.clear();yield .4
    assert draws and records()==state['baseline']
    if project:assert hashlib.sha256(Path(project).read_bytes()).hexdigest()==source_hash,'Source project was written'
    print('RUSTER_GUI_VOLUME_INTERACTION_OK '+json.dumps({'placements':len(scene.prefab_roots()),'volumes':len(roots),'output':str(output)}),flush=True)
    os._exit(0)


steps=run()


def tick():
    try:
        window=bpy.context.window_manager.windows[0];area=next(a for a in window.screen.areas if a.type=='VIEW_3D')
        region=next(r for r in area.regions if r.type=='WINDOW');state['context']=(window,area,region)
        with bpy.context.temp_override(window=window,area=area,region=region):return next(steps)
    except Exception:traceback.print_exc();os._exit(1)


bpy.app.timers.register(tick,first_interval=2.)
