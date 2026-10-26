"""The Parameters window (incad.ui.parameters_window): the table, edits as signals, Find, Delete Unused, a row being
added surviving a refresh."""
import unittest

from widgets import qtapp
from incad.qt import QtCore
from incad.ui.parameters_window import ParametersWindow

ROWS = [("dimension", "d0", "Width", "40 mm", ("Sketch", "Pad")),
        ("feature", "d1", "25 mm", "25 mm", ("Pad",)),
        ("feature", "d2", "3 mm", "3 mm", ()),
        ("user", "Width", "40 mm", "40 mm", ("Sketch (d0)",)),
        ("user", "Half", "Width / 2", "20 mm", ())]


class ParametersWindowTest(unittest.TestCase):
    def setUp(self):
        qtapp.app()
        self.w = ParametersWindow("light")
        self.w.set_rows(ROWS)
        self.events = []
        self.w.parameterSet.connect(lambda n, t: self.events.append(("set", n, t)))
        self.w.parameterRenamed.connect(lambda o, n: self.events.append(("rename", o, n)))
        self.w.parameterRemoved.connect(lambda n: self.events.append(("remove", n)))
        self.w.parameterClicked.connect(lambda n: self.events.append(("click", n)))
        self.w.deleteUnusedRequested.connect(lambda: self.events.append(("unused",)))

    def item(self, name, column):
        r = [t[0] for t in self.w.row_texts()].index(name)
        return self.w.table.item(r, column)

    def test_rows_with_what_uses_them(self):
        self.assertEqual(self.w.row_texts()[0], ("d0", "Width", "40 mm", "Sketch, Pad"))
        self.assertEqual(self.w.row_texts()[2][3], "— not used")
        self.assertEqual(len(self.w.row_texts()), 5)

    def test_value_edit_sets(self):
        self.item("d1", 1).setText("30 mm")
        self.item("Half", 1).setText("Width / 4")
        self.assertEqual(self.events, [("set", "d1", "30 mm"), ("set", "Half", "Width / 4")])

    def test_model_names_rename_user_names_stay(self):
        self.item("d1", 0).setText("Depth")
        self.assertEqual(self.events, [("rename", "d1", "Depth")])
        self.assertFalse(self.item("Width", 0).flags() & QtCore.Qt.ItemIsEditable)
        self.assertFalse(self.item("Width", 2).flags() & QtCore.Qt.ItemIsEditable)  # Result
        self.assertFalse(self.item("Width", 3).flags() & QtCore.Qt.ItemIsEditable)  # Used by

    def test_add_then_name_and_value_creates(self):
        r = self.w.add_row()
        self.w.table.item(r, 0).setText("Gap")
        self.assertEqual(self.events, [])  # no value yet
        self.w.table.item(r, 1).setText("2 mm")
        self.assertEqual(self.events, [("set", "Gap", "2 mm")])

    def test_a_row_being_added_survives_a_refresh(self):
        r = self.w.add_row()
        self.w.table.item(r, 0).setText("Gap")
        self.w.table.closePersistentEditor(self.w.table.item(r, 0))
        self.w.set_rows(ROWS[:-1])  # a refresh from an edit elsewhere
        self.assertEqual(self.w.row_texts()[-1][0], "Gap")

    def test_remove_selected(self):
        self.w.select("d2")
        self.w.remove_selected()
        self.assertEqual(self.events, [("remove", "d2")])
        r = self.w.add_row()
        self.w.remove_selected()  # a row not saved yet just goes
        self.assertEqual(len(self.w.row_texts()), 5)
        self.assertEqual(self.events, [("remove", "d2")])
        del r

    def test_find_narrows_the_list(self):
        self.w.find.setText("wid")
        self.assertEqual(self.w.visible_names(), ["Width"])
        self.w.find.setText("")
        self.assertEqual(len(self.w.visible_names()), 5)

    def test_name_click_inserts_and_delete_unused_asks(self):
        self.w._clicked(1, 0)
        self.w.unused_button.click()
        self.assertEqual(self.events, [("click", "d1"), ("unused",)])

    def test_not_a_part_edits_nothing(self):
        self.w.set_rows([], enabled=False)
        self.assertFalse(self.w.add_button.isEnabled())
        self.assertEqual(self.w.add_row(), -1)

    def test_closing_says_so(self):
        closed = []
        self.w.closed.connect(lambda: closed.append(True))
        self.w.show()
        self.w.close()
        self.assertEqual(closed, [True])

    def test_dark_theme_keeps_the_rows(self):
        self.w.set_theme("dark")
        self.assertEqual(len(self.w.row_texts()), 5)


if __name__ == "__main__":
    unittest.main()
