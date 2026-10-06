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
        self.assertEqual(theme.ICON_PX, {"medium": 32, "large": 40})

    def test_navicube_params(self):
        self.assertEqual(theme.navicube_params("dark"), {"BaseColor": ("Unsigned", 0x3D4450FF)})
        self.assertEqual(set(theme.navicube_params("light")), set(theme.NAVICUBE_KEYS))

    def test_sketch_params(self):
        p = theme.sketch_params("dark", "expression")
        self.assertEqual(p[theme.SKETCH_ROOT]["ShowDialogOnDistanceConstraint"], ("Bool", False))
        self.assertEqual(p[theme.SKETCH_ROOT]["DimensionalStringFormat"], ("String", "%N = %V"))
        self.assertEqual(p[theme.SKETCH_TOOLS]["OnViewParameterVisibility"], ("Int", 1))
        self.assertEqual(p[theme.VIEW_GROUP]["EditedEdgeColor"], ("Unsigned", 0xF2F2F2FF))
        self.assertEqual(theme.sketch_params("light", "value")[theme.SKETCH_ROOT]["ShowDimensionalName"], ("Bool", False))
        for group, values in p.items():
            self.assertEqual(set(values), set(theme.SKETCH_KEYS[group]), group)


class AxisColoursTest(unittest.TestCase):
    def test_axis_colours_are_muted_in_both_themes(self):
        import colorsys
        from incad.ui import theme
        for t in ("light", "dark"):
            params = theme.view_params(t)
            for key in ("AxisXColor", "AxisYColor", "AxisZColor"):
                self.assertIn(key, params)
                self.assertIn(key, theme.VIEW_KEYS)
                rgba = params[key][1]
                r, g, b = ((rgba >> 24) & 255) / 255.0, ((rgba >> 16) & 255) / 255.0, ((rgba >> 8) & 255) / 255.0
                self.assertLess(colorsys.rgb_to_hsv(r, g, b)[1], 0.6, (t, key))  # not a loud, saturated colour
