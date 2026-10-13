"""Assembly: the clicked part's DOF gizmo — easy to catch (screen space, 12 px), stays while the pointer goes from the
part to an arc outside it, the handle under the pointer lit; drag an arc to turn the part, an arrow to slide it."""
import math
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from pivy import coin  # noqa: E402,F401
from incad.qt import QtCore, QtGui, QtWidgets  # noqa: E402
from incad import actions  # noqa: E402
from incad.core import assembly, commands, prefs, safe, tree  # noqa: E402
from incad.features import constraints as C  # noqa: E402
from incad.ui import shell  # noqa: E402
from incad.ui.nav import to_coin  # noqa: E402
from headless.test_assembly import save_part  # noqa: E402

ST = {}
L, N = QtCore.Qt.LeftButton, QtCore.Qt.NoButton


def s():
    return shell.instance()


def doc():
    return App.getDocument(ST["asm"])


def obj(key):
    return doc().getObject(ST[key])


def rows():
    return {n.name: n.detail for n in tree.build(doc())[0].children if n.kind == "component"}


def fz(link, z):
    return "%s:Face%d" % (link.Name, [i + 1 for i, f in enumerate(link.LinkedObject.Shape.Faces)
                                      if abs(f.CenterOfMass.z - z) < 1e-6][0])


def view():
    return Gui.getDocument(ST["asm"]).ActiveView


def viewport():
    return view().graphicsView().viewport()


def screen_of(point):
    vp = viewport()
    x, y = view().getPointOnViewport(point)
    dpr = vp.devicePixelRatioF()
    return QtCore.QPointF(x / dpr, vp.height() - y / dpr)


def send(kind, pos, button, buttons):
    vp = viewport()
    glob = QtCore.QPointF(vp.mapToGlobal(pos.toPoint()))
    QtWidgets.QApplication.sendEvent(vp, QtGui.QMouseEvent(kind, pos, glob, button, buttons, QtCore.Qt.NoModifier))


def hover(pos, ms=150):
    send(QtCore.QEvent.MouseMove, pos, N, N)
    harness.pump(ms)


def click(pos):
    hover(pos, 300)
    send(QtCore.QEvent.MouseButtonPress, pos, L, L)
    harness.pump(60)
    send(QtCore.QEvent.MouseButtonRelease, pos, L, N)
    harness.pump(600)


def drag_path(points, release=True):
    """Press on the first point, move through the others, release on the last."""
    hover(points[0], 300)
    send(QtCore.QEvent.MouseButtonPress, points[0], L, L)
    harness.pump(100)
    for p in points[1:]:
        send(QtCore.QEvent.MouseMove, p, N, L)
        harness.pump(40)
    if release:
        send(QtCore.QEvent.MouseButtonRelease, points[-1], L, N)
        harness.pump(800)


def same(a, b):
    return a.isSame(b, 1e-7)


def temp_grounds():
    return len([j for j in assembly.joints(doc()) if hasattr(j, "ObjectToGround")])


def gizmo():
    d = s().dof_handles.drawn
    return d[1] if d is not None else None


def handle(kind):
    hs = s().dof_handles.drawn[2]
    return [(k, h) for k, h in enumerate(hs) if h.kind == kind][0]


def top_of(key):
    bb = obj(key).Shape.BoundBox
    return screen_of(App.Vector(bb.Center.x, bb.Center.y, bb.ZMax))


def hits_bar(pos):
    info = view().getObjectInfo(to_coin(viewport(), pos.x(), pos.y()))
    return bool(info) and (info.get("SubName") or "").split(".")[0] == ST["b"]


def select_bar():
    if gizmo() != ST["b"]:
        click(top_of("b"))
    assert gizmo() == ST["b"], ("the clicked bar shows its gizmo", gizmo())


def test_0_setup():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    ST["dir"] = tempfile.mkdtemp(prefix="incad_gui_handles_")
    for name, w, h, t in (("Plate", 60, 40, 10), ("Bar", 30, 6, 6)):
        d, ST[name] = save_part(ST["dir"], name, w, h, t)
        App.closeDocument(d.Name)
    d = actions.new_assembly("mm")
    d.saveAs(os.path.join(ST["dir"], "Asm.FCStd"))
    ST["asm"] = d.Name
    ST["p"] = s().assembly_place(ST["Plate"]).Name
    ST["b"] = s().assembly_place(ST["Bar"]).Name
    r = safe.run_safely("Mate", lambda: C.MATE.create(doc(), None, None, dict(
        C.MATE.defaults(doc(), None), first=fz(obj("p"), 10), second=fz(obj("b"), 0))), doc())
    assert r.ok, r.error
    view().viewIsometric()
    Gui.SendMsgToActiveView("ViewFit")
    s().schedule_refresh()
    harness.pump(1500)
    assert rows()[ST["b"]] == "DOF 3", rows()
    Gui.Selection.clearSelection()
    harness.pump(300)


