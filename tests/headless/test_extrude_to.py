"""Extrude ▸ To reaches any face of any Solid (flat or curved), a work or origin plane, or any point (the user): a face
of another Solid through a hidden binder (FreeCAD reads another Solid's features in its own coordinates and missed),
a point through a hidden plane parallel to the sketch; both follow when the target moves, go with the extrude, and
the dialog shows what was picked."""
import unittest

import FreeCAD as App
import Part

from incad.features import extrude
from headless import util

V = App.Vector


class ExtrudeTo(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("ExTo")
        from incad.core import document
        self.body = document.make_part(self.doc)
        self.sk = util.add_rect_sketch(self.body, 5, 5)
        self.other = self.doc.addObject("PartDesign::Body", "Other")
        self.box = self.other.newObject("PartDesign::AdditiveBox", "Box")
        self.box.Length = self.box.Width = 30
        self.box.Height = 5
        self.other.Placement = App.Placement(V(-10, -10, 20), App.Rotation())
        self.doc.recompute()

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def make(self, to):
        k = extrude
        values = dict(k.defaults(self.doc, self.body, self.sk), operation="join", extent="to", to_face=to)
        f = k.create(self.doc, self.body, self.sk, values)
        self.doc.recompute()
        self.assertNotIn("Invalid", f.State, f.getStatusString())
        return f

    def top(self, f):
        return round(f.Shape.BoundBox.ZMax, 6)

    def face(self, obj, test):
        return "%s:Face%d" % (obj.Name, [i + 1 for i, fc in enumerate(obj.Shape.Faces) if test(fc)][0])

    def helpers(self, f):
        return [o for o in self.body.Group if getattr(o, "InCadHelperOf", None) == f.Name]

    def test_face_of_another_solid_follows_it(self):
        f = self.make(self.face(self.box, lambda fc: fc.normalAt(0, 0).z < -0.5))  # its bottom, at z = 20
        self.assertEqual(self.top(f), 20)
        self.assertEqual([h.TypeId for h in self.helpers(f)], ["PartDesign::SubShapeBinder"])
        self.assertFalse(self.helpers(f)[0].Visibility)
        self.other.Placement = App.Placement(V(-10, -10, 32), App.Rotation())
        self.doc.recompute()
        self.assertEqual(self.top(f), 32)
        self.assertEqual(extrude.read(self.doc, f)["to_face"], self.face(self.box, lambda fc: fc.normalAt(0, 0).z < -0.5))

    def test_curved_face_of_another_solid(self):
        """A sphere over the sketch: the extrude stops on its round face."""
        ball = self.doc.addObject("PartDesign::Body", "Ball")
        sphere = ball.newObject("PartDesign::AdditiveSphere", "Sphere")
        sphere.Radius = 20
        ball.Placement = App.Placement(V(2.5, 2.5, 40), App.Rotation())
        self.doc.recompute()
        f = self.make("%s:Face1" % sphere.Name)
        import math
        self.assertAlmostEqual(f.Shape.BoundBox.ZMax, 40 - math.sqrt(400 - 2 * 2.5 ** 2), places=3)
        ball.Placement = App.Placement(V(2.5, 2.5, 50), App.Rotation())
        self.doc.recompute()
        self.assertAlmostEqual(f.Shape.BoundBox.ZMax, 50 - math.sqrt(400 - 2 * 2.5 ** 2), places=3)

    def test_point_of_another_solid_and_it_moves(self):
        v = [i + 1 for i, p in enumerate(self.box.Shape.Vertexes)
             if abs(self.other.Placement.multVec(p.Point).z - 25) < 1e-6][0]
        f = self.make("%s:Vertex%d" % (self.box.Name, v))
        self.assertEqual(self.top(f), 25)
        self.assertEqual(sorted(h.TypeId for h in self.helpers(f)), ["PartDesign::Plane", "PartDesign::SubShapeBinder"])
        self.other.Placement = App.Placement(V(-10, -10, 40), App.Rotation())
        self.doc.recompute()
        self.assertEqual(self.top(f), 45)

    def test_point_of_its_own_part_and_a_work_point(self):
        pad = util.add_pad(self.body, util.add_rect_sketch(self.body, 2, 2, "Base"), 12)
        self.body.Tip = pad
        self.doc.recompute()
        v = [i + 1 for i, p in enumerate(pad.Shape.Vertexes) if abs(p.Point.z - 12) < 1e-6][0]
        f = self.make("%s:Vertex%d" % (pad.Name, v))
        self.assertEqual(self.top(f), 12)
        self.assertEqual([h.TypeId for h in self.helpers(f)], ["PartDesign::Plane"])
        point = self.body.newObject("PartDesign::Point", "WP")
        point.MapMode = "Deactivated"
        point.Placement = App.Placement(V(50, 50, 7), App.Rotation())
        self.doc.recompute()
        extrude.update(self.doc, f, dict(extrude.read(self.doc, f), to_face=point.Name))
        self.doc.recompute()
        self.assertEqual(self.top(f), 12)  # the earlier pad is higher: the part's top stays
        self.assertEqual(round(f.AddSubShape.BoundBox.ZMax, 6), 7)

    def test_origin_plane_and_back_to_distance_drops_helpers(self):
        v = [i + 1 for i, p in enumerate(self.box.Shape.Vertexes)][0]
        f = self.make("%s:Vertex%d" % (self.box.Name, v))
        self.assertEqual(len(self.helpers(f)), 2)
        values = dict(extrude.read(self.doc, f), extent="distance", distance="4 mm")
        extrude.update(self.doc, f, values)
        self.doc.recompute()
        self.assertEqual(self.helpers(f), [])
        self.assertEqual(self.top(f), 4)
        self.assertEqual(extrude.read(self.doc, f)["to_face"], "")

    def test_join_to_cut_keeps_the_target(self):
        f = self.make(self.face(self.box, lambda fc: fc.normalAt(0, 0).z < -0.5))
        g = extrude.update(self.doc, f, dict(extrude.read(self.doc, f), operation="cut")) or f
        self.doc.recompute()
        g = [o for o in self.body.Group if o.TypeId == "PartDesign::Pocket"][0]
        self.assertEqual([h.TypeId for h in self.helpers(g)], ["PartDesign::SubShapeBinder"])
        self.assertEqual(extrude.read(self.doc, g)["to_face"][:len(self.box.Name)], self.box.Name)
