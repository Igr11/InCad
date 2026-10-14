"""Move Face in the real window: the dialog from a selected top face, a typed distance, the drag arrow on the face
(screen-space press on its head, move, release) with the distance shown at it, one undo step on OK, the edit (a
re-pick lands on the base shape), a command that ends a drag, a refused distance (the arrow stays at the last good
one) and another tab's view (its presses go to the DOF gizmo)."""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from pivy import coin  # noqa: E402,F401
from PySide6.QtTest import QTest  # noqa: E402
from incad.qt import QtCore, QtGui, QtWidgets  # noqa: E402
from incad.core import commands, document, prefs  # noqa: E402
from incad.ui import dof_handles, shell  # noqa: E402
from incad.ui.nav import to_coin  # noqa: E402
import headless.util as util  # noqa: E402

ST = {}
L, N = QtCore.Qt.LeftButton, QtCore.Qt.NoButton


def s():
    return shell.instance()


def doc():
    return App.getDocument(ST["doc"])


def body():
    return document.primary_body(doc())


def dialog():
    fs = s().feature_session
    return fs.dialog if fs is not None else None


def ok():
    QTest.mouseClick(dialog().ok_button, QtCore.Qt.LeftButton)
    harness.pump(1500)


def view():
    return Gui.getDocument(ST["doc"]).ActiveView


def viewport():
    return view().graphicsView().viewport()


def screen_of(point):
    x, y = dof_handles.screen(view(), viewport(), point)
    return QtCore.QPointF(x, y)


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


def press(pos):
    hover(pos, 300)
    send(QtCore.QEvent.MouseButtonPress, pos, L, L)
    ST["at"] = QtCore.QPointF(pos)
    harness.pump(100)


def move_by(dx, dy, steps=8, ms=40):
    start = ST["at"]
    for k in range(1, steps + 1):
        p = QtCore.QPointF(start.x() + dx * k / steps, start.y() + dy * k / steps)
        send(QtCore.QEvent.MouseMove, p, N, L)
        harness.pump(ms)
    ST["at"] = QtCore.QPointF(start.x() + dx, start.y() + dy)


def release():
    send(QtCore.QEvent.MouseButtonRelease, ST["at"], L, N)


def top_face(obj):
    z = obj.Shape.BoundBox.ZMax
    return "Face%d" % [i + 1 for i, f in enumerate(obj.Shape.Faces)
                       if abs(f.CenterOfMass.z - z) < 1e-6 and abs(f.normalAt(0, 0).z - 1) < 1e-6][0]


def select_top():
    tip = body().Tip
    Gui.Selection.clearSelection()
    Gui.Selection.addSelection(doc().Name, tip.Name, top_face(tip))
    harness.pump(200)


class SelectionLog:
    """What FreeCAD's selection was told, for a failure message."""
    def __init__(self):
        self.events = []

    def addSelection(self, doc, obj, sub, pnt):
        self.events.append(("add", obj, sub))

    def clearSelection(self, doc):
        self.events.append(("clear",))


def clear_selection(timeout_ms=3000):
    """Empty the selection and wait until it stays empty."""
    end, quiet = time.time() + timeout_ms / 1000.0, 0
    while time.time() < end:
        if Gui.Selection.getSelectionEx(doc().Name):
            Gui.Selection.clearSelection()
            quiet = 0
        else:
            quiet += 1
            if quiet >= 3:
                return
        harness.pump(100)
    raise AssertionError("the selection does not stay empty: %s"
                         % [(x.ObjectName, x.SubElementNames) for x in Gui.Selection.getSelectionEx(doc().Name)])


def lit_cursor():
    return viewport().cursor().shape() in (QtCore.Qt.OpenHandCursor, QtCore.Qt.ClosedHandCursor)


def set_distance(text):
    w = dialog().field("distance")
    w.setText(text)
    w.editingFinished.emit()


def arrow_head_screen():
    a = s()._overlay
    point, normal, size = a._geom
    return screen_of(point + normal * (a._offset + size))


def test_0_setup():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    d = App.newDocument("MoveFaceGui")
    ST["doc"] = d.Name
    harness.pump(500)
    _, pad = util.padded_part(d, 10, incad=True)
    ST["pad"] = pad.Name
    harness.pump(300)
    view().viewIsometric()
    view().fitAll()
    harness.pump(500)
    assert s()._overlay is None


