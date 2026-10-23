"""What's New (RU) slides, 1920 x 1080, in the presentation's style: wn/ru/*.html next to their JPGs."""
import os
import sys

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "out", "ru")
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
<p class="k" style="font-size:30px;color:#F08A24;letter-spacing:4px">Новое в этой сборке</p>
<h1 style="font-family:'Rubik';font-size:140px;font-weight:700;line-height:1;margin-top:36px">Что нового</h1>
<p style="font-size:42px;line-height:1.3;color:#C9D3DD;margin-top:36px;width:840px">Разрез и пересечения в сборке, цвет и фактуры, картинка-подложка с масштабом, 3D-линия, плоскости для лофта — и ещё много мелочей</p>
<div style="position:absolute;right:96px;top:170px;display:flex;gap:18px">
  <img src="chess_7_black.jpg" style="width:240px;height:500px;object-fit:cover;border-radius:16px">
  <img src="chess_6_wood.jpg" style="width:240px;height:500px;object-fit:cover;border-radius:16px;margin-top:70px">
  <img src="chess_8_red.jpg" style="width:240px;height:500px;object-fit:cover;border-radius:16px">
</div>
<p style="position:absolute;left:128px;bottom:64px;font-size:26px;color:#8FA0B2">InnCad Plus 0.10.0 · InnCad 0.14.0 · InCad 0.10.0 (и всё из 0.8 и 0.9) &nbsp;·&nbsp; 23 октября 2026 &nbsp;·&nbsp; FreeCAD 1.1</p>
</section>""")

# 2 — the chess demo
steps = [("chess_1_photo.jpg", "1", "Фото пешки", "Image ▸ Insert Image, затем On XZ — картинка встаёт вертикально"),
         ("chess_2_scale.jpg", "2", "Масштаб", "Две точки — низ и макушка, Real length 50 мм; лупа под курсором, прозрачность 35 %"),
         ("chess_3_sketch.jpg", "3", "Эскиз по контуру", "Половина силуэта поверх фото на плоскости XZ"),
         ("chess_4_revolve.jpg", "4", "Revolve", "Вокруг оси Z — пешка готова, ровно 50 мм"),
         ("chess_5_appearance.jpg", "5", "Appearance", "Дерево, Satin, Hide Edges — сразу видно на детали")]
cards = "".join(f"""<div style="width:322px;display:flex;flex-direction:column;gap:14px">
<img class="img" src="{img}" style="width:322px;height:470px;object-fit:cover">
<p style="font-family:'Rubik';font-size:30px;font-weight:700"><span style="color:#F08A24">{n}</span>&nbsp; {t}</p>
<p class="b" style="font-size:22px;line-height:1.35;color:#3A4654">{d}</p></div>""" for img, n, t, d in steps)
page("02_chess.html", f"""<section style="{LIGHT};padding:96px 112px;display:flex;flex-direction:column;gap:30px">
<p class="k" style="color:#2F6FA8">Демо: шахматная пешка</p>
<h2 class="t">От фотографии к детали за пять шагов</h2>
<div style="display:flex;gap:22px;margin-top:10px">{cards}</div>
</section>""")

# 3 — the three pawns
trio = [("chess_6_wood.jpg", "Wood · Satin"), ("chess_7_black.jpg", "Glossy, чёрный"), ("chess_8_red.jpg", "Metal + Brushed")]
cards = "".join(f"""<div style="display:flex;flex-direction:column;gap:16px;align-items:center">
<img src="{i}" style="width:520px;height:640px;object-fit:cover;border-radius:16px">
<p style="font-size:30px;color:#C9D3DD">{t}</p></div>""" for i, t in trio)
page("03_pawns.html", f"""<section style="{DARK};padding:96px 112px;display:flex;flex-direction:column;gap:34px">
<p class="k" style="color:#F08A24">Appearance</p>
<h2 class="t">Одна деталь — три характера</h2>
<div style="display:flex;gap:44px;justify-content:center">{cards}</div>
</section>""")

# 4 — Appearance
slide("04_appearance.html", "Tools ▸ Material ▸ Appearance", "Цвет и вид поверхности",
      '<img class="img" src="finishes.jpg" style="width:1000px;height:534px">',
      '<div style="flex:1;display:flex;flex-direction:column;gap:26px"><img class="img" src="appearance_dialog.jpg" style="width:560px;height:334px">' +
      bullets(["Любой цвет: палитра или <b>More…</b>",
               "Вид: <b>Matte, Satin, Glossy, Metal, Chrome, Glass, Rubber</b>",
               "Красит выбранные грани, Solid'ы или всю деталь; <b>Hide Edges</b> убирает линии рёбер",
               "Видно сразу, OK — один шаг Undo; цвет грани не теряется, когда её сдвигает фича"], size=25) + '</div>')

# 5 — textures
slide("05_textures.html", "Appearance ▸ Texture", "Фактуры поверх цвета",
      '<img class="img" src="textures.jpg" style="width:1040px;height:555px">',
      '<div style="flex:1">' + bullets(["<b>Brushed, Wood, Carbon, Knurl, Sand</b>",
                                        "Цвет просвечивает: красная деталь — красное дерево",
                                        "Рисунок в настоящем размере на детали любого размера",
                                        "Сохраняется в файле, видна и в сборке",
                                        "Рендер через Blender — когда-нибудь потом; пока цвет и фактуры"], "#F3F2EE") + '</div>',
      dark=True)

# 6 — Image tab
slide("06_image.html", "Вкладка Image", "Картинка-подложка в точном масштабе",
      '<div style="display:flex;flex-direction:column;gap:20px"><img class="img" src="chess_2_scale.jpg" style="width:900px;height:582px;object-fit:cover"></div>',
      '<div style="flex:1;display:flex;flex-direction:column;gap:24px"><img class="img" src="picture_scale_level.jpg" style="width:520px;height:384px">' +
      bullets(["<b>Insert Image</b>: JPG, PNG, BMP; On XY / XZ / YZ, Turn 90°, Mirror, Show / Hide",
               "<b>Scale</b>: две точки и настоящая длина — масштабируется вся картинка",
               "Line ▸ <b>Horizontal / Vertical</b> выравнивает картинку по линии",
               "Лупа под курсором, точки — маленькие крестики; ползунок прозрачности"], size=24) + '</div>')

# 7 — 3D Line
slide("07_line3d.html", "3D Model ▸ Sketch ▸ 3D Line", "Линия в пространстве по виртуальному кубу",
      '<img class="img" src="line3d_layer.jpg" style="width:960px;height:670px">',
      '<div style="flex:1;display:flex;flex-direction:column;gap:24px"><img class="img" src="line3d.jpg" style="width:540px;height:396px">' +
      bullets(["Куб точек вокруг начала координат: размер и шаг ваши, размеры — серым",
               "<b>Рабочий слой</b> XY / XZ / YZ: Tab / Shift+Tab — шаг вверх / вниз",
               "Точки тянутся мышью; Lines, Spline или Through points, гребёнка кривизны",
               "Готовая линия — путь для Sweep"], size=24) + '</div>', dark=True)

# 8 — loft planes
slide("08_planes.html", "Work Plane", "Плоскости для лофта — сразу несколько и с поворотом",
      '<img class="img" src="work_plane_series_view.jpg" style="width:900px;height:628px">',
      '<div style="flex:1;display:flex;flex-direction:column;gap:24px"><img class="img" src="work_plane_series.jpg" style="width:580px;height:357px">' +
      bullets(["Offset ▸ <b>Planes</b>: 2×, 3×… отступа за один раз",
               "<b>Turn</b>: X, Y, Z относительно предыдущей плоскости или глобально",
               "Вводом или кольцами на плоскости; следующая плоскость остаётся как была"], size=25) + '</div>')

# 9 — assembly
slide("09_assembly.html", "Сборка", "Оси, за которые удобно хвататься",
      '<img class="img" src="assembly_axes.jpg" style="width:860px;height:574px">',
      '<div style="flex:1">' + bullets(["У каждого тела вращения и отверстия — <b>ось</b> светлой осевой линией",
                                        "Mate, Flush, Insert, Cylindrical, Parallel… берут ось щелчком",
                                        "Гизмо держится ~3 секунды после перетаскивания — легко схватить снова",
                                        "Схваченная ручка <b>меняет цвет</b>; стрелки стали компактнее",
                                        "Make Assembly: детали сохраняют свои имена, сборка — <b>имя_assy</b>"], "#F3F2EE", 27) + '</div>',
      dark=True)

# 9b — assembly section and interference (the user: the Moto Engine Demo's section for the presentation)
page("09b_asm_section.html", f"""<section class="dark" style="{DARK};padding:96px 112px;display:flex;flex-direction:column;gap:28px">
<p class="k" style="color:#F08A24">Сборка · View ▸ Section</p>
<h2 class="t">Разрез всей сборки — каждая деталь в своём цвете<span class="tag">НОВОЕ В 0.9</span></h2>
<div style="display:flex;gap:40px;align-items:flex-start">
  <img class="img" src="moto_front.jpg" style="width:1040px;height:700px;object-fit:contain;background:#1b222c">
  <div style="flex:1;display:flex;flex-direction:column;gap:22px">
    <div style="display:flex;gap:18px">
      <img class="img" src="moto_iso.jpg" style="width:300px;height:220px;object-fit:cover">
      <img class="img" src="interference.jpg" style="width:300px;height:220px;object-fit:cover">
    </div>
    """ + bullets(["Плоскость режет все детали, через которые проходит, — со своей штриховкой у каждой",
                   "Любые тела: сборки InnCad и FreeCAD, STEP, файлы из других программ",
                   "<b>Interference</b>: где детали заходят друг в друга — ярко-красным, с объёмом",
                   "Hide / Show для осей, эскизов, начала координат; <b>Open</b> детали в своём окне"], "#F3F2EE", 24) + """
  </div>
