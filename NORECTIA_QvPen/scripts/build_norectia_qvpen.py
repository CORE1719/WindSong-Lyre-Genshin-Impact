"""
NORECTIA original QvPen + display stand generator (Blender 4.2+/5.x, bpy).

Builds every mesh from scratch (no imported/reused assets), assigns the 5
materials, generates the 1024px black-marble texture, UV-unwraps, adds the
QvPen empties and saves NORECTIA_QvPen_Custom_v02.blend next to this folder.

Run:
    blender -b -P build_norectia_qvpen.py -- [--overwrite]
    or (bpy as a Python module)
    python build_norectia_qvpen.py [--overwrite]

Units: 1 Blender unit = 1 m. All design values below are written in mm.
Pen axis = X, drawing tip at -X, pen local origin = PenCenter (middle of 350mm).
"""
import bpy
import bmesh
import math
import os
import sys

import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
TEX_DIR = os.path.join(ROOT, "textures")
BLEND_PATH = os.path.join(ROOT, "NORECTIA_QvPen_Custom_v02.blend")
STONE_TEX = os.path.join(TEX_DIR, "T_Stand_Stone_Marble_1024.png")

MM = 0.001
ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
OVERWRITE = "--overwrite" in ARGS

# --------------------------------------------------------------------------
# Design parameters (mm / degrees)
# --------------------------------------------------------------------------
TIP_X = -175.0            # PenTip (front of the writing ball)
REAR_X = 175.0            # rear end of the N frame -> overall length 350
BODY_FRONT_X = -160.0
BODY_REAR_X = 122.0       # body / rear-frame joint
DISPLAY_ANGLE = 16.0      # pen inclination on the stand

# Body cross sections, -Y half listed from top to bottom (mirrored to +Y).
# Every station has the same vertex count so facets can be lofted 1:1.
SEC_T = [(-1.3, 3.2), (-3.0, 2.0), (-3.7, 0.2), (-3.1, -1.9), (-1.4, -3.2)]
SEC_F = [(-1.6, 7.6), (-7.6, 5.0), (-9.6, 0.5), (-8.3, -4.6), (-3.6, -7.6)]
SEC_G = [(-3.2, 10.6), (-10.8, 8.2), (-13.0, -0.5), (-12.0, -7.8), (-6.0, -10.6)]
# window section: P1-P2-P3 collinear -> one flat 21mm facet for the slits
SEC_M = [(-4.5, 12.5), (-12.5, 10.0), (-14.0, -0.5), (-15.5, -11.0), (-6.0, -12.5)]
SEC_R1 = [(-5.2, 12.7), (-12.8, 10.4), (-16.0, 0.0), (-15.3, -10.6), (-6.2, -12.7)]
SEC_R1B = [(-6.8, 12.9), (-14.2, 9.2), (-15.6, -1.5), (-15.4, -10.9), (-9.5, -12.6)]
# rear section == outer section of the rear frame (30 x 24, 2mm chamfer)
FR_HW, FR_HT, FR_CH = 15.5, 13.0, 2.2
SEC_R2 = [(-(FR_HW - FR_CH), FR_HT), (-FR_HW, FR_HT - FR_CH), (-FR_HW, 0.0),
          (-FR_HW, -(FR_HT - FR_CH)), (-(FR_HW - FR_CH), -FR_HT)]
STATIONS = [(BODY_FRONT_X, SEC_T), (-128.0, SEC_F), (-98.0, SEC_G), (-68.0, SEC_M),
            (-30.0, SEC_M), (35.0, SEC_R1), (82.0, SEC_R1B),
            (BODY_REAR_X, SEC_R2)]

# colour windows (on the -Y window facet)
WIN_LEN, WIN_W, WIN_GAP = 18.0, 3.0, 8.0
WIN_POCKET_MARGIN, WIN_POCKET_DEPTH, WIN_RECESS = 0.4, 1.0, 0.35
WIN_CENTER_X = -49.0

# rear N frame
FRAME_T = 4.0             # bar thickness
FRAME_FRONT_PLATE = 4.0
FRAME_DIAG_HALF = 2.1     # half width of the N diagonal (perpendicular)

# stand
BASE_H = 25.0
BASE_HALF_D = 35.0
BASE_GOLD_H = 2.5
BASE_FRONT_SLANT = 10.0   # top front edge set back by this much
BASE_FRONT_CHAMFER = (12.0, 10.0)  # plan chamfer of the front corners (x, y)
TIP_OFFSET = 26.0         # PenTip from base front edge (x)
TIP_HEIGHT = 8.5          # PenTip above base top
FRONT_CONTACT_X = (-147.5, -142.5)  # pen-local x range resting on Stand_Front
CONTACT_GAP = 0.15
REAR_FRONT_ANGLE = 70.0
REAR_SEAT_FROM_X = 148.0   # pen-local x where the frame starts resting on the seat
REAR_BASE_OVERLAP = 0.45  # fraction of the support footprint that sits on the slab   # slant of the gold front face of Stand_Rear
REAR_HALF_W_BOTTOM, REAR_HALF_W_TOP = 30.0, 21.0
REAR_GOLD_BAND = 14.0

# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def say(*a):
    print("[NORECTIA]", *a, flush=True)


def mirror_half(half):
    """-Y half (top->bottom) -> closed ring ordered around the X axis."""
    ring = [(y, z) for (y, z) in half]                 # -Y side, top -> bottom
    ring += [(-y, z) for (y, z) in reversed(half)]     # +Y side, bottom -> top
    return ring


def new_collection(name, parent=None):
    col = bpy.data.collections.new(name)
    (parent or bpy.context.scene.collection).children.link(col)
    return col


def new_empty(name, col, parent=None, loc=(0, 0, 0), kind="PLAIN_AXES", size=0.01):
    ob = bpy.data.objects.new(name, None)
    ob.empty_display_type = kind
    ob.empty_display_size = size
    ob.location = Vector(loc)
    ob.parent = parent
    col.objects.link(ob)
    return ob


def bm_to_object(bm, name, mats, col, parent=None, scale_mm=True):
    if scale_mm:
        for v in bm.verts:
            v.co *= MM
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    ob = bpy.data.objects.new(name, me)
    col.objects.link(ob)
    ob.parent = parent
    return ob


def add_box(bm, center, axes, half, mat_index=0):
    """oriented box; axes = 3 orthonormal Vectors, half = 3 half sizes"""
    c = Vector(center)
    vs = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            for sz in (-1, 1):
                vs.append(bm.verts.new(c + axes[0] * (sx * half[0]) +
                                       axes[1] * (sy * half[1]) + axes[2] * (sz * half[2])))
    idx = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    for q in idx:
        f = bm.faces.new([vs[i] for i in q])
        f.material_index = mat_index
    return vs


def add_prism_xz(bm, poly_xz, y0, y1, mat_index=0):
    """extrude an XZ polygon between y0 and y1 (closed solid)"""
    a = [bm.verts.new((x, y0, z)) for (x, z) in poly_xz]
    b = [bm.verts.new((x, y1, z)) for (x, z) in poly_xz]
    n = len(poly_xz)
    faces = [bm.faces.new(a), bm.faces.new(list(reversed(b)))]
    for i in range(n):
        j = (i + 1) % n
        faces.append(bm.faces.new((a[i], a[j], b[j], b[i])))
    for f in faces:
        f.material_index = mat_index
    return faces


def finalize_normals(bm):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])


def apply_boolean(ob, cutter, op="DIFFERENCE"):
    mod = ob.modifiers.new("BOOL_tmp", "BOOLEAN")
    mod.operation = op
    mod.solver = "EXACT"
    mod.object = cutter
    try:
        mod.material_mode = "INDEX"
    except Exception:
        pass
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    old = ob.data
    ob.modifiers.remove(mod)
    ob.data = me
    me.name = old.name
    bpy.data.meshes.remove(old)
    # the operand adds an empty material slot; drop empty slots no face uses
    used = {p.material_index for p in me.polygons}
    for i in reversed(range(len(me.materials))):
        if me.materials[i] is None and i not in used and i == len(me.materials) - 1:
            me.materials.pop(index=i)


def remove_object(ob):
    me = ob.data
    bpy.data.objects.remove(ob)
    if me is not None and me.users == 0:
        bpy.data.meshes.remove(me)


def cleanup_mesh(ob, angle=0.5, dissolve=True):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=0.00002)
    if dissolve:
        bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(angle), use_dissolve_boundaries=False,
                                 verts=bm.verts[:], edges=bm.edges[:], delimit={'MATERIAL'})
    bm.to_mesh(ob.data)
    bm.free()


def shade_smooth(ob):
    for p in ob.data.polygons:
        p.use_smooth = True


def add_bevel_wn(ob, width_mm, angle_deg=30.0, segments=1):
    bev = ob.modifiers.new("Bevel", "BEVEL")
    bev.width = width_mm * MM
    bev.segments = segments
    bev.limit_method = "ANGLE"
    bev.angle_limit = math.radians(angle_deg)
    bev.miter_outer = "MITER_ARC" if segments > 1 else "MITER_SHARP"
    try:
        bev.use_clamp_overlap = True
    except Exception:
        pass
    wn = ob.modifiers.new("WeightedNormal", "WEIGHTED_NORMAL")
    wn.mode = "FACE_AREA"
    wn.weight = 100
    wn.keep_sharp = True
    shade_smooth(ob)


def select_only(ob):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob


def smart_uv(ob, angle=50.0, margin=0.01):
    select_only(ob)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(angle), island_margin=margin,
                             area_weight=0.0, correct_aspect=True, scale_to_bounds=False)
    bpy.ops.object.mode_set(mode="OBJECT")


