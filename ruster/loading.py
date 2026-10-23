"""One model-loading summary and set of recovery actions for native UI surfaces."""
from . import scene


def model_state(obj,pending):
    if obj.get('ruster_marker'):return 'HELPER'
    if int(obj['ruster_uid']) in pending:return 'LOADING'
    if obj.get('ruster_model_error'):return 'ISSUE'
    return 'READY' if obj.get('ruster_visual') else 'MISSING'


def model_summary():
    from . import app
    pending=app._pending_asset_ids|app._job_ids|set(app._visual_queue)
    counts=dict.fromkeys(('READY','LOADING','MISSING','ISSUE','HELPER'),0)
    for obj in scene.prefab_roots():counts[model_state(obj,pending)]+=1
    return counts


def header_label(state,counts):
    if state.busy:return 'Loading assets…'
    if counts['ISSUE']:return f"Models: {counts['ISSUE']:,} with issues"
    if counts['MISSING']:return f"Models: {counts['MISSING']:,} not loaded"
    return f"Models: {counts['READY']:,} loaded"


def draw_status(layout,context,*,installation=True):
    from .ui_style import ICONS as I,action,wrapped
    state=context.scene.ruster
    counts=model_summary()
    wrapped(layout,context,state.asset_status,icon='busy' if state.busy else 'info')
    if state.busy and state.asset_progress_known:
        layout.progress(factor=state.asset_progress,type='BAR',text='Loading Assets')
    layout.label(text=f"{counts['READY']:,} loaded · {counts['LOADING']:,} loading",icon=I['prefab'])
    layout.label(text=f"{counts['MISSING']:,} not loaded · {counts['ISSUE']:,} with issues",icon=I['error' if counts['ISSUE'] else 'info'])
    if counts['HELPER']:layout.label(text=f"{counts['HELPER']:,} helpers without static models",icon=I['info'])
    row=layout.row(align=True)
    missing=row.row(align=True);missing.enabled=bool(counts['MISSING'])
    missing.operator('ruster.select_model_status',text='Select Unloaded').status='MISSING'
    issues=row.row(align=True);issues.enabled=bool(counts['ISSUE'])
    issues.operator('ruster.select_model_status',text='Select Issues').status='ISSUE'
    if state.busy:action(layout,'ruster.cancel_assets')
    else:
        action(layout,'ruster.assets',text='Load / Retry Selected Models')
        action(layout,'ruster.assets',text='Refresh Asset Catalog',icon='refresh').rebuild=True
    action(layout,'ruster.asset_report',text='View Asset Report…')
    if installation:action(layout,'ruster.setup')
