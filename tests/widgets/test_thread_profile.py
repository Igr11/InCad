import unittest

from incad.threads import profile, standards as st


def _segments(poly):
    return [(poly[i], poly[(i + 1) % len(poly)]) for i in range(len(poly))]


def _cross(a, b, c, d):
    def orient(p, q, r):
        v = (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
        return 0 if abs(v) < 1e-12 else (1 if v > 0 else -1)
    return orient(a, b, c) * orient(a, b, d) < 0 and orient(c, d, a) * orient(c, d, b) < 0


class GrooveTest(unittest.TestCase):
    def test_external_m10(self):
        s = st.spec("iso", "M10")
        g = profile.groove(s, internal=False, clearance=0.0)
        rs = [r for r, _ in g]
        self.assertAlmostEqual(min(rs), 5 - s.depth, places=6)
        self.assertGreater(max(rs), 5)
        self.assertAlmostEqual(profile.width_at(g, 5.0), 7 / 8 * 1.5, places=6)

    def test_clearance_moves_the_flanks(self):
        s = st.spec("iso", "M10")
        g = profile.groove(s, internal=False, clearance=0.4)
        self.assertAlmostEqual(min(r for r, _ in g), 5 - s.depth - 0.2, places=6)
        self.assertGreater(profile.width_at(g, 5.0), 7 / 8 * 1.5)

    def test_internal_reaches_major_plus_half_clearance(self):
        s = st.spec("iso", "M10")
        g = profile.groove(s, internal=True, clearance=0.4)
        self.assertAlmostEqual(max(r for r, _ in g), 5 + 0.2, places=6)
        self.assertLess(min(r for r, _ in g), 5 - s.depth_int)

    def test_turns_never_touch_and_polygons_are_simple(self):
        for key, _ in st.STANDARDS:
            for size in st.sizes(key):
                s = st.spec(key, size)
                for internal in (False, True):
                    g = profile.groove(s, internal=internal, clearance=0.6)
                    self.assertLess(profile.max_width(g), s.pitch, (key, size, internal))
                    segs = _segments(g)
                    for i, (a, b) in enumerate(segs):
                        for j, (c, d) in enumerate(segs):
                            if abs(i - j) > 1 and {i, j} != {0, len(segs) - 1}:
                                self.assertFalse(_cross(a, b, c, d), (key, size, internal))

    def test_no_repeated_points(self):
        s = st.spec("custom", "", custom={"major": 10, "pitch": 2, "angle": 60, "depth": 1.7320508})
        g = profile.groove(s, internal=False, clearance=0.0)
        self.assertEqual(len(g), len({(round(r, 9), round(z, 9)) for r, z in g}))
