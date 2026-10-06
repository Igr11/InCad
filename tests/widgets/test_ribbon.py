import unittest

from widgets import qtapp
from incad.qt import QtCore, QtWidgets
from incad.core.commands import Command, Registry
from incad.ui import ribbon_layout
from incad.ui.ribbon import Ribbon


class RibbonTest(unittest.TestCase):
    def setUp(self):
        qtapp.app()
        self.ran = []
        self.checked = False
        self.reg = Registry()
        for i in ("a", "b", "c"):
            self.reg.register(Command(id=i, label=i.upper(), icon="incad", handler=lambda i=i: self.ran.append(i)))
        self.reg.register(Command(id="t", label="Toggle", icon="incad", handler=lambda: None,
                                  checkable=True, is_checked=lambda: self.checked))
        self.layout = {
            "part": [["Model", [["G1", ["a", "missing"]], ["Empty", ["missing"]]]],
                     ["Nothing", [["G", ["missing"]]]],
                     ["View", [["G2", ["b", "c", "t"]]]]],
            "empty": [["Start", [["New", ["a"]]]]],
        }
        self.rb = Ribbon(self.reg, self.layout, mode="part", size="large", theme="light")

    def test_tabs_skip_empty(self):
        self.assertEqual(self.rb.tab_names(), ["Model", "View"])

    def test_buttons_and_click(self):
        self.rb.button("a").click()
        self.assertEqual(self.ran, ["a"])
        self.assertIsNone(self.rb.button("missing"))

    def test_sizes(self):
        cases = (("medium", 24, QtCore.Qt.ToolButtonTextUnderIcon),
                 ("large", 32, QtCore.Qt.ToolButtonTextUnderIcon))
        for size, px, style in cases:
            self.rb.set_size(size)
            b = self.rb.button("a")
            self.assertEqual(b.iconSize().width(), px, size)
            self.assertEqual(b.toolButtonStyle(), style, size)
            self.assertEqual(self.rb.current_size(), size)

    def test_size_signal_once_per_change(self):
        seen = []
        self.rb.sizeChanged.connect(seen.append)
        self.rb.set_size("medium")
        self.rb.set_size("medium")
        self.assertEqual(seen, ["medium"])

    def test_bad_size(self):
        with self.assertRaises(ValueError):
            self.rb.set_size("huge")
        with self.assertRaises(ValueError):
            self.rb.set_size("small")  # removed: too small to use

    def test_theme_rebuild_keeps_tab(self):
        self.rb._tabs.setCurrentIndex(1)
        self.rb.set_theme("dark")
        self.assertEqual(self.rb.current_tab(), "View")

    def test_mode_switch(self):
        self.rb.set_mode("empty")
        self.assertEqual(self.rb.tab_names(), ["Start"])
        self.rb.set_mode("sketch")
        self.assertEqual(self.rb.tab_names(), [])

    def test_size_menu(self):
        m = self.rb.size_menu(None)
        acts = m.actions()
        self.assertEqual([a.text() for a in acts], ["Small", "Large"])
        self.assertEqual([a.isChecked() for a in acts], [False, True])
        acts[0].trigger()
        self.assertEqual(self.rb.current_size(), "medium")

    def test_checkable_reflects_state(self):
        self.assertFalse(self.rb.button("t").isChecked())
        self.checked = True
        self.rb.refresh_checks()
        self.assertTrue(self.rb.button("t").isChecked())

    def test_add_group(self):
        layout = {"part": [["Model", []]]}
        ribbon_layout.add_group("part", "Model", "Sketch", ["a"], layout)
        ribbon_layout.add_group("part", "Inspect", "Measure", ["b"], layout)
        self.assertEqual(layout, {"part": [["Model", [["Sketch", ["a"]]]], ["Inspect", [["Measure", ["b"]]]]]})