def test_1_dialog_and_typed_distance():
    ST["undo"] = len(doc().UndoNames)  # FreeCAD lists the dialog's open step among UndoNames already
    select_top()
    commands.REGISTRY.run("feature.move_face")
    harness.pump(1500)
    assert dialog() is not None and dialog().values()["faces"], dialog().values()
    # the user: it starts at 0 mm — nothing moved, no red "too large" on a small part
    assert dialog().values()["distance"] == "0 mm", dialog().values()
    assert not dialog().error_text(), dialog().error_text()
    set_distance("5 mm")
    harness.pump(1500)
    assert abs(body().Shape.BoundBox.ZMax - 15) < 1e-6, body().Shape.BoundBox
    arrow = s()._overlay
    assert arrow is not None and arrow.label_text() == "5 mm", arrow.label_text() if arrow else None
    assert s().navigator.handle_hook is arrow
    assert arrow.root is not None and view().getSceneGraph().findChild(arrow.root) >= 0, "the arrow is drawn"
    assert abs(arrow._geom[0].z - 15) < 1e-6 and abs(arrow._geom[1].z - 1) < 1e-9, arrow._geom
    set_distance("3 mm")
    harness.pump(1500)
    assert arrow.label_text() == "3 mm" and abs(arrow._geom[0].z - 13) < 1e-6, (arrow.label_text(), arrow._geom)
    set_distance("-3 mm")
    harness.pump(1500)
    # a plain "-": the view's text drops the typographic minus (U+2212), and −3 mm then showed as "3 mm"
    assert arrow.label_text() == "-3 mm" and dialog().values()["distance"] == "-3 mm", arrow.label_text()
    assert arrow.label_text().isascii(), arrow.label_text()
    assert abs(arrow._geom[0].z - 7) < 1e-6 and abs(body().Shape.BoundBox.ZMax - 7) < 1e-6, \
        (arrow._geom, body().Shape.BoundBox)
    set_distance("5 mm")
    harness.pump(1500)


def test_2_drag_the_arrow_changes_the_distance_and_shows_it():
    arrow = s()._overlay
    head = arrow_head_screen()
    faces = dialog().values()["faces"]
    hover(head)
    assert arrow.lit and lit_cursor(), (arrow.lit, viewport().cursor().shape())
    hover(QtCore.QPointF(viewport().width() - 5, viewport().height() - 5))
    assert not arrow.lit and not lit_cursor(), (arrow.lit, viewport().cursor().shape())
    click(head)  # a plain click on the arrow is neither a drag nor a pick of the face under it
    harness.pump(800)
    assert not arrow.dragging() and dialog().values()["faces"] == faces, dialog().values()
    assert dialog().values()["distance"] == "5 mm", dialog().values()
    dialog().set_values({"extent": "to"})  # To: the arrow shows, but can't be dragged
    assert not arrow.press(view(), viewport(), head.x(), head.y()) and not arrow.dragging()
    dialog().set_values({"extent": "distance"})
    fs = s().feature_session
    previews, shown_before = [0], fs.on_previewed
    fs.on_previewed = lambda: (previews.__setitem__(0, previews[0] + 1), shown_before())
    try:
        press(head)
        move_by(0, -40, steps=12, ms=90)  # a steady drag over about a second
        during = previews[0]
        harness.pump(300)
    finally:
        fs.on_previewed = shown_before
    assert during >= 2, ("the preview follows a steady drag (throttled, not only when it rests)", during)
    assert arrow.dragging()
    shown = arrow.label_text()
    t = arrow._nodes["shift"].translation.getValue()
    assert abs(arrow._geom[0].z + t[2] - (10 + float(shown.split()[0]))) < 1e-6, (arrow._geom, t[2], shown)
    assert shown.endswith("mm") and shown != "5 mm", shown   # the label follows the pointer during the drag
    assert float(shown.split()[0]) > 5, shown  # up on the screen = outward
    names = list(doc().UndoNames)
    release()
    harness.pump(1500)
    assert not arrow.dragging()
    assert dialog().values()["distance"] == shown, (dialog().values()["distance"], shown)
    assert abs(body().Shape.BoundBox.ZMax - (10 + float(shown.split()[0]))) < 1e-6, body().Shape.BoundBox
    assert arrow.label_text() == shown, arrow.label_text()  # it stays while the dialog is open
    assert list(doc().UndoNames) == names, "the drag is no undo step of its own"
    sel = [(x.ObjectName, x.SubElementNames) for x in Gui.Selection.getSelectionEx(doc().Name)]
    assert dialog().values()["faces"] and not dialog().error_text(), (dialog().values(), dialog().error_text(), sel)
    ST["shown"] = shown


def test_3_ok_is_one_undo_step_and_the_arrow_goes():
    n = ST["undo"]
    root = s()._overlay.root
    ok()
    harness.pump(1200)
    assert doc().UndoNames[0] == "Move Face" and len(doc().UndoNames) == n + 1, doc().UndoNames
    assert s()._overlay is None
    assert s().navigator.handle_hook is s().dof_handles
    assert view().getSceneGraph().findChild(root) < 0, "the arrow is gone from the view"


