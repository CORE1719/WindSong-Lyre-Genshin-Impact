"""
Verification renders for NORECTIA_QvPen_Custom_v02.blend (Cycles, CPU).

The studio set (cyclorama, lights, cameras) is created in memory only; the
.blend is never saved by this script.

    python render_views.py [view ...] [--samples N] [--scale 0.5]
"""
import bpy
import math
import os
import sys
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
BLEND = os.path.join(ROOT, "NORECTIA_QvPen_Custom_v02.blend")
OUT = os.path.join(ROOT, "renders")
MM = 0.001

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
SAMPLES = 96
SCALE = 1.0
views_req = []
i = 0
while i < len(args):
    if args[i] == "--samples":
        SAMPLES = int(args[i + 1]); i += 2; continue
    if args[i] == "--scale":
        SCALE = float(args[i + 1]); i += 2; continue
    views_req.append(args[i]); i += 1

bpy.ops.wm.open_mainfile(filepath=BLEND)
sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.cycles.device = "CPU"
sc.cycles.samples = SAMPLES
sc.cycles.use_denoising = True
sc.cycles.max_bounces = 8
sc.render.film_transparent = False
sc.view_settings.view_transform = "AgX"
sc.view_settings.look = "AgX - Medium High Contrast"
sc.render.image_settings.file_format = "PNG"

pen = bpy.data.objects["NORECTIA_Pen"]
stand = bpy.data.objects["NORECTIA_PenStand"]
PEN_DISPLAY = pen.matrix_world.copy()
pen_parts = [o for o in bpy.data.objects if o.parent == pen]
stand_parts = [o for o in bpy.data.objects if o.parent == stand]

# ---------------------------------------------------------------- studio set
studio = bpy.data.collections.new("_Studio_RenderOnly")
sc.collection.children.link(studio)


def make_cyc():
    import bmesh
    bm = bmesh.new()
    prof = []
    R = 1.0
    for k in range(13):  # floor -> quarter circle -> wall
        a = math.radians(90 * k / 12)
        prof.append((1.2 + R * math.sin(a), R - R * math.cos(a)))
    prof = [(-6.0, 0.0)] + prof + [(1.2 + R, 6.0)]
    rows = []
    for (y, z) in prof:
        rows.append([bm.verts.new((x, y, z)) for x in (-8.0, 8.0)])
    for a, b in zip(rows, rows[1:]):
        bm.faces.new((a[0], a[1], b[1], b[0]))
    me = bpy.data.meshes.new("Studio_Cyc")
    bm.to_mesh(me)
    for p in me.polygons:
        p.use_smooth = True
    ob = bpy.data.objects.new("Studio_Cyc", me)
    ob.location.z = -0.00005
    studio.objects.link(ob)
    m = bpy.data.materials.new("STUDIO_Cyc")
    nt = m.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (0.26, 0.245, 0.23, 1)
    # glossy floor, matte wall (roughness driven by height)
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value = 0.0
    mr.inputs["From Max"].default_value = 0.25
    mr.inputs["To Min"].default_value = 0.13
    mr.inputs["To Max"].default_value = 0.65
    nt.links.new(geo.outputs["Position"], sep.inputs[0])
    nt.links.new(sep.outputs["Z"], mr.inputs["Value"])
    nt.links.new(mr.outputs["Result"], bsdf.inputs["Roughness"])
    me.materials.append(m)
    return ob


cyc = make_cyc()

world = bpy.data.worlds.new("STUDIO_World")
sc.world = world
bg = next(n for n in world.node_tree.nodes if n.type == "BACKGROUND")
bg.inputs[0].default_value = (0.42, 0.40, 0.38, 1)
bg.inputs[1].default_value = 0.45


def area(name, loc, target, size, power, color=(1, 0.97, 0.93), sx=None):
    ld = bpy.data.lights.new(name, "AREA")
    ld.shape = "RECTANGLE"
    ld.size = size
    ld.size_y = sx if sx else size
    ld.energy = power
    ld.color = color
    ob = bpy.data.objects.new(name, ld)
    ob.location = Vector(loc)
    d = Vector(target) - ob.location
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    studio.objects.link(ob)
    return ob


area("L_Key", (-0.35, -0.75, 0.95), (0, 0, 0.06), 1.0, 26)
area("L_Top", (0.05, 0.05, 1.2), (0, 0, 0), 1.4, 20, sx=0.6)
area("L_Rim", (0.55, 0.65, 0.45), (0, 0, 0.08), 0.8, 14, color=(0.95, 0.97, 1.0))
area("L_Fill", (0.6, -0.8, 0.25), (0, 0, 0.06), 0.9, 7)

cam_data = bpy.data.cameras.new("CAM")
cam_data.sensor_width = 36
cam = bpy.data.objects.new("CAM", cam_data)
studio.objects.link(cam)
sc.camera = cam


def set_cam(loc, target, lens=60, ortho=None, up="Y"):
    cam.location = Vector(loc)
    d = Vector(target) - cam.location
    cam.rotation_euler = d.to_track_quat("-Z", up).to_euler()
    if ortho:
        cam_data.type = "ORTHO"
        cam_data.ortho_scale = ortho
    else:
        cam_data.type = "PERSP"
        cam_data.lens = lens
    cam_data.clip_start = 0.005
    cam_data.clip_end = 20


