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

    def test_plain_numbers_added_to_a_dimension_take_its_unit(self):
        """Inventor: d16+2 means 2 of the part's unit; FreeCAD refused it ('Unit mismatch')."""
        sk = self.line_sketch()
        sketch.name_new_dimensions(self.doc)  # d0 = 20 mm, d1 = 10 mm
        sketch.set_dimension(self.doc, "d1", "d0+2")
        self.assertAlmostEqual(sk.getDatum("d1").Value, 22)
        sketch.set_dimension(self.doc, "d1", "(d0 - 4) / 2 + 1")
        self.assertAlmostEqual(sk.getDatum("d1").Value, 9)
        rows = {n: f for n, f, v in sketch.model_parameters(self.doc)}
        self.assertEqual(rows["d1"], "(d0 - 4 mm) / 2 + 1 mm")  # shown with the units, as Inventor does

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

    def test_a_construction_line_joined_to_normal_geometry_toggles_back_to_normal(self):
        """The direction comes from the picked edge, not its chain: a construction line joined to a normal profile
        used to read the mixed chain as 'make construction' and never flip back."""
        import Part
        cl = self.sk.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(20, 0, 0)), True)  # construction
        self.sk.addConstraint(Sketcher.Constraint("Coincident", cl, 1, 0, 1))  # joined to the profile's corner
        self.doc.recompute()
        self.assertTrue(self.sk.getConstruction(cl))
        sketch.toggle_construction(self.sk, [cl])  # construction -> normal
        self.assertFalse(self.sk.getConstruction(cl))
        self.assertEqual([self.sk.getConstruction(i) for i in range(3)], [False] * 3)  # the profile is left normal
        sketch.toggle_construction(self.sk, [cl])  # normal -> construction again
        self.assertTrue(self.sk.getConstruction(cl))

    def test_a_single_construction_line_toggles_both_ways(self):
        import Part
        g = self.sk.addGeometry(Part.LineSegment(App.Vector(70, 0, 0), App.Vector(80, 0, 0)), True)
        self.doc.recompute()
        for want in (False, True, False):
            sketch.toggle_construction(self.sk, [g])
            self.assertEqual(self.sk.getConstruction(g), want)

    def test_a_projected_line_becomes_a_normal_line_tied_to_it(self):
        """External (projected) geometry is always construction in FreeCAD and cannot be switched, so the
        Construction button puts a NORMAL line of the same size and place on it, joined at both ends."""
        doc = util.new_doc("Proj")
        try:
            body, pad = util.padded_part(doc, 10, incad=True)
            sk = sketch.make_sketch(body, plane(body, "XY_Plane"))
            edge = [i + 1 for i, e in enumerate(pad.Shape.Edges)
                    if all(abs(v.Z) < 1e-6 for v in e.Vertexes) and e.Curve.TypeId == "Part::GeomLine"][0]
            sk.addExternal(pad.Name, "Edge%d" % edge)
            doc.recompute()
            ext = -3  # the first projected item after the two axes
            self.assertTrue(sk.getConstruction(ext))
            before = sk.GeometryCount
            new = sketch.toggle_construction(sk, [ext])
            self.assertEqual(sk.GeometryCount, before + 1)
            self.assertEqual(new, [before])
            line, src = sk.Geometry[before], sk.ExternalGeo[2]
            self.assertFalse(sk.getConstruction(before))
            self.assertLess(line.StartPoint.distanceToPoint(src.StartPoint), 1e-6)
            self.assertLess(line.EndPoint.distanceToPoint(src.EndPoint), 1e-6)
            tied = {(c.First, c.FirstPos, c.Second, c.SecondPos) for c in sk.Constraints if c.Type == "Coincident"}
            self.assertIn((before, 1, ext, 1), tied)
            self.assertIn((before, 2, ext, 2), tied)
            # picking the new (normal) line switches it to construction and back as usual
            sketch.toggle_construction(sk, [before])
            self.assertTrue(sk.getConstruction(before))
            sketch.toggle_construction(sk, [before])
            self.assertFalse(sk.getConstruction(before))
            # the copy lies exactly on the projected line, so a click can pick the projected one again: that
            # toggles back (the copy goes), never piles up more copies
            sketch.toggle_construction(sk, [ext])
            self.assertEqual(sk.GeometryCount, before)
            sketch.toggle_construction(sk, [ext])
            self.assertEqual(sk.GeometryCount, before + 1)
            self.assertFalse(sk.getConstruction(before))
            sketch.toggle_construction(sk, [ext])
            self.assertEqual(sk.GeometryCount, before)
        finally:
            App.closeDocument(doc.Name)