def test_4_edit_reopens_with_the_values_and_modes_switch():
    mf = body().Tip
    shell.edit_feature(mf)
    harness.pump(1200)
    assert dialog().values()["mode"] == "inventor"
    assert dialog().values()["distance"] == ST["shown"], dialog().values()
    assert s()._overlay is not None and s()._overlay.label_text() == ST["shown"]
    # a new face pick during the edit lands on the base shape (shown while picking), never on the Move Face itself
    base = mf.BaseFeature
    dialog().set_active_pick("faces")
    harness.pump(500)
    assert base.Visibility and not mf.Visibility, (base.Visibility, mf.Visibility)
    dialog().set_pick("faces", "")
    harness.pump(800)  # its preview (no faces: an error) is done
    clear_selection()
    watch = SelectionLog()
    Gui.Selection.addObserver(watch)
    try:
        click(screen_of(App.Vector(4, 3, 10)))
        harness.pump(1500)
    finally:
        Gui.Selection.removeObserver(watch)
    faces = dialog().values()["faces"]
    sel = [(x.ObjectName, x.SubElementNames) for x in Gui.Selection.getSelectionEx(doc().Name)]
    info = view().getObjectInfo(to_coin(viewport(), *dof_handles.screen(view(), viewport(), App.Vector(4, 3, 10))))
    assert faces.startswith(base.Name + ":Face") and mf.Name not in faces, (faces, sel, info, dialog().error_text(),
                                                                          dialog().active_pick(), watch.events)
    assert faces == "%s:%s" % (base.Name, top_face(base)), faces
    dialog().set_active_pick(None)
    harness.pump(800)
    dialog().set_values({"mode": "step"})
    s().feature_session._changed(dialog().values())
    harness.pump(1500)
    assert not dialog().error_text(), dialog().error_text()
    s().feature_session.cancel()
    harness.pump(900)
    assert s()._overlay is None and s().navigator.handle_hook is s().dof_handles


def test_5_a_command_ends_the_drag():
    select_top()
    commands.REGISTRY.run("feature.move_face")
    harness.pump(1500)
    arrow = s()._overlay
    press(arrow_head_screen())
    move_by(0, -20)
    harness.pump(300)
    assert arrow.dragging()
    commands.REGISTRY.run("view.zoom_all")
    harness.pump(500)
    assert not arrow.dragging(), "the command ended the drag"
    assert dialog() is not None and dialog().values()["distance"].endswith("mm")
    release()
    harness.pump(300)
    s().feature_session.cancel()
    harness.pump(900)
    assert s()._overlay is None


def test_6_a_refused_distance_leaves_the_arrow_at_the_last_good_one():
    z0 = body().Shape.BoundBox.ZMax
    select_top()
    commands.REGISTRY.run("feature.move_face")
    harness.pump(1500)
    set_distance("5 mm")
    harness.pump(1500)
    arrow = s()._overlay
    assert abs(arrow._geom[0].z - (z0 + 5)) < 1e-6, (arrow._geom, z0)
    set_distance("-40 mm")  # through the part: refused
    harness.pump(1500)
    assert dialog().error_text(), dialog().values()
    arrow.refresh()  # as a theme switch redraws it
    assert abs(arrow._geom[0].z - (z0 + 5)) < 1e-6, (arrow._geom, z0)
    assert arrow.label_text() == "5 mm", arrow.label_text()
    set_distance("5 mm")
    harness.pump(1500)


class HandlesLog:
    """A stand-in for the shell's DOF gizmo hook: what the arrow handed it."""
    def __init__(self):
        self.calls, self.drag = [], False

    def hover(self, view, viewport, x, y):
        self.calls.append(("hover", viewport))
        return False

    def press(self, view, viewport, x, y):
        self.calls.append(("press", viewport))
        self.drag = True
        return True

    def move(self, x, y):
        self.calls.append(("move",))

    def release(self):
        self.calls.append(("release",))
        self.drag = False
        return False

    def dragging(self):
        return self.drag

    def finish(self, moved_ok=True, closing=False):
        self.drag = False


