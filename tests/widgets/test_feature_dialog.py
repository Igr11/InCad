import unittest

from widgets import qtapp
from incad.qt import QtCore
from incad.features.common import Field
from incad.ui.feature_dialog import FeatureDialog, step_text

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

    def test_many_choices_wrap_into_rows(self):
        """The user: the Move Solid window was too wide (seven snap types in one row). Four per row at most."""
        from incad.ui.feature_dialog import ChoiceField
        seven = tuple(("c%d" % i, "Choice %d" % i) for i in range(7))
        w = ChoiceField(seven)
        w.show()
        qtapp.app().processEvents()
        first, fifth = w.button("c0"), w.button("c4")
        self.assertEqual(fifth.x(), first.x())
        self.assertGreater(fifth.y(), first.y())
        w.close()

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

    def test_undo_and_redo_step_through_the_changes_made_in_the_dialog(self):
        """Undo while a dialog is open reverts the last change made in it (Inventor's dialogs), redo puts it back;
        the values the dialog opened with are the floor."""
        w = self.d.field("distance")
        w.setText("25 mm")
        w.editingFinished.emit()
        self.d.field("operation").button("cut").click()
        self.assertEqual(len(self.seen), 2)
        self.assertTrue(self.d.undo_change())
        self.assertEqual(self.d.values()["operation"], "join")
        self.assertEqual(self.seen[-1]["operation"], "join", "the undo previews like any change")
        self.assertTrue(self.d.undo_change())
        self.assertEqual(self.d.values()["distance"], "10 mm")
        self.assertFalse(self.d.undo_change(), "nothing before the values the dialog opened with")
        self.assertTrue(self.d.redo_change())
        self.assertEqual(self.d.values()["distance"], "25 mm")
        w.setText("40 mm")
        w.editingFinished.emit()
        self.assertFalse(self.d.redo_change(), "a new change drops the redo trail")
        self.assertTrue(self.d.undo_change())
        self.assertEqual(self.d.values()["distance"], "25 mm")

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


class SmallMovableTest(unittest.TestCase):
    """The user: "these windows sometimes take up more space than half the screen ... move them, or make them smaller"."""
    def setUp(self):
        qtapp.app()
        from incad.qt import QtWidgets
        self.view = QtWidgets.QWidget()
        self.view.resize(1000, 700)
        self.view.show()
        FeatureDialog.spot = None
        self.d = FeatureDialog("Snap Fit", "incad", FIELDS, {"operation": "join", "extent": "distance",
                                                            "to_face": "", "distance": "10 mm", "flip": False},
                               parent=self.view)
        self.d.place()
        self.d.show()
        qtapp.app().processEvents()

    def tearDown(self):
        self.d.close()
        self.view.close()
        FeatureDialog.spot = None

    def test_a_long_hint_keeps_the_dialog_narrow_and_folds(self):
        narrow = self.d.width()
        hint = ("A hook stands on every line of the sketch: draw the line on top of the wall. " + "More words. " * 20)
        self.d.set_info(hint)
        qtapp.app().processEvents()
        self.assertLessEqual(self.d.width(), narrow + 2, "the hint wraps at the fields' width")
        self.assertEqual(self.d.info_text(), hint)
        self.assertNotIn("More words", self.d._info.text(), "folded: the first sentence only")
        self.d._toggle_info()
        self.assertIn("More words", self.d._info.text())

    def test_the_title_drags_it_and_the_next_one_opens_there(self):
        from PySide6 import QtTest
        title = self.d.findChild(QtCore.QObject, "InCadDialogTitle")
        start = self.d.pos()
        at = title.mapTo(self.d, title.rect().center())
        QtTest.QTest.mousePress(self.d, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, at)
        QtTest.QTest.mouseMove(self.d, at + QtCore.QPoint(300, 200))
        QtTest.QTest.mouseRelease(self.d, QtCore.Qt.LeftButton, QtCore.Qt.NoModifier, at + QtCore.QPoint(300, 200))
        self.assertEqual(self.d.pos(), start + QtCore.QPoint(300, 200))
        other = FeatureDialog("Boss", "incad", FIELDS, {}, parent=self.view)
        other.place()
        self.assertEqual(other.pos(), self.d.pos())
        self.d.move(self.d.kept_inside(QtCore.QPoint(5000, 5000)))
        self.assertLess(self.d.y(), self.view.height(), "never dragged out of reach")
        other.close()


