import unittest

import FreeCAD as App
import Part
import Sketcher
from incad.core import document, safe, sketch
from headless import util


def plane(body, role):
    return [o for o in body.Origin.OriginFeatures if o.Role == role][0]


class SketchTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Sk")
        self.body = document.make_part(self.doc)

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def line_sketch(self):
        sk = sketch.make_sketch(self.body, plane(self.body, "XY_Plane"))
        sk.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(20, 0, 0)))
        sk.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(0, 10, 0)))
        sk.addConstraint(Sketcher.Constraint("DistanceX", 0, 1, 0, 2, 20))
        sk.addConstraint(Sketcher.Constraint("DistanceY", 1, 1, 1, 2, 10))
        self.doc.recompute()
        return sk

    def test_valid_support(self):
        self.assertTrue(sketch.valid_support(plane(self.body, "XY_Plane")))
        self.assertFalse(sketch.valid_support(plane(self.body, "X_Axis")))
        body, pad = util.padded_part(util.new_doc("P"), 10, incad=True)
        try:
            tops = [f"Face{i + 1}" for i, f in enumerate(pad.Shape.Faces) if abs(f.CenterOfMass.z - 10) < 1e-6]
            self.assertTrue(sketch.valid_support(pad, tops[0]))
            self.assertFalse(sketch.valid_support(pad, "Edge1"))
            self.assertFalse(sketch.valid_support(None))
        finally:
            App.closeDocument(body.Document.Name)

    def test_cylindrical_face_is_not_flat(self):
        cyl = self.doc.addObject("Part::Cylinder", "Cyl")
        self.doc.recompute()
        side = [f"Face{i + 1}" for i, f in enumerate(cyl.Shape.Faces) if f.Surface.TypeId != "Part::GeomPlane"][0]
        self.assertFalse(sketch.valid_support(cyl, side))

    def test_make_sketch(self):
        a = sketch.make_sketch(self.body, plane(self.body, "XY_Plane"))
        b = sketch.make_sketch(self.body, plane(self.body, "XZ_Plane"))
        self.assertEqual((a.Label, b.Label), ("Sketch1", "Sketch2"))
        self.assertIn(a, self.body.Group)
        self.assertEqual(a.MapMode, "FlatFace")
        with self.assertRaises(ValueError):
            sketch.make_sketch(self.body, plane(self.body, "X_Axis"))

    def test_names_are_unique_across_sketches_and_parameters(self):
        document.set_parameter(self.doc, "d5", "1 mm")
        sk = self.line_sketch()
        self.assertEqual(sketch.name_new_dimensions(self.doc), ["d6", "d7"])
        sk2 = self.line_sketch()
        sk2.renameConstraint(0, "Len")
        self.assertEqual(sketch.name_new_dimensions(self.doc), ["d8"])
        self.assertEqual(sketch.name_new_dimensions(self.doc), [])
        self.assertEqual(sorted(n for n, _, _ in sketch.dimensions(self.doc)), ["Len", "d6", "d7", "d8"])

    def test_status(self):
        sk = self.line_sketch()
        st = sketch.status(sk)
        self.assertEqual(st["dof"], sk.DoF)
        self.assertFalse(st["fully"])
        self.assertEqual(st["conflicting"], [])

    def test_set_dimension_value_and_formulas(self):
        sk = self.line_sketch()
        sketch.name_new_dimensions(self.doc)  # d0 (X 20), d1 (Y 10)
        document.set_parameter(self.doc, "Width", "60 mm")
        sketch.set_dimension(self.doc, "d0", "40 mm")
        self.assertAlmostEqual(sk.getDatum("d0").Value, 40)
        sketch.set_dimension(self.doc, "d1", "d0 / 2")
        self.assertAlmostEqual(sk.getDatum("d1").Value, 20)
        sketch.set_dimension(self.doc, "d0", "Width / 2")
        self.assertAlmostEqual(sk.getDatum("d1").Value, 15)
        rows = {n: (f, v) for n, f, v in sketch.model_parameters(self.doc)}
        self.assertEqual(rows["d0"], ("Width / 2", "30 mm"))
        self.assertEqual(rows["d1"], ("d0 / 2", "15 mm"))
        sketch.set_dimension(self.doc, "d1", "12")  # a plain number uses the part's units
        self.assertEqual({n: (f, v) for n, f, v in sketch.model_parameters(self.doc)}["d1"], ("", "12 mm"))

    def test_bad_input(self):
        self.line_sketch()
        sketch.name_new_dimensions(self.doc)
        with self.assertRaises(ValueError):
            sketch.set_dimension(self.doc, "nope", "1")
        with self.assertRaises(ValueError):
            sketch.set_dimension(self.doc, "d0", " ")
        r = safe.run_safely("bad", lambda: sketch.set_dimension(self.doc, "d0", "Missing * 2"), self.doc)
        self.assertFalse(r.ok)

    def test_rename_keeps_formulas(self):
        self.line_sketch()
        sketch.name_new_dimensions(self.doc)
        sketch.set_dimension(self.doc, "d1", "d0 / 2")
        sketch.rename_dimension(self.doc, "d0", "Len")
        rows = {n: f for n, f, _ in sketch.model_parameters(self.doc)}
        self.assertEqual(rows["d1"], "Len / 2")
        document.set_parameter(self.doc, "Width", "1 mm")
        for bad in ("mm", "Width", "2x", "d1"):
            with self.assertRaises(ValueError, msg=bad):
                sketch.rename_dimension(self.doc, "Len", bad)

    def test_translation_roundtrip(self):
        sk = self.line_sketch()
        sketch.name_new_dimensions(self.doc)
        document.set_parameter(self.doc, "Width", "1 mm")
        expr = sketch.to_expression(self.doc, "Width + d0*2 + sin(30)")
        self.assertEqual(expr, "InCadParameters.Width + %s.Constraints.d0*2 + sin(30)" % sk.Name)
        self.assertEqual(sketch.to_display(self.doc, expr), "Width + d0*2 + sin(30)")


class NamesAreNeverReusedTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("NR")
        self.body = document.make_part(self.doc)

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_a_deleted_name_is_not_given_again(self):
        sk = sketch.make_sketch(self.body, plane(self.body, "XY_Plane"))
        sk.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(20, 0, 0)))
        sk.addConstraint(Sketcher.Constraint("DistanceX", 0, 1, 0, 2, 20))
        sk.addConstraint(Sketcher.Constraint("DistanceY", 0, 1, 0, 2, 0))
        self.doc.recompute()
        self.assertEqual(sketch.name_new_dimensions(self.doc), ["d0", "d1"])
        sk.delConstraint(1)
        sk.addConstraint(Sketcher.Constraint("DistanceY", 0, 1, 0, 2, 0))
        self.doc.recompute()
        self.assertEqual(sketch.name_new_dimensions(self.doc), ["d2"])

    def test_user_parameter_cannot_take_a_dimension_name(self):
        sk = sketch.make_sketch(self.body, plane(self.body, "XY_Plane"))
        sk.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(20, 0, 0)))
        sk.addConstraint(Sketcher.Constraint("DistanceX", 0, 1, 0, 2, 20))
        self.doc.recompute()
        sketch.name_new_dimensions(self.doc)
        with self.assertRaises(ValueError):
            document.set_parameter(self.doc, "d0", "5 mm")


class HideConstraintsTest(unittest.TestCase):
    def test_hide_and_show_keeps_dimensions(self):
        import Sketcher
        doc = util.new_doc("HC")
        try:
            body = document.make_part(doc)
            sk = util.add_rect_sketch(body)
            sk.addConstraint(Sketcher.Constraint("Horizontal", 0))
            sk.addConstraint(Sketcher.Constraint("DistanceX", 0, 1, 0, 2, 20))
            doc.recompute()
            self.assertFalse(sketch.constraints_hidden(sk))
            sketch.set_constraints_hidden(sk, True)
            self.assertTrue(sketch.constraints_hidden(sk))
            dims = [i for i, c in enumerate(sk.Constraints) if c.Type == "DistanceX"]
            self.assertFalse(sk.getVirtualSpace(dims[0]))
            sketch.set_constraints_hidden(sk, False)
            self.assertFalse(sketch.constraints_hidden(sk))
        finally:
            App.closeDocument(doc.Name)


class ConstructionChainTest(unittest.TestCase):
    """One picked edge switches its whole profile (a polygon's sides), not just itself."""
    def setUp(self):
        self.doc = util.new_doc("CC")
        body = document.make_part(self.doc)
        sk = self.sk = sketch.make_sketch(body, plane(body, "XY_Plane"))
        pts = [App.Vector(0, 0, 0), App.Vector(20, 0, 0), App.Vector(10, 15, 0)]
        for i in range(3):
            sk.addGeometry(Part.LineSegment(pts[i], pts[(i + 1) % 3]))
        for i in range(3):
            sk.addConstraint(Sketcher.Constraint("Coincident", i, 2, (i + 1) % 3, 1))
        circle = sk.addGeometry(Part.Circle(App.Vector(10, 5, 0), App.Vector(0, 0, 1), 11), True)  # polygon's
        for i in range(3):
            sk.addConstraint(Sketcher.Constraint("PointOnObject", i, 1, circle))
        self.other = sk.addGeometry(Part.LineSegment(App.Vector(50, 0, 0), App.Vector(60, 0, 0)))
        self.circle = circle
        self.doc.recompute()

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_chain_follows_joined_ends_only(self):
        self.assertEqual(sketch.chain(self.sk, [1]), {0, 1, 2})
        self.assertEqual(sketch.chain(self.sk, [self.other]), {self.other})

    def test_toggle_switches_the_whole_profile_and_back(self):
        sketch.toggle_construction(self.sk, [2])
        self.assertEqual([self.sk.getConstruction(i) for i in range(3)], [True] * 3)
        self.assertTrue(self.sk.getConstruction(self.circle))
        self.assertFalse(self.sk.getConstruction(self.other))
        sketch.toggle_construction(self.sk, [0])
        self.assertEqual([self.sk.getConstruction(i) for i in range(3)], [False] * 3)
        self.assertTrue(self.sk.getConstruction(self.circle))  # the polygon's guide circle stays construction
