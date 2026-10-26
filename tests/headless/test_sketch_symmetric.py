"""Sketch ▸ Symmetric, InCad's own (incad.core.sketch_symmetric): picks by point / edge / axis, never a dimension;
two points, two lines (ends paired by their mirror images) or two circles / arcs (centres, equal radii) mirrored about
a line, an axis or a point; older ties the new ones repeat go."""
import math
import unittest

import FreeCAD as App
import Part
import Sketcher
from incad.core import document, safe, sketch_symmetric as sym
from incad.core import sketch as sketches
from headless import util

V = App.Vector


class SymmetricTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Sym")
        self.body = document.make_part(self.doc)
        sk = self.body.newObject("Sketcher::SketchObject", "S")
        sk.AttachmentSupport = [(util.xy_plane(self.body), "")]
        sk.MapMode = "FlatFace"
        self.sk = sk

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def add(self, geom, construction=False):
        g = self.sk.addGeometry(geom, construction)
        self.doc.recompute()
        return g

    def apply(self, a, b, s):
        r = safe.run_safely("Symmetric", lambda: sym.constrain(self.sk, a, b, s), self.doc)
        self.doc.recompute()
        return r

    def test_two_points_about_the_y_axis(self):
        p = self.add(Part.Point(V(-7, 2, 0)))
        q = self.add(Part.Point(V(5, 6, 0)))
        r = self.apply(("point", p, 1), ("point", q, 1), ("edge", sym.V_AXIS))
        self.assertTrue(r.ok, r.error)
        a, b = self.sk.getPoint(p, 1), self.sk.getPoint(q, 1)
        self.assertAlmostEqual(a.x, -b.x, places=6)
        self.assertAlmostEqual(a.y, b.y, places=6)

    def test_two_lines_ends_paired_by_their_mirror(self):
        axis = self.add(Part.LineSegment(V(0, -10, 0), V(0, 10, 0)), construction=True)
        left = self.add(Part.LineSegment(V(-8, -3, 0), V(-4, 5, 0)))
        right = self.add(Part.LineSegment(V(5, 4, 0), V(9, -2, 0)))  # drawn the other way round
        r = self.apply(("edge", left), ("edge", right), ("edge", axis))
        self.assertTrue(r.ok, r.error)
        self.assertEqual([c.Type for c in self.sk.Constraints].count("Symmetric"), 2)
        for pa, pb in ((1, 2), (2, 1)):  # left's start mirrors right's end (nearest), not a crossed pair
            a, b = self.sk.getPoint(left, pa), self.sk.getPoint(right, pb)
            m = sym._mirror(self.sk, ("edge", axis), a)  # about the centreline where the solver left it (it is free)
            self.assertAlmostEqual((m - b).Length, 0, places=6)

    def test_two_circles_and_two_arcs(self):
        c1 = self.add(Part.Circle(V(-6, 3, 0), V(0, 0, 1), 2))
        c2 = self.add(Part.Circle(V(7, 1, 0), V(0, 0, 1), 3))
        r = self.apply(("edge", c1), ("edge", c2), ("edge", sym.V_AXIS))
        self.assertTrue(r.ok, r.error)
        self.assertAlmostEqual(self.sk.Geometry[c1].Radius, self.sk.Geometry[c2].Radius, places=6)
        a, b = self.sk.getPoint(c1, 3), self.sk.getPoint(c2, 3)
        self.assertAlmostEqual(a.x, -b.x, places=6)
        a1 = self.add(Part.ArcOfCircle(Part.Circle(V(2, 9, 0), V(0, 0, 1), 2), 0, math.pi))
        a2 = self.add(Part.ArcOfCircle(Part.Circle(V(3, -8, 0), V(0, 0, 1), 4), math.pi, 2 * math.pi))
        r = self.apply(("edge", a1), ("edge", a2), ("edge", sym.H_AXIS))
        self.assertTrue(r.ok, r.error)
        self.assertAlmostEqual(self.sk.getPoint(a1, 3).y, -self.sk.getPoint(a2, 3).y, places=6)

    def test_about_a_point(self):
        p = self.add(Part.Point(V(-3, 1, 0)))
        q = self.add(Part.Point(V(4, 4, 0)))
        r = self.apply(("point", p, 1), ("point", q, 1), sym.ROOT)
        self.assertTrue(r.ok, r.error)
        self.assertAlmostEqual((self.sk.getPoint(p, 1) + self.sk.getPoint(q, 1)).Length, 0, places=6)

    def test_refusals_in_plain_words(self):
        line = self.add(Part.LineSegment(V(-5, 0, 0), V(-1, 4, 0)))
        circle = self.add(Part.Circle(V(5, 2, 0), V(0, 0, 1), 1))
        arc = self.add(Part.ArcOfCircle(Part.Circle(V(0, 8, 0), V(0, 0, 1), 2), 0, 1))
        for a, b, s, word in ((("edge", line), ("edge", circle), ("edge", sym.V_AXIS), "two of a kind"),
                              (("edge", line), ("point", line, 1), ("edge", sym.V_AXIS), "two of a kind"),
                              (("point", line, 1), ("point", line, 2), ("edge", arc), "straight line"),
                              (("edge", line), ("edge", line), ("edge", sym.V_AXIS), "two different")):
            r = self.apply(a, b, s)
            self.assertFalse(r.ok)
            self.assertIn(word, r.error)
        self.assertEqual(self.sk.ConstraintCount, 0)  # each refusal left nothing behind

    def test_picks_points_first_then_edges_then_axes_never_dimensions(self):
        line = self.add(Part.LineSegment(V(-10, 5, 0), V(10, 5, 0)))
        self.sk.addConstraint(Sketcher.Constraint("DistanceX", line, 1, line, 2, 20))
        self.doc.recompute()
        self.assertEqual(sym.pick_at(self.sk, V(-9.6, 5.3, 0), 1.0, 0.5), ("point", line, 1))
        self.assertEqual(sym.pick_at(self.sk, V(2, 5.3, 0), 1.0, 0.5), ("edge", line))
        self.assertEqual(sym.pick_at(self.sk, V(0.2, -7, 0), 1.0, 0.5), ("edge", sym.V_AXIS))
        self.assertEqual(sym.pick_at(self.sk, V(0.2, 0.3, 0), 1.0, 0.5), sym.ROOT)
        label = sketches.label_point(self.sk, self.sk.Constraints[0].Name) if self.sk.Constraints[0].Name else None
        if label is not None:  # a click on the dimension's label takes no dimension
            pick = sym.pick_at(self.sk, self.sk.getGlobalPlacement().inverse().multVec(label), 1.0, 0.5)
            self.assertTrue(pick is None or pick[0] in ("point", "edge"))
        self.assertIsNone(sym.pick_at(self.sk, V(30, 30, 0), 1.0, 0.5))

    def test_selection_names_round_trip(self):
        line = self.add(Part.LineSegment(V(-10, 5, 0), V(10, 5, 0)))
        for pick in (("edge", line), ("point", line, 2), ("edge", sym.H_AXIS), ("edge", sym.V_AXIS), sym.ROOT):
            self.assertEqual(sym.from_subname(self.sk, sym.subname(self.sk, pick)), pick)

    def test_a_slots_horizontal_goes(self):
        from incad.core import slots
        ids = slots.add(self.sk, V(-12, 3, 0), V(14, 3, 0), 4)
        self.doc.recompute()
        self.assertIn("Horizontal", [c.Type for c in self.sk.Constraints])
        r = self.apply(("point", ids[0], 3), ("point", ids[1], 3), ("edge", sym.V_AXIS))
        self.assertTrue(r.ok, r.error)
        self.assertNotIn("Horizontal", [c.Type for c in self.sk.Constraints])
        self.assertEqual(self.sk.solve(), 0)


if __name__ == "__main__":
    unittest.main()
