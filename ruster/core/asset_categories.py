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
    ('GAMEPLAY', 'Gameplay', ('%/spawners/%', '%/npc/%')),
    ('VEHICLES', 'Vehicles', ('%/vehicles/%', '%/vehicle/%', '%/boats/%')),
    ('EFFECTS', 'Effects & Lighting', ('%/effects/%', '%/fx/%', '%/lights/%', '%/lighting/%')),
    ('OTHER', 'Other Rust Prefabs', ()),
    ('DEVELOPMENT', 'Development & Primitives', ('%/modding/%',)),
    ('HIDDEN', 'Hidden & IO Helpers', ('%/tools/%', '%/engine/%', '%/player/%',
        '%/sound/%', '%/sounds/%', '%/sfx/%', '%/effects/%', '%/fx/%',
        '%/trigger/%', '%/triggers/%', '%/volumes/%', '%/test/%', '%/tests/%',
        '%/testing/%', '%/testscenario%', '%hidden%')),
    ('ALL_ASSETS', 'All Rust Assets (Including Hidden)', ()),
    # Append so saved Blender enum numbers retain their existing meaning.
    ('VOLUMES', 'Volumes', ('%/volumes_and_triggers/%', '%/volumes/%', '%/volume/%',
        '%/triggers/%', '%/trigger/%', '%/environmentvolume%.prefab',
        '%/modding/radiation/%', '%/structures/radiation/%', '%/generators/twotierradiation%.prefab',
        '%/monument/radiation/%', '%/launchsite/radiation.prefab',
        '%/safezone%.prefab', '%/prevent_building%.prefab',
        '%/prevent_movement%.prefab', '%/prevent_movment%.prefab',
        '%/dynamicpreventbuilding.prefab', '%/ioentitypreventbuilding.prefab',
        '%/npcpreventbuildingvolume.prefab', '%/terrain triggers.prefab')),
)
LABELS = {key: label for key, label, _ in GROUPS}


def is_volume(path):
    """Use the same bounded path rules as the browser, never every collider."""
    from fnmatch import fnmatchcase
    patterns = next(patterns for key, _label, patterns in GROUPS if key == 'VOLUMES')
    return any(fnmatchcase(path.lower(), pattern.replace('%', '*')) for pattern in patterns)


def sql_case(column='n.path'):
    from .wire import FormatError
    if column not in ('n.path', 'path'):raise FormatError('Invalid category column')
    parts = []
    # A volume in a monument/development directory still belongs to Volumes.
    for key, _label, patterns in sorted(GROUPS, key=lambda group: group[0] != 'VOLUMES'):
        if patterns and key!='HIDDEN':
            parts.append('WHEN (' + ' OR '.join(column + " LIKE '" + p.replace('_', '\\_') + "' ESCAPE char(92)" for p in patterns)
                         + ") THEN '" + key + "'")
    return 'CASE ' + ' '.join(parts) + " ELSE 'OTHER' END"