def box_uv_world(ob, tile_mm=300.0):
    """World-scale box mapping for the tiling stone texture."""
    me = ob.data
    if not me.uv_layers:
        me.uv_layers.new(name="UVMap")
    uv = me.uv_layers.active.data
    mw = ob.matrix_world
    s = 1.0 / (tile_mm * MM)
    for p in me.polygons:
        n = (mw.to_3x3() @ p.normal)
        ax = max(range(3), key=lambda i: abs(n[i]))
        for li in p.loop_indices:
            co = mw @ me.vertices[me.loops[li].vertex_index].co
            if ax == 0:
                u, v = co.y * math.copysign(1, n.x), co.z
            elif ax == 1:
                u, v = -co.x * math.copysign(1, n.y), co.z
            else:
                u, v = co.x, co.y * math.copysign(1, n.z)
            # per-axis offset so the same vein does not repeat on every face
            uv[li].uv = (u * s + 0.37 * ax, v * s + 0.19 * ax)


def tri_count(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    me.calc_loop_triangles()
    n = len(me.loop_triangles)
    ev.to_mesh_clear()
    return n


# --------------------------------------------------------------------------
# materials + texture
# --------------------------------------------------------------------------
def principled(name, base, metallic, rough, emission=None, strength=0.0, coat=0.0,
               aniso=0.0):
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    nt = m.node_tree
    bsdf = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
    if bsdf is None:
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
        out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
        nt.links.new(bsdf.outputs[0], out.inputs[0])
    bsdf.inputs["Base Color"].default_value = (*base, 1.0)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = rough
    if coat:
        bsdf.inputs["Coat Weight"].default_value = coat
        bsdf.inputs["Coat Roughness"].default_value = 0.25
    if aniso and "Anisotropic" in bsdf.inputs:
        bsdf.inputs["Anisotropic"].default_value = aniso
    if emission is not None:
        bsdf.inputs["Emission Color"].default_value = (*emission, 1.0)
        bsdf.inputs["Emission Strength"].default_value = strength
    m.diffuse_color = (*base, 1.0)
    m.metallic = metallic
    m.roughness = rough
    return m, bsdf


def make_marble_texture(path, n=1024):
    """Tileable black marble with restrained white veins (linear -> sRGB PNG)."""
    def fbm(beta, seed):
        r = np.random.default_rng(seed)
        F = np.fft.fft2(r.standard_normal((n, n)))
        fx = np.fft.fftfreq(n)[:, None]
        fy = np.fft.fftfreq(n)[None, :]
        f = np.sqrt(fx * fx + fy * fy)
        f[0, 0] = 1.0
        F *= f ** (-beta)
        F[0, 0] = 0
        o = np.real(np.fft.ifft2(F))
        return (o - o.mean()) / o.std()

    u, v = np.meshgrid(np.arange(n) / n, np.arange(n) / n, indexing="xy")
    t1, t2, t3 = fbm(2.0, 11), fbm(2.3, 12), fbm(1.7, 13)
    cloud, mask_n, width_n = fbm(1.5, 14), fbm(1.3, 15), fbm(1.8, 16)
    # main diagonal veins (integer frequencies keep the tile seamless)
    ph1 = 2 * np.pi * (2 * u + 1 * v) + 1.9 * t1
    w1 = 0.022 + 0.012 * np.clip(width_n, -1.5, 1.5)
    vein1 = np.exp(-np.abs(np.sin(ph1)) / np.maximum(w1 * 0.7, 0.005))
    # thin crossing hairlines
    ph2 = 2 * np.pi * (1 * u - 3 * v) + 2.6 * t2
    vein2 = np.exp(-np.abs(np.sin(ph2)) / 0.010)
    ph3 = 2 * np.pi * (3 * u + 2 * v) + 3.2 * t3
    vein3 = np.exp(-np.abs(np.sin(ph3)) / 0.007)
    m1 = np.clip(0.55 + 0.45 * mask_n, 0, 1)
    veins = np.clip(vein1 * m1 * 0.85 + vein2 * (1 - m1) * 0.55 + vein3 * 0.25, 0, 1)
    base = 0.016 + 0.006 * np.tanh(cloud)          # near black, soft clouds
    vein_col = 0.24
    lin = base * (1 - veins) + vein_col * veins
    rgb = np.stack([lin * 1.00, lin * 0.985, lin * 0.965], axis=-1)
    srgb = np.where(rgb <= 0.0031308, rgb * 12.92, 1.055 * np.power(rgb, 1 / 2.4) - 0.055)
    srgb = np.clip(srgb, 0, 1)

    os.makedirs(os.path.dirname(path), exist_ok=True)
    img = bpy.data.images.new("T_Stand_Stone_Marble_1024", n, n, alpha=False)
    rgba = np.concatenate([srgb, np.ones((n, n, 1))], axis=-1)
    img.pixels.foreach_set(rgba[::-1].astype(np.float32).ravel())  # Blender is bottom-up
    img.filepath_raw = path
    img.file_format = "PNG"
    img.save()
    img.filepath = bpy.path.relpath(path) if bpy.data.filepath else path
    return img


def build_materials():
    M = {}
    M["pen"], _ = principled("MAT_Pen_Charcoal", (0.026, 0.026, 0.028), 0.45, 0.52)
    M["gold"], _ = principled("MAT_Metal_Champagne", (0.44, 0.32, 0.18), 1.0, 0.32, aniso=0.3)
    M["dark"], _ = principled("MAT_DarkMetal", (0.20, 0.20, 0.21), 1.0, 0.22)
    M["win"], _ = principled("MAT_ColorWindow", (0.85, 0.95, 1.0), 0.0, 0.3,
                             emission=(0.62, 0.86, 1.0), strength=2.2)
    M["stone"], bsdf = principled("MAT_Stand_Stone", (0.02, 0.02, 0.02), 0.0, 0.32)
    img = make_marble_texture(STONE_TEX)
    nt = M["stone"].node_tree
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.location = (-400, 200)
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    M["stone"]["texture"] = os.path.basename(STONE_TEX)
    return M, img


# --------------------------------------------------------------------------
# pen
# --------------------------------------------------------------------------
def build_body(mats, col, parent):
    """Faceted body: lofted sections, quads split along convex diagonals so the
    surface reads as planar triangles/trapezoids (architectural facets)."""
    bm = bmesh.new()
    rings = []
    for x, half in STATIONS:
        rings.append([bm.verts.new((x, y, z)) for (y, z) in mirror_half(half)])
    N = len(rings[0])
    eps = 0.03
    for k in range(len(rings) - 1):
        A, B = rings[k], rings[k + 1]
        for i in range(N):
            a, b, c, d = A[i], A[(i + 1) % N], B[(i + 1) % N], B[i]
            axis = Vector(((a.co.x + c.co.x) * 0.5, 0, 0))
            n1 = (b.co - a.co).cross(c.co - a.co)
            if n1.length < 1e-9:
                n1 = (c.co - a.co).cross(d.co - a.co)
            n1.normalize()
            if n1.dot(a.co - axis) < 0:
                n1 = -n1
            dist = (d.co - a.co).dot(n1)
            if abs(dist) < eps:
                bm.faces.new((a, b, c, d))
            elif dist < 0:   # convex fold along a-c
                bm.faces.new((a, b, c))
                bm.faces.new((a, c, d))
            else:            # convex fold along b-d
                bm.faces.new((a, b, d))
                bm.faces.new((b, c, d))
    front = bm.faces.new(list(reversed(rings[0])))
    rear = bm.faces.new(rings[-1])
    finalize_normals(bm)
    bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(0.4), use_dissolve_boundaries=False,
                             verts=bm.verts[:], edges=bm.edges[:])
    bm.normal_update()

    # champagne accent facets (from reference: gold triangles on the tapered
    # front top/bottom, and the gold upper-side triangle behind the windows)
    for f in bm.faces:
        cx = f.calc_center_median()
        n = f.normal
        if cx.x < -126.0 and abs(n.x) < 0.9 and abs(n.z) > 0.45:
            f.material_index = 1
        if 35.0 < cx.x < 82.0 and n.z > 0.25 and abs(n.y) > 0.4 and cx.z > 4.0:
            f.material_index = 1
    ob = bm_to_object(bm, "Pen_Body", [mats["pen"], mats["gold"], mats["dark"]], col, parent)
    return ob


