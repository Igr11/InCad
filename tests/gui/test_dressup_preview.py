"""The user: Fillet has no preview (a picked edge showed the part as it was, not rounded) and Chamfer started on the
wrong edge. The dialog shows the result while edges are picked, and a new Chamfer starts on nothing but the edges
selected for it."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
import Part  # noqa: E402
from incad.qt import QtCore, QtGui, QtWidgets  # noqa: E402
from incad.ui import dof_handles  # noqa: E402
from incad.core import commands, document, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402
import headless.util as util  # noqa: E402

ST = {}


def s():
    return shell.instance()


def doc():
    return App.getDocument(ST["doc"])


def fs():
    return s().feature_session


def edge_at(obj, x, y, z):
    """'EdgeN' of the straight edge of `obj` whose middle is at (x, y, z)."""
    p = App.Vector(x, y, z)
    return "Edge%d" % next(i for i, e in enumerate(obj.Shape.Edges, 1) if (e.CenterOfMass - p).Length < 1e-6)


def test_0_setup():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    d = App.newDocument("DressupPreview")
    ST["doc"] = d.Name
    harness.pump(500)
    _, pad = util.padded_part(d, 10, incad=True)  # 20 x 10 x 10
    ST["pad"] = pad.Name
    harness.pump(500)


def test_1_a_clicked_edge_shows_the_fillet():
    pad = doc().getObject(ST["pad"])
    Gui.Selection.clearSelection()
    harness.pump(300)
    commands.REGISTRY.run("feature.fillet")
    harness.pump(1000)
    assert fs() is not None and fs().dialog.active_pick() == "edges"
    Gui.Selection.addSelection(doc().Name, pad.Name, edge_at(pad, 10, 0, 10))  # the click: top front edge
    harness.pump(1500)
    f = fs().feature
    assert f is not None and "Invalid" not in f.State, fs().dialog.error_text()
    shown = {"Pad": pad.ViewObject.Visibility, "Fillet": f.ViewObject.Visibility}
    assert shown["Fillet"] and not shown["Pad"], ("the rounded part shows", shown, fs().dialog.active_pick())
    # a second edge clicked on the preview (the top back edge, untouched by the fillet) stands for the part's edge
    Gui.Selection.addSelection(doc().Name, f.Name, edge_at(f, 10, 10, 10))
    harness.pump(1500)
    picked = set(fs().dialog.values()["edges"].replace(" ", "").split(","))
    assert picked == {"%s:%s" % (pad.Name, edge_at(pad, 10, 0, 10)), "%s:%s" % (pad.Name, edge_at(pad, 10, 10, 10))}, (
        picked, fs().dialog.error_text())
    assert f.ViewObject.Visibility and not pad.ViewObject.Visibility, "still the preview"
    QTest.mouseClick(fs().dialog.ok_button, QtCore.Qt.LeftButton)
    harness.pump(1200)
    assert fs() is None and document.primary_body(doc()).Tip.TypeId == "PartDesign::Fillet"


def test_2_chamfer_after_a_fillet_starts_empty():
    """Right after Fillet's OK nothing the fillet picked may slip into the Chamfer."""
    commands.REGISTRY.run("feature.chamfer")
    harness.pump(1200)
    assert fs() is not None, "the Chamfer dialog opens"
    edges = fs().dialog.values()["edges"]
    sel = [(x.ObjectName, list(x.SubElementNames)) for x in Gui.Selection.getSelectionEx(doc().Name)]
    assert edges == "", ("Chamfer starts on no edge", edges, sel)
    QTest.mouseClick(fs().dialog.cancel_button, QtCore.Qt.LeftButton)
    harness.pump(900)


L, N = QtCore.Qt.LeftButton, QtCore.Qt.NoButton


def click(point):
    view = Gui.getDocument(ST["doc"]).ActiveView
    vp = view.graphicsView().viewport()
    pos = QtCore.QPointF(*dof_handles.screen(view, vp, point))
    for kind, button, buttons, ms in ((QtCore.QEvent.MouseMove, N, N, 300), (QtCore.QEvent.MouseButtonPress, L, L, 60),
                                      (QtCore.QEvent.MouseButtonRelease, L, N, 1200)):
        QtWidgets.QApplication.sendEvent(vp, QtGui.QMouseEvent(kind, pos, QtCore.QPointF(vp.mapToGlobal(pos.toPoint())),
                                                                button, buttons, QtCore.Qt.NoModifier))
        harness.pump(ms)


