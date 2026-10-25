"""Explicit crate previews for client-stripped Rust spawner prefabs.

These are editor illustrations using shipped crate assets, not reconstructed
server spawn rules. Do not infer arbitrary entities from similar filenames.
"""
MODDING='assets/bundled/prefabs/modding/lootables/'
RADTOWN='assets/bundled/prefabs/radtown/'
LABS=RADTOWN+'underwater_labs/'
_CRATES={
    'basic_crate_spawner':('crate_basic','Basic Crate Spawner'),
    'crate_normal_spawner':('crate_normal','Military Crate Spawner'),
    'crate_normal_2_spawner':('crate_normal_2','Wooden Crate Spawner'),
    'crate_normal_random_spawner':('crate_normal','Random Crate Spawner'),
    'elite_crate_spawner':('crate_elite','Elite Crate Spawner'),
    'food_crate_spawner':('crate_normal_2_food','Food Crate Spawner'),
    'med_crate_spawner':('crate_normal_2_medical','Medical Crate Spawner'),
    'tool_crate_spawner':('crate_tools','Tool Crate Spawner'),
    'mine_crate_spawner':('crate_mine','Mine Crate Spawner'),
    'underwater_advanced_crate_spawner':('crate_underwater_advanced','Advanced Underwater Crate Spawner'),
    'underwater_basic_crate_spawner':('crate_underwater_basic','Basic Underwater Crate Spawner'),
}
PREVIEWS={MODDING+name+'.prefab':(RADTOWN+target+'.prefab',label)
          for name,(target,label) in _CRATES.items()}
PREVIEWS.update({MODDING+'invisible/invisible_'+name+'_spawner.prefab':(RADTOWN+target+'.prefab',label)
    for name,target,label in (
        ('crate_basic','crate_basic','Invisible Basic Crate Spawner'),
        ('crate_elite','crate_elite','Invisible Elite Crate Spawner'),
        ('crate_normal','crate_normal','Invisible Military Crate Spawner'),
        ('crate_normal_2','crate_normal_2','Invisible Wooden Crate Spawner'),
        ('crate_food','crate_normal_2_food','Invisible Food Crate Spawner'),
        ('crate_medical','crate_normal_2_medical','Invisible Medical Crate Spawner'),
        ('crate_tools','crate_tools','Invisible Tool Crate Spawner'))})
PREVIEWS.update({LABS+'spawners/'+name+'.prefab':(LABS+target+'.prefab',label)
    for name,target,label in (
        ('spawner_elite_crate','crate_elite','Underwater Lab Elite Crate Spawner'),
        ('spawner_crate_normal_old_style','crate_normal','Underwater Lab Military Crate Spawner'),
        ('spawner_normal_crates','crate_normal_2','Underwater Lab Crate Spawner'),
        ('spawner_food_crates','crate_food_1','Underwater Lab Food Crate Spawner'),
        ('spawner_medical_crate','crate_medical','Underwater Lab Medical Crate Spawner'),
        ('spawner_tools_crate','crate_tools','Underwater Lab Tool Crate Spawner'),
        ('spawner_ammo_crate','crate_ammunition','Underwater Lab Ammunition Crate Spawner'))})


def preview(path):
    entry=PREVIEWS.get(path.lower())
    return {'path':entry[0],'label':entry[1], 'kind':'SPAWNER',
        'note':'Crate preview at the spawner origin; Rust controls runtime spawn choices, offsets and rotation variations.'} if entry else None
