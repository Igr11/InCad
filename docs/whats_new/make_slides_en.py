"""What's New (EN) slides, 1920 x 1080, in the presentation's style: wn/ru/*.html next to their JPGs."""
import os
import sys

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "en")
os.makedirs(OUT, exist_ok=True)
HEAD = """<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Rubik:wght@500;700&family=IBM+Plex+Sans:wght@400;600&display=swap"><style>
html,body{margin:0;padding:0;width:1920px;height:1080px;overflow:hidden}
*{box-sizing:border-box}
h1,h2,h3,p{margin:0}
section{position:relative;width:1920px;height:1080px;overflow:hidden;font-family:'IBM Plex Sans', Arial, sans-serif}
.k{font-size:24px;font-weight:600;letter-spacing:3px;text-transform:uppercase}
.t{font-family:'Rubik', Arial, sans-serif;font-size:60px;font-weight:700;line-height:1.08}
.b{font-size:27px;line-height:1.42}
.b b{font-weight:600}
.img{border-radius:12px;border:1px solid #DEDBD3;background:#1c212a;object-fit:contain;display:block}
.dark .img{border-color:#2A3746}
.tag{display:inline-block;font-size:18px;font-weight:600;letter-spacing:2px;padding:4px 12px;border-radius:6px;background:#F08A24;color:#16202C;vertical-align:middle;margin-left:14px}
ul{margin:0;padding-left:1.1em} li{margin:0 0 14px 0}
</style></head><body>"""
FOOT = "</body></html>"
LIGHT = "background:#F3F2EE;color:#16202C"
DARK = "background:#16202C;color:#F3F2EE"


def page(name, body):
    with open(os.path.join(OUT, name), "w") as f:
        f.write(HEAD + body + FOOT)


def bullets(items, color="#16202C", size=27):
    return '<ul class="b" style="color:%s;font-size:%dpx">%s</ul>' % (color, size, "".join("<li>%s</li>" % i for i in items))


def slide(name, kicker, title, left, right, dark=False, tag=""):
    style = DARK if dark else LIGHT
    kc = "#F08A24" if dark else "#2F6FA8"
    page(name, f"""<section class="{'dark' if dark else ''}" style="{style};padding:96px 112px;display:flex;flex-direction:column;gap:30px">
<p class="k" style="color:{kc}">{kicker}</p>
<h2 class="t">{title}{('<span class="tag">' + tag + '</span>') if tag else ''}</h2>
<div style="display:flex;gap:56px;align-items:flex-start;flex:1;min-height:0">{left}{right}</div>
</section>""")


# 1 — cover
page("01_cover.html", f"""<section style="{DARK};padding:120px 128px">
<div style="position:absolute;left:0;top:0;width:24px;height:1080px;background:#F08A24"></div>
<p class="k" style="font-size:30px;color:#F08A24;letter-spacing:4px">New in this build</p>
<h1 style="font-family:'Rubik';font-size:140px;font-weight:700;line-height:1;margin-top:36px">What's new</h1>
<p style="font-size:42px;line-height:1.3;color:#C9D3DD;margin-top:36px;width:840px">Assembly section and interference, colour and textures, a scaled photo to sketch over, a 3D line, loft planes — and many small things</p>
<div style="position:absolute;right:96px;top:170px;display:flex;gap:18px">
  <img src="chess_7_black.jpg" style="width:240px;height:500px;object-fit:cover;border-radius:16px">
  <img src="chess_6_wood.jpg" style="width:240px;height:500px;object-fit:cover;border-radius:16px;margin-top:70px">
  <img src="chess_8_red.jpg" style="width:240px;height:500px;object-fit:cover;border-radius:16px">
</div>
<p style="position:absolute;left:128px;bottom:64px;font-size:26px;color:#8FA0B2">InnCad Plus 0.10.0 · InnCad 0.14.0 · InCad 0.10.0 (with all of 0.8 and 0.9) &nbsp;·&nbsp; 23 October 2026 &nbsp;·&nbsp; FreeCAD 1.1</p>
</section>""")

