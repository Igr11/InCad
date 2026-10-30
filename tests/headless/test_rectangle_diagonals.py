"""Rectangles get a construction centre point (the user: symmetry with one constraint; the diagonals show only
while a rectangle is drawn): a plain rectangle; a Center Rectangle
keeps FreeCAD's own centre point (no second one); a Rounded Rectangle's point sits between its corner arcs' centres.
The point follows the rectangle, its Symmetric icon is hidden (virtual space: the icon sat on the point and took
the clicks), a handled rectangle is not handled again, and lines that make no rectangle get nothing."""
import math
import unittest

import FreeCAD as App
import Part
import Sketcher

from incad.core import sketch as sketches

V = App.Vector


def rect(k, x0, y0, x1, y1):
    pts = [V(x0, y0, 0), V(x1, y0, 0), V(x1, y1, 0), V(x0, y1, 0)]
    ids = [k.addGeometry(Part.LineSegment(pts[i], pts[(i + 1) % 4])) for i in range(4)]
    for i in range(4):
        k.addConstraint(Sketcher.Constraint("Coincident", ids[i], 2, ids[(i + 1) % 4], 1))
    for i, t in enumerate(("Horizontal", "Vertical", "Horizontal", "Vertical")):
        k.addConstraint(Sketcher.Constraint(t, ids[i]))
    return ids


def rounded(k, x0, y0, x1, y1, r):
    """Four corner arcs of radius r and four lines between them, as FreeCAD's Rounded Rectangle draws it."""
    centres = [V(x1 - r, y0 + r, 0), V(x1 - r, y1 - r, 0), V(x0 + r, y1 - r, 0), V(x0 + r, y0 + r, 0)]
    arcs = []
    for n, c in enumerate(centres):
        a0 = -math.pi / 2 + n * math.pi / 2
        arcs.append(k.addGeometry(Part.ArcOfCircle(Part.Circle(c, V(0, 0, 1), r), a0, a0 + math.pi / 2)))
    lines = []
    for n in range(4):
        a, b = arcs[n], arcs[(n + 1) % 4]
        lines.append(k.addGeometry(Part.LineSegment(k.getPoint(a, 2), k.getPoint(b, 1))))
        k.addConstraint(Sketcher.Constraint("Tangent", a, 2, lines[-1], 1))
        k.addConstraint(Sketcher.Constraint("Tangent", lines[-1], 2, b, 1))
    for a in arcs[1:]:
        k.addConstraint(Sketcher.Constraint("Equal", arcs[0], a))
    return arcs, lines


