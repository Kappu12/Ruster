"""Broad Rust asset categories shared by SQL filtering and the Add menu."""
GROUPS = (
    ('MONUMENTS', 'Monuments', ('%/monument/%', '%/monuments/%', '%/radtown/%')),
    ('NATURE', 'Nature & Rocks', ('%/nature/%', '%/autospawn/%', '%/vegetation/%', '%/trees/%', '%/rocks/%', '%/cliffs/%')),
    ('BUILDING', 'Building & Modular', ('%/building/%', '%/building core/%', '%/construction/%', '%/buildings/%', '%/building parts/%')),
    ('INDUSTRIAL', 'Industrial', ('%/industrial/%', '%/pipes/%', '%/machinery/%', '%/electrical/%')),
    ('ROADS', 'Roads & Rail', ('%/roads/%', '%/road/%', '%/railway/%', '%/rail/%', '%/train%')),
    ('DEPLOYABLES', 'Deployables', ('%/deployable/%', '%/deployables/%')),
    ('FURNITURE', 'Furniture & Interior', ('%/furniture/%', '%/interior/%', '%/chairs/%', '%/tables/%')),
    ('PROPS', 'Props & Decoration', ('%/decor/%', '%/props/%', '%/decoration/%')),
    ('GAMEPLAY', 'Gameplay & Volumes', ('%/triggers/%', '%/trigger/%', '%/volumes/%', '%/spawners/%', '%/npc/%')),
    ('VEHICLES', 'Vehicles', ('%/vehicles/%', '%/vehicle/%', '%/boats/%')),
    ('EFFECTS', 'Effects & Lighting', ('%/effects/%', '%/fx/%', '%/lights/%', '%/lighting/%')),
    ('OTHER', 'Other Rust Prefabs', ()),
    ('DEVELOPMENT', 'Development & Primitives', ('%/modding/%',)),
    ('HIDDEN', 'Hidden & IO Helpers', ('%/tools/%', '%/engine/%', '%/player/%',
        '%/sound/%', '%/sounds/%', '%/sfx/%', '%/effects/%', '%/fx/%',
        '%/trigger/%', '%/triggers/%', '%/volumes/%', '%/test/%', '%/tests/%',
        '%/testing/%', '%/testscenario%', '%hidden%')),
    ('ALL_ASSETS', 'All Rust Assets (Including Hidden)', ()),
)
LABELS = {key: label for key, label, _ in GROUPS}


def sql_case(column='n.path'):
    from .wire import FormatError
    if column not in ('n.path', 'path'):raise FormatError('Invalid category column')
    parts = []
    for key, _label, patterns in GROUPS:
        if patterns and key!='HIDDEN':
            parts.append('WHEN (' + ' OR '.join(column + " LIKE '" + p + "'" for p in patterns)
                         + ") THEN '" + key + "'")
    return 'CASE ' + ' '.join(parts) + " ELSE 'OTHER' END"
