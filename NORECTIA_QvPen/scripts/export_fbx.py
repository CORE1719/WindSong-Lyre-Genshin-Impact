"""
Export Unity-ready FBX files from NORECTIA_QvPen_Custom_v02.blend
(modifiers applied on export, the .blend itself is not modified/saved).

  fbx/NORECTIA_Pen.fbx       pen hierarchy, root reset to identity (tip -X, origin = PenCenter)
  fbx/NORECTIA_PenStand.fbx  stand hierarchy (origin = base bottom centre)
"""
import bpy
import os
from mathutils import Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
OUT = os.path.join(ROOT, "fbx")
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.open_mainfile(filepath=os.path.join(ROOT, "NORECTIA_QvPen_Custom_v02.blend"))


def export(root_name, filename, reset_root):
    root = bpy.data.objects[root_name]
    keep = root.matrix_world.copy()
    if reset_root:
        root.matrix_world = Matrix.Identity(4)
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    root.select_set(True)
    for c in root.children_recursive:
        c.select_set(True)
    bpy.context.view_layer.objects.active = root
    bpy.ops.export_scene.fbx(
        filepath=os.path.join(OUT, filename),
        use_selection=True,
        object_types={"EMPTY", "MESH"},
        use_mesh_modifiers=True,
        mesh_smooth_type="OFF",          # custom split normals are exported
        use_tspace=False,
        apply_unit_scale=True,
        apply_scale_options="FBX_SCALE_ALL",
        bake_space_transform=True,
        axis_forward="-Z",
        axis_up="Y",
        add_leaf_bones=False,
        path_mode="COPY",
        embed_textures=False,
    )
    root.matrix_world = keep
    print("[FBX]", filename, flush=True)


export("NORECTIA_Pen", "NORECTIA_Pen.fbx", reset_root=True)
export("NORECTIA_PenStand", "NORECTIA_PenStand.fbx", reset_root=False)
