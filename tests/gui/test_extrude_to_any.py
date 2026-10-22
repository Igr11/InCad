"""Extrude ▸ To in the dialog (the user: "To must reach any face, any surface, any point"): a face of another Solid
and a corner of it are taken (they were refused as not on the current shape), the preview stops there, OK keeps it."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from incad.qt import QtCore  # noqa: E402
from incad.core import commands, document, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402
import headless.util as util  # noqa: E402

V = App.Vector
ST = {}


def s():
    return shell.instance()


def doc():
    return App.ActiveDocument


def dialog():
    fs = s().feature_session
    return fs.dialog if fs is not None else None


def feature():
    return s().feature_session.feature


def test_0_part_and_a_box_above():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    body = document.primary_body(doc())
    util.add_pad(body, util.add_rect_sketch(body, 20, 10, "Base"), 5)
    doc().recompute()
    other = document.new_solid(doc())
    box = other.newObject("PartDesign::AdditiveBox", "Roof")
    box.Length, box.Width, box.Height = 40, 30, 4
    other.Placement = App.Placement(V(-10, -10, 25), App.Rotation())
    sk = body.newObject("Sketcher::SketchObject", "Post")
    sk.AttachmentSupport = [(util.xy_plane(body), "")]
    sk.MapMode = "FlatFace"
    sk.AttachmentOffset = App.Placement(V(0, 0, 5), App.Rotation())
    import Part
    sk.addGeometry(Part.Circle(V(10, 5, 0), V(0, 0, 1), 2))
    doc().recompute()
    harness.pump(500)
    ST.update(body=body, box=box, sk=sk)


def open_to():
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, ST["sk"].Name)
    commands.REGISTRY.run("feature.extrude")
    harness.pump(800)
    dialog().field("operation").button("join").click()
    dialog().field("extent").button("to").click()
    harness.pump(500)
    if dialog().active_pick() != "to_face":
        dialog().field("to_face").click()
    harness.pump(300)


def test_1_face_of_another_solid():
    open_to()
    box = ST["box"]
    bottom = [i + 1 for i, f in enumerate(box.Shape.Faces) if f.normalAt(0, 0).z < -0.5][0]
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, box.getParentGeoFeatureGroup().Name, "%s.Face%d" % (box.Name, bottom))
    harness.pump(1500)
    assert dialog().values()["to_face"] == "%s:Face%d" % (box.Name, bottom), (dialog().values()["to_face"],
                                                                             dialog().error_text())
    assert not dialog().error_text(), dialog().error_text()
    assert abs(feature().Shape.BoundBox.ZMax - 25) < 1e-6, feature().Shape.BoundBox
    QTest.mouseClick(dialog().ok_button, QtCore.Qt.LeftButton)
    harness.pump(1200)
    assert s().feature_session is None
    f = ST["body"].Tip
    assert "Invalid" not in f.State and abs(f.Shape.BoundBox.ZMax - 25) < 1e-6, (f.State, f.Shape.BoundBox)
    ST["f"] = f.Name


def test_2_edit_to_a_corner_of_it():
    f = doc().getObject(ST["f"])
    Gui.Selection.clearSelection()
    s().edit_feature(f)
    harness.pump(1000)
    assert dialog() is not None
    if dialog().active_pick() != "to_face":
        dialog().field("to_face").click()
        harness.pump(300)
    box = ST["box"]
    top = [i + 1 for i, p in enumerate(box.Shape.Vertexes) if abs(p.Point.z - 4) < 1e-6][0]
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, box.getParentGeoFeatureGroup().Name, "%s.Vertex%d" % (box.Name, top))
    harness.pump(1500)
    assert dialog().values()["to_face"] == "%s:Vertex%d" % (box.Name, top), (dialog().values(), dialog().error_text())
    QTest.mouseClick(dialog().ok_button, QtCore.Qt.LeftButton)
    harness.pump(1200)
    f = ST["body"].Tip
    assert abs(f.Shape.BoundBox.ZMax - 29) < 1e-6, f.Shape.BoundBox


def test_9_cleanup():
    if s().feature_session is not None:
        s().feature_session.cancel()
    harness.pump(300)
    App.closeDocument(doc().Name)


harness.run([test_0_part_and_a_box_above, test_1_face_of_another_solid, test_2_edit_to_a_corner_of_it, test_9_cleanup])
