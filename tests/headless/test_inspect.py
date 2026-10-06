import unittest

import FreeCAD as App
from incad.core import inspect
from headless import util


class InspectTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("In")
        self.body, self.pad = util.padded_part(self.doc, 10, incad=True)
        faces = self.pad.Shape.Faces
        self.top = "Face%d" % ([i + 1 for i, f in enumerate(faces) if abs(f.CenterOfMass.z - 10) < 1e-6][0])
        self.bottom = "Face%d" % ([i + 1 for i, f in enumerate(faces) if abs(f.CenterOfMass.z) < 1e-6][0])

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_face_area(self):
        self.assertEqual(inspect.measure([(self.pad, self.top)]), [("Area", "200 mm²")])

    def test_distance_and_angle_between_faces(self):
        rows = dict(inspect.measure([(self.pad, self.top), (self.pad, self.bottom)]))
        self.assertEqual(rows["Distance"], "10 mm")
        self.assertEqual(rows["Angle"], "0°")

    def test_nothing_selected(self):
        with self.assertRaises(ValueError):
            inspect.measure([])

    def test_mass_properties(self):
        rows = dict(inspect.mass_properties(self.body, 1.24))
        self.assertEqual(rows["Volume"], "2000 mm³")
        self.assertEqual(rows["Mass"], "2.48 g")
        self.assertEqual(rows["Size"], "20 × 10 × 10 mm")

    def test_origin_items_are_refused_plainly(self):
        xy = [o for o in self.body.Origin.OriginFeatures if o.Role == "XY_Plane"][0]
        for pairs in ([(xy, "")], [(self.body.Origin, "")]):
            with self.assertRaises(ValueError) as ctx:
                inspect.measure(pairs)
            self.assertIn("Select a face", str(ctx.exception))
