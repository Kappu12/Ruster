"""One incremental, metadata-only index shared by all native Add submenus."""
from contextlib import closing
from pathlib import PurePosixPath

from . import catalog
from ..core.asset_categories import GROUPS, sql_case
from ..core.asset_names import IO_SEARCH_ORDER, display_name, menu_label


def build(cache, favorites):
    """Yield between small SQLite batches; return a complete menu snapshot.

    The caller can advance this on idle ticks or finish it synchronously when
    needed. Closing the generator also releases its read-only database snapshot.
    No Blender data, bundles, textures or models are accessed.
    """
    groups = {key: [] for key, _label, _patterns in GROUPS}
    hidden_patterns = next(patterns for key, _label, patterns in GROUPS if key == 'HIDDEN')
    hidden_sql = '('+' OR '.join('n.path LIKE ?' for _pattern in hidden_patterns)+')'
    entries = []
    with closing(catalog.read_connection(cache)) as db:
        cursor = db.execute('SELECT n.uid,n.path,'+catalog.AVAILABLE+','+sql_case()+','+hidden_sql+' FROM names n', hidden_patterns)
        while rows := cursor.fetchmany(256):
            for uid, source, available, category, hidden in rows:
                name = display_name(source)
                stem = PurePosixPath(source).stem.casefold()
                rank = IO_SEARCH_ORDER.index(stem) if '/ioslothandles/' in source.casefold() and stem in IO_SEARCH_ORDER else None
                weight = 1000-rank*50 if rank is not None else (20 if uid in favorites else 0)
                icon = 'SOLO_ON' if uid in favorites else 'MESH_CUBE' if available else 'QUESTION'
                item = (str(uid), menu_label(source), source, weight, icon)
                entries.append(((uid not in favorites, name.casefold(), uid), item, category, hidden))
            yield
    # Close the read transaction before sorting; a background catalog refresh
    # must not wait for UI work after the last database batch.
    entries.sort(key=lambda entry: entry[0])
    all_items = []
    for _order, item, category, hidden in entries:
        all_items.append(item)
        groups[category].append(item)
        if hidden:groups['HIDDEN'].append(item)
    groups['ALL_ASSETS'] = all_items
    result = {'@'+key: {'items': items, 'total': len(items)} for key, items in groups.items()}
    result[''] = result['@ALL_ASSETS']
    return result
