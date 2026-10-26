"""Linked hierarchy bounds/exports match evaluated instances; no game assets."""
import gzip,json,os,sys,tempfile,traceback
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
if '--' in sys.argv:sys.path.insert(0,sys.argv[sys.argv.index('--')+1])
import bpy,ruster
from mathutils import Matrix,Vector
from ruster import scene,studio,mcp_building,mcp_bridge,model_export,protection,placement
from ruster.core import wire
from ruster.assets import catalog
from tests.fixtures import triangle_asset


def near(actual,expected,label):
    assert actual and expected,(label,actual,expected)
    for field in ('min','max','dimensions'):
        assert max(abs(a-b) for a,b in zip(actual[field],expected[field]))<2e-4,(label,field,actual,expected)


def evaluated(roots,vertices=False):
    roots=set(roots)
    return mcp_building.bounds([item.matrix_world@Vector(corner)
        for item in bpy.context.evaluated_depsgraph_get().object_instances
        if item.is_instance and item.parent.original in roots and item.object.type=='MESH'
        for corner in ([v.co for v in item.object.data.vertices] if vertices else item.object.bound_box)])


def check(root):
    bpy.context.view_layer.update();expected=evaluated([root])
    before=root.matrix_world.copy();record=wire.serialize(placement.world_record(root))
    original_scene=bpy.context.scene;geometry=evaluated([root],vertices=True)
    near(mcp_building.object_bounds(root),expected,'linked model bounds')
    info=mcp_bridge.object_info(None,root.name)
    near(info['world_bounds'],expected,'typed MCP world bounds')
    with model_export.realized_scene([root]) as exported:
        actual=mcp_building.bounds([obj.matrix_world@v.co
            for obj in exported.objects if obj.type=='MESH' for v in obj.data.vertices])
        near(actual,geometry,'realized export geometry')
    assert bpy.context.scene==original_scene and root.matrix_world==before
    assert wire.serialize(placement.world_record(root))==record,'Bounds/export changed the Rust placement'
    assert all(obj.library and not obj.is_editable for obj in root.instance_collection.all_objects)


def run():
    with tempfile.TemporaryDirectory(prefix='ruster-model-bounds-') as folder:
        os.environ['RUSTER_USER_DIR']=folder;ruster.register();studio.new_prefab()
        directory=scene.cache_dir()/'prefabs';directory.mkdir(parents=True,exist_ok=True)
        asset=triangle_asset(123456)
        def node(name,parent,position=(0,0,0),rotation=(1,0,0,0),scale=(1,1,1),mesh=None):
            return dict(name=name,parent=parent,position=position,rotation=rotation,scale=scale,
                mesh=mesh,materials=['mat'] if mesh else [])
        # A translated/rotated/scaled parent, a grandchild and a second mesh.
        # The source prefab root transform belongs to the placement, so ignore it.
        asset['nodes']=[node('root',None,(33,44,55),(.5,.5,.5,.5),(4,5,6)),
            node('skin',0,(.056,0,-.598)),
            node('hinge',1,(-.04,1.17,0),(.70710678,0,.70710678,0),(1.1,.9,1.3)),
            node('mesh',2,(-.2,.3,.4),(.92387953,.38268343,0,0),mesh='mesh'),
            node('other',0,(.49,.98,.29),scale=(.5,.8,1.2),mesh='mesh')]
        (directory/'123456.json.gz').write_bytes(gzip.compress(json.dumps(asset).encode()))
        db=catalog.connect(scene.cache_dir());db.execute('INSERT INTO names VALUES(?,?)',(123456,asset['path']));db.commit();db.close()
        roots=[]
        for position,rotation,scale in (((1.2617816,5.3716497,-.0725486),(0,0,90),(1,1,1)),
                ((4.659,4.8287024,.0250001),(0,0,180),(.8939993,1.3121514,1.1949999))):
            root=scene.root_object([wire.encode(2,0,123456)],bpy.context.scene.collection)
            mcp_bridge.set_transform(root,position,rotation,scale)
            assert scene.attach_visual(root);roots.append(root);check(root)
        # Group bounds must compose placement and asset hierarchies once each.
        group=placement.group(roots);mcp_bridge.set_transform(group,[3,-2,4],[13,0,25],[1.3,1.3,1.3])
        for root in roots:check(root)
        near(mcp_building.object_bounds(group),evaluated(roots),'group bounds')
        # Library IDs are not in the scene. Include inverse-parent matrices and
        # the collection offset, even when their saved world matrices are stale.
        collection=bpy.data.collections.new('Parent inverse fixture')
        parent=bpy.data.objects.new('Unlinked parent',None);collection.objects.link(parent)
        parent.location=(.4,-.8,1.2);parent.rotation_euler=(.2,.3,.7);parent.scale=(2,1,1.5)
        mesh=bpy.data.meshes.new('Original fixture geometry')
        mesh.from_pydata([(0,0,0),(2,0,0),(0,1,3)],[],[(0,1,2)])
        child=bpy.data.objects.new('Unlinked mesh',mesh);collection.objects.link(child)
        child.parent=parent;child.location=(.3,.1,-.4);child.rotation_euler=(.4,-.2,.1)
        child.matrix_parent_inverse=Matrix.Translation((.6,.2,-.3))
        collection.instance_offset=(.3,-.2,.5)
        root=scene.root_object([wire.encode(2,0,654321)],bpy.context.scene.collection)
        root.instance_type='COLLECTION';root.instance_collection=protection.freeze(collection,654321,'bounds-inverse-fixture',verified=True)
        root['ruster_visual']=True
        mcp_bridge.set_transform(root,[7,2,-1],[20,-15,75],[-.8,1.4,1.1]);check(root)
        # A saved and reopened linked library must work without rebuilding it.
        path=Path(folder)/'linked-bounds.blend';bpy.ops.wm.save_as_mainfile(filepath=str(path),check_existing=False)
        bpy.ops.wm.open_mainfile(filepath=str(path),load_ui=False,use_scripts=False)
        for root in scene.prefab_roots():check(root)
        ruster.unregister()
    print('RUSTER_LINKED_MODEL_BOUNDS_OK',flush=True)


try:run()
except Exception:traceback.print_exc();os._exit(1)