class TogglesTest(unittest.TestCase):
    def test_each_button_on_or_off_by_itself(self):
        qtapp.app()
        fields = (Field("skip", "Leave out", "toggles", (("1", "1"), ("2", "2"), ("3", "3")), ""),)
        d = FeatureDialog("Boss", "incad", fields, {"skip": "2"})
        seen = []
        d.changed.connect(lambda v: seen.append(v["skip"]))
        self.assertEqual(d.values()["skip"], "2")
        d.field("skip").button("3").click()
        self.assertEqual(d.values()["skip"], "2,3")
        d.field("skip").button("2").click()
        self.assertEqual(seen[-1], "3")
        d.close()


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

    def test_a_click_on_a_field_the_dialog_made_active_keeps_it_active(self):
        """The dialog activates a field by itself (at the start, or when a choice shows it); the user's habitual
        click on its Select… button must start picking, not stop it. A second click stops it."""
        self.d.set_active_pick("edges")
        self.d.field("edges").click()
        self.assertEqual(self.d.active_pick(), "edges")
        self.assertTrue(self.d.field("edges").isChecked())
        self.d.field("edges").click()
        self.assertIsNone(self.d.active_pick())


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


class RescueButtonTest(unittest.TestCase):
    """An error may come with a way around it: a button under the message that runs the kind's rescue."""

    def setUp(self):
        qtapp.app()
        self.d = FeatureDialog("Shell", "incad", PICK_FIELDS, {"edges": "", "plane": "", "radius": "1 mm"})

    def test_rescue_button_shows_with_the_error_and_runs_its_callable(self):
        calls = []
        self.d.set_error("Shell: FreeCAD can't hollow this", ("Shell before Thread", lambda: calls.append(1)))
        self.assertTrue(self.d.rescue_button.isVisibleTo(self.d))
        self.assertEqual(self.d.rescue_button.text(), "Shell before Thread")
        self.assertFalse(self.d.ok_button.isEnabled())
        self.d.rescue_button.click()
        self.assertEqual(calls, [1])
        self.d.set_error("")
        self.assertFalse(self.d.rescue_button.isVisibleTo(self.d))
        self.d.set_error("plain failure")
        self.assertFalse(self.d.rescue_button.isVisibleTo(self.d), "no rescue: no button")


class StepTextTest(unittest.TestCase):
    """The ± arrows of a value field: 1 of the shown unit (1 mm, 1°, 1 count; 1/16 in), Shift ×10, a formula
    cannot be stepped, a length never goes below zero."""

    def test_lengths_counts_and_angles(self):
        self.assertEqual(step_text("10 mm", 1, "value_length"), "11 mm")
        self.assertEqual(step_text("10.5 mm", -1, "value_length"), "9.5 mm")
        self.assertEqual(step_text("10 mm", 10, "value_length"), "20 mm")
        self.assertEqual(step_text("2", -1, "value_length"), "1")
        self.assertEqual(step_text("360°", 10, "value_angle"), "370°")
        self.assertEqual(step_text("30 °", -1, "value_angle"), "29 °")
        self.assertEqual(step_text("0.5 in", 1, "value_length"), "0.5625 in")
        self.assertEqual(step_text("12mm", 1, "value_length"), "13mm")
        self.assertEqual(step_text("  7 mm ", 1, "value_length"), "8 mm")

    def test_floors_and_formulas(self):
        self.assertEqual(step_text("0 mm", -1, "value_length"), "0 mm")
        self.assertEqual(step_text("0.5 mm", -1, "value_length"), "0 mm")
        self.assertEqual(step_text("-5°", -1, "value_angle"), "-6°")
        self.assertIsNone(step_text("d0 / 1.5", 1, "value_length"))
        self.assertIsNone(step_text("", 1, "value_length"))
        self.assertIsNone(step_text("10 mm + 2", 1, "value_length"))


