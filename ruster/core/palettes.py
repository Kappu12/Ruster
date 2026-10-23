"""Persistent local prefab palettes, shared by browser and painting tools."""
MAX_FAVORITES=512
MAX_RECENT=48


def favorite_ids(config):
    return _ids(config.get('favorite_prefabs',[]),MAX_FAVORITES)


def recent_ids(config):
    return _ids(config.get('recent_prefabs',[]),MAX_RECENT)


def _ids(value,limit):
    if not isinstance(value,list):return []
    ids=[]
    for entry in value:
        if isinstance(entry,bool) or not isinstance(entry,(str,int)):continue
        try:uid=int(entry)
        except ValueError:continue
        if 0<=uid<=0xFFFFFFFF and uid not in ids:ids.append(uid)
        if len(ids)==limit:break
    return ids


def remember(config,uid):
    uid=int(uid)
    if not 0<=uid<=0xFFFFFFFF:raise ValueError('Invalid Rust prefab ID')
    ids=[uid]+[value for value in recent_ids(config) if value!=uid]
    return {**config,'recent_prefabs':[str(value) for value in ids[:MAX_RECENT]]}


def toggle(config,uid):
    uid=int(uid)
    if not 0<=uid<=0xFFFFFFFF:raise ValueError('Invalid Rust prefab ID')
    ids=favorite_ids(config)
    if uid in ids:ids.remove(uid)
    else:
        if len(ids)>=MAX_FAVORITES:raise ValueError('Your favorite palette is full; remove an existing favorite first')
        ids.append(uid)
    return {**config,'favorite_prefabs':[str(value) for value in ids]}