def window_frame():
    """orthonormal frame of the window facet (P1->P3 of SEC_M, -Y side)"""
    p1, p3 = Vector((0, *SEC_M[1])), Vector((0, *SEC_M[3]))
    v = (p3 - p1).normalized()                    # along facet, pointing down
    n = Vector((1, 0, 0)).cross(v).normalized()   # outward?
    if n.y > 0:
        n = -n
    c = (p1 + p3) * 0.5
    return Vector((1, 0, 0)), v, n, c


def window_centers():
    pitch = WIN_W + WIN_GAP
    return [WIN_CENTER_X + (i - 1) * pitch for i in range(3)]


def cut_window_pockets(body, col):
    u, v, n, c = window_frame()
    bm = bmesh.new()
    for x in window_centers():
        center = Vector((x, c.y, c.z)) + n * ((1.5 - WIN_POCKET_DEPTH) * 0.5)
        add_box(bm, center, (u, v, n),
                (WIN_W * 0.5 + WIN_POCKET_MARGIN, WIN_LEN * 0.5 + WIN_POCKET_MARGIN,
                 (1.5 + WIN_POCKET_DEPTH) * 0.5), mat_index=2)
    finalize_normals(bm)
    cutter = bm_to_object(bm, "CUT_windows", [], col, body.parent)
    apply_boolean(body, cutter)
    remove_object(cutter)


