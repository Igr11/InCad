import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
from incad.qt import QtCore  # noqa: E402
from incad.core import commands, document, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402
import headless.util as util  # noqa: E402

ST = {}


def s():
    return shell.instance()


def dialog():
    fs = s().feature_session
    return fs.dialog if fs is not None else None


def test_0_setup_block_and_point_sketch():
    prefs.set_remember_new_choice(True)
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    doc = App.ActiveDocument
    body = document.primary_body(doc)
    pad = util.add_pad(body, util.add_rect_sketch(body), 10)
    body.Tip = pad
    doc.recompute()
    top = [i + 1 for i, fc in enumerate(pad.Shape.Faces) if abs(fc.CenterOfMass.z - 10) < 1e-6][0]
    sk = body.newObject("Sketcher::SketchObject", "Points")
    sk.AttachmentSupport = [(pad, "Face%d" % top)]
    sk.MapMode = "FlatFace"
    sk.addGeometry(Part.Point(App.Vector(5, 5, 0)))
    doc.recompute()
    harness.pump(300)
    ST["sk"] = sk.Name


def open_hole():
    Gui.Selection.clearSelection()
    commands.REGISTRY.run("feature.hole")
    harness.pump(800)
    assert dialog() is not None, open(os.environ["INCAD_LOG"]).read()[-500:]
    assert dialog().active_pick() == "sketch", (dialog().active_pick(), dialog().values())


def cancel():
    from PySide6.QtTest import QTest
    QTest.mouseClick(dialog().cancel_button, QtCore.Qt.LeftButton)
    harness.pump(600)


def test_1_clicking_the_sketch_point_in_3d_picks_the_sketch():
    open_hole()
    Gui.Selection.addSelection(App.ActiveDocument.Name, ST["sk"], "Vertex1")
    harness.pump(600)
    assert dialog().values().get("sketch") == ST["sk"], dialog().values().get("sketch")
    cancel()


def test_2_clicking_the_sketch_in_the_model_tree_picks_it():
    open_hole()
    s().browser.select_row(ST["sk"])  # a user's single click on the row
    harness.pump(600)
    assert dialog().values().get("sketch") == ST["sk"], dialog().values().get("sketch")
    cancel()


harness.run([test_0_setup_block_and_point_sketch, test_1_clicking_the_sketch_point_in_3d_picks_the_sketch,
             test_2_clicking_the_sketch_in_the_model_tree_picks_it])
