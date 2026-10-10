"""Hide / Show for chosen origin items and unused sketches: from the tree's menu, on a multi-selection, Show All /
Hide All, the plane pick restoring the choice, a consumed sketch refused, a right click on a shown plane."""
import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from incad.qt import QtCore, QtGui, QtWidgets  # noqa: E402
from incad.core import commands, prefs  # noqa: E402
from incad.ui import shell  # noqa: E402
from incad.ui.browser import STATE_ROLE  # noqa: E402
import headless.util as util  # noqa: E402


def _send(kind, pos, button, buttons):
    vp = Gui.ActiveDocument.ActiveView.graphicsView().viewport()
    types = {"press": QtCore.QEvent.MouseButtonPress, "release": QtCore.QEvent.MouseButtonRelease,
             "move": QtCore.QEvent.MouseMove}
    ev = QtGui.QMouseEvent(types[kind], pos, QtCore.QPointF(vp.mapToGlobal(pos.toPoint())), button, buttons,
                           QtCore.Qt.NoModifier)
    QtWidgets.QApplication.sendEvent(vp, ev)
    harness.pump(80)


def _body():
    from incad.core import document
    return document.primary_body(App.ActiveDocument)


def _xy():
    from incad.core import document
    return [o for o in document.origin_items(_body()) if o.Role == "XY_Plane"][0]


def test_0_part():
    prefs.set_remember_new_choice(True)
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    body = _body()
    sk = util.add_rect_sketch(body)
    sk.AttachmentOffset = App.Placement(App.Vector(30, 30, 0), App.Rotation())  # the pad away from the origin:
    pad = util.add_pad(body, sk, 10)                                             # FreeCAD draws the planes 2 mm
    body.Tip = pad
    App.ActiveDocument.recompute()
    from incad.core import document
    document.show_result(body)
    shell.instance().schedule_refresh()
    harness.pump(600)
    from incad.core import document
    assert not document.is_shown(_xy()), "a new part's planes start hidden (the Origin group is)"


def test_1_tree_menu_hide_show_on_a_plane():
    sh = shell.instance()
    xy = _xy()
    sh.browser.markingMenuRequested.emit(xy.Name, QtCore.QPoint(400, 400))
    harness.pump(300)
    assert sh.menu_kind == "origin", sh.menu_kind
    sh.marking_menu.close()
    harness.pump(200)
    r = commands.REGISTRY.run("view.toggle_visibility")  # the target is the row the menu was opened on
    assert r.ok, r.error
    harness.pump(400)
    from incad.core import document
    assert document.is_shown(xy)
    assert not any(document.is_shown(o) for o in document.origin_items(_body()) if o is not xy), "only the chosen plane"
    assert sh.browser.item_by_label("XY Plane").data(0, STATE_ROLE) == ""
    commands.REGISTRY.run("view.toggle_visibility")
    harness.pump(400)
    assert not document.is_shown(xy)
    assert sh.browser.item_by_label("XY Plane").data(0, STATE_ROLE) == "hidden"


def _click_row(label, modifier=QtCore.Qt.NoModifier):
    from PySide6.QtTest import QTest
    b = shell.instance().browser
    item = b.item_by_label(label)
    parent = item.parent()
    while parent is not None:
        parent.setExpanded(True)
        parent = parent.parent()
    harness.pump(100)
    QTest.mouseClick(b.tree.viewport(), QtCore.Qt.LeftButton, modifier, b.tree.visualItemRect(item).center())
    harness.pump(400)


def test_2_two_selected_axes_toggle_together():
    sh = shell.instance()
    from incad.core import context
    context.set_target(None)
    _click_row("X Axis")
    _click_row("Y Axis", QtCore.Qt.ControlModifier)  # Cmd-click on macOS: adds the row
    assert sh.browser.selected_names() == ["X_Axis", "Y_Axis"], sh.browser.selected_names()
    assert sorted(s.ObjectName for s in Gui.Selection.getSelectionEx()) == ["X_Axis", "Y_Axis"]
    r = commands.REGISTRY.run("view.toggle_visibility")
    assert r.ok, r.error
    harness.pump(400)
    from incad.core import document
    doc = App.ActiveDocument
    assert document.is_shown(doc.getObject("X_Axis")) and document.is_shown(doc.getObject("Y_Axis"))
    assert not document.is_shown(doc.getObject("Z_Axis"))
    sh.browser.tree.clearSelection()


def test_3_show_all_and_hide_all():
    from incad.core import document
    commands.REGISTRY.run("view.origin_show_all")
    harness.pump(300)
    items = document.origin_items(_body())
    assert all(document.is_shown(o) for o in items)
    commands.REGISTRY.run("view.origin_hide_all")
    harness.pump(300)
    assert not any(document.is_shown(o) for o in items)


def test_4_plane_pick_restores_the_choice():
    from incad.core import document
    sh = shell.instance()
    xy = _xy()
    document.set_visibility([xy], True)
    commands.REGISTRY.run("sketch.start")
    harness.pump(600)
    assert all(document.is_shown(o) for o in document.origin_items(_body())), "the pick shows every plane"
    sh._on_escape()
    harness.pump(600)
    items = document.origin_items(_body())
    assert document.is_shown(xy) and not any(document.is_shown(o) for o in items if o is not xy), \
        [(o.Role, document.is_shown(o)) for o in items]


