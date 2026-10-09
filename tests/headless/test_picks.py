import unittest

import FreeCAD as App
from incad.core import document
from incad.features import common
from headless import util


class PicksTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Pk")
        self.body, self.pad = util.padded_part(self.doc, 10, incad=True)

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_format_and_parse(self):
        text = common.format_picks([(self.pad, "Edge1"), (self.pad, "Edge3")])
        self.assertEqual(text, "%s:Edge1,%s:Edge3" % (self.pad.Name, self.pad.Name))
        self.assertEqual(common.parse_picks(self.doc, text), [(self.pad, "Edge1"), (self.pad, "Edge3")])
        self.assertEqual(common.parse_picks(self.doc, ""), [])
        self.assertEqual(common.format_picks([(self.pad, "")]), self.pad.Name)

    def test_body_pick_means_tip(self):
        self.assertEqual(common.resolve(self.body, "Face6"), (self.pad, "Face6"))
        self.assertEqual(common.resolve(self.body, "%s.Face6" % self.pad.Name), (self.pad, "Face6"))

    def test_accepts(self):
        x = [o for o in self.body.Origin.OriginFeatures if o.Role == "X_Axis"][0]
        xy = [o for o in self.body.Origin.OriginFeatures if o.Role == "XY_Plane"][0]
        top = [i + 1 for i, f in enumerate(self.pad.Shape.Faces) if abs(f.CenterOfMass.z - 10) < 1e-6][0]
        self.assertTrue(common.accepts("edge", self.pad, "Edge1"))
        self.assertFalse(common.accepts("edge", self.pad, "Face%d" % top))
        self.assertTrue(common.accepts("face", self.pad, "Face%d" % top))
        self.assertTrue(common.accepts("axis", x, ""))
        self.assertTrue(common.accepts("axis", self.pad, "Edge1"))
        self.assertTrue(common.accepts("plane", xy, ""))
        self.assertTrue(common.accepts("plane", self.pad, "Face%d" % top))
        self.assertFalse(common.accepts("plane", x, ""))
        self.assertTrue(common.accepts("feature", self.pad, ""))
        self.assertTrue(common.accepts("vertex", self.pad, "Vertex1"))
        self.assertFalse(common.accepts("circular_edge", self.pad, "Edge1"))

    def test_labels(self):
        self.assertEqual(common.pick_label("edge", ""), "Select…")
        text = common.format_picks([(self.pad, "Edge1"), (self.pad, "Edge2"), (self.pad, "Edge3")])
        self.assertEqual(common.pick_label("edge", text), "3 edges")
        self.assertEqual(common.pick_label("face", "%s:Face6" % self.pad.Name), "%s · Face6" % self.pad.Label)
        # several features are listed by name (a count alone doesn't say what is picked)
        names = "%s,%s" % (self.pad.Name, self.pad.Name)
        self.assertEqual(common.pick_label("feature", names), "%s + %s" % (self.pad.Label, self.pad.Label))
        four = ",".join([self.pad.Name] * 4)
        self.assertEqual(common.pick_label("feature", four), "4 features")

    def test_link_sub(self):
        self.assertEqual(common.link_sub([(self.pad, "Edge1"), (self.pad, "Edge2")]), (self.pad, ["Edge1", "Edge2"]))
        with self.assertRaises(ValueError):
            common.link_sub([])
