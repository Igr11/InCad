import math
import unittest

import FreeCAD as App
from incad.features import work
from headless import util


class WorkTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Wk")
        self.body, self.pad = util.padded_part(self.doc, 10, incad=True)

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_offset_plane(self):
        xy = [o for o in self.body.Origin.OriginFeatures if o.Role == "XY_Plane"][0]
        k = work.PLANE
        f = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None), base=xy.Name,
                                                     offset="15 mm"))
        self.doc.recompute()
        self.assertAlmostEqual(f.Placement.Base.z, 15, places=6)
        self.assertEqual(k.read(self.doc, f)["offset"], "15 mm")

    def test_several_offset_planes_in_one_go(self):
        """Planes = 3: three planes 10, 20, 30 mm off the base (for a loft); a new offset spaces them all, a new count
        adds or drops planes, and one plane of the row can still be moved on its own."""
        xy = util.xy_plane(self.body)
        k = work.PLANE
        f = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None), base=xy.Name,
                                                     offset="10 mm", count="3"))
        self.doc.recompute()
        row = work.series(self.doc, f)
        self.assertEqual([round(p.Placement.Base.z, 6) for p in [f] + row], [10, 20, 30])
        self.assertEqual(k.read(self.doc, f)["count"], "3")
        k.update(self.doc, f, dict(k.read(self.doc, f), offset="5 mm", count="4"))
        self.doc.recompute()
        row = work.series(self.doc, f)
        self.assertEqual([round(p.Placement.Base.z, 6) for p in [f] + row], [5, 10, 15, 20])
        k.update(self.doc, f, dict(k.read(self.doc, f), count="2"))
        self.doc.recompute()
        row = work.series(self.doc, f)
        self.assertEqual([round(p.Placement.Base.z, 6) for p in [f] + row], [5, 10])
        self.assertEqual(len([o for o in self.body.Group if o.TypeId == "PartDesign::Plane"]), 2)
        second = row[0]
        self.assertIn("* 2", k.read(self.doc, second)["offset"])
        k.update(self.doc, second, dict(k.read(self.doc, second), offset="12 mm"))
        self.doc.recompute()
        self.assertAlmostEqual(second.Placement.Base.z, 12, places=6)
        self.assertAlmostEqual(f.Placement.Base.z, 5, places=6)

    def test_turn_a_plane_of_the_row(self):
        """Turn X / Y / Z (the user: loft planes turned about their axes, relative to the previous plane or the global
        axes): the plane turns about its own point; turning one leaves the next as it was."""
        k = work.PLANE
        f = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None),
                                                     base=util.xy_plane(self.body).Name, offset="10 mm", count="3"))
        self.doc.recompute()
        second, third = work.series(self.doc, f)
        n = lambda p: p.Placement.Rotation.multVec(App.Vector(0, 0, 1))
        k.update(self.doc, second, dict(k.read(self.doc, second), turn_x="30 °"))
        self.doc.recompute()
        self.assertAlmostEqual(second.Placement.Base.z, 20, places=6)  # turned about its own point
        self.assertAlmostEqual(n(second).getAngle(App.Vector(0, 0, 1)), math.radians(30), places=6)
        self.assertAlmostEqual(n(third).getAngle(App.Vector(0, 0, 1)), 0, places=9)  # the next one as it was
        self.assertEqual(k.read(self.doc, second)["turn_x"], "30 °")
        # the third: 10° more than the second, relative to it; then read in global axes
        k.update(self.doc, third, dict(k.read(self.doc, third), turn_ref="previous", turn_x="10 °", turn_y="0 °",
                                       turn_z="0 °"))
        self.doc.recompute()
        self.assertAlmostEqual(n(third).getAngle(App.Vector(0, 0, 1)), math.radians(40), places=6)
        self.assertEqual(k.read(self.doc, third)["turn_x"], "10 °")
        k.update(self.doc, second, dict(k.read(self.doc, second), turn_x="0 °"))  # the second back: the third stays
        self.doc.recompute()
        self.assertAlmostEqual(n(third).getAngle(App.Vector(0, 0, 1)), math.radians(40), places=6)
        g = dict(k.read(self.doc, third), turn_ref="global")
        self.assertEqual(work.turn_text(self.doc, third, "global")["turn_x"], "40 °")
        k.update(self.doc, third, dict(g, turn_x="-15 °", turn_y="0 °", turn_z="0 °"))
        self.doc.recompute()
        self.assertAlmostEqual(n(third).getAngle(App.Vector(0, 0, 1)), math.radians(15), places=6)
        self.assertAlmostEqual(third.Placement.Base.z, 30, places=6)

    def test_axis_through_an_edge(self):
        k = work.AXIS
        f = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None),
                                                     edge="%s:Edge1" % self.pad.Name))
        self.doc.recompute()
        self.assertEqual(f.State, ["Up-to-date"])

    def test_point_at_a_vertex(self):
        k = work.POINT
        f = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None),
                                                     vertex="%s:Vertex1" % self.pad.Name))
        self.doc.recompute()
        v = self.pad.Shape.Vertexes[0].Point
        self.assertAlmostEqual((f.Placement.Base - v).Length, 0, places=6)

    def test_three_marker_points_corners_follow_others_are_fixed(self):
        """Work Plane ▸ Three points clicked on Section's markers: the part's corners become vertex picks (the plane
        follows them), an edge middle or a circle centre a fixed point; the plane goes through all three."""
        k = work.PLANE
        vs = self.pad.Shape.Vertexes
        e = self.pad.Shape.Edges[0]
        middle = e.valueAt((e.FirstParameter + e.LastParameter) / 2)
        corners = [v.Point for v in vs if (v.Point - e.Vertexes[0].Point).Length > 1e-6
                   and (v.Point - e.Vertexes[-1].Point).Length > 1e-6]
        a, b = corners[0], [c for c in corners if ((c - corners[0]).cross(middle - corners[0])).Length > 1e-3][0]
        text = work.format_point_picks(self.body, self.pad, [a, middle, b])
        items = text.split(",")
        self.assertTrue(items[0].startswith(self.pad.Name + ":Vertex") and items[2].startswith(self.pad.Name + ":"))
        self.assertTrue(items[1].startswith("@"), items)
        for body_at in (App.Placement(), App.Placement(App.Vector(5, -7, 3), App.Rotation(App.Vector(0, 0, 1), 30))):
            self.body.Placement = body_at
            self.doc.recompute()
            glob = [body_at.multVec(p) for p in (a, middle, b)]  # the markers are drawn where the part is
            text = work.format_point_picks(self.body, self.pad, glob)
            self.assertEqual(text.split(",")[0], items[0])
            f = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None), mode="three_points",
                                                         points=text))
            self.doc.recompute()
            self.assertNotIn("Invalid", f.State)
            n = f.Placement.Rotation.multVec(App.Vector(0, 0, 1))  # the plane in its body
            for p in (a, middle, b):
                self.assertAlmostEqual((p - f.Placement.Base).dot(n), 0, places=6)
            r = k.read(self.doc, f)
            self.assertEqual((r["mode"], r["points"]), ("three_points", text))
            k.update(self.doc, f, r)
            self.doc.recompute()
            self.assertNotIn("Invalid", f.State)

    def test_three_points_in_a_line_refused(self):
        k = work.PLANE
        with self.assertRaises(ValueError):
            k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None), mode="three_points",
                                                     points="@0 0 0,@1 1 1,@2 2 2"))

    def test_three_point_plane_and_two_point_axis_round_trip(self):
        pts = "%s:Vertex1,%s:Vertex2,%s:Vertex3" % ((self.pad.Name,) * 3)
        k = work.PLANE
        f = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None), mode="three_points",
                                                     points=pts))
        self.doc.recompute()
        r = k.read(self.doc, f)
        self.assertEqual((r["mode"], r["points"]), ("three_points", pts))
        k.update(self.doc, f, r)
        self.doc.recompute()
        self.assertNotIn("Invalid", f.State)
        a = work.AXIS
        two = "%s:Vertex1,%s:Vertex2" % ((self.pad.Name,) * 2)
        g = a.create(self.doc, self.body, None, dict(a.defaults(self.doc, self.body, None), mode="two_points",
                                                     points=two))
        self.doc.recompute()
        r = a.read(self.doc, g)
        self.assertEqual((r["mode"], r["points"]), ("two_points", two))
        a.update(self.doc, g, r)
        self.doc.recompute()
        self.assertNotIn("Invalid", g.State)


