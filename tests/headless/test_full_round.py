"""Full round fillet (incad.core.full_round): the end of a bar or a plate's side becomes a half cylinder meeting its
two sides tangentially; the narrower pair of sides is the one rounded across; a face without parallel sides is
refused."""
import math
import unittest

import FreeCAD as App
import Part

from incad.core import full_round

V = App.Vector


def face_with(shape, normal):
    return next(f for f in shape.Faces if f.normalAt(0, 0).isEqual(normal, 1e-9))


class FullRound(unittest.TestCase):
    def test_end_of_a_plate_rounds_across_its_thickness(self):
        plate = Part.makeBox(40, 20, 6)  # the end at x = 40: its sides z = 0 / 6 (6 apart) and y = 0 / 20
        end = face_with(plate, V(1, 0, 0))
        result = full_round.apply(plate, end)
        self.assertTrue(result.isValid())
        # two quarter corners of a 3 x 3 square minus a quarter disk each, all along the 20 mm end
        cut = 2 * (3 * 3 - math.pi * 9 / 4) * 20
        self.assertAlmostEqual(plate.Volume - result.Volume, cut, places=4)
        cyl = [f for f in result.Faces if f.Surface.TypeId == "Part::GeomCylinder"]
        self.assertEqual(len(cyl), 1)
        self.assertAlmostEqual(cyl[0].Surface.Radius, 3, places=6)
        self.assertAlmostEqual(result.BoundBox.XMax, 40, places=6)  # the round's tip stays at the end
        self.assertEqual(len([f for f in result.Faces if f.Surface.TypeId == "Part::GeomPlane"
                              and f.normalAt(0, 0).isEqual(V(1, 0, 0), 1e-9)]), 0)  # the flat end is gone

    def test_the_top_of_a_wall_on_a_base(self):
        part = Part.makeBox(30, 30, 4).fuse(Part.makeBox(30, 5, 20, V(0, 10, 0))).removeSplitter()
        top = next(f for f in part.Faces if f.normalAt(0, 0).isEqual(V(0, 0, 1), 1e-9) and f.CenterOfMass.z > 19)
        result = full_round.apply(part, top)
        self.assertTrue(result.isValid())
        self.assertAlmostEqual(result.BoundBox.ZMax, 20, places=6)
        cyl = [f for f in result.Faces if f.Surface.TypeId == "Part::GeomCylinder"]
        self.assertEqual(len(cyl), 1)
        self.assertAlmostEqual(cyl[0].Surface.Radius, 2.5, places=6)

    def test_a_round_face_is_refused(self):
        rod = Part.makeCylinder(5, 20)
        side = next(f for f in rod.Faces if f.Surface.TypeId == "Part::GeomCylinder")
        with self.assertRaises(ValueError):
            full_round.apply(rod, side)

    def test_a_triangle_without_parallel_sides_is_refused(self):
        prism = Part.Face(Part.makePolygon([V(0, 0, 0), V(20, 0, 0), V(5, 12, 0), V(0, 0, 0)])).extrude(V(0, 0, 8))
        top = face_with(prism, V(0, 0, 1))
        with self.assertRaises(ValueError):
            full_round.apply(prism, top)


def edges_along(shape, axis, at):
    """The straight edges of `shape` running along `axis` whose middle is `at` (a predicate on the point)."""
    out = []
    for e in shape.Edges:
        d = e.Vertexes[-1].Point - e.Vertexes[0].Point
        if len(e.Vertexes) > 1 and abs(abs(d.normalize().dot(axis)) - 1) < 1e-9 and at(e.CenterOfMass):
            out.append(e)
    return out


class PickedByEdges(unittest.TestCase):
    """The user: a full round is picked by its two edges (the face between them and the way across are theirs)."""

    def test_the_two_edges_of_a_plate_end(self):
        plate = Part.makeBox(40, 20, 6)
        e1, e2 = sorted(edges_along(plate, V(0, 1, 0), lambda p: abs(p.x - 40) < 1e-9), key=lambda e: e.CenterOfMass.z)
        face, across = full_round.between(plate, e1, e2)
        self.assertTrue(face.normalAt(0, 0).isEqual(V(1, 0, 0), 1e-9))
        self.assertAlmostEqual(abs(across.z), 1, places=9)
        result = full_round.apply(plate, face, across)
        cyl = [f for f in result.Faces if f.Surface.TypeId == "Part::GeomCylinder"]
        self.assertEqual(len(cyl), 1)
        self.assertAlmostEqual(cyl[0].Surface.Radius, 3, places=6)

    def test_across_the_wide_way_when_those_edges_are_picked(self):
        plate = Part.makeBox(40, 20, 6)
        e1, e2 = sorted(edges_along(plate, V(0, 0, 1), lambda p: abs(p.x - 40) < 1e-9), key=lambda e: e.CenterOfMass.y)
        face, across = full_round.between(plate, e1, e2)
        result = full_round.apply(plate, face, across)  # rounded across its 20 mm width, not the 6 mm thickness
        cyl = [f for f in result.Faces if f.Surface.TypeId == "Part::GeomCylinder"]
        self.assertAlmostEqual(cyl[0].Surface.Radius, 10, places=6)

    def test_edges_of_different_faces_or_not_parallel_are_refused(self):
        plate = Part.makeBox(40, 20, 6)
        end = edges_along(plate, V(0, 1, 0), lambda p: abs(p.x - 40) < 1e-9 and p.z < 1e-9)[0]
        start = edges_along(plate, V(0, 1, 0), lambda p: abs(p.x) < 1e-9 and p.z > 5)[0]  # far corners: no face
        with self.assertRaises(ValueError):
            full_round.between(plate, end, start)  # no face between them
        up = edges_along(plate, V(0, 0, 1), lambda p: abs(p.x - 40) < 1e-9)[0]
        with self.assertRaises(ValueError):
            full_round.between(plate, end, up)  # not parallel
