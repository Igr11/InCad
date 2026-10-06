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
