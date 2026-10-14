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


def exact_edges(test, shape):
    """Inventor's result has only lines and circles (a curved edge stops the next Inventor move: round); the one
    exception is FreeCAD's refine turning the merged seam of a hole wall into a straight B-spline."""
    for e in shape.Edges:
        kind = e.Curve.__class__.__name__
        if kind == "BSplineCurve" and e.Curve.Degree == 1 and e.Curve.NbPoles == 2:
            continue
        test.assertIn(kind, ("Line", "Circle"))


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
            if mode == "inventor":
                exact_edges(self, up)
                exact_edges(self, down)

    def test_two_inventor_moves_in_a_row(self):
        box = Part.makeBox(40, 30, 10)
        once = mf.apply(box, [top(box)], 3, "inventor")
        twice = mf.apply(once, [top(once)], 2, "inventor")
        self.assertAlmostEqual(twice.BoundBox.ZMax, 15, 9)
        self.assertAlmostEqual(twice.Volume, 40 * 30 * 15, 6)
        exact_edges(self, twice)

    def test_zero_is_the_shape_before(self):
        box = Part.makeBox(40, 30, 10)
        self.assertIs(mf.apply(box, [top(box)], 0, "inventor"), box)


class ChamferTest(unittest.TestCase):
    def test_inventor_extends_the_chamfer(self):
        ch = chamfered()
        r = mf.apply(ch, [top(ch)], 4, "inventor")
        self.assertAlmostEqual(r.Volume, 40 * 30 * 14 - 0.5 * 7 * 7 * 30, 6)
        self.assertAlmostEqual(top(r).BoundBox.XMax, 40 - 7, 6)  # the top face 4 mm narrower toward the chamfer
        exact_edges(self, r)

    def test_inventor_at_a_chamfered_corner(self):
        """The top's right edge and the back right vertical edge chamfered 3: the top's corner (37, 30, 10) has two
        side edges (top chamfer / corner chamfer, back wall / corner chamfer) and neither lies on both its neighbours
        (the top chamfer and the back wall); it moves along the line those two planes meet in.
        Expected, built from half-spaces: the part is the box minus x + z > 47 (top chamfer) minus x + y > 67 (corner
        chamfer). Top +2 extends the neighbours and leaves the other faces: the 40 x 30 x 12 box minus the same two
        half-spaces (the top chamfer plane unchanged, now 5 wide; the corner chamfer still ends below z 10)."""
        def wedges(height):
            x0 = 47 - height - 1  # on x + z = 47 at z height + 1
            top_ch = Part.Face(Part.makePolygon([V(x0, -1, height + 1), V(41, -1, height + 1), V(41, -1, 6),
                                                 V(x0, -1, height + 1)])).extrude(V(0, 32, 0))
            corner = Part.Face(Part.makePolygon([V(36, 31, -1), V(41, 31, -1), V(41, 26, -1), V(36, 31, -1)]))
            return top_ch, corner.extrude(V(0, 0, height + 2))

        def built(height):
            a, b = wedges(height)
            return Part.makeBox(40, 30, height).cut(a).cut(b)

        box = Part.makeBox(40, 30, 10)
        c = [e.CenterOfMass for e in box.Edges]
        edges = [e for e, m in zip(box.Edges, c) if abs(m.x - 40) < 1e-9 and (
            abs(m.z - 10) < 1e-9 or abs(m.y - 30) < 1e-9 and abs(m.z - 5) < 1e-9)]
        s = box.makeChamfer(3, edges)
        self.assertAlmostEqual(s.Volume, built(10).Volume, 6)  # the half-space model is the chamfered part
        r = mf.apply(s, [top(s)], 2, "inventor")
        expected = built(12)
        self.assertTrue(r.isValid())
        self.assertEqual(len(r.Solids), 1)
        self.assertAlmostEqual(r.Volume, expected.Volume, 6)
        self.assertAlmostEqual(r.cut(expected).Volume + expected.cut(r).Volume, 0, 6)
        planes = [(f.normalAt(0, 0), f.CenterOfMass) for f in r.Faces if f.Surface.__class__.__name__ == "Plane"]
        for e in top(s).Edges:  # every neighbour's plane is still a face of the result
            nb = next(f for f in s.ancestorsOfType(e, Part.Face) if not f.isSame(top(s)))
            nn, p = nb.normalAt(0, 0), nb.CenterOfMass
            self.assertTrue(any(m.dot(nn) > 1 - 1e-9 and abs((c - p).dot(nn)) < 1e-6 for m, c in planes), nn)
        exact_edges(self, r)

    def test_inventor_twice_is_one_move(self):
        ch = chamfered()
        once = mf.apply(ch, [top(ch)], 2, "inventor")
        twice = mf.apply(once, [top(once)], 2, "inventor")
        self.assertAlmostEqual(twice.Volume, mf.apply(ch, [top(ch)], 4, "inventor").Volume, 6)
        self.assertAlmostEqual(twice.Volume, 40 * 30 * 14 - 0.5 * 7 * 7 * 30, 6)
        exact_edges(self, twice)

    def test_inventor_inward(self):
        ch = chamfered()
        r = mf.apply(ch, [top(ch)], -2, "inventor")
        self.assertAlmostEqual(r.Volume, 40 * 30 * 8 - 0.5 * 1 * 1 * 30, 6)
        exact_edges(self, r)

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


