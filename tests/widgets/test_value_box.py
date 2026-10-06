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

    def test_clicking_the_tick_applies_and_the_cross_cancels(self):
        from PySide6.QtTest import QTest
        self.box.edit.setText("25 mm")
        QTest.mouseClick(self.box.apply_button, QtCore.Qt.LeftButton)
        self.assertEqual(self.seen, [("d1", "25 mm")])
        self.assertFalse(self.box.isVisible())
        other = ValueBox("d2", "5 mm", "light")
        other.applied.connect(lambda n, t: self.seen.append((n, t)))
        other.show_near(QtCore.QPoint(300, 300))
        other.edit.setText("99 mm")
        QTest.mouseClick(other.cancel_button, QtCore.Qt.LeftButton)
        self.assertEqual(self.seen, [("d1", "25 mm")])  # nothing applied
        self.assertFalse(other.isVisible())

    def test_clicking_the_boxs_own_dimension_inserts_nothing(self):
        self.box.insert("d1")
        self.assertEqual(self.box.edit.text(), "20 mm")

    def test_a_clicked_name_replaces_a_fully_selected_value_even_after_typing(self):
        from PySide6.QtTest import QTest
        QTest.keyClicks(self.box.edit, "30")
        self.box.edit.selectAll()
        self.box.insert("d0")
        self.assertEqual(self.box.edit.text(), "d0")

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


class ValueBoxApplyTest(unittest.TestCase):
    def setUp(self):
        qtapp.app()

    def test_rejected_formula_keeps_the_box_open_and_red(self):
        from PySide6.QtTest import QTest
        box = ValueBox("d1", "20 mm", "light", apply=lambda n, t: (False, "Nope is not a parameter"))
        box.show_near(QtCore.QPoint(300, 300))
        box.edit.setText("Nope*2")
        QTest.keyClick(box.edit, QtCore.Qt.Key_Return)
        self.assertTrue(box.isVisible())
        self.assertEqual(box.edit.text(), "Nope*2")
        self.assertIn("Nope", box.error_text())
        box.close()

    def test_accepted_value_closes(self):
        from PySide6.QtTest import QTest
        seen = []
        box = ValueBox("d1", "20 mm", "light", apply=lambda n, t: (seen.append((n, t)), (True, ""))[1])
        box.show_near(QtCore.QPoint(300, 300))
        QTest.keyClick(box.edit, QtCore.Qt.Key_Return)
        self.assertEqual(seen, [("d1", "20 mm")])
        self.assertFalse(box.isVisible())

    def test_insert_brings_keyboard_focus_back(self):
        box = ValueBox("d1", "20 mm", "light")
        calls = []
        box.activateWindow = lambda: calls.append("activate")
        box.show_near(QtCore.QPoint(300, 300))
        calls.clear()
        box.insert("d0")
        self.assertEqual(calls, ["activate"])
        box.close()
