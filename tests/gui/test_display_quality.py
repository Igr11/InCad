"""⚙ ▸ Display Quality (user request): Fine draws curved faces with finer triangles (a ball's highlight showed its
facets); new shapes take it, an opened file is drawn at it without being marked changed, the menu switches it."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from incad.core import document, prefs, quality  # noqa: E402
from incad.ui import shell  # noqa: E402

ST = {}


def drawn(o):
    return round(o.ViewObject.Deviation, 3), round(float(o.ViewObject.AngularDeflection), 2)


def test_0_a_saved_ball():
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    shell.instance().set_display_quality("normal")
    d = App.newDocument("QualityBall")
    body = document.make_part(d)
    ball = body.newObject("PartDesign::AdditiveSphere", "Ball")
    body.Tip = ball
    d.recompute()
    harness.pump(500)
    assert drawn(ball) == quality.VALUES["normal"], drawn(ball)
    ST["path"] = os.path.join(tempfile.mkdtemp(), "ball.FCStd")
    d.saveAs(ST["path"])
    App.closeDocument(d.Name)
    harness.pump(300)


def test_1_an_opened_file_is_drawn_fine_and_stays_unchanged():
    prefs.set_display_quality("fine")
    quality.set_defaults()
    d = App.openDocument(ST["path"])
    harness.pump(2000)
    assert drawn(d.getObject("Ball")) == quality.VALUES["fine"], drawn(d.getObject("Ball"))
    assert not Gui.getDocument(d.Name).Modified, "only the drawing changed: nothing to save"
    ST["doc"] = d.Name


def test_2_the_menu_switches_open_files_and_new_shapes():
    d = App.getDocument(ST["doc"])
    shell.instance().set_display_quality("normal")
    harness.pump(500)
    assert prefs.display_quality() == "normal"
    assert drawn(d.getObject("Ball")) == quality.VALUES["normal"], drawn(d.getObject("Ball"))
    shell.instance().set_display_quality("fine")
    body = document.primary_body(d)
    box = body.newObject("PartDesign::AdditiveBox", "Box")
    d.recompute()
    assert drawn(box) == quality.VALUES["fine"] == drawn(d.getObject("Ball")), (drawn(box), drawn(d.getObject("Ball")))
    App.closeDocument(d.Name)
    harness.pump(300)


harness.run([test_0_a_saved_ball, test_1_an_opened_file_is_drawn_fine_and_stays_unchanged,
             test_2_the_menu_switches_open_files_and_new_shapes])
