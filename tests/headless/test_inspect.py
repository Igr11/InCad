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


class MeasureModesTest(unittest.TestCase):
    """Inspect's menu: Distance, Angle, Length (a loop of edges), Area (faces)."""
    def setUp(self):
        self.doc = util.new_doc("Im")
        self.body, self.pad = util.padded_part(self.doc, 10, incad=True)  # 20 x 10 x 10
        faces = self.pad.Shape.Faces
        self.top = "Face%d" % ([i + 1 for i, f in enumerate(faces) if abs(f.CenterOfMass.z - 10) < 1e-6][0])
        self.bottom = "Face%d" % ([i + 1 for i, f in enumerate(faces) if abs(f.CenterOfMass.z) < 1e-6][0])
        self.top_edges = ["Edge%d" % (i + 1) for i, e in enumerate(self.pad.Shape.Edges)
                          if abs(e.CenterOfMass.z - 10) < 1e-6]

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_distance(self):
        rows = dict(inspect.measure([(self.pad, self.top), (self.pad, self.bottom)], "distance"))
        self.assertEqual(list(rows), ["Distance"])
        self.assertEqual(rows["Distance"], "10 mm")
        with self.assertRaises(ValueError) as c:
            inspect.measure([(self.pad, self.top)], "distance")
        self.assertIn("two", str(c.exception))

    def test_angle(self):
        rows = dict(inspect.measure([(self.pad, self.top), (self.pad, self.bottom)], "angle"))
        self.assertEqual(rows, {"Angle": "0°"})
        side = "Face%d" % ([i + 1 for i, f in enumerate(self.pad.Shape.Faces) if abs(f.normalAt(0, 0).x) > 0.9][0])
        self.assertEqual(dict(inspect.measure([(self.pad, self.top), (self.pad, side)], "angle")), {"Angle": "90°"})

    def test_length_of_a_loop(self):
        rows = dict(inspect.measure([(self.pad, e) for e in self.top_edges], "length"))
        self.assertEqual(rows, {"Length": "60 mm", "Edges": "4"})
        with self.assertRaises(ValueError):
            inspect.measure([(self.pad, self.top)], "length")

    def test_area_of_faces(self):
        rows = dict(inspect.measure([(self.pad, self.top), (self.pad, self.bottom)], "area"))
        self.assertEqual(rows, {"Area": "400 mm²", "Faces": "2"})

    def test_empty_selection_says_what_to_pick(self):
        for mode in inspect.MODES:
            with self.assertRaises(ValueError) as c:
                inspect.measure([], mode)
            self.assertEqual(str(c.exception), inspect.PROMPTS[mode])
