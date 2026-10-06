import unittest

import FreeCAD as App
from incad.core import model
from incad.features import common, kind_for, patterns
from headless import util


class PatternsTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Pt")
        self.body, self.pad = util.padded_part(self.doc, 10, incad=True)

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_rectangular_two_directions(self):
        k = patterns.RECT
        v = dict(k.defaults(self.doc, self.body, None), count1="3", spacing1="30 mm", two_directions=True,
                 count2="2", spacing2="20 mm")
        f = k.create(self.doc, self.body, None, v)
        self.doc.recompute()
        self.assertAlmostEqual(f.Shape.Volume, 6 * 2000, places=1)
        self.assertIs(kind_for(f), k)
        r = k.read(self.doc, f)
        self.assertEqual((r["count1"], r["spacing1"], r["count2"], r["two_directions"]), ("3", "30 mm", "2", True))

    def test_spacing_parameter_drives_the_pattern(self):
        k = patterns.RECT
        f = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None), count1="2",
                                                     spacing1="30 mm"))
        self.doc.recompute()
        name = model.bound_parameter(f, "Offset") or k.spacing_param(f, 1)
        model.set_model_parameter(self.doc, name, "10 mm")  # overlapping copies now
        self.assertLess(f.Shape.Volume, 2 * 2000 - 1)

    def test_circular(self):
        k = patterns.CIRC
        f = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None), count="4"))
        self.doc.recompute()
        self.assertAlmostEqual(f.Shape.Volume, 8000, places=1)

    def test_mirror(self):
        k = patterns.MIRROR
        f = k.create(self.doc, self.body, None, k.defaults(self.doc, self.body, None))
        self.doc.recompute()
        self.assertAlmostEqual(f.Shape.Volume, 4000, places=1)
        self.assertEqual(common.parse_picks(self.doc, k.read(self.doc, f)["features"]), [(self.pad, "")])

    def test_new_pattern_becomes_the_tip(self):
        for k in (patterns.RECT, patterns.CIRC, patterns.MIRROR):
            f = k.create(self.doc, self.body, None, k.defaults(self.doc, self.body, None))
            self.doc.recompute()
            self.assertIs(self.body.Tip, f, k.TITLE)

    def test_defaults_name_the_origin_directions(self):
        names = {o.Role: o.Name for o in self.body.Origin.OriginFeatures}
        r = patterns.RECT.defaults(self.doc, self.body, None)
        self.assertEqual((r["dir1"], r["dir2"]), (names["X_Axis"], names["Y_Axis"]))
        self.assertEqual(patterns.CIRC.defaults(self.doc, self.body, None)["axis"], names["Z_Axis"])
        self.assertEqual(patterns.MIRROR.defaults(self.doc, self.body, None)["plane"], names["YZ_Plane"])

    def test_spacing_parameters_are_named_for_the_dialog(self):
        k = patterns.RECT
        f = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None), two_directions=True))
        self.doc.recompute()
        names = k.param_names(f)
        self.assertEqual(set(names), {"spacing1", "spacing2"})
        self.assertTrue(all(names.values()))

    def test_default_feature_survives_an_edit(self):
        for k in (patterns.RECT, patterns.CIRC, patterns.MIRROR):
            tip = self.body.Tip
            f = k.create(self.doc, self.body, None, k.defaults(self.doc, self.body, None))
            self.doc.recompute()
            f = k.update(self.doc, f, k.defaults(self.doc, self.body, None))
            self.doc.recompute()
            self.assertEqual(list(f.Originals), [tip], k.TITLE)
            self.assertNotIn("Invalid", f.State, k.TITLE)
            self.body.removeObject(f)
            self.doc.removeObject(f.Name)
            self.body.Tip = tip
            self.doc.recompute()

    def test_default_skips_back_over_patterns_and_dressups(self):
        r = patterns.RECT.create(self.doc, self.body, None, patterns.RECT.defaults(self.doc, self.body, None))
        self.doc.recompute()
        self.assertIs(self.body.Tip, r)
        c = patterns.CIRC.create(self.doc, self.body, None, patterns.CIRC.defaults(self.doc, self.body, None))
        self.doc.recompute()
        self.assertEqual(list(c.Originals), [self.pad])
        self.assertNotIn("Invalid", c.State)
