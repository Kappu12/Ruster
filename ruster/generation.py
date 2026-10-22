"""Native Blender controls for asynchronous seed map generation."""
import atexit
import secrets
import bpy
from bpy.props import IntProperty,PointerProperty
from .core import generation as backend,settings
from .ui_style import action,properties,wrapped

_job=None
_classes=[]


def info():return _job.info() if _job else {'status':'IDLE','message':'Generate a Rust procedural map from a seed'}


def start(seed,size):
    global _job
    if _job and _job.active:raise ValueError('Map generation is already running')
    config=settings.load();binary=config.get('rust_dedicated') or backend.detect()
    if not binary:raise ValueError('RustDedicated was not found. Set its path in Preferences > Rust Assets. The Rust client alone is not sufficient.')
    _job=backend.Generation(binary,seed,size,settings.user_root()/'generated').start()
    if not bpy.app.timers.is_registered(tick):bpy.app.timers.register(tick,first_interval=.2)
    return info()


def tick():
    from .app import redraw
    redraw()
    return .35 if _job and _job.active else None


class RUSTER_PG_generation(bpy.types.PropertyGroup):
    seed:IntProperty(name='Seed',default=12345,min=0,max=2147483647,options={'SKIP_SAVE'})
    size:IntProperty(name='Map Size',description='Rust procedural world size in metres',default=4000,min=1000,max=6000,options={'SKIP_SAVE'})


def draw(layout,context,inputs=True):
    state=context.window_manager.ruster_generation;status=info();active=bool(_job and _job.active)
    if inputs:
        fields=properties(layout.column());fields.enabled=not active
        row=fields.row(align=True);row.prop(state,'seed');action(row,'ruster.random_seed',text='',icon='generate')
        fields.prop(state,'size')
    wrapped(layout,context,status['message'],icon='busy' if active else 'info')
    if _job:
        layout.label(text=f"{status['elapsed_seconds']:.1f} seconds · {status['status'].title()}")
        if active:action(layout,'ruster.cancel_generation')
        if status['status']=='READY':action(layout,'ruster.open',text='Open Generated Map',icon='open').filepath=status['result']
        row=layout.row();row.operator('wm.path_open',text='Open Generation Logs',icon='FILE_FOLDER').filepath=str(_job.directory)
    if not active and inputs:action(layout,'ruster.generate_map',text='Generate Map')
    wrapped(layout,context,'Uses your local RustDedicated headlessly and stops when a valid map is ready. Does not replace your open project.',icon='locked')
    action(layout,'ruster.preferences',text='Generator Installation',icon='settings').section='RUSTER_ASSETS'


class RUSTER_OT_generate_map(bpy.types.Operator):
    bl_idname='ruster.generate_map'
    bl_label='Generate Rust Map'
    bl_description='Generate a seeded procedural map using an installed RustDedicated; keep the current project open'
    def invoke(self,context,event):return context.window_manager.invoke_props_dialog(self,width=460)
    def draw(self,context):
        state=context.window_manager.ruster_generation
        fields=properties(self.layout.column());fields.prop(state,'seed');fields.prop(state,'size')
        wrapped(self.layout,context,'RustDedicated runs headlessly until it writes a valid map. Your current project stays open. See progress in the Ruster sidebar.')
    def execute(self,context):
        try:
            state=context.window_manager.ruster_generation;start(state.seed,state.size)
            self.report({'INFO'},'Map generation started. Progress is in the Ruster sidebar.');return {'FINISHED'}
        except Exception as error:self.report({'ERROR'},str(error));return {'CANCELLED'}


class RUSTER_OT_random_seed(bpy.types.Operator):
    bl_idname='ruster.random_seed'
    bl_label='Random Seed'
    def execute(self,context):
        context.window_manager.ruster_generation.seed=secrets.randbelow(2147483648);return {'FINISHED'}


class RUSTER_OT_cancel_generation(bpy.types.Operator):
    bl_idname='ruster.cancel_generation'
    bl_label='Cancel Generation'
    def execute(self,context):
        if _job and _job.active:_job.cancel()
        return {'FINISHED'}


class RUSTER_PT_generation(bpy.types.Panel):
    bl_label='Rust Map Generation'
    bl_space_type='VIEW_3D'
    bl_region_type='UI'
    bl_category='Ruster'
    bl_options={'DEFAULT_CLOSED'}
    def draw(self,context):draw(self.layout,context)


def register():
    for cls in (RUSTER_PG_generation,RUSTER_OT_generate_map,RUSTER_OT_random_seed,RUSTER_OT_cancel_generation,RUSTER_PT_generation):
        bpy.utils.register_class(cls);_classes.append(cls)
    bpy.types.WindowManager.ruster_generation=PointerProperty(type=RUSTER_PG_generation)
    atexit.register(shutdown_job)


def shutdown_job():
    if _job:_job.close()


def unregister():
    global _job
    atexit.unregister(shutdown_job)
    if bpy.app.timers.is_registered(tick):bpy.app.timers.unregister(tick)
    if _job:_job.close();_job=None
    if hasattr(bpy.types.WindowManager,'ruster_generation'):del bpy.types.WindowManager.ruster_generation
    for cls in reversed(_classes):bpy.utils.unregister_class(cls)
    _classes.clear()
