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
        prefs.set_ribbon_size("medium")
        prefs.set_default_units("in")
        prefs.set_remember_new_choice(True)
        prefs.set_last_workbench("SketcherWorkbench")
        prefs.set_takeover_snapshot('{"a": 1}')
        self.assertEqual(
            (prefs.theme(), prefs.ribbon_size(), prefs.default_units(), prefs.remember_new_choice(),
             prefs.last_workbench(), prefs.takeover_snapshot()),
            ("dark", "medium", "in", True, "SketcherWorkbench", '{"a": 1}'))
        prefs.clear_takeover_snapshot()
        self.assertEqual(prefs.takeover_snapshot(), "")

    def test_new_remembers_part_or_assembly(self):
        """The user ticked 'Remember my choice' at the start and could no longer make an assembly with New."""
        self.assertEqual(prefs.new_kind(), "part")
        prefs.set_new_kind("assembly")
        self.assertEqual(prefs.new_kind(), "assembly")

    def test_a_saved_small_ribbon_becomes_the_default(self):
        prefs._s().set("str", "RibbonSize", "small")  # saved before the small size was removed
        self.assertEqual(prefs.ribbon_size(), "large")

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
