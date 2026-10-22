"""Native prefab catalog filters and persistent favorite palettes."""
import zlib
import sqlite3
import bpy
from bpy.props import StringProperty
from . import scene
from .assets import catalog
from .core import settings,palettes

_classes=[]
_category_key=None
_category_history=[]
_category_items=[('ALL','All Categories','',0)]


def category_items(_state,_context):
    global _category_key,_category_items
    path=scene.cache_dir()/'catalog.sqlite3'
    key=(str(path),path.stat().st_mtime_ns if path.exists() else 0)
    if key!=_category_key:
        try:
            items=[('ALL','All Categories','',0)]+[(prefix,f"{prefix.removeprefix('assets/')} ({count})",prefix,
                1+(zlib.crc32(prefix.encode())%2147483646)) for prefix,count in catalog.categories(scene.cache_dir())]
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
    def execute(self,context):
        if not catalog.find(scene.cache_dir(),int(self.uid)):return {'CANCELLED'}
        brush=context.scene.ruster_paint
        brush.uid=self.uid;brush.palette='SINGLE'
        bpy.ops.wm.tool_set_by_id(name='ruster.prefab_brush')
        return {'FINISHED'}


def register():
    for cls in (RUSTER_OT_favorite,RUSTER_OT_paint_asset):bpy.utils.register_class(cls);_classes.append(cls)


def unregister():
    global _category_key
    _category_key=None
    for cls in reversed(_classes):bpy.utils.unregister_class(cls)
    _classes.clear()
