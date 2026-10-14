"""Move Face geometry: the slab between a flat face's old and new place, three ways for the neighbours."""
import unittest

import FreeCAD as App
import Part

from incad.core import move_face as mf

V = App.Vector
UP = V(0, 0, 1)


def top(shape):
    """The highest face facing up."""
    flat = [f for f in shape.Faces if f.Surface.__class__.__name__ == "Plane" and f.normalAt(0, 0).z > 0.999]
    return max(flat, key=lambda f: f.CenterOfMass.z)


def chamfered():
    box = Part.makeBox(40, 30, 10)
    e = next(e for e in box.Edges if abs(e.CenterOfMass.z - 10) < 1e-9 and abs(e.CenterOfMass.x - 40) < 1e-9)
    return box.makeChamfer(3, [e])


def filleted():
    box = Part.makeBox(40, 30, 10)
    e = next(e for e in box.Edges if abs(e.CenterOfMass.z - 10) < 1e-9 and abs(e.CenterOfMass.x - 40) < 1e-9)
    return box.makeFillet(2, [e])


class BoxTest(unittest.TestCase):
    def test_every_mode_moves_a_box_top(self):
        box = Part.makeBox(40, 30, 10)
        for mode in ("inventor", "step", "together"):
            up = mf.apply(box, [top(box)], 5, mode)
            down = mf.apply(box, [top(box)], -3, mode)
            self.assertEqual(len(up.Solids), 1, mode)
            self.assertAlmostEqual(up.Volume, 40 * 30 * 15, 6, mode)
            self.assertAlmostEqual(down.Volume, 40 * 30 * 7, 6, mode)
            self.assertAlmostEqual(up.BoundBox.ZMax, 15, 9, mode)

    def test_zero_is_the_shape_before(self):
        box = Part.makeBox(40, 30, 10)
        self.assertIs(mf.apply(box, [top(box)], 0, "inventor"), box)


class ChamferTest(unittest.TestCase):
    def test_inventor_extends_the_chamfer(self):
        ch = chamfered()
        r = mf.apply(ch, [top(ch)], 4, "inventor")
        self.assertAlmostEqual(r.Volume, 40 * 30 * 14 - 0.5 * 7 * 7 * 30, 6)
        self.assertAlmostEqual(top(r).BoundBox.XMax, 40 - 7, 6)  # the top face 4 mm narrower toward the chamfer

    def test_inventor_inward(self):
        ch = chamfered()
        r = mf.apply(ch, [top(ch)], -2, "inventor")
        self.assertAlmostEqual(r.Volume, 40 * 30 * 8 - 0.5 * 1 * 1 * 30, 6)

    def test_inventor_too_far_inward_is_refused(self):
        ch = chamfered()
        with self.assertRaises(ValueError) as e:
            mf.apply(ch, [top(ch)], -4, "inventor")  # the 3 mm chamfer would vanish
        self.assertEqual(str(e.exception), mf.TOO_LARGE_MSG)

    def test_step_leaves_a_straight_wall(self):
        ch = chamfered()
        r = mf.apply(ch, [top(ch)], 4, "step")
        self.assertAlmostEqual(r.Volume, ch.Volume + top(ch).Area * 4, 6)
        self.assertAlmostEqual(top(r).BoundBox.XMax, 37, 6)

    def test_together_moves_the_chamfer_up(self):
        ch = chamfered()
        r = mf.apply(ch, [top(ch)], 4, "together")
        self.assertAlmostEqual(r.Volume, ch.Volume + 40 * 30 * 4, 6)  # the side wall 4 taller, chamfer unchanged
        self.assertAlmostEqual(top(r).BoundBox.XMax, 37, 6)


class FilletTest(unittest.TestCase):
    def test_inventor_says_a_round_neighbour_cannot_follow(self):
        fl = filleted()
        with self.assertRaises(ValueError) as e:
            mf.apply(fl, [top(fl)], 3, "inventor")
        self.assertEqual(str(e.exception), mf.ROUND_MSG)

    def test_together_and_step_work(self):
        fl = filleted()
        self.assertAlmostEqual(mf.apply(fl, [top(fl)], 3, "together").Volume, fl.Volume + 40 * 30 * 3, 6)
        self.assertAlmostEqual(mf.apply(fl, [top(fl)], 3, "step").Volume, fl.Volume + top(fl).Area * 3, 6)


