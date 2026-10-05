import unittest

from incad.core import prefs


class PrefsMemoryTest(unittest.TestCase):
    def setUp(self):
        prefs.use_memory_backend()

    def test_defaults(self):
        self.assertEqual(prefs.theme(), "auto")
        self.assertEqual(prefs.ribbon_size(), "large")
        self.assertEqual(prefs.default_units(), "mm")
        self.assertFalse(prefs.remember_new_choice())
        self.assertEqual(prefs.last_workbench(), "PartDesignWorkbench")
        self.assertEqual(prefs.takeover_snapshot(), "")

    def test_roundtrip(self):
        prefs.set_theme("dark")
        prefs.set_ribbon_size("small")
        prefs.set_default_units("in")
        prefs.set_remember_new_choice(True)
        prefs.set_last_workbench("SketcherWorkbench")
        prefs.set_takeover_snapshot('{"a": 1}')
        self.assertEqual(
            (prefs.theme(), prefs.ribbon_size(), prefs.default_units(), prefs.remember_new_choice(),
             prefs.last_workbench(), prefs.takeover_snapshot()),
            ("dark", "small", "in", True, "SketcherWorkbench", '{"a": 1}'))
        prefs.clear_takeover_snapshot()
        self.assertEqual(prefs.takeover_snapshot(), "")

    def test_invalid_values_rejected(self):
        for setter, bad in ((prefs.set_theme, "blue"), (prefs.set_ribbon_size, "huge"), (prefs.set_default_units, "cm")):
            with self.assertRaises(ValueError):
                setter(bad)

    def test_navigation_flag(self):
        self.assertTrue(prefs.navigation_enabled())
        prefs.set_navigation_enabled(False)
        self.assertFalse(prefs.navigation_enabled())

    def test_dimension_display(self):
        self.assertEqual(prefs.dimension_display(), "value")
        prefs.set_dimension_display("expression")
        self.assertEqual(prefs.dimension_display(), "expression")
        with self.assertRaises(ValueError):
            prefs.set_dimension_display("fancy")
