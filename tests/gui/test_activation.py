import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
from PySide6 import QtWidgets  # noqa: E402
from incad.ui import shell  # noqa: E402


def pd_sketch():
    Gui.activateWorkbench("PartDesignWorkbench")
    harness.pump(800)
    doc = App.newDocument("PD")
    body = doc.addObject("PartDesign::Body", "Body")
    sk = body.newObject("Sketcher::SketchObject", "Sketch")
    sk.AttachmentSupport = [([o for o in body.Origin.OriginFeatures if o.Role == "XY_Plane"][0], "")]
    sk.MapMode = "FlatFace"
    doc.recompute()
    harness.pump(300)
    return doc, body, sk


def test_1_switching_to_incad_while_editing_a_freecad_sketch_takes_over():
    doc, body, sk = pd_sketch()
    Gui.ActiveDocument.setEdit(sk.Name)
    harness.pump(1000)
    sk.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(10, 0, 0)))
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1500)
    assert shell.instance() is not None and shell.instance().active, "InCad's interface must open"
    assert Gui.ActiveDocument.getInEdit() is None, "the sketch edit was finished"
    assert sk.GeometryCount == 1, "the sketch keeps what was drawn"
    Gui.activateWorkbench("PartDesignWorkbench")
    harness.pump(800)
    App.closeDocument(doc.Name)


def test_2_another_freecad_task_says_why_incad_waits():
    doc, body, sk = pd_sketch()
    sk.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 5))
    doc.recompute()
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc.Name, sk.Name)
    Gui.runCommand("PartDesign_Pad")
    harness.pump(1200)
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    assert not shell.instance().active
    notes = [w for w in QtWidgets.QApplication.topLevelWidgets()
             if w.objectName() == "InCadWaitNotice" and w.isVisible()]
    assert notes, "a visible notice tells the user to finish the FreeCAD task"
    Gui.Control.closeDialog()  # as Cancel in the Pad panel does
    Gui.ActiveDocument.resetEdit()
    harness.pump(1500)
    from incad.core import safe
    assert shell.instance().active, ("InCad opens once the task is closed", Gui.ActiveDocument.getInEdit(),
                                     safe.edit_open(), shell.instance()._pending, Gui.activeWorkbench().name(),
                                     Gui.Control.activeDialog())
    assert not [w for w in QtWidgets.QApplication.topLevelWidgets()
                if w.objectName() == "InCadWaitNotice" and w.isVisible()], "the notice goes away"


harness.run([test_1_switching_to_incad_while_editing_a_freecad_sketch_takes_over,
             test_2_another_freecad_task_says_why_incad_waits])