class InventorWorkFeaturesTest(unittest.TestCase):
    """Box 20 x 10 x 10 (padded_part) plus a Ø6 cylinder at (30, 5)."""

    def setUp(self):
        import Part
        self.doc = util.new_doc("Wi")
        self.body, self.pad = util.padded_part(self.doc, 10, incad=True)
        sk = self.body.newObject("Sketcher::SketchObject", "CylSk")
        sk.AttachmentSupport = [(util.xy_plane(self.body), "")]
        sk.MapMode = "FlatFace"
        sk.addGeometry(Part.Circle(App.Vector(30, 5, 0), App.Vector(0, 0, 1), 3))
        self.cyl = util.add_pad(self.body, sk, 10, "Cyl")
        self.body.Tip = self.cyl
        self.doc.recompute()
        S = self.cyl.Shape
        self.name = self.cyl.Name
        self.top = self._face(lambda f: f.Surface.TypeId == "Part::GeomPlane" and abs(f.CenterOfMass.z - 10) < 1e-6
                              and f.Area > 150)
        self.bottom = self._face(lambda f: f.Surface.TypeId == "Part::GeomPlane" and abs(f.CenterOfMass.z) < 1e-6
                                 and f.Area > 150)
        self.side = self._face(lambda f: f.Surface.TypeId == "Part::GeomPlane" and abs(f.CenterOfMass.x) < 1e-6)
        self.cylface = self._face(lambda f: f.Surface.TypeId == "Part::GeomCylinder")
        self.top_edge = self._edge(lambda e: e.Curve.TypeId == "Part::GeomLine" and abs(e.BoundBox.ZMin - 10) < 1e-6
                                   and abs(e.BoundBox.ZMax - 10) < 1e-6 and abs(e.BoundBox.YMin) < 1e-6)
        self.vertical = self._edge(lambda e: e.Curve.TypeId == "Part::GeomLine" and e.BoundBox.ZLength > 9)
        self.circle = self._edge(lambda e: e.Curve.TypeId == "Part::GeomCircle" and abs(e.BoundBox.ZMax - 10) < 1e-6)
        self.v_top = self._vertex(lambda v: abs(v.Point.z - 10) < 1e-6 and v.Point.x < 1e-6)

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def _pick(self, kind, pred):
        items = getattr(self.cyl.Shape, kind + "s")
        return "%s:%s%d" % (self.name, kind, [i + 1 for i, x in enumerate(items) if pred(x)][0])

    def _face(self, pred):
        return self._pick("Face", pred)

    def _edge(self, pred):
        return self._pick("Edge", pred)

    def _vertex(self, pred):
        return "%s:Vertex%d" % (self.name, [i + 1 for i, v in enumerate(self.cyl.Shape.Vertexes) if pred(v)][0])

    def make(self, kind, **values):
        v = dict(kind.defaults(self.doc, self.body, None), **values)
        f = kind.create(self.doc, self.body, None, v)
        self.doc.recompute()
        self.assertNotIn("Invalid", f.State, (values, f.getStatusString()))
        r = kind.read(self.doc, f)
        self.assertEqual(r["mode"], values["mode"])
        return f

    def normal(self, f):
        return f.Placement.Rotation.multVec(App.Vector(0, 0, 1))

    def test_plane_parallel_through_a_point(self):
        f = self.make(work.PLANE, mode="parallel_point", base=self.bottom, point=self.v_top)
        self.assertAlmostEqual(f.Placement.Base.z, 10, places=6)

    def test_midplane(self):
        f = self.make(work.PLANE, mode="midplane", base=self.bottom, base2=self.top)
        self.assertAlmostEqual(f.Placement.Base.z, 5, places=6)

    def test_plane_at_an_angle_around_an_edge(self):
        f = self.make(work.PLANE, mode="angle", base=self.top, edge=self.top_edge, angle="90 °")
        n = self.normal(f)
        self.assertAlmostEqual(abs(n.z), 0, places=6)   # turned 90° around the edge: vertical now
        self.assertAlmostEqual(abs(n.y), 1, places=6)

    def test_plane_normal_to_an_edge_at_a_point(self):
        f = self.make(work.PLANE, mode="normal_edge", edge=self.vertical, point=self.v_top)
        self.assertAlmostEqual(abs(self.normal(f).z), 1, places=6)

    def test_plane_tangent_to_a_cylinder(self):
        pt = self._vertex(lambda v: abs(v.Point.z - 10) < 1e-6 and abs(v.Point.x - 33) < 1e-6)
        f = self.make(work.PLANE, mode="tangent", face=self.cylface, point=pt)
        self.assertAlmostEqual(abs(self.normal(f).x), 1, places=6)

    def test_axis_from_two_planes(self):
        f = self.make(work.AXIS, mode="intersection", base=self.top, base2=self.side)
        self.assertAlmostEqual(abs(f.Placement.Rotation.multVec(App.Vector(0, 0, 1)).y), 1, places=6)

    def test_axis_normal_to_a_plane_through_a_point(self):
        f = self.make(work.AXIS, mode="normal_plane", base=self.top, point=self.v_top)
        self.assertAlmostEqual(abs(f.Placement.Rotation.multVec(App.Vector(0, 0, 1)).z), 1, places=6)

    def test_axis_of_a_cylinder(self):
        f = self.make(work.AXIS, mode="cylinder", face=self.cylface)
        self.assertAlmostEqual(f.Placement.Base.x, 30, places=6)
        self.assertAlmostEqual(f.Placement.Base.y, 5, places=6)

    def test_axis_parallel_to_an_edge_through_a_point(self):
        pt = self._vertex(lambda v: abs(v.Point.z - 10) < 1e-6 and abs(v.Point.x - 20) < 1e-6 and v.Point.y > 9)
        f = self.make(work.AXIS, mode="parallel_point", edge=self.top_edge, point=pt)
        d = f.Placement.Rotation.multVec(App.Vector(0, 0, 1))
        self.assertAlmostEqual(abs(d.x), 1, places=6)
        self.assertAlmostEqual(f.Placement.Base.y, 10, places=6)

    def test_points(self):
        c = self.make(work.POINT, mode="center", edge=self.circle)
        self.assertAlmostEqual((c.Placement.Base - App.Vector(30, 5, 10)).Length, 0, places=6)
        m = self.make(work.POINT, mode="midpoint", edge=self.top_edge)
        self.assertAlmostEqual((m.Placement.Base - App.Vector(10, 0, 10)).Length, 0, places=6)
        x = self.make(work.POINT, mode="edge_plane", edge=self.vertical, base=util.xy_plane(self.body).Name)
        self.assertAlmostEqual(x.Placement.Base.z, 0, places=6)


