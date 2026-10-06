import math
import unittest

import FreeCAD as App
from incad.core import document, slots
from headless import util

V = App.Vector


class SlotsTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Sl")
        body = document.make_part(self.doc)
        self.sk = body.newObject("Sketcher::SketchObject", "S")
        self.sk.AttachmentSupport = [(util.xy_plane(body), "")]
        self.sk.MapMode = "FlatFace"
        self.doc.recompute()

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def area(self):
        self.doc.recompute()
        import Part
        return Part.Face(self.sk.Shape.Wires[0]).Area

    def test_overall_slot_ends_at_the_picked_points(self):
        c1, c2, r = slots.overall(V(0, 0, 0), V(30, 0, 0), V(10, 4, 0))
        self.assertEqual((round(c1.x, 6), round(c2.x, 6), round(r, 6)), (4.0, 26.0, 4.0))
        slots.add(self.sk, c1, c2, r)
        self.doc.recompute()
        bb = self.sk.Shape.BoundBox
        self.assertAlmostEqual(bb.XMin, 0, places=6)
        self.assertAlmostEqual(bb.XMax, 30, places=6)
        self.assertAlmostEqual(self.area(), 22 * 8 + math.pi * 16, places=4)
        self.assertEqual(len(self.sk.Shape.Wires), 1)
        self.assertTrue(self.sk.Shape.Wires[0].isClosed())

    def test_center_point_slot_is_symmetric(self):
        c1, c2, r = slots.center_point(V(10, 10, 0), V(20, 10, 0), V(15, 13, 0))
        self.assertAlmostEqual((c1 - V(0, 10, 0)).Length, 0, places=6)
        self.assertAlmostEqual((c2 - V(20, 10, 0)).Length, 0, places=6)
        self.assertAlmostEqual(r, 3, places=6)
        slots.add(self.sk, c1, c2, r)
        self.assertAlmostEqual(self.area(), 20 * 6 + math.pi * 9, places=4)

    def test_slanted_slot_is_closed_and_solves(self):
        c1, c2, r = slots.overall(V(0, 0, 0), V(20, 20, 0), V(0, 10, 0))
        slots.add(self.sk, c1, c2, r)
        self.doc.recompute()
        self.assertTrue(self.sk.Shape.Wires[0].isClosed())
        self.assertNotIn("Invalid", self.sk.State)

    def test_too_short_is_refused(self):
        with self.assertRaises(ValueError):
            slots.overall(V(0, 0, 0), V(5, 0, 0), V(0, 4, 0))  # width larger than the length
