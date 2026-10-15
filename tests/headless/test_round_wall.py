"""Round walls for Move Face (incad.core.round_wall): which faces, their pieces, the section and the material side."""
import math
import unittest

import FreeCAD as App
import Part

from incad.core import round_wall as rw

V = App.Vector
UP = V(0, 0, 1)


def boss():
    """A 40 x 30 x 5 block with a cylinder boss r 5, 10 high, on top at (20, 15)."""
    return Part.makeBox(40, 30, 5).fuse(Part.makeCylinder(5, 10, V(20, 15, 5))).removeSplitter()


def holed():
    """A 40 x 30 x 10 block with a through hole r 5 at (20, 15)."""
    return Part.makeBox(40, 30, 10).cut(Part.makeCylinder(5, 10, V(20, 15, 0)))


def ellipse_pad(h=10):
    """The user's band shape: a 3-point ellipse (20 x 10) extruded h; its wall is a SurfaceOfExtrusion."""
    ring = Part.Ellipse(V(20, 0, 0), V(0, 10, 0), V(0, 0, 0)).toShape()
    return Part.Face(Part.Wire(ring)).extrude(V(0, 0, h))


def wall_of(shape, kind):
    return next(f for f in shape.Faces if type(f.Surface).__name__ == kind)


class Detection(unittest.TestCase):
    def test_cylinder_and_extruded_ellipse_are_round_walls(self):
        self.assertTrue(rw.is_round_wall(wall_of(boss(), "Cylinder")))
        self.assertTrue(rw.is_round_wall(wall_of(ellipse_pad(), "SurfaceOfExtrusion")))
        self.assertTrue(abs(abs(rw.direction(wall_of(ellipse_pad(), "SurfaceOfExtrusion")).dot(UP)) - 1) < 1e-9)

    def test_flat_faces_cones_and_spheres_are_not(self):
        self.assertFalse(rw.is_round_wall(next(f for f in boss().Faces if rw.mf._is_plane(f))))
        self.assertFalse(rw.is_round_wall(Part.makeCone(5, 2, 10).Faces[0]))
        self.assertFalse(rw.is_round_wall(Part.makeSphere(5).Faces[0]))


class Pieces(unittest.TestCase):
    def test_a_one_face_cylinder_is_its_own_wall(self):
        shape = boss()
        faces, a = rw.pieces(shape, wall_of(shape, "Cylinder"))
        self.assertEqual(len(faces), 1)

    def test_a_wall_split_in_two_halves_is_taken_whole(self):
        """Review focus 1: a seam-split ring (two half-cylinders) — one click takes both halves."""
        half = Part.makeCylinder(5, 10, V(0, 0, 0), UP, 180)
        other = Part.makeCylinder(5, 10, V(0, 0, 0), UP, 180).rotated(V(0, 0, 0), UP, 180)
        shape = half.fuse(other)  # no removeSplitter: two cylinder faces stay
        cyl = [f for f in shape.Faces if type(f.Surface).__name__ == "Cylinder"]
        self.assertEqual(len(cyl), 2)
        faces, _ = rw.pieces(shape, cyl[0])
        self.assertEqual(len(faces), 2)


