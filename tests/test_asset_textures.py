from types import SimpleNamespace
import pytest
from UnityPy.enums import TextureFormat,BuildTarget
from ruster.assets.textures import preview_image


def texture(width=4096,height=4096,mips=13):
    return SimpleNamespace(m_Name='test',m_TextureFormat=TextureFormat.DXT1,
        m_Width=width,m_Height=height,m_MipCount=mips,image_data=b'',
        m_StreamData=SimpleNamespace(path='source.resS',offset=123,size=12*1024*1024),
        object_reader=SimpleNamespace(assets_file=object(),version=(2022,3,1,0),platform=BuildTarget.StandaloneWindows64))


def test_large_texture_reads_only_selected_mip(monkeypatch):
    from UnityPy.helpers import ResourceReader
    from UnityPy.export import Texture2DConverter
    reads=[]
    def read(path,file,offset,size):
        reads.append((path,offset,size));return bytes(size)
    monkeypatch.setattr(ResourceReader,'get_resource_data',read)
    monkeypatch.setattr(Texture2DConverter,'parse_image_data',lambda data,w,h,*args:(w,h,len(data)))
    assert preview_image(texture())==(2048,2048,2048*2048//2)
    assert reads==[('source.resS',123+4096*4096//2,2048*2048//2)]


def test_large_texture_without_mip_is_rejected_before_read(monkeypatch):
    from UnityPy.helpers import ResourceReader
    monkeypatch.setattr(ResourceReader,'get_resource_data',lambda *args:pytest.fail('Must not read the full texture'))
    with pytest.raises(ValueError,match='2048px'):preview_image(texture(mips=1))


def test_truncated_texture_stream_is_rejected():
    source=texture(64,64,1);source.m_StreamData.size=10
    with pytest.raises(ValueError,match='exceeds'):preview_image(source)
