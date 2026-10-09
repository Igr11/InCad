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


class RectangularTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Sr")
        self.body = document.make_part(self.doc)
        self.sk = self.body.newObject("Sketcher::SketchObject", "Sketch")
        self.sk.AttachmentSupport = [(util.xy_plane(self.body), "")]
        self.sk.MapMode = "FlatFace"
        self.doc.recompute()

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def _rect(self, originals, count=3, spacing="12 mm", angle=0.0, flip=False, **more):
        name = sp.next_name(self.sk)
        rec = {"name": name, "kind": "rect", "originals": [sp.ensure_id(self.sk, g) for g in originals],
               "count": count, "spacing_param": model.new_feature_parameter(self.doc, spacing, "length"),
               "angle": angle, "flip": flip}
        rec.update(more)
        rec = sp.build_rect(self.doc, self.sk, rec)
        self.doc.recompute()
        return rec

    def _xy(self, geo, pos):
        p = sp.point_of(self.sk, geo, pos)
        return round(p.x, 3), round(p.y, 3)

    def test_a_circle_is_copied_along_x_with_equal_radius_and_hidden_ties(self):
        c = circle(self.sk, 2, 3, 1)
        self.sk.addConstraint(Sketcher.Constraint("DistanceX", -1, 1, c, 3, 2.0))  # pin the original
        self.sk.addConstraint(Sketcher.Constraint("DistanceY", -1, 1, c, 3, 3.0))
        self.sk.addConstraint(Sketcher.Constraint("Radius", c, 1.0))
        rec = self._rect([c])
        self.assertEqual(len(rec["copies"]), 2)  # count 3 = the original + 2 copies
        k1, k2 = (sp.index_of(self.sk, ids[0]) for ids in rec["copies"])
        self.assertEqual(self._xy(k1, 3), (14.0, 3.0))
        self.assertEqual(self._xy(k2, 3), (26.0, 3.0))
        self.assertAlmostEqual(self.sk.Geometry[k2].Radius, 1.0)
        self.assertEqual(self.sk.solve(), 0)
        names = [c.Name for c in self.sk.Constraints if sketch.is_pattern_name(c.Name)]
        self.assertEqual(sorted(names), sorted(rec["constraints"]))
        self.assertTrue(all(self.sk.getVirtualSpace(i) for i, c in enumerate(self.sk.Constraints)
                            if sketch.is_pattern_name(c.Name)))
        self.assertEqual([n for n, _, _ in sketch.dimensions(self.doc)], [])  # none of ours is a dimension

    def test_copies_follow_the_original_and_the_spacing_parameter(self):
        c = circle(self.sk, 2, 3, 1)
        dx = self.sk.addConstraint(Sketcher.Constraint("DistanceX", -1, 1, c, 3, 2.0))
        self.sk.addConstraint(Sketcher.Constraint("DistanceY", -1, 1, c, 3, 3.0))
        rec = self._rect([c], count=2, spacing="10 mm", angle=90.0)
        k1 = sp.index_of(self.sk, rec["copies"][0][0])
        self.assertEqual(self._xy(k1, 3), (2.0, 13.0))
        self.sk.setDatum(dx, App.Units.Quantity("7 mm"))
        self.doc.recompute()
        self.assertEqual(self._xy(k1, 3), (7.0, 13.0))
        model.set_model_parameter(self.doc, rec["spacing_param"], "25 mm")
        self.doc.recompute()
        self.assertEqual(self._xy(k1, 3), (7.0, 28.0))

    def test_flip_and_two_directions(self):
        c = circle(self.sk, 0, 0, 1)
        self.sk.addConstraint(Sketcher.Constraint("Coincident", c, 3, -1, 1))
        rec = self._rect([c], count=2, spacing="10 mm", angle=0.0, flip=True, count2=2,
                         spacing_param2=model.new_feature_parameter(self.doc, "5 mm", "length"), angle2=90.0)
        got = sorted(self._xy(sp.index_of(self.sk, ids[0]), 3) for ids in rec["copies"])
        self.assertEqual(got, [(-10.0, 0.0), (-10.0, 5.0), (0.0, 5.0)])

    def test_a_line_an_arc_and_a_construction_line_keep_their_kind_and_shape(self):
        ln = line(self.sk, 0, 0, 4, 0)
        arc = self.sk.addGeometry(Part.ArcOfCircle(Part.Circle(App.Vector(6, 0, 0), App.Vector(0, 0, 1), 2),
                                                   0.0, math.pi / 2))
        con = line(self.sk, 0, 5, 1, 5, construction=True)
        self.sk.addConstraint(Sketcher.Constraint("Coincident", ln, 1, -1, 1))
        self.sk.addConstraint(Sketcher.Constraint("PointOnObject", ln, 2, -1))
        for g, pos, x, y in ((arc, 3, 6.0, 0.0), (con, 1, 0.0, 5.0)):  # pin the originals: the copies' places
            self.sk.addConstraint(Sketcher.Constraint("DistanceX", -1, 1, g, pos, x))  # below are absolute
            self.sk.addConstraint(Sketcher.Constraint("DistanceY", -1, 1, g, pos, y))
        rec = self._rect([ln, arc, con], count=2, spacing="20 mm", angle=30.0)
        dx, dy = 20 * math.cos(math.radians(30)), 20 * math.sin(math.radians(30))
        l2, a2, c2 = (sp.index_of(self.sk, g) for g in rec["copies"][0])
        self.assertEqual(self._xy(l2, 2), (round(4 + dx, 3), round(dy, 3)))
        self.assertEqual(self.sk.Geometry[a2].TypeId, "Part::GeomArcOfCircle")
        self.assertAlmostEqual(self.sk.Geometry[a2].Radius, 2.0, places=6)
        self.assertEqual(self._xy(a2, 1), (round(8 + dx, 3), round(dy, 3)))
        self.assertTrue(self.sk.getConstruction(c2))
        self.assertEqual(self.sk.solve(), 0)

    def test_a_closed_rectangle_is_tied_once_per_corner(self):
        ids = [line(self.sk, 0, 0, 4, 0), line(self.sk, 4, 0, 4, 2), line(self.sk, 4, 2, 0, 2), line(self.sk, 0, 2, 0, 0)]
        for i in range(4):
            self.sk.addConstraint(Sketcher.Constraint("Coincident", ids[i], 2, ids[(i + 1) % 4], 1))
        self.sk.addConstraint(Sketcher.Constraint("Coincident", ids[0], 1, -1, 1))
        self.sk.addConstraint(Sketcher.Constraint("Horizontal", ids[0]))
        self.doc.recompute()
        before = self.sk.solve()
        rec = self._rect(ids, count=2, spacing="10 mm")
        self.assertEqual(self.sk.solve(), before)  # not over-constrained: 8 ties for 4 corners, not 16
        copy = [sp.index_of(self.sk, g) for g in rec["copies"][0]]
        self.assertEqual(self._xy(copy[2], 1), (14.0, 2.0))

    def test_remove_takes_copies_and_constraints_and_leaves_the_original(self):
        c = circle(self.sk, 2, 3, 1)
        rec = self._rect([c], count=4)
        n_geo, n_con = self.sk.GeometryCount, len(self.sk.Constraints)
        self.assertEqual(n_geo, 4)
        sp.remove(self.doc, self.sk, rec["name"])
        self.doc.recompute()
        self.assertEqual(self.sk.GeometryCount, 1)
        self.assertEqual([c.Name for c in self.sk.Constraints if sketch.is_pattern_name(c.Name)], [])
        self.assertIsNone(sp.find(self.sk, rec["name"]))
        self.assertEqual(sp.copies_of(self.sk, rec["name"]), [])
