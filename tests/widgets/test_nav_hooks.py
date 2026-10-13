import unittest

from widgets import qtapp
from incad.qt import QtCore, QtGui, QtWidgets
from incad.core import gestures
from incad.ui.nav import Navigator


def ev(kind, button, buttons):
    t = {"press": QtCore.QEvent.MouseButtonPress, "release": QtCore.QEvent.MouseButtonRelease,
         "dbl": QtCore.QEvent.MouseButtonDblClick}[kind]
    return QtGui.QMouseEvent(t, QtCore.QPointF(10, 10), QtCore.QPointF(10, 10), button, buttons, QtCore.Qt.NoModifier)


class HooksTest(unittest.TestCase):
    def setUp(self):
        qtapp.app()
        self.nav = Navigator(lambda *a: None)
        self.w = QtWidgets.QWidget()
        self.nav._attached[self.w] = [None, gestures.Gestures(), QtCore.Qt.NoModifier]
        self.calls = []

    def test_click_hook_takes_press_and_release(self):
        self.nav.click_hook = lambda *a: (self.calls.append(a[2:]), True)[1]
        L = QtCore.Qt.LeftButton
        self.assertTrue(self.nav.eventFilter(self.w, ev("press", L, L)))
        self.assertTrue(self.nav.eventFilter(self.w, ev("release", L, QtCore.Qt.NoButton)))
        self.assertEqual(self.calls, [(10.0, 10.0)])
        self.assertEqual(self.nav._attached[self.w][1].state, "idle")

    def test_declined_click_goes_through_gestures(self):
        self.nav.click_hook = lambda *a: False
        L = QtCore.Qt.LeftButton
        self.assertTrue(self.nav.eventFilter(self.w, ev("press", L, L)))  # held back by the gesture rules
        self.assertEqual(self.nav._attached[self.w][1].state, "left_held")

    def test_dblclick_hook(self):
        self.nav.dblclick_hook = lambda *a: True
        L = QtCore.Qt.LeftButton
        self.assertTrue(self.nav.eventFilter(self.w, ev("dbl", L, L)))
        self.nav.dblclick_hook = lambda *a: False
        self.assertFalse(self.nav.eventFilter(self.w, ev("dbl", L, L)))

    def test_drag_hook_begins_before_the_replay_and_ends_on_release(self):
        L = QtCore.Qt.LeftButton
        seen = []

        class Hook:
            def begin(self, view, viewport, x, y):
                seen.append(("begin", x, y))

            def end(self):
                seen.append(("end",))

        self.nav.drag_hook = Hook()
        self.nav._replay = lambda *a, **k: seen.append(("replay",))
        move = lambda x: QtGui.QMouseEvent(QtCore.QEvent.MouseMove, QtCore.QPointF(x, 10), QtCore.QPointF(x, 10),
                                           QtCore.Qt.NoButton, L, QtCore.Qt.NoModifier)
        self.nav.eventFilter(self.w, ev("press", L, L))
        self.nav.eventFilter(self.w, move(40))
        self.nav.eventFilter(self.w, ev("release", L, QtCore.Qt.NoButton))
        self.assertEqual(seen, [("begin", 10.0, 10.0), ("replay",), ("end",)])

    def test_a_failing_drag_hook_still_replays(self):
        L = QtCore.Qt.LeftButton
        seen = []

        class Hook:
            def begin(self, *a):
                raise RuntimeError("boom")

            def end(self):
                pass

        self.nav.drag_hook = Hook()
        self.nav._replay = lambda *a, **k: seen.append("replay")
        move = QtGui.QMouseEvent(QtCore.QEvent.MouseMove, QtCore.QPointF(40, 10), QtCore.QPointF(40, 10),
                                 QtCore.Qt.NoButton, L, QtCore.Qt.NoModifier)
        self.nav.eventFilter(self.w, ev("press", L, L))
        self.nav.eventFilter(self.w, move)
        self.assertEqual(seen, ["replay"])


class Recorder(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.seen = []

    def mousePressEvent(self, e):
        self.seen.append(("press", e.button()))

    def mouseReleaseEvent(self, e):
        self.seen.append(("release", e.button()))


class ToolRightClickTest(unittest.TestCase):
    """A plain right click while a Sketcher tool runs (bitmap cursor on the view) is handed to FreeCAD as
    press+release (the spline and polyline tools finish on it); otherwise it opens the marking menu."""
    def setUp(self):
        qtapp.app()
        self.menus = []
        self.nav = Navigator(lambda *a: self.menus.append(a[-1]))
        self.w = Recorder()
        self.nav._attached[self.w] = [None, gestures.Gestures(), QtCore.Qt.NoModifier]

    def right_click(self):
        R = QtCore.Qt.RightButton
        self.assertTrue(self.nav.eventFilter(self.w, ev("press", R, R)))
        self.assertTrue(self.nav.eventFilter(self.w, ev("release", R, QtCore.Qt.NoButton)))

    def test_tool_cursor_gets_the_click(self):
        self.w.setCursor(QtGui.QCursor(QtGui.QPixmap(16, 16)))
        self.assertTrue(Navigator.tool_cursor(self.w))
        self.right_click()
        self.assertEqual(self.w.seen, [("press", QtCore.Qt.RightButton), ("release", QtCore.Qt.RightButton)])
        self.assertEqual(self.menus, [])

    def test_plain_cursor_opens_the_menu(self):
        self.assertFalse(Navigator.tool_cursor(self.w))
        self.right_click()
        self.assertEqual(self.w.seen, [])
        self.assertEqual(self.menus, [False])  # a click, not a flick
