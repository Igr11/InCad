"""Sketch constraints listed for the Constraints window: what each one is, what it ties, filtered by a pick."""
import unittest

import FreeCAD as App
import Part
import Sketcher
from incad.core import document, sketch_constraints as sc
from headless import util


def rect(sk):
    """A 60 x 45 rectangle: Lines 1-4, four corner coincidents, H/V, two dimensions d1, d2."""
    p = [App.Vector(0, 0, 0), App.Vector(60, 0, 0), App.Vector(60, 45, 0), App.Vector(0, 45, 0)]
    for i in range(4):
        sk.addGeometry(Part.LineSegment(p[i], p[(i + 1) % 4]))
    for i in range(4):
        sk.addConstraint(Sketcher.Constraint("Coincident", i, 2, (i + 1) % 4, 1))
    sk.addConstraint(Sketcher.Constraint("Horizontal", 0))
    sk.addConstraint(Sketcher.Constraint("Horizontal", 2))
    sk.addConstraint(Sketcher.Constraint("Vertical", 1))
    sk.addConstraint(Sketcher.Constraint("Vertical", 3))
    i = sk.addConstraint(Sketcher.Constraint("DistanceX", 0, 1, 0, 2, 60.0))
    sk.renameConstraint(i, "d1")
    i = sk.addConstraint(Sketcher.Constraint("DistanceY", 1, 1, 1, 2, 45.0))
    sk.renameConstraint(i, "d2")


class RowsTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Sc")
        self.body = document.make_part(self.doc)
        self.sk = self.body.newObject("Sketcher::SketchObject", "Sk")
        self.sk.AttachmentSupport = [(util.xy_plane(self.body), "")]
        self.sk.MapMode = "FlatFace"
        rect(self.sk)
        self.doc.recompute()

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_every_constraint_is_a_row_in_order(self):
        rs = sc.rows(self.sk)
        self.assertEqual([r.index for r in rs], list(range(10)))
        self.assertEqual([r.type for r in rs[:6]], ["Coincident"] * 4 + ["Horizontal"] * 2)
        self.assertEqual(rs[0].text, "Line 1 end ↔ Line 2 start")
        self.assertEqual(rs[4].text, "Line 1")
        self.assertEqual((rs[8].type, rs[8].name, rs[8].value), ("Horizontal Distance", "d1", "60 mm"))

    def test_a_formula_shows_as_written(self):
        self.sk.setExpression("Constraints.d2", "d1 / 2")
        self.doc.recompute()
        self.assertEqual(sc.rows(self.sk)[9].value, "d1 / 2")

    def test_axes_origin_projected_and_construction_are_named(self):
        sk = self.sk
        sk.addGeometry(Part.Point(App.Vector(10, 10, 0)), True)  # Point 5 (construction)
        sk.addConstraint(Sketcher.Constraint("PointOnObject", 4, 1, -1))
        sk.addConstraint(Sketcher.Constraint("Coincident", 0, 1, -1, 1))
        self.assertEqual(sc.element_name(sk, 4, 1), "Point 5 (construction)")
        self.assertEqual(sc.element_name(sk, -1, 0), "X axis")
        self.assertEqual(sc.element_name(sk, -1, 1), "Origin")
        self.assertEqual(sc.element_name(sk, -2, 0), "Y axis")
        self.assertEqual(sc.element_name(sk, -3, 0), "Projected edge 1")
        rs = sc.rows(sk)
        self.assertEqual(rs[-2].text, "Point 5 (construction) ↔ X axis")
        self.assertEqual(rs[-1].text, "Line 1 start ↔ Origin")

    def test_filter_by_an_edge_and_by_a_vertex(self):
        self.assertEqual([r.index for r in sc.for_elements(self.sk, ["Edge1"])], [0, 3, 4, 8])
        v = self.sk.getGeoVertexIndex  # which Vertex is Line 2's start: find it, FreeCAD numbers vertices itself
        name = next("Vertex%d" % (i + 1) for i in range(8) if v(i) == (1, 1))
        self.assertEqual([r.index for r in sc.for_elements(self.sk, [name])], [0, 9])
        self.assertEqual(len(sc.for_elements(self.sk, [])), 10)

    def test_a_pattern_tie_names_its_pattern(self):
        i = self.sk.addConstraint(Sketcher.Constraint("Equal", 0, 2))
        self.sk.renameConstraint(i, "pat3_0")
        self.assertEqual(sc.rows(self.sk)[i].owner, "Pattern3")
