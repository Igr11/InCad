import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
from incad.qt import QtCore, QtWidgets  # noqa: E402
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



def on_top(widget):
    """Is the widget above every document window in the view area (children later in the list draw on top)?"""
    kids = [c for c in widget.parentWidget().children() if isinstance(c, QtWidgets.QWidget) and c.isVisible()]
    windows = [c for c in kids if isinstance(c, QtWidgets.QMdiSubWindow)]
    return widget.isVisible() and all(kids.index(widget) > kids.index(w) for w in windows)


def test_3_the_dialog_stays_on_top_when_document_tabs_switch():
    """The user's Hole dialog vanished behind the 3D view while still open (everything else refused)."""
    part = App.ActiveDocument
    other = App.newDocument("Other")
    harness.pump(500)
    App.setActiveDocument(part.Name)
    Gui.getDocument(part.Name).ActiveView  # its view
    mdi = Gui.getMainWindow().findChild(QtWidgets.QMdiArea)
    part_win = [w for w in mdi.subWindowList() if w.windowTitle().startswith(part.Label)][0]
    other_win = [w for w in mdi.subWindowList() if w.windowTitle().startswith("Other")][0]
    mdi.setActiveSubWindow(part_win)
    harness.pump(500)
    open_hole()
    mdi.setActiveSubWindow(other_win)
    harness.pump(300)
    mdi.setActiveSubWindow(part_win)
    harness.pump(500)
    assert on_top(dialog()), "the Hole dialog is buried under the 3D view"
    cancel()
    App.closeDocument(other.Name)
    harness.pump(300)



def test_4_a_refused_command_brings_the_open_dialog_to_the_front():
    from incad.core import context
    open_hole()
    dialog().lower()  # buried by whatever route
    assert not on_top(dialog())
    context.set_target(ST["sk"])
    commands.REGISTRY.run("browser.edit")  # refused: the Hole dialog is open
    harness.pump(400)
    assert on_top(dialog()), "the dialog that blocks the command must be seen"
    commands.REGISTRY.run("browser.delete")
    harness.pump(400)
    assert App.ActiveDocument.getObject(ST["sk"]) is not None and on_top(dialog())
    cancel()


harness.run([test_0_setup_block_and_point_sketch, test_1_clicking_the_sketch_point_in_3d_picks_the_sketch,
             test_2_clicking_the_sketch_in_the_model_tree_picks_it,
             test_3_the_dialog_stays_on_top_when_document_tabs_switch,
             test_4_a_refused_command_brings_the_open_dialog_to_the_front])
