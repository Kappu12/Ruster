"""Adapter regressions using current UnityPy component layouts and original data."""
import gzip
import json
from types import SimpleNamespace as S
from PIL import Image
from UnityPy.classes.generated import ComponentPair
from UnityPy.enums import TextureFormat, BuildTarget
from ruster.assets.worker import export_prefab


class Reader:
    sequence=100
    def __init__(self,kind,data):
        Reader.sequence+=1
        self.path_id=Reader.sequence;self.type=S(name=kind);self.data=data
        self.assets_file=S(name='CAB-test')
    def read(self):return self.data


class Pointer:
    def __init__(self,reader=None):self.reader=reader;self.path_id=reader.path_id if reader else 0
    def deref(self):return self.reader
    def read(self):return self.reader.read()


class MeshHandler:
    def __init__(self,mesh):self.src=mesh
    def process(self):
        self.m_Vertices=[[0,0,0],[1,0,0],[0,1,0]]
        self.m_UV0=[[0,0],[1,0],[0,1]]
    def get_triangles(self):return [[[0,1,2]]]


def graph():
    texture=Reader('Texture2D',S(m_Name='fixture',m_Width=2,m_Height=2,m_MipCount=1,
        m_TextureFormat=TextureFormat.RGBA32,image_data=Image.new('RGBA',(2,2),(255,100,20,255)).tobytes(),
        object_reader=S(version=(2022,3,1,0),platform=BuildTarget.StandaloneWindows64)))
    texenv=S(m_Texture=Pointer(texture),m_Scale=S(x=2,y=3),m_Offset=S(x=.2,y=.3))
    mat=Reader('Material',S(m_Name='Example',m_SavedProperties=S(m_Floats=[('_Glossiness',.25),('_Metallic',.4)],
        m_Colors=[],m_TexEnvs=[('_MainTex',texenv)])))
    renderers=[];children=[]
    for i in range(2):
        renderer=Reader('MeshRenderer',S(m_Enabled=True,m_Materials=[Pointer(mat)]));renderers.append(renderer)
        mesh=Reader('Mesh',S())
        transform=Reader('Transform',S(m_LocalPosition=S(x=i,y=0,z=0),m_LocalRotation=S(w=1,x=0,y=0,z=0),
            m_LocalScale=S(x=1,y=1,z=1),m_Children=[]))
        filter_=Reader('MeshFilter',S(m_Mesh=Pointer(mesh)))
        go=Reader('GameObject',S(m_Name='LOD'+str(i),m_IsActive=True,m_Component=[ComponentPair(component=Pointer(c)) for c in (transform,filter_,renderer)]))
        transform.data.m_GameObject=Pointer(go);children.append(Pointer(transform))
    transform=Reader('Transform',S(m_LocalPosition=S(x=0,y=0,z=0),m_LocalRotation=S(w=1,x=0,y=0,z=0),
        m_LocalScale=S(x=1,y=1,z=1),m_Children=children))
    lod=Reader('LODGroup',S(m_LODs=[S(renderers=[S(renderer=Pointer(r))]) for r in renderers]))
    return Reader('GameObject',S(m_Name='Root',m_IsActive=True,m_Component=[ComponentPair(component=Pointer(c)) for c in (transform,lod)]))


def test_modern_lod_material_and_texture_conversion(tmp_path,monkeypatch):
    monkeypatch.setattr('UnityPy.helpers.MeshHelper.MeshHandler',MeshHandler)
    output=tmp_path/'asset.json.gz'
    warnings=export_prefab(None,graph(),output,42,'assets/example.prefab','revision-1')
    result=json.loads(gzip.decompress(output.read_bytes()))
    assert not warnings
    assert len(result['meshes'])==1  # LOD1 must not overlap LOD0 in Blender.
    material=next(iter(result['materials'].values()))
    assert material['roughness']==.75 and material['metallic']==.4
    assert material['uv_scale']==[2,3] and material['uv_offset']==[.2,.3]
    assert (tmp_path/material['texture']).is_file()
    from ruster.assets import geometry
    mesh=next(iter(result['meshes'].values()))
    assert isinstance(mesh['vertices'],int) and mesh['vertices']==3
    assert len(geometry.read(tmp_path/mesh['buffer'])[0])==3


