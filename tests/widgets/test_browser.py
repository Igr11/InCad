import unittest

from widgets import qtapp
from incad.qt import QtCore, QtGui
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
        self.b.drop_end_of_part_on(self.b.item_by_label("Sketch1"))
        self.b.drop_end_of_part_on(self.b.item_by_label("XY Plane"))
        self.assertEqual(self.events, [("endOfPartMoved", "Fillet"), ("endOfPartMoved", "Pad"),
                                       ("endOfPartMoved", "")])

    def test_context_actions(self):
        texts = [t for t, _ in self.b.context_actions(self.b.item_by_label("Fillet1"))]
        self.assertEqual(texts, ["Edit", "Move End of Part Here"])
        dict(self.b.context_actions(self.b.item_by_label("Fillet1")))["Move End of Part Here"]()
        self.assertEqual(self.events, [("endOfPartMoved", "Fillet")])
        self.assertEqual(self.b.context_actions(self.b.item_by_label("Origin")), [])

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
        dict(b.context_actions(b.item_by_label("Pad001")))["Move End of Part Here"]()
        self.assertEqual(seen, ["Pad001", "Pad001", "Pad001"])


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