def show(pen_on=True, stand_on=True, studio_on=True):
    for o in pen_parts + [pen]:
        o.hide_render = not pen_on
    for o in stand_parts + [stand]:
        o.hide_render = not stand_on
    cyc.hide_render = not studio_on


def pen_pose(mat):
    pen.matrix_world = mat


def pen_local(x, y=0, z=0):
    return PEN_DISPLAY @ Vector((x * MM, y * MM, z * MM))


NEUTRAL = Matrix.Translation((0, 0, 0.12))   # pen alone, horizontal, 120mm up


def neutral(x, y=0, z=0):
    return NEUTRAL @ Vector((x * MM, y * MM, z * MM))


VIEWS = {}


def view(name, res=(1440, 1080)):
    def deco(fn):
        VIEWS[name] = (fn, res)
        return fn
    return deco


@view("01_reference_angle")
def _():
    show(True, True, True); pen_pose(PEN_DISPLAY)
    set_cam((0.0, -0.56, 0.10), (0.0, 0.0, 0.068), lens=50)


@view("12_display_three_quarter")
def _():
    show(True, True, True); pen_pose(PEN_DISPLAY)
    set_cam((-0.42, -0.55, 0.26), (0.0, 0.0, 0.055), lens=55)


@view("11_stand_only")
def _():
    show(False, True, True)
    set_cam((-0.38, -0.60, 0.28), (0.0, 0.0, 0.045), lens=55)


def pen_alone_ortho(name, loc_off, up="Y", scale=0.39):
    @view(name, (1600, 700))
    def _():
        show(True, False, False); pen_pose(NEUTRAL)
        c = neutral(0)
        set_cam(c + Vector(loc_off), c, ortho=scale, up=up)


pen_alone_ortho("02_pen_left_side_-Y", (0, -1.0, 0))
pen_alone_ortho("03_pen_right_side_+Y", (0, 1.0, 0))
pen_alone_ortho("04_pen_top_+Z", (0, 0, 1.0), up="Y")
pen_alone_ortho("05_pen_bottom_-Z", (0, 0, -1.0), up="Y")


@view("06_pen_front_from_tip", (900, 900))
def _():
    show(True, False, False); pen_pose(NEUTRAL)
    c = neutral(0)
    set_cam(c + Vector((-1.0, 0, 0)), c, ortho=0.045)


@view("07_pen_back_from_rear", (900, 900))
def _():
    show(True, False, False); pen_pose(NEUTRAL)
    c = neutral(0)
    set_cam(c + Vector((1.0, 0, 0)), c, ortho=0.045)


@view("08_tip_closeup", (1440, 1080))
def _():
    show(True, True, True); pen_pose(PEN_DISPLAY)
    t = pen_local(-150, 0, 0)
    set_cam(t + Vector((-0.06, -0.13, 0.035)), t + Vector((0.004, 0, -0.004)), lens=85)


@view("09_rear_N_frame_closeup", (1440, 1080))
def _():
    show(True, True, True); pen_pose(PEN_DISPLAY)
    t = pen_local(150, 0, 0)
    set_cam(t + Vector((-0.07, -0.14, 0.06)), t, lens=85)


@view("09b_rear_N_frame_pen_alone", (1440, 1080))
def _():
    show(True, False, False); pen_pose(NEUTRAL)
    t = neutral(150, 0, 0)
    set_cam(t + Vector((0.09, -0.12, 0.08)), t, lens=80)


@view("10_color_window_closeup", (1440, 1080))
def _():
    show(True, True, True); pen_pose(PEN_DISPLAY)
    t = pen_local(-49, -14, 0)
    set_cam(t + Vector((-0.02, -0.11, 0.03)), t, lens=90)


@view("13_front_contact", (1200, 900))
def _():
    show(True, True, True); pen_pose(PEN_DISPLAY)
    t = pen_local(-145, 0, -6)
    set_cam(t + Vector((0.0, -0.16, 0.0)), t, lens=100)


@view("14_rear_contact", (1200, 900))
def _():
    show(True, True, True); pen_pose(PEN_DISPLAY)
    t = pen_local(155, 0, 0)
    set_cam(t + Vector((0.0, -0.22, 0.0)), t, lens=90)


@view("15_display_rear_three_quarter")
def _():
    show(True, True, True); pen_pose(PEN_DISPLAY)
    set_cam((0.45, 0.50, 0.30), (0.0, 0.0, 0.06), lens=55)


@view("16_pen_hero_three_quarter", (1600, 900))
def _():
    show(True, False, False); pen_pose(NEUTRAL)
    c = neutral(0)
    set_cam(c + Vector((-0.28, -0.42, 0.20)), c, lens=55)


os.makedirs(OUT, exist_ok=True)
names = views_req or sorted(VIEWS)
for n in names:
    fn, res = VIEWS[n]
    fn()
    sc.render.resolution_x = int(res[0] * SCALE)
    sc.render.resolution_y = int(res[1] * SCALE)
    sc.render.filepath = os.path.join(OUT, n + ".png")
    bpy.ops.render.render(write_still=True)
    print("[RENDER]", n, flush=True)
