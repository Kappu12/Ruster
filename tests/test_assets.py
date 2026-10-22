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


def test_texture_cache_revision_changes_filename(tmp_path,monkeypatch):
    monkeypatch.setattr('UnityPy.helpers.MeshHelper.MeshHandler',MeshHandler)
    output=tmp_path/'asset.json.gz';root=graph()
    export_prefab(None,root,output,42,'assets/example.prefab','revision-1')
    first=json.loads(gzip.decompress(output.read_bytes()))
    export_prefab(None,root,output,42,'assets/example.prefab','revision-2')
    second=json.loads(gzip.decompress(output.read_bytes()))
    assert next(iter(first['materials'].values()))['texture']!=next(iter(second['materials'].values()))['texture']
