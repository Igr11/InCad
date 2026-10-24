"""3D Model ▸ Gear and Worm as part features (incad.features.gear): made from the dialog's values, a pair that
meshes, a gear sized by its diameter, one on a sketch circle, a worm and its wheel, values read back."""
import math
import unittest

import FreeCAD as App
import Part
from incad.core import document, gears
from incad.features import gear, kind_for
from headless import util

V = App.Vector


def values(kind, **over):
    v = (gear.GEAR if kind == "gear" else gear.WORM).defaults(None, None)
    v.update(over)
    return v


class GearFeatureTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("GF")
        self.body = document.make_part(self.doc)
        self.doc.recompute()

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def make(self, kind, body=None, **over):
        k = gear.GEAR if kind == "gear" else gear.WORM
        f = k.create(self.doc, body or self.body, None, values(kind, **over))
        self.doc.recompute()
        self.assertNotIn("Invalid", f.State, f.getStatusString())
        return f

    def test_a_gear_in_an_empty_part(self):
        f = self.make("gear")
        self.assertIs(kind_for(f), gear.SPUR_GEARS)
        self.assertEqual(len(f.Shape.Solids), 1)
        face = Part.Face(gears.gear_profile(2, 20))
        self.assertAlmostEqual(f.Shape.Volume, face.Area * 10, delta=1e-3 * f.Shape.Volume)
        self.assertAlmostEqual(f.Shape.BoundBox.XMax, 22, 3)

    def test_values_go_through_parameters_and_read_back(self):
        f = self.make("gear", teeth="24", module="1.5 mm", helix="15 °", hand="left", width="8 mm", bore="6 mm")
        read = gear.GEAR.read(self.doc, f)
        self.assertEqual((read["teeth"], read["module"], read["helix"], read["hand"], read["bore"]),
                         ("24", "1.5 mm", "15°", "left", "6 mm"))
        gear.GEAR.update(self.doc, f, dict(read, teeth="30"))
        self.assertEqual(gear.effective(f)["teeth"], 30)

    def test_sized_by_diameter(self):
        f = self.make("gear", size="diameter", diameter="61 mm", module="2 mm")
        self.assertEqual(gear.effective(f)["teeth"], 30)  # 30.5 -> the whole number nearest
        self.assertIn("30 teeth", gear.GEAR.info(values("gear", size="diameter", diameter="61 mm")))

    def test_a_pair_meshes_in_its_own_solid(self):
        a = self.make("gear", teeth="20")
        b = self.make("gear", mesh=a.Name, teeth="30", width="10 mm")
        self.assertIsNot(b.getParentGeoFeatureGroup(), a.getParentGeoFeatureGroup(), "a Solid of its own")
        sa, sb = a.Shape, b.Shape
        self.assertTrue(sb.isValid())
        self.assertLess(sa.common(sb).Volume, 0.05, "the teeth fit between each other")
        centre = b.Shape.BoundBox.Center
        self.assertAlmostEqual(math.hypot(centre.x, centre.y), gears.center_distance(2, 20, 30), delta=0.5)
        self.assertIn("centre distance 50 mm", gear.GEAR.info(values("gear", mesh=a.Name, teeth="30")))
        # the pair follows the first gear's module
        gear.GEAR.update(self.doc, a, dict(gear.GEAR.read(self.doc, a), module="1 mm"))
        self.doc.recompute()
        self.assertEqual(gear.effective(b)["module"], 1.0)
        self.assertLess(a.Shape.common(b.Shape).Volume, 0.05)

    def test_a_helical_pair_meshes_with_opposite_hands(self):
        a = self.make("gear", teeth="18", helix="20 °", width="14 mm")
        b = self.make("gear", mesh=a.Name, teeth="27", width="14 mm")
        self.assertEqual(gear.effective(b)["hand"], "left")
        self.assertTrue(b.Shape.isValid())
        tooth = b.Shape.Volume / 27  # the twisted flanks are splines: a hair of overlap, never a tooth's worth
        self.assertLess(a.Shape.common(b.Shape).Volume, 1e-3 * tooth)

    def test_on_a_sketch_circle(self):
        sk = self.body.newObject("Sketcher::SketchObject", "Shaft")
        sk.AttachmentSupport = [(util.xy_plane(self.body), "")]
        sk.MapMode = "FlatFace"
        sk.AttachmentOffset = App.Placement(V(0, 0, 5), App.Rotation())
        sk.addGeometry(Part.Circle(V(30, 10, 0), V(0, 0, 1), 4))
        self.doc.recompute()
        f = self.make("gear", center="%s:Edge1" % sk.Name, bore="8 mm")
        bb = f.Shape.BoundBox
        self.assertAlmostEqual(bb.Center.x, 30, delta=0.3)
        self.assertAlmostEqual(bb.Center.y, 10, delta=0.3)
        self.assertAlmostEqual(bb.ZMin, 5, 6)
        self.assertFalse(f.Shape.isInside(V(30, 10, 7), 1e-6, True), "the bore round the shaft")

    def test_a_worm_and_its_wheel(self):
        w = self.make("worm", starts="2", diameter="20 mm", length="40 mm")
        self.assertIs(kind_for(w), gear.WORM_GEAR)
        self.assertAlmostEqual(w.Shape.BoundBox.ZMax, 40, 3)
        wheel = self.make("gear", mesh=w.Name, teeth="30", width="12 mm")
        e = gear.effective(wheel)
        gamma = gears.lead_angle(2, 2, 20)
        self.assertAlmostEqual(e["helix"], gamma)
        self.assertEqual(e["hand"], "right")
        self.assertAlmostEqual(e["module"] / math.cos(math.radians(e["helix"])), 2.0)  # transverse = the worm's
        c = wheel.Shape.BoundBox.Center
        self.assertAlmostEqual(c.z, 20, delta=0.5, msg="at the worm's middle")
        self.assertAlmostEqual(math.hypot(c.x, c.y), (20 + 60) / 2, delta=0.5)
        self.assertIn("Lead", gear.WORM.info(values("worm")))
        tooth = wheel.Shape.Volume / 30
        self.assertLess(w.Shape.common(wheel.Shape).Volume, 0.02 * tooth, "the wheel's teeth stand in the worm's spaces")

    def test_worm_wheels_mesh_for_both_hands_and_more_starts(self):
        for starts, hand, turn in (("1", "right", "0 °"), ("3", "right", "17 °"), ("2", "left", "0 °")):
            w = self.make("worm", starts=starts, hand=hand, diameter="24 mm", length="36 mm", turn=turn)
            wheel = self.make("gear", mesh=w.Name, teeth="28", width="10 mm")
            tooth = wheel.Shape.Volume / 28
            self.assertLess(w.Shape.common(wheel.Shape).Volume, 0.02 * tooth, (starts, hand, turn))
            for o in (wheel, w):
                o.getParentGeoFeatureGroup().removeObject(o)
                self.doc.removeObject(o.Name)
            self.doc.recompute()

    def test_a_worm_meshing_a_gear_made_first(self):
        gamma = gears.lead_angle(2, 1, 20)
        g = self.make("gear", teeth="30", module="%.9g mm" % (2 * math.cos(math.radians(gamma))),
                      helix="%.9g °" % gamma, width="12 mm")
        w = self.make("worm", mesh=g.Name, starts="1", diameter="20 mm", length="40 mm")
        self.assertIsNot(w.getParentGeoFeatureGroup(), g.getParentGeoFeatureGroup())
        self.assertAlmostEqual(gear.effective(w)["module"], 2.0, 6)
        self.assertTrue(w.Shape.isValid())
        tooth = g.Shape.Volume / 30
        self.assertLess(w.Shape.common(g.Shape).Volume, 0.02 * tooth, "the thread runs in the gear's spaces")
        c = w.Shape.BoundBox.Center
        self.assertAlmostEqual(c.z, 6, delta=0.5, msg="at the gear's middle plane")
        self.assertAlmostEqual(math.hypot(c.x, c.y), (20 + 60) / 2, delta=0.5)
        self.assertNotIn("true mesh", gear.WORM.info(values("worm", mesh=g.Name)))
        spur = self.make("gear", teeth="30", width="12 mm")
        self.assertIn("helix angle of", gear.WORM.info(values("worm", mesh=spur.Name)))

    def test_without_a_place_it_is_a_solid_of_its_own(self):
        """The user: a Gear, then a Worm — the worm ran through the gear and the part became one lump."""
        g = self.make("gear", size="diameter", diameter="58 mm", width="6 mm")
        w = self.make("worm")
        self.assertIsNot(w.getParentGeoFeatureGroup(), g.getParentGeoFeatureGroup())
        self.assertEqual(len(g.getParentGeoFeatureGroup().Shape.Solids), 1)

    def test_no_mesh_loops(self):
        a = self.make("gear")
        b = self.make("gear", mesh=a.Name, teeth="30")
        with self.assertRaises(ValueError):
            gear.GEAR.update(self.doc, a, dict(gear.GEAR.read(self.doc, a), mesh=b.Name))

    def test_a_pair_by_ratio_or_centre_distance(self):
        a = self.make("gear", teeth="20", helix="15 °")
        b = self.make("gear", mesh=a.Name, size="ratio", ratio="1.5")
        self.assertEqual(gear.effective(b)["teeth"], 30)
        self.assertEqual((gear.effective(b)["helix"], gear.effective(b)["hand"]), (15.0, "left"), "the same angle")
        self.assertIn("ratio 30:20 = 1.5", gear.GEAR.info(values("gear", mesh=a.Name, size="ratio", ratio="1.5")))
        a2 = gears.center_distance(2, 20, 30, 15)
        c = self.make("gear", mesh=a.Name, size="distance", distance="%.6f mm" % a2)
        self.assertEqual(gear.effective(c)["teeth"], 30)
        self.assertIn("nearest whole number", gear.GEAR.info(values("gear", mesh=a.Name, size="distance",
                                                                    distance="%.6f mm" % (a2 + 1.3))))
        self.assertLess(a.Shape.common(c.Shape).Volume, 1e-3 * c.Shape.Volume / 30)

    def test_a_worm_wheel_by_ratio(self):
        w = self.make("worm", starts="2")
        wheel = self.make("gear", mesh=w.Name, size="ratio", ratio="20")
        self.assertEqual(gear.effective(wheel)["teeth"], 40)

    def test_ratio_needs_a_mate(self):
        with self.assertRaises(ValueError):
            gear.GEAR.create(self.doc, self.body, None, values("gear", size="ratio"))

    def test_offsets_move_it_in_its_own_frame(self):
        f = self.make("gear", offset_x="30 mm", offset_y="-5 mm", offset_z="7 mm")
        c = f.Shape.BoundBox.Center
        self.assertAlmostEqual(c.x, 30, delta=0.3)
        self.assertAlmostEqual(c.y, -5, delta=0.3)
        self.assertAlmostEqual(f.Shape.BoundBox.ZMin, 7, 6)
        g = gear.gizmo_frame(f)
        self.assertAlmostEqual((g.Base - V(30, -5, 12)).Length, 0, 6)
        mate = self.make("gear", mesh=f.Name, teeth="30")
        self.assertIsNone(gear.gizmo_frame(mate), "a meshing gear is placed by its mate: no gizmo")

    def test_rotate_x_tilts_its_axis_and_the_mate_follows(self):
        f = self.make("gear", rotate_x="90 °")
        bb = f.Shape.BoundBox
        self.assertAlmostEqual(bb.YLength, 10, 3, "the width now runs along -Y")
        self.assertAlmostEqual(bb.ZLength, bb.XLength, 3)
        mate = self.make("gear", mesh=f.Name, teeth="30")
        self.assertAlmostEqual(mate.Shape.BoundBox.YLength, 10, 3, "the pair turned together")
        self.assertLess(f.Shape.common(mate.Shape).Volume, 0.05)
        before = mate.Shape.copy()
        gear.bake(mate)
        self.doc.recompute()
        self.assertLess((mate.Shape.BoundBox.Center - before.BoundBox.Center).Length, 1e-6, "baked where it stood")

    def test_a_worm_along_a_sketch_line(self):
        sk = self.body.newObject("Sketcher::SketchObject", "Path")
        sk.AttachmentSupport = [(util.xy_plane(self.body), "")]
        sk.MapMode = "FlatFace"
        sk.addGeometry(Part.LineSegment(V(10, 5, 0), V(10, 45, 0)))  # a line along +Y
        self.doc.recompute()
        w = self.make("worm", axis="%s:Edge1" % sk.Name, length="30 mm")
        bb = w.Shape.BoundBox
        self.assertAlmostEqual(bb.YMin, 5, 3)
        self.assertAlmostEqual(bb.YMax, 35, 3)
        self.assertAlmostEqual(bb.Center.x, 10, delta=0.3)
        self.assertAlmostEqual(bb.Center.z, 0, delta=0.3)
        sk2 = self.body.newObject("Sketcher::SketchObject", "Guide")
        sk2.AttachmentSupport = [(util.xy_plane(self.body), "")]
        sk2.MapMode = "FlatFace"
        sk2.addGeometry(Part.LineSegment(V(-40, 0, 0), V(-40, 0, 0) + V(0, -1, 0) * 50), True)  # construction
        self.doc.recompute()
        w2 = self.make("worm", axis="%s:Edge1" % sk2.Name, length="20 mm")
        self.assertAlmostEqual(w2.Shape.BoundBox.YMax, 0, 3)
        self.assertAlmostEqual(w2.Shape.BoundBox.YMin, -20, 3)

    def test_refusals(self):
        with self.assertRaises(ValueError):
            gear.GEAR.create(self.doc, self.body, None, values("gear", teeth="3"))
        with self.assertRaises(ValueError):
            gear.GEAR.create(self.doc, self.body, None, values("gear", teeth="20.5"))
        self.assertEqual([o for o in self.doc.Objects if gear.is_gear(o)], [], "nothing left behind")


if __name__ == "__main__":
    unittest.main()
