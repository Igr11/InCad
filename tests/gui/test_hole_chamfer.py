"""Hole ▸ Chamfer in a real window: the option is there for every hole, OK makes one undo step with the chamfer
under the Hole in the tree, and Start is unavailable while the hole has a seat."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from incad.qt import QtCore  # noqa: E402
from incad.core import commands, document, prefs, tree  # noqa: E402
from incad.ui import shell  # noqa: E402
import headless.util as util  # noqa: E402


def dialog():
    fs = shell.instance().feature_session
    return fs.dialog if fs is not None else None


def test_0_chamfered_hole_from_the_dialog():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    doc = App.ActiveDocument
    body = document.primary_body(doc)
    plate = util.add_pad(body, util.add_rect_sketch(body, w=30, h=20, name="Plate"), 6, name="Plate")
    body.Tip = plate
    doc.recompute()
    top = [i + 1 for i, f in enumerate(plate.Shape.Faces) if abs(f.CenterOfMass.z - 6) < 1e-6 and f.Area > 400][0]
    hs = body.newObject("Sketcher::SketchObject", "HoleAt")
    hs.AttachmentSupport = [(plate, "Face%d" % top)]
    hs.MapMode = "FlatFace"
    hs.addGeometry(Part.Circle(App.Vector(20, 10, 0), App.Vector(0, 0, 1), 1))
    doc.recompute()
    Gui.Selection.clearSelection()
    n = len(doc.UndoNames)
    commands.REGISTRY.run("feature.hole")
    harness.pump(800)
    Gui.Selection.addSelection(doc.Name, hs.Name)
    harness.pump(800)
    dialog().field("chamfer").button("both").click()
    harness.pump(1500)
    assert not dialog().error_text(), dialog().error_text()
    QTest.mouseClick(dialog().ok_button, QtCore.Qt.LeftButton)
    harness.pump(1500)
    h = [o for o in body.Group if o.TypeId == "PartDesign::Hole"][-1]
    helper = [o for o in body.Group if getattr(o, "InCadHelperOf", None) == h.Name]
    assert len(helper) == 1 and body.Tip is helper[0], (helper, body.Tip.Name)
    assert len(doc.UndoNames) == n + 1, (doc.UndoNames, n)
    row = next(r for r in tree.build(doc)[0].children if r.name == h.Name)
    assert helper[0].Name in [c.name for c in row.children], [c.name for c in row.children]


def test_1_start_is_unavailable_with_a_seat():
    doc = App.ActiveDocument
    h = [o for o in document.primary_body(doc).Group if o.TypeId == "PartDesign::Hole"][-1]
    shell.edit_feature(h)
    harness.pump(900)
    assert dialog().field("chamfer").button("start").isEnabled()
    dialog().field("seat").setCurrentIndex(dialog().field("seat").findData("counterbore"))
    harness.pump(1500)
    assert not dialog().field("chamfer").button("start").isEnabled(), "a seat is the start"
    assert dialog().field("chamfer").button("both").isEnabled()
    shell.instance().feature_session.cancel()
    harness.pump(600)


harness.run([test_0_chamfered_hole_from_the_dialog, test_1_start_is_unavailable_with_a_seat])
