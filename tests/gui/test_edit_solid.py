"""Edit on a Solid (the user: the jar's lid in the same part): the other Solids turn see-through (an override, nothing
saved), Esc or Edit again ends it; the Solid's own feature can be edited meanwhile."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
from incad.core import commands, context, document, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402
from incad.ui.marking_layout import LAYOUT  # noqa: E402
import headless.util as util  # noqa: E402

ST = {}


def doc():
    return App.ActiveDocument


def see_through(body):
    root = body.Tip.ViewObject.RootNode
    return any(m.transparency[0] > 0.5 for r, m in shell.instance()._solid_see if r == root)


def test_0_jar_and_lid():
    prefs.set_remember_new_choice(True)
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    jar = document.primary_body(doc())
    jar.Tip = util.add_pad(jar, util.add_rect_sketch(jar, 20, 10, "JarSk"), 10, "Jar")
    lid = doc().addObject("PartDesign::Body", "Lid")
    sk = lid.newObject("Sketcher::SketchObject", "LidSk")
    sk.AttachmentSupport = [(util.xy_plane(lid), "")]
    sk.MapMode = "FlatFace"
    sk.addGeometry(Part.Circle(App.Vector(40, 5, 0), App.Vector(0, 0, 1), 5))
    lid.Tip = util.add_pad(lid, sk, 4, "LidPad")
    doc().recompute()
    shell.instance().schedule_refresh()
    harness.pump(600)
    ST.update(jar=jar, lid=lid)
    assert "browser.edit_solid" in LAYOUT["solid"]["list"]


def test_1_edit_the_lid_the_jar_goes_see_through():
    context.set_target(ST["lid"].Name)
    r = commands.REGISTRY.run("browser.edit_solid")
    harness.pump(500)
    assert r.ok, r.error
    assert see_through(ST["jar"]) and not see_through(ST["lid"])
    assert ST["jar"].Tip.Visibility


def test_2_esc_ends_it():
    shell.instance()._on_escape()
    harness.pump(300)
    assert shell.instance()._solid_edit is None and not shell.instance()._solid_see


def test_3_edit_again_toggles():
    context.set_target(ST["lid"].Name)
    commands.REGISTRY.run("browser.edit_solid")
    harness.pump(300)
    assert see_through(ST["jar"])
    context.set_target(ST["lid"].Name)
    commands.REGISTRY.run("browser.edit_solid")
    harness.pump(300)
    assert shell.instance()._solid_edit is None


def test_9_cleanup():
    App.closeDocument(doc().Name)


harness.run([test_0_jar_and_lid, test_1_edit_the_lid_the_jar_goes_see_through, test_2_esc_ends_it,
             test_3_edit_again_toggles, test_9_cleanup])