class RectangleCentresTest(unittest.TestCase):
    def setUp(self):
        self.doc = App.newDocument("RD")
        self.k = self.doc.addObject("Sketcher::SketchObject", "Sk")

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def construction(self, kind):
        return [i for i in range(self.k.GeometryCount) if self.k.getConstruction(i) and self.k.Geometry[i].TypeId == kind]

    def test_diagonals_when_asked(self):
        """⚙ ▸ Rectangle Diagonals: the two diagonals as construction lines, tied to the corners (they follow)."""
        from incad.core import prefs
        k = self.k
        prefs.set_rectangle_diagonals(True)
        try:
            ids = rect(k, 0, 0, 40, 20)
            sketches.add_rectangle_centres(k, 0, set())
        finally:
            prefs.set_rectangle_diagonals(False)
        lines = self.construction("Part::GeomLineSegment")
        self.assertEqual(len(lines), 2)
        self.assertEqual(len(self.construction("Part::GeomPoint")), 1)
        lengths = sorted(round(k.Geometry[i].length(), 6) for i in lines)
        self.assertEqual(lengths, [round(math.hypot(40, 20), 6)] * 2)
        k.addConstraint(Sketcher.Constraint("DistanceX", ids[0], 1, ids[0], 2, 60))
        k.solve()
        self.assertEqual(sorted(round(k.Geometry[i].length(), 6) for i in lines), [round(math.hypot(60, 20), 6)] * 2,
                         "the diagonals follow the rectangle")

    def test_no_diagonals_by_default(self):
        rect(self.k, 0, 0, 40, 20)
        sketches.add_rectangle_centres(self.k, 0, set())
        self.assertEqual(self.construction("Part::GeomLineSegment"), [])

    def test_plain_rectangle(self):
        k = self.k
        ids = rect(k, -30, 5, 10, 25)
        done = set()
        self.assertEqual(sketches.add_rectangle_centres(k, 0, done), 1)
        self.assertEqual(self.construction("Part::GeomLineSegment"), [], "no construction lines")
        pt = self.construction("Part::GeomPoint")
        self.assertEqual(len(pt), 1)
        self.assertEqual(k.solve(), 0)
        c = k.getPoint(pt[0], 1)
        self.assertAlmostEqual(c.x, -10)
        self.assertAlmostEqual(c.y, 15)
        self.assertEqual(sketches.add_rectangle_centres(k, 0, done), 0, "handled once")
        sym = [n for n, c in enumerate(k.Constraints) if c.Type == "Symmetric"]
        self.assertTrue(sym and all(k.getVirtualSpace(n) for n in sym), "its icon took the clicks meant for the point")
        k.addConstraint(Sketcher.Constraint("Coincident", pt[0], 1, -1, 1))  # one constraint: centred
        self.assertEqual(k.solve(), 0)
        xs = sorted(round(k.getPoint(i, 1).x, 6) for i in ids)
        self.assertEqual(xs[0], -xs[-1])

    def test_several_at_once(self):
        k = self.k
        rect(k, 0, 0, 10, 10)
        rect(k, 20, 0, 40, 10)
        ours = set()
        self.assertEqual(sketches.add_rectangle_centres(k, 0, set(), ours), 2)
        self.assertEqual(len(ours), 2)
        self.assertEqual(k.solve(), 0)

    def test_center_rectangle_keeps_its_own_centre_point(self):
        k = self.k
        ids = rect(k, 20, -20, 40, -10)
        own = k.addGeometry(Part.Point(V(30, -15, 0)), True)  # FreeCAD's Center Rectangle makes this one
        k.addConstraint(Sketcher.Constraint("Symmetric", ids[0], 1, ids[1], 2, own, 1))
        self.assertEqual(sketches.add_rectangle_centres(k, 0, set()), 0)
        self.assertEqual(self.construction("Part::GeomPoint"), [own])
        self.assertTrue(k.getVirtualSpace(len(k.Constraints) - 1), "FreeCAD's own Symmetric icon hides too")
        self.assertEqual(k.solve(), 0)

    def test_rounded_rectangle_between_the_arc_centres(self):
        k = self.k
        rounded(k, -20, -10, 20, 10, 3)
        self.assertEqual(sketches.add_rectangle_centres(k, 0, set()), 1)
        pt = self.construction("Part::GeomPoint")[0]
        self.assertAlmostEqual(k.getPoint(pt, 1).Length, 0, places=6)
        self.assertEqual(k.solve(), 0)

    def test_it_follows_the_rectangle(self):
        k = self.k
        ids = rect(k, 0, 0, 20, 10)
        sketches.add_rectangle_centres(k, 0, set())
        k.moveGeometry(ids[1], 2, V(40, 30, 0), False)  # a corner dragged out
        pt = self.construction("Part::GeomPoint")[0]
        mid = (k.getPoint(ids[0], 1) + k.getPoint(ids[2], 1)) * 0.5  # the middle of the corners as they are now
        self.assertAlmostEqual((k.getPoint(pt, 1) - mid).Length, 0, places=6)

    def test_a_parallelogram_too(self):
        """FreeCAD's 3-Point Rectangle draws a parallelogram from three corners (Parallel sides, no right angles)."""
        k = self.k
        pts = [V(0, 0, 0), V(20, 5, 0), V(25, 20, 0), V(5, 15, 0)]
        ids = [k.addGeometry(Part.LineSegment(pts[i], pts[(i + 1) % 4])) for i in range(4)]
        for i in range(4):
            k.addConstraint(Sketcher.Constraint("Coincident", ids[i], 2, ids[(i + 1) % 4], 1))
        k.addConstraint(Sketcher.Constraint("Parallel", ids[0], ids[2]))
        k.addConstraint(Sketcher.Constraint("Parallel", ids[1], ids[3]))
        self.assertEqual(sketches.add_rectangle_centres(k, 0, set()), 1)
        self.assertEqual(k.solve(), 0)

    def test_a_kite_gets_nothing(self):
        k = self.k
        pts = [V(0, 0, 0), V(10, -5, 0), V(20, 0, 0), V(10, 15, 0)]
        ids = [k.addGeometry(Part.LineSegment(pts[i], pts[(i + 1) % 4])) for i in range(4)]
        for i in range(4):
            k.addConstraint(Sketcher.Constraint("Coincident", ids[i], 2, ids[(i + 1) % 4], 1))
        self.assertEqual(sketches.add_rectangle_centres(k, 0, set()), 0)

    def test_no_rectangle_nothing(self):
        k = self.k
        a = k.addGeometry(Part.LineSegment(V(0, 0, 0), V(10, 0, 0)))
        b = k.addGeometry(Part.LineSegment(V(10, 0, 0), V(10, 10, 0)))
        k.addConstraint(Sketcher.Constraint("Coincident", a, 2, b, 1))
        self.assertEqual(sketches.add_rectangle_centres(k, 0, set()), 0)


if __name__ == "__main__":
    unittest.main()
