"""Wireframe is readable: in the dark theme the lines were nearly black on the dark background, and in both themes
they were thin. Wireframe makes them thick (and light in the dark theme); Shaded puts them back; a file saved in
Wireframe keeps the normal lines."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from incad.core import commands, document, prefs  # noqa: E402
from incad.ui import shell, theme  # noqa: E402
import headless.util as util  # noqa: E402

ST = {}


def tip():
    return document.primary_body(App.ActiveDocument).Tip


def brightness(rgb):
    return sum(rgb[:3]) / 3.0


def test_0_a_part_in_the_dark_theme():
    prefs.set_remember_new_choice(True)
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    doc = App.ActiveDocument
    body = document.primary_body(doc)
    body.Tip = util.add_pad(body, util.add_rect_sketch(body), 10)
    doc.recompute()
    if theme.current() != "dark":
        commands.REGISTRY.run("view.theme_toggle")
        harness.pump(800)
    assert theme.current() == "dark"
    vo = tip().ViewObject
    ST["normal"] = (tuple(vo.LineColor), vo.LineWidth)


def test_1_wireframe_lines_are_light_and_thick():
    commands.REGISTRY.run("view.style_wireframe")
    harness.pump(600)
    vo = tip().ViewObject
    assert brightness(vo.LineColor) > 0.7, vo.LineColor
    assert vo.LineWidth >= 3.0, vo.LineWidth


def test_2_a_file_saved_in_wireframe_opens_with_normal_lines():
    doc = App.ActiveDocument
    path = os.path.join(os.environ["FREECAD_USER_TEMP"], "wire.FCStd")
    doc.saveAs(path)
    harness.pump(500)
    assert tip().ViewObject.LineWidth >= 3.0, "still wireframe on screen after saving"
    name = tip().Name
    App.closeDocument(doc.Name)
    harness.pump(800)
    App.openDocument(path)
    harness.pump(2500)
    vo = App.ActiveDocument.getObject(name).ViewObject
    assert (tuple(vo.LineColor), vo.LineWidth) == ST["normal"], ((tuple(vo.LineColor), vo.LineWidth), ST["normal"])
    commands.REGISTRY.run("view.style_wireframe")  # back to the state test_3 starts from
    harness.pump(600)


def test_3_shaded_puts_the_lines_back():
    commands.REGISTRY.run("view.style_shaded")
    harness.pump(600)
    vo = tip().ViewObject
    assert (tuple(vo.LineColor), vo.LineWidth) == ST["normal"], ((tuple(vo.LineColor), vo.LineWidth), ST["normal"])


def test_4_light_theme_wireframe_is_dark_and_thick():
    commands.REGISTRY.run("view.theme_toggle")
    harness.pump(800)
    commands.REGISTRY.run("view.style_wireframe")
    harness.pump(600)
    vo = tip().ViewObject
    assert brightness(vo.LineColor) < 0.3 and vo.LineWidth >= 3.0, (vo.LineColor, vo.LineWidth)
    commands.REGISTRY.run("view.style_shaded")
    harness.pump(400)


harness.run([test_0_a_part_in_the_dark_theme, test_1_wireframe_lines_are_light_and_thick,
             test_2_a_file_saved_in_wireframe_opens_with_normal_lines, test_3_shaded_puts_the_lines_back,
             test_4_light_theme_wireframe_is_dark_and_thick])
