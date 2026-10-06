import unittest

import FreeCAD as App
import Part
from incad.core import document, model
from incad.features import extrude, kind_for
from incad.features.common import closed_profile, unconsumed_closed_sketches
from headless import util


class ExtrudeTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("E")
        self.body = document.make_part(self.doc)
        self.sk = util.add_rect_sketch(self.body)  # 20 x 10 on XY
        self.doc.recompute()

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def make(self, **changes):
        values = extrude.defaults(self.doc, self.body, self.sk)
        values.update(changes)
        f = extrude.create(self.doc, self.body, self.sk, values)
        self.doc.recompute()
        return f

    def test_profile_helpers(self):
        self.assertTrue(closed_profile(self.sk))
        self.assertEqual(unconsumed_closed_sketches(self.body), [self.sk])

    def test_defaults_and_join(self):
        v = extrude.defaults(self.doc, self.body, self.sk)
        self.assertEqual((v["operation"], v["extent"], v["direction"], v["distance"]), ("join", "distance", "default", "10 mm"))
        f = self.make()
        self.assertEqual(f.TypeId, "PartDesign::Pad")
        self.assertAlmostEqual(f.Shape.Volume, 20 * 10 * 10, places=3)
        self.assertEqual(model.bound_parameter(f, "Length"), "d0")
        self.assertIs(kind_for(f), extrude)
        self.assertEqual(unconsumed_closed_sketches(self.body), [])

    def test_read_back(self):
        f = self.make(distance="25 mm", direction="symmetric", taper="5")
        v = extrude.read(self.doc, f)
        self.assertEqual((v["distance"], v["direction"], v["taper"], v["operation"]), ("25 mm", "symmetric", "5°", "join"))

    def test_update_values_and_formulas(self):
        f = self.make()
        document.set_parameter(self.doc, "Width", "40 mm")
        f = extrude.update(self.doc, f, dict(extrude.read(self.doc, f), distance="Width / 2"))
        self.doc.recompute()
        self.assertAlmostEqual(f.Length.Value, 20)
        self.assertEqual(extrude.read(self.doc, f)["distance"], "Width / 2")

    def test_join_to_cut_keeps_parameter_and_place(self):
        base = self.make(distance="10 mm")
        top = [i + 1 for i, fc in enumerate(base.Shape.Faces) if abs(fc.CenterOfMass.z - 10) < 1e-6][0]
        sk2 = self.body.newObject("Sketcher::SketchObject", "Hole")
        sk2.AttachmentSupport = [(base, "Face%d" % top)]
        sk2.MapMode = "FlatFace"
        sk2.addGeometry(Part.Circle(App.Vector(10, 5, 0), App.Vector(0, 0, 1), 2))
        self.doc.recompute()
        f = extrude.create(self.doc, self.body, sk2, dict(extrude.defaults(self.doc, self.body, sk2), distance="3 mm"))
        self.doc.recompute()
        name = model.bound_parameter(f, "Length")
        g = extrude.update(self.doc, f, dict(extrude.read(self.doc, f), operation="cut"))
        self.doc.recompute()
        self.assertEqual(g.TypeId, "PartDesign::Pocket")
        self.assertEqual(model.bound_parameter(g, "Length"), name)
        self.assertIs(self.body.Tip, g)
        self.assertLess(g.Shape.Volume, base.Shape.Volume)

    def test_join_cut_switch_mid_history_keeps_later_features(self):
        base = self.make(distance="10 mm")
        later_sk = util.add_rect_sketch(self.body, w=4, h=4, name="Later")
        later = extrude.create(self.doc, self.body, later_sk,
                               dict(extrude.defaults(self.doc, self.body, later_sk), distance="20 mm"))
        self.doc.recompute()
        g = extrude.update(self.doc, base, dict(extrude.read(self.doc, base), operation="cut"))
        self.doc.recompute()
        self.assertIs(later.BaseFeature, g)
        self.assertIs(self.body.Tip, later)
        self.assertFalse(g.Visibility)

    def test_join_cut_switch_refused_when_a_sketch_sits_on_its_face(self):
        base = self.make(distance="10 mm")
        top = [i + 1 for i, fc in enumerate(base.Shape.Faces) if abs(fc.CenterOfMass.z - 10) < 1e-6][0]
        sk2 = self.body.newObject("Sketcher::SketchObject", "OnTop")
        sk2.AttachmentSupport = [(base, "Face%d" % top)]
        sk2.MapMode = "FlatFace"
        sk2.addGeometry(Part.Circle(App.Vector(10, 5, 0), App.Vector(0, 0, 1), 2))
        self.doc.recompute()
        with self.assertRaises(ValueError) as ctx:
            extrude.update(self.doc, base, dict(extrude.read(self.doc, base), operation="cut"))
        self.assertIn("OnTop", str(ctx.exception))
        self.assertEqual(sk2.AttachmentSupport[0][0], base)
        self.assertEqual(base.TypeId, "PartDesign::Pad")

    def test_up_to_a_work_plane(self):
        plane = self.body.newObject("PartDesign::Plane", "Limit")
        plane.AttachmentSupport = [(util.xy_plane(self.body), "")]
        plane.MapMode = "FlatFace"
        plane.AttachmentOffset = App.Placement(App.Vector(0, 0, 7), App.Rotation())
        self.doc.recompute()
        f = self.make(extent="to", to_face=plane.Name)
        self.assertAlmostEqual(f.Shape.Volume, 20 * 10 * 7, places=3)
        self.assertEqual(extrude.read(self.doc, f)["to_face"], plane.Name)

    def test_through_all_cut(self):
        base = self.make(distance="10 mm")
        sk2 = util.add_rect_sketch(self.body, w=4, h=4, name="Cutter")
        self.doc.recompute()
        f = extrude.create(self.doc, self.body, sk2, dict(extrude.defaults(self.doc, self.body, sk2),
                                                          operation="cut", extent="through_all", direction="symmetric"))
        self.doc.recompute()
        self.assertEqual((f.TypeId, f.Type), ("PartDesign::Pocket", "ThroughAll"))
        self.assertAlmostEqual(f.Shape.Volume, 20 * 10 * 10 - 4 * 4 * 10, places=3)

    def test_two_sides(self):
        f = self.make(direction="two_sides", distance="10 mm", distance2="5 mm")
        self.assertEqual(f.SideType, "Two sides")
        self.assertAlmostEqual(f.Shape.Volume, 20 * 10 * 15, places=3)

    def test_new_solid_moves_the_sketch(self):
        f = self.make(operation="new_solid")
        self.assertEqual(len(document.bodies(self.doc)), 2)
        self.assertIsNot(f.getParentGeoFeatureGroup(), self.body)
        self.assertIs(self.sk.getParentGeoFeatureGroup(), f.getParentGeoFeatureGroup())

    def test_intersect(self):
        self.make(distance="10 mm")
        sk2 = util.add_rect_sketch(self.body, w=5, h=5, name="Cross")
        self.doc.recompute()
        f = extrude.create(self.doc, self.body, sk2, dict(extrude.defaults(self.doc, self.body, sk2),
                                                          operation="intersect", distance="30 mm"))
        self.doc.recompute()
        self.assertEqual(f.TypeId, "PartDesign::Boolean")
        self.assertAlmostEqual(self.body.Shape.Volume, 5 * 5 * 10, places=3)

    def test_default_operation_is_cut_inside_material(self):
        self.make(distance="10 mm")
        mid = self.body.newObject("Sketcher::SketchObject", "Mid")
        mid.AttachmentSupport = [(util.xy_plane(self.body), "")]
        mid.MapMode = "FlatFace"
        mid.AttachmentOffset = App.Placement(App.Vector(0, 0, 5), App.Rotation())
        mid.addGeometry(Part.Circle(App.Vector(10, 5, 0), App.Vector(0, 0, 1), 2))
        self.doc.recompute()
        self.assertEqual(extrude.defaults(self.doc, self.body, mid)["operation"], "cut")
