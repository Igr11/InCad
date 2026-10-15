"""Fillet / Chamfer on an edge that lies on the visible profile sketch (the bottom edges of a pad): a click there
picked the sketch's line, the chamfer was built on the sketch ('No Base object linked'), and the sketch could not be
hidden while the dialog was open. While a pick on the solid waits, sketches are not clickable."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from incad.qt import QtCore, QtGui, QtWidgets  # noqa: E402
from incad.core import commands, document, prefs  # noqa: E402
from incad.ui import dof_handles, shell  # noqa: E402
import headless.util as util  # noqa: E402

ST = {}
L, N = QtCore.Qt.LeftButton, QtCore.Qt.NoButton


def s():
    return shell.instance()


def doc():
    return App.getDocument(ST["doc"])


def dialog():
    fs = s().feature_session
    return fs.dialog if fs is not None else None


def view():
    return Gui.getDocument(ST["doc"]).ActiveView


def viewport():
    return view().graphicsView().viewport()


def send(kind, pos, button, buttons):
    vp = viewport()
    glob = QtCore.QPointF(vp.mapToGlobal(pos.toPoint()))
    QtWidgets.QApplication.sendEvent(vp, QtGui.QMouseEvent(kind, pos, glob, button, buttons, QtCore.Qt.NoModifier))


def click(point):
    pos = QtCore.QPointF(*dof_handles.screen(view(), viewport(), point))
    send(QtCore.QEvent.MouseMove, pos, N, N)
    harness.pump(300)
    send(QtCore.QEvent.MouseButtonPress, pos, L, L)
    harness.pump(60)
    send(QtCore.QEvent.MouseButtonRelease, pos, L, N)
    harness.pump(900)


def test_0_setup():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    d = App.newDocument("DressupOverSketch")
    ST["doc"] = d.Name
    harness.pump(500)
    _, pad = util.padded_part(d, 10, incad=True)
    ST["pad"], ST["sk"] = pad.Name, pad.Profile[0].Name
    pad.Profile[0].ViewObject.Visibility = True  # the profile shown, as in the user's part
    view().viewIsometric()
    view().fitAll()
    harness.pump(600)


def _pick_bottom_edge(command):
    Gui.Selection.clearSelection()
    harness.pump(300)
    commands.REGISTRY.run(command)
    harness.pump(1200)
    assert dialog() is not None and dialog().active_pick() == "edges", (dialog() and dialog().active_pick())
    click(App.Vector(10, 0, 0))  # the middle of the bottom front edge, on the sketch's bottom line
    harness.pump(800)
    edges = dialog().values()["edges"]
    picked = [(sel.ObjectName, list(sel.SubElementNames)) for sel in Gui.Selection.getSelectionEx(ST["doc"])]
    assert edges and ST["sk"] not in edges and ":Edge" in edges, (edges, picked, dialog().error_text())
    assert not dialog().error_text(), dialog().error_text()
    QTest.mouseClick(dialog().cancel_button, QtCore.Qt.LeftButton)
    harness.pump(900)


def test_1_fillet_picks_the_solid_edge_over_the_sketch_line():
    _pick_bottom_edge("feature.fillet")


def test_2_chamfer_picks_the_solid_edge_over_the_sketch_line():
    _pick_bottom_edge("feature.chamfer")


def test_2b_a_click_on_the_sketch_line_stands_for_the_solid_edge_under_it():
    """The sketch caught the click in the user's view: its line over the edge picks the edge."""
    sk = doc().getObject(ST["sk"])
    Gui.Selection.clearSelection()
    harness.pump(300)
    commands.REGISTRY.run("feature.chamfer")
    harness.pump(1200)
    bottom = next(i for i, e in enumerate(sk.Shape.Edges, 1)
                  if abs(e.Vertexes[0].Point.y) < 1e-6 and abs(e.Vertexes[-1].Point.y) < 1e-6)
    Gui.Selection.addSelection(doc().Name, sk.Name, "Edge%d" % bottom)  # what FreeCAD gives for that click
    harness.pump(800)
    edges = dialog().values()["edges"]
    pad = doc().getObject(ST["pad"])
    assert edges.startswith(ST["pad"] + ":Edge"), (edges, dialog().error_text())
    e = pad.Shape.getElement(edges.split(":")[1])
    assert abs(e.CenterOfMass.y) < 1e-6 and abs(e.CenterOfMass.z) < 1e-6 and abs(e.Length - 20) < 1e-6, e.CenterOfMass
    QTest.mouseClick(dialog().cancel_button, QtCore.Qt.LeftButton)
    harness.pump(900)


def _shown_sketch(name, y):
    """A sketch the user showed by hand (Hide / Show: InCadShown True), beside the block."""
    body = document.primary_body(doc())
    sk = util.add_rect_sketch(body, name=name)
    sk.AttachmentOffset = App.Placement(App.Vector(0, y, 0), App.Rotation())
    doc().recompute()
    document.prepare_choice([sk])
    document.set_visibility([sk], True)
    harness.pump(400)
    assert sk.ViewObject.Visibility and document.sketch_shown(sk)
    return sk


def _extrude(sk, button):
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, sk.Name)
    commands.REGISTRY.run("feature.extrude")
    harness.pump(1200)
    assert dialog() is not None, open(os.environ["INCAD_LOG"]).read()[-400:]
    QTest.mouseClick(button(), QtCore.Qt.LeftButton)
    harness.pump(1000)


def test_3_a_sketch_shown_by_hand_is_hidden_once_a_feature_uses_it():
    """The user: a sketch a feature uses is hidden (Inventor) — even one shown by hand before."""
    sk = _shown_sketch("ShownThenUsed", 30)
    _extrude(sk, lambda: dialog().ok_button)
    from incad.features import common
    assert common.consumers(sk), "the extrude uses it"
    assert not sk.ViewObject.Visibility and not document.sketch_shown(sk), (sk.ViewObject.Visibility,
                                                                            getattr(sk, document.SHOWN_PROP, None))
    doc().undo()
    harness.pump(800)
    assert document.sketch_shown(sk), "undo gives the shown sketch back"


def test_4_cancel_keeps_a_shown_sketch_shown():
    sk = _shown_sketch("ShownCancelled", 60)
    _extrude(sk, lambda: dialog().cancel_button)
    assert sk.ViewObject.Visibility and document.sketch_shown(sk)


def test_5_cleanup():
    App.closeDocument(ST["doc"])
    harness.pump(500)


harness.run([test_0_setup, test_1_fillet_picks_the_solid_edge_over_the_sketch_line,
             test_2_chamfer_picks_the_solid_edge_over_the_sketch_line,
             test_2b_a_click_on_the_sketch_line_stands_for_the_solid_edge_under_it,
             test_3_a_sketch_shown_by_hand_is_hidden_once_a_feature_uses_it, test_4_cancel_keeps_a_shown_sketch_shown,
             test_5_cleanup])
