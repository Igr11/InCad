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

    def test_turns_never_touch(self):
        for key, _ in st.STANDARDS:
            for size in st.sizes(key):
                s = st.spec(key, size)
                for internal in (False, True):
                    for grow in (False, True):
                        sides = (profile._tooth_sides(s, internal, 0.15, None, 0.1) if grow
                                 else profile._groove_sides(s, internal, 0.15, 0.5))
                        left, right, lo, hi = sides
                        for k in range(41):
                            r = lo + (hi - lo) * k / 40
                            w = profile._at(right, r) - profile._at(left, r)
                            self.assertLess(w, s.pitch, (key, size, internal, grow, r))
                            self.assertGreaterEqual(w, -1e-9, (key, size, internal, grow, r))

    def test_no_repeated_points(self):
        s = st.spec("custom", "", custom={"major": 10, "pitch": 2, "angle": 60, "depth": 1.7320508})
        g = profile.groove(s, internal=False, clearance=0.0)
        self.assertEqual(len(g), len({(round(r, 9), round(z, 9)) for r, z in g}))


def _custom(kind, angle=60, pitch=1.5, depth=0.7):
    return st.spec("custom", "", custom={"major": 30, "pitch": pitch, "angle": angle, "depth": depth, "profile": kind})


class OutlineTest(unittest.TestCase):
    """The thread's sketch: a few lines and arcs (the user: a semicircle drawn as a row of dots and segments made a
    thread of dozens of strips that took long and hung the program), the shape picked cut in or grown on."""

    def test_every_thread_is_a_few_lines_and_arcs_joined_end_to_start(self):
        for key, _ in st.STANDARDS:
            for size in st.sizes(key):
                s = st.spec(key, size)
                for internal in (False, True):
                    for grow in (False, True):
                        o = profile.outline(s, internal, 0.3, grow=grow)
                        self.assertLessEqual(len(o), 14, (key, size, internal, grow))
                        for a, b in zip(o, o[1:] + o[:1]):
                            self.assertEqual(a[-1], b[1], (key, size, internal, grow))

    def test_a_semicircle_is_arcs(self):
        for grow in (False, True):
            o = profile.outline(_custom("semicircle", 0), False, 0.2, grow=grow, base=15.0 if grow else None)
            self.assertLessEqual(len(o), 8)
            self.assertEqual(len([x for x in o if x[0] == "arc"]), 2)

    def test_grown_semicircle_is_a_bead_on_the_surface(self):
        o = profile.outline(_custom("semicircle", 0, depth=0.7), False, 0.2, grow=True, base=15.0)
        pts = [p for x in o for p in x[1:]]
        top = max(r for r, _ in pts)
        self.assertAlmostEqual(top, 15.0 + 0.7 - 0.1, places=6)  # the radius less half the clearance
        self.assertAlmostEqual(profile.outline_width(o), 2 * (0.7 - 0.1), places=6)
        at_top = [z for r, z in pts if abs(r - top) < 1e-9]
        self.assertLess(max(abs(z) for z in at_top), 1e-6, "round: one point at the top, no flat")

    def test_triangle_and_trapezoid_cut_and_grow_as_picked(self):
        def ends(o):
            return [p for x in o for p in (x[1], x[-1])]
        t = 0.57735026919  # tan 30°
        tri_cut = profile.outline(_custom("triangle"), False, 0.0, runout=0.5)
        bottom = min(r for r, _ in ends(tri_cut))
        self.assertAlmostEqual(bottom, 15.0 - 0.7, places=6)
        self.assertEqual(len({round(z, 9) for r, z in ends(tri_cut) if abs(r - bottom) < 1e-9}), 1, "a sharp V")
        trap_cut = profile.outline(_custom("trapezoid"), False, 0.0, runout=0.5)
        zs = sorted({round(z, 9) for r, z in ends(trap_cut) if abs(r - bottom) < 1e-9})
        self.assertEqual(len(zs), 2, "a flat bottom")
        self.assertAlmostEqual(zs[1] - zs[0], (1.5 - 2 * 0.7 * t) / 2, places=6)
        tri_grow = profile.outline(_custom("triangle"), False, 0.0, grow=True, base=15.0)
        top = max(r for r, _ in ends(tri_grow))
        self.assertAlmostEqual(top, 15.7, places=6)
        self.assertEqual(len({round(z, 9) for r, z in ends(tri_grow) if abs(r - top) < 1e-9}), 1, "a sharp tip")
        self.assertAlmostEqual(profile.outline_width(tri_grow), 2 * 0.7 * t, places=6)
        trap_grow = profile.outline(_custom("trapezoid"), False, 0.0, grow=True, base=15.0)
        zs = sorted({round(z, 9) for r, z in ends(trap_grow) if abs(r - 15.7) < 1e-9})
        self.assertAlmostEqual(zs[1] - zs[0], (1.5 - 2 * 0.7 * t) / 2, places=6, msg="a flat top")


if __name__ == "__main__":
    unittest.main()