# 2 — the chess demo
steps = [("chess_1_photo.jpg", "1", "A photo of a pawn", "Image ▸ Insert Image, then On XZ — the picture stands upright"),
         ("chess_2_scale.jpg", "2", "Scale", "Two points — foot and top, Real length 50 mm; a magnifier under the pointer, 35 % transparency"),
         ("chess_3_sketch.jpg", "3", "Sketch the outline", "Half the silhouette over the photo on the XZ plane"),
         ("chess_4_revolve.jpg", "4", "Revolve", "About the Z axis — the pawn is done, exactly 50 mm"),
         ("chess_5_appearance.jpg", "5", "Appearance", "Wood, Satin, Hide Edges — shown on the part at once")]
cards = "".join(f"""<div style="width:322px;display:flex;flex-direction:column;gap:14px">
<img class="img" src="{img}" style="width:322px;height:470px;object-fit:cover">
<p style="font-family:'Rubik';font-size:30px;font-weight:700"><span style="color:#F08A24">{n}</span>&nbsp; {t}</p>
<p class="b" style="font-size:22px;line-height:1.35;color:#3A4654">{d}</p></div>""" for img, n, t, d in steps)
page("02_chess.html", f"""<section style="{LIGHT};padding:96px 112px;display:flex;flex-direction:column;gap:30px">
<p class="k" style="color:#2F6FA8">Demo: a chess pawn</p>
<h2 class="t">From a photo to a part in five steps</h2>
<div style="display:flex;gap:22px;margin-top:10px">{cards}</div>
</section>""")

# 3 — the three pawns
trio = [("chess_6_wood.jpg", "Wood · Satin"), ("chess_7_black.jpg", "Glossy, black"), ("chess_8_red.jpg", "Metal + Brushed")]
cards = "".join(f"""<div style="display:flex;flex-direction:column;gap:16px;align-items:center">
<img src="{i}" style="width:520px;height:640px;object-fit:cover;border-radius:16px">
<p style="font-size:30px;color:#C9D3DD">{t}</p></div>""" for i, t in trio)
page("03_pawns.html", f"""<section style="{DARK};padding:96px 112px;display:flex;flex-direction:column;gap:34px">
<p class="k" style="color:#F08A24">Appearance</p>
<h2 class="t">One part, three characters</h2>
<div style="display:flex;gap:44px;justify-content:center">{cards}</div>
</section>""")

# 4 — Appearance
slide("04_appearance.html", "Tools ▸ Material ▸ Appearance", "Colour and finish",
      '<img class="img" src="finishes.jpg" style="width:1000px;height:534px">',
      '<div style="flex:1;display:flex;flex-direction:column;gap:26px"><img class="img" src="appearance_dialog.jpg" style="width:560px;height:334px">' +
      bullets(["Any colour: the palette or <b>More…</b>",
               "Finish: <b>Matte, Satin, Glossy, Metal, Chrome, Glass, Rubber</b>",
               "Colours the picked faces, Solids or the whole part; <b>Hide Edges</b> takes the edge lines off",
               "Shown at once, OK is one Undo step; a face keeps its colour when a feature moves it"], size=25) + '</div>')

# 5 — textures
slide("05_textures.html", "Appearance ▸ Texture", "Textures over the colour",
      '<img class="img" src="textures.jpg" style="width:1040px;height:555px">',
      '<div style="flex:1">' + bullets(["<b>Brushed, Wood, Carbon, Knurl, Sand</b>",
                                        "The colour shows through: a red part gets red wood",
                                        "The pattern keeps its real size on any part",
                                        "Saved in the file, shown in assemblies too",
                                        "Photo rendering through Blender — some day; colour and textures for now"], "#F3F2EE") + '</div>',
      dark=True)

