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


def test_1_a_chamfer_past_the_faces_stops_at_their_far_edges():
    """A distance too big for the faces no longer fails (the user: a 2.5 mm chamfer on a 2 mm face is a 2 mm one):
    two top edges at a corner of a 40 x 20 x 10 block chamfered by 500 mm stop at the bottom of the 10 mm sides
    (40·10²/2 + 20·10²/2 less the corner's 10³/3 taken off); the dialog keeps 500 mm; Cancel leaves the part as
    it was."""
    base = doc().getObject(ST["pad"])
    Gui.Selection.clearSelection()
    for e in top_line_edges(base):
        Gui.Selection.addSelection(doc().Name, base.Name, e)
    commands.REGISTRY.run("feature.chamfer")
    harness.pump(900)
    assert dialog() is not None and len(dialog().values()["edges"].split(",")) == 2, dialog().values()
    assert dialog().values()["size"] == "0.5 mm", dialog().values()["size"]
    w = dialog().field("size")
    w.setText("500 mm")
    w.editingFinished.emit()
    harness.pump(1200)
    assert not dialog().error_text(), dialog().error_text()
    shown = body().Tip
    assert shown is not base and "Invalid" not in shown.State and abs(shown.Shape.Volume - (8000 - 3000 + 1000 / 3.0)) < 0.5, \
        (shown.Name, shown.State, shown.Shape.Volume)
    assert shown.Visibility and not base.Visibility, (shown.Visibility, base.Visibility)
    assert dialog().values()["size"] == "500 mm", dialog().values()["size"]
    QTest.mouseClick(dialog().cancel_button, QtCore.Qt.LeftButton)
    harness.pump(800)
    assert body().Tip is base and base.Visibility, ("Cancel leaves the part as it was", body().Tip.Name)
    assert [o.Name for o in body().Group if "Chamfer" in o.Name] == [], [o.Name for o in body().Group]
    Gui.Selection.clearSelection()


def test_2_an_edit_past_the_faces_and_back():
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
    ok()
    chamfer = body().Tip
    assert chamfer.TypeId == "PartDesign::Chamfer" and chamfer.Visibility and not base.Visibility
    shell.edit_feature(chamfer)
    harness.pump(900)
    w = dialog().field("size")
    w.setText("500 mm")
    w.editingFinished.emit()
    harness.pump(1200)
    assert not dialog().error_text(), dialog().error_text()
    ok()
    tip = body().Tip
    assert "Invalid" not in tip.State and abs(tip.Shape.Volume - (8000 - 3000 + 1000 / 3.0)) < 0.5, (tip.Name, tip.State, tip.Shape.Volume)
    shell.edit_feature(chamfer)
    harness.pump(900)
    assert dialog().values()["size"] == "500 mm", dialog().values()["size"]
    w = dialog().field("size")
    w.setText("1 mm")
    w.editingFinished.emit()
    harness.pump(1000)
    ok()
    tip = body().Tip
    assert "Invalid" not in tip.State and abs(tip.Shape.Volume - (8000 - 30 + 1 / 3.0)) < 0.1, tip.Shape.Volume


harness.run([test_0_setup, test_1_a_chamfer_past_the_faces_stops_at_their_far_edges,
             test_2_an_edit_past_the_faces_and_back])