def test_1_a_click_shows_the_gizmo():
    assert gizmo() is None
    click(top_of("b"))
    assert gizmo() == ST["b"], gizmo()
    assert s()._dof_glyphs is not None and s()._dof_glyphs.parts[ST["b"]] == (3, 5), "two slides and a turn"


def test_2_the_gizmo_stays_on_the_way_to_an_arc_outside_the_part():
    k, arc = handle("turn")
    outside = [p for p in arc.line if not hits_bar(screen_of(p))]
    assert outside, "a point of the arc is outside the bar on screen"
    target = screen_of(outside[len(outside) // 2])
    ST["arc_point"] = outside[len(outside) // 2]
    start = top_of("b")
    for i in range(1, 13):
        hover(QtCore.QPointF(start.x() + (target.x() - start.x()) * i / 12,
                             start.y() + (target.y() - start.y()) * i / 12), 80)
    harness.pump(700)
    assert gizmo() == ST["b"], "the gizmo is still shown"
    assert s()._dof_glyphs.lit == (ST["b"], k), ("the arc under the pointer is lit", s()._dof_glyphs.lit)
    assert viewport().cursor().shape() == QtCore.Qt.OpenHandCursor
    hover(QtCore.QPointF(target.x() + 40, target.y() + 40), 300)
    assert s()._dof_glyphs.lit is None and gizmo() == ST["b"], "off the arc: nothing lit, the gizmo stays"


def arc_path(arc, t0, turn_deg, offset_px=8, steps=24):
    """Screen points on the arc's circle from angle t0 (radians) through turn_deg, offset_px outside it."""
    c = screen_of(arc.point)
    out = []
    for i in range(steps + 1):
        t = t0 + math.radians(turn_deg) * i / steps
        p = screen_of(arc.point + (arc.u * math.cos(t) + arc.w * math.sin(t)) * arc.radius)
        dx, dy = p.x() - c.x(), p.y() - c.y()
        n = math.hypot(dx, dy) or 1
        out.append(QtCore.QPointF(p.x() + dx / n * offset_px, p.y() + dy / n * offset_px))
    return out


def arc_angle_of(arc, point):
    v = point - arc.point
    return math.atan2(v.dot(arc.w), v.dot(arc.u))


def test_3_drag_the_arc_a_quarter_turn():
    select_bar()
    b, p = obj("b"), obj("p")
    bb, bp = App.Placement(b.Placement), App.Placement(p.Placement)
    n0 = len(doc().UndoNames)
    _, arc = handle("turn")
    path = arc_path(arc, arc_angle_of(arc, ST["arc_point"]), 90)
    assert s().dof_handles.hit(view(), viewport(), path[0].x(), path[0].y()) is not None, "8 px off still catches"
    drag_path(path)
    rel = b.Placement.multiply(bb.inverse())
    angle = math.degrees(rel.Rotation.Angle)
    assert abs(angle - 90) < 4, ("a quarter turn", angle)
    assert abs(abs(rel.Rotation.Axis.z) - 1) < 1e-3, ("about the plate's normal", rel.Rotation.Axis)
    assert abs(b.Shape.BoundBox.ZMin - 10) < 1e-6, "still on the plate"
    assert same(p.Placement, bp), "the plate does not move"
    assert len(doc().UndoNames) == n0 + 1 and doc().UndoNames[0] == "Move part", doc().UndoNames[:3]
    assert temp_grounds() == 1, "no temporary ground left"
    assert not s().dof_handles.dragging() and Gui.getDocument(ST["asm"]).getInEdit() is None
    assert "Moved Bar" in s().status.texts()["message"], s().status.texts()
    assert gizmo() == ST["b"], "the gizmo stays for the next grab"
    commands.REGISTRY.run("edit.undo")
    harness.pump(800)
    assert same(b.Placement, bb), "Undo turns it back"


def test_4_drag_an_arrow_slides_along_it():
    select_bar()
    b = obj("b")
    bb = App.Placement(b.Placement)
    n0 = len(doc().UndoNames)
    k, arrow = handle("slide")
    size = s().dof_handles.drawn[3]
    a = screen_of(arrow.point + arrow.axis * (size * 0.85))  # beyond the arc (0.6 size), before the head
    z = screen_of(arrow.point + arrow.axis * (size * 0.85 + 10))
    dx, dy = z.x() - a.x(), z.y() - a.y()
    n = math.hypot(dx, dy)
    off = (-dy / n * 5, dx / n * 5)  # 5 px beside the arrow
    path = [QtCore.QPointF(a.x() + off[0] + dx * i / 16, a.y() + off[1] + dy * i / 16) for i in range(17)]
    assert s().dof_handles.hit(view(), viewport(), path[0].x(), path[0].y()) == k, "the press catches the arrow"
    drag_path(path)
    moved = b.Placement.Base - bb.Base
    assert (moved - arrow.axis * 10).Length < 0.5, ("10 mm along the arrow only", moved, arrow.axis)
    assert abs(moved.z) < 1e-6 and b.Placement.Rotation.isSame(bb.Rotation, 1e-7), "no other motion"
    assert len(doc().UndoNames) == n0 + 1 and doc().UndoNames[0] == "Move part", doc().UndoNames[:3]
    assert temp_grounds() == 1
    commands.REGISTRY.run("edit.undo")
    harness.pump(800)
    assert same(b.Placement, bb)


def test_5_a_press_on_the_part_off_the_handles_is_freecads_drag():
    select_bar()
    b = obj("b")
    bb = App.Placement(b.Placement)
    box = b.Shape.BoundBox
    spot = None
    for i in range(1, 15):
        for j in range(1, 6):
            q = screen_of(App.Vector(box.XMin + box.XLength * i / 15, box.YMin + box.YLength * j / 6, box.ZMax))
            if hits_bar(q) and s().dof_handles.hit(view(), viewport(), q.x(), q.y()) is None:
                spot = q
                break
        if spot is not None:
            break
    assert spot is not None, "a spot on the bar away from its handles"
    began = []
    real = s().asm_drag.begin
    s().asm_drag.begin = lambda *a: began.append(real(*a)) or began[-1]
    try:
        drag_path([QtCore.QPointF(spot.x() + 70 * i / 12, spot.y() - 50 * i / 12) for i in range(13)])
    finally:
        del s().asm_drag.begin
    assert began == [True], ("FreeCAD's own drag (asm_drag), as before", began)
    assert not same(b.Placement, bb), "it moved"
    assert doc().UndoNames[0] == "Move part" and temp_grounds() == 1
    commands.REGISTRY.run("edit.undo")
    harness.pump(800)


def test_6_a_command_ends_a_handle_drag_first():
    select_bar()
    b = obj("b")
    bb = App.Placement(b.Placement)
    n0 = len(doc().UndoNames)
    _, arc = handle("turn")
    path = arc_path(arc, arc_angle_of(arc, ST["arc_point"]), 45, steps=12)
    drag_path(path, release=False)
    assert s().dof_handles.dragging() and temp_grounds() > 0
    commands.REGISTRY.run("view.dof")  # any command
    harness.pump(500)
    assert not s().dof_handles.dragging(), "the command ended the drag"
    send(QtCore.QEvent.MouseButtonRelease, path[-1], L, N)
    harness.pump(500)
    assert temp_grounds() == 1 and not same(b.Placement, bb)
    assert len(doc().UndoNames) == n0 + 1 and doc().UndoNames[0] == "Move part"
    commands.REGISTRY.run("view.dof")
    commands.REGISTRY.run("edit.undo")
    harness.pump(800)
    assert same(b.Placement, bb)


def test_7_a_click_on_empty_space_hides_the_gizmo():
    select_bar()
    click(QtCore.QPointF(5, 5))
    assert gizmo() is None
    assert s()._dof_glyphs is None or ST["b"] not in s()._dof_glyphs.parts, "no glyph left"


def test_8_no_handle_while_a_constraint_dialog_is_open():
    select_bar()
    b = obj("b")
    bb = App.Placement(b.Placement)
    _, arc = handle("turn")
    path = arc_path(arc, arc_angle_of(arc, ST["arc_point"]), 90, offset_px=0)
    commands.REGISTRY.run("constrain.flush")
    harness.pump(800)
    assert s().feature_session is not None
    s().dof_display_changed()
    assert not s().dof_handles.press(view(), viewport(), path[0].x(), path[0].y()), "no handle grabbed"
    drag_path(path)
    assert not s().dof_handles.dragging() and same(b.Placement, bb), "the part does not turn"
    s()._close_feature_session(cancel=True)
    harness.pump(800)
    assert same(b.Placement, bb) and temp_grounds() == 1


def test_9_cleanup():
    for name in list(App.listDocuments()):
        App.closeDocument(name)
    shutil.rmtree(ST["dir"], ignore_errors=True)


TESTS = [test_0_setup, test_1_a_click_shows_the_gizmo, test_2_the_gizmo_stays_on_the_way_to_an_arc_outside_the_part,
         test_3_drag_the_arc_a_quarter_turn, test_4_drag_an_arrow_slides_along_it,
         test_5_a_press_on_the_part_off_the_handles_is_freecads_drag, test_6_a_command_ends_a_handle_drag_first,
         test_7_a_click_on_empty_space_hides_the_gizmo, test_8_no_handle_while_a_constraint_dialog_is_open]
harness.run(TESTS + [test_9_cleanup])