class FrustumTest(unittest.TestCase):
    def frustum(self):
        box = Part.makeBox(20, 20, 10)
        return box.makeChamfer(5, [e for e in box.Edges if abs(e.CenterOfMass.z - 10) < 1e-9])  # top 10 x 10

    def test_inventor_grows_the_frustum(self):
        fr = self.frustum()
        r = mf.apply(fr, [top(fr)], 3, "inventor")  # the top 4 x 4 at z 13
        self.assertAlmostEqual(r.Volume, 20 * 20 * 5 + 8 / 3 * (20 * 20 + 4 * 4 + 20 * 4), 6)
        self.assertAlmostEqual(top(r).Area, 16, 6)
        exact_edges(self, r)

    def test_inventor_past_the_apex_is_refused(self):
        fr = self.frustum()
        for d in (5, 7):  # at +5 the top shrinks to a point, past it the outline would turn inside out
            with self.assertRaises(ValueError) as e:
                mf.apply(fr, [top(fr)], d, "inventor")
            self.assertEqual(str(e.exception), mf.TOO_LARGE_MSG, d)


class HoleSlotTest(unittest.TestCase):
    def test_face_with_a_hole_keeps_the_hole(self):
        part = Part.makeBox(40, 30, 10).cut(Part.makeCylinder(4, 10, V(20, 15, 0)))
        r = mf.apply(part, [top(part)], 5, "inventor")
        self.assertAlmostEqual(r.Volume, (40 * 30 - 3.141592653589793 * 16) * 15, 3)
        hit = r.common(Part.LineSegment(V(20, 15, -1), V(20, 15, 20)).toShape())
        self.assertAlmostEqual(hit.Length, 0, 6)  # the hole still goes through
        exact_edges(self, r)
        again = mf.apply(r, [top(r)], 2, "inventor")  # past the hole wall's seam (a straight B-spline after refine)
        self.assertAlmostEqual(again.Volume, (40 * 30 - 3.141592653589793 * 16) * 17, 3)
        exact_edges(self, again)

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


    def test_a_cut_through_the_part_is_refused(self):
        part = Part.makeBox(40, 30, 10).cut(Part.makeBox(20, 10, 4, V(10, 10, 6)))  # floor at z 6
        floor = next(f for f in part.Faces if f.Surface.__class__.__name__ == "Plane"
                     and f.normalAt(0, 0).z > 0.999 and abs(f.CenterOfMass.z - 6) < 1e-9)
        for mode in ("inventor", "step", "together"):
            for d in (-6, -7):  # down to the bottom face, or through it
                with self.assertRaises(ValueError) as e:
                    mf.apply(part, [floor], d, mode)
                self.assertEqual(str(e.exception), mf.TOO_LARGE_MSG, (mode, d))

    def test_together_through_the_bottom_is_refused(self):
        ch = chamfered()
        with self.assertRaises(ValueError) as e:
            mf.apply(ch, [top(ch)], -8, "together")  # the 7 mm wall under the chamfer would vanish
        self.assertEqual(str(e.exception), mf.TOO_LARGE_MSG)

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


    def test_tops_in_two_planes_move_to_one_plane(self):
        base = Part.makeBox(60, 20, 5)
        part = base.fuse([Part.makeBox(10, 10, 5, V(5, 5, 5)), Part.makeBox(10, 10, 2, V(45, 5, 5))]).removeSplitter()
        tops = sorted((f for f in part.Faces if f.normalAt(0, 0).z > 0.999 and f.CenterOfMass.z > 6),
                      key=lambda f: -f.CenterOfMass.z)  # z 10, z 7
        gaps = mf.gaps_to(tops, (V(0, 0, 12), UP))
        self.assertEqual([round(g, 9) for g in gaps], [2, 5])
        self.assertAlmostEqual(mf.gap_to(tops, (V(0, 0, 12), UP)), 2, 9)
        r = mf.apply(part, tops, gaps, "inventor")
        self.assertAlmostEqual(r.Volume, part.Volume + 100 * 2 + 100 * 5, 6)
        at12 = [f for f in r.Faces if f.normalAt(0, 0).z > 0.999 and abs(f.CenterOfMass.z - 12) < 1e-9]
        self.assertEqual(len(at12), 2)
        self.assertIs(mf.apply(part, tops, [0, 0], "inventor"), part)

    def test_unknown_mode(self):
        box = Part.makeBox(40, 30, 10)
        with self.assertRaises(ValueError) as e:
            mf.apply(box, [top(box)], 3, "sideways")
        self.assertEqual(str(e.exception), "Unknown neighbours mode: sideways")

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
        for f in (mf.gap_to, mf.gaps_to):
            with self.assertRaises(ValueError) as e:
                f([top(box)], (V(0, 0, 16), V(0, 0, 0)))
            self.assertEqual(str(e.exception), mf.PARALLEL_MSG)
