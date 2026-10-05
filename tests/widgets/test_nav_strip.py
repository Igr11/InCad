import unittest

from widgets import qtapp
from incad.qt import QtCore
from incad.core.commands import Command, Registry
from incad.ui.nav_strip import NavStrip


class NavStripTest(unittest.TestCase):
    def setUp(self):
        qtapp.app()
        self.ran = []
        self.mode = None
        self.reg = Registry()
        self.reg.register(Command(id="view.zoom_all", label="Zoom All", icon="zoom_all",
                                  handler=lambda: self.ran.append("zoom")))
        self.reg.register(Command(id="nav.orbit", label="Orbit", icon="orbit", handler=self.toggle,
                                  checkable=True, is_checked=lambda: self.mode == "orbit"))
        self.strip = NavStrip(self.reg, "light")

    def toggle(self):
        self.mode = None if self.mode == "orbit" else "orbit"

    def test_only_registered_commands(self):
        self.assertIsNotNone(self.strip.button("view.zoom_all"))
        self.assertIsNone(self.strip.button("view.home"))

    def test_click_runs(self):
        self.strip.button("view.zoom_all").click()
        self.assertEqual(self.ran, ["zoom"])

    def test_checkable_follows_state(self):
        self.strip.button("nav.orbit").click()
        self.assertTrue(self.strip.button("nav.orbit").isChecked())
        self.strip.button("nav.orbit").click()
        self.assertFalse(self.strip.button("nav.orbit").isChecked())

    def test_place(self):
        self.strip.adjustSize()
        self.strip.place(QtCore.QRect(0, 0, 1000, 700))
        self.assertEqual(self.strip.x() + self.strip.width(), 1000 - 14)
        self.assertGreaterEqual(self.strip.y(), 140)