class StepButtonsTest(unittest.TestCase):
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

    def test_each_press_steps_and_previews_at_once(self):
        up, down = self.d.step_buttons("distance")
        up.click()
        self.assertEqual(self.d.field("distance").text(), "11 mm")
        self.assertEqual([v["distance"] for v in self.seen], ["11 mm"], "previewed without waiting for the pause")
        down.click()
        down.click()
        self.assertEqual(self.d.field("distance").text(), "9 mm")
        self.assertEqual(len(self.seen), 3)
        self.assertTrue(self.d.undo_change())
        self.assertEqual(self.d.field("distance").text(), "10 mm", "each press is one undo step in the dialog")

    def test_shift_steps_by_ten(self):
        from PySide6.QtTest import QTest
        up, down = self.d.step_buttons("distance")
        QTest.mouseClick(up, QtCore.Qt.LeftButton, QtCore.Qt.ShiftModifier)
        self.assertEqual(self.d.field("distance").text(), "20 mm")

    def test_arrow_keys_in_the_field_step_too(self):
        from PySide6.QtTest import QTest
        w = self.d.field("distance")
        w.setFocus()
        QTest.keyClick(w, QtCore.Qt.Key_Up)
        self.assertEqual(w.text(), "11 mm")
        QTest.keyClick(w, QtCore.Qt.Key_Down, QtCore.Qt.ShiftModifier)
        self.assertEqual(w.text(), "1 mm")
        self.assertEqual([v["distance"] for v in self.seen], ["11 mm", "1 mm"])

    def test_a_formula_disables_the_arrows(self):
        up, down = self.d.step_buttons("distance")
        self.d.field("distance").setText("d0 / 1.5")
        self.assertFalse(up.isEnabled() or down.isEnabled())
        up.click()
        self.assertEqual(self.d.field("distance").text(), "d0 / 1.5")
        self.d.field("distance").setText("12 mm")
        self.assertTrue(up.isEnabled() and down.isEnabled())

    def test_a_held_arrow_lets_go_after_a_slow_preview(self):
        """The user: the pitch climbed by itself to 1243 mm — the arrow's auto-repeat went on, one millimetre a
        repeat, its release lost while a slow preview held the window. A repeat after such a pause lets the button
        go; a held arrow with quick previews keeps stepping."""
        import time
        up, _down = self.d.step_buttons("distance")
        up.setDown(True)
        up._last_step = time.monotonic()
        up.clicked.emit()  # an auto-repeat (the button still down) right away: steps
        self.assertEqual(self.d.field("distance").text(), "11 mm")
        up.setDown(True)
        up._last_step = time.monotonic() - 2.0  # the next repeat 2 s later: the preview held the window
        up.clicked.emit()
        self.assertEqual(self.d.field("distance").text(), "11 mm", "no step")
        self.assertFalse(up.isDown(), "the button let go")

    def test_the_arrows_hide_with_their_row(self):
        up, down = self.d.step_buttons("distance")
        self.d.field("extent").button("to").click()
        self.assertFalse(self.d.row_visible("distance"))
        self.assertFalse(up.isVisible() or down.isVisible())


LOFT_FIELDS = (
    Field("sections", "Sections", "picks", pick="sketch", listed=True),
    Field("ruled", "Ruled", "bool", default=False),
)


