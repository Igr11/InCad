"""Interference between the Solids of one part (the user: a jar and its lid in one part — the button was only in
assemblies): on, the overlap is drawn and listed; off, it goes; the button is on the part's Inspect tab."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
from incad.core import commands, document, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402
from incad.ui.ribbon_layout import LAYOUT  # noqa: E402
import headless.util as util  # noqa: E402


def doc():
    return App.ActiveDocument


def test_0_two_solids_going_into_each_other():
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
    sk.addGeometry(Part.Circle(App.Vector(20, 5, 0), App.Vector(0, 0, 1), 4))
    lid.Tip = util.add_pad(lid, sk, 15, "LidPad")
    doc().recompute()
    shell.instance().schedule_refresh()
    harness.pump(600)
    tabs = [t for t in LAYOUT["part"] if t[0] == "Inspect"][0]
    assert any("assembly.interference" in g[1] for g in tabs[1])


def test_1_on_shows_the_overlap():
    r = commands.REGISTRY.run("assembly.interference")
    harness.pump(1500)
    assert r.ok, r.error
    sh = shell.instance()
    assert sh.interference_shown()
    panel = sh.info_panel
    assert panel is not None and getattr(panel, "_incad_interference", False)
    assert sh._interference is not None


def test_2_off_clears_it():
    commands.REGISTRY.run("assembly.interference")
    harness.pump(800)
    sh = shell.instance()
    assert not sh.interference_shown() and sh._interference is None


def test_9_cleanup():
    App.closeDocument(doc().Name)


harness.run([test_0_two_solids_going_into_each_other, test_1_on_shows_the_overlap, test_2_off_clears_it, test_9_cleanup])
