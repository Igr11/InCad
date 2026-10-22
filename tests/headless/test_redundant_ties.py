"""Ties that repeat each other stop a sketch solving (FreeCAD: 'redundant constraints'). The Offset of an outline with
smooth joins (a slot, a rounded rectangle) ties only what is not implied, and a constraint tool's new tie takes off
the older ties it covers (incad.core.sketch.make_room): a slot made symmetric about an axis keeps solving."""
import unittest

import FreeCAD as App
import Part
import Sketcher

from incad.core import sketch as sketches
from incad.core import sketch_offset as so
from incad.core import slots
from headless import util

V = App.Vector


class Base(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Ties")
        body, _ = util.padded_part(self.doc, 5)
        self.sk = body.newObject("Sketcher::SketchObject", "Sk")
        self.sk.AttachmentSupport = [(util.xy_plane(body), "")]
        self.sk.MapMode = "FlatFace"
        self.doc.recompute()

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def assertSolves(self):
        self.assertEqual(self.sk.solve(), 0, "redundant %s, conflicting %s" % (
            list(self.sk.RedundantConstraints), list(self.sk.ConflictingConstraints)))
        self.doc.recompute()
        self.assertNotIn("Invalid", self.sk.State)


class OffsetSmooth(Base):
    def offset(self, edge, pointer):
        """The copy, tied all round: the sketch's degrees of freedom stay as they were."""
        chain, closed = so.outline(self.sk, edge)
        self.sk.solve()
        dof = self.sk.DoF
        new = so.add(self.sk, chain, closed, pointer)
        self.sk.solve()
        self.assertEqual(self.sk.DoF, dof)
        return new

    def check_copy(self, new, d):
        """Every copy edge is d from the original outline."""
        orig = Part.Wire(Part.__sortEdges__([self.sk.Geometry[g].toShape() for g in range(new[0])]))
        for g in new:
            e = self.sk.Geometry[g].toShape()
            for p in e.discretize(9):
                self.assertAlmostEqual(orig.distToShape(Part.Vertex(p))[0], d, places=5)

    def test_slot_outside_and_inside(self):
        for pointer, d in ((V(15, 9, 0), 4), (V(15, 3, 0), 2)):
            with self.subTest(d=d):
                self.sk.deleteAllGeometry()
                ids = slots.add(self.sk, V(0, 0, 0), V(30, 0, 0), 5)
                self.sk.addConstraint(Sketcher.Constraint("Radius", ids[0], 5))
                new, dim = self.offset(ids[2], pointer)
                self.assertEqual(len(new), 4)
                self.assertTrue(dim)
                self.assertSolves()
                self.check_copy(new, d)

    def test_slot_offset_follows_its_dimension(self):
        """The offset dimension measures between two lines (the value box offered Centers / Overall / Gap for two
        concentric arcs and failed: the user)."""
        from incad.core import overall_dims
        ids = slots.add(self.sk, V(0, 0, 0), V(30, 0, 0), 5)
        self.sk.addConstraint(Sketcher.Constraint("Radius", ids[0], 5))
        new, dim = self.offset(ids[2], V(15, 9, 0))
        index = [c.Name for c in self.sk.Constraints].index(dim)
        c = self.sk.Constraints[index]
        self.assertEqual(self.sk.Geometry[c.First].TypeId, "Part::GeomLineSegment")
        self.assertIsNone(overall_dims.kind_of(self.sk, index))
        self.sk.setDatum(dim, App.Units.Quantity("6 mm"))
        self.assertSolves()
        self.check_copy(new, 6)
        self.assertAlmostEqual(self.sk.Geometry[ids[0]].Radius, 5, places=6)  # the copy moves, not the slot

    def test_slot_at_an_angle(self):
        slots.add(self.sk, V(0, 0, 0), V(20, 12, 0), 3)
        new, dim = self.offset(2, V(-2, 8, 0))
        self.assertSolves()
        self.assertTrue(dim)

    def test_fully_tied_symmetric_slot(self):
        """The user's slot (0.9.3 showed 'redundant constraints'): centred on the origin — arc centres on the X axis,
        symmetric about the Y axis — with its radius and length dimensioned, then offset outwards."""
        ids = slots.add(self.sk, V(-11, 0, 0), V(11, 0, 0), 5.8)
        sym = self.sk.addConstraint(Sketcher.Constraint("Symmetric", ids[0], 3, ids[1], 3, -2))
        sketches.make_room(self.sk, [sym])
        self.sk.addConstraint([Sketcher.Constraint("PointOnObject", ids[0], 3, -1),
                               Sketcher.Constraint("Radius", ids[0], 5.8),
                               Sketcher.Constraint("DistanceX", ids[0], 3, ids[1], 3, 22.3706)])
        self.assertSolves()
        self.assertEqual(self.sk.DoF, 0)
        new, dim = self.offset(ids[2], V(0, 11, 0))
        self.assertSolves()
        self.check_copy(new, 11 - 5.8)  # the pointer 11 above the centre line, the side at 5.8

    def test_rounded_rectangle(self):
        r, w, h = 2, 20, 10
        g = self.sk.addGeometry([
            Part.LineSegment(V(r, 0, 0), V(w - r, 0, 0)), Part.LineSegment(V(w, r, 0), V(w, h - r, 0)),
            Part.LineSegment(V(w - r, h, 0), V(r, h, 0)), Part.LineSegment(V(0, h - r, 0), V(0, r, 0))])
        z = V(0, 0, 1)
        import math
        arcs = self.sk.addGeometry([
            Part.ArcOfCircle(Part.Circle(V(w - r, r, 0), z, r), -math.pi / 2, 0),
            Part.ArcOfCircle(Part.Circle(V(w - r, h - r, 0), z, r), 0, math.pi / 2),
            Part.ArcOfCircle(Part.Circle(V(r, h - r, 0), z, r), math.pi / 2, math.pi),
            Part.ArcOfCircle(Part.Circle(V(r, r, 0), z, r), math.pi, 3 * math.pi / 2)])
        a = arcs
        self.sk.addConstraint([
            Sketcher.Constraint("Tangent", g[0], 2, a[0], 1), Sketcher.Constraint("Tangent", a[0], 2, g[1], 1),
            Sketcher.Constraint("Tangent", g[1], 2, a[1], 1), Sketcher.Constraint("Tangent", a[1], 2, g[2], 1),
            Sketcher.Constraint("Tangent", g[2], 2, a[2], 1), Sketcher.Constraint("Tangent", a[2], 2, g[3], 1),
            Sketcher.Constraint("Tangent", g[3], 2, a[3], 1), Sketcher.Constraint("Tangent", a[3], 2, g[0], 1),
            Sketcher.Constraint("Horizontal", g[0]), Sketcher.Constraint("Vertical", g[1])])
        self.assertSolves()
        new, dim = self.offset(g[0], V(10, -3, 0))
        self.assertEqual(len(new), 8)
        self.assertSolves()
        self.check_copy(new, 3)


class Concentric(Base):
    def test_no_centres_overall_gap_for_concentric_circles(self):
        """A circle's Offset: its dimension is circle to circle, concentric — the value box offers no kinds."""
        from incad.core import overall_dims
        c = self.sk.addGeometry(Part.Circle(V(0, 0, 0), V(0, 0, 1), 5))
        new, dim = so.add(self.sk, [c], True, V(8, 0, 0))
        index = [k.Name for k in self.sk.Constraints].index(dim)
        self.assertIsNone(overall_dims.kind_of(self.sk, index))
        a = self.sk.addGeometry(Part.Circle(V(20, 0, 0), V(0, 0, 1), 2))
        gap = self.sk.addConstraint(Sketcher.Constraint("Distance", c, a, 3))
        self.assertEqual(overall_dims.kind_of(self.sk, gap)[0], "gap")  # apart: still offered


class MakeRoom(Base):
    def test_slot_symmetric_about_the_axis(self):
        ids = slots.add(self.sk, V(-12, 3, 0), V(14, 3, 0), 4)  # Horizontal on its line
        new = self.sk.addConstraint(Sketcher.Constraint("Symmetric", ids[0], 3, ids[1], 3, -2))
        self.assertTrue(sketches.redundant(self.sk))  # FreeCAD names the Horizontal or the Symmetric
        gone = sketches.make_room(self.sk, [new])
        self.assertEqual(gone, ["Horizontal"])
        self.assertSolves()
        self.assertIn("Symmetric", [c.Type for c in self.sk.Constraints])
        c1, c2 = self.sk.getPoint(ids[0], 3), self.sk.getPoint(ids[1], 3)
        self.assertAlmostEqual(c1.x, -c2.x, places=6)
        self.assertAlmostEqual(c1.y, c2.y, places=6)

    def test_parallel_of_two_horizontal_lines(self):
        a = self.sk.addGeometry(Part.LineSegment(V(0, 0, 0), V(10, 0, 0)))
        b = self.sk.addGeometry(Part.LineSegment(V(0, 5, 0), V(10, 5, 0)))
        self.sk.addConstraint([Sketcher.Constraint("Horizontal", a), Sketcher.Constraint("Horizontal", b)])
        new = self.sk.addConstraint(Sketcher.Constraint("Parallel", a, b))
        self.assertEqual(sketches.make_room(self.sk, [new]), ["Horizontal"])
        self.assertSolves()
        self.assertEqual(sorted(c.Type for c in self.sk.Constraints), ["Horizontal", "Parallel"])

    def test_nothing_to_take_off_drops_the_repeat(self):
        a = self.sk.addGeometry(Part.LineSegment(V(0, 0, 0), V(10, 0, 0)))
        b = self.sk.addGeometry(Part.LineSegment(V(10, 0, 0), V(10, 5, 0)))
        self.sk.addConstraint(Sketcher.Constraint("Coincident", a, 2, b, 1))
        first = self.sk.addConstraint(Sketcher.Constraint("Coincident", a, 2, b, 1))  # the same twice: nothing implied
        self.assertTrue(sketches.make_room(self.sk, [first]))
        self.assertSolves()
        self.assertEqual([c.Type for c in self.sk.Constraints], ["Coincident"])

    def test_solving_sketch_untouched(self):
        ids = slots.add(self.sk, V(0, 0, 0), V(20, 0, 0), 3)
        n = self.sk.ConstraintCount
        self.assertEqual(sketches.make_room(self.sk, [n - 1]), [])
        self.assertEqual(self.sk.ConstraintCount, n)