class SectionListTest(unittest.TestCase):
    """Loft's sections as Inventor shows them: a numbered list under the field, each row removable and movable;
    the empty field says that several sketches are picked, in order."""

    def setUp(self):
        qtapp.app()
        self.d = FeatureDialog("Loft", "incad", LOFT_FIELDS, {"sections": "", "ruled": False})
        self.seen, self.edited = [], []
        self.d.changed.connect(lambda v: self.seen.append(v["sections"]))
        self.d.picksEdited.connect(self.edited.append)
        self.d.show()

    def tearDown(self):
        self.d.close()

    def test_empty_field_explains_itself(self):
        self.assertEqual(self.d.list_rows("sections"), [])
        self.assertIn("in order", self.d.pick_text("sections"))
        self.assertLessEqual(len(self.d.pick_text("sections")), 26, "short enough to show whole")

    def test_a_reason_while_still_picking_is_quiet(self):
        """At the start nothing is wrong yet: the reason shows grey, not as a red error; OK stays off."""
        self.d.set_error("Pick at least two section sketches, in order", waiting=True)
        self.assertTrue(self.d.error_waiting())
        self.assertFalse(self.d.ok_button.isEnabled())
        self.d.set_error("The sections are out of order")
        self.assertFalse(self.d.error_waiting())

    def test_rows_follow_the_picks(self):
        self.d.set_pick("sections", "SkA,SkB,SkC")
        self.assertEqual(self.d.list_rows("sections"), ["1.  SkA", "2.  SkB", "3.  SkC"])
        self.assertIn("add", self.d.pick_text("sections"))
        self.d.set_values({"sections": "SkC"})
        self.assertEqual(self.d.list_rows("sections"), ["1.  SkC"])

    def test_remove_and_reorder(self):
        self.d.set_pick("sections", "SkA,SkB,SkC")
        self.seen.clear()
        self.d.row_button("sections", 1, "remove").click()
        self.assertEqual(self.d.values()["sections"], "SkA,SkC")
        self.d.row_button("sections", 1, "up").click()
        self.assertEqual(self.d.values()["sections"], "SkC,SkA")
        self.d.row_button("sections", 0, "down").click()
        self.assertEqual(self.d.values()["sections"], "SkA,SkC")
        self.assertEqual(self.seen, ["SkA,SkC", "SkC,SkA", "SkA,SkC"], "each edit previews")
        self.assertEqual(self.edited, ["sections"] * 3)
        self.assertFalse(self.d.row_button("sections", 0, "up").isEnabled())
        self.assertFalse(self.d.row_button("sections", 1, "down").isEnabled())
        self.assertTrue(self.d.undo_change())
        self.assertEqual(self.d.values()["sections"], "SkC,SkA")


class FieldsAreaTest(unittest.TestCase):
    def setUp(self):
        qtapp.app()

    def test_a_tall_dialog_scrolls_its_fields_and_keeps_ok_in_the_view(self):
        """The user: Worm's fields ran off the screen and OK with them."""
        from incad.qt import QtWidgets
        parent = QtWidgets.QWidget()
        parent.resize(600, 420)
        fields = tuple(Field("v%d" % i, "Value %d" % i, "value_length", default="1 mm") for i in range(20))
        d = FeatureDialog("Tall", "incad", fields, {f.key: "1 mm" for f in fields}, parent=parent)
        parent.show()
        d.show()
        d.adjustSize()
        qtapp.app().processEvents()
        try:
            self.assertLessEqual(d.height(), parent.height() - 16, "inside the view")
            ok = d.ok_button.mapTo(parent, d.ok_button.rect().bottomLeft())
            self.assertLess(ok.y(), parent.height(), "OK in sight")
            self.assertTrue(d._fields_area.verticalScrollBar().maximum() > 0, "the fields scroll")
            area = d._fields_area
            step = d._steppers["v0"][1]
            right = step.mapTo(area.viewport(), step.rect().topRight()).x()
            self.assertLessEqual(right, area.viewport().width(), "the ▲▼ stay in sight beside the scroll bar")
        finally:
            parent.close()
