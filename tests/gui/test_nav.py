import os
import sys

sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests", "gui"))
sys.path.insert(0, os.path.join(os.environ["INCAD_REPO"], "tests"))
import harness  # noqa: E402
import FreeCAD as App  # noqa: E402
import FreeCADGui as Gui  # noqa: E402
from pivy import coin  # noqa: E402,F401  (getCameraNode needs pivy loaded)
from incad.qt import QtCore, QtGui, QtWidgets  # noqa: E402
from incad.core import commands, context, document, params, prefs  # noqa: E402
from incad.ui import shell, theme  # noqa: E402
from incad.ui.marking_menu import MarkingMenu  # noqa: E402

mw = Gui.getMainWindow()
L, R = QtCore.Qt.LeftButton, QtCore.Qt.RightButton
BASE = {}
NAV_KEYS = {"NavigationStyle": "String", "ZoomAtCursor": "Bool"}


def view():
    return Gui.ActiveDocument.ActiveView


def vp():
    return view().graphicsView().viewport()


def s():
    return shell.instance()


def qt_pos_of(point):
    x, y = view().getPointOnScreen(App.Vector(*point))
    dpr = vp().devicePixelRatioF()
    return QtCore.QPointF(x / dpr, vp().height() - y / dpr)


def empty_pos():
    return QtCore.QPointF(vp().width() * 0.2, vp().height() * 0.8)


def send(kind, pos, button, buttons, target=None):
    target = target or vp()
    types = {"press": QtCore.QEvent.MouseButtonPress, "release": QtCore.QEvent.MouseButtonRelease,
             "move": QtCore.QEvent.MouseMove}
    glob = QtCore.QPointF(target.mapToGlobal(pos.toPoint()))
    ev = QtGui.QMouseEvent(types[kind], pos, glob, button, buttons, QtCore.Qt.NoModifier)
    QtWidgets.QApplication.sendEvent(target, ev)
    harness.pump(40)


def close_menu():
    m = s().marking_menu
    if m is not None and m.isVisible():
        m.close()
    harness.pump(100)


def nav_params():
    return (params.snapshot(theme.VIEW_GROUP, NAV_KEYS), params.snapshot(theme.NAVICUBE_GROUP, theme.NAVICUBE_KEYS))


def test_0_setup():
    prefs.set_remember_new_choice(True)
    prefs.set_default_units("mm")
    Gui.activateWorkbench("PartDesignWorkbench")
    harness.pump(800)
    BASE["params"] = nav_params()
    Gui.activateWorkbench("InCadWorkbench")
    harness.pump(1000)
    commands.REGISTRY.run("file.new")
    harness.pump(800)
    box = App.ActiveDocument.addObject("Part::Box", "Box")
    App.ActiveDocument.recompute()
    Gui.SendMsgToActiveView("ViewFit")
    harness.pump(800)
    assert box.Shape.isValid()


def test_1_navigation_installed():
    assert vp() in s().navigator.attached()
    assert view().getNavigationType() == "Gui::CADNavigationStyle", view().getNavigationType()
    assert App.ParamGet(theme.VIEW_GROUP).GetBool("ZoomAtCursor", False)


def test_2_left_click_still_selects():
    Gui.Selection.clearSelection()
    p = qt_pos_of((5, 5, 10))
    send("press", p, L, L)
    send("release", p, L, QtCore.Qt.NoButton)
    names = [o.ObjectName for o in Gui.Selection.getSelectionEx()]
    assert names == ["Box"], names


def test_3_left_right_drag_orbits_without_selecting():
    Gui.Selection.clearSelection()
    before = view().getCameraOrientation()
    p = qt_pos_of((5, 5, 10))
    pivot_before = view().getPointOnScreen(App.Vector(5, 5, 10))
    send("press", p, L, L)
    send("press", p, R, L | R)
    for i in range(1, 5):
        send("move", p + QtCore.QPointF(10 * i, 0), QtCore.Qt.NoButton, L | R)
    send("release", p + QtCore.QPointF(40, 0), L, R)
    send("release", p + QtCore.QPointF(40, 0), R, QtCore.Qt.NoButton)
    after = view().getCameraOrientation()
    assert not after.isSame(before, 1e-4), "camera did not orbit"
    pivot_after = view().getPointOnScreen(App.Vector(5, 5, 10))
    assert abs(pivot_after[0] - pivot_before[0]) < 6 and abs(pivot_after[1] - pivot_before[1]) < 6, (pivot_before, pivot_after)
    assert Gui.Selection.getSelectionEx() == [], "an orbit must not select"
    assert s().marking_menu is None or not s().marking_menu.isVisible()
    Gui.SendMsgToActiveView("ViewFit")
    harness.pump(300)


