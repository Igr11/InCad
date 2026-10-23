"""Work Plane ▸ Offset ▸ Planes (the user: several planes at different offsets in one click, for lofts): Planes = 3 on the
box's top face makes three planes 5, 10, 15 mm above it; reopening the first plane's dialog shows Planes 3, and a
new offset there spaces the whole row."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from incad.qt import QtCore  # noqa: E402
from incad.core import commands, document, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402

V = App.Vector
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


def test_0_box():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    box = body().newObject("PartDesign::AdditiveBox", "Box")
    box.Length, box.Width, box.Height = 20, 10, 6
    doc().recompute()
    Gui.SendMsgToActiveView("ViewFit")
    harness.pump(500)
    ST["box"] = box.Name


def _planes():
    return sorted((o for o in body().Group if o.TypeId == "PartDesign::Plane"), key=lambda o: o.Placement.Base.z)


def test_1_three_planes_in_one_go():
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, body().Name, ST["box"] + ".Face6")
    commands.REGISTRY.run("work.plane")
    harness.pump(1000)
    d = dialog()
    assert d is not None
    assert "count" in d._widgets and d.field("count").isVisible(), "no Planes field"
    d.set_values({"offset": "5 mm", "count": "3"})
    harness.pump(1500)
    QTest.mouseClick(d.ok_button, QtCore.Qt.LeftButton)
    harness.pump(1200)
    assert s().feature_session is None
    zs = [round(p.Placement.Base.z, 6) for p in _planes()]
    assert zs == [11, 16, 21], zs
    for p in _planes():
        assert "Invalid" not in p.State, p.getStatusString()


def test_2_edit_spaces_the_row():
    first = _planes()[0]
    Gui.Selection.clearSelection()
    s().edit_feature(first)
    harness.pump(1000)
    d = dialog()
    assert d is not None, "no dialog for the first plane"
    assert d.values()["count"] == "3", d.values()
    d.set_values({"offset": "2 mm"})
    harness.pump(1500)
    QTest.mouseClick(d.ok_button, QtCore.Qt.LeftButton)
    harness.pump(1200)
    zs = [round(p.Placement.Base.z, 6) for p in _planes()]
    assert zs == [8, 10, 12], zs


def test_3_turn_a_plane_with_its_ring():
    """The second plane's dialog: one compact Turn row (Prev / Global, X, Y, Z) and rings on the plane; dragging the
    red (X) knob tilts the plane and writes the angle; the third plane stays as it was."""
    from incad.ui import dof_handles as dh
    from incad.ui.plane_turn import viewport_of
    planes = _planes()
    second, third = planes[1], planes[2]
    Gui.Selection.clearSelection()
    s().edit_feature(second)
    harness.pump(1200)
    d = dialog()
    assert d is not None
    rows = {d.field(k).parentWidget() for k in ("turn_ref", "turn_x", "turn_y", "turn_z")}
    assert len(rows) == 1, "Turn is not one row"
    ring = s()._overlay
    assert ring is not None and ring.root is not None, "no rings"
    view = Gui.ActiveDocument.ActiveView
    vp = viewport_of(view)
    Gui.SendMsgToActiveView("ViewFit")
    harness.pump(400)
    ring.refresh()
    kx, ky = dh.screen(view, vp, ring._at(0, 0.0))
    assert ring.press(view, vp, kx, ky), "the X knob not caught"
    target = None
    for a in range(5, 90, 5):  # a point of the X circle at 30°
        if a == 30:
            target = dh.screen(view, vp, ring._at(0, 30.0))
    ring.move(kx + (target[0] - kx) * 0.5, ky + (target[1] - ky) * 0.5)
    ring.move(*target)
    harness.pump(1500)
    ring.release()
    harness.pump(800)
    assert d.values()["turn_x"] == "30 °", d.values()["turn_x"]
    if os.environ.get("INNCAD_SHOT"):
        d.grab().save(os.environ["INNCAD_SHOT"])
        view.saveImage(os.environ["INNCAD_SHOT"].replace(".png", "_view.png"), 900, 600, "Current")
    QTest.mouseClick(d.ok_button, QtCore.Qt.LeftButton)
    harness.pump(1200)
    n2 = second.Placement.Rotation.multVec(V(0, 0, 1))
    n3 = third.Placement.Rotation.multVec(V(0, 0, 1))
    import math
    assert abs(math.degrees(n2.getAngle(V(0, 0, 1))) - 30) < 1e-6, n2
    assert n3.getAngle(V(0, 0, 1)) < 1e-9, n3


def test_9_cleanup():
    harness.pump(300)
    App.closeDocument(doc().Name)


harness.run([test_0_box, test_1_three_planes_in_one_go, test_2_edit_spaces_the_row, test_3_turn_a_plane_with_its_ring, test_9_cleanup])
