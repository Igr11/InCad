import unittest

import FreeCAD as App
from incad.features import work
from headless import util


class WorkTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Wk")
        self.body, self.pad = util.padded_part(self.doc, 10, incad=True)

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_offset_plane(self):
        xy = [o for o in self.body.Origin.OriginFeatures if o.Role == "XY_Plane"][0]
        k = work.PLANE
        f = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None), base=xy.Name,
                                                     offset="15 mm"))
        self.doc.recompute()
        self.assertAlmostEqual(f.Placement.Base.z, 15, places=6)
        self.assertEqual(k.read(self.doc, f)["offset"], "15 mm")

    def test_axis_through_an_edge(self):
        k = work.AXIS
        f = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None),
                                                     edge="%s:Edge1" % self.pad.Name))
        self.doc.recompute()
        self.assertEqual(f.State, ["Up-to-date"])

    def test_point_at_a_vertex(self):
        k = work.POINT
        f = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None),
                                                     vertex="%s:Vertex1" % self.pad.Name))
        self.doc.recompute()
        v = self.pad.Shape.Vertexes[0].Point
        self.assertAlmostEqual((f.Placement.Base - v).Length, 0, places=6)