</div>
<p style="position:absolute;left:112px;bottom:40px;font-size:20px;color:#8FA0B2">Moto Engine Demo — сборка из 20 деталей, сделанная в FreeCAD</p>
</section>""")

# 9c — 0.10
page("09c_v010.html", f"""<section class="dark" style="{DARK};padding:96px 112px;display:flex;flex-direction:column;gap:30px">
<p class="k" style="color:#F08A24">Новое в 0.10</p>
<h2 class="t">Порядок в сборке</h2>
<div style="display:flex;gap:56px;align-items:flex-start">
  <img class="img" src="moto_iso.jpg" style="width:820px;height:600px;object-fit:cover">
  <div style="flex:1">""" + bullets(["Явные <b>Hide</b>, <b>Show</b> и <b>Show All</b> — на ленте и в каждом меню правой кнопки",
                                     "В сборке деталь прячется и показывается <b>в дереве сборки</b>: её строка остаётся, Show возвращает",
                                     "Файлы не из InnCad — из скрипта, FreeCAD, STEP — открываются <b>со всеми инструментами</b>",
                                     "<b>Save</b> сборки: папка с её именем, в ней сборка и все детали",
                                     "Гизмо меньше и появляется по щелчку на пару секунд; стрелки прокрутки у вкладок"], "#F3F2EE", 27) + """</div>