class Section(unittest.TestCase):
    def test_section_of_the_boss_is_its_circle_at_mid_height(self):
        shape = boss()
        faces, a = rw.pieces(shape, wall_of(shape, "Cylinder"))
        h0, h1 = rw.extent(faces, a)
        self.assertAlmostEqual(h0, 5, 6)
        self.assertAlmostEqual(h1, 15, 6)
        wire = rw.section(faces, a, h0, h1)
        self.assertTrue(wire.isClosed())
        self.assertAlmostEqual(wire.Length, 2 * math.pi * 5, 4)
        self.assertAlmostEqual(wire.BoundBox.ZMin, 10, 6)

    def test_material_side_boss_inside_hole_outside(self):
        """Review focus 2: + grows a boss and shrinks a hole — the side comes from the face normal."""
        for shape, inside in ((boss(), True), (holed(), False)):
            faces, a = rw.pieces(shape, wall_of(shape, "Cylinder"))
            wire = rw.section(faces, a, *rw.extent(faces, a))
            self.assertEqual(rw.material_inside(faces, wire, a), inside)

    def test_a_wall_in_two_stacked_pieces_has_one_ring(self):
        """The user's band: one ellipse surface in two faces one above the other (split by earlier Move Faces): the
        section is the ring at mid height only — a piece that does not reach that height adds nothing."""
        low = ellipse_pad(2)
        high = ellipse_pad(6).translated(V(0, 0, 2))
        shape = low.fuse(high)  # no removeSplitter: the wall stays in two faces, z 0..2 and 2..8
        walls = [f for f in shape.Faces if type(f.Surface).__name__ == "SurfaceOfExtrusion"]
        self.assertEqual(len(walls), 2)
        faces, a = rw.pieces(shape, walls[0])
        self.assertEqual(len(faces), 2)
        wire = rw.section(faces, a, *rw.extent(faces, a))
        self.assertEqual(len(wire.Edges), 1)
        self.assertAlmostEqual(Part.Face(wire).Area, math.pi * 20 * 10, 6)  # (a wire's Length of an ellipse is off)
        moved = rw.offset(shape, [walls[0]], 1.0, "step")
        self.assertTrue(moved.isValid())

    def test_an_open_wall_is_refused(self):
        """A rounded end between flat faces (half a cylinder on a box): not a ring."""
        shape = Part.makeBox(10, 10, 10).fuse(Part.makeCylinder(5, 10, V(10, 5, 0), UP, 180)
                                              .rotated(V(10, 5, 0), UP, -90)).removeSplitter()
        face = wall_of(shape, "Cylinder")
        faces, a = rw.pieces(shape, face)
        with self.assertRaises(ValueError) as e:
            rw.section(faces, a, *rw.extent(faces, a))
        self.assertEqual(str(e.exception), rw.OPEN_MSG)


def ring_area(r_out, r_in):
    return math.pi * (r_out ** 2 - r_in ** 2)


class StepAndInventor(unittest.TestCase):
    def test_boss_grows_and_shrinks_exactly(self):
        for mode in ("step", "inventor"):
            for d in (1.0, -1.0):
                shape = boss()
                moved = rw.offset(shape, [wall_of(shape, "Cylinder")], d, mode)
                self.assertTrue(moved.isValid(), (mode, d))
                self.assertAlmostEqual(moved.Volume - shape.Volume, math.copysign(ring_area(5 + max(d, 0), 5 + min(d, 0)), d) * 10, 3)
                cyl = wall_of(moved, "Cylinder")
                self.assertAlmostEqual(cyl.Surface.Radius, 5 + d, 6, (mode, d))

    def test_plus_makes_a_hole_smaller(self):
        shape = holed()
        moved = rw.offset(shape, [wall_of(shape, "Cylinder")], 1.0, "step")
        self.assertAlmostEqual(wall_of(moved, "Cylinder").Surface.Radius, 4, 6)
        self.assertAlmostEqual(moved.Volume - shape.Volume, ring_area(5, 4) * 10, 3)
        bigger = rw.offset(shape, [wall_of(shape, "Cylinder")], -1.0, "step")
        self.assertAlmostEqual(wall_of(bigger, "Cylinder").Surface.Radius, 6, 6)

    def test_ellipse_band_offset_by_the_exact_outline(self):
        shape = ellipse_pad()
        wall = wall_of(shape, "SurfaceOfExtrusion")
        base = Part.Face(Part.Wire(Part.Ellipse(V(20, 0, 0), V(0, 10, 0), V(0, 0, 0)).toShape()))
        for d in (1.0, -1.0):
            moved = rw.offset(shape, [wall], d, "step")
            grown = Part.Face(base.OuterWire.makeOffset2D(d))
            self.assertTrue(moved.isValid())
            self.assertAlmostEqual(moved.Volume - shape.Volume, (grown.Area - base.Area) * 10, 2)

    def test_inventor_reaches_a_slanted_top(self):
        """Review focus 4: a cylinder cut by a slanted plane at the top — the slab reaches that plane."""
        cyl = Part.makeCylinder(5, 20)
        cutter = Part.makeBox(40, 40, 40, V(-20, -20, 10)).rotated(V(0, 0, 10), V(1, 0, 0), 20)
        shape = cyl.cut(cutter)
        moved = rw.offset(shape, [wall_of(shape, "Cylinder")], 1.0, "inventor")
        self.assertTrue(moved.isValid())
        top = next(f for f in moved.Faces if rw.mf._is_plane(f) and f.normalAt(0, 0).z > 0.5)
        self.assertEqual(len(moved.Solids), 1)
        for v in moved.Vertexes:  # nothing sticks out above the slanted top plane
            self.assertLess((v.Point - top.CenterOfMass).dot(top.normalAt(0, 0)), 1e-6)

    def test_inventor_refuses_a_fillet_next_to_the_wall(self):
        shape = ellipse_pad()
        top_ring = next(e for e in shape.Edges if abs(e.CenterOfMass.z - 10) < 1e-9)
        shape = shape.makeFillet(2, [top_ring])
        with self.assertRaises(ValueError) as e:
            rw.offset(shape, [wall_of(shape, "SurfaceOfExtrusion")], 1.0, "inventor")
        self.assertEqual(str(e.exception), rw.mf.ROUND_MSG)

    def test_step_leaves_ledges_next_to_a_fillet(self):
        shape = ellipse_pad()
        top_ring = next(e for e in shape.Edges if abs(e.CenterOfMass.z - 10) < 1e-9)
        shape = shape.makeFillet(2, [top_ring])
        moved = rw.offset(shape, [wall_of(shape, "SurfaceOfExtrusion")], 1.0, "step")
        self.assertTrue(moved.isValid())
        self.assertGreater(moved.Volume, shape.Volume)

    def test_too_large_inward_is_refused_cleanly(self):
        """Review focus 3: more than the radius — a clean refusal."""
        shape = boss()
        with self.assertRaises(ValueError) as e:
            rw.offset(shape, [wall_of(shape, "Cylinder")], -6.0, "step")
        self.assertEqual(str(e.exception), rw.mf.TOO_LARGE_MSG)
        shape = ellipse_pad()
        with self.assertRaises(ValueError) as e:
            rw.offset(shape, [wall_of(shape, "SurfaceOfExtrusion")], -11.0, "step")
        self.assertEqual(str(e.exception), rw.mf.TOO_LARGE_MSG)

    def test_two_walls_picked_both_grow(self):
        shape = Part.makeBox(40, 20, 5).fuse([Part.makeCylinder(3, 6, V(10, 10, 5)),
                                              Part.makeCylinder(3, 6, V(30, 10, 5))]).removeSplitter()
        walls = [f for f in shape.Faces if type(f.Surface).__name__ == "Cylinder"]
        moved = rw.offset(shape, walls, 1.0, "inventor")
        self.assertTrue(moved.isValid())
        radii = sorted(round(f.Surface.Radius, 6) for f in moved.Faces if type(f.Surface).__name__ == "Cylinder")
        self.assertEqual(radii, [4.0, 4.0])
        self.assertAlmostEqual(moved.Volume - shape.Volume, 2 * ring_area(4, 3) * 6, 3)

    def test_zero_changes_nothing(self):
        shape = boss()
        self.assertIs(rw.offset(shape, [wall_of(shape, "Cylinder")], 0.0, "step"), shape)

