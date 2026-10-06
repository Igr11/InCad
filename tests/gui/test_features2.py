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
from incad.qt import QtCore  # noqa: E402
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


def test_0_setup():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    sk = util.add_rect_sketch(body(), w=40, h=20)
    pad = util.add_pad(body(), sk, 10)
    body().Tip = pad
    doc().recompute()
    ST["pad"] = pad.Name
    harness.pump(300)


def test_1_fillet_takes_preselected_edges():
    pad = doc().getObject(ST["pad"])
    Gui.Selection.clearSelection()
    for e in top_edges(pad, 10):
        Gui.Selection.addSelection(doc().Name, pad.Name, e)
    commands.REGISTRY.run("feature.fillet")
    harness.pump(900)
    assert dialog() is not None
    assert dialog().field("edges").text() == "4 edges", dialog().field("edges").text()
    ok()
    assert body().Tip.TypeId == "PartDesign::Fillet", body().Tip.TypeId


def test_2_hole_from_sketch():
    fillet = body().Tip
    top = [i + 1 for i, f in enumerate(fillet.Shape.Faces)
           if abs(f.CenterOfMass.z - 10) < 1e-6 and f.Surface.TypeId == "Part::GeomPlane"][0]
    sk = body().newObject("Sketcher::SketchObject", "Holes")
    sk.AttachmentSupport = [(fillet, "Face%d" % top)]
    sk.MapMode = "FlatFace"
    sk.addGeometry(Part.Circle(App.Vector(10, 10, 0), App.Vector(0, 0, 1), 1))
    sk.addGeometry(Part.Circle(App.Vector(30, 10, 0), App.Vector(0, 0, 1), 1))
    doc().recompute()
    Gui.Selection.clearSelection()
    commands.REGISTRY.run("feature.hole")
    harness.pump(800)
    assert dialog().active_pick() == "sketch"
    Gui.Selection.addSelection(doc().Name, sk.Name)
    harness.pump(800)
    ok()
    assert body().Tip.TypeId == "PartDesign::Hole", body().Tip.TypeId


def test_3_wrong_pick_kind_is_refused():
    Gui.Selection.clearSelection()
    commands.REGISTRY.run("feature.chamfer")
    harness.pump(800)
    tip = body().Tip
    assert tip.TypeId == "PartDesign::Hole", tip.TypeId  # an unfinished Chamfer must not linger as the Tip
    top = [i + 1 for i, f in enumerate(tip.Shape.Faces) if abs(f.CenterOfMass.z - 10) < 1e-6][0]
    Gui.Selection.addSelection(doc().Name, tip.Name, "Face%d" % top)
    harness.pump(600)
    assert "Select edge" in dialog().error_text(), dialog().error_text()
    QTest.keyClick(dialog(), QtCore.Qt.Key_Escape)
    harness.pump(600)
    assert s().feature_session is None


def test_4_rectangular_pattern_of_the_hole():
    hole = body().Tip
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, hole.Name)
    commands.REGISTRY.run("feature.rect_pattern")
    harness.pump(900)
    w = dialog().field("spacing1")
    w.setText("5 mm")
    w.editingFinished.emit()
    harness.pump(600)
    assert not dialog().error_text(), (dialog().error_text(), dialog().values())
    ok()
    assert body().Tip.TypeId == "PartDesign::LinearPattern", body().Tip.TypeId


def test_5_measure_and_mass():
    tip = body().Tip
    faces = tip.Shape.Faces
    bottom = [i + 1 for i, f in enumerate(faces) if abs(f.CenterOfMass.z) < 1e-6][0]
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, tip.Name, "Face%d" % bottom)
    commands.REGISTRY.run("inspect.measure")
    harness.pump(500)
    rows = dict(s().info_panel.rows())
    assert "Area" in rows, rows
    commands.REGISTRY.run("inspect.mass")
    harness.pump(500)
    rows = dict(s().info_panel.rows())
    assert "Mass" in rows and "Volume" in rows, rows
    Gui.Selection.clearSelection()
    commands.REGISTRY.run("inspect.measure")
    harness.pump(400)
    assert "select" in s().status.texts()["message"].lower(), s().status.texts()


def test_6_extrude_to_face_pick_now_works():
    sk = body().newObject("Sketcher::SketchObject", "ToProfile")
    sk.AttachmentSupport = [(util.xy_plane(body()), "")]
    sk.MapMode = "FlatFace"
    sk.addGeometry(Part.Circle(App.Vector(-20, 0, 0), App.Vector(0, 0, 1), 2))
    plane = body().newObject("PartDesign::Plane", "Limit")
    plane.AttachmentSupport = [(util.xy_plane(body()), "")]
    plane.MapMode = "FlatFace"
    plane.AttachmentOffset = App.Placement(App.Vector(0, 0, 7), App.Rotation())
    doc().recompute()
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, sk.Name)
    commands.REGISTRY.run("feature.extrude")
    harness.pump(800)
    dialog().field("operation").button("new_solid").click()
    dialog().field("extent").button("to").click()
    harness.pump(500)
    dialog().field("to_face").click()
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, plane.Name)
    harness.pump(800)
    assert dialog().values()["to_face"].startswith(plane.Name), dialog().values()
    QTest.mouseClick(dialog().cancel_button, QtCore.Qt.LeftButton)
    harness.pump(600)


def test_7_theme_switch_closes_the_old_info_panel():
    commands.REGISTRY.run("inspect.mass")
    harness.pump(400)
    assert s().info_panel is not None
    commands.REGISTRY.run("view.theme_toggle")
    harness.pump(500)
    commands.REGISTRY.run("view.theme_toggle")
    harness.pump(500)
    assert s().info_panel is None


harness.run([test_0_setup, test_1_fillet_takes_preselected_edges, test_2_hole_from_sketch,
             test_3_wrong_pick_kind_is_refused, test_4_rectangular_pattern_of_the_hole, test_5_measure_and_mass,
             test_6_extrude_to_face_pick_now_works, test_7_theme_switch_closes_the_old_info_panel])
