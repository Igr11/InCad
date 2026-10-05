import unittest

from widgets import qtapp
from incad.qt import QtCore
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
        cases = (("small", 16, QtCore.Qt.ToolButtonIconOnly),
                 ("medium", 24, QtCore.Qt.ToolButtonTextUnderIcon),
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
        self.rb.set_size("small")
        self.rb.set_size("small")
        self.assertEqual(seen, ["small"])

    def test_bad_size(self):
        with self.assertRaises(ValueError):
            self.rb.set_size("huge")

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
        self.assertEqual([a.text() for a in acts], ["Small", "Medium", "Large"])
        self.assertEqual([a.isChecked() for a in acts], [False, False, True])
        acts[0].trigger()
        self.assertEqual(self.rb.current_size(), "small")

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
