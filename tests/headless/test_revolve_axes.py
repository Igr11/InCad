"""Revolve around: the sketch's vertical/horizontal axis, a construction line of the sketch, a picked line / axis /
edge, or two points (a hidden Work Axis owned by the revolve)."""
import unittest

import FreeCAD as App
import Part
from incad.core import delete, document, safe
from incad.features import revolve
from headless import util


def profile(body, support, sub="", pts=((10, 0), (18, 0), (18, 10), (10, 10)), construction=()):
    sk = body.newObject("Sketcher::SketchObject", "Prof")
    sk.AttachmentSupport = [(support, sub)]
    sk.MapMode = "FlatFace"
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        sk.addGeometry(Part.LineSegment(App.Vector(a[0], a[1], 0), App.Vector(b[0], b[1], 0)))
    for a, b in construction:
        sk.addGeometry(Part.LineSegment(App.Vector(a[0], a[1], 0), App.Vector(b[0], b[1], 0)), True)
    body.Document.recompute()
    return sk


class RevolveAxesTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Rev")
        document.make_part(self.doc, "mm")
        self.body = document.primary_body(self.doc)
        self.xz = [o for o in self.body.Origin.OriginFeatures if o.Role == "XZ_Plane"][0]

    def make(self, sk, **over):
        values = revolve.defaults(self.doc, self.body, sk)
        values.update(over)
        f = revolve.create(self.doc, self.body, sk, values)
        self.doc.recompute()
        return f

    def test_sketch_axes_as_before(self):
        sk = profile(self.body, self.xz)
        f = self.make(sk, axis_mode="V_Axis")
        self.assertEqual(f.ReferenceAxis[1], ["V_Axis"])
        self.assertAlmostEqual(f.Shape.Volume, 3.14159265 * (18 ** 2 - 10 ** 2) * 10, places=1)
        self.assertEqual(revolve.read(self.doc, f)["axis_mode"], "V_Axis")

    def test_construction_lines_are_listed_and_one_is_the_default(self):
        sk = profile(self.body, self.xz, construction=[((5, -5), (5, 20))])
        self.assertEqual(revolve.construction_lines(sk), [("Axis0", "Line 1 · 25 mm, vertical")])
        values = revolve.defaults(self.doc, self.body, sk)
        self.assertEqual((values["axis_mode"], values["axis_construction"]), ("construction", "Axis0"))
        f = self.make(sk)
        self.assertEqual(revolve.axis_name(f.ReferenceAxis[1][0]), "Axis0")  # FreeCAD stores it as 'Axis'
        self.assertAlmostEqual(f.Shape.Volume, 3.14159265 * (13 ** 2 - 5 ** 2) * 10, places=1)
        back = revolve.read(self.doc, f)
        self.assertEqual((back["axis_mode"], back["axis_construction"]), ("construction", "Axis0"))

    def test_several_construction_lines_keep_the_sketch_axis_default_and_list_all(self):
        sk = profile(self.body, self.xz, construction=[((5, -5), (5, 20)), ((0, 30), (40, 30))])
        lines = revolve.construction_lines(sk)
        self.assertEqual([v for v, _ in lines], ["Axis0", "Axis1"])
        self.assertIn("horizontal", lines[1][1])
        self.assertEqual(revolve.defaults(self.doc, self.body, sk)["axis_mode"], "V_Axis")
        self.assertEqual(revolve.options("axis_construction", {}, sk), lines)
        f = self.make(sk, axis_mode="construction", axis_construction="Axis1")
        self.assertEqual(f.ReferenceAxis[1], ["Axis1"])

    def test_construction_mode_without_a_line_says_so(self):
        sk = profile(self.body, self.xz)
        with self.assertRaises(ValueError) as cm:
            self.make(sk, axis_mode="construction", axis_construction="")
        self.assertIn("construction or projected line", str(cm.exception))

    def test_sketch_line_origin_axis_and_solid_edge_as_reference(self):
        sk = profile(self.body, self.xz)
        f = self.make(sk, axis_mode="reference", axis_ref="%s:Edge4" % sk.Name)  # the profile's own left side
        self.assertEqual(f.ReferenceAxis[0], sk)
        self.assertAlmostEqual(f.Shape.Volume, 3.14159265 * 8 ** 2 * 10, places=1)
        back = revolve.read(self.doc, f)
        self.assertEqual((back["axis_mode"], back["axis_ref"]), ("reference", "%s:Edge4" % sk.Name))
        z = [o for o in self.body.Origin.OriginFeatures if o.Role == "Z_Axis"][0]
        values = back
        values.update(axis_ref=z.Name)
        f = revolve.update(self.doc, f, values)
        self.doc.recompute()
        self.assertEqual(f.ReferenceAxis[0], z)
        self.assertEqual(revolve.read(self.doc, f)["axis_ref"], z.Name)
        pad = util.add_pad(self.body, util.add_rect_sketch(self.body, 30, 20, name="Base"), 10)
        self.doc.recompute()
        edge = next(i + 1 for i, e in enumerate(pad.Shape.Edges)
                    if e.Curve.TypeId == "Part::GeomLine" and abs(e.Vertexes[0].Point.x - 30) < 1e-6
                    and abs(e.Vertexes[1].Point.x - 30) < 1e-6 and abs(e.Vertexes[0].Point.y - e.Vertexes[1].Point.y) < 1e-6)
        values.update(axis_ref="%s:Edge%d" % (pad.Name, edge), operation="cut")
        sk2 = profile(self.body, self.xz, pts=((5, 2), (8, 2), (8, 8), (5, 8)))
        g = self.make(sk2, axis_mode="reference", axis_ref="%s:Edge%d" % (pad.Name, edge), operation="cut")
        self.assertEqual(g.TypeId, "PartDesign::Groove")
        self.assertIn("Edge%d" % edge, g.ReferenceAxis[1])

    def test_reference_mode_without_a_pick_says_so(self):
        sk = profile(self.body, self.xz)
        with self.assertRaises(ValueError) as cm:
            self.make(sk, axis_mode="reference", axis_ref="")
        self.assertIn("Pick", str(cm.exception))

    def test_two_points_make_a_hidden_work_axis_owned_by_the_revolve(self):
        sk = profile(self.body, self.xz)
        f = self.make(sk, axis_mode="two_points", axis_points="0 0 -5;0 0 30")
        line = f.ReferenceAxis[0]
        self.assertEqual(line.TypeId, "PartDesign::Line")
        self.assertEqual(getattr(line, "InCadHelperOf"), f.Name)
        self.assertFalse(line.Visibility)
        self.assertLess(self.body.Group.index(line), self.body.Group.index(f))  # before the revolve
        self.assertIs(self.body.Tip, f)
        self.assertAlmostEqual(f.Shape.Volume, 3.14159265 * (18 ** 2 - 10 ** 2) * 10, places=1)
        back = revolve.read(self.doc, f)
        self.assertEqual((back["axis_mode"], back["axis_points"]), ("two_points", "0 0 -5;0 0 30"))
        # moved points: the same helper is re-placed, not duplicated
        back["axis_points"] = "5 0 -5;5 0 30"
        f = revolve.update(self.doc, f, back)
        self.doc.recompute()
        self.assertEqual(len([o for o in self.body.Group if o.TypeId == "PartDesign::Line"]), 1)
        self.assertAlmostEqual(f.Shape.Volume, 3.14159265 * (13 ** 2 - 5 ** 2) * 10, places=1)
        # back to a sketch axis: the helper goes away
        back = revolve.read(self.doc, f)
        back.update(axis_mode="V_Axis")
        f = revolve.update(self.doc, f, back)
        self.doc.recompute()
        self.assertEqual([o for o in self.body.Group if o.TypeId == "PartDesign::Line"], [])
        self.assertEqual(f.ReferenceAxis[1], ["V_Axis"])

    def test_two_points_need_two_different_points(self):
        sk = profile(self.body, self.xz)
        with self.assertRaises(ValueError):
            self.make(sk, axis_mode="two_points", axis_points="0 0 0")
        with self.assertRaises(ValueError):
            self.make(sk, axis_mode="two_points", axis_points="1 2 3;1 2 3")

    def test_delete_removes_the_axis_helper_with_the_revolve(self):
        sk = profile(self.body, self.xz)
        f = self.make(sk, axis_mode="two_points", axis_points="0 0 -5;0 0 30")
        name, fname = f.ReferenceAxis[0].Name, f.Name
        safe.run_safely("Delete", lambda: delete.delete(f), self.doc)
        self.assertIsNone(self.doc.getObject(fname))
        self.assertIsNone(self.doc.getObject(name))

    def test_pick_label_for_two_points(self):
        from incad.features.common import pick_label
        self.assertEqual(pick_label("two_points", ""), "Select…")
        self.assertEqual(pick_label("two_points", "0 0 0"), "1 of 2 points")
        self.assertEqual(pick_label("two_points", "0 0 0;1 1 1"), "2 points")

    def test_axis_crossing_the_profile_is_said_plainly(self):
        from incad.core import model
        self.assertIn("crosses the profile", model.friendly("Revolve axis intersects the sketch"))

    def test_cut_that_removes_everything_is_said_plainly(self):
        xy = [o for o in self.body.Origin.OriginFeatures if o.Role == "XY_Plane"][0]
        base = profile(self.body, xy, pts=((50, 50), (70, 50), (70, 70), (50, 70)))  # a pad away from the Z axis
        util.add_pad(self.body, base, 10)
        self.doc.recompute()
        sk = profile(self.body, self.xz, pts=((2, -5), (150, -5), (150, 15), (2, 15)))  # beside the Z axis, huge
        broken = safe.snapshot_broken(self.doc)
        z = [o for o in self.body.Origin.OriginFeatures if o.Role == "Z_Axis"][0]
        g = self.make(sk, axis_mode="reference", axis_ref=z.Name, operation="cut")
        found = safe.problems(self.doc, broken, {o.Name for o in self.doc.Objects})
        self.assertTrue(any("whole part" in p for p in found), found)


