import unittest

from widgets import qtapp
from incad.qt import QtCore
from incad.features.common import Field
from incad.ui.feature_dialog import FeatureDialog

FIELDS = (
    Field("operation", "Operation", "choice", (("join", "Join"), ("cut", "Cut")), "join"),
    Field("extent", "Extents", "choice", (("distance", "Distance"), ("to", "To")), "distance"),
    Field("to_face", "Face", "pick", show_if=("extent", ("to",))),
    Field("distance", "Distance", "value_length", default="10 mm", show_if=("extent", ("distance",))),
    Field("flip", "Flip", "bool", default=False),
)


class FeatureDialogTest(unittest.TestCase):
    def setUp(self):
        qtapp.app()
        self.d = FeatureDialog("Extrude", "incad", FIELDS,
                               {"operation": "join", "extent": "distance", "to_face": "", "distance": "10 mm",
                                "flip": False})
        self.seen = []
        self.d.changed.connect(lambda v: self.seen.append(dict(v)))
        self.d.show()

    def tearDown(self):
        self.d.close()

    def test_values_round_trip(self):
        self.assertEqual(self.d.values(), {"operation": "join", "extent": "distance", "to_face": "",
                                           "distance": "10 mm", "flip": False})

    def test_choice_change_emits(self):
        self.d.field("operation").button("cut").click()
        self.assertEqual(self.seen[-1]["operation"], "cut")

    def test_value_edit_emits(self):
        self.d.field("distance").setText("25 mm")
        self.d.field("distance").editingFinished.emit()
        self.assertEqual(self.seen[-1]["distance"], "25 mm")

    def test_show_if_hides_rows(self):
        self.assertTrue(self.d.row_visible("distance"))
        self.assertFalse(self.d.row_visible("to_face"))
        self.d.field("extent").button("to").click()
        self.assertFalse(self.d.row_visible("distance"))
        self.assertTrue(self.d.row_visible("to_face"))

    def test_error_disables_ok(self):
        self.d.set_error("Pad: length is zero")
        self.assertFalse(self.d.ok_button.isEnabled())
        self.assertIn("zero", self.d.error_text())
        self.d.set_error("")
        self.assertTrue(self.d.ok_button.isEnabled())

    def test_buttons_and_keys(self):
        from PySide6.QtTest import QTest
        got = []
        self.d.accepted.connect(lambda: got.append("ok"))
        self.d.cancelled.connect(lambda: got.append("cancel"))
        self.d.applied.connect(lambda: got.append("apply"))
        self.d.apply_button.click()
        QTest.keyClick(self.d.field("distance"), QtCore.Qt.Key_Return)
        QTest.keyClick(self.d.field("distance"), QtCore.Qt.Key_Escape)
        self.assertEqual(got, ["apply", "ok", "cancel"])

    def test_insert_into_focused_field(self):
        f = self.d.field("distance")
        f.setFocus()
        f.selectAll()
        self.assertIs(self.d.focused_value_field(), f) if f.hasFocus() else None
        f.insert("d3")
        self.assertEqual(f.text(), "d3")

    def test_param_name_and_pick_text(self):
        self.d.set_param_name("distance", "d4")
        self.assertIn("d4", self.d.label_text("distance"))
        self.d.set_pick_text("to_face", "Pad · Face6")
        self.assertEqual(self.d.pick_text("to_face"), "Pad · Face6")
        picks = []
        self.d.pickRequested.connect(picks.append)
        self.d.field("to_face").click()
        self.assertEqual(picks, ["to_face"])


class DialogLooksTest(unittest.TestCase):
    def setUp(self):
        qtapp.app()
        self.d = FeatureDialog("Extrude", "incad", FIELDS,
                               {"operation": "join", "extent": "distance", "to_face": "", "distance": "10 mm",
                                "flip": False})
        self.d.show()

    def tearDown(self):
        self.d.close()

    def test_dialog_grows_to_fit_an_error(self):
        self.d.set_error("A long reason that wraps over more than one line in the dialog, to make sure it fits")
        qtapp.app().processEvents()
        self.assertGreaterEqual(self.d.height(), self.d.sizeHint().height())

    def test_buttons_have_explicit_colors(self):
        """macOS draws native buttons in the system appearance unless the stylesheet sets them (seen live)."""
        qss = self.d.styleSheet().replace(" ", "")
        self.assertIn("QPushButton{background:", qss)
