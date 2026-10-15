"""The Dimension tool's dead zone (incad.ui.dimension_place): FreeCAD's areas for each distance type around the
box of the two points, and where InCad holds the cursor so the type changes only clearly past a side."""
import unittest

import FreeCAD as App

from incad.ui import dimension_place as dz

V = App.Vector
T = 1.0  # the dead zone, in sketch units
EPS = 0.01


class Areas(unittest.TestCase):
    def setUp(self):
        self.box = dz.areas(V(0, 0, 0), V(20, 6, 0))  # a slanted line: box 20 x 6

    def test_types_as_freecad_picks_them(self):
        self.assertEqual(dz.type_at(self.box, 10, 10), "DistanceX")  # above
        self.assertEqual(dz.type_at(self.box, 10, -3), "DistanceX")  # below
        self.assertEqual(dz.type_at(self.box, 25, 3), "DistanceY")  # beside
        self.assertEqual(dz.type_at(self.box, 25, 10), "Distance")  # a corner
        self.assertEqual(dz.type_at(self.box, 10, 3), "Distance")  # inside
        self.assertIsNone(dz.type_at(self.box, 20, 10))  # on a side: FreeCAD keeps its type

    def test_just_past_a_side_the_type_is_held_at_the_side(self):
        q = dz.held(self.box, "DistanceX", 20.4, 10, T, EPS)  # 0.4 past the right side, above
        self.assertIsNotNone(q)
        self.assertEqual(dz.type_at(self.box, *q), "DistanceX")
        self.assertAlmostEqual(q[0], 20 - EPS, 9)  # at the side, the height kept: the label slides along
        self.assertAlmostEqual(q[1], 10, 9)

    def test_clearly_past_a_side_freecad_gets_the_cursor(self):
        self.assertIsNone(dz.held(self.box, "DistanceX", 21.5, 10, T, EPS))

    def test_held_on_the_way_back_too(self):
        q = dz.held(self.box, "Distance", 19.6, 10, T, EPS)
        self.assertEqual(dz.type_at(self.box, *q), "Distance")
        self.assertIsNone(dz.held(self.box, "Distance", 18.5, 10, T, EPS))

    def test_same_type_is_never_touched(self):
        self.assertIsNone(dz.held(self.box, "DistanceX", 10, 10, T, EPS))


class NarrowBox(unittest.TestCase):
    """A nearly horizontal line: the vertical type's band is thinner than the dead zone."""

    def setUp(self):
        self.box = dz.areas(V(0, 0, 0), V(20, 1, 0))  # 1 unit high

    def test_the_band_is_entered_in_its_middle(self):
        self.assertIsNotNone(dz.held(self.box, "Distance", 25, 0.9, T, EPS))  # near its edge: held
        self.assertIsNone(dz.held(self.box, "Distance", 25, 0.5, T, EPS))  # its middle: vertical

    def test_leaving_it_takes_the_whole_dead_zone(self):
        q = dz.held(self.box, "DistanceY", 25, 1.5, T, EPS)  # 0.5 above it
        self.assertEqual(dz.type_at(self.box, *q), "DistanceY")
        self.assertIsNone(dz.held(self.box, "DistanceY", 25, 2.2, T, EPS))


if __name__ == "__main__":
    unittest.main()