def build_windows(mats, col, parent):
    u, v, n, c = window_frame()
    obs = []
    for i, x in enumerate(window_centers()):
        bm = bmesh.new()
        ctr = Vector((x, c.y, c.z)) - n * WIN_RECESS
        hu, hv = WIN_W * 0.5, WIN_LEN * 0.5
        vs = [bm.verts.new(ctr + u * su * hu + v * sv * hv)
              for (su, sv) in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        f = bm.faces.new(vs)
        f.normal_update()
        if f.normal.dot(n) < 0:
            f.normal_flip()
        uvl = bm.loops.layers.uv.new("UVMap")
        for loop in f.loops:
            p = loop.vert.co - ctr
            loop[uvl].uv = (p.dot(u) / (2 * hu) + 0.5, p.dot(v) / (2 * hv) + 0.5)
        ob = bm_to_object(bm, "Pen_ColorWindow_%02d" % (i + 1), [mats["win"]], col, parent)
        ob["qvpen_role"] = "color_indicator"
        obs.append(ob)
    return obs


def octagon(x, r):
    return [(x, r * math.cos(math.radians(22.5 + 45 * i)), r * math.sin(math.radians(22.5 + 45 * i)))
            for i in range(8)]


def build_tip(mats, col, parent):
    """3-stage tip: (1) body taper (in Pen_Body) (2) champagne collar + faceted
    dark-metal cone (3) writing ball."""
    bm = bmesh.new()
    rings = [(octagon(BODY_FRONT_X + 0.4, 3.15), 0), (octagon(BODY_FRONT_X - 4.0, 2.6), 0),
             (octagon(BODY_FRONT_X - 4.0, 2.42), 1), (octagon(-173.3, 0.82), 1)]
    vr = [[bm.verts.new(p) for p in r] for r, _ in rings]
    for k in (0, 2):
        A, B = vr[k], vr[k + 1]
        for i in range(8):
            f = bm.faces.new((A[i], A[(i + 1) % 8], B[(i + 1) % 8], B[i]))
            f.material_index = rings[k][1]
    f = bm.faces.new(vr[1])      # collar front ring face (visible around the cone)
    f.material_index = 0
    f = bm.faces.new(vr[3])      # cone end (inside ball)
    f.material_index = 1
    # the collar back cap and cone back cap are hidden -> omitted
    # writing ball
    ret = bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=8, radius=1.0,
                                    matrix=Matrix.Translation((-174.0, 0, 0)) @
                                    Matrix.Rotation(math.radians(90), 4, "Y"))
    for fv in {f for v in ret["verts"] for f in v.link_faces}:
        fv.material_index = 1
    finalize_normals(bm)
    bm.normal_update()
    ob = bm_to_object(bm, "Pen_TipMesh", [mats["gold"], mats["dark"]], col, parent)
    return ob


def build_rear_frame(mats, col, parent):
    x0, x1 = BODY_REAR_X, REAR_X
    bm = bmesh.new()
    sec = mirror_half(SEC_R2)
    # drop the collinear mid-side points for the frame prism
    sec = [p for p in sec if not (abs(abs(p[0]) - FR_HW) < 1e-6 and abs(p[1]) < 1e-6)]
    A = [bm.verts.new((x0, y, z)) for (y, z) in sec]
    B = [bm.verts.new((x1, y, z)) for (y, z) in sec]
    n = len(sec)
    bm.faces.new(list(reversed(A)))
    bm.faces.new(B)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((A[i], A[j], B[j], B[i]))
    finalize_normals(bm)
    frame = bm_to_object(bm, "Pen_RearFrame", [mats["gold"]], col, parent)

    iy, iz = FR_HW - FRAME_T, FR_HT - FRAME_T
    xa, xb = x0 + FRAME_FRONT_PLATE, x1 - FRAME_T
    X, Y, Z = Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))
    boxes = [
        # inner cavity, open at the rear end
        (((xa + x1 + 10) * 0.5, 0, 0), ((x1 + 10 - xa) * 0.5, iy, iz)),
        # top / bottom openings (rails of FRAME_T remain along the edges)
        (((xa + xb) * 0.5, 0, 0), ((xb - xa) * 0.5, iy, FR_HT + 5)),
    ]
    for ctr, half in boxes:
        cb = bmesh.new()
        add_box(cb, ctr, (X, Y, Z), half)
        finalize_normals(cb)
        cut1 = bm_to_object(cb, "CUT_frame_box", [], col, parent)
        apply_boolean(frame, cut1)
        remove_object(cut1)

    # side openings: two triangles per side leaving an N diagonal.
    # -Y side (seen with the tip on the left): diagonal top-front -> bottom-rear
    # +Y side (seen with the tip on the right): diagonal top-rear -> bottom-front
    L, H = xb - xa, 2 * iz
    slope = H / L
    dz = FRAME_DIAG_HALF / math.cos(math.atan(slope))
    dx = dz / slope

    def tris(flip):
        up = [(xa + dx, iz), (xb, iz), (xb, -iz + dz)]
        lo = [(xa, iz - dz), (xa, -iz), (xb - dx, -iz)]
        if flip:  # mirror in x around the window centre
            m = lambda p: (xa + xb - p[0], p[1])
            up, lo = [m(p) for p in reversed(up)], [m(p) for p in reversed(lo)]
        return up, lo

    for side, flip in ((-1, False), (1, True)):
        sb = bmesh.new()
        for poly in tris(flip):
            y0, y1 = (side * (FR_HW + 5), side * (iy - 0.5))
            add_prism_xz(sb, poly, min(y0, y1), max(y0, y1))
        finalize_normals(sb)
        cut = bm_to_object(sb, "CUT_frame_side", [], col, parent)
        apply_boolean(frame, cut)
        remove_object(cut)
    cleanup_mesh(frame)
    frame["design"] = "N-frame: open box, side diagonals mirrored (N from either side)"
    return frame