def ring(obj, z):
    """'EdgeN' of the elliptic edge of `obj` at height z."""
    return "Edge%d" % next(i for i, e in enumerate(obj.Shape.Edges, 1)
                           if "Ellipse" in type(e.Curve).__name__ and abs(e.CenterOfMass.z - z) < 1e-6)


def on_ring(z, t=-0.7):
    import math
    return App.Vector(20 * math.cos(t), 10 * math.sin(t), z)


def test_4_elliptic_pad():
    """The user's part: a sketch with a 3-point ellipse (major 20, minor 10), extruded 10."""
    d = App.newDocument("EllipsePad")
    ST["edoc"] = d.Name
    harness.pump(500)
    body = document.make_part(d)
    sk = body.newObject("Sketcher::SketchObject", "Ellipse")
    sk.AttachmentSupport = [(util.xy_plane(body), "")]
    sk.MapMode = "FlatFace"
    sk.addGeometry(Part.Ellipse(App.Vector(20, 0, 0), App.Vector(0, 10, 0), App.Vector(0, 0, 0)))  # 3 points
    pad = util.add_pad(body, sk, 10)
    body.Tip = pad
    d.recompute()
    assert pad.Shape.isValid() and abs(pad.Shape.Volume - 3.14159265 * 20 * 10 * 10) < 1, pad.Shape.Volume
    ST["doc"], ST["epad"] = d.Name, pad.Name
    view = Gui.getDocument(d.Name).ActiveView
    view.viewIsometric()
    view.fitAll()
    harness.pump(800)


def test_5_fillet_on_the_top_ring_shows_the_round():
    pad = doc().getObject(ST["epad"])
    Gui.Selection.clearSelection()
    harness.pump(300)
    commands.REGISTRY.run("feature.fillet")
    harness.pump(1000)
    click(on_ring(10))  # on the top ring, toward the viewer (off the seam at the end of the major axis)
    harness.pump(800)
    edges = fs().dialog.values()["edges"]
    assert edges == "%s:%s" % (pad.Name, ring(pad, 10)), (edges, ring(pad, 10), ring(pad, 0), fs().dialog.error_text())
    f = fs().feature
    assert f is not None and "Invalid" not in f.State and f.ViewObject.Visibility and not pad.ViewObject.Visibility, (
        f and f.State, fs().dialog.error_text())
    QTest.mouseClick(fs().dialog.ok_button, QtCore.Qt.LeftButton)
    harness.pump(1200)
    tip = document.primary_body(doc()).Tip
    assert tip.TypeId == "PartDesign::Fillet" and "Invalid" not in tip.State, tip.getStatusString()


def test_6_chamfer_starts_empty_and_takes_the_ring_clicked():
    fillet = document.primary_body(doc()).Tip
    commands.REGISTRY.run("feature.chamfer")
    harness.pump(1200)
    assert fs().dialog.values()["edges"] == "", ("Chamfer starts on no edge", fs().dialog.values()["edges"])
    click(on_ring(0))  # the bottom ring
    harness.pump(800)
    edges = fs().dialog.values()["edges"]
    assert edges == "%s:%s" % (fillet.Name, ring(fillet, 0)), (edges, ring(fillet, 0), fs().dialog.error_text())
    f = fs().feature
    assert f is not None and "Invalid" not in f.State and f.ViewObject.Visibility, (f and f.State, fs().dialog.error_text())
    QTest.mouseClick(fs().dialog.ok_button, QtCore.Qt.LeftButton)
    harness.pump(1200)
    tip = document.primary_body(doc()).Tip
    assert tip.TypeId == "PartDesign::Chamfer" and "Invalid" not in tip.State, tip.getStatusString()
    assert abs(tip.Shape.BoundBox.ZMin) < 1e-6 and tip.Shape.Volume < fillet.Shape.Volume - 1, "cut at the bottom"


def test_3_cleanup():
    for name in ("DressupPreview", ST.get("edoc")):
        if name and name in App.listDocuments():
            App.closeDocument(name)
            harness.pump(400)


harness.run([test_0_setup, test_1_a_clicked_edge_shows_the_fillet, test_2_chamfer_after_a_fillet_starts_empty,
             test_4_elliptic_pad, test_5_fillet_on_the_top_ring_shows_the_round,
             test_6_chamfer_starts_empty_and_takes_the_ring_clicked, test_3_cleanup])