class PolygonCentreTest(unittest.TestCase):
    """A polygon's centre drawn on the origin or an axis keeps that constraint, as Inventor remembers the snap."""
    def setUp(self):
        self.doc = util.new_doc("PC")
        body = document.make_part(self.doc)
        self.sk = sketch.make_sketch(body, plane(body, "XY_Plane"))

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def polygon(self, centre):
        from ProfileLib import RegularPolygon
        first = self.sk.GeometryCount
        RegularPolygon.makeRegularPolygon(self.sk, 6, centre, centre + App.Vector(8, 3, 0), False)
        circle = [i for i in range(first, self.sk.GeometryCount) if self.sk.Geometry[i].TypeId == "Part::GeomCircle"][0]
        return first, circle

    def to_origin(self, circle):
        return [c for c in self.sk.Constraints if c.Type == "Coincident" and {(c.First, c.FirstPos), (c.Second, c.SecondPos)}
                == {(circle, 3), (-1, 1)}]

    def test_centre_on_the_origin_becomes_coincident(self):
        first, circle = self.polygon(App.Vector(0, 0, 0))
        self.assertEqual(sketch.pin_polygon_centres(self.sk, first), [circle])
        self.assertEqual(len(self.to_origin(circle)), 1)
        self.assertEqual(sketch.pin_polygon_centres(self.sk, first), [])  # already there: nothing twice

    def test_centre_on_an_axis_lies_on_it(self):
        first, circle = self.polygon(App.Vector(0, 12, 0))
        sketch.pin_polygon_centres(self.sk, first)
        on = [c for c in self.sk.Constraints if c.Type == "PointOnObject" and c.First == circle and c.Second == -2]
        self.assertEqual(len(on), 1)  # the Y axis

    def test_centre_elsewhere_is_left_free(self):
        first, circle = self.polygon(App.Vector(5, 7, 0))
        n = len(self.sk.Constraints)
        self.assertEqual(sketch.pin_polygon_centres(self.sk, first), [])
        self.assertEqual(len(self.sk.Constraints), n)


class LabelPointTest(unittest.TestCase):
    """Where FreeCAD draws a dimension's text (its SoDatumLabel): the two points moved by LabelDistance along the
    datum normal, the text in the middle moved by LabelPosition along the datum."""
    def setUp(self):
        self.doc = util.new_doc("LP")
        body = document.make_part(self.doc)
        self.sk = sketch.make_sketch(body, plane(body, "XZ_Plane"))  # a non-trivial placement
        pts = [App.Vector(0, 0, 0), App.Vector(20, 0, 0), App.Vector(20, 10, 0), App.Vector(0, 10, 0)]
        for i in range(4):
            self.sk.addGeometry(Part.LineSegment(pts[i], pts[(i + 1) % 4]))
        self.sk.addConstraint(Sketcher.Constraint("DistanceX", 0, 1, 0, 2, 20))   # bottom, left->right
        self.sk.addConstraint(Sketcher.Constraint("DistanceY", 1, 1, 1, 2, 10))   # right, up
        self.sk.addConstraint(Sketcher.Constraint("Distance", 2, 20))             # top line, right->left
        self.sk.addConstraint(Sketcher.Constraint("Distance", 0, 1, 2, 1, 22.36))  # diagonal (0,0)-(20,10)
        self.doc.recompute()
        sketch.name_new_dimensions(self.doc)  # d0..d3

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def local(self, name):
        return self.sk.getGlobalPlacement().inverse().multVec(sketch.label_point(self.sk, name))

    def test_distance_x_and_y(self):
        self.assertAlmostEqual((self.local("d0") - App.Vector(10, 10, 0)).Length, 0, places=2)   # LabelDistance 10 up
        self.assertAlmostEqual((self.local("d1") - App.Vector(10, 5, 0)).Length, 0, places=2)    # 10 to the left

    def test_distance_along_a_line_and_between_points(self):
        self.assertAlmostEqual((self.local("d2") - App.Vector(10, 0, 0)).Length, 0, places=2)  # normal of (-1,0) is (0,-1)
        d = App.Vector(20, 10, 0); d.normalize()
        n = App.Vector(-d.y, d.x, 0)
        self.assertAlmostEqual((self.local("d3") - (App.Vector(10, 5, 0) + n * 10)).Length, 0, places=2)

    def test_is_a_global_point(self):
        p = sketch.label_point(self.sk, "d0")
        self.assertAlmostEqual(p.y, 0, places=6)  # the XZ plane: sketch y is global z
        self.assertAlmostEqual(p.z, 10, places=6)

    def test_unknown_or_non_dimensional_name_is_none(self):
        self.assertIsNone(sketch.label_point(self.sk, "nope"))


