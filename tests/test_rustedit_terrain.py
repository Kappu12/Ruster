import io

import numpy as np
from PIL import Image
import pytest

from ruster.core import rustedit_terrain, wire
from ruster.core.ground import flat_ground
from ruster.core.rustedit_prefab import RustEditPrefab
from ruster.core.terrain import Terrain


def pixels(data):
    with Image.open(io.BytesIO(data)) as image:
        assert image.mode == 'RGBA'
        return np.array(image)


def test_native_masks_share_the_prefab_pivot_and_keep_rustedit_channels():
    terrain = Terrain(flat_ground(height=12.5, biome='Jungle'))
    origin = (62.5, -62.5, 15.)
    native = terrain.grid('splat')
    native[:] = np.array([10, 30, 40, 20, 10, 55, 40, 50], dtype='u1')[:, None, None]
    # Divide the crop at its own centre, away from the map origin.
    south = int((origin[1] / terrain.size + .5) * native.shape[-1])
    terrain.grid('biome')[:, :south] = np.array([10, 40, 25, 15, 165])[:, None, None]
    terrain.grid('alpha')[0, :south] = 0
    terrain.grid('topology')[0, south:] = 0x21000405
    terrain.grid('topology')[0, :south] = 0x08000002

    masks = rustedit_terrain.capture(terrain, origin, 24)
    assert set(masks) == set(rustedit_terrain.TERRAIN_SUFFIXES)
    assert tuple(pixels(masks['.splat0'])[0, 0]) == (10, 30, 40, 20)
    assert tuple(pixels(masks['.splat1'])[0, 0]) == (10, 55, 40, 50)
    biome = pixels(masks['.biome'])
    assert 255 - int(biome[0, 0].sum()) == 255
    assert 255 - int(biome[-1, 0].sum()) == 165
    alpha = pixels(masks['.alpha'])
    assert tuple(alpha[0, 0]) == (0, 0, 0, 255)
    assert tuple(alpha[-1, 0]) == (0, 0, 0, 0)
    topology = pixels(masks['.topology'])
    assert tuple(topology[0, 0]) == (5, 4, 0, 33)
    assert tuple(topology[-1, 0]) == (2, 0, 0, 8)
    low, green, high, alpha = map(int, pixels(masks['.heights'])[0, 0])
    relative_height = int.from_bytes(bytes([low, high]), 'little', signed=True) * 1000 / 32766
    assert (green, alpha) == (0, 1)
    assert relative_height == pytest.approx(-2.5, abs=.04)

    prefab = RustEditPrefab.create([[wire.encode(2, 0, 123)]])
    prefab.set_terrain_options(24, 5)
    reopened = RustEditPrefab.read(prefab.write())
    options = wire.parse(wire.get(reopened.fields, 1))
    assert [wire.get(options, i) for i in range(1, 6)] == [24, 5, 255, 31, 0x7FFFFFFF]


def test_bundle_overwrite_includes_companions_and_rolls_back(tmp_path, monkeypatch):
    path = tmp_path / 'test.prefab'
    alpha = tmp_path / 'test.prefab.alpha'
    masks = rustedit_terrain.capture(Terrain(flat_ground()), (0, 0, 0), 10)
    alpha.write_bytes(masks['.alpha'])
    with pytest.raises(FileExistsError):
        rustedit_terrain.write_bundle(path, b'one', masks, overwrite=False)
    assert not path.exists() and alpha.read_bytes() == masks['.alpha']

    rustedit_terrain.write_bundle(path, b'one', masks, overwrite=True)
    assert rustedit_terrain.read_companions(path) == masks

    real_replace = rustedit_terrain.os.replace

    def fail_publish(source, destination):
        if destination == path and source.name.startswith('new-'):
            raise OSError('simulated publish failure')
        return real_replace(source, destination)

    with monkeypatch.context() as patch:
        patch.setattr(rustedit_terrain.os, 'replace', fail_publish)
        with pytest.raises(OSError, match='simulated publish failure'):
            rustedit_terrain.write_bundle(path, b'two', {'.biome': masks['.biome']}, overwrite=True)
    assert path.read_bytes() == b'one'
    assert rustedit_terrain.read_companions(path) == masks

    rustedit_terrain.write_bundle(path, b'two', {}, overwrite=True)
    assert path.read_bytes() == b'two'
    assert list(tmp_path.iterdir()) == [path]
