import numpy as np
import pytest
import lz4.block
from ruster.core import legacy_lz4,wire


@pytest.mark.parametrize('length',(0,1,8,128,4096,65536,1024*1024))
def test_native_and_fallback_decode_identical_legacy_blocks(length,monkeypatch):
    rng=np.random.default_rng(9)
    data=(rng.integers(0,256,4096,dtype=np.uint8).tobytes()*((length//4096)+1))[:length]
    compressed=lz4.block.compress(data,store_size=False)
    assert legacy_lz4.decompress_block(compressed,len(data))==data
    monkeypatch.setattr(legacy_lz4,'_native_lz4',None)
    assert legacy_lz4.decompress_block(compressed,len(data))==data


@pytest.mark.parametrize('native',(True,False))
def test_size_mismatch_and_limits_are_rejected(native,monkeypatch):
    if not native:monkeypatch.setattr(legacy_lz4,'_native_lz4',None)
    data=b'Rust map '*1024;compressed=lz4.block.compress(data,store_size=False)
    with pytest.raises(wire.FormatError):legacy_lz4.decompress_block(compressed,len(data)+1)
    with pytest.raises(wire.FormatError):legacy_lz4.decompress_block(compressed,len(data)-1)
    with pytest.raises(wire.FormatError):legacy_lz4.decompress_block(compressed,legacy_lz4.MAX_CHUNK+1)
    with pytest.raises(wire.FormatError):legacy_lz4.decompress_block(compressed,-1)


def test_native_errors_are_format_errors():
    with pytest.raises(wire.FormatError):legacy_lz4.decompress_block(b'\xff\0',100)
