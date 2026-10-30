"""Project Geometry on an edge of another Solid (the user: nothing of the lid could be projected into a sketch of the
jar — FreeCAD links projected edges only from the sketch's own Solid): the edge is copied into the sketch as its own
geometry; an edge of the sketch's own Solid is still projected (linked) by FreeCAD, not copied."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
from incad.core import commands, document, prefs  # noqa: E402
from incad.core import sketch as sketches  # noqa: E402
from incad.ui import shell  # noqa: E402
import headless.util as util  # noqa: E402

V = App.Vector
ST = {}


def doc():
    return App.ActiveDocument


def test_0_jar_and_lid():
    prefs.set_remember_new_choice(True)
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    jar = document.primary_body(doc())
    pad = util.add_pad(jar, util.add_rect_sketch(jar, 20, 10, "JarSk"), 10, "Jar")
    jar.Tip = pad
    lid = doc().addObject("PartDesign::Body", "Lid")
    sk = lid.newObject("Sketcher::SketchObject", "LidSk")
    sk.AttachmentSupport = [(util.xy_plane(lid), "")]
    sk.MapMode = "FlatFace"
    sk.addGeometry(Part.Circle(V(40, 5, 0), V(0, 0, 1), 5))
    lid.Tip = util.add_pad(lid, sk, 4, "LidPad")
    doc().recompute()
    Gui.SendMsgToActiveView("ViewFit")
    harness.pump(500)
    ST.update(jar=jar, pad=pad, lid=lid)


def test_1_copy_edges_lies_on_the_sketch_plane():
    top = [i + 1 for i, f in enumerate(ST["pad"].Shape.Faces) if f.normalAt(0, 0).z > 0.99][0]
    new = shell.instance().sketches.start_on(ST["pad"], "Face%d" % top)
    harness.pump(1200)
    assert shell.instance().sketches.editing() is new
    ST["sk"] = new


def _click(p):
    from PySide6.QtTest import QTest
    from incad.qt import QtCore
    from incad.ui import dof_handles as dh
    view = Gui.ActiveDocument.ActiveView
    vp = view.graphicsView().viewport()
    x, y = dh.screen(view, vp, p)
    QTest.mouseMove(vp, QtCore.QPoint(int(x), int(y)))
    harness.pump(300)
    QTest.mouseClick(vp, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, QtCore.QPoint(int(x), int(y)))
    harness.pump(1200)


def test_2_a_lid_edge_is_copied_during_project():
    sk = ST["sk"]
    before = sk.GeometryCount
    r = commands.REGISTRY.run("sketch.project")
    harness.pump(800)
    assert r.ok, r.error
    assert shell.instance().projecting
    lid_pad = ST["lid"].Tip
    edge = [e for e in lid_pad.Shape.Edges if e.Curve.TypeId == "Part::GeomCircle" and e.BoundBox.ZMax > 3][0]
    _click(edge.valueAt(edge.FirstParameter + 0.3))
    assert sk.GeometryCount > before, (before, sk.GeometryCount)
    assert any(isinstance(g, Part.Circle) and abs(g.Radius - 5) < 1e-6 for g in sk.Geometry), sk.Geometry
    assert not sk.ExternalGeometry


def test_3_an_own_edge_is_still_projected_by_freecad():
    sk = ST["sk"]
    before = sk.GeometryCount
    pad = ST["pad"]
    edge = [e for e in pad.Shape.Edges if e.BoundBox.ZMax < 1e-6 and e.Length > 15][0]
    _click(edge.valueAt(edge.FirstParameter + edge.Length / 2))
    assert sk.GeometryCount == before, "an edge of the sketch's own Solid was copied"
    Gui.runCommand("Sketcher_StopOperation")
    harness.pump(300)
    commands.REGISTRY.run("sketch.finish")
    harness.pump(900)


def test_4_copy_edges_directly():
    sk = ST["sk"]
    n = sk.GeometryCount
    line = Part.makeLine(V(0, 0, 30), V(10, 0, 30))  # above the sketch plane: drawn on it
    ids = sketches.copy_edges(sk, [line, Part.makeLine(V(5, 5, 0), V(5, 5, 20))])  # the second is seen end on
    doc().recompute()
    assert len(ids) == 1 and sk.GeometryCount == n + 1
    g = sk.Geometry[ids[0]]
    assert abs(g.StartPoint.z) < 1e-9 and abs(g.EndPoint.z) < 1e-9 and abs(g.length() - 10) < 1e-6


def test_9_cleanup():
    App.closeDocument(doc().Name)


harness.run([test_0_jar_and_lid, test_1_copy_edges_lies_on_the_sketch_plane, test_2_a_lid_edge_is_copied_during_project,
             test_3_an_own_edge_is_still_projected_by_freecad, test_4_copy_edges_directly, test_9_cleanup])