def user_like():
    """The user's kind of part: the ellipse pad, its top ring filleted 2, its bottom ring chamfered 1."""
    shape = ellipse_pad()
    top_ring = next(e for e in shape.Edges if abs(e.CenterOfMass.z - 10) < 1e-9)
    shape = shape.makeFillet(2, [top_ring])
    bottom_ring = next(e for e in shape.Edges if "Ellipse" in type(e.Curve).__name__ and abs(e.CenterOfMass.z) < 1e-9)
    return shape.makeChamfer(1, [bottom_ring])


class Together(unittest.TestCase):
    def test_the_band_and_its_blends_move_exactly_d(self):
        shape = user_like()
        wall = wall_of(shape, "SurfaceOfExtrusion")
        for d in (1.0,):  # inward next to blends is refused (Final ruling: re-blending comes later)
            moved = rw.offset(shape, [wall], d, "together")
            self.assertTrue(moved.isValid(), d)
            new_wall = next(f for f in moved.Faces if type(f.Surface).__name__ != "Plane"
                            and rw.direction(f) is not None and abs(f.CenterOfMass.z - 5) < 3)
            for e in wall.Edges:  # every sampled point of the old wall is d from the new one
                for p in e.discretize(8):
                    if 2.5 < p.z < 7.5:
                        self.assertAlmostEqual(new_wall.distToShape(Part.Vertex(p))[0], abs(d), 3)
            box = moved.optimalBoundingBox()  # BoundBox is loose around B-spline faces
            self.assertAlmostEqual(box.ZMax, 10, 6)  # the top stays where it was
            self.assertAlmostEqual(box.ZMin, 0, 6)
            flats = sorted(round(f.CenterOfMass.z, 6) for f in moved.Faces if type(f.Surface).__name__ == "Plane")
            self.assertEqual(flats, [0.0, 10.0], d)  # no step cut into the top or bottom near the band

    def test_another_wall_inside_the_band_height_stays(self):
        """Review focus 5: an inner hole through the part is left exactly as it was."""
        shape = user_like().cut(Part.makeCylinder(3, 10))
        hole = wall_of(shape, "Cylinder")
        moved = rw.offset(shape, [wall_of(shape, "SurfaceOfExtrusion")], 1.0, "together")
        self.assertTrue(moved.isValid())
        self.assertAlmostEqual(wall_of(moved, "Cylinder").Surface.Radius, hole.Surface.Radius, 9)

    def test_the_moved_band_can_be_moved_again(self):
        """After Together the band is an offset surface: still a round wall, picked and moved again."""
        shape = user_like()
        once = rw.offset(shape, [wall_of(shape, "SurfaceOfExtrusion")], 1.0, "together")
        band = max((f for f in once.Faces if rw.is_round_wall(f)), key=lambda f: f.Area)
        twice = rw.offset(once, [band], 1.0, "step")
        self.assertTrue(twice.isValid())
        self.assertGreater(twice.Volume, once.Volume)

    def test_a_feature_beyond_the_flat_top_stays(self):
        """A cone standing on the top face (beyond the fillet's flat neighbour) is no blend of the band: it stays."""
        shape = user_like().fuse(Part.makeCone(4, 1, 5, V(0, 0, 10))).removeSplitter()
        cone = wall_of(shape, "Cone")
        moved = rw.offset(shape, [wall_of(shape, "SurfaceOfExtrusion")], 1.0, "together")
        self.assertTrue(moved.isValid())
        kept = wall_of(moved, "Cone")
        self.assertAlmostEqual(kept.Area, cone.Area, 6)
        self.assertAlmostEqual((kept.CenterOfMass - cone.CenterOfMass).Length, 0, 6)


