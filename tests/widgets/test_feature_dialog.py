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

    def _wait(self, ms):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(ms, loop.quit)
        loop.exec()

    def test_typing_a_value_emits_after_a_pause_without_enter(self):
        """A value typed into a field previews by itself: no Enter, no focus change (a click in the 3D view takes
        no Qt focus, so editingFinished never came and the preview stayed stale)."""
        w = self.d.field("distance")
        w.setText("2")  # the keystrokes of '25 mm', one text change each
        w.setText("25")
        w.setText("25 mm")
        self.assertEqual(self.seen, [], "nothing while still typing")
        self._wait(900)
        self.assertEqual([v["distance"] for v in self.seen], ["25 mm"], "once, after the pause")
        w.editingFinished.emit()
        self.assertEqual(len(self.seen), 1, "Enter after a previewed value does not preview again")

    def test_a_programmatic_value_does_not_emit(self):
        self.d.set_values({"distance": "30 mm"})
        self._wait(900)
        self.assertEqual(self.seen, [])

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


PICK_FIELDS = (
    Field("edges", "Edges", "picks", pick="edge"),
    Field("plane", "Plane", "pick", pick="plane"),
    Field("radius", "Radius", "value_length", default="1 mm"),
)


class PickFieldsTest(unittest.TestCase):
    def setUp(self):
        qtapp.app()
        self.d = FeatureDialog("Fillet", "incad", PICK_FIELDS, {"edges": "", "plane": "", "radius": "1 mm"})
        self.seen = []
        self.d.changed.connect(lambda v: self.seen.append(dict(v)))

    def test_one_active_pick(self):
        self.d.set_active_pick("edges")
        self.assertEqual(self.d.active_pick(), "edges")
        self.d.field("plane").click()
        self.assertEqual(self.d.active_pick(), "plane")
        self.assertFalse(self.d.field("edges").isChecked())

    def test_set_pick_emits_and_labels(self):
        self.d.set_pick("edges", "Pad:Edge1,Pad:Edge2")
        self.assertEqual(self.seen[-1]["edges"], "Pad:Edge1,Pad:Edge2")
        self.assertEqual(self.d.field("edges").text(), "2 edges")

    def test_clicking_the_active_pick_again_ends_picking(self):
        seen = []
        self.d.activePickChanged.connect(seen.append)
        self.d.field("edges").click()
        self.d.field("edges").click()
        self.assertIsNone(self.d.active_pick())
        self.assertEqual(seen, ["edges", ""])


COMBO_FIELDS = (
    Field("threaded", "Threaded", "bool", default=False),
    Field("standard", "Standard", "combo", (("iso", "ISO"), ("unc", "UNC")), "iso", show_if=("threaded", (True,))),
    Field("size", "Size", "combo", (), "", show_if=("threaded", (True,))),
    Field("deep", "Deep", "value_length", default="1 mm", show_if=(("threaded", (True,)), ("standard", ("unc",)))),
)


class ComboFieldsTest(unittest.TestCase):
    def setUp(self):
        qtapp.app()
        self.d = FeatureDialog("Hole", "incad", COMBO_FIELDS,
                               {"threaded": True, "standard": "iso", "size": "", "deep": "1 mm"})
        self.seen = []
        self.d.changed.connect(lambda v: self.seen.append(dict(v)))

    def test_options_and_value(self):
        self.d.set_options("size", [("M6", "M6"), ("M8", "M8")])
        self.assertEqual(self.d.values()["size"], "M6")
        self.d.set_values({"size": "M8"})
        self.assertEqual(self.d.values()["size"], "M8")
        self.d.set_options("size", [("M8", "M8"), ("M10", "M10")])
        self.assertEqual(self.d.values()["size"], "M8")  # still offered: kept
        self.d.set_options("size", [("1/4", "1/4")])
        self.assertEqual(self.d.values()["size"], "1/4")

    def test_user_change_emits_once(self):
        self.d.set_options("size", [("M6", "M6"), ("M8", "M8")])
        self.seen.clear()
        self.d.field("size").setCurrentIndex(1)
        self.assertEqual(len(self.seen), 1)
        self.assertEqual(self.seen[0]["size"], "M8")
        self.seen.clear()
        self.d.set_options("size", [("M8", "M8"), ("M10", "M10")])
        self.assertEqual(self.seen, [])  # programmatic: no signal

    def test_and_conditions(self):
        self.assertFalse(self.d.row_visible("deep"))
        self.d.field("standard").setCurrentIndex(1)
        self.assertTrue(self.d.row_visible("deep"))
        self.d.field("threaded").setChecked(False)
        self.assertFalse(self.d.row_visible("deep"))
