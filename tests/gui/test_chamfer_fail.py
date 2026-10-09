import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
from pivy import coin  # noqa: E402,F401
from PySide6.QtTest import QTest  # noqa: E402
from incad.qt import QtCore, QtWidgets  # noqa: E402
from incad.core import commands, document, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402
import headless.util as util  # noqa: E402

ST = {}


def s():
    return shell.instance()


def doc():
    return App.ActiveDocument


def body():
    return document.primary_body(doc())


def dialog():
    fs = s().feature_session
    return fs.dialog if fs is not None else None


def ok():
    QTest.mouseClick(dialog().ok_button, QtCore.Qt.LeftButton)
    harness.pump(700)


def top_edges(f, z):
    return ["Edge%d" % (i + 1) for i, e in enumerate(f.Shape.Edges)
            if abs(e.BoundBox.ZMin - z) < 1e-6 and abs(e.BoundBox.ZMax - z) < 1e-6]


def top_line_edges(f):
    return ["Edge%d" % (i + 1) for i, e in enumerate(f.Shape.Edges)
            if abs(e.BoundBox.ZMin - 10) < 1e-6 and abs(e.BoundBox.ZMax - 10) < 1e-6][:2]


def test_0_setup():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    pad = util.add_pad(body(), util.add_rect_sketch(body(), w=40, h=20), 10)
    body().Tip = pad
    doc().recompute()
    ST["pad"] = pad.Name
    harness.pump(300)


def test_1_a_failing_chamfer_explains_itself_and_keeps_the_part_on_screen():
    """A distance too big for the edges fails the chamfer: the dialog says it is the chamfer (not a revolve) and
    the part stays visible (the base shows until the value is valid); Cancel leaves the part shown."""
    base = doc().getObject(ST["pad"])
    Gui.Selection.clearSelection()
    for e in top_line_edges(base):
        Gui.Selection.addSelection(doc().Name, base.Name, e)
    commands.REGISTRY.run("feature.chamfer")
    harness.pump(900)
    assert dialog() is not None and len(dialog().values()["edges"].split(",")) == 2, dialog().values()
    w = dialog().field("size")
    w.setText("1 mm")
    w.editingFinished.emit()
    harness.pump(800)
    feature = s().feature_session.feature
    assert feature is not None and not dialog().error_text(), dialog().error_text()
    assert feature.Visibility and not base.Visibility, (feature.Visibility, base.Visibility)
    w.setText("500 mm")
    w.editingFinished.emit()
    harness.pump(900)
    err = dialog().error_text()
    assert "chamfer" in err.lower() and "revolve" not in err.lower(), err
    assert base.Visibility and not feature.Visibility, ("part still shown", base.Visibility, feature.Visibility)
    w.setText("1 mm")
    w.editingFinished.emit()
    harness.pump(900)
    assert not dialog().error_text(), dialog().error_text()
    assert feature.Visibility and not base.Visibility, (feature.Visibility, base.Visibility)
    w.setText("500 mm")
    w.editingFinished.emit()
    harness.pump(900)
    QTest.mouseClick(dialog().cancel_button, QtCore.Qt.LeftButton)
    harness.pump(800)
    assert base.Visibility, "Cancel leaves the part shown"
    Gui.Selection.clearSelection()


def test_2_cancelling_an_edit_that_was_failing_shows_the_feature_again():
    base = doc().getObject(ST["pad"])
    Gui.Selection.clearSelection()
    for e in top_line_edges(base):
        Gui.Selection.addSelection(doc().Name, base.Name, e)
    commands.REGISTRY.run("feature.chamfer")
    harness.pump(900)
    w = dialog().field("size")
    w.setText("1 mm")
    w.editingFinished.emit()
    harness.pump(800)
    QTest.mouseClick(dialog().ok_button, QtCore.Qt.LeftButton)
    harness.pump(800)
    chamfer = body().Tip
    assert chamfer.TypeId == "PartDesign::Chamfer" and chamfer.Visibility and not base.Visibility
    shell.edit_feature(chamfer)
    harness.pump(900)
    w = dialog().field("size")
    w.setText("500 mm")
    w.editingFinished.emit()
    harness.pump(900)
    assert dialog().error_text() and base.Visibility and not chamfer.Visibility
    QTest.mouseClick(dialog().cancel_button, QtCore.Qt.LeftButton)
    harness.pump(900)
    assert chamfer.Visibility and not base.Visibility, (chamfer.Visibility, base.Visibility)
    assert "Invalid" not in chamfer.State and chamfer.Shape.Volume > 0


harness.run([test_0_setup, test_1_a_failing_chamfer_explains_itself_and_keeps_the_part_on_screen,
             test_2_cancelling_an_edit_that_was_failing_shows_the_feature_again])
