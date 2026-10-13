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


class AngleTest(unittest.TestCase):
    def test_signed_angle_counter_clockwise_on_screen_is_positive(self):
        c = (100, 100)  # screen: y grows downwards
        right, up, left, down = (110, 100), (100, 90), (90, 100), (100, 110)
        self.assertAlmostEqual(H.signed_angle(c, right, up), 90)
        self.assertAlmostEqual(H.signed_angle(c, up, left), 90)
        self.assertAlmostEqual(H.signed_angle(c, left, down), 90)
        self.assertAlmostEqual(H.signed_angle(c, down, right), 90)
        self.assertAlmostEqual(H.signed_angle(c, right, down), -90)
        self.assertAlmostEqual(H.signed_angle(c, up, (110, 90)), -45)

    def test_signed_angle_wraps_past_180(self):
        c = (0, 0)
        a = (-10, -1)   # just above the left (screen y up = negative)
        b = (-10, 1)    # just below it: a small turn through 180°, not -358°
        self.assertAlmostEqual(H.signed_angle(c, a, b), 2 * math.degrees(math.atan2(1, 10)), places=6)
        self.assertAlmostEqual(H.wrap(190), -170)
        self.assertAlmostEqual(H.wrap(-190), 170)
        self.assertAlmostEqual(H.wrap(180), 180)

    def test_plane_angle_reads_the_projected_ellipse(self):
        c, pu, pw = (100, 100), (40, 0), (0, -20)  # the arc's plane seen at a slant: a flat ellipse
        self.assertAlmostEqual(H.plane_angle(c, pu, pw, (140, 100)), 0)
        self.assertAlmostEqual(H.plane_angle(c, pu, pw, (100, 80)), 90)
        self.assertAlmostEqual(H.plane_angle(c, pu, pw, (100 + 40 * math.cos(math.radians(30)),
                                                         100 - 20 * math.sin(math.radians(30)))), 30)
        self.assertAlmostEqual(H.plane_angle(c, pu, pw, (100, 130)), -90)  # off the ellipse: its direction
        self.assertIsNone(H.plane_angle(c, (40, 0), (39, 1), (120, 100)), "seen edge-on: no reading")
        self.assertIsNone(H.plane_angle(c, pu, pw, c), "on the centre: no direction")


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
