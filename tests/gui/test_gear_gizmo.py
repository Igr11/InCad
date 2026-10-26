"""The assembly's gizmo on a Gear while its dialog is open (the user: arrows as in the assembly, moving with
dimensions): dragging the X arrow sets Offset X in whole mm and moves the gear; dragging the arc sets Turn in 5°."""
import math
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from incad.qt import QtCore, QtGui, QtWidgets, viewport_of  # noqa: E402
from incad.core import commands, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402
from incad.ui import dof_handles as dh  # noqa: E402
from incad.ui.gear_gizmo import GearGizmo  # noqa: E402

L, N = QtCore.Qt.LeftButton, QtCore.Qt.NoButton


def s():
    return shell.instance()


def dialog():
    fs = s().feature_session
    return fs.dialog if fs is not None else None


def vp():
    return viewport_of(Gui.ActiveDocument.ActiveView)


def send(kind, pos, button, buttons):
    v = vp()
    QtWidgets.QApplication.sendEvent(v, QtGui.QMouseEvent(kind, pos, QtCore.QPointF(v.mapToGlobal(pos.toPoint())),
                                                          button, buttons, QtCore.Qt.NoModifier))


def drag(points):
    send(QtCore.QEvent.MouseMove, points[0], N, N)
    harness.pump(200)
    send(QtCore.QEvent.MouseButtonPress, points[0], L, L)
    harness.pump(60)
    for p in points[1:]:
        send(QtCore.QEvent.MouseMove, p, N, L)
        harness.pump(120)
    send(QtCore.QEvent.MouseButtonRelease, points[-1], L, N)
    harness.pump(1200)


def on_screen(v):
    x, y = dh.screen(Gui.ActiveDocument.ActiveView, vp(), v)
    return QtCore.QPointF(x, y)


def gizmo():
    g = s()._overlay
    assert isinstance(g, GearGizmo), g
    return g


def test_0_a_gear_dialog_shows_the_gizmo():
    prefs.set_remember_new_choice(True)
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    Gui.ActiveDocument.ActiveView.viewIsometric()
    commands.REGISTRY.run("feature.gear")
    harness.pump(1500)
    Gui.SendMsgToActiveView("ViewFit")
    harness.pump(600)
    gizmo().refresh()
    assert len(gizmo().handles) == 6, gizmo().handles  # X, Y, Z arrows; arcs round Z (Turn), X, Y
    f = s().feature_session.feature
    assert gizmo().size < f.Shape.BoundBox.XLength / 2, "smaller than the gear (the user)"
    from incad.ui import gear_gizmo as gg
    colours = gizmo().colours()  # the user: all one colour, too small, hard to hold
    assert len({colours[i] for i in range(3)}) == 3, colours  # X, Y, Z arrows in three colours
    assert {colours[3], colours[4], colours[5]} == {colours[0], colours[1], colours[2]}, colours  # arcs: their axes
    width = max(f.Shape.BoundBox.XLength, f.Shape.BoundBox.YLength)
    assert gg.GRAB_PX > 12 and gizmo().size > 0.3 * width, (gizmo().size, width)  # big enough to hold
    if os.environ.get("INNCAD_SHOT"):
        Gui.ActiveDocument.ActiveView.saveImage(os.environ["INNCAD_SHOT"], 1000, 700, "Current")
    # the long dialog fits the view: its fields scroll, the ▲▼ stay in sight, OK is on screen (the user)
    d = dialog()
    area = d._fields_area
    step = d._steppers["module"][1]
    assert step.mapTo(area.viewport(), step.rect().topRight()).x() <= area.viewport().width()
    holder = d.parentWidget()
    assert d.ok_button.mapTo(holder, d.ok_button.rect().bottomLeft()).y() <= holder.height(), (
        d.geometry(), holder.height())


def test_1_the_x_arrow_sets_offset_x_in_whole_mm():
    g = gizmo()
    h = g.handles[0]  # the X slide
    a = on_screen(h.point + h.axis * (g.size * 0.6))
    b = on_screen(h.point + h.axis * (g.size * 0.6 + 12.3))  # 12.3 mm further along X
    drag([a, QtCore.QPointF((a.x() * 3 + b.x()) / 4, (a.y() * 3 + b.y()) / 4), b])
    value = dialog().values()["offset_x"]
    mm = float(value.split()[0])
    assert mm == round(mm) and 10 <= mm <= 14, value
    f = s().feature_session.feature
    App.ActiveDocument.recompute()
    assert abs(f.Shape.BoundBox.Center.x - mm) < 0.5, (f.Shape.BoundBox.Center, value)


def test_2_the_arc_sets_the_turn_in_5_degrees():
    g = gizmo()
    h = g.handles[3]  # the turn
    pts = [on_screen(h.point + (h.u * math.cos(t) + h.w * math.sin(t)) * h.radius)
           for t in [math.radians(a) for a in (10, 20, 30, 40, 50)]]
    drag(pts)
    value = dialog().values()["turn"]
    deg = float(value.replace("°", "").split()[0])
    assert deg % 5 == 0 and 25 <= abs(deg) <= 55, value


def arc_drag(h):
    pts = [on_screen(h.point + (h.u * math.cos(t) + h.w * math.sin(t)) * h.radius)
           for t in [math.radians(a) for a in (10, 20, 30, 40, 50)]]
    drag(pts)


def test_3_the_x_arc_tilts_it():
    g = gizmo()
    arc_drag(g.handles[4])  # round X
    value = dialog().values()["rotate_x"]
    deg = float(value.replace("°", "").split()[0])
    assert deg % 5 == 0 and 25 <= abs(deg) <= 55, value


def test_4_a_placed_gear_selected_has_its_gizmo():
    """The user: the gizmo was gone once the gears were placed."""
    from incad.features import gear
    s().feature_session.ok()
    harness.pump(1500)
    assert s().feature_session is None
    doc = App.ActiveDocument
    lead = next(o for o in doc.Objects if gear.is_gear(o) and gear.second_of(o) is not None)
    before = lead.OffsetX.Value
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc.Name, lead.Name)
    harness.pump(800)
    g = s()._gear_gizmo
    assert isinstance(g, GearGizmo) and len(g.handles) == 6, g
    h = g.handles[1]  # the Y slide
    a = on_screen(h.point + h.axis * (g.size * 0.6))
    b = on_screen(h.point + h.axis * (g.size * 0.6 + 7.4))
    drag([a, QtCore.QPointF((a.x() + b.x()) / 2, (a.y() + b.y()) / 2), b])
    moved = lead.OffsetY.Value
    assert moved == round(moved) and 5 <= moved <= 9, moved
    assert lead.OffsetX.Value == before
    second = gear.second_of(lead)
    assert lead.Shape.common(second.Shape).Volume < 0.05, "the pair moved together"
    doc.undo()
    doc.recompute()
    harness.pump(600)
    assert abs(lead.OffsetY.Value) < 1e-9, "one undo step"


def test_9_cleanup():
    if s().feature_session is not None:
        s().feature_session.cancel()
        harness.pump(600)
    App.closeDocument(App.ActiveDocument.Name)
    harness.pump(400)


harness.run([test_0_a_gear_dialog_shows_the_gizmo, test_1_the_x_arrow_sets_offset_x_in_whole_mm,
             test_2_the_arc_sets_the_turn_in_5_degrees, test_3_the_x_arc_tilts_it,
             test_4_a_placed_gear_selected_has_its_gizmo, test_9_cleanup])