def test_4_right_click_on_face():
    Gui.Selection.clearSelection()
    p = qt_pos_of((5, 5, 10))
    send("press", p, R, R)
    send("release", p, R, QtCore.Qt.NoButton)
    harness.pump(200)
    assert isinstance(QtWidgets.QApplication.activePopupWidget(), MarkingMenu), QtWidgets.QApplication.activePopupWidget()
    assert s().menu_kind == "face", s().menu_kind
    assert [o.ObjectName for o in Gui.Selection.getSelectionEx()] == ["Box"]
    close_menu()


def test_5_right_click_on_empty_space():
    send("press", empty_pos(), R, R)
    send("release", empty_pos(), R, QtCore.Qt.NoButton)
    harness.pump(200)
    assert s().menu_kind == "part", s().menu_kind
    assert isinstance(QtWidgets.QApplication.activePopupWidget(), MarkingMenu)
    close_menu()


def test_6_flick_north_runs_home_view():
    ran = []
    original = commands.REGISTRY.run
    commands.REGISTRY.run = lambda i: (ran.append(i), original(i))[1]
    try:
        p = empty_pos()
        send("press", p, R, R)
        send("move", p + QtCore.QPointF(0, -10), QtCore.Qt.NoButton, R)
        harness.pump(200)
        menu = s().marking_menu
        assert menu is not None and menu.isVisible(), "flick did not open the menu"
        end = menu.mapFromGlobal(menu.center_global() + QtCore.QPoint(0, -70))
        send("move", QtCore.QPointF(end), QtCore.Qt.NoButton, R, target=menu)
        send("release", QtCore.QPointF(end), R, QtCore.Qt.NoButton, target=menu)
        harness.pump(300)
    finally:
        commands.REGISTRY.run = original
    assert ran == ["view.home"], ran


def test_7_browser_marking_menu_suppress():
    doc = App.ActiveDocument
    body = document.primary_body(doc)
    import headless.util as util
    sketch = util.add_rect_sketch(body)
    pad = util.add_pad(body, sketch, 5)
    doc.recompute()
    harness.pump(500)
    s().browser.markingMenuRequested.emit(pad.Name, QtCore.QPoint(400, 400))
    harness.pump(200)
    assert s().menu_kind == "browser" and context.target() == pad.Name
    s().marking_menu.choose("browser.suppress")
    harness.pump(400)
    assert pad.Suppressed
    s().browser.markingMenuRequested.emit(pad.Name, QtCore.QPoint(400, 400))
    harness.pump(200)
    s().marking_menu.choose("browser.suppress")
    harness.pump(400)
    assert not pad.Suppressed


def test_8_strip_orbit_tool():
    strip = s().strip
    assert strip is not None and not strip.isHidden()
    strip.button("nav.orbit").click()
    assert shell.nav_mode() == "orbit" and strip.button("nav.orbit").isChecked()
    before = view().getCameraOrientation()
    p = empty_pos()
    send("press", p, L, L)
    send("move", p + QtCore.QPointF(30, 10), QtCore.Qt.NoButton, L)
    send("release", p + QtCore.QPointF(30, 10), L, QtCore.Qt.NoButton)
    assert not view().getCameraOrientation().isSame(before, 1e-4)
    strip.button("nav.orbit").click()
    assert shell.nav_mode() is None and not strip.button("nav.orbit").isChecked()


def test_9_navicube_follows_theme():
    got = App.ParamGet(theme.NAVICUBE_GROUP).GetUnsigned("BaseColor")
    assert got == theme.navicube_params(s().theme)["BaseColor"][1], hex(got)


def test_10_navigation_off_and_on():
    s().set_navigation(False)
    assert s().navigator.attached() == [] and not prefs.navigation_enabled()
    s().set_navigation(True)
    assert vp() in s().navigator.attached()


def test_11_leaving_incad_restores_navigation():
    Gui.activateWorkbench("PartDesignWorkbench")
    harness.pump(1000)
    assert nav_params() == BASE["params"], (nav_params(), BASE["params"])
    assert s().navigator is None or s().navigator.attached() == []


harness.run([test_0_setup, test_1_navigation_installed, test_2_left_click_still_selects,
             test_3_left_right_drag_orbits_without_selecting, test_4_right_click_on_face,
             test_5_right_click_on_empty_space, test_6_flick_north_runs_home_view, test_7_browser_marking_menu_suppress,
             test_8_strip_orbit_tool, test_9_navicube_follows_theme, test_10_navigation_off_and_on,
             test_11_leaving_incad_restores_navigation])
