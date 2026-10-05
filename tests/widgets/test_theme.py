import unittest

from incad.core import prefs
from incad.ui import theme


class ThemeTest(unittest.TestCase):
    def setUp(self):
        prefs.use_memory_backend()

    def test_resolve(self):
        self.assertEqual(theme.resolve("auto", True), "dark")
        self.assertEqual(theme.resolve("auto", False), "light")
        self.assertEqual(theme.resolve("light", True), "light")
        self.assertEqual(theme.resolve("dark", False), "dark")

    def test_toggled(self):
        self.assertEqual(theme.toggled("light"), "dark")
        self.assertEqual(theme.toggled("dark"), "light")

    def test_current_uses_pref(self):
        prefs.set_theme("dark")
        self.assertEqual(theme.current(), "dark")

    def test_stylesheet_filled_in(self):
        for t in ("light", "dark"):
            qss = theme.stylesheet(t)
            self.assertIn(theme.PALETTES[t]["panel"], qss)
            self.assertIn("#InCadRibbon", qss)
            self.assertNotIn("{panel}", qss)

    def test_palettes_have_same_keys(self):
        self.assertEqual(set(theme.PALETTES["light"]), set(theme.PALETTES["dark"]))

    def test_view_params(self):
        v = theme.view_params("dark")
        self.assertEqual(v["Gradient"], ("Bool", True))
        self.assertEqual(v["BackgroundColor2"], ("Unsigned", 0x2B3440FF))
        self.assertEqual(set(v), set(theme.VIEW_KEYS))

    def test_icon_px(self):
        self.assertEqual(theme.ICON_PX, {"small": 16, "medium": 24, "large": 32})
