"""Gear geometry (incad.core.gears): sizes, spur and helical gears, worms, and a pair that meshes."""
import math
import unittest

import FreeCAD as App
import Part
from incad.core import gears

V = App.Vector


def inside(solid, p):
    return solid.isInside(p, 1e-6, True)


class SizesTest(unittest.TestCase):
    def test_diameters(self):
        self.assertAlmostEqual(gears.pitch_diameter(2, 20), 40)
        self.assertAlmostEqual(gears.tip_diameter(2, 20), 44)
        self.assertAlmostEqual(gears.root_diameter(2, 20), 35)
        self.assertAlmostEqual(gears.pitch_diameter(2, 20, 20), 40 / math.cos(math.radians(20)))

    def test_teeth_for_a_diameter(self):
        self.assertEqual(gears.teeth_for(40, 2), 20)
        self.assertEqual(gears.teeth_for(41, 2), 20)  # 20.5 rounds to the even 20
        self.assertEqual(gears.teeth_for(5, 2), gears.MIN_TEETH)

    def test_centre_distance_and_lead_angle(self):
        self.assertAlmostEqual(gears.center_distance(2, 20, 30), 50)
        self.assertAlmostEqual(gears.lead_angle(2, 1, 20), math.degrees(math.atan(2 * math.pi / (20 * math.pi))))

    def test_mesh_turn(self):
        self.assertAlmostEqual(gears.mesh_turn(20, 0, 30), 180 / 30)  # even: half a tooth
        self.assertAlmostEqual(gears.mesh_turn(20, 0, 31), 0)         # odd: a space faces A already

    def test_refusals(self):
        with self.assertRaises(ValueError):
            gears.check_gear(2, 4, 20, 0, 10, 0)
        with self.assertRaises(ValueError):
            gears.check_gear(2, 20, 20, 0, 10, 40)  # wider than the root
        with self.assertRaises(ValueError):
            gears.check_worm(2, 1, 6, 30, 20, 0)    # too thin for the module


class GearTest(unittest.TestCase):
    def test_spur(self):
        g = gears.gear_solid(2, 20, width=10)
        face = Part.Face(gears.gear_profile(2, 20))
        self.assertTrue(g.isValid())
        self.assertAlmostEqual(g.Volume, face.Area * 10, delta=1e-3 * g.Volume)
        self.assertAlmostEqual(g.BoundBox.ZMin, 0, 6)
        self.assertAlmostEqual(g.BoundBox.ZMax, 10, 6)
        r = gears.tip_diameter(2, 20) / 2 - 0.3
        self.assertTrue(inside(g, V(r, 0, 5)), "a tooth's middle on +X")
        self.assertFalse(inside(g, _at(r, 180 / 20, 5)), "a space half a tooth on")

    def test_bore(self):
        g = gears.gear_solid(2, 20, width=10, bore=10)
        self.assertFalse(inside(g, V(0, 0, 5)))
        self.assertTrue(inside(g, V(6, 0, 5)))

    def test_helical_turns_with_height(self):
        beta, width = 15.0, 10.0
        g = gears.gear_solid(2, 20, helix=beta, width=width)
        self.assertTrue(g.isValid())
        face = Part.Face(gears.gear_profile(2, 20, helix=beta))
        self.assertAlmostEqual(g.Volume, face.Area * width, delta=1e-3 * g.Volume)
        rp = gears.pitch_diameter(2, 20, beta) / 2
        twist = math.degrees(width * math.tan(math.radians(beta)) / rp)
        r = gears.tip_diameter(2, 20, beta) / 2 - 0.3
        self.assertTrue(inside(g, _at(r, twist, width - 1e-3)), "right hand: the tooth turns counter-clockwise")
        left = gears.gear_solid(2, 20, helix=beta, hand="left", width=width)
        self.assertTrue(inside(left, _at(r, -twist, width - 1e-3)))

    def test_a_pair_meshes(self):
        za, zb = 20, 30
        a = gears.gear_solid(2, za, width=10)
        b = gears.gear_solid(2, zb, width=10)
        b.rotate(V(), V(0, 0, 1), gears.mesh_turn(za, 0, zb))
        b.translate(V(gears.center_distance(2, za, zb), 0, 0))
        self.assertLess(a.common(b).Volume, 0.05, "the teeth fit between each other (they touch: no backlash)")
        wrong = gears.gear_solid(2, zb, width=10)
        wrong.translate(V(gears.center_distance(2, za, zb), 0, 0))
        self.assertGreater(a.common(wrong).Volume, 1.0, "out of phase they clash")


class WormTest(unittest.TestCase):
    def test_worm_stays_within_its_diameters(self):
        for starts in (1, 2, 3):
            w = gears.worm_solid(2, starts, 20, 30)
            self.assertTrue(w.isValid(), starts)
            tip, root = 12.0, 7.5
            self.assertAlmostEqual(w.common(Part.makeCylinder(tip + 1e-2, 40, V(0, 0, -5))).Volume, w.Volume,
                                   delta=1e-3 * w.Volume)
            core = Part.makeCylinder(root - 1e-3, 26, V(0, 0, 2)).fuse(Part.makeCylinder(7.46 - 1e-3, 30))  # ends
            # turned a hair under the root
            self.assertAlmostEqual(w.common(core).Volume, core.Volume, delta=1e-3 * core.Volume)

    def test_thread_rises_with_the_lead(self):
        w = gears.worm_solid(2, 1, 20, 30)
        r = 11.5
        lead = gears.lead(2, 1)
        z = lead  # a lead up: past the round end, where the thread is as at the bottom
        self.assertTrue(inside(w, V(r, 0, z + 1e-3)), "a thread's middle on +X a lead up from the bottom")
        self.assertFalse(inside(w, _at(r, 180, z + 1e-3)))
        self.assertTrue(inside(w, _at(r, 90, z + lead / 4)), "right hand: a quarter turn up, a quarter lead")
        self.assertFalse(inside(w, _at(r, -90, z + lead / 4)))

    def test_the_ends_are_round(self):
        """The user: a worm's ends exactly round, to work with: the thread runs out a module before each end."""
        w = gears.worm_solid(2, 2, 20, 30, bore=8)
        self.assertTrue(w.isValid())
        for z in (0.0, 30.0):
            ends = [f for f in w.Faces if f.Surface.TypeId == "Part::GeomPlane" and abs(f.CenterOfMass.z - z) < 1e-6]
            self.assertEqual(len(ends), 1, z)
            radii = sorted(round(e.Curve.Radius, 6) for e in ends[0].Edges)
            self.assertEqual(radii, [4.0, 7.46], "the bore and a circle a hair under the root at z = %g" % z)


def _at(r, deg, z):
    a = math.radians(deg)
    return V(r * math.cos(a), r * math.sin(a), z)


if __name__ == "__main__":
    unittest.main()
