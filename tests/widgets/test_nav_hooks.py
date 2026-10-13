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


    def test_a_failure_mid_drag_still_ends_the_drag(self):
        L = QtCore.Qt.LeftButton
        seen = []

        class Hook:
            def begin(self, *a):
                seen.append("begin")

            def end(self):
                seen.append("end")

        self.nav.drag_hook = Hook()
        self.nav._replay = lambda *a, **k: None
        move = lambda x: QtGui.QMouseEvent(QtCore.QEvent.MouseMove, QtCore.QPointF(x, 10), QtCore.QPointF(x, 10),
                                           QtCore.Qt.NoButton, L, QtCore.Qt.NoModifier)
        self.nav.eventFilter(self.w, ev("press", L, L))
        self.nav.eventFilter(self.w, move(40))
        machine = self.nav._attached[self.w][1]
        self.assertEqual(machine.state, "passthrough")

        def boom(*a):
            raise RuntimeError("boom")
        machine.feed = boom
        self.nav.eventFilter(self.w, move(50))
        self.assertEqual(seen, ["begin", "end"], "the reset drops the drag's release: the drag ends now")
        self.assertEqual(machine.state, "idle")

def mouse(kind, x, button, buttons):
    t = {"press": QtCore.QEvent.MouseButtonPress, "release": QtCore.QEvent.MouseButtonRelease,
         "move": QtCore.QEvent.MouseMove}[kind]
    return QtGui.QMouseEvent(t, QtCore.QPointF(x, 10), QtCore.QPointF(x, 10), button, buttons, QtCore.Qt.NoModifier)


class HandleHook:
    """Records the navigator's calls; takes the press when `take`."""

    def __init__(self, take):
        self.take, self.seen = take, []

    def at(self, view, viewport, x, y):
        return self.take

    def press(self, view, viewport, x, y):
        self.seen.append(("press", x))
        return self.take

    def move(self, x, y):
        self.seen.append(("move", x))

    def release(self):
        self.seen.append(("release",))

    def hover(self, view, viewport, x, y):
        self.seen.append(("hover", x))