</div>
</section>""")

# 10 — goodies
slide("10_goodies.html", "И ещё", "Мелочи, которые экономят время",
      '<img class="img" src="open_preview.jpg" style="width:900px;height:490px">',
      '<div style="flex:1">' + bullets(["<b>Open</b> с превью: FCStd, STEP, STL — картинка, дата, размер; в списке только то, что открывается",
                                        "Import: <b>IGES</b>, <b>OBJ</b> (Plus), JPG / PNG как подложка",
                                        "<b>Screenshot</b>: 3D-вид или всё окно, PNG (можно с прозрачным фоном), JPEG, BMP",
                                        "Extrude ⇄ 2: у второй стороны свои Distance / To Next / Through All / To",
                                        "Extrude ▸ To: до грани, ребра, точки, оси",
                                        "Fillet ▸ <b>Full</b>: полный радиус между двумя рёбрами",
                                        "Подсказки синие, ошибки красные"], size=25) + '</div>')

# 11 — Plus: Connect AI
slide("11_ai.html", "Tools ▸ AI ▸ Connect AI", "Одна кнопка — и ваш ИИ уже в InnCad",
      '<img class="img" src="ai_help_light.jpg" style="width:1000px;height:657px">',
      '<div style="flex:1">' + bullets(["Стоит Claude Code — <b>Connect AI</b> сразу открывает Терминал с ним в папке детали, без вопросов",
                                        "MCP-сервер встроен в InnCad Plus — скачивать ничего не нужно",
                                        "Ничего не установлено — окно слева: где взять Claude Code, Codex или Gemini CLI и команда установки",
                                        "Claude Desktop, Cursor, VS Code, Windsurf, LM Studio: готовые пути и JSON с Copy"], "#F3F2EE", 26) + '</div>',
      dark=True, tag="ТОЛЬКО PLUS")

# 12 — end
page("12_end.html", f"""<section style="{LIGHT};padding:120px 128px;display:flex;flex-direction:column;justify-content:center;gap:36px">
<div style="position:absolute;left:0;top:0;width:24px;height:1080px;background:#2F6FA8"></div>
<h2 style="font-family:'Rubik';font-size:120px;font-weight:700">Пробуйте!</h2>
<p style="font-size:38px;line-height:1.4;width:1000px;color:#3A4654">Начните с пешки: фото → Scale → эскиз → Revolve → Appearance. Если что-то пошло не так — пришлите журнал (глава 11 руководства).</p>
<img src="pawn_photo.jpg" style="position:absolute;right:150px;top:150px;width:470px;height:627px;object-fit:cover;border-radius:16px;box-shadow:0 20px 60px rgba(0,0,0,0.18)">
</section>""")
print("ok", len([f for f in os.listdir(OUT) if f.endswith(".html")]))