def test_texture_cache_revision_changes_filename(tmp_path,monkeypatch):
    monkeypatch.setattr('UnityPy.helpers.MeshHelper.MeshHandler',MeshHandler)
    output=tmp_path/'asset.json.gz';root=graph()
    export_prefab(None,root,output,42,'assets/example.prefab','revision-1')
    first=json.loads(gzip.decompress(output.read_bytes()))
    export_prefab(None,root,output,42,'assets/example.prefab','revision-2')
    second=json.loads(gzip.decompress(output.read_bytes()))
    assert next(iter(first['materials'].values()))['texture']!=next(iter(second['materials'].values()))['texture']


def test_sound_only_prefab_is_a_marker_not_a_failed_mesh(tmp_path):
    transform=Reader('Transform',S(m_LocalPosition=S(x=0,y=0,z=0),m_LocalRotation=S(w=1,x=0,y=0,z=0),
        m_LocalScale=S(x=1,y=1,z=1),m_Children=[]))
    sound=Reader('MonoBehaviour',S(soundDefinition=Pointer(Reader('MonoBehaviour',S()))))
    root=Reader('GameObject',S(m_Name='sound',m_IsActive=True,m_Component=[ComponentPair(component=Pointer(c)) for c in (transform,sound)]))
    output=tmp_path/'sound.json.gz'
    assert not export_prefab(None,root,output,1188595389,'assets/sound.prefab')
    asset=json.loads(gzip.decompress(output.read_bytes()))
    assert asset['marker']=='SOUND' and not asset['meshes']


def first_material(root):
    transform=root.read().m_Component[0].component.read()
    renderer=transform.m_Children[0].read().m_GameObject.read().m_Component[2].component.read()
    return renderer.m_Materials[0].read()


def test_hidden_hose_preserves_hdr_emission_and_blending(tmp_path,monkeypatch):
    monkeypatch.setattr('UnityPy.helpers.MeshHelper.MeshHandler',MeshHandler)
    root=graph();mat=first_material(root)
    mat.m_SavedProperties.m_Colors=[('_Color',S(r=0,g=.9687,b=1,a=1)),
        ('_EmissionColor',S(r=0,g=1.0353,b=1.498,a=1))]
    mat.m_SavedProperties.m_Floats=[('_Mode',3)]
    mat.m_SavedProperties.m_TexEnvs=[]
    output=tmp_path/'hose.json.gz'
    assert not export_prefab(None,root,output,147092032,'assets/hose.prefab')
    spec=next(iter(json.loads(gzip.decompress(output.read_bytes()))['materials'].values()))
    assert spec['emission']==[0,1.0353,1.498,1]
    assert spec['alpha_blend'] and not spec['alpha_clip']


def test_concrete_preserves_packed_metallic_gloss_map(tmp_path,monkeypatch):
    monkeypatch.setattr('UnityPy.helpers.MeshHelper.MeshHandler',MeshHandler)
    root=graph();root.read().m_IsActive=False;mat=first_material(root)
    mat.m_SavedProperties.m_Floats=[('_Metallic',1),('_Glossiness',1),('_GlossMapScale',.7)]
    base=mat.m_SavedProperties.m_TexEnvs[0][1]
    mat.m_SavedProperties.m_TexEnvs.append(('_MetallicGlossMap',base))
    output=tmp_path/'concrete.json.gz'
    assert not export_prefab(None,root,output,3471408108,'assets/concrete.prefab')
    spec=next(iter(json.loads(gzip.decompress(output.read_bytes()))['materials'].values()))
    assert spec['metallic_gloss_texture']==spec['texture']
    assert spec['metallic_gloss_texture_uv_scale']==[2,3] and spec['gloss_map_scale']==.7


