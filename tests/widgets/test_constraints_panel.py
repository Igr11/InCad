import unittest

from widgets import qtapp
from incad.ui.constraints_panel import ConstraintsPanel

ROWS = [(0, "Coincident", "Line 1 end ↔ Line 2 start", "", False),
        (4, "Horizontal", "Line 1", "", False),
        (8, "Horizontal Distance", "Line 1 start ↔ Line 1 end", "d1 = 60 mm", False),
        (11, "Equal", "Line 1 ↔ Line 3", "", True)]


class ConstraintsPanelTest(unittest.TestCase):
    def setUp(self):
        qtapp.app()
        self.p = ConstraintsPanel("light")
        self.p.set_rows("Constraints — Sketch2", "All constraints (4)", ROWS)
        self.seen = {"delete": [], "hi": [], "all": 0, "closed": 0}
        self.p.delete_requested.connect(lambda ids: self.seen["delete"].append(ids))
        self.p.highlight.connect(lambda i: self.seen["hi"].append(i))
        self.p.show_all.connect(lambda: self.seen.__setitem__("all", self.seen["all"] + 1))
        self.p.closed.connect(lambda: self.seen.__setitem__("closed", self.seen["closed"] + 1))

    def test_rows_title_and_header(self):
        self.assertEqual(self.p.title_text(), "Constraints — Sketch2")
        self.assertEqual(self.p.header_text(), "All constraints (4)")
        self.assertEqual(self.p.row_texts()[2], ("Horizontal Distance", "Line 1 start ↔ Line 1 end", "d1 = 60 mm"))

    def test_selecting_a_row_asks_for_its_highlight(self):
        self.p.select_index(8)
        self.assertEqual(self.seen["hi"][-1], 8)
        self.assertEqual(self.p.selected(), 8)

    def test_delete_takes_the_checked_rows_else_the_selected_one(self):
        self.p.select_index(4)
        self.p.delete_button.click()
        self.assertEqual(self.seen["delete"][-1], [4])
        self.p.set_checked(0, True)
        self.p.set_checked(8, True)
        self.p.delete_button.click()
        self.assertEqual(self.seen["delete"][-1], [0, 8])

    def test_nothing_chosen_says_so(self):
        self.p.delete_button.click()
        self.assertEqual(self.seen["delete"], [])
        self.assertEqual(self.p.message_text(), "Check rows or select one first")

    def test_select_all_checks_the_listed_rows(self):
        self.p.select_all_button.click()
        self.assertEqual(self.p.checked(), [0, 4, 8, 11])

    def test_esc_shows_all_and_x_closes(self):
        from PySide6.QtTest import QTest
        from incad.qt import QtCore
        QTest.keyClick(self.p, QtCore.Qt.Key_Escape)
        self.assertEqual(self.seen["all"], 1)
        self.p.close_button.click()
        self.assertEqual(self.seen["closed"], 1)

    def test_set_rows_keeps_the_selection_when_the_row_is_still_there(self):
        self.p.select_index(8)
        self.p.set_rows("Constraints — Sketch2", "Picked: Line 1", ROWS[1:3])
        self.assertEqual(self.p.selected(), 8)
        self.p.set_rows("Constraints — Sketch2", "Picked: Line 2", ROWS[:1])
        self.assertIsNone(self.p.selected())
