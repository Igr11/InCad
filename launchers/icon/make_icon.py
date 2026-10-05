"""Draws the InCad icon -> icon.png (1024) and InCad.icns. Run with FreeCAD's python (has Pillow)."""
import shutil, subprocess, tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = Path(__file__).parent
S = 1024
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
m, r = 100, 185
grad = Image.new("RGBA", (S, S))
gd = ImageDraw.Draw(grad)
top, bot = (44, 62, 80), (16, 24, 36)               # dark slate, like the dark-mode shell
for y in range(S):
    t = y / S
    gd.line([(0, y), (S, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bot)) + (255,))
mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).rounded_rectangle([m, m, S - m, S - m], r, fill=255)
shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
ImageDraw.Draw(shadow).rounded_rectangle([m, m + 18, S - m, S - m + 18], r, fill=(0, 0, 0, 110))
img = Image.alpha_composite(img, shadow.filter(ImageFilter.GaussianBlur(18)))
img.paste(grad, (0, 0), mask)
d = ImageDraw.Draw(img)
# isometric block with a hole: the "part" (same style as the mockup's Extrude icon)
cx, cy, w, h = 512, 300, 250, 170
top_f = [(cx, cy - w * 0.5), (cx + w, cy), (cx, cy + w * 0.5), (cx - w, cy)]
left_f = [(cx - w, cy), (cx, cy + w * 0.5), (cx, cy + w * 0.5 + h), (cx - w, cy + h)]
right_f = [(cx, cy + w * 0.5), (cx + w, cy), (cx + w, cy + h), (cx, cy + w * 0.5 + h)]
d.polygon(top_f, fill=(170, 206, 246), outline=(255, 255, 255), width=10)
d.polygon(left_f, fill=(90, 154, 230), outline=(255, 255, 255), width=10)
d.polygon(right_f, fill=(10, 100, 214), outline=(255, 255, 255), width=10)
d.ellipse([cx - 80, cy - 40, cx + 80, cy + 40], fill=(16, 40, 72), outline=(255, 255, 255), width=8)
# orange extrude arrow (the drag handle)
d.line([(cx + 150, cy - 10), (cx + 150, cy - 110)], fill=(230, 126, 34), width=22)
d.polygon([(cx + 114, cy - 100), (cx + 150, cy - 165), (cx + 186, cy - 100)], fill=(230, 126, 34))
# "InCad" wordmark
font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 190, index=1)
tw = d.textlength("InCad", font=font)
d.text(((S - tw) / 2, 690), "InCad", font=font, fill="white")
img.save(HERE / "icon.png")
iconset = Path(tempfile.mkdtemp()) / "InCad.iconset"   # not on the exFAT volume (._ files)
iconset.mkdir()
for size in (16, 32, 128, 256, 512):
    for scale in (1, 2):
        px = size * scale
        img.resize((px, px), Image.LANCZOS).save(iconset / f"icon_{size}x{size}{'@2x' if scale == 2 else ''}.png")
subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(HERE / "InCad.icns")], check=True)
shutil.rmtree(iconset, ignore_errors=True)
print("ok")