def test_entity_follows_its_separate_visual_prefab_reference(tmp_path,monkeypatch):
    monkeypatch.setattr('UnityPy.helpers.MeshHelper.MeshHandler',MeshHandler)
    target=graph();target.read().m_IsActive=False
    target_transform=target.read().m_Component[0].component
    target_transform.read().m_GameObject=Pointer(target)
    transform=Reader('Transform',S(m_LocalPosition=S(x=0,y=0,z=0),m_LocalRotation=S(w=1,x=0,y=0,z=0),
        m_LocalScale=S(x=1,y=1,z=1),m_Children=[target_transform]))
    entity=Reader('MonoBehaviour',S(prefab=S(guid='tree-model-guid')))
    audio=Reader('AudioSource',S())
    root=Reader('GameObject',S(m_Name='Tree entity',m_IsActive=False,
        m_Component=[ComponentPair(component=Pointer(c)) for c in (transform,entity,audio)]))
    requests=[]
    env=S(resolve_prefab=lambda guid:requests.append(guid) or target)
    output=tmp_path/'tree.json.gz'
    assert not export_prefab(env,root,output,44,'assets/tree.prefab')
    asset=json.loads(gzip.decompress(output.read_bytes()))
    assert requests==['tree-model-guid'] and len(asset['meshes'])==1
    assert asset['nodes'][1]['parent']==0 and not asset['marker']


def test_explicitly_selected_lod_prefab_is_not_filtered_out(tmp_path,monkeypatch):
    monkeypatch.setattr('UnityPy.helpers.MeshHelper.MeshHandler',MeshHandler)
    root=graph();root.read().m_Name='assets/props/model_lod1.prefab'
    output=tmp_path/'lod-prefab.json.gz'
    assert not export_prefab(None,root,output,48,'assets/props/model_lod1.prefab')
    asset=json.loads(gzip.decompress(output.read_bytes()))
    assert len(asset['meshes'])==1 and not asset['marker']


def test_terrain_stamp_is_a_named_helper_not_a_failed_model(tmp_path):
    transform=Reader('Transform',S(m_LocalPosition=S(x=0,y=0,z=0),m_LocalRotation=S(w=1,x=0,y=0,z=0),
        m_LocalScale=S(x=1,y=1,z=1),m_Children=[]))
    modifier=Reader('MonoBehaviour',S(HeightMap=1,size=S(x=1000,y=75,z=1000)))
    root=Reader('GameObject',S(m_Name='Canyon',m_IsActive=False,
        m_Component=[ComponentPair(component=Pointer(c)) for c in (transform,modifier)]))
    output=tmp_path/'canyon.json.gz'
    assert not export_prefab(None,root,output,45,'assets/canyon.prefab')
    asset=json.loads(gzip.decompress(output.read_bytes()))
    assert asset['marker']=='TERRAIN' and asset['helper_bounds']==[1000,75,1000] and not asset['meshes']


def test_cutout_shader_tags_preserve_foliage_transparency(tmp_path,monkeypatch):
    monkeypatch.setattr('UnityPy.helpers.MeshHelper.MeshHandler',MeshHandler)
    root=graph();mat=first_material(root)
    mat.m_StringTagMap=[('RenderType','TransparentCutout')]
    output=tmp_path/'foliage.json.gz'
    assert not export_prefab(None,root,output,46,'assets/foliage.prefab')
    spec=next(iter(json.loads(gzip.decompress(output.read_bytes()))['materials'].values()))
    assert spec['alpha_clip'] and not spec['alpha_blend']


def test_current_rust_base_color_and_mask_properties_are_loaded(tmp_path,monkeypatch):
    monkeypatch.setattr('UnityPy.helpers.MeshHelper.MeshHandler',MeshHandler)
    root=graph();mat=first_material(root)
    base=mat.m_SavedProperties.m_TexEnvs[0][1]
    mat.m_SavedProperties.m_TexEnvs=[('_BaseColorMap',base),('_MaskMap',base)]
    mat.m_SavedProperties.m_Floats=[('_AlphaCutoffEnable',1),('_AlphaCutoff',.35)]
    output=tmp_path/'tree.json.gz'
    assert not export_prefab(None,root,output,47,'assets/tree.prefab')
    spec=next(iter(json.loads(gzip.decompress(output.read_bytes()))['materials'].values()))
    assert spec['texture'] and spec['metallic_gloss_texture']
    assert spec['alpha_clip'] and spec['alpha_cutoff']==.35