# 6 — Image tab
slide("06_image.html", "Image tab", "A photo to sketch over, at its true scale",
      '<div style="display:flex;flex-direction:column;gap:20px"><img class="img" src="chess_2_scale.jpg" style="width:900px;height:582px;object-fit:cover"></div>',
      '<div style="flex:1;display:flex;flex-direction:column;gap:24px"><img class="img" src="picture_scale_level.jpg" style="width:520px;height:384px">' +
      bullets(["<b>Insert Image</b>: JPG, PNG, BMP; On XY / XZ / YZ, Turn 90°, Mirror, Show / Hide",
               "<b>Scale</b>: two points and the real length — the whole picture scales",
               "Line ▸ <b>Horizontal / Vertical</b> turns the picture to level that line",
               "A magnifier under the pointer, small cross points; a transparency slider"], size=24) + '</div>')

# 7 — 3D Line
slide("07_line3d.html", "3D Model ▸ Sketch ▸ 3D Line", "A line in space on a virtual cube",
      '<img class="img" src="line3d_layer.jpg" style="width:960px;height:670px">',
      '<div style="flex:1;display:flex;flex-direction:column;gap:24px"><img class="img" src="line3d.jpg" style="width:540px;height:396px">' +
      bullets(["A cube of points round the origin: its size and step are yours, sizes in grey",
               "A <b>working layer</b> XY / XZ / YZ: Tab / Shift+Tab steps it up / down",
               "Drag the points; Lines, Spline or Through points, a curvature comb",
               "The line is a path for Sweep"], size=24) + '</div>', dark=True)

# 8 — loft planes
slide("08_planes.html", "Work Plane", "Loft planes — several at once, and turned",
      '<img class="img" src="work_plane_series_view.jpg" style="width:900px;height:628px">',
      '<div style="flex:1;display:flex;flex-direction:column;gap:24px"><img class="img" src="work_plane_series.jpg" style="width:580px;height:357px">' +
      bullets(["Offset ▸ <b>Planes</b>: 2×, 3×… the offset in one go",
               "<b>Turn</b>: X, Y, Z about the previous plane or the global axes",
               "Typed or dragged on rings; the next plane stays as it was"], size=25) + '</div>')

# 9 — assembly
slide("09_assembly.html", "Assembly", "Axes to constrain to",
      '<img class="img" src="assembly_axes.jpg" style="width:860px;height:574px">',
      '<div style="flex:1">' + bullets(["Every turned body and hole shows its <b>axis</b> as a light centre line",
                                        "Mate, Flush, Insert, Cylindrical, Parallel… take an axis with a click",
                                        "The gizmo stays about 3 s after a drag — easy to grab again",
                                        "The grabbed handle <b>changes colour</b>; smaller arrows",
                                        "Make Assembly keeps the parts' names; the assembly is <b>name_assy</b>"], "#F3F2EE", 27) + '</div>',
      dark=True)

# 9b — assembly section and interference (the user: the Moto Engine Demo's section for the presentation)
page("09b_asm_section.html", f"""<section class="dark" style="{DARK};padding:96px 112px;display:flex;flex-direction:column;gap:28px">
<p class="k" style="color:#F08A24">Assembly · View ▸ Section</p>
<h2 class="t">The whole assembly cut — every part in its colour<span class="tag">NEW IN 0.9</span></h2>
<div style="display:flex;gap:40px;align-items:flex-start">
  <img class="img" src="moto_front.jpg" style="width:1040px;height:700px;object-fit:contain;background:#1b222c">
  <div style="flex:1;display:flex;flex-direction:column;gap:22px">
    <div style="display:flex;gap:18px">
      <img class="img" src="moto_iso.jpg" style="width:300px;height:220px;object-fit:cover">
      <img class="img" src="interference.jpg" style="width:300px;height:220px;object-fit:cover">
    </div>
    """ + bullets(["The plane cuts every part it meets, each with its own hatching",
                   "Any shape: InnCad and FreeCAD assemblies, STEP, other programs' files",
                   "<b>Interference</b>: where parts go into each other, in bright red, with the volume",
                   "Hide / Show for axes, sketches, origin; <b>Open</b> a part in its own window"], "#F3F2EE", 24) + """
  </div>
</div>
<p style="position:absolute;left:112px;bottom:40px;font-size:20px;color:#8FA0B2">Moto Engine Demo — a 20-part assembly made in FreeCAD</p>
</section>""")