class ReviewFindings(unittest.TestCase):
    """The final review's findings, each pinned (RED before the fix)."""

    def test_find_takes_the_picked_segment_not_another_on_the_same_surface(self):
        """Critical 1: a shaft r5 with a circlip groove: the lower segment is found, never the upper one."""
        shaft = Part.makeCylinder(5, 30).cut(Part.makeCylinder(10, 2, V(0, 0, 14)).cut(Part.makeCylinder(4, 2, V(0, 0, 14))))
        segs = sorted((f for f in shaft.Faces if type(f.Surface).__name__ == "Cylinder" and abs(f.Surface.Radius - 5) < 1e-9),
                      key=lambda f: f.CenterOfMass.z)
        self.assertEqual(len(segs), 2)
        found = rw.find(shaft, rw.signature(shaft, segs[0]))
        self.assertTrue(found is not None and found.isSame(segs[0]), found and found.CenterOfMass)

    def test_folding_inward_past_the_curvature_is_refused(self):
        """Critical 3: an ellipse 20 x 10 has its smallest radius of curvature 5: −5.5 would fold the outline."""
        shape = ellipse_pad()
        for mode in ("step", "inventor"):
            with self.assertRaises(ValueError) as e:
                rw.offset(shape, [wall_of(shape, "SurfaceOfExtrusion")], -5.5, mode)
            self.assertEqual(str(e.exception), rw.mf.TOO_LARGE_MSG, mode)
        block = Part.makeBox(60, 40, 10, V(-30, -20, 0)).cut(ellipse_pad())
        with self.assertRaises(ValueError) as e:  # the elliptic hole closing by 5.5 folds the same way
            rw.offset(block, [wall_of(block, "SurfaceOfExtrusion")], 5.5, "step")
        self.assertEqual(str(e.exception), rw.mf.TOO_LARGE_MSG)

    def test_together_inward_with_blends_is_refused(self):
        """Critical 2 / Important 8 (ruling): inward Together next to a fillet / chamfer is refused, not a ridge."""
        shape = user_like()
        with self.assertRaises(ValueError) as e:
            rw.offset(shape, [wall_of(shape, "SurfaceOfExtrusion")], -1.0, "together")
        self.assertEqual(str(e.exception), rw.INWARD_BLEND_MSG)

    def test_only_known_messages_reach_the_user(self):
        """Important 4: a blind drilled hole (cylinder + drill-point cone) in every mode both ways: a valid part or
        one of the module's own messages, never a raw OCC error."""
        hole = Part.makeCylinder(5, 8, V(20, 15, 2)).fuse(Part.makeCone(0, 5, 3, V(20, 15, -1))).removeSplitter()
        block = Part.makeBox(40, 30, 10).cut(hole)
        wall = wall_of(block, "Cylinder")
        known = {rw.mf.TOO_LARGE_MSG, rw.mf.ROUND_MSG, rw.mf.WALLS_MSG, rw.INWARD_BLEND_MSG, rw.OPEN_MSG,
                 rw.NOT_STRAIGHT_MSG, rw.CROSSED_MSG}
        for mode in ("step", "inventor", "together"):
            for d in (1.0, -1.0):
                try:
                    moved = rw.offset(block, [wall], d, mode)
                    self.assertTrue(moved.isValid(), (mode, d))
                except ValueError as e:
                    self.assertIn(str(e), known, (mode, d))

    def test_a_steep_slanted_top_in_inventor(self):
        """Important 5: a boss r5 with its top slanted 50°: Inventor ±1 works, nothing above the slanted top."""
        cyl = Part.makeCylinder(5, 30)
        cutter = Part.makeBox(60, 60, 60, V(-30, -30, 15)).rotated(V(0, 0, 15), V(0, 1, 0), 50)
        shape = cyl.cut(cutter)
        top = next(f for f in shape.Faces if rw.mf._is_plane(f) and f.normalAt(0, 0).z > 0.3)
        for d in (1.0, -1.0):
            moved = rw.offset(shape, [wall_of(shape, "Cylinder")], d, "inventor")
            self.assertTrue(moved.isValid(), d)
            self.assertAlmostEqual(wall_of(moved, "Cylinder").Surface.Radius, 5 + d, 6)
            for v in moved.Vertexes:
                self.assertLess((v.Point - top.CenterOfMass).dot(top.normalAt(0, 0)), 1e-6, d)

    def test_together_never_succeeds_without_moving(self):
        """Important 6: a hole through a 50° slanted top, Together +1: a moved wall or a refusal, never 'done'
        with the part unchanged."""
        block = Part.makeBox(40, 40, 30, V(-20, -20, 0))
        cutter = Part.makeBox(80, 80, 80, V(-40, -40, 15)).rotated(V(0, 0, 15), V(0, 1, 0), 50)
        block = block.cut(cutter).cut(Part.makeCylinder(5, 40, V(0, 0, -5)))
        try:
            moved = rw.offset(block, [wall_of(block, "Cylinder")], 1.0, "together")
        except ValueError as e:
            self.assertEqual(str(e), rw.mf.TOO_LARGE_MSG)
            return
        self.assertGreater(moved.Volume, block.Volume + 1)

    def test_step_never_adds_material_above_a_slanted_top(self):
        """Important 7: a boss with its top slanted 20°: Step +1 stays under the slanted top, as Inventor does."""
        cyl = Part.makeCylinder(5, 20)
        shape = cyl.cut(Part.makeBox(40, 40, 40, V(-20, -20, 10)).rotated(V(0, 0, 10), V(1, 0, 0), 20))
        top = next(f for f in shape.Faces if rw.mf._is_plane(f) and f.normalAt(0, 0).z > 0.5)
        moved = rw.offset(shape, [wall_of(shape, "Cylinder")], 1.0, "step")
        self.assertTrue(moved.isValid())
        for v in moved.Vertexes:
            self.assertLess((v.Point - top.CenterOfMass).dot(top.normalAt(0, 0)), 1e-6)
        inventor = rw.offset(shape, [wall_of(shape, "Cylinder")], 1.0, "inventor")
        self.assertAlmostEqual(moved.Volume, inventor.Volume, 3)

    def test_a_wall_crossed_by_another_hole_is_refused(self):
        """Important 9: a vertical hole crossed by a horizontal one: refused in every mode (comes later)."""
        block = Part.makeBox(40, 40, 20, V(-20, -20, 0)).cut(Part.makeCylinder(5, 20))
        block = block.cut(Part.makeCylinder(2, 40, V(-20, 0, 10), V(1, 0, 0)))
        wall = next(f for f in block.Faces if type(f.Surface).__name__ == "Cylinder" and abs(f.Surface.Radius - 5) < 1e-9)
        for mode in ("step", "inventor", "together"):
            with self.assertRaises(ValueError) as e:
                rw.offset(block, [wall], 1.0, mode)
            self.assertEqual(str(e.exception), rw.CROSSED_MSG, mode)


if __name__ == "__main__":
    unittest.main()
