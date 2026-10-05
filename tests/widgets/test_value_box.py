import unittest

from widgets import qtapp
from incad.qt import QtCore
from incad.ui.value_box import ValueBox


class ValueBoxTest(unittest.TestCase):
    def setUp(self):
        qtapp.app()
        self.box = ValueBox("d1", "20 mm", "light")
        self.seen = []
        self.box.applied.connect(lambda n, t: self.seen.append((n, t)))
        self.box.show_near(QtCore.QPoint(300, 300))

    def tearDown(self):
        self.box.close()

    def test_enter_applies_and_closes(self):
        from PySide6.QtTest import QTest
        self.box.edit.setText("25 mm")
        QTest.keyClick(self.box.edit, QtCore.Qt.Key_Return)
        self.assertEqual(self.seen, [("d1", "25 mm")])
        self.assertFalse(self.box.isVisible())

    def test_escape_cancels(self):
        from PySide6.QtTest import QTest
        QTest.keyClick(self.box.edit, QtCore.Qt.Key_Escape)
        self.assertEqual(self.seen, [])
        self.assertFalse(self.box.isVisible())

    def test_insert_replaces_selection_then_typing_builds_a_formula(self):
        from PySide6.QtTest import QTest
        self.box.insert("d0")
        QTest.keyClicks(self.box.edit, "*2")
        QTest.keyClick(self.box.edit, QtCore.Qt.Key_Return)
        self.assertEqual(self.seen, [("d1", "d0*2")])

    def test_empty_text_applies_nothing(self):
        from PySide6.QtTest import QTest
        self.box.edit.setText("  ")
        QTest.keyClick(self.box.edit, QtCore.Qt.Key_Return)
        self.assertEqual(self.seen, [])
