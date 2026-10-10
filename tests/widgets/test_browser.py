import unittest

from widgets import qtapp
from incad.qt import QtCore, QtGui, QtWidgets
from incad.core.nodes import Node
from incad.ui import theme
from incad.ui.browser import ModelBrowser


def sample():
    return [Node("part", "Bracket", children=[
        Node("origin", "Origin", "Origin", children=[Node("origin_item", "XY Plane", "XY_Plane")]),
        Node("feature", "Extrusion1", "Pad", children=[Node("sketch", "Sketch1", "Sketch")]),
        Node("end_of_part", "End of Part"),
        Node("feature", "Fillet1", "Fillet", "rolled_back"),
        Node("feature", "Broken", "Pocket", "error", "Pocket: nothing to cut"),
    ])]


class BrowserTest(unittest.TestCase):
    def setUp(self):
        qtapp.app()
        self.b = ModelBrowser("light")
        self.b.set_nodes(sample())
        self.events = []
        for sig in ("featureActivated", "endOfPartMoved", "actionTriggered", "parameterRemoved"):
            getattr(self.b, sig).connect(lambda v, s=sig: self.events.append((s, v)))
        self.b.parameterSet.connect(lambda n, t: self.events.append(("parameterSet", n, t)))

    def test_rows(self):
        self.assertEqual(self.b.tree_rows(), [
            (0, "Bracket", "part", ""), (1, "Origin", "origin", ""), (2, "XY Plane", "origin_item", ""),
            (1, "Extrusion1", "feature", ""), (2, "Sketch1", "sketch", ""), (1, "End of Part", "end_of_part", ""),
            (1, "Fillet1", "feature", "rolled_back"), (1, "Broken", "feature", "error")])

    def test_error_color_and_tooltip(self):
        item = self.b.item_by_label("Broken")
        self.assertEqual(item.foreground(0).color(), QtGui.QColor(theme.PALETTES["light"]["error"]))
        self.assertEqual(item.toolTip(0), "Pocket: nothing to cut")

    def test_origin_collapsed_features_expanded(self):
        self.assertFalse(self.b.item_by_label("Origin").isExpanded())
        self.assertTrue(self.b.item_by_label("Extrusion1").isExpanded())

    def test_double_click(self):
        self.b.tree.itemDoubleClicked.emit(self.b.item_by_label("Sketch1"), 0)
        self.assertEqual(self.events, [("featureActivated", "Sketch")])

    def test_drop_end_of_part(self):
        self.b.drop_end_of_part_on(self.b.item_by_label("Fillet1"))
        self.b.drop_end_of_part_on(self.b.item_by_label("XY Plane"))
        self.assertEqual(self.events, [("endOfPartMoved", "Fillet"), ("endOfPartMoved", "")])

    def test_drop_on_the_feature_right_above_the_marker_means_before_it(self):
        """Extrusion1 sits right above End of Part: 'after it' is where the marker is, so a drop on it (any half,
        or on its sketch) puts End of Part before it — the user's drag up one row that did nothing."""
        self.b.drop_end_of_part_on(self.b.item_by_label("Extrusion1"))
        self.b.drop_end_of_part_on(self.b.item_by_label("Sketch1"))
        self.b.drop_end_of_part_on(self.b.item_by_label("Extrusion1"), above=False)
        self.assertEqual(self.events, [("endOfPartMoved", ""), ("endOfPartMoved", ""), ("endOfPartMoved", "")])

    def test_drop_on_a_rolled_back_feature_applies_it(self):
        """Fillet1 sits BELOW End of Part (rolled back): dropping on it, either half, brings the marker down to
        include it (dragging the marker back down onto a rolled-back feature was landing on the upper half and
        reading as 'before it', where the marker already was)."""
        self.b.drop_end_of_part_on(self.b.item_by_label("Fillet1"), above=True)
        self.b.drop_end_of_part_on(self.b.item_by_label("Fillet1"), above=False)
        self.assertEqual(self.events, [("endOfPartMoved", "Fillet"), ("endOfPartMoved", "Fillet")])

    def test_drop_on_the_upper_half_of_an_applied_feature_puts_end_of_part_before_it(self):
        """Extrusion1 is applied (above the marker) and is the first feature: a drop on its upper half rolls back
        to before it (empty name)."""
        self.b.drop_end_of_part_on(self.b.item_by_label("Extrusion1"), above=True)
        self.assertEqual(self.events, [("endOfPartMoved", "")])

    def test_drop_target_by_row_half(self):
        self.b.resize(260, 500)
        self.b.show()
        tree = self.b.tree
        fillet = self.b.item_by_label("Fillet1")
        rect = tree.visualItemRect(fillet)
        self.assertEqual(tree.drop_target(rect.center() - QtCore.QPoint(0, rect.height() // 3)), (fillet, True))
        self.assertEqual(tree.drop_target(rect.center() + QtCore.QPoint(0, rect.height() // 3)), (fillet, False))
        self.assertEqual(tree.drop_target(tree.visualItemRect(self.b.item_by_label("End of Part")).center()),
                         (None, False))

    def test_right_click_requests_marking_menu(self):
        seen = []
        self.b.markingMenuRequested.connect(lambda name, pos: seen.append(name))
        self.b.resize(260, 500)
        self.b.show()
        qtapp.app().processEvents()
        for label in ("Fillet1", "Origin"):
            rect = self.b.tree.visualItemRect(self.b.item_by_label(label))
            self.b._on_context_menu(rect.center())
        self.b.hide()
        self.assertEqual(seen, ["Fillet"])
        self.assertEqual(self.b.tree.currentItem().text(0), "Fillet1")

    def test_actions_for_plain_file(self):
        self.b.set_nodes([Node("message", "Not an InCad part"), Node("action", "Convert to InCad Part", "convert")])
        self.b.tree.itemDoubleClicked.emit(self.b.item_by_label("Convert to InCad Part"), 0)
        self.assertEqual(self.events, [("actionTriggered", "convert")])

    def test_parameters_show_formula_and_result(self):
        self.b.set_parameters([("Width", "", "80 mm"), ("HoleD", "Width/8", "10 mm")])
        self.assertEqual(self.b.parameter_rows(), [("Width", "80 mm", "80 mm"), ("HoleD", "Width/8", "10 mm")])
        self.assertEqual(self.events, [])

    def test_edit_value_emits(self):
        self.b.set_parameters([("Width", "", "80 mm")])
        self.b.params.item(0, 1).setText("90 mm")
        self.assertEqual(self.events, [("parameterSet", "Width", "90 mm")])

    def test_add_row_emits_when_complete(self):
        r = self.b.add_parameter_row()
        self.b.params.item(r, 0).setText("Gap")
        self.assertEqual(self.events, [])
        self.b.params.item(r, 1).setText("0.2 mm")
        self.assertEqual(self.events, [("parameterSet", "Gap", "0.2 mm")])

    def test_remove(self):
        self.b.set_parameters([("Width", "", "80 mm")])
        self.b.params.setCurrentCell(0, 0)
        self.b.remove_selected_parameter()
        self.assertEqual(self.events, [("parameterRemoved", "Width")])
        r = self.b.add_parameter_row()
        self.b.params.setCurrentCell(r, 0)
        self.b.remove_selected_parameter()
        self.assertEqual(self.b.params.rowCount(), 1)

    def test_theme_redraw(self):
        self.b.set_theme("dark")
        self.assertEqual(self.b.item_by_label("Broken").foreground(0).color(),
                         QtGui.QColor(theme.PALETTES["dark"]["error"]))


class ParametersFitTest(unittest.TestCase):
    def test_columns_fit_the_panel_without_horizontal_scrolling(self):
        qtapp.app()
        b = ModelBrowser("light")
        b.set_parameters([("HoleD", "Width / 8", "10 mm"), ("Width", "", "80 mm")])
        b.resize(230, 600)
        b.show()
        qtapp.app().processEvents()
        self.assertEqual(b.params.horizontalScrollBar().maximum(), 0)
        b.hide()


class MultiSolidTest(unittest.TestCase):
    def test_end_of_part_on_second_solid_feature_names_that_feature(self):
        qtapp.app()
        b = ModelBrowser("light")
        b.set_nodes([Node("part", "Bracket", children=[
            Node("solids", "Solid Bodies (2)", children=[
                Node("body", "Solid1", "Body"),
                Node("body", "Solid2", "Body001", children=[
                    Node("feature", "Pad001", "Pad001", children=[Node("sketch", "Sketch001", "Sketch001")]),
                    Node("end_of_part", "End of Part")])]),
            Node("feature", "Pad", "Pad")])])
        seen = []
        b.endOfPartMoved.connect(seen.append)
        b.drop_end_of_part_on(b.item_by_label("Pad001"))
        b.drop_end_of_part_on(b.item_by_label("Sketch001"))
        self.assertEqual(seen, ["Pad001", "Pad001"])


class ParametersLockTest(unittest.TestCase):
    def test_editing_disabled_outside_incad_parts(self):
        qtapp.app()
        b = ModelBrowser("light")
        seen = []
        b.parameterSet.connect(lambda n, t: seen.append(n))
        b.set_parameters_enabled(False)
        self.assertFalse(b.add_button.isEnabled())
        self.assertFalse(b.remove_button.isEnabled())
        self.assertEqual(b.add_parameter_row(), -1)
        self.assertEqual(b.params.rowCount(), 0)
        b.set_parameters_enabled(True)
        r = b.add_parameter_row()
        b.params.item(r, 0).setText("Gap")
        b.params.item(r, 1).setText("1 mm")
        self.assertEqual(seen, ["Gap"])


class ParametersTypingTest(unittest.TestCase):
    """What a user does: click +, type a name, Tab, type a value, Enter."""

    def test_plus_then_typing_creates_the_parameter(self):
        from incad.qt import QtCore
        from PySide6.QtTest import QTest
        qtapp.app()
        b = ModelBrowser("light")
        seen = []
        b.parameterSet.connect(lambda n, t: seen.append((n, t)))
        b.resize(260, 600)
        b.show()
        b.activateWindow()
        QTest.mouseClick(b.add_button, QtCore.Qt.LeftButton)
        qtapp.app().processEvents()
        QTest.keyClicks(qtapp.app().focusWidget(), "Width")
        QTest.keyClick(qtapp.app().focusWidget(), QtCore.Qt.Key_Tab)
        qtapp.app().processEvents()
        QTest.keyClicks(qtapp.app().focusWidget(), "80 mm")
        QTest.keyClick(qtapp.app().focusWidget(), QtCore.Qt.Key_Return)
        qtapp.app().processEvents()
        b.hide()
        self.assertEqual(seen, [("Width", "80 mm")])

    def test_typing_on_an_existing_value_edits_it(self):
        from incad.qt import QtCore
        from PySide6.QtTest import QTest
        qtapp.app()
        b = ModelBrowser("light")
        b.set_parameters([("Width", "", "80 mm")])
        seen = []
        b.parameterSet.connect(lambda n, t: seen.append((n, t)))
        b.resize(260, 600)
        b.show()
        b.params.setFocus()
        b.params.setCurrentCell(0, 1)
        QTest.keyClicks(b.params, "9")  # typing on a selected cell opens its editor with that key
        qtapp.app().processEvents()
        QTest.keyClicks(qtapp.app().focusWidget(), "0 mm")
        QTest.keyClick(qtapp.app().focusWidget(), QtCore.Qt.Key_Return)
        qtapp.app().processEvents()
        b.hide()
        self.assertEqual(seen, [("Width", "90 mm")])

    def test_disabled_plus_explains_why(self):
        qtapp.app()
        b = ModelBrowser("light")
        b.set_parameters_enabled(False)
        self.assertIn("InCad part", b.add_button.toolTip())
        b.set_parameters_enabled(True)
        self.assertEqual(b.add_button.toolTip(), "Add parameter")


class ModelParametersTest(unittest.TestCase):
    def setUp(self):
        qtapp.app()
        self.b = ModelBrowser("light")
        self.b.set_parameters([("Width", "", "80 mm")], [("d0", "", "40 mm"), ("d1", "d0 * 2", "80 mm")])
        self.events = []
        self.b.parameterSet.connect(lambda n, t: self.events.append(("set", n, t)))
        self.b.parameterRenamed.connect(lambda o, n: self.events.append(("rename", o, n)))
        self.b.parameterClicked.connect(lambda n: self.events.append(("click", n)))
        self.b.parameterRemoved.connect(lambda n: self.events.append(("remove", n)))

    def test_model_rows_first(self):
        self.assertEqual(self.b.parameter_rows(),
                         [("d0", "40 mm", "40 mm"), ("d1", "d0 * 2", "80 mm"), ("Width", "80 mm", "80 mm")])

    def test_rename_model_parameter(self):
        self.b.params.item(0, 0).setText("Len")
        self.assertEqual(self.events, [("rename", "d0", "Len")])

    def test_edit_model_value(self):
        self.b.params.item(1, 1).setText("d0 * 3")
        self.assertEqual(self.events, [("set", "d1", "d0 * 3")])

    def test_model_rows_ask_to_be_removed(self):
        self.b.params.setCurrentCell(0, 0)
        self.b.remove_selected_parameter()
        self.assertEqual(self.events, [("remove", "d0")])

    def test_click_on_name_reports_it(self):
        self.b.params.cellClicked.emit(2, 0)
        self.b.params.cellClicked.emit(2, 1)
        self.assertEqual(self.events, [("click", "Width")])


class DetailTest(unittest.TestCase):
    def test_detail_is_shown_but_label_stays(self):
        qtapp.app()
        b = ModelBrowser("light")
        b.set_nodes([Node("part", "P", children=[Node("sketch", "Sketch1", "Sketch", detail="3 DOF")])])
        item = b.item_by_label("Sketch1")
        self.assertIn("3 DOF", item.text(0))
        self.assertEqual([r[1] for r in b.tree_rows()], ["P", "Sketch1"])


class TypingBeatsShortcutsTest(unittest.TestCase):
    def _override(self, widget, key, text, mods):
        ev = QtGui.QKeyEvent(QtCore.QEvent.ShortcutOverride, key, mods, text)
        ev.ignore()
        qtapp.app().sendEvent(widget, ev)
        return ev.isAccepted()

    def test_plain_keys_go_to_the_table_and_tree(self):
        qtapp.app()
        b = ModelBrowser("light")
        N = QtCore.Qt.NoModifier
        self.assertTrue(self._override(b.params, QtCore.Qt.Key_S, "s", N))
        self.assertTrue(self._override(b.params, QtCore.Qt.Key_D, "D", QtCore.Qt.ShiftModifier))
        self.assertTrue(self._override(b.tree, QtCore.Qt.Key_L, "l", N))
        self.assertFalse(self._override(b.params, QtCore.Qt.Key_N, "n", QtCore.Qt.ControlModifier))  # ⌘N still works
        self.assertFalse(self._override(b.params, QtCore.Qt.Key_F7, "", N))


class AssemblyIconsTest(unittest.TestCase):
    def test_assembly_rows_have_icons(self):
        from incad.ui import browser
        for kind in ("assembly", "component", "relationships", "joint"):
            self.assertIn(kind, browser.KIND_ICONS)


class OriginRowsTest(unittest.TestCase):
    def test_double_click_and_right_click_on_an_origin_plane(self):
        qtapp.app()
        b = ModelBrowser("light")
        b.set_nodes([Node("part", "P", children=[Node("origin", "Origin", "Origin", children=[
            Node("origin_item", "XY Plane", "XY_Plane")])])])
        seen = []
        b.featureActivated.connect(lambda n: seen.append(("edit", n)))
        b.markingMenuRequested.connect(lambda n, pos: seen.append(("menu", n)))
        item = b.item_by_label("XY Plane")
        b._on_double_click(item)
        b.tree.scrollToItem(item)
        b._on_context_menu(b.tree.visualItemRect(item).center())
        self.assertEqual(seen, [("edit", "XY_Plane"), ("menu", "XY_Plane")])


class HiddenRowsTest(unittest.TestCase):
    def test_hidden_rows_are_dimmed_and_multi_selection_reports_names(self):
        qtapp.app()
        b = ModelBrowser("light")
        b.set_nodes([Node("part", "P", "Body", children=[
            Node("origin", "Origin", "Origin", children=[Node("origin_item", "XY Plane", "XY_Plane", "hidden"),
                                                         Node("origin_item", "XZ Plane", "XZ_Plane")]),
            Node("sketch", "Path", "Path", "hidden")])])
        dim = QtGui.QColor(theme.PALETTES["light"]["text_dim"])
        self.assertEqual(b.item_by_label("XY Plane").foreground(0).color(), dim)
        self.assertEqual(b.item_by_label("Path").foreground(0).color(), dim)
        self.assertNotEqual(b.item_by_label("XZ Plane").foreground(0).color(), dim)
        self.assertEqual(b.tree.selectionMode(), QtWidgets.QAbstractItemView.ExtendedSelection)
        b.item_by_label("XY Plane").setSelected(True)
        b.item_by_label("Path").setSelected(True)
        self.assertEqual(b.selected_names(), ["XY_Plane", "Path"])
