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