# --------------------------------------------------------------------------
# stand
# --------------------------------------------------------------------------
class PenPlacement:
    def __init__(self, base_front_x):
        a = math.radians(DISPLAY_ANGLE)
        self.c, self.s = math.cos(a), math.sin(a)
        tip = Vector((base_front_x + TIP_OFFSET, 0, BASE_H + TIP_HEIGHT))
        self.P = tip + Vector((-TIP_X * self.c, 0, -TIP_X * self.s))

    def W(self, lx, lz, ly=0.0):
        return Vector((self.P.x + lx * self.c - lz * self.s, ly,
                       self.P.z + lx * self.s + lz * self.c))

    def matrix(self):
        return (Matrix.Translation(self.P * MM) @
                Matrix.Rotation(math.radians(-DISPLAY_ANGLE), 4, "Y"))


def rear_profile(pp):
    """XZ profile of Stand_Rear (world mm, base top = BASE_H)."""
    lz_seat = -FR_HT - CONTACT_GAP
    q1 = pp.W(REAR_SEAT_FROM_X, lz_seat)          # seat front edge
    q2 = pp.W(REAR_X + 0.3, lz_seat)              # seat / lip corner
    q3 = pp.W(REAR_X + 0.3, FR_HT - 1.5)          # lip top (behind frame top)
    q4 = Vector((q3.x + 5.0, 0, q3.z + 2.0))      # apex
    q5 = Vector((q4.x + 25.0, 0, 0.0))            # back bottom on the floor (near vertical back)
    q0 = Vector((q1.x - (q1.z - BASE_H) / math.tan(math.radians(REAR_FRONT_ANGLE)), 0, BASE_H))
    # the slab ends under the support; the support steps down over its end
    xr = q0.x + (q5.x - q0.x) * REAR_BASE_OVERLAP
    q6 = Vector((xr, 0, 0.0))
    q7 = Vector((xr, 0, BASE_H))
    return [q0, q1, q2, q3, q4, q5, q6, q7]


def stand_extent():
    pp = PenPlacement(0.0)
    prof = rear_profile(pp)
    return prof[5].x, prof[7].x


def build_stand_base(mats, col, parent, xf, xr):
    cx, cy = BASE_FRONT_CHAMFER
    hd = BASE_HALF_D

    def outline(shift):
        return [(xf + shift, -hd + cy), (xf + shift + cx, -hd), (xr, -hd),
                (xr, hd), (xf + shift + cx, hd), (xf + shift, hd - cy)]

    bm = bmesh.new()
    zs = [0.0, BASE_GOLD_H, BASE_H]
    rings = [[bm.verts.new((x, y, z)) for (x, y) in outline(BASE_FRONT_SLANT * z / BASE_H)] for z in zs]
    bot = bm.faces.new(list(reversed(rings[0])))
    bot.material_index = 1
    top = bm.faces.new(rings[2])
    top.material_index = 0
    n = len(rings[0])
    for k in range(2):
        for i in range(n):
            j = (i + 1) % n
            f = bm.faces.new((rings[k][i], rings[k][j], rings[k + 1][j], rings[k + 1][i]))
            f.material_index = 1 if k == 0 else 0
    finalize_normals(bm)
    return bm_to_object(bm, "Stand_Base", [mats["stone"], mats["gold"]], col, parent)