def test_7_other_views_go_to_the_dof_gizmo():
    """While the dialog is open in this tab the gizmo of an assembly in another tab still gets its hovers and
    presses (the arrow is the navigator's handle hook)."""
    arrow = s()._overlay
    assert arrow is not None and s().navigator.handle_hook is arrow
    other = App.newDocument("MoveFaceOther")
    harness.pump(800)
    vp2 = Gui.getDocument(other.Name).ActiveView.graphicsView().viewport()
    real, log_ = s().dof_handles, HandlesLog()
    s().dof_handles = log_
    try:
        at = QtCore.QPointF(vp2.width() / 2.0, vp2.height() / 2.0)
        glob = QtCore.QPointF(vp2.mapToGlobal(at.toPoint()))
        ev = lambda kind, b, bs: QtWidgets.QApplication.sendEvent(
            vp2, QtGui.QMouseEvent(kind, at, glob, b, bs, QtCore.Qt.NoModifier))
        ev(QtCore.QEvent.MouseMove, N, N)
        harness.pump(150)
        ev(QtCore.QEvent.MouseButtonPress, L, L)
        harness.pump(100)
        assert arrow.dragging(), log_.calls  # the gizmo's drag is the hook's drag
        at = QtCore.QPointF(at.x() + 30, at.y())
        ev(QtCore.QEvent.MouseMove, N, L)
        harness.pump(100)
        ev(QtCore.QEvent.MouseButtonRelease, L, N)
        harness.pump(300)
        kinds = [c[0] for c in log_.calls]
        assert kinds[:2] == ["hover", "press"] and "move" in kinds and kinds[-1] == "release", log_.calls
        assert all(c[1] is vp2 for c in log_.calls if len(c) > 1), log_.calls
        assert not arrow.dragging() and not arrow.lit
    finally:
        s().dof_handles = real
        App.closeDocument(other.Name)
        harness.pump(800)
    s().feature_session.cancel()
    harness.pump(900)
    assert s()._overlay is None


def test_8_finish_move_in_the_right_click_menu():
    """The user: the right-click menu has "Finish move" on top (N) while the dialog is open, doing the same as OK."""
    height = body().Shape.BoundBox.ZMax
    n = len(doc().UndoNames)
    select_top()
    commands.REGISTRY.run("feature.move_face")
    harness.pump(1500)
    set_distance("2 mm")
    harness.pump(1500)
    vp = viewport()
    local = QtCore.QPoint(8, 8)  # empty space in a corner of the view
    # read the menu at once: a popup may close by itself when the test window lacks the focus
    menu = s()._open_marking_menu(view(), vp, local, vp.mapToGlobal(local), False)
    top = menu.button("N") if menu is not None else None
    assert top is not None and top.text() == "Finish move", (menu and menu._slot_ids, s()._session_finish(),
                                                             s().registry.has("feature.finish_move"), s().menu_kind)
    assert menu.extra_button("Finish move") is None, "only on top, not again below the list"
    top.click()
    harness.pump(1500)
    assert s().feature_session is None, "the dialog closed as with OK"
    assert doc().UndoNames[0] == "Move Face" and len(doc().UndoNames) == n + 1, doc().UndoNames
    assert abs(body().Shape.BoundBox.ZMax - (height + 2)) < 1e-6, body().Shape.BoundBox.ZMax
    # no dialog open: no Finish move
    menu = s()._open_marking_menu(view(), vp, local, vp.mapToGlobal(local), False)
    assert menu is not None and (menu.button("N") is None or menu.button("N").text() != "Finish move")
    menu.close()
    harness.pump(300)


def test_8b_to_takes_an_edge_clicked_in_the_view():
    """The user: Move Face up to an edge too — with To active, a click on an edge fills To."""
    if s().feature_session is not None:  # an earlier test left its dialog open: start clean
        s().feature_session.cancel()
        harness.pump(900)
    zmax = body().Shape.BoundBox.ZMax  # the shape before the move: what the view shows while To picks
    select_top()
    commands.REGISTRY.run("feature.move_face")
    harness.pump(1500)
    dialog().set_values({"extent": "to"})
    s().feature_session._changed(dialog().values())
    harness.pump(800)
    dialog().set_active_pick("to")
    harness.pump(500)
    clear_selection()
    watch = SelectionLog()
    Gui.Selection.addObserver(watch)
    p = App.Vector(10, 0, zmax)
    try:
        click(screen_of(p))  # the middle of the top front edge
        harness.pump(1500)
    finally:
        Gui.Selection.removeObserver(watch)
    to = dialog().values()["to"]
    info = view().getObjectInfo(to_coin(viewport(), *dof_handles.screen(view(), viewport(), p)))
    assert ":Edge" in to, (to, dialog().error_text(), dialog().active_pick(), info, watch.events, zmax)
    assert not dialog().error_text(), dialog().error_text()  # its own top edge: level with the face, no move
    s().feature_session.cancel()
    harness.pump(900)


def test_9_cleanup():
    App.closeDocument(ST["doc"])
    harness.pump(500)


harness.run([test_0_setup, test_1_dialog_and_typed_distance, test_2_drag_the_arrow_changes_the_distance_and_shows_it,
             test_3_ok_is_one_undo_step_and_the_arrow_goes, test_4_edit_reopens_with_the_values_and_modes_switch,
             test_5_a_command_ends_the_drag, test_6_a_refused_distance_leaves_the_arrow_at_the_last_good_one,
             test_7_other_views_go_to_the_dof_gizmo, test_8_finish_move_in_the_right_click_menu,
             test_8b_to_takes_an_edge_clicked_in_the_view, test_9_cleanup])
