"""Open a standalone exported .blend in ordinary Blender and render it."""
from pathlib import Path
import sys

import bpy
from mathutils import Vector

objects = list(bpy.context.scene.objects)
assert objects and all(obj.type == 'MESH' and obj.library is None and obj.data.library is None for obj in objects)
assert len(bpy.data.scenes) == 1 and not list(bpy.data.libraries)
assert bpy.data.workspaces, 'Export has no standard Blender workspace'
assert all(not obj.get('ruster_kind') for obj in objects)
for material in bpy.data.materials:
    assert material.library is None
    if material.use_nodes:
        for node in material.node_tree.nodes:
            if node.type == 'TEX_IMAGE' and node.image:
                assert node.image.library is None and node.image.packed_file

# Users can add these in normal Blender; the Ruster editor exposes neither.
scene = bpy.context.scene
corners = [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]
low = Vector(tuple(min(point[i] for point in corners) for i in range(3)))
high = Vector(tuple(max(point[i] for point in corners) for i in range(3)))
center = (low+high)/2
distance = max((high-low).length*2, 5.)
bpy.ops.object.camera_add(location=center+Vector((1, -1, 1)).normalized()*distance)
camera = bpy.context.object
camera.rotation_euler = (center-camera.location).to_track_quat('-Z', 'Y').to_euler()
camera.data.clip_end = max(1000., distance*4)
scene.camera = camera
bpy.ops.object.light_add(type='AREA', location=center+Vector((0, 0, distance)))
bpy.context.object.data.energy = 1000
world = scene.world or bpy.data.worlds.new('Render World')
scene.world = world
world.use_nodes = True
world.node_tree.nodes['Background'].inputs['Color'].default_value = (.8, .8, .8, 1.)
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = 1
scene.render.resolution_x = scene.render.resolution_y = 32
scene.render.resolution_percentage = 100
output = Path(sys.argv[sys.argv.index('--')+1])
scene.render.filepath = str(output)
scene.render.image_settings.file_format = 'PNG'
bpy.ops.render.render(write_still=True)
assert output.is_file() and output.stat().st_size > 100
print('RUSTER_EXPORTED_BLEND_OPENS_AND_RENDERS_OK', flush=True)
