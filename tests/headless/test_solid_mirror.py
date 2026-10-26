"""Mirror Solid (the user: mirror the part as a dependent copy until the link is broken, the way the sketch's
Mirror works): the copy is a new Solid that follows its original, takes features of its own, can mirror about a
face; Break Mirror Link keeps it as it is; deleting the original keeps it too. Break Mirror Link on a feature
Mirror keeps the material it made while the features before it still change."""
import unittest

import FreeCAD as App

from incad.core import delete, document
from incad.features import patterns, solid_mirror
from headless import util

V = App.Vector


def origin(body, role):
    return [o for o in body.Origin.OriginFeatures if o.Role == role][0]


def bb(obj):
    b = obj.Shape.BoundBox
    return tuple(round(x, 6) for x in (b.XMin, b.XMax, b.YMin, b.YMax, b.ZMin, b.ZMax))


class SolidMirrorTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("SM")
        self.body, self.pad = util.padded_part(self.doc, 10, incad=True)  # x 0..20, y 0..10, z 0..10
        self.doc.recompute()

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def make(self, plane):
        values = dict(solid_mirror.defaults(self.doc, self.body, None), plane=plane)
        self.doc.openTransaction("Mirror Solid")
        f = solid_mirror.create(self.doc, self.body, None, values)
        self.doc.commitTransaction()
        self.doc.recompute()
        return f, f.getParentGeoFeatureGroup()

    def test_new_solid_follows_the_original(self):
        f, copy = self.make(origin(self.body, "YZ_Plane").Name)
        self.assertIsNot(copy, self.body)
        self.assertIn(copy, document.bodies(self.doc))
        self.assertIs(copy.Tip, f)
        self.assertEqual(bb(copy), (-20, 0, 0, 10, 0, 10))
        self.pad.Length = 14
        self.doc.recompute()
        self.assertEqual(bb(copy), (-20, 0, 0, 10, 0, 14))  # follows
        self.assertTrue(solid_mirror.claims(f))
        from incad import features
        self.assertIs(features.kind_for(f), solid_mirror)
        self.assertEqual(solid_mirror.read(self.doc, f)["solid"], self.body.Name)

    def test_features_on_the_copy_stay_while_it_follows(self):
        f, copy = self.make(origin(self.body, "YZ_Plane").Name)
        cyl = copy.newObject("PartDesign::AdditiveCylinder", "Cyl")
        cyl.Radius, cyl.Height = 2, 20
        cyl.Placement = App.Placement(V(-10, 5, 0), App.Rotation())
        copy.Tip = cyl
        self.doc.recompute()
        self.assertNotIn("Invalid", cyl.State)
        self.assertEqual(round(bb(copy)[5], 6), 20)
        self.pad.Length = 14
        self.doc.recompute()
        self.assertAlmostEqual(copy.Shape.Volume, 20 * 10 * 14 + 3.141592653589793 * 4 * 6, places=3)

    def test_a_flat_face_as_the_mirror(self):
        face = [i + 1 for i, fc in enumerate(self.pad.Shape.Faces)
                if fc.Surface.TypeId == "Part::GeomPlane" and abs(fc.CenterOfMass.x - 20) < 1e-6][0]
        f, copy = self.make("%s:Face%d" % (self.pad.Name, face))
        self.assertEqual(bb(copy), (20, 40, 0, 10, 0, 10))

    def test_a_moved_original_moves_the_copy(self):
        f, copy = self.make(origin(self.body, "XZ_Plane").Name)
        self.body.Placement = App.Placement(V(0, 0, 5), App.Rotation())
        self.doc.recompute()
        self.assertEqual(bb(copy), (0, 20, -10, 0, 5, 15))

    def test_break_mirror_link_keeps_the_copy(self):
        f, copy = self.make(origin(self.body, "YZ_Plane").Name)
        self.assertTrue(solid_mirror.is_linked(copy))  # its Solid's row offers it too
        kept = solid_mirror.break_link(copy)
        self.assertIs(kept, f)
        self.assertFalse(solid_mirror.is_linked(f))
        self.assertIsNone(f.Source)
        self.pad.Length = 14
        self.doc.recompute()
        self.assertEqual(bb(copy), (-20, 0, 0, 10, 0, 10))  # stays as it was
        self.assertNotIn("Invalid", f.State)

    def test_the_mirror_can_not_be_its_own_solid(self):
        f, copy = self.make(origin(self.body, "YZ_Plane").Name)
        with self.assertRaises(ValueError):
            solid_mirror.update(self.doc, f, {"solid": copy.Name, "plane": origin(self.body, "YZ_Plane").Name})

    def test_no_plane_yet_makes_nothing(self):
        before = len(document.bodies(self.doc))
        with self.assertRaises(ValueError):
            solid_mirror.create(self.doc, self.body, None, solid_mirror.defaults(self.doc, self.body, None))
        self.assertEqual(len(document.bodies(self.doc)), before)

    def test_deleting_the_original_keeps_the_copy(self):
        other = document.new_solid(self.doc)
        sk = util.add_rect_sketch(other, 5, 5, name="S2")
        pad2 = util.add_pad(other, sk, 3, name="P2")
        other.Tip = pad2
        self.doc.recompute()
        values = {"solid": other.Name, "plane": origin(self.body, "YZ_Plane").Name}
        f = solid_mirror.create(self.doc, self.body, None, values)
        copy = f.getParentGeoFeatureGroup()
        self.doc.recompute()
        self.assertEqual(bb(copy), (-5, 0, 0, 5, 0, 3))
        delete.delete(other)
        self.doc.recompute()
        self.assertIsNotNone(self.doc.getObject(copy.Name))
        self.assertEqual(bb(copy), (-5, 0, 0, 5, 0, 3))
        self.assertNotIn("Invalid", f.State)

    def test_deleting_the_mirror_takes_its_empty_solid(self):
        f, copy = self.make(origin(self.body, "YZ_Plane").Name)
        name = copy.Name
        delete.delete(f)
        self.assertIsNone(self.doc.getObject(name))

    def test_saved_and_opened_again_it_still_follows(self):
        import os
        import tempfile
        f, copy = self.make(origin(self.body, "YZ_Plane").Name)
        path = os.path.join(tempfile.mkdtemp(), "sm.FCStd")
        name = copy.Name
        self.doc.saveAs(path)
        App.closeDocument(self.doc.Name)
        self.doc = App.openDocument(path)
        pad, copy = self.doc.getObject("Pad"), self.doc.getObject(name)
        pad.Length = 14
        self.doc.recompute()
        self.assertEqual(bb(copy), (-20, 0, 0, 10, 0, 14))

    def test_several_solids_wait_for_a_pick(self):
        other = document.new_solid(self.doc)
        sk = util.add_rect_sketch(other, 5, 5, name="S2")
        other.Tip = util.add_pad(other, sk, 3, name="P2")
        self.doc.recompute()
        self.assertEqual(solid_mirror.defaults(self.doc, self.body, None)["solid"], "")  # which one: the user's click
        self.assertEqual(solid_mirror.defaults(self.doc, self.body, None)["plane"], "")

    def test_join_makes_a_half_whole_and_follows(self):
        values = {"solid": self.body.Name, "plane": "%s:Face%d" % (self.pad.Name, self.x_face(20)), "result": "join"}
        f = solid_mirror.create(self.doc, self.body, None, values)
        self.assertIs(f.getParentGeoFeatureGroup(), self.body)  # a step of the same Solid, no new one
        self.assertEqual(len(document.bodies(self.doc)), 1)
        self.assertIs(self.body.Tip, f)
        self.assertEqual(bb(self.body), (0, 40, 0, 10, 0, 10))
        self.assertEqual(len(self.body.Shape.Solids), 1)
        self.pad.Length = 14
        self.doc.recompute()
        self.assertAlmostEqual(self.body.Shape.Volume, 40 * 10 * 14, places=3)
        self.assertEqual(solid_mirror.read(self.doc, f)["result"], "join")
        kept = solid_mirror.break_link(f)
        self.pad.Length = 18
        self.doc.recompute()
        self.assertNotIn("Invalid", kept.State)
        self.assertAlmostEqual(self.body.Shape.Volume, 20 * 10 * 18 + 20 * 10 * 14, places=3)  # the half it added stays

    def test_cut_by_the_mirror_image(self):
        from incad.features import work
        k = work.PLANE
        wp = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None),
                                                       base=origin(self.body, "YZ_Plane").Name, offset="5 mm"))
        self.doc.recompute()
        values = {"solid": self.body.Name, "plane": wp.Name, "result": "cut"}
        f = solid_mirror.create(self.doc, self.body, None, values)
        self.assertEqual(bb(self.body), (10, 20, 0, 10, 0, 10))  # its image -10..10 cut away
        self.assertNotIn("Invalid", f.State)

    def test_one_side_of_a_plane_through_the_part(self):
        """The user: a part crossing the plane, mirrored to the other side. Join with one side makes it symmetric."""
        from incad.features import work
        k = work.PLANE
        wp = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None),
                                                       base=origin(self.body, "YZ_Plane").Name, offset="5 mm"))
        self.doc.recompute()
        cases = (("join", "front", (-10, 20), 3000), ("join", "back", (0, 10), 1000),
                 ("new", "front", (-10, 5), 1500), ("new", "whole", (-10, 10), 2000))
        for result, side, xs, volume in cases:
            self.doc.openTransaction(result + side)
            f = solid_mirror.create(self.doc, self.body, None, {"solid": self.body.Name, "plane": wp.Name,
                                                                "result": result, "side": side})
            self.doc.recompute()
            shape = f.getParentGeoFeatureGroup().Shape
            self.assertEqual((round(shape.BoundBox.XMin, 6), round(shape.BoundBox.XMax, 6)), xs, (result, side))
            self.assertAlmostEqual(shape.Volume, volume, places=3, msg=(result, side))
            self.assertEqual(solid_mirror.read(self.doc, f)["side"], side)
            self.doc.abortTransaction()
            self.doc.recompute()

    def x_face(self, x):
        return [i + 1 for i, fc in enumerate(self.pad.Shape.Faces)
                if fc.Surface.TypeId == "Part::GeomPlane" and abs(fc.CenterOfMass.x - x) < 1e-6][0]

    def test_boolean_with_its_own_mirrored_copy(self):
        """The user: the mirror is a new part, so why can't I cut, join or intersect it? The copy follows the base
        up to the step before the Boolean."""
        from incad.features import combine, work
        k = work.PLANE
        wp = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None),
                                                       base=origin(self.body, "YZ_Plane").Name, offset="15 mm"))
        self.doc.recompute()
        for op, volume in (("join", 3000), ("cut", 1000), ("intersect", 1000)):
            self.doc.openTransaction(op)
            f = solid_mirror.create(self.doc, self.body, None, {"solid": self.body.Name, "plane": wp.Name})
            copy = f.getParentGeoFeatureGroup()  # x 10..30 over the original's 0..20
            values = dict(combine.defaults(self.doc, self.body), base=self.body.Name, tools=copy.Name, operation=op,
                          clearance="0 mm")
            b = combine.create(self.doc, self.body, None, values)
            self.doc.recompute()
            self.assertNotIn("Invalid", b.State, b.getStatusString())
            self.assertAlmostEqual(self.body.Shape.Volume, volume, places=3, msg=op)
            self.assertIs(f.Source, self.pad)  # follows up to the step before the Boolean
            self.pad.Length = 14
            self.doc.recompute()
            self.assertNotIn("Invalid", b.State)
            self.assertAlmostEqual(copy.Shape.Volume, 2800, places=3)  # still follows
            self.assertAlmostEqual(self.body.Shape.Volume, volume * 1.4, places=3, msg=op)
            self.doc.abortTransaction()
            self.doc.recompute()

    def test_break_link_of_a_feature_mirror(self):
        k = patterns.MIRROR
        values = dict(k.defaults(self.doc, self.body, None), features=self.pad.Name,
                      plane=origin(self.body, "YZ_Plane").Name)
        m = k.create(self.doc, self.body, None, values)
        self.doc.recompute()
        self.assertAlmostEqual(self.body.Shape.Volume, 4000, places=3)
        name = m.Name
        kept = solid_mirror.break_link(m)
        self.assertIsNone(self.doc.getObject(name))  # a step of its own in its place
        self.assertIs(self.body.Tip, kept)
        self.assertAlmostEqual(self.body.Shape.Volume, 4000, places=3)
        self.pad.Length = 14
        self.doc.recompute()
        self.assertNotIn("Invalid", kept.State)
        self.assertAlmostEqual(self.body.Shape.Volume, 2800 + 2000, places=3)  # the copy stays 10 high


if __name__ == "__main__":
    unittest.main()
