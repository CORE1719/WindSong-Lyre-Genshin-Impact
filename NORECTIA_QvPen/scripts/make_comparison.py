"""Side-by-side / overlay comparison of the reference image and a render."""
import os, sys
from PIL import Image, ImageDraw, ImageChops

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ref = Image.open(os.path.join(ROOT, "reference", "reference_design.webp")).convert("RGB")
ren = Image.open(os.path.join(ROOT, "renders", sys.argv[1] if len(sys.argv) > 1 else "01_reference_angle.png")).convert("RGB")
h = 720
ref = ref.resize((round(ref.width * h / ref.height), h))
ren = ren.resize((round(ren.width * h / ren.height), h))
out = Image.new("RGB", (ref.width + ren.width + 20, h + 40), (30, 30, 30))
out.paste(ref, (0, 40)); out.paste(ren, (ref.width + 20, 40))
d = ImageDraw.Draw(out)
d.text((10, 12), "REFERENCE", fill=(230, 230, 230)); d.text((ref.width + 30, 12), "BLENDER (Cycles)", fill=(230, 230, 230))
out.save(os.path.join(ROOT, "renders", "00_comparison_reference_vs_blender.png"))
# 50% overlay (same framing) to check silhouette alignment
ren2 = ren.resize(ref.size)
Image.blend(ref, ren2, 0.5).save(os.path.join(ROOT, "renders", "00_overlay_reference_blender.png"))