def build_stand_front(mats, col, parent, pen_bvh, pp):
    """low faceted pedestal: stone plinth + champagne pyramid cap whose top is
    a shallow V matched to the underside of the pen (CONTACT_GAP)."""
    xs = FRONT_CONTACT_X
    tops = {}
    # the top follows the lowest line of the pen (bottom centre); a cradle
    # surface spanning several sampled points would cut into the convex
    # underside, so every top vertex uses the centre-line height.
    for lx in xs:
        hit = pen_bvh.ray_cast(Vector((lx, 0.0, -60.0)), Vector((0, 0, 1)))
        if hit[0] is None:
            raise RuntimeError("front contact ray missed the pen at x=%s" % lx)
        lz = hit[0].z - CONTACT_GAP
        for ly in (-3.0, 0.0, 3.0):
            tops[(lx, ly)] = pp.W(lx, lz, ly)
    xc = (tops[(xs[0], 0.0)].x + tops[(xs[1], 0.0)].x) * 0.5
    bm = bmesh.new()
    zb, zm = BASE_H, BASE_H + 2.5
    r0 = [bm.verts.new((xc + sx * 15.0, sy * 12.5, zb)) for sx, sy in ((-1, -1), (-1, 1), (1, 1), (1, -1))]
    m = [bm.verts.new((xc + sx * 13.8, sy * 11.3, zm)) for sx, sy in ((-1, -1), (-1, 1), (1, 1), (1, -1))]
    fl, fc, fr = (bm.verts.new(tops[(xs[0], y)]) for y in (-3.0, 0.0, 3.0))
    bl, bc, br = (bm.verts.new(tops[(xs[1], y)]) for y in (-3.0, 0.0, 3.0))
    stone = []
    for i in range(4):
        j = (i + 1) % 4
        stone.append(bm.faces.new((r0[i], r0[j], m[j], m[i])))
    gold = [
        bm.faces.new((fl, fc, bc, bl)), bm.faces.new((fc, fr, br, bc)),            # V top
        bm.faces.new((m[0], m[1], fc)), bm.faces.new((m[1], fr, fc)), bm.faces.new((m[0], fc, fl)),  # front
        bm.faces.new((m[1], m[2], br, fr)),                                          # +Y
        bm.faces.new((m[2], m[3], bc)), bm.faces.new((m[3], bl, bc)), bm.faces.new((m[2], bc, br)),  # back
        bm.faces.new((m[3], m[0], fl, bl)),                                          # -Y
    ]
    for f in gold:
        f.material_index = 1
    # orient normals outward (open bottom -> do it manually)
    ctr = Vector((xc, 0, zb))
    for f in bm.faces:
        f.normal_update()
        if f.normal.dot(f.calc_center_median() - ctr) < 0:
            f.normal_flip()
    ob = bm_to_object(bm, "Stand_Front", [mats["stone"], mats["gold"]], col, parent)
    return ob


