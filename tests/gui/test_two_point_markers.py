"""The 'Two points' revolve axis shows its markers on the part's corners/edges/centres; they sit on the solid,
which can be off screen when the user is zoomed into the sketch, so starting the pick fits the view to bring
every marker on screen (the 'markers don't appear every time' report)."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from incad.qt import QtCore  # noqa: E402
from incad.core import commands, document, prefs, slots  # noqa: E402
from incad.ui import shell  # noqa: E402
import headless.util as util  # noqa: E402


def s():
    return shell.instance()


def body():
    return document.primary_body(App.ActiveDocument)


def dialog():
    return s().feature_session.dialog if s().feature_session else None


def open_two_point_revolve():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    util.add_pad(body(), util.add_rect_sketch(body(), 100, 80, name="Base"), 20)
    App.ActiveDocument.recompute()
    pad = App.ActiveDocument.getObject("Pad")
    top = [i + 1 for i, f in enumerate(pad.Shape.Faces) if abs(f.CenterOfMass.z - 20) < 1e-6][0]
    sk = body().newObject("Sketcher::SketchObject", "Prof")
    sk.AttachmentSupport = [(pad, "Face%d" % top)]
    sk.MapMode = "FlatFace"
    App.ActiveDocument.recompute()
    slots.add(sk, App.Vector(45, 40, 0), App.Vector(55, 40, 0), 2)
    App.ActiveDocument.recompute()
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(App.ActiveDocument.Name, sk.Name)
    commands.REGISTRY.run("feature.revolve")
    harness.pump(1000)


def activate_two_points():
    w = dialog().field("axis_mode")
    w.setCurrentIndex(w.findData("two_points"))
    harness.pump(800)
    QTest.mouseClick(dialog().field("axis_points"), QtCore.Qt.LeftButton)
    harness.pump(800)


def all_markers_on_screen():
    view = Gui.ActiveDocument.ActiveView
    pk = s()._point_pick
    assert pk is not None and len(pk.points) >= 8, pk and len(pk.points)
    w, h = view.getSize()
    return sum(1 for p in pk.points if 0 <= view.getPointOnViewport(p)[0] <= w
               and 0 <= view.getPointOnViewport(p)[1] <= h), len(pk.points)


def test_0_markers_appear_and_fit_when_zoomed_into_the_sketch():
    open_two_point_revolve()
    view = Gui.ActiveDocument.ActiveView
    cam = view.getCameraNode()
    try:
        cam.height.setValue(8.0)  # zoom hard into the slot so the solid's corners fall off screen
    except Exception:
        pass
    harness.pump(300)
    activate_two_points()
    on, total = all_markers_on_screen()
    assert on == total, "markers off screen: %d of %d" % (on, total)
    QTest.mouseClick(dialog().cancel_button, QtCore.Qt.LeftButton)
    harness.pump(500)


def test_1_markers_reappear_on_every_activation():
    open_two_point_revolve()
    for _ in range(3):
        activate_two_points()
        assert s()._point_pick is not None, "markers missing on an activation"
        QTest.mouseClick(dialog().field("axis_points"), QtCore.Qt.LeftButton)  # toggle off
        harness.pump(400)
        assert s()._point_pick is None
    QTest.mouseClick(dialog().cancel_button, QtCore.Qt.LeftButton)
    harness.pump(500)


harness.run([test_0_markers_appear_and_fit_when_zoomed_into_the_sketch,
             test_1_markers_reappear_on_every_activation])
