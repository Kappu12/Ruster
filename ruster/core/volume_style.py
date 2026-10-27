"""Editor-only semantic colours; independent of native prefab materials."""
from functools import lru_cache
import re

COLORS={
    'SAFE_ZONE':(.20,.78,.38),
    'NO_BUILD':(.96,.60,.13),
    'NO_ENTRY':(.95,.26,.30),
    'OTHER':(.28,.72,.82),
}


@lru_cache(maxsize=256)
def classify(source):
    # Includes the original Rust asset's "movment" spelling. Generated asset
    # labels also work offline in projects saved before type metadata existed.
    name=re.sub('[^a-z0-9]','',source.lower())
    if 'safezone' in name:return 'SAFE_ZONE'
    if any(word in name for word in ('preventbuilding','nobuild','buildingblocked')):return 'NO_BUILD'
    if any(word in name for word in ('preventmovement','preventmovment','noentry')):return 'NO_ENTRY'
    return 'OTHER'


def state(kind,selected=False,hovered=False):
    base=COLORS.get(kind,COLORS['OTHER'])
    brighten=.45 if hovered else (.12 if selected else 0.)
    return {'color':tuple(c+(1-c)*brighten for c in base),'fill_color':base,
        'fill_alpha':.035 if selected else (.022 if hovered else .012),
        'line_alpha':1. if selected or hovered else .75,
        'width':2.75 if selected else (2. if hovered else 1.25),
        'halo':(.95,.97,1.,.85) if selected else (.015,.025,.035,.65)}
