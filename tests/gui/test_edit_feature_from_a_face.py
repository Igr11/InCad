"""Edit Feature on a face picked in the view (the user: a right-click on the lid had no Edit): the dialog of the
feature that made the face opens — an earlier feature's face opens that earlier feature."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from incad.core import commands, document, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402
from incad.ui.marking_layout import LAYOUT  # noqa: E402
import headless.util as util  # noqa: E402

V = App.Vector
ST = {}


def doc():
    return App.ActiveDocument


def session():
    return shell.instance().feature_session


def test_0_two_pads():
    prefs.set_remember_new_choice(True)
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    body = document.primary_body(doc())
    base = util.add_pad(body, util.add_rect_sketch(body, 20, 10, "Base"), 10, "BasePad")
    top = util.add_rect_sketch(body, 6, 4, "Top")
    top.AttachmentOffset = App.Placement(V(0, 0, 10), App.Rotation())
    boss = util.add_pad(body, top, 5, "TopPad")
    body.Tip = boss
    doc().recompute()
    harness.pump(400)
    ST.update(base=base, boss=boss)
    assert "view.edit_feature" in LAYOUT["face"]["list"] and "view.edit_feature" in LAYOUT["edge"]["list"]


def _edit_face_at(z_top, expect):
    tip = ST["boss"]
    face = [i + 1 for i, f in enumerate(tip.Shape.Faces)
            if abs(f.normalAt(0, 0).z - 1) < 1e-9 and abs(f.CenterOfMass.z - z_top) < 1e-6][0]
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, tip.Name, "Face%d" % face)
    r = commands.REGISTRY.run("view.edit_feature")
    harness.pump(1500)
    assert r.ok, r.error
    assert session() is not None and session().feature is expect, (session() and session().feature)
    session().cancel()
    harness.pump(800)


def test_1_the_boss_top_opens_the_boss():
    _edit_face_at(15, ST["boss"])


def test_2_the_base_top_opens_the_base():
    _edit_face_at(10, ST["base"])


def test_9_cleanup():
    App.closeDocument(doc().Name)


harness.run([test_0_two_pads, test_1_the_boss_top_opens_the_boss, test_2_the_base_top_opens_the_base, test_9_cleanup])
