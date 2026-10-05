import math
import unittest

from pivy import coin
from incad.core import camera


def ortho(z=10.0):
    c = coin.SoOrthographicCamera()
    c.position.setValue(0, 0, z)
    c.orientation.setValue(coin.SbRotation())
    c.focalDistance.setValue(z)
    c.height.setValue(20)
    return c


def local(cam, p):
    rel = coin.SbVec3f(*p) - cam.position.getValue()
    return cam.orientation.getValue().inverse().multVec(rel)


class CameraTest(unittest.TestCase):
    def test_focal_point(self):
        p = camera.focal_point(ortho())
        self.assertAlmostEqual(p[2], 0, places=5)

    def test_drag_right_turns_model_right(self):
        c = ortho()
        camera.orbit(c, (0, 0, 0), 20, 0)
        self.assertLess(c.position.getValue()[0], 0)

    def test_drag_down_turns_model_down(self):
        c = ortho()
        camera.orbit(c, (0, 0, 0), 0, 20)
        self.assertGreater(c.position.getValue()[1], 0)

    def test_pivot_stays_put_on_screen_and_distance_kept(self):
        c = ortho()
        pivot = (3.0, 2.0, 1.0)
        before = local(c, pivot)
        dist = (c.position.getValue() - coin.SbVec3f(*pivot)).length()
        camera.orbit(c, pivot, 37, -18)
        after = local(c, pivot)
        for i in range(3):
            self.assertAlmostEqual(before[i], after[i], places=4)
        self.assertAlmostEqual((c.position.getValue() - coin.SbVec3f(*pivot)).length(), dist, places=4)

    def test_units_per_px(self):
        self.assertAlmostEqual(camera.units_per_px(ortho(), 200), 0.1)
        p = coin.SoPerspectiveCamera()
        p.focalDistance.setValue(10)
        p.heightAngle.setValue(math.pi / 4)
        self.assertAlmostEqual(camera.units_per_px(p, 100), 2 * 10 * math.tan(math.pi / 8) / 100, places=6)

    def test_pan_moves_model_with_the_mouse(self):
        c = ortho()
        camera.pan_pixels(c, 100, 0, 200)
        self.assertAlmostEqual(c.position.getValue()[0], -10, places=4)
        c = ortho()
        camera.pan_pixels(c, 0, 100, 200)
        self.assertAlmostEqual(c.position.getValue()[1], 10, places=4)
