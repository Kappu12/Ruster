"""Read a bounded texture mip directly, without decoding larger source levels."""
MAX_TEXTURE_EDGE = 512


def preview_image(texture):
    from UnityPy.enums import TextureFormat, BuildTarget
    from UnityPy.export.Texture2DConverter import parse_image_data
    from UnityPy.helpers.ResourceReader import get_resource_data
    fmt=TextureFormat(texture.m_TextureFormat)
    width,height=texture.m_Width,texture.m_Height
    blocks={'DXT1':8,'DXT5':16,'BC4':8,'BC5':16,'BC6H':16,'BC7':16}
    pixels={'Alpha8':1,'R8':1,'RGB24':3,'RGBA32':4,'ARGB32':4,'BGRA32':4,'RGB565':2,'RGBAHalf':8}
    def level_size(w,h):
        if fmt.name in blocks:return max(1,(w+3)//4)*max(1,(h+3)//4)*blocks[fmt.name]
        if fmt.name in pixels:return w*h*pixels[fmt.name]
        return None
    offset=0
    for _ in range(max(1,getattr(texture,'m_MipCount',1) or 1)-1):
        if max(width,height)<=MAX_TEXTURE_EDGE:break
        size=level_size(width,height)
        if size is None:break
        offset+=size;width=max(1,width//2);height=max(1,height//2)
    if max(width,height)>MAX_TEXTURE_EDGE:
        # Some small uncompressed textures have no mip chain. A bounded source
        # decode is still safe; never decode a full 4K/8K source as a fallback.
        if max(width,height)>2048:
            raise ValueError(f'Texture {texture.m_Name} has no readable mip within {MAX_TEXTURE_EDGE}px')
        from PIL import Image
        image=texture.image
        image.thumbnail((MAX_TEXTURE_EDGE,MAX_TEXTURE_EDGE),Image.Resampling.LANCZOS)
        return image
    size=level_size(width,height)
    if size is None:
        # Small platform/crunched textures still use UnityPy's native decoder.
        return texture.image
    if texture.image_data:
        data=texture.image_data[offset:offset+size]
    else:
        stream=texture.m_StreamData
        if not stream or offset+size>stream.size:raise ValueError('Texture mip exceeds its source stream')
        data=get_resource_data(stream.path,texture.object_reader.assets_file,stream.offset+offset,size)
    if len(data)!=size:raise ValueError('Texture mip is truncated')
    return parse_image_data(data,width,height,fmt,texture.object_reader.version,
                            getattr(texture.object_reader,'platform',BuildTarget.UnknownPlatform),
                            getattr(texture,'m_PlatformBlob',None))
