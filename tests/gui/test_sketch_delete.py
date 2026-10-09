"""Delete in a sketch on geometry a pattern tied up: FreeCAD's own Std_Delete crashed in
ViewProviderSketch::onDelete (crash report 2026-10-10 00:12). Both cases run in a real window."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
import Part  # noqa: E402
import Sketcher  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from incad.qt import QtCore  # noqa: E402
from incad.core import commands, prefs, sketch_patterns as sp  # noqa: E402
from incad.ui import shell  # noqa: E402

ST = {}


def s():
    return shell.instance()


def sk():
    return Gui.ActiveDocument.getInEdit().Object


def dialog():
    fs = s().feature_session
    return fs.dialog if fs is not None else None


def test_0_sketch():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    commands.REGISTRY.run("sketch.start")
    harness.pump(600)
    s().plane_panel.button("XY_Plane").click()
    harness.pump(1200)


def test_1_delete_a_circle_whose_constraint_is_hidden():
    k = sk()
    c = k.addGeometry(Part.Circle(App.Vector(20, 20, 0), App.Vector(0, 0, 1), 1))
    i = k.addConstraint(Sketcher.Constraint("DistanceX", -1, 1, c, 3, 20.0))
    k.setVirtualSpace(i, True)
    App.ActiveDocument.recompute()
    harness.pump(500)
    before = k.GeometryCount
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(App.ActiveDocument.Name, k.Name, "Edge%d" % (c + 1))
    harness.pump(300)
    res = commands.REGISTRY.run("edit.delete")
    harness.pump(1200)
    assert res.ok, res.error
    assert k.GeometryCount == before - 1


def test_2_delete_a_copy_of_a_circular_pattern():
    k = sk()
    hole = k.addGeometry(Part.Circle(App.Vector(10, 0, 0), App.Vector(0, 0, 1), 1))
    k.addConstraint(Sketcher.Constraint("DistanceX", -1, 1, hole, 3, 10.0))
    k.addConstraint(Sketcher.Constraint("DistanceY", -1, 1, hole, 3, 0.0))
    App.ActiveDocument.recompute()
    harness.pump(300)
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(App.ActiveDocument.Name, k.Name, "Edge%d" % (hole + 1))
    commands.REGISTRY.run("sketch.circ_pattern")
    harness.pump(1500)
    assert dialog() is not None and not dialog().error_text(), dialog() and dialog().error_text()
    QTest.mouseClick(dialog().ok_button, QtCore.Qt.LeftButton)
    harness.pump(1000)
    rec = sp.records(k)[-1]
    copy = sp.index_of(k, [g for g in rec["copies"][0] if not k.getConstruction(sp.index_of(k, g))][0])
    before = k.GeometryCount
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(App.ActiveDocument.Name, k.Name, "Edge%d" % (copy + 1))
    harness.pump(300)
    res = commands.REGISTRY.run("edit.delete")
    harness.pump(1500)
    assert res.ok, res.error
    assert k.GeometryCount < before
    assert sp.is_broken(k, rec["name"])
    assert sp.find(k, rec["name"]) is not None, "the pattern stays, broken, and is rebuilt on its next edit"
    App.ActiveDocument.undo()
    harness.pump(600)
    assert k.GeometryCount == before, "one undo step"
    App.ActiveDocument.redo()
    harness.pump(600)


def test_2b_stale_selection_names_are_dropped_before_the_sketchers_delete():
    k = sk()
    extra = k.addGeometry(Part.Circle(App.Vector(-20, -20, 0), App.Vector(0, 0, 1), 1))
    App.ActiveDocument.recompute()
    harness.pump(300)
    before = k.GeometryCount
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(App.ActiveDocument.Name, k.Name, "Edge%d" % (extra + 1))
    Gui.Selection.addSelection(App.ActiveDocument.Name, k.Name, "Edge%d" % (before + 40))  # points past the end
    harness.pump(300)
    res = commands.REGISTRY.run("edit.delete")
    harness.pump(1200)
    assert res.ok, res.error
    assert k.GeometryCount == before - 1, (k.GeometryCount, before)


def test_3_delete_a_copy_of_a_pattern_round_a_projected_point_on_a_face_sketch():
    """The user's case: a sketch on the part's face, the axis a projected vertex, Delete on a copy."""
    import headless.util as util
    from incad.core import document
    commands.REGISTRY.run("sketch.finish")
    harness.pump(800)
    doc = App.ActiveDocument
    body = document.primary_body(doc)
    pad = util.add_pad(body, util.add_rect_sketch(body, w=40, h=20, name="PadSk"), 10)
    body.Tip = pad
    doc.recompute()
    harness.pump(500)
    top = [i + 1 for i, f in enumerate(pad.Shape.Faces) if abs(f.CenterOfMass.z - 10) < 1e-6][0]
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc.Name, pad.Name, "Face%d" % top)
    commands.REGISTRY.run("sketch.start")
    harness.pump(1500)
    k = sk()
    v = [i + 1 for i, x in enumerate(pad.Shape.Vertexes) if abs(x.Z - 10) < 1e-6 and x.X < 1 and x.Y < 1][0]
    k.addExternal(pad.Name, "Vertex%d" % v)
    hole = k.addGeometry(Part.Circle(App.Vector(8, 4, 0), App.Vector(0, 0, 1), 1))
    doc.recompute()
    harness.pump(500)
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc.Name, k.Name, "Edge%d" % (hole + 1))
    commands.REGISTRY.run("sketch.circ_pattern")
    harness.pump(1500)
    dialog().field("axis").click()
    harness.pump(400)
    # the vertex name as it is NOW (the preview's copies and spokes renumbered the vertices): what a click gives
    axis = "Vertex%d" % ([n for n in range(60) if tuple(k.getGeoVertexIndex(n)) == (-3, 1)][0] + 1)
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc.Name, k.Name, axis)
    harness.pump(1200)
    picked = dialog().values()["axis"]
    sub = picked.split(":")[-1]
    recs = sp.records(k)
    assert not dialog().error_text(), (dialog().error_text(), "axis text", picked, "element", sp.element(k, sub),
                                       "expected", axis, "axis_ref", recs[-1].get("axis_ref") if recs else None,
                                       "ext", [g.TypeId for g in k.ExternalGeo])
    QTest.mouseClick(dialog().ok_button, QtCore.Qt.LeftButton)
    harness.pump(1000)
    rec = sp.records(k)[-1]
    copy = sp.index_of(k, [g for g in rec["copies"][0] if not k.getConstruction(sp.index_of(k, g))][0])
    before = k.GeometryCount
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc.Name, k.Name, "Edge%d" % (copy + 1))
    harness.pump(300)
    res = commands.REGISTRY.run("edit.delete")
    harness.pump(1500)
    assert res.ok, res.error
    assert k.GeometryCount < before


harness.run([test_0_sketch, test_1_delete_a_circle_whose_constraint_is_hidden, test_2_delete_a_copy_of_a_circular_pattern,
             test_2b_stale_selection_names_are_dropped_before_the_sketchers_delete, test_3_delete_a_copy_of_a_pattern_round_a_projected_point_on_a_face_sketch])
