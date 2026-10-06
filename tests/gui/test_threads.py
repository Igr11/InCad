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
from headless.test_thread import shaft, cyl_face  # noqa: E402

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
    harness.pump(1500)


def test_0_setup():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    ST["pad"] = shaft(doc(), body(), radius=4.0, length=16).Name
    harness.pump(300)


def test_1_thread_on_a_selected_shaft_face():
    pad = doc().getObject(ST["pad"])
    obj_sub = cyl_face(pad, 4).split(":")
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, obj_sub[0], obj_sub[1])
    names = list(doc().UndoNames)
    commands.REGISTRY.run("feature.thread")
    harness.pump(1500)
    assert dialog() is not None
    assert dialog().values()["size"] == "", dialog().values()
    assert not dialog().error_text(), dialog().error_text()
    ok()
    tip = body().Tip
    assert tip.TypeId == "PartDesign::SubtractiveHelix", tip.TypeId
    assert abs(tip.Pitch.Value - 1.25) < 1e-6, tip.Pitch  # M8 suggested from the Ø8 face
    assert doc().UndoNames[0] == "Thread" and len(doc().UndoNames) == len(names) + 1, (doc().UndoNames, names)
    ST["thread"] = tip.Name


def test_2_edit_the_thread_size():
    t = doc().getObject(ST["thread"])
    shell.edit_feature(t)
    harness.pump(900)
    assert dialog().values()["size"] == "M8", dialog().values()
    combo = dialog().field("standard")
    combo.setCurrentIndex(combo.findData("iso_fine"))
    harness.pump(300)
    size = dialog().field("size")
    size.setCurrentIndex(size.findData("M8x1"))
    harness.pump(1500)
    assert not dialog().error_text(), dialog().error_text()
    ok()
    assert abs(doc().getObject(ST["thread"]).Pitch.Value - 1.0) < 1e-6


def test_3_threaded_hole():
    tip = body().Tip
    sk = util.add_rect_sketch(body(), w=30, h=20, name="Plate")
    plate = util.add_pad(body(), sk, 6, name="Plate")
    body().Tip = plate
    doc().recompute()
    top = [i + 1 for i, f in enumerate(plate.Shape.Faces) if abs(f.CenterOfMass.z - 6) < 1e-6
           and f.Surface.TypeId == "Part::GeomPlane" and f.Area > 400][0]
    hs = body().newObject("Sketcher::SketchObject", "HoleAt")
    hs.AttachmentSupport = [(plate, "Face%d" % top)]
    hs.MapMode = "FlatFace"
    hs.addGeometry(Part.Circle(App.Vector(20, 10, 0), App.Vector(0, 0, 1), 1))
    doc().recompute()
    Gui.Selection.clearSelection()
    commands.REGISTRY.run("feature.hole")
    harness.pump(800)
    Gui.Selection.addSelection(doc().Name, hs.Name)
    harness.pump(800)
    dialog().field("threaded").setChecked(True)
    harness.pump(400)
    assert dialog().values()["thread_size"] == "", dialog().values()  # Auto: from the diameter
    size = dialog().field("thread_size")
    assert size.findData("M6x1.0") >= 0
    size.setCurrentIndex(size.findData("M6x1.0"))
    harness.pump(3000)
    assert not dialog().error_text(), dialog().error_text()
    ok()
    h = body().Tip
    assert h.TypeId == "PartDesign::Hole" and h.Threaded and h.ModelThread, (h.TypeId, h.Threaded)
    assert h.ThreadSize.startswith("M6"), h.ThreadSize


harness.run([test_0_setup, test_1_thread_on_a_selected_shaft_face, test_2_edit_the_thread_size,
             test_3_threaded_hole])
