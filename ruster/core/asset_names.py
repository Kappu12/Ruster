"""Readable catalog names shared by search and placement feedback."""
from pathlib import PurePosixPath
from functools import lru_cache
import re


# These are real placeable prefab IDs, despite living under Rust's tools folder.
IO_NAMES = {
    'ioslothandlehose': ('IO Hose Tube', 'fluid pipe'),
    'ioslothandlehose_inuse': ('IO Hose Tube In Use', 'fluid pipe connected'),
    'ioslothandlehose_pending': ('IO Hose Tube Pending (Cyan Glow)', 'fluid pipe glowing neon maze'),
    'ioslothandle': ('IO Wire Tube', 'electric cable slot'),
    'ioslothandle_inuse': ('IO Wire Tube In Use', 'electric cable slot connected'),
    'ioslothandle_pending': ('IO Wire Tube Pending (Green Glow)', 'electric cable slot glow glowing neon'),
    'ioslothandle_selected': ('IO Wire Tube Selected (Yellow Glow)', 'electric cable slot glow glowing neon'),
    'ioslothandle_selected_inuse': ('IO Wire Tube Selected In Use (Red Glow)', 'electric cable slot connected glow glowing neon'),
}


IO_SEARCH_ORDER = ('ioslothandlehose_pending', 'ioslothandle',
                   'ioslothandle_pending', 'ioslothandle_selected',
                   'ioslothandle_selected_inuse', 'ioslothandlehose',
                   'ioslothandlehose_inuse', 'ioslothandle_inuse')


def priority_paths(query):
    """Rank relevant IO aliases before broad path substring matches, before paging."""
    if not {token.strip('()') for token in query.casefold().split()} & {'io','glow','glowing','neon','cyan','tube','hose','wire'}:
        return []
    return ['%/ioslothandles/'+stem+'.prefab' for stem in IO_SEARCH_ORDER]


def alias_paths(token):
    """Small name aliases; search still reads metadata, never game bundles."""
    token=token.casefold()
    return ['%/ioslothandles/'+stem+'.prefab' for stem,(name,aliases) in IO_NAMES.items()
            if token in (name+' '+aliases).casefold()]


def display_name(path):
    stem=re.sub(r'\.prefab$','',PurePosixPath(path).name,flags=re.IGNORECASE)
    if '/ioslothandles/' in path.lower() and stem.lower() in IO_NAMES:
        return IO_NAMES[stem.lower()][0]
    match=re.fullmatch(r'cube_(.+)_dev_(\d+)',stem,re.IGNORECASE)
    if match:return f'Dev Cube {re.sub(r"[._-]+", " ", match[1]).title()} {match[2]}'
    name=re.sub(r'[._-]+',' ',stem).strip()
    if '/sound/' in path.lower():name+=' (Sound effect)'
    return name


@lru_cache(maxsize=32768)
def search_name(path):
    """Small cached catalog labels only; no model, texture or bundle reads."""
    return display_name(path).casefold()