class HandleModeTest(unittest.TestCase):
    """A left press the handle hook takes is InCad's handle drag: its moves and release go to the hook, consumed
    (FreeCAD would box-select or start its own drag); a press it declines goes through the gesture rules."""
    def setUp(self):
        qtapp.app()
        self.nav = Navigator(lambda *a: None)
        self.w = QtWidgets.QWidget()
        self.machine = gestures.Gestures()
        self.nav._attached[self.w] = [None, self.machine, QtCore.Qt.NoModifier]
        self.replays = []
        self.nav._replay = lambda *a, **k: self.replays.append(a[1:3])
        self.drags = []

        class Drag:
            def begin(_, *a):
                self.drags.append("begin")

            def end(_):
                self.drags.append("end")
        self.nav.drag_hook = Drag()

    def test_a_taken_press_sends_moves_and_release_to_the_hook(self):
        hook = self.nav.handle_hook = HandleHook(True)
        L, N = QtCore.Qt.LeftButton, QtCore.Qt.NoButton
        self.assertTrue(self.nav.eventFilter(self.w, mouse("press", 10, L, L)))
        self.assertTrue(self.nav.eventFilter(self.w, mouse("move", 30, N, L)), "a handle drag's move is consumed")
        self.assertTrue(self.nav.eventFilter(self.w, mouse("move", 60, N, L)))
        self.assertTrue(self.nav.eventFilter(self.w, mouse("release", 60, L, N)), "and its release")
        self.assertEqual(hook.seen, [("press", 10.0), ("move", 30.0), ("move", 60.0), ("release",)])
        self.assertEqual((self.replays, self.drags), ([], []), "FreeCAD never sees it; no native drag")
        self.assertEqual(self.machine.state, "idle")
        self.assertFalse(self.nav.eventFilter(self.w, mouse("move", 70, N, N)), "back to normal: a hover passes")
        self.assertEqual(hook.seen[-1], ("hover", 70.0))

    def test_a_declined_press_is_the_normal_gesture_flow(self):
        hook = self.nav.handle_hook = HandleHook(False)
        L, N = QtCore.Qt.LeftButton, QtCore.Qt.NoButton
        self.nav.eventFilter(self.w, mouse("press", 10, L, L))
        self.assertEqual(self.machine.state, "left_held")
        self.nav.eventFilter(self.w, mouse("move", 40, N, L))
        self.nav.eventFilter(self.w, mouse("release", 40, L, N))
        self.assertEqual(self.drags, ["begin", "end"], "FreeCAD's own drag (asm_drag), as before")
        self.assertEqual(self.replays, [(10.0, 10.0)])
        self.assertEqual([s for s in hook.seen if s[0] != "hover"], [("press", 10.0)])

    def test_a_lost_release_ends_handle_mode(self):
        hook = self.nav.handle_hook = HandleHook(True)
        L, N = QtCore.Qt.LeftButton, QtCore.Qt.NoButton
        self.nav.eventFilter(self.w, mouse("press", 10, L, L))
        self.nav.eventFilter(self.w, mouse("move", 30, N, L))
        self.assertFalse(self.nav.eventFilter(self.w, mouse("move", 40, N, N)), "buttons gone: the move passes")
        self.assertEqual(hook.seen[:3], [("press", 10.0), ("move", 30.0), ("release",)])
        hook.take = False
        self.nav.eventFilter(self.w, mouse("press", 50, L, L))
        self.assertEqual(self.machine.state, "left_held", "the next press is a normal one")

    def test_hover_reaches_the_hook_and_still_passes(self):
        hook = self.nav.handle_hook = HandleHook(False)
        N = QtCore.Qt.NoButton
        self.assertFalse(self.nav.eventFilter(self.w, mouse("move", 25, N, N)))
        self.assertEqual(hook.seen, [("hover", 25.0)])

    def test_a_failing_hook_never_blocks_the_mouse(self):
        class Boom(HandleHook):
            def press(self, *a):
                raise RuntimeError("boom")

            def hover(self, *a):
                raise RuntimeError("boom")
        self.nav.handle_hook = Boom(True)
        L, N = QtCore.Qt.LeftButton, QtCore.Qt.NoButton
        self.assertFalse(self.nav.eventFilter(self.w, mouse("move", 25, N, N)))
        self.nav.eventFilter(self.w, mouse("press", 10, L, L))
        self.assertEqual(self.machine.state, "left_held", "a failed press is a normal press")

    def test_a_quick_second_press_is_a_handle_press_too(self):
        """Within the double-click interval Qt sends a double-click event, not a press: the retry after a press
        that moved too little must still be the handle's, not FreeCAD's."""
        hook = self.nav.handle_hook = HandleHook(True)
        L, N = QtCore.Qt.LeftButton, QtCore.Qt.NoButton
        dbl = QtGui.QMouseEvent(QtCore.QEvent.MouseButtonDblClick, QtCore.QPointF(12, 10), QtCore.QPointF(12, 10),
                                L, L, QtCore.Qt.NoModifier)
        self.assertTrue(self.nav.eventFilter(self.w, mouse("press", 10, L, L)))
        self.assertTrue(self.nav.eventFilter(self.w, mouse("release", 10, L, N)))
        self.assertTrue(self.nav.eventFilter(self.w, dbl), "the double-click event is the hook's press")
        self.assertTrue(self.nav.eventFilter(self.w, mouse("move", 40, N, L)))
        self.assertTrue(self.nav.eventFilter(self.w, mouse("release", 40, L, N)))
        self.assertEqual(hook.seen, [("press", 10.0), ("release",), ("press", 12.0), ("move", 40.0), ("release",)])
        self.assertEqual((self.replays, self.drags), ([], []))

    def test_a_click_the_hook_gives_back_is_replayed_to_freecad(self):
        class Click(HandleHook):
            def release(self):
                super().release()
                return True  # a plain click, not on the gizmo's own part
        hook = self.nav.handle_hook = Click(True)
        L, N = QtCore.Qt.LeftButton, QtCore.Qt.NoButton
        self.nav.eventFilter(self.w, mouse("press", 10, L, L))
        self.nav.eventFilter(self.w, mouse("release", 11, L, N))
        self.assertEqual(self.replays, [(10.0, 10.0)], "press and release replayed where it was pressed")
        self.nav.eventFilter(self.w, mouse("press", 30, L, L))
        self.nav.eventFilter(self.w, mouse("move", 33, N, N))  # a lost release: nothing replayed
        self.assertEqual(self.replays, [(10.0, 10.0)])
        self.assertEqual(hook.seen.count(("release",)), 2)

    def test_shift_or_ctrl_press_is_never_a_handle_grab(self):
        hook = self.nav.handle_hook = HandleHook(True)
        L = QtCore.Qt.LeftButton
        for mod in (QtCore.Qt.ShiftModifier, QtCore.Qt.ControlModifier, QtCore.Qt.MetaModifier):
            self.machine.reset()
            press = QtGui.QMouseEvent(QtCore.QEvent.MouseButtonPress, QtCore.QPointF(10, 10),
                                      QtCore.QPointF(10, 10), L, L, mod)
            self.nav.eventFilter(self.w, press)
            self.assertEqual(self.machine.state, "left_held", "FreeCAD adds to the selection")
        self.assertEqual(hook.seen, [])

    def test_no_handle_press_while_a_navigation_tool_runs(self):
        hook = self.nav.handle_hook = HandleHook(True)
        self.nav.set_mode("orbit")
        self.nav._pivot_at = lambda *a: None  # no 3D view here
        L = QtCore.Qt.LeftButton
        self.nav.eventFilter(self.w, mouse("press", 10, L, L))
        self.assertEqual(self.machine.state, "tool")
        self.assertEqual(hook.seen, [])


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

    def test_right_click_is_unchanged_with_a_handle_hook(self):
        """The DOF handle hook is left-button only: a right press/release still reaches the gesture rules and opens
        the marking menu, and the hook never hears of it."""
        hook = self.nav.handle_hook = HandleHook(True)
        self.right_click()
        self.assertEqual(self.menus, [False])
        self.assertEqual(self.w.seen, [], "FreeCAD gets nothing")
        self.assertEqual(hook.seen, [])
        self.assertEqual(self.nav._attached[self.w][1].state, "idle")

    def test_plain_cursor_opens_the_menu(self):
        self.assertFalse(Navigator.tool_cursor(self.w))
        self.right_click()
        self.assertEqual(self.w.seen, [])
        self.assertEqual(self.menus, [False])  # a click, not a flick
