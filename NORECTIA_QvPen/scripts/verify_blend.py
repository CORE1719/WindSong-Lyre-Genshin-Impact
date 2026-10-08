"""
Re-open NORECTIA_QvPen_Custom_v02.blend and verify / measure everything that
the report needs. Writes renders/../verification_report.json and prints it.
"""
import bpy
import bmesh
import json
import math
import os
from mathutils import Vector
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
BLEND = os.path.join(ROOT, "NORECTIA_QvPen_Custom_v02.blend")
MM = 1000.0

bpy.ops.wm.open_mainfile(filepath=BLEND)
dg = bpy.context.evaluated_depsgraph_get()
R = {"file": os.path.relpath(BLEND, ROOT), "file_size_kb": round(os.path.getsize(BLEND) / 1024, 1)}


def eval_bm(ob, world=True):
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    bm = bmesh.new()
    bm.from_mesh(me)
    if world:
        bm.transform(ob.matrix_world)
    ev.to_mesh_clear()
    return bm


def tris(ob):
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    me.calc_loop_triangles()
    n = len(me.loop_triangles)
    ev.to_mesh_clear()
    return n


def bbox_mm(obs, space_mat=None):
    pts = []
    for ob in obs:
        bm = eval_bm(ob)
        if space_mat is not None:
            bm.transform(space_mat)
        pts += [v.co.copy() for v in bm.verts]
        bm.free()
    mn = Vector([min(p[i] for p in pts) for i in range(3)])
    mx = Vector([max(p[i] for p in pts) for i in range(3)])
    return [round(c * MM, 2) for c in mn], [round(c * MM, 2) for c in mx], [round((b - a) * MM, 2) for a, b in zip(mn, mx)]


pen = bpy.data.objects["NORECTIA_Pen"]
stand = bpy.data.objects["NORECTIA_PenStand"]
R["hierarchy"] = {
    pen.name: sorted(o.name for o in pen.children),
    stand.name: sorted(o.name for o in stand.children),
}
expected_pen = {"Pen_Body", "Pen_TipMesh", "Pen_RearFrame", "Pen_ColorWindow_01", "Pen_ColorWindow_02",
                "Pen_ColorWindow_03", "PenTip", "GripPoint", "PenCenter"}
expected_stand = {"Stand_Base", "Stand_Front", "Stand_Rear"}
R["hierarchy_ok"] = set(R["hierarchy"][pen.name]) == expected_pen and set(R["hierarchy"][stand.name]) == expected_stand

pen_meshes = [o for o in pen.children if o.type == "MESH"]
stand_meshes = [o for o in stand.children if o.type == "MESH"]

# pen dimensions in pen-local space (undo display transform)
inv = pen.matrix_world.inverted()
mn, mx, size = bbox_mm(pen_meshes, inv)
R["pen_local_bbox_min_mm"], R["pen_local_bbox_max_mm"], R["pen_size_mm(LxWxT)"] = mn, mx, size
mn, mx, size = bbox_mm([bpy.data.objects["Pen_Body"]], inv)
R["pen_body_size_mm"] = size
mn, mx, size = bbox_mm([bpy.data.objects["Pen_RearFrame"]], inv)
R["rear_frame_size_mm"] = size
mn, mx, size = bbox_mm(stand_meshes)
R["stand_bbox_min_mm"], R["stand_bbox_max_mm"], R["stand_size_mm(LxDxH)"] = mn, mx, size
for n in expected_stand:
    R["%s_size_mm" % n] = bbox_mm([bpy.data.objects[n]])[2]

# grip width/thickness at GripPoint (section of the evaluated body)
def section_size(x_mm):
    bm = eval_bm(bpy.data.objects["Pen_Body"], world=False)
    geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
    res = bmesh.ops.bisect_plane(bm, geom=geom, plane_co=(x_mm / MM, 0, 0), plane_no=(1, 0, 0))
    vs = [e for e in res["geom_cut"] if isinstance(e, bmesh.types.BMVert)]
    ys = [v.co.y for v in vs]; zs = [v.co.z for v in vs]
    bm.free()
    return round((max(ys) - min(ys)) * MM, 2), round((max(zs) - min(zs)) * MM, 2)

R["section_WxT_mm"] = {str(x): section_size(x) for x in (-145, -98, -49, 35, 100)}

