"""Typed project lifecycle and owned live-preview controls for MCP."""
from pathlib import Path
import bpy
from . import app,scene,quitting,live_preview
from .core import settings

READ={'get_project_status','list_recent_projects','get_live_preview_status'}
PROJECT_EDIT={'new_project','open_project'}
EDIT=PROJECT_EDIT|{'start_live_preview','stop_live_preview','send_live_preview_command','grant_live_preview_owner'}


def project_status():
    state=bpy.context.scene.ruster
    return {'mode':state.mode,'title':state.title,'path':state.project_path or None,
        'unsaved_changes':quitting.has_unsaved_changes(),'prefab_count':len(scene.prefab_roots()),
        'preview_active':bool(live_preview._job and live_preview._job.active)}


def preview_status(log_lines=20):
    from .mcp_building import bounded_int
    from .core.preview_protocol import MAX_PLACEMENTS,MAX_SNAPSHOT
    bounded_int(log_lines,0,100,'Log line count')
    live_preview.refresh_status()
    job=live_preview._job
    state=bpy.context.window_manager.ruster_live_preview
    info=dict(live_preview.status())
    port=job.port if job and job.active else state.port
    info.update(active=bool(job and job.active),address=f'127.0.0.1:{port}',connect_command=f'connect 127.0.0.1:{port}',
        placement_count=len(scene.prefab_roots()),placement_limit=MAX_PLACEMENTS,snapshot_byte_limit=MAX_SNAPSHOT,
        server=live_preview._server_status,client=live_preview._client_status,
        error=live_preview._error,scene_error=live_preview._snapshot_error,
        client_module_loaded=live_preview._module_loaded,client_check=live_preview._probe_message,
        client_operation=live_preview._future_kind if live_preview._future is not None else None,
        client_controls='Launch Rust Without EAC and Inject are explicit actions in the Live Preview panel.',
        logs=job.log_tail(log_lines) if job and log_lines else [])
    return info


def checked_params(p,allowed):
    unknown=set(p)-set(allowed)
    if unknown:raise ValueError('Unknown parameters: '+', '.join(sorted(unknown)))


def require_replacement(p,bridge):
    checked_params(p,('path','discard_unsaved'))
    if type(p.get('discard_unsaved',False)) is not bool:raise ValueError('discard_unsaved must be boolean')
    bridge.require_idle()
    if bpy.context.scene.ruster.busy:raise ValueError('Wait for asset extraction to finish before switching projects')
    if live_preview._job and live_preview._job.active:
        raise ValueError('Stop live preview and wait for it to finish before switching projects')
    if live_preview._future is not None and live_preview._future_kind!='probe':
        raise ValueError('Wait for the current Rust client operation before switching projects')
    if not p.get('discard_unsaved',False) and quitting.has_unsaved_changes():
        raise ValueError('The current project has unsaved changes. Use save_project first, or explicitly set discard_unsaved=True.')


def dispatch(server,kind,p,bridge):
    if kind=='get_project_status':
        checked_params(p,());return project_status()
    if kind=='list_recent_projects':
        from .mcp_building import bounded_int
        checked_params(p,('limit','offset'))
        limit=bounded_int(p.get('limit',20),1,100,'Limit');offset=bounded_int(p.get('offset',0),0,2**31-1,'Offset')
        config=settings.load();rows=[]
        recent=config.get('recent_projects',[])
        for path in (recent if isinstance(recent,list) else [])[:100]:
            if not isinstance(path,str):continue
            source=Path(path)
            if source.suffix.lower()!='.ruster':continue
            rows.append({'path':str(source),'name':source.stem,'exists':source.is_file()})
        return {'projects':rows[offset:offset+limit],'total':len(rows),'next_offset':offset+limit if offset+limit<len(rows) else None}
    if kind in PROJECT_EDIT:
        if kind=='new_project' and 'path' in p:raise ValueError('new_project does not accept a path; use save_project afterward')
        require_replacement(p,bridge)
        if kind=='open_project':
            value=p.get('path')
            if not isinstance(value,str) or not value or not Path(value).is_absolute():raise ValueError('Provide an absolute .ruster project path')
            path=Path(value).resolve()
            if path.suffix.lower()!='.ruster' or not path.is_file():raise ValueError('Choose an existing .ruster project')
            app.open_path(path)
        else:
            from .studio import new_prefab
            new_prefab()
        app.redraw();return project_status()
    if kind=='get_live_preview_status':
        checked_params(p,('log_lines',));return preview_status(p.get('log_lines',20))
    bridge.require_idle()
    if kind=='start_live_preview':
        checked_params(p,('port','owner_id','update_server'))
        bridge.require_editor()
        live_preview.start_preview(port=p.get('port'),owner=p.get('owner_id'),update_server=p.get('update_server',False))
    elif kind=='stop_live_preview':
        checked_params(p,())
        if live_preview._job and live_preview._job.active:live_preview._job.request_stop()
    elif kind=='send_live_preview_command':
        checked_params(p,('command',))
        value=p.get('command')
        if not isinstance(value,str):raise ValueError('command must be a string')
        if not live_preview._job:raise ValueError('Start live preview first')
        live_preview._job.send_command(value)
        return {'queued':True,'command':value.strip(),'execution':'Check get_live_preview_status logs for the server result.'}
    elif kind=='grant_live_preview_owner':
        checked_params(p,('steam_id',))
        if not isinstance(p.get('steam_id'),str):raise ValueError('Provide your 17-digit SteamID64 as a string')
        owner=live_preview.backend.owner_id(p.get('steam_id'))
        if not owner:raise ValueError('Provide your 17-digit SteamID64')
        if not live_preview._job:raise ValueError('Start live preview first')
        live_preview._job.send_command('ownerid '+owner+' "Ruster preview owner"')
        return {'queued':True,'steam_id':owner,'message':'Reconnect in Rust after the server applies the owner ID.'}
    else:raise ValueError('Unsupported session command')
    return preview_status()
