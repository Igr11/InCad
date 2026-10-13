"""DOF handles: the screen-space math (pure, no FreeCAD): hit-test, turn angle, slide distance."""
import math
import unittest

from incad.ui import dof_handles as H


class DistanceTest(unittest.TestCase):
    def test_point_to_segment(self):
        self.assertAlmostEqual(H.segment_distance((5, 3), (0, 0), (10, 0)), 3)
        self.assertAlmostEqual(H.segment_distance((-4, 3), (0, 0), (10, 0)), 5)  # past the end: to the end point
        self.assertAlmostEqual(H.segment_distance((13, 4), (0, 0), (10, 0)), 5)
        self.assertAlmostEqual(H.segment_distance((2, 2), (1, 1), (1, 1)), math.hypot(1, 1))  # a point

    def test_point_to_polyline(self):
        square = [(0, 0), (10, 0), (10, 10)]
        self.assertAlmostEqual(H.polyline_distance((12, 5), square), 2)
        self.assertAlmostEqual(H.polyline_distance((5, -1), square), 1)
        self.assertAlmostEqual(H.polyline_distance((3, 4), [(0, 0)]), 5)


class HitTest(unittest.TestCase):
    def test_nearest_handle_within_tolerance_wins(self):
        handles = [(0, [[(0, 0), (100, 0)]]),            # a slide arrow along x
                   (1, [[(0, 20), (100, 20)], [(50, 30), (50, 40)]])]  # another, with a head
        self.assertEqual(H.nearest(handles, (50, 8)), 0)   # 8 px from 0, 12 from 1
        self.assertEqual(H.nearest(handles, (50, 13)), 1)  # 13 from 0, 7 from 1
        self.assertEqual(H.nearest(handles, (50, 45)), 1)  # 5 px from the head
        self.assertIsNone(H.nearest(handles, (50, 60)))    # 20 px from everything
        self.assertIsNone(H.nearest(handles, (-H.HANDLE_PX - 1, 0)), "just outside the tolerance")
        self.assertEqual(H.nearest(handles, (-H.HANDLE_PX + 1, 0)), 0)

    def test_tolerance_is_about_twelve_px(self):
        self.assertEqual(H.HANDLE_PX, 12)
        self.assertIsNone(H.nearest([], (0, 0)))


class DirectionTest(unittest.TestCase):
    """Where handles cross on screen, the first move picks the one it runs along."""
    def test_segment_toward(self):
        d, direction = H.segment_toward((5, 2), [[(0, 0), (10, 0), (10, 10)], [(20, 20), (30, 30)]])
        self.assertAlmostEqual(d, 2)
        self.assertEqual(direction, (1.0, 0.0))

    def test_the_move_picks_the_handle_it_runs_along(self):
        options = [(0, 3.0, (1.0, 0.0)), (1, 6.0, (0.0, 1.0))]  # an arrow along x, an arc running along y
        self.assertEqual(H.by_direction(options, (1, 9)), 1, "moving along y: the arc, though farther")
        self.assertEqual(H.by_direction(options, (9, -1)), 0)
        self.assertEqual(H.by_direction(options, (5, 5)), 0, "as well aligned: the nearer one")
        self.assertEqual(H.by_direction(options, (0, 0)), 0)
        self.assertEqual(H.by_direction([(4, 2.0, (0.0, 1.0))], (9, 0)), 4, "one handle: that one")
        self.assertIsNone(H.by_direction([], (1, 1)))


class AngleTest(unittest.TestCase):
    def test_wrap_keeps_steps_within_half_a_turn(self):
        self.assertAlmostEqual(H.wrap(190), -170)
        self.assertAlmostEqual(H.wrap(-190), 170)
        self.assertAlmostEqual(H.wrap(180), 180)
        self.assertAlmostEqual(H.wrap(-358), 2)

    def test_plane_angle_reads_the_projected_ellipse(self):
        c, pu, pw = (100, 100), (40, 0), (0, -20)  # the arc's plane seen at a slant: a flat ellipse
        self.assertAlmostEqual(H.plane_angle(c, pu, pw, (140, 100)), 0)
        self.assertAlmostEqual(H.plane_angle(c, pu, pw, (100, 80)), 90)
        self.assertAlmostEqual(H.plane_angle(c, pu, pw, (100 + 40 * math.cos(math.radians(30)),
                                                         100 - 20 * math.sin(math.radians(30)))), 30)
        self.assertAlmostEqual(H.plane_angle(c, pu, pw, (100, 130)), -90)  # off the ellipse: its direction
        self.assertIsNone(H.plane_angle(c, (40, 0), (39, 1), (120, 100)), "seen edge-on: no reading")
        self.assertIsNone(H.plane_angle(c, pu, pw, c), "on the centre: no direction")


class TrackTest(unittest.TestCase):
    """An arc seen edge-on is a line on screen: the reading follows the pointer along it from the last one."""
    def test_edge_on_arc_follows_the_pointer(self):
        c, pu, pw = (100, 100), (40, 0), (0, 0.5)  # nearly a line along x
        self.assertIsNone(H.plane_angle(c, pu, pw, (120, 100)))
        self.assertAlmostEqual(H.track_angle(c, pu, pw, (140, 100), None), 0, delta=1)
        self.assertAlmostEqual(H.track_angle(c, pu, pw, (120, 100), 10), 60, delta=1)  # the front half, near 10°
        self.assertAlmostEqual(H.track_angle(c, pu, pw, (120, 100), -10), -60, delta=1)  # the back half
        last, seen = 0, []
        for x in (135, 125, 110, 100, 90, 75, 62):  # along the line to the far end: half a turn
            last = H.track_angle(c, pu, pw, (x, 100), last)
            seen.append(last)
        self.assertIn(seen, (sorted(seen), sorted(seen, reverse=True)), "it keeps turning one way")
        self.assertAlmostEqual(abs(seen[-1]), 180 - math.degrees(math.acos(38 / 40)), delta=1.5)

    def test_tilted_arc_reads_the_same_either_way(self):
        c, pu, pw = (0, 0), (30, 10), (-5, 12)
        for deg in (-150, -45, 0, 30, 100, 170):
            r = math.radians(deg)
            p = (pu[0] * math.cos(r) + pw[0] * math.sin(r), pu[1] * math.cos(r) + pw[1] * math.sin(r))
            self.assertAlmostEqual(H.plane_angle(c, pu, pw, p), deg, places=6)
            self.assertAlmostEqual(H.track_angle(c, pu, pw, p, deg + 20), deg, delta=0.5)


class SlideTest(unittest.TestCase):
    def test_screen_delta_to_mm_along_the_arrow(self):
        per_mm = (3, 4)  # 1 mm along the direction = 5 px on screen, at (0.6, 0.8)
        self.assertAlmostEqual(H.mm_along((30, 40), per_mm), 10)
        self.assertAlmostEqual(H.mm_along((-6, -8), per_mm), -2)
        self.assertAlmostEqual(H.mm_along((40, -30), per_mm), 0)  # across the arrow: no slide
        self.assertAlmostEqual(H.mm_along((5, 0), per_mm), 0.6)
        self.assertEqual(H.mm_along((5, 5), (0, 0)), 0)  # an arrow pointing at the viewer: nothing


if __name__ == "__main__":
    unittest.main()
