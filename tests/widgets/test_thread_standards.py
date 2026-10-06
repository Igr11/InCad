import unittest

from incad.threads import standards as st


class StandardsTest(unittest.TestCase):
    def test_families_in_order(self):
        self.assertEqual([k for k, _ in st.STANDARDS],
                         ["iso", "iso_fine", "unc", "unf", "g", "npt", "tr", "acme", "print", "custom"])

    def test_iso_coarse_and_fine(self):
        s = st.spec("iso", "M8")
        self.assertEqual((s.major, s.pitch, s.angle), (8.0, 1.25, 60.0))
        self.assertIn("M10x1.25", st.sizes("iso_fine"))
        self.assertEqual(st.spec("iso_fine", "M10x1.25").pitch, 1.25)

    def test_unified(self):
        s = st.spec("unc", "1/4-20")
        self.assertAlmostEqual(s.pitch, 1.27, places=3)
        self.assertAlmostEqual(s.major, 6.35, places=3)
        self.assertIn("1/4-28", st.sizes("unf"))

    def test_pipe(self):
        g = st.spec("g", "G1/4")
        self.assertAlmostEqual(g.major, 13.157, places=3)
        self.assertAlmostEqual(g.pitch, 25.4 / 19, places=3)
        self.assertEqual(g.angle, 55.0)
        n = st.spec("npt", "1/4")
        self.assertAlmostEqual(n.pitch, 25.4 / 18, places=3)
        self.assertAlmostEqual(n.taper, 1.7899, places=3)

    def test_trapezoidal_and_acme(self):
        t = st.spec("tr", "Tr16x4")
        self.assertEqual((t.major, t.pitch, t.angle), (16.0, 4.0, 30.0))
        self.assertAlmostEqual(t.depth, 2.25, places=6)  # ISO 2904: h3 = P/2 + ac, ac = 0.25 for P 2..5
        a = st.spec("acme", "1/2-10")
        self.assertAlmostEqual(a.pitch, 2.54, places=3)
        self.assertEqual(a.angle, 29.0)

    def test_suggest(self):
        self.assertEqual(st.suggest("iso", 10.0, False), "M10")
        self.assertEqual(st.suggest("iso", 8.6, True, 0.2), "M10")
        self.assertEqual(st.suggest("unc", 6.3, False), "1/4-20")

    def test_bore_diameter(self):
        s = st.spec("iso", "M10")
        self.assertAlmostEqual(st.bore_diameter(s, 0.2), 10 - 2 * s.depth_int + 0.2, places=6)
        self.assertAlmostEqual(st.bore_diameter(s, 0), 8.376, places=3)  # ISO D1

    def test_every_size_is_sane(self):
        for key, _ in st.STANDARDS:
            if key == "custom":
                continue
            for size in st.sizes(key):
                s = st.spec(key, size)
                self.assertTrue(0 < s.depth < s.pitch and 0 < s.depth_int < s.pitch, (key, size, s))
                self.assertTrue(0 <= s.crest_ext < s.pitch and 0 <= s.crest_int < s.pitch, (key, size))
                self.assertGreater(s.major, 2 * s.depth, (key, size))

    def test_custom(self):
        s = st.spec("custom", "", custom={"major": 12, "pitch": 2, "angle": 45, "depth": 0.8})
        self.assertEqual((s.major, s.pitch, s.angle, s.depth), (12.0, 2.0, 45.0, 0.8))

    def test_default_clearance(self):
        self.assertEqual(st.default_clearance("iso"), 0.2)
        self.assertEqual(st.default_clearance("print"), 0.3)