class RevolveProjectedAxisTest(unittest.TestCase):
    """Revolve around a PROJECTED line: the user projects an edge of the solid into the profile sketch and uses it
    as the axis. It can't be referenced as 'ExternalEdgeN' (FreeCAD rejects that), so it resolves to the source."""

    def setUp(self):
        self.doc = util.new_doc("RP")
        document.make_part(self.doc, "mm")
        self.body = document.primary_body(self.doc)
        self.pad = util.add_pad(self.body, util.add_rect_sketch(self.body, 20, 20, name="Base"), 30)
        self.doc.recompute()
        xz = [o for o in self.body.Origin.OriginFeatures if o.Role == "XZ_Plane"][0]
        self.sk = self.body.newObject("Sketcher::SketchObject", "Prof")
        self.sk.AttachmentSupport = [(xz, "")]
        self.sk.MapMode = "FlatFace"
        self.doc.recompute()
        for i, (ax, ay) in enumerate([(30, 5), (38, 5), (38, 15), (30, 15)]):
            bx, by = [(30, 5), (38, 5), (38, 15), (30, 15)][(i + 1) % 4]
            self.sk.addGeometry(Part.LineSegment(App.Vector(ax, ay, 0), App.Vector(bx, by, 0)))
        # project a vertical edge of the pad (runs along Z) into the sketch
        vedge = next(i + 1 for i, e in enumerate(self.pad.Shape.Edges)
                     if e.Curve.TypeId == "Part::GeomLine" and abs(e.Vertexes[0].Point.z - e.Vertexes[1].Point.z) > 1)
        self.sk.addExternal(self.pad.Name, "Edge%d" % vedge)
        self.doc.recompute()
        self.vedge = vedge

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_projected_line_is_listed_and_revolves_around_its_source(self):
        projected = revolve.projected_lines(self.sk)
        self.assertEqual(len(projected), 1, projected)
        value, label, ref = projected[0]
        self.assertTrue(value.startswith("ext") and "Projected" in label, (value, label))
        self.assertEqual(ref, (self.pad.Name, "Edge%d" % self.vedge))
        self.assertIn((value, label), revolve.axis_line_options(self.sk))

        values = revolve.defaults(self.doc, self.body, self.sk)
        values.update(axis_mode="construction", axis_construction=value)
        f = revolve.create(self.doc, self.body, self.sk, values)
        self.doc.recompute()
        self.assertNotIn("Invalid", f.State, f.getStatusString())
        self.assertEqual(f.ReferenceAxis[0], self.pad)  # the source edge, not the sketch's ExternalEdge
        self.assertEqual(f.ReferenceAxis[1], ["Edge%d" % self.vedge])
        self.assertGreater(f.Shape.Volume, 1)
        back = revolve.read(self.doc, f)
        self.assertEqual((back["axis_mode"], back["axis_construction"]), ("construction", value))

    def test_a_single_projected_line_is_the_default_axis(self):
        values = revolve.defaults(self.doc, self.body, self.sk)
        self.assertEqual(values["axis_mode"], "construction")
        self.assertTrue(values["axis_construction"].startswith("ext"))