class HoleSlotTest(unittest.TestCase):
    def test_face_with_a_hole_keeps_the_hole(self):
        part = Part.makeBox(40, 30, 10).cut(Part.makeCylinder(4, 10, V(20, 15, 0)))
        r = mf.apply(part, [top(part)], 5, "inventor")
        self.assertAlmostEqual(r.Volume, (40 * 30 - 3.141592653589793 * 16) * 15, 3)
        hit = r.common(Part.LineSegment(V(20, 15, -1), V(20, 15, 20)).toShape())
        self.assertAlmostEqual(hit.Length, 0, 6)  # the hole still goes through

    def test_slot_floor_deeper_and_shallower(self):
        part = Part.makeBox(40, 30, 10).cut(Part.makeBox(20, 10, 4, V(10, 10, 6)))  # floor at z 6
        floor = next(f for f in part.Faces if f.Surface.__class__.__name__ == "Plane"
                     and f.normalAt(0, 0).z > 0.999 and abs(f.CenterOfMass.z - 6) < 1e-9)
        self.assertAlmostEqual(mf.apply(part, [floor], -2, "inventor").Volume, part.Volume - 20 * 10 * 2, 6)
        self.assertAlmostEqual(mf.apply(part, [floor], 2, "inventor").Volume, part.Volume + 20 * 10 * 2, 6)

    def test_slot_floor_deeper_than_its_walls(self):
        part = Part.makeBox(40, 30, 10).cut(Part.makeBox(20, 10, 4, V(10, 10, 6)))  # 4 mm walls
        floor = next(f for f in part.Faces if f.Surface.__class__.__name__ == "Plane"
                     and f.normalAt(0, 0).z > 0.999 and abs(f.CenterOfMass.z - 6) < 1e-9)
        # the walls' edges point away from the material: the floor's corners go beyond them, nothing vanishes
        self.assertAlmostEqual(mf.apply(part, [floor], -5, "inventor").Volume, part.Volume - 20 * 10 * 5, 6)


class SeveralFacesTest(unittest.TestCase):
    def two_bosses(self):
        base = Part.makeBox(60, 20, 5)
        return base.fuse([Part.makeBox(10, 10, 5, V(5, 5, 5)), Part.makeBox(10, 10, 5, V(45, 5, 5))]).removeSplitter()

    def test_two_tops_move_together(self):
        part = self.two_bosses()
        tops = [f for f in part.Faces if f.normalAt(0, 0).z > 0.999 and abs(f.CenterOfMass.z - 10) < 1e-9]
        self.assertEqual(len(tops), 2)
        r = mf.apply(part, tops, 3, "inventor")
        self.assertAlmostEqual(r.Volume, part.Volume + 2 * 100 * 3, 6)

    def test_faces_facing_other_ways_are_refused(self):
        box = Part.makeBox(40, 30, 10)
        side = next(f for f in box.Faces if f.normalAt(0, 0).x > 0.999)
        with self.assertRaises(ValueError) as e:
            mf.apply(box, [top(box), side], 3, "inventor")
        self.assertEqual(str(e.exception), mf.FACES_MSG)


class FindAndGapTest(unittest.TestCase):
    def test_signature_finds_the_face_again_on_a_changed_shape(self):
        box = Part.makeBox(40, 30, 10)
        sig = mf.signature(top(box))
        boss = Part.makeBox(40, 30, 10).fuse(Part.makeBox(10, 10, 5, V(0, 0, 10))).removeSplitter()  # a boss on top
        self.assertAlmostEqual(mf.find(boss, sig).CenterOfMass.z, 10, 9)  # the stored plane first, not the boss top
        self.assertAlmostEqual(mf.find(Part.makeBox(40, 30, 12), sig).CenterOfMass.z, 12, 9)  # made taller: found
        self.assertIsNone(mf.find(Part.makeBox(10, 10, 10, V(100, 0, 0)), sig))  # nothing overlaps: gone

    def test_gap_to_a_parallel_plane_and_a_tilted_one(self):
        box = Part.makeBox(40, 30, 10)
        self.assertAlmostEqual(mf.gap_to([top(box)], (V(0, 0, 16), UP)), 6, 9)
        self.assertAlmostEqual(mf.gap_to([top(box)], (V(0, 0, 4), V(0, 0, -1))), -6, 9)
        with self.assertRaises(ValueError) as e:
            mf.gap_to([top(box)], (V(0, 0, 16), V(0, 1, 1).normalize()))
        self.assertEqual(str(e.exception), mf.PARALLEL_MSG)