def build_stand_rear(mats, col, parent, pp):
    prof = rear_profile(pp)
    H = max(p.z for p in prof)

    def hw(z):
        return REAR_HALF_W_BOTTOM + (REAR_HALF_W_TOP - REAR_HALF_W_BOTTOM) * z / H

    bm = bmesh.new()
    L = [bm.verts.new((p.x, -hw(p.z), p.z)) for p in prof]
    R = [bm.verts.new((p.x, hw(p.z), p.z)) for p in prof]
    n = len(prof)
    bm.faces.new(L)
    bm.faces.new(list(reversed(R)))
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((L[i], L[j], R[j], R[i]))
    finalize_normals(bm)

    q0, q1, q2, q3, q4, q5, q6, q7 = prof
    # architectural facets on the stone flanks: a large crease running from the
    # apex down to the base (as in the reference), plus a narrow chamfer on the
    # rear vertical corners.
    for side in (-1, 1):
        cuts = []
        A = Vector((q4.x, side * hw(q4.z), q4.z))
        B = Vector((q6.x + 3.0, side * hw(0.0), 0.0))
        C = Vector((q5.x, side * (hw(0.0) - 9.0), 0.0))
        cuts.append((A, B, C, Vector((q5.x, side * hw(0.0), 0.0))))
        A2 = Vector((q4.x, side * (hw(q4.z) - 3.0), q4.z))
        B2 = Vector((q5.x - 7.0, side * hw(0.0), 0.0))
        C2 = Vector((q5.x, side * (hw(0.0) - 16.0), 0.0))
        cuts.append((A2, B2, C2, Vector((q5.x, side * hw(0.0), 0.0))))
        for A, B, C, corner in cuts:
            nrm = (B - A).cross(C - A).normalized()
            if nrm.dot(corner - A) < 0:
                nrm = -nrm
            bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], dist=1e-4,
                                   plane_co=A, plane_no=nrm, clear_outer=True)
            bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary], sides=0)
    finalize_normals(bm)

    # gold band: everything within REAR_GOLD_BAND of the slanted front face
    t = (q1 - q0).normalized()
    nf = Vector((-t.z, 0, t.x))          # perpendicular in XZ
    if nf.x > 0:
        nf = -nf                          # point toward -X (front)
    co = q0 - nf * REAR_GOLD_BAND
    bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], dist=1e-4,
                           plane_co=co, plane_no=nf, clear_outer=False, clear_inner=False)
    bm.normal_update()
    seat_n = Vector((-pp.s, 0, pp.c))
    lip_n = Vector((-pp.c, 0, -pp.s))
    for f in bm.faces:
        cen = f.calc_center_median()
        if (cen - co).dot(nf) > 0.01:
            f.material_index = 1
        elif f.normal.dot(seat_n) > 0.995 or f.normal.dot(lip_n) > 0.995:
            f.material_index = 1
    # hidden faces resting on / against Stand_Base
    bm.normal_update()
    bottom = [f for f in bm.faces
              if (f.normal.z < -0.999 and abs(f.calc_center_median().z - BASE_H) < 1e-3)
              or (f.normal.x < -0.999 and abs(f.calc_center_median().x - q7.x) < 1e-3)]
    bmesh.ops.delete(bm, geom=bottom, context="FACES_ONLY")
    ob = bm_to_object(bm, "Stand_Rear", [mats["stone"], mats["gold"]], col, parent)
    return ob, prof


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def main():
    if os.path.exists(BLEND_PATH) and not OVERWRITE:
        raise SystemExit("%s exists - refusing to overwrite (pass --overwrite)" % BLEND_PATH)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    sc.unit_settings.scale_length = 1.0
    sc.unit_settings.length_unit = "MILLIMETERS"

    mats, stone_img = build_materials()

    col_pen = new_collection("NORECTIA_Pen")
    col_stand = new_collection("NORECTIA_PenStand")
    col_tmp = new_collection("_tmp")

    # stand layout: centre the whole stand on the world origin
    length, base_len = stand_extent()
    xf = -length * 0.5
    xr = xf + base_len
    pp = PenPlacement(xf)

    pen_root = new_empty("NORECTIA_Pen", col_pen, kind="ARROWS", size=0.03)
    pen_root.matrix_world = pp.matrix()
    pen_root["display_angle_deg"] = DISPLAY_ANGLE
    pen_root["note"] = "Reset this object's transform to get the neutral pen (tip -X, origin = PenCenter)."

    body = build_body(mats, col_pen, pen_root)
    cut_window_pockets(body, col_tmp)
    cleanup_mesh(body, angle=0.3)
    # body rear cap is fully covered by the frame front plate -> remove
    bm = bmesh.new()
    bm.from_mesh(body.data)
    bm.normal_update()
    rear = [f for f in bm.faces if f.normal.x > 0.999 and abs(f.calc_center_median().x - BODY_REAR_X * MM) < 1e-6]
    bvh_bm = bm.copy()
    bmesh.ops.delete(bm, geom=rear, context="FACES_ONLY")
    bm.to_mesh(body.data)
    bm.free()
    for v in bvh_bm.verts:
        v.co /= MM
    pen_bvh = BVHTree.FromBMesh(bvh_bm)
    bvh_bm.free()

    tip = build_tip(mats, col_pen, pen_root)
    frame = build_rear_frame(mats, col_pen, pen_root)
    wins = build_windows(mats, col_pen, pen_root)

    e_tip = new_empty("PenTip", col_pen, pen_root, (TIP_X * MM, 0, 0), "SPHERE", 0.002)
    e_grip = new_empty("GripPoint", col_pen, pen_root, (-98.0 * MM, 0, 0), "ARROWS", 0.015)
    e_ctr = new_empty("PenCenter", col_pen, pen_root, (0, 0, 0), "PLAIN_AXES", 0.02)
    e_tip["qvpen_role"] = "draw origin (front of writing ball)"

    stand_root = new_empty("NORECTIA_PenStand", col_stand, kind="ARROWS", size=0.05)
    base = build_stand_base(mats, col_stand, stand_root, xf, xr)
    front = build_stand_front(mats, col_stand, stand_root, pen_bvh, pp)
    rear_ob, prof = build_stand_rear(mats, col_stand, stand_root, pp)

    # modifiers (non destructive, applied on export)
    add_bevel_wn(body, 0.35, angle_deg=1.0)
    add_bevel_wn(frame, 0.3, angle_deg=30.0)
    add_bevel_wn(tip, 0.12, angle_deg=40.0)
    for ob in (base, front, rear_ob):
        add_bevel_wn(ob, 0.7, angle_deg=30.0)

    # UVs
    for ob in (body, frame, tip):
        smart_uv(ob)
    for ob in (base, front, rear_ob):
        box_uv_world(ob)

    bpy.data.collections.remove(col_tmp)

    # pack + save
    stone_img.pack()
    sc["norectia_version"] = "v02"
    bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH, compress=True, relative_remap=True)
    say("saved", BLEND_PATH)
    for ob in (body, tip, frame, *wins, base, front, rear_ob):
        say("tris %-22s %6d" % (ob.name, tri_count(ob)))
    say("rear profile", [tuple(round(c, 2) for c in (p.x, p.z)) for p in prof])
    say("stand length", round(length, 2), "xf", round(xf, 2))


if __name__ == "__main__":
    main()