class SplitButtonTest(unittest.TestCase):
    def setUp(self):
        qtapp.app()
        self.ran = []
        self.reg = Registry()
        for i in ("r2", "rc", "r3"):
            self.reg.register(Command(id=i, label=i.upper(), icon="incad", handler=lambda i=i: self.ran.append(i)))
        self.layout = {"sketch": [["Sketch", [["Create", [["r2", "rc", "missing", "r3"]]]]]]}
        self.rb = Ribbon(self.reg, self.layout, mode="sketch", size="large", theme="light")

    def test_split_button_runs_the_default_and_lists_variants(self):
        b = self.rb.button("r2")
        self.assertIs(self.rb.button("r3"), b)
        self.assertEqual(b.text(), "R2")
        self.assertEqual([a.text() for a in b.menu().actions()], ["R2", "RC", "R3"])
        b.click()
        self.assertEqual(self.ran, ["r2"])

    def test_choosing_a_variant_runs_it_and_becomes_the_default(self):
        b = self.rb.button("r2")
        b.menu().actions()[2].trigger()
        self.assertEqual(self.ran, ["r3"])
        self.assertEqual(b.text(), "R3")
        b.click()
        self.assertEqual(self.ran, ["r3", "r3"])
        self.rb.set_theme("dark")  # rebuild keeps the choice
        self.assertEqual(self.rb.button("r2").text(), "R3")


class WideRibbonTest(unittest.TestCase):
    def test_many_buttons_never_widen_the_window(self):
        qtapp.app()
        reg = Registry()
        ids = ["c%d" % i for i in range(40)]
        for i in ids:
            reg.register(Command(id=i, label="Command %s" % i, icon="incad", handler=lambda: None))
        layout = {"part": [["Model", [["G%d" % g, ids[g * 5:(g + 1) * 5]] for g in range(8)]]]}
        rb = Ribbon(reg, layout, mode="part", size="large", theme="light")
        self.assertLess(rb.minimumSizeHint().width(), 700)
        rb.resize(600, rb.sizeHint().height())
        rb.show()
        self.assertTrue(rb.button("c39") is not None)


class CompactRibbonTest(unittest.TestCase):
    def setUp(self):
        qtapp.app()
        self.reg = Registry()
        for i in range(12):
            self.reg.register(Command(id="k%d" % i, label="Constraint %d" % i, icon="incad", handler=lambda: None))
        self.reg.register(Command(id="slot", label="Center-to-Center Slot", short="Slot", icon="incad",
                                  handler=lambda: None))
        self.layout = {"sketch": [["Sketch", [["Constrain", ["k%d" % i for i in range(12)], "stacked"],
                                              ["Create", ["slot"]]]]]}

    def test_stacked_group_is_small_icons_in_rows(self):
        rb = Ribbon(self.reg, self.layout, mode="sketch", size="large", theme="light")
        b = rb.button("k0")
        self.assertEqual(b.toolButtonStyle(), QtCore.Qt.ToolButtonIconOnly)
        self.assertEqual(b.iconSize().width(), 32)  # big enough to read on a large ribbon
        rb.show()
        rows = {rb.button("k%d" % i).mapTo(rb, QtCore.QPoint(0, 0)).y() for i in range(12)}
        self.assertEqual(len(rows), 2)
        medium = Ribbon(self.reg, self.layout, mode="sketch", size="medium", theme="light")
        self.assertEqual(medium.button("k0").iconSize().width(), 28)

    def test_short_label_on_the_button(self):
        rb = Ribbon(self.reg, self.layout, mode="sketch", size="large", theme="light")
        self.assertEqual(rb.button("slot").text(), "Slot")
        self.assertIn("Center-to-Center Slot", rb.button("slot").toolTip())

    def test_scrollbar_never_covers_the_labels(self):
        rb = Ribbon(self.reg, self.layout, mode="sketch", size="medium", theme="light")
        rb.resize(200, rb.sizeHint().height())
        rb.show()
        area = rb.findChild(QtWidgets.QScrollArea, "InCadRibbonPage")
        page = area.widget()
        self.assertGreaterEqual(area.height(), page.sizeHint().height() + area.horizontalScrollBar().sizeHint().height())


class StackedHeightTest(unittest.TestCase):
    def test_stacked_group_is_no_taller_than_a_normal_one(self):
        qtapp.app()
        reg = Registry()
        for i in range(10):
            reg.register(Command(id="k%d" % i, label="K%d" % i, icon="incad", handler=lambda: None))
        layout = {"sketch": [["Sketch", [["Big", ["k0"]], ["Constrain", ["k%d" % i for i in range(1, 10)], "stacked"]]]]}
        for size in ("medium", "large"):
            rb = Ribbon(reg, layout, mode="sketch", size=size, theme="light")
            rb.show()
            big = rb.button("k0").parentWidget().sizeHint().height()
            stacked = rb.button("k1").parentWidget().sizeHint().height()
            self.assertLessEqual(stacked, big + 12, size)  # readable icons cost the ribbon a few px