class RoundFaceAxisTest(unittest.TestCase):
    """The user: Axis of a cylinder on a partial cylinder (a half ring) or a cone came out across the part — it was the
    face's axis of inertia, not the surface's own axis."""

    def setUp(self):
        self.doc = util.new_doc("Ra")
        self.body, self.pad = util.padded_part(self.doc, 10, incad=True)

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def solid(self, type_id, **props):
        o = self.body.newObject(type_id, "Round")
        for k, v in props.items():
            setattr(o, k, v)
        o.Placement = App.Placement(App.Vector(40, 7, 0), App.Rotation(App.Vector(1, 0, 0), -90))  # axis along +Y
        self.body.Tip = o
        self.doc.recompute()
        return o

    def axis_of(self, o, surface):
        face = [i + 1 for i, f in enumerate(o.Shape.Faces) if f.Surface.TypeId == surface][0]
        k = work.AXIS
        f = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None), mode="cylinder",
                                                       face="%s:Face%d" % (o.Name, face)))
        self.doc.recompute()
        self.assertNotIn("Invalid", f.State, f.getStatusString())
        d = f.Placement.Rotation.multVec(App.Vector(0, 0, 1))
        self.assertAlmostEqual(abs(d.y), 1, places=6, msg="along the round face's axis: %s" % d)
        p = f.Placement.Base
        self.assertAlmostEqual(math.hypot(p.x - 40, p.z), 0, places=6, msg="through its centre: %s" % p)
        return f

    def test_a_half_cylinder(self):
        o = self.solid("PartDesign::AdditiveCylinder", Radius=12, Height=8, Angle=180)
        f = self.axis_of(o, "Part::GeomCylinder")
        self.assertTrue(f.AttachmentSupport[0][1][0].startswith("Edge"), "follows the part: on a round edge")
        o.Placement = App.Placement(App.Vector(50, 7, 3), o.Placement.Rotation)
        self.doc.recompute()
        self.assertAlmostEqual((f.Placement.Base - App.Vector(50, f.Placement.Base.y, 3)).Length, 0, places=6)

    def test_a_cone(self):
        self.axis_of(self.solid("PartDesign::AdditiveCone", Radius1=28, Radius2=23, Height=27), "Part::GeomCone")

    def test_a_flat_face_is_refused(self):
        k = work.AXIS
        top = [i + 1 for i, f in enumerate(self.pad.Shape.Faces) if f.Surface.TypeId == "Part::GeomPlane"][0]
        with self.assertRaises(ValueError) as ctx:
            k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None), mode="cylinder",
                                                    face="%s:Face%d" % (self.pad.Name, top)))
        self.assertIn("round", str(ctx.exception))

    def test_an_axis_through_two_marked_points(self):
        """Work Axis ▸ Two points on the part's markers: a corner stays a vertex (followed), an edge middle is '@x y z'."""
        k = work.AXIS
        corner = [i + 1 for i, v in enumerate(self.pad.Shape.Vertexes) if v.Point.Length < 1e-6][0]
        text = "%s:Vertex%d,@0 0 10" % (self.pad.Name, corner)
        f = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None), mode="two_points",
                                                     points=text))
        self.doc.recompute()
        self.assertNotIn("Invalid", f.State, f.getStatusString())
        d = f.Placement.Rotation.multVec(App.Vector(0, 0, 1))
        self.assertAlmostEqual(abs(d.z), 1, places=6)
        self.assertAlmostEqual(f.Placement.Base.Length, 0, places=6)
        self.assertEqual(k.read(self.doc, f)["points"], text)
        with self.assertRaises(ValueError):
            k.update(self.doc, f, dict(k.read(self.doc, f), points="@1 1 1,@1 1 1"))

    def test_marked_points_that_are_no_corners(self):
        """Every Point field takes the part's marked points; one that is no corner ('@x y z', global) fixes the
        feature where it is now (an edge middle of the 20 x 10 x 10 box: 10 0 10)."""
        mid = "@10 0 10"
        k = work.POINT
        f = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None), mode="vertex", vertex=mid))
        self.doc.recompute()
        self.assertAlmostEqual((f.Placement.Base - App.Vector(10, 0, 10)).Length, 0, places=6)
        edge = [i + 1 for i, e in enumerate(self.pad.Shape.Edges)
                if e.Curve.TypeId == "Part::GeomLine" and e.BoundBox.ZLength > 9][0]
        a = work.AXIS
        g = a.create(self.doc, self.body, None, dict(a.defaults(self.doc, self.body, None), mode="parallel_point",
                                                     edge="%s:Edge%d" % (self.pad.Name, edge), point=mid))
        self.doc.recompute()
        self.assertAlmostEqual(abs(g.Placement.Rotation.multVec(App.Vector(0, 0, 1)).z), 1, places=6)
        self.assertAlmostEqual(math.hypot(g.Placement.Base.x - 10, g.Placement.Base.y), 0, places=6)
        top = [i + 1 for i, fc in enumerate(self.pad.Shape.Faces)
               if fc.Surface.TypeId == "Part::GeomPlane" and abs(fc.CenterOfMass.z - 10) < 1e-6][0]
        h = a.create(self.doc, self.body, None, dict(a.defaults(self.doc, self.body, None), mode="normal_plane",
                                                     base="%s:Face%d" % (self.pad.Name, top), point=mid))
        self.doc.recompute()
        self.assertAlmostEqual(abs(h.Placement.Rotation.multVec(App.Vector(0, 0, 1)).z), 1, places=6)
        self.assertAlmostEqual(math.hypot(h.Placement.Base.x - 10, h.Placement.Base.y), 0, places=6)
        xy = [o for o in self.body.Origin.OriginFeatures if o.Role == "XY_Plane"][0]
        k = work.PLANE
        q = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None), mode="parallel_point",
                                                     base=xy.Name, point=mid))
        self.doc.recompute()
        self.assertAlmostEqual(q.Placement.Base.z, 10, places=6)

    def test_a_work_feature_recomputes_only_itself(self):
        """The user: Work Axis lagged — every pick recomputed the whole part (a touched Emboss: 9.6 s, not 0.1 s)."""
        self.pad.touch()
        k = work.AXIS
        corner = [i + 1 for i, v in enumerate(self.pad.Shape.Vertexes) if v.Point.Length < 1e-6][0]
        f = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None), mode="two_points",
                                                     points="%s:Vertex%d,@0 0 10" % (self.pad.Name, corner)))
        self.assertNotIn("Invalid", f.State)
        self.assertIn("Touched", self.pad.State, "the part waits for OK")

