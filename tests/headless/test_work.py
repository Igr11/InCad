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