class ReplacedDimensionTest(unittest.TestCase):
    """FreeCAD 1.1's Dimension tool makes a constraint at the first click and replaces it at the placing click:
    the replacement must keep the name and the value the user already gave it, whether or not a box is open."""
    def setUp(self):
        self.doc = util.new_doc("RD")
        body = document.make_part(self.doc)
        self.sk = sketch.make_sketch(body, plane(body, "XY_Plane"))
        pts = [App.Vector(0, 0, 0), App.Vector(20, 0, 0), App.Vector(20, 10, 0), App.Vector(0, 10, 0)]
        for i in range(4):
            self.sk.addGeometry(Part.LineSegment(pts[i], pts[(i + 1) % 4]))
        self.sk.addConstraint(Sketcher.Constraint("DistanceX", 0, 1, 0, 2, 20))
        self.doc.recompute()
        sketch.name_new_dimensions(self.doc)  # d0
        self.known = sketch.dimension_snapshot(self.sk)

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def replace(self):
        i = [k for k, c in enumerate(self.sk.Constraints) if c.Name == "d0"][0]
        self.sk.delConstraint(i)
        self.sk.addConstraint(Sketcher.Constraint("DistanceX", 0, 1, 0, 2, 20))
        self.doc.recompute()

    def test_snapshot_lists_named_dimensions(self):
        self.assertEqual(set(self.known), {"d0"})
        self.assertEqual(self.known["d0"]["type"], "DistanceX")

    def test_replacement_keeps_the_name_and_no_number_is_burned(self):
        self.replace()
        self.assertEqual(sketch.reconcile_replaced(self.sk, self.known), "d0")
        self.assertEqual([c.Name for c in self.sk.Constraints if c.Name], ["d0"])
        self.assertEqual(sketch.name_new_dimensions(self.doc), [])  # nothing left to name

    def test_replacement_keeps_a_typed_value_and_formula(self):
        sketch.set_dimension(self.doc, "d0", "25 mm")
        known = sketch.dimension_snapshot(self.sk)
        self.replace()
        sketch.reconcile_replaced(self.sk, known)
        self.assertAlmostEqual(self.sk.getDatum("d0").Value, 25)
        document.set_parameter(self.doc, "Width", "40 mm")
        sketch.set_dimension(self.doc, "d0", "Width / 2")
        known = sketch.dimension_snapshot(self.sk)
        self.replace()
        sketch.reconcile_replaced(self.sk, known)
        self.doc.recompute()
        self.assertAlmostEqual(self.sk.getDatum("d0").Value, 20)
        self.assertEqual({n: f for n, f, v in sketch.model_parameters(self.doc)}["d0"], "Width / 2")

    def test_nothing_to_reconcile(self):
        self.assertIsNone(sketch.reconcile_replaced(self.sk, self.known))
        self.sk.addConstraint(Sketcher.Constraint("DistanceY", 1, 1, 1, 2, 10))  # a plain new one, d0 still there
        self.doc.recompute()
        self.assertIsNone(sketch.reconcile_replaced(self.sk, self.known))
        self.assertEqual(sketch.name_new_dimensions(self.doc), ["d1"])

    def test_vanished_without_replacement_is_reported(self):
        i = [k for k, c in enumerate(self.sk.Constraints) if c.Name == "d0"][0]
        self.sk.delConstraint(i)
        self.doc.recompute()
        self.assertEqual(sketch.vanished_dimensions(self.sk, self.known), ["d0"])

    def test_while_the_tools_undo_step_is_open_only_the_name_is_put_back(self):
        sketch.set_dimension(self.doc, "d0", "25 mm")
        known = sketch.dimension_snapshot(self.sk)
        self.doc.openTransaction("Add sketch dimension")  # as FreeCAD's Dimension tool does while placing
        self.replace()
        n = len(self.doc.UndoNames)
        self.assertEqual(sketch.reconcile_replaced(self.sk, known), "d0")
        self.assertEqual(self.sk.Constraints[-1].Name, "d0")
        self.assertAlmostEqual(self.sk.getDatum("d0").Value, 20)  # the value waits for the tool to finish
        self.assertEqual(len(self.doc.UndoNames), n)  # nothing of ours committed over the tool's step
        self.assertTrue(self.doc.HasPendingTransaction)
        self.doc.commitTransaction()


class FriendlyMessageTest(unittest.TestCase):
    def test_glued_number_and_name(self):
        from incad.core import model
        self.assertIn("operator", model.friendly("Failed to parse expression '30d0'"))
        self.assertIn("30", model.friendly("Failed to parse expression '30d0'"))
        self.assertNotIn("Constraints", model.friendly("Failed to parse expression 'Sketch002.Constraints.d16=2'"))
        self.assertIn("d16=2", model.friendly("Failed to parse expression 'Sketch002.Constraints.d16=2'"))

    def test_units_skip_function_arguments(self):
        from incad.core import model
        self.assertEqual(model.with_units("sqrt(4) + d1", "mm"), "sqrt(4) + d1")
        self.assertEqual(model.with_units("d1 + (2 + 3) * 2", "mm"), "d1 + (2 mm + 3 mm) * 2")
