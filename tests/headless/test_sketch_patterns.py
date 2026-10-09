import json
import math
import unittest

import FreeCAD as App
import Part
import Sketcher
from incad.core import document, model, sketch, sketch_patterns as sp
from headless import util


def circle(sk, x, y, r, construction=False):
    return sk.addGeometry(Part.Circle(App.Vector(x, y, 0), App.Vector(0, 0, 1), r), construction)


def line(sk, x1, y1, x2, y2, construction=False):
    return sk.addGeometry(Part.LineSegment(App.Vector(x1, y1, 0), App.Vector(x2, y2, 0)), construction)


class RecordsAndIdsTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Sp")
        self.body = document.make_part(self.doc)
        self.sk = self.body.newObject("Sketcher::SketchObject", "Sketch")
        self.sk.AttachmentSupport = [(util.xy_plane(self.body), "")]
        self.sk.MapMode = "FlatFace"
        self.doc.recompute()

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_ids_are_given_once_and_found_after_other_geometry_is_deleted(self):
        a, b = circle(self.sk, 0, 0, 1), circle(self.sk, 5, 0, 1)
        gid = sp.ensure_id(self.sk, b)
        self.assertEqual(sp.ensure_id(self.sk, b), gid)
        self.sk.delGeometry(a)
        self.assertEqual(sp.index_of(self.sk, gid), 0)
        self.assertIsNone(sp.index_of(self.sk, 999999))

    def test_records_round_trip_and_names_are_never_reused(self):
        self.assertEqual(sp.records(self.sk), [])
        n1 = sp.next_name(self.sk)
        sp.save_records(self.sk, [{"name": n1, "kind": "rect"}])
        self.assertEqual(sp.find(self.sk, n1)["kind"], "rect")
        sp.save_records(self.sk, [])
        self.assertNotEqual(sp.next_name(self.sk), n1)
        self.assertEqual(sp.next_name(self.sk), "Pattern3")
        self.assertEqual(json.loads(self.sk.InCadPatterns)["patterns"], [])

    def test_elements_map_to_geometry_and_positions(self):
        c = circle(self.sk, 2, 3, 1)
        ln = line(self.sk, 0, 0, 4, 0)
        self.doc.recompute()
        self.assertEqual(sp.element(self.sk, "Edge1"), (c, 0))
        self.assertEqual(sp.element(self.sk, "H_Axis"), (-1, 0))
        self.assertEqual(sp.element(self.sk, "V_Axis"), (-2, 0))
        self.assertEqual(sp.element(self.sk, "RootPoint"), (-1, 1))
        geo, pos = sp.element(self.sk, "Vertex1")  # the circle's centre is its first vertex: (geo, PointPos 3)
        self.assertEqual((geo, pos), (c, 3))
        self.assertEqual(sp.element(self.sk, "Vertex2"), (ln, 1))  # the line's start
        with self.assertRaises(ValueError):
            sp.element(self.sk, "Vertex99")
        self.assertEqual(sp.ref_points(self.sk, ln), [1, 2])
        self.assertEqual(sp.ref_points(self.sk, c), [3])
        p = sp.point_of(self.sk, ln, 2)
        self.assertAlmostEqual((p.x, p.y), (4.0, 0.0))
        e = self.sk.addGeometry(Part.Ellipse(App.Vector(0, 0, 0), 3, 2))
        with self.assertRaises(ValueError) as cm:
            sp.ref_points(self.sk, e)
        self.assertIn("lines, arcs, circles and points", str(cm.exception))

    def test_pattern_constraint_names_are_not_dimensions_or_symbols(self):
        c = circle(self.sk, 2, 3, 1)
        i = self.sk.addConstraint(Sketcher.Constraint("DistanceX", -1, 1, c, 3, 2.0))
        self.sk.renameConstraint(i, "pat1_0")
        j = self.sk.addConstraint(Sketcher.Constraint("Radius", c, 1.0))
        self.sk.renameConstraint(j, "d3")
        self.assertTrue(sketch.is_pattern_name("pat1_0"))
        self.assertFalse(sketch.is_pattern_name("d3"))
        self.assertFalse(sketch.is_pattern_name("pattern"))
        self.assertEqual([n for n, _, _ in sketch.dimensions(self.doc)], ["d3"])
        self.assertEqual(list(sketch.dimension_snapshot(self.sk)), ["d3"])
        k = self.sk.addConstraint(Sketcher.Constraint("Coincident", c, 3, -1, 1))
        self.sk.renameConstraint(k, "pat1_1")
        self.assertNotIn(k, sketch._symbol_constraints(self.sk))
        self.assertEqual(sketch.name_new_dimensions(self.doc), [])  # ours are named: nothing to name