# 9c — 0.10
page("09c_v010.html", f"""<section class="dark" style="{DARK};padding:96px 112px;display:flex;flex-direction:column;gap:30px">
<p class="k" style="color:#F08A24">New in 0.10</p>
<h2 class="t">Order in the assembly</h2>
<div style="display:flex;gap:56px;align-items:flex-start">
  <img class="img" src="moto_iso.jpg" style="width:820px;height:600px;object-fit:cover">
  <div style="flex:1">""" + bullets(["<b>Hide</b>, <b>Show</b> and <b>Show All</b> said outright — in the ribbon and every right-click menu",
                                     "In an assembly a part hides and shows <b>in the assembly's tree</b>: its row stays, Show brings it back",
                                     "Files not made in InnCad — a script's, FreeCAD's, a STEP — open <b>with every tool</b>",
                                     "<b>Save</b> of an assembly: a folder of its name holding it and all its parts",
                                     "A smaller gizmo, shown on a click for a couple of seconds; scroll arrows on the file tabs"], "#F3F2EE", 27) + """</div>
</div>
</section>""")

# 10 — goodies
slide("10_goodies.html", "And more", "Small things that save time",
      '<img class="img" src="open_preview.jpg" style="width:900px;height:490px">',
      '<div style="flex:1">' + bullets(["<b>Open</b> with previews: FCStd, STEP, STL — picture, date, size; only what opens is listed",
                                        "Import: <b>IGES</b>, <b>OBJ</b> (Plus), JPG / PNG to sketch over",
                                        "<b>Screenshot</b>: the 3D view or the whole window, PNG (transparent too), JPEG, BMP",
                                        "Extrude ⇄ 2: the second side has its own Distance / To Next / Through All / To",
                                        "Extrude ▸ To: a face, an edge, a point, an axis",
                                        "Fillet ▸ <b>Full</b>: a full round between two edges",
                                        "Tips in blue, errors in red"], size=25) + '</div>')

# 11 — Plus: Connect AI
slide("11_ai.html", "Tools ▸ AI ▸ Connect AI", "One button, and your AI is in InnCad",
      '<img class="img" src="ai_help_light.jpg" style="width:1000px;height:657px">',
      '<div style="flex:1">' + bullets(["Claude Code installed? <b>Connect AI</b> opens a Terminal with it in the part's folder, no questions",
                                        "The MCP server is built into InnCad Plus — nothing to download",
                                        "Nothing installed? The window on the left: where to get Claude Code, Codex or Gemini CLI, and the install command",
                                        "Claude Desktop, Cursor, VS Code, Windsurf, LM Studio: ready paths and JSON with Copy"], "#F3F2EE", 26) + '</div>',
      dark=True, tag="PLUS ONLY")

# 12 — end
page("12_end.html", f"""<section style="{LIGHT};padding:120px 128px;display:flex;flex-direction:column;justify-content:center;gap:36px">
<div style="position:absolute;left:0;top:0;width:24px;height:1080px;background:#2F6FA8"></div>
<h2 style="font-family:'Rubik';font-size:120px;font-weight:700">Try it!</h2>
<p style="font-size:38px;line-height:1.4;width:1000px;color:#3A4654">Start with the pawn: photo → Scale → sketch → Revolve → Appearance. If something goes wrong, send the log (chapter 11 of the manual).</p>
<img src="pawn_photo.jpg" style="position:absolute;right:150px;top:150px;width:470px;height:627px;object-fit:cover;border-radius:16px;box-shadow:0 20px 60px rgba(0,0,0,0.18)">
</section>""")
print("ok", len([f for f in os.listdir(OUT) if f.endswith(".html")]))
