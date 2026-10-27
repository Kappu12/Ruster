import pytest
from ruster.core import volume_style as styles


@pytest.mark.parametrize('source,expected',[
    ('assets/bundled/prefabs/modding/volumes_and_triggers/safezoneoverridebox.prefab','SAFE_ZONE'),
    ('assets/bundled/prefabs/modding/volumes_and_triggers/safezonesphere.prefab','SAFE_ZONE'),
    ('assets/bundled/prefabs/modding/volumes_and_triggers/prevent_building_cube.prefab','NO_BUILD'),
    ('assets/prefabs/misc/dynamicpreventbuilding.prefab','NO_BUILD'),
    ('assets/rust.ai/npcpreventbuildingvolume.prefab','NO_BUILD'),
    ('assets/bundled/prefabs/modding/volumes_and_triggers/prevent_movment_volume.prefab','NO_ENTRY'),
    ('Prevent Movement Volume.017','NO_ENTRY'),
    ('prevent movment volume.068','NO_ENTRY'),
    ('Safe Zone Override Box.004','SAFE_ZONE'),
    ('unknown trigger','OTHER'),
])
def test_original_asset_paths_and_offline_generated_labels(source,expected):
    assert styles.classify(source)==expected


def test_semantic_colours_stay_distinct_and_fills_stay_subtle_in_all_states():
    assert len(set(styles.COLORS.values()))==4
    for kind,color in styles.COLORS.items():
        idle=styles.state(kind);hover=styles.state(kind,hovered=True);selected=styles.state(kind,selected=True)
        assert idle['fill_color']==hover['fill_color']==selected['fill_color']==color
        assert idle['color']==color
        assert 0<idle['fill_alpha']<hover['fill_alpha']<selected['fill_alpha']<=.05
        assert idle['width']<hover['width']<selected['width']
        assert selected['halo']!=idle['halo']
