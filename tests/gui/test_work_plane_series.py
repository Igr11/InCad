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
from incad.ui import browser, shell  # noqa: E402

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


def _row(name):
    tree = s().browser.tree
    items = [i for i in s().browser._items() if i.data(0, browser.NAME_ROLE) == name]
    assert items, ("a row for", name)
    item = items[0]
    parent = item.parent()
    while parent is not None:
        parent.setExpanded(True)
        parent = parent.parent()
    harness.pump(200)
    tree.scrollToItem(item)
    harness.pump(200)
    return tree.viewport(), tree.visualItemRect(item).center()


def _drag_ring(axis, degrees):
    from incad.ui import dof_handles as dh
    from incad.ui.plane_turn import viewport_of
    ring = s()._overlay
    assert ring is not None and ring.root is not None, "no rings"
    view = Gui.ActiveDocument.ActiveView
    vp = viewport_of(view)
    ring.refresh()
    kx, ky = dh.screen(view, vp, ring._at(axis, ring._angle(axis)))
    assert ring.press(view, vp, kx, ky), "knob %d not caught" % axis
    tx, ty = dh.screen(view, vp, ring._at(axis, degrees))
    ring.move(kx + (tx - kx) * 0.5, ky + (ty - ky) * 0.5)
    ring.move(tx, ty)
    harness.pump(1500)
    ring.release()
    harness.pump(800)


def _tilt(p):
    import math
    return math.degrees(p.Placement.Rotation.multVec(V(0, 0, 1)).getAngle(V(0, 0, 1)))


def test_4_turn_every_plane_of_the_row():
    """The user: only the second plane could be turned. The third turns with its own rings (relative to the second),
    the first with its own, and each keeps its turn."""
    planes = _planes()
    first, second, third = planes
    Gui.Selection.clearSelection()
    vp, at = _row(third.Name)
    QTest.mouseClick(vp, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, at)  # the user's way: the row's double-click
    QTest.mouseDClick(vp, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, at)
    harness.pump(1500)
    assert s().sketches.editing() is None, "a double-click on a work plane started a sketch"
    d = dialog()
    assert d is not None and s().feature_session.feature is third, "no dialog for the third plane"
    assert d.field("turn_x").isVisible(), "no Turn row on the third plane"
    _drag_ring(0, 20.0)
    assert d.values()["turn_x"] == "20 °", d.values()["turn_x"]
    QTest.mouseClick(d.ok_button, QtCore.Qt.LeftButton)
    harness.pump(1200)
    assert abs(_tilt(third) - 50) < 1e-6, _tilt(third)  # 20° more than the second's 30°
    assert abs(_tilt(second) - 30) < 1e-6, _tilt(second)
    Gui.Selection.clearSelection()
    s().edit_feature(first)
    harness.pump(1200)
    d = dialog()
    assert d is not None, "no dialog for the first plane"
    _drag_ring(1, 15.0)
    assert d.values()["turn_y"] == "15 °", d.values()["turn_y"]
    QTest.mouseClick(d.ok_button, QtCore.Qt.LeftButton)
    harness.pump(1200)
    assert abs(_tilt(first) - 15) < 1e-6, _tilt(first)
    assert abs(_tilt(second) - 30) < 1e-6, _tilt(second)
    assert abs(_tilt(third) - 50) < 1e-6, _tilt(third)


def test_5_click_another_plane_moves_the_dialog_there():
    """The user: the rings move with the selected plane. The first plane's dialog open, a click on the third plane's
    row keeps the first as set and opens the third (its offset along its normal, its turn, the rings on it)."""
    first, second, third = _planes()
    Gui.Selection.clearSelection()
    s().edit_feature(first)
    harness.pump(1200)
    d = dialog()
    d.set_values({"turn_z": "10 °"})
    harness.pump(1500)
    vp, at = _row(third.Name)
    QTest.mouseClick(vp, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, at)
    harness.pump(2500)
    fs = s().feature_session
    assert fs is not None and fs.feature is third, ("the dialog is not on the third plane", fs and fs.feature.Name)
    assert fs.dialog.values()["turn_x"] == "20 °", fs.dialog.values()
    assert "* 3" in fs.dialog.values()["offset"], fs.dialog.values()["offset"]
    ring = s()._overlay
    assert ring is not None and ring.root is not None, "no rings on the third plane"
    g = third.getParentGeoFeatureGroup().getGlobalPlacement()
    assert (ring._frame[0] - g.multVec(third.Placement.Base)).Length < 1e-6, "the rings are not on the third plane"
    fs.dialog.set_values({"offset": "13 mm"})
    harness.pump(1500)
    QTest.mouseClick(fs.dialog.ok_button, QtCore.Qt.LeftButton)
    harness.pump(1200)
    assert s().feature_session is None
    assert work_turn(first)["turn_z"] == "10 °", work_turn(first)
    assert abs(third.AttachmentOffset.Base.z - 13) < 1e-6, third.AttachmentOffset.Base.z  # moved along its own normal


def work_turn(f):
    from incad.features import work
    return work.turn_text(doc(), f, "previous")


def test_9_cleanup():
    harness.pump(300)
    App.closeDocument(doc().Name)


harness.run([test_0_box, test_1_three_planes_in_one_go, test_2_edit_spaces_the_row, test_3_turn_a_plane_with_its_ring,
             test_4_turn_every_plane_of_the_row, test_5_click_another_plane_moves_the_dialog_there, test_9_cleanup])
