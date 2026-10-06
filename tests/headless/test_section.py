import unittest

import FreeCAD as App
from incad.core import section
from headless import util


class SectionTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Sc")
        self.body, self.pad = util.padded_part(self.doc, 10, incad=True)

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def normal(self, plc):
        return plc.Rotation.multVec(App.Vector(0, 0, 1))

    def test_three_points(self):
        vs = self.pad.Shape.Vertexes
        top = [i + 1 for i, v in enumerate(vs) if abs(v.Point.z - 10) < 1e-6][:3]
        plc = section.placement([(self.pad, "Vertex%d" % i) for i in top])
        self.assertAlmostEqual(abs(self.normal(plc).z), 1, places=6)
        self.assertAlmostEqual(plc.Base.z, 10, places=6)

    def test_flat_face_and_work_plane(self):
        side = [i + 1 for i, f in enumerate(self.pad.Shape.Faces) if abs(f.CenterOfMass.x) < 1e-6][0]
        plc = section.placement([(self.pad, "Face%d" % side)])
        self.assertAlmostEqual(abs(self.normal(plc).x), 1, places=6)
        xz = [o for o in self.body.Origin.OriginFeatures if o.Role == "XZ_Plane"][0]
        plc = section.placement([(xz, "")])
        self.assertAlmostEqual(abs(self.normal(plc).y), 1, places=6)

    def test_default_and_refusals(self):
        self.assertAlmostEqual(abs(self.normal(section.placement([])).y), 1, places=6)  # XZ
        # what can't define a plane (an edge, a whole solid) is ignored: XZ
        self.assertAlmostEqual(abs(self.normal(section.placement([(self.pad, "Edge1")])).y), 1, places=6)
        self.assertAlmostEqual(abs(self.normal(section.placement([(self.body, "")])).y), 1, places=6)
        vs = [(self.pad, "Vertex1"), (self.pad, "Vertex1"), (self.pad, "Vertex2")]
        with self.assertRaises(ValueError):
            section.placement(vs)  # not three different points


class AdjustedTest(unittest.TestCase):
    def test_offset_moves_along_the_normal_and_flip_turns_it(self):
        from incad.core import section
        base = App.Placement(App.Vector(1, 2, 3), App.Rotation(App.Vector(1, 0, 0), 90))  # normal +Z -> -Y
        n = base.Rotation.multVec(App.Vector(0, 0, 1))
        moved = section.adjusted(base, 5.0)
        self.assertAlmostEqual((moved.Base - base.Base - n * 5.0).Length, 0, places=9)
        flipped = section.adjusted(base, 0.0, True)
        self.assertAlmostEqual((flipped.Rotation.multVec(App.Vector(0, 0, 1)) + n).Length, 0, places=9)
