"""Read original linked model transforms without stale dependency-graph caches."""
from mathutils import Matrix


def model_matrix(obj, cache):
    # Library objects exist outside the active scene. Their saved matrix_world
    # can omit parent transforms even while Blender renders instances correctly.
    # Converted models use object parenting; derive its full chain from source
    # local transforms, preserving parent inverses and nonuniform/negative scale.
    pending=[];parent=obj
    while parent is not None and parent not in cache:
        pending.append(parent);parent=parent.parent
    matrix=Matrix.Identity(4) if parent is None else cache[parent]
    for node in reversed(pending):
        matrix=(matrix@node.matrix_parent_inverse if node.parent else Matrix.Identity(4))@node.matrix_basis
        cache[node]=matrix
    return cache[obj]


def placement_meshes(root, transforms=None):
    """Yield original meshes and exact world matrices for one collection instance."""
    collection=root.instance_collection
    if collection is None:return
    transforms={} if transforms is None else transforms
    matrix=root.matrix_world@Matrix.Translation(-collection.instance_offset)
    for obj in collection.all_objects:
        if obj.type=='MESH':yield obj,matrix@model_matrix(obj,transforms)