def test_5_consumed_sketch_can_be_shown_and_hidden():
    from incad.core import context
    sh = shell.instance()
    Gui.Selection.clearSelection()
    sh.browser.tree.clearSelection()
    context.set_target("Sketch")
    sk = App.ActiveDocument.getObject("Sketch")
    assert not sk.Visibility
    r = commands.REGISTRY.run("view.toggle_visibility")
    assert r.ok, r.error
    harness.pump(400)
    assert sk.Visibility, "a feature's sketch shown by choice"
    assert sh.browser.item_by_label("Sketch").data(0, STATE_ROLE) == ""
    r = commands.REGISTRY.run("view.toggle_visibility")
    assert r.ok, r.error
    harness.pump(400)
    assert not sk.Visibility
    assert sh.browser.item_by_label("Sketch").data(0, STATE_ROLE) == "hidden"
    context.set_target(None)


def test_6_right_click_on_a_visible_plane_in_the_view_opens_the_origin_menu():
    from incad.core import context, document
    sh = shell.instance()
    context.set_target(None)
    xy = _xy()
    document.set_visibility([xy], True)
    sh.schedule_refresh()
    harness.pump(400)
    Gui.SendMsgToActiveView("ViewFit")
    harness.pump(400)
    view = Gui.ActiveDocument.ActiveView
    vp = view.graphicsView().viewport()
    hit = None
    for x, y in ((1.2, 1.2), (1.5, 0.8), (0.8, 1.5), (2.0, 2.0)):  # inside FreeCAD's small drawn plane (0.3..2.4 mm)
        sx, sy = view.getPointOnViewport(App.Vector(x, y, 0))
        info = view.getObjectInfo((int(sx), int(sy)))
        if info and info["Object"] == xy.Name:
            hit = (sx, sy)
            break
    assert hit is not None, "the shown XY plane is under one of the probe points"
    dpr = vp.devicePixelRatioF()
    pos = QtCore.QPointF(hit[0] / dpr, vp.height() - hit[1] / dpr)
    _send("press", pos, QtCore.Qt.RightButton, QtCore.Qt.RightButton)
    _send("release", pos, QtCore.Qt.RightButton, QtCore.Qt.NoButton)
    harness.pump(300)
    assert sh.menu_kind == "origin", sh.menu_kind
    assert context.target() == xy.Name
    sh.marking_menu.close()
    harness.pump(200)
    document.set_visibility([xy], False)


def test_7_right_click_on_a_work_plane_in_the_view_offers_hide_show():
    """A work plane (PartDesign::Plane) is a plane too: its RMB menu in the view has Hide / Show, and the command
    hides it; the tree dims its row; a second Hide / Show from the row shows it again."""
    from incad.core import context, document
    sh = shell.instance()
    context.set_target(None)
    body = _body()
    wp = body.newObject("PartDesign::Plane", "WorkPlane")
    wp.Placement = App.Placement(App.Vector(0, 0, 25), App.Rotation())  # above the pad, in the clear
    App.ActiveDocument.recompute()
    sh.schedule_refresh()
    harness.pump(500)
    assert wp.Visibility
    Gui.SendMsgToActiveView("ViewFit")
    harness.pump(400)
    view = Gui.ActiveDocument.ActiveView
    vp = view.graphicsView().viewport()
    hit = None
    for x, y in ((0, 0), (2, 2), (-2, 2), (3, -1)):
        sx, sy = view.getPointOnViewport(App.Vector(x, y, 25))
        info = view.getObjectInfo((int(sx), int(sy)))
        if info and info["Object"] == wp.Name:
            hit = (sx, sy)
            break
    assert hit is not None, "the work plane is under a probe point"
    dpr = vp.devicePixelRatioF()
    pos = QtCore.QPointF(hit[0] / dpr, vp.height() - hit[1] / dpr)
    _send("press", pos, QtCore.Qt.RightButton, QtCore.Qt.RightButton)
    _send("release", pos, QtCore.Qt.RightButton, QtCore.Qt.NoButton)
    harness.pump(300)
    assert sh.menu_kind == "origin", sh.menu_kind
    assert context.target() == wp.Name
    from incad.ui import marking_layout
    _, items = marking_layout.resolve(sh.menu_kind, commands.REGISTRY)
    assert any(c.id == "view.toggle_visibility" for c in items), [c.id for c in items]
    sh.marking_menu.close()
    harness.pump(200)
    r = commands.REGISTRY.run("view.toggle_visibility")
    assert r.ok, r.error
    harness.pump(400)
    assert not wp.Visibility and not document.is_shown(wp)
    assert sh.browser.item_by_label("WorkPlane").data(0, STATE_ROLE) == "hidden"
    _click_row("WorkPlane")
    assert wp.Visibility, "shown while its row is selected"
    r = commands.REGISTRY.run("view.toggle_visibility")
    assert r.ok, r.error
    harness.pump(400)
    _click_row("Pad")
    assert wp.Visibility, "shown for good"


harness.run([test_0_part, test_1_tree_menu_hide_show_on_a_plane, test_2_two_selected_axes_toggle_together,
             test_3_show_all_and_hide_all, test_4_plane_pick_restores_the_choice, test_5_consumed_sketch_can_be_shown_and_hidden,
             test_6_right_click_on_a_visible_plane_in_the_view_opens_the_origin_menu,
             test_7_right_click_on_a_work_plane_in_the_view_offers_hide_show])