R["display_angle_deg"] = round(-math.degrees(pen.matrix_world.to_euler().y), 3)
R["pen_root_world_location_mm"] = [round(c * MM, 2) for c in pen.matrix_world.translation]

R["empties_local_mm"] = {n: [round(c * MM, 3) for c in bpy.data.objects[n].location] for n in ("PenTip", "GripPoint", "PenCenter")}
# PenTip must coincide with the front of the writing ball
tipmesh = eval_bm(bpy.data.objects["Pen_TipMesh"], world=False)
R["writing_ball_front_x_mm"] = round(min(v.co.x for v in tipmesh.verts) * MM, 3)
tipmesh.free()

R["transforms"] = {}
for o in list(pen.children) + list(stand.children) + [pen, stand]:
    R["transforms"][o.name] = {
        "loc_mm": [round(c * MM, 2) for c in o.location],
        "rot_deg": [round(math.degrees(c), 3) for c in o.rotation_euler],
        "scale": [round(c, 4) for c in o.scale],
    }

R["triangles"] = {o.name: tris(o) for o in pen_meshes + stand_meshes}
R["triangles_pen_total"] = sum(tris(o) for o in pen_meshes)
R["triangles_stand_total"] = sum(tris(o) for o in stand_meshes)
R["triangles_total"] = R["triangles_pen_total"] + R["triangles_stand_total"]

used = set()
R["materials_per_object"] = {}
for o in pen_meshes + stand_meshes:
    names = [m.name for m in o.data.materials]
    R["materials_per_object"][o.name] = names
    used |= set(names)
R["materials_used"] = sorted(used)
R["material_count"] = len(used)
R["modifiers"] = {o.name: [(m.type, round(getattr(m, "width", 0) * MM, 3)) for m in o.modifiers] for o in pen_meshes + stand_meshes}
R["uv_layers"] = {o.name: [l.name for l in o.data.uv_layers] for o in pen_meshes + stand_meshes}

R["images"] = [{"name": i.name, "size": list(i.size), "filepath": i.filepath, "packed": bool(i.packed_file)}
               for i in bpy.data.images if i.type == "IMAGE"]

# manifold / normals sanity
def mesh_stats(ob):
    bm = eval_bm(ob, world=False)
    nm = sum(1 for e in bm.edges if not e.is_manifold)
    zero = sum(1 for f in bm.faces if f.calc_area() < 1e-12)
    bm.free()
    return {"non_manifold_edges": nm, "zero_area_faces": zero}

R["mesh_checks"] = {o.name: mesh_stats(o) for o in pen_meshes + stand_meshes}

# pen <-> stand interpenetration + contact gaps
def bvh(obs):
    bms = []
    bm = bmesh.new()
    for o in obs:
        b = eval_bm(o)
        tmp = bpy.data.meshes.new("tmp")
        b.to_mesh(tmp)
        b.free()
        bm.from_mesh(tmp)
        bpy.data.meshes.remove(tmp)
    return bm, BVHTree.FromBMesh(bm)

pbm, pbvh = bvh(pen_meshes)
R["pen_vs_stand_overlap_pairs"] = {}
for o in stand_meshes:
    sbm, sbvh = bvh([o])
    R["pen_vs_stand_overlap_pairs"][o.name] = len(pbvh.overlap(sbvh))
    # minimum distance from stand vertices to the pen surface
    best = 1e9
    for v in sbm.verts:
        hit = pbvh.find_nearest(v.co)
        if hit[0] is not None:
            best = min(best, hit[3])
    # and pen verts to stand
    for v in pbm.verts:
        hit = sbvh.find_nearest(v.co)
        if hit[0] is not None:
            best = min(best, hit[3])
    R.setdefault("pen_to_stand_min_gap_mm", {})[o.name] = round(best * MM, 3)
    sbm.free()
pbm.free()

# stand parts sit on each other (base top / floor)
R["stand_base_top_z_mm"] = bbox_mm([bpy.data.objects["Stand_Base"]])[1][2]
R["stand_front_min_z_mm"] = bbox_mm([bpy.data.objects["Stand_Front"]])[0][2]
R["stand_rear_min_z_mm"] = bbox_mm([bpy.data.objects["Stand_Rear"]])[0][2]

out = os.path.join(ROOT, "verification_report.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump(R, f, indent=2, ensure_ascii=False)
print(json.dumps(R, indent=1, ensure_ascii=False))
