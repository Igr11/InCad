"""3D Line (the user's idea): a virtual cube of points round the origin, `step` apart, with construction lines; a
click takes a cube point, or a free place on a line (with the cube points either side); the line is made of lines,
a spline on the points, or a spline through them; Sweep takes it as its path."""
import unittest

import FreeCAD as App
import Part

from incad.core import line3d
from incad.features import common, kind_for
from incad.features import line3d as kind
from incad.features import shapes
from headless import util

V = App.Vector
PTS = "0 0 0; 0 0 20; 20 10 40; 40 0 40"


class Lattice(unittest.TestCase):
    def test_cube_round_the_origin(self):
        c = line3d.coords(100, 10)
        self.assertEqual((c[0], c[-1], len(c)), (-50, 50, 11))
        self.assertEqual(len(line3d.lattice(100, 10)), 11 ** 3)
        with self.assertRaises(ValueError):
            line3d.coords(10, 20)  # a step larger than the cube

    def test_a_point_or_a_free_place_on_a_line(self):
        down = (0, 0, -1)
        self.assertEqual(line3d.snap((10, 20, 100), down, 100, 10, 1.0), {"kind": "point", "point": (10, 20, 50)})
        hit = line3d.snap((13.3, 20, 100), down, 100, 10, 1.0)  # on the X line through y 20, z 50 (the front one)
        self.assertEqual((hit["kind"], hit["axis"], hit["ends"]), ("line", 0, (10.0, 20.0)))
        self.assertAlmostEqual(hit["point"][0], 13.3, places=9)
        self.assertIsNone(line3d.snap((13.3, 21.5, 100), down, 100, 10, 1.0))  # between the lines: nothing
        tilted = line3d.snap((10, 20, 100), (0.2, 0, -1), 100, 10, 1.0)
        self.assertEqual(tilted["point"], (20.0, 20.0, 50.0))  # the front one along the ray

    def test_a_working_layer_only(self):
        """A working layer (the user: the whole cube was hard to read): only its points and lines, at any level."""
        down = (0, 0, -1)
        self.assertEqual(line3d.snap((10, 20, 100), down, 100, 10, 1.0, (2, 20.0))["point"], (10, 20, 20))
        hit = line3d.snap((10, 20, 100), (0.2, 0, -1), 100, 10, 1.0, (2, -30.0))
        self.assertEqual((hit["kind"], round(hit["point"][2], 9)), ("line", -30))  # on that layer, nowhere else
        self.assertEqual(len(line3d.layer_points(100, 10, 2, 7.5)), 121)
        self.assertTrue(all(abs(p[2] - 7.5) < 1e-12 for p in line3d.layer_points(100, 10, 2, 7.5)))

    def test_three_kinds_of_line(self):
        pts = line3d.parse_points(PTS)
        poly = line3d.curve(pts, "polyline")
        self.assertEqual(len(poly.Edges), 3)
        spline = line3d.curve(pts, "spline")
        self.assertEqual(spline.Edges[0].Curve.TypeId, "Part::GeomBSplineCurve")
        self.assertAlmostEqual((spline.Edges[0].Curve.getPole(2) - V(0, 0, 20)).Length, 0, places=9)  # a control
        through = line3d.curve(pts, "through")
        for p in pts:  # it passes every point
            self.assertLess(through.distToShape(Part.Vertex(V(*p)))[0], 1e-7)
        self.assertIsNone(line3d.curve(pts[:1]))


class Feature(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("L3")
        from incad.core import document
        self.body = document.make_part(self.doc)

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_made_read_and_swept_along(self):
        values = dict(kind.defaults(self.doc, self.body), shape="through", points=PTS)
        f = kind.create(self.doc, self.body, None, values)
        self.doc.recompute()
        self.assertIs(f.getParentGeoFeatureGroup(), self.body)
        self.assertIs(kind_for(f), kind)
        self.assertEqual(kind.read(self.doc, f)["shape"], "through")
        self.assertEqual(len(line3d.parse_points(kind.read(self.doc, f)["points"])), 4)
        self.assertTrue(common.accepts("path", f, ""))
        self.assertFalse(common.accepts("sketch", f, ""))  # a profile or a Loft section is a sketch
        sk = self.body.newObject("Sketcher::SketchObject", "Ring")
        sk.AttachmentSupport = [(util.xy_plane(self.body), "")]
        sk.MapMode = "FlatFace"
        sk.addGeometry(Part.Circle(V(0, 0, 0), V(0, 0, 1), 2))
        self.doc.recompute()
        k = shapes.SWEEP
        sweep = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body), profile=sk.Name,
                                                         path=f.Name))
        self.doc.recompute()
        self.assertNotIn("Invalid", sweep.State, sweep.getStatusString())
        self.assertGreater(sweep.Shape.Volume, 500)
        kind.update(self.doc, f, dict(kind.read(self.doc, f), points=PTS + "; 60 0 30"))
        self.doc.recompute()
        self.assertNotIn("Invalid", sweep.State, sweep.getStatusString())
        self.assertGreater(sweep.Shape.BoundBox.XMax, 55)  # the sweep follows the longer line

    def test_waits_for_two_points(self):
        self.assertTrue(kind.pending({"points": ""}))
        self.assertTrue(kind.pending({"points": "0 0 0"}))
        self.assertFalse(kind.pending({"points": "0 0 0; 10 0 0"}))
