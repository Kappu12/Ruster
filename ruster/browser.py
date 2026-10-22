"""Native prefab catalog filters and persistent favorite palettes."""
import zlib
import sqlite3
import bpy
from bpy.props import StringProperty
from . import scene
from .assets import catalog
from .core import settings,palettes

_classes=[]
PAGE_SIZE=12
_category_key=None
_category_history=[]
_category_items=[('ALL','All Categories','',0)]
_page_cache={}


def prefab_page(state):
    """UI redraws reuse a page until its filters or the catalog actually change."""
    path=scene.cache_dir()/'catalog.sqlite3'
    stat=path.stat() if path.exists() else None
    favorites=tuple(palettes.favorite_ids(settings.load())) if state.favorites_only else None
    key=(str(path),stat.st_mtime_ns if stat else 0,stat.st_size if stat else 0,
         state.query,state.query_page,state.category,favorites,state.available_only,state.include_helpers)
    if key not in _page_cache:
        result=catalog.page(scene.cache_dir(),state.query,page_size=PAGE_SIZE,
            page_index=state.query_page,category='' if state.category=='ALL' else state.category,
            favorites=favorites,available_only=state.available_only,include_helpers=state.include_helpers)
        _page_cache[key]=result
        while len(_page_cache)>16:del _page_cache[next(iter(_page_cache))]
    return _page_cache[key]


def prefab_description(uid,action):
    try:
        found=catalog.find(scene.cache_dir(),int(uid))
        if found:return f'{action}\n{found[0]}\nRust prefab ID: {uid}'+('' if found[1] else '\nNot found in local Rust bundles')
    except (ValueError,OSError,sqlite3.Error):pass
    return action


def category_items(_state,_context):
    global _category_key,_category_items
    path=scene.cache_dir()/'catalog.sqlite3'
    key=(str(path),path.stat().st_mtime_ns if path.exists() else 0)
    if key!=_category_key:
        try:
            from .core.asset_categories import GROUPS
            items=[('ALL','All Categories','',0)]+[('@'+key,label,'',index+1)
                for index,(key,label,_patterns) in enumerate(GROUPS)]
            if items!=_category_items:
                _category_history.append(_category_items)  # RNA may retain callback string references.
                _category_items=items
            _category_key=key
        except (OSError,ValueError,sqlite3.Error):pass
    return _category_items


class RUSTER_OT_favorite(bpy.types.Operator):
    bl_idname='ruster.favorite'
    bl_label='Toggle Favorite Prefab'
    bl_description='Add or remove this prefab from your local favorite palette'
    uid:StringProperty()
    def execute(self,context):
        try:
            settings.save(palettes.toggle(settings.load(),self.uid))
            context.scene.ruster.query_page=0
            for window in context.window_manager.windows:
                for area in window.screen.areas:area.tag_redraw()
            return {'FINISHED'}
        except ValueError as error:
            self.report({'ERROR'},str(error));return {'CANCELLED'}


class RUSTER_OT_paint_asset(bpy.types.Operator):
    bl_idname='ruster.paint_asset'
    bl_label='Paint this Prefab'
    bl_description='Choose this prefab for terrain placement painting'
    uid:StringProperty()
    @classmethod
    def description(cls,context,properties):return prefab_description(properties.uid,'Paint this prefab on terrain')
    def execute(self,context):
        try:
            found=catalog.find(scene.cache_dir(),int(self.uid))
            if not found or not found[1]:raise ValueError('Choose a prefab available in your local Rust bundles')
        except (ValueError,OSError,sqlite3.Error) as error:
            self.report({'ERROR'},str(error));return {'CANCELLED'}
        brush=context.scene.ruster_paint
        brush.uid=self.uid;brush.palette='SINGLE'
        bpy.ops.wm.tool_set_by_id(name='ruster.prefab_brush')
        return {'FINISHED'}


class RUSTER_OT_copy_prefab(bpy.types.Operator):
    bl_idname='ruster.copy_prefab'
    bl_label='Copy Prefab ID'
    uid:StringProperty()
    @classmethod
    def description(cls,context,properties):return prefab_description(properties.uid,'Copy this Rust prefab ID')
    def execute(self,context):
        try:
            if not catalog.find(scene.cache_dir(),int(self.uid)):raise ValueError('Prefab is no longer in the local catalog')
            context.window_manager.clipboard=self.uid
            self.report({'INFO'},'Prefab ID copied');return {'FINISHED'}
        except (ValueError,OSError,sqlite3.Error) as error:
            self.report({'ERROR'},str(error));return {'CANCELLED'}


def register():
    for cls in (RUSTER_OT_favorite,RUSTER_OT_copy_prefab):bpy.utils.register_class(cls);_classes.append(cls)


def unregister():
    global _category_key
    _category_key=None
    _page_cache.clear()
    for cls in reversed(_classes):bpy.utils.unregister_class(cls)
    _classes.clear()
