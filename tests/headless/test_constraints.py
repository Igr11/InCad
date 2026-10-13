import math
import os
import shutil
import tempfile
import unittest

import FreeCAD as App
import Part
from incad.core import assembly, document, model
from incad.features import constraints as C
from incad.features import kind_for
from headless import util
from headless.test_assembly import save_part


def face(link, pred):
    return "%s:Face%d" % (link.Name, [i + 1 for i, f in enumerate(link.LinkedObject.Shape.Faces) if pred(f)][0])


def z_is(v):
    return lambda f: f.Surface.TypeId == "Part::GeomPlane" and abs(f.CenterOfMass.z - v) < 1e-6


def x_is(v):
    return lambda f: f.Surface.TypeId == "Part::GeomPlane" and abs(f.CenterOfMass.x - v) < 1e-6


class ConstraintsTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="incad_con_")
        _, plate = save_part(self.dir, "Plate", 40, 30, 10)
        _, block = save_part(self.dir, "Block", 10, 10, 10)
        self.doc = App.newDocument("Asm")
        self.doc.UndoMode = 1
        assembly.make_assembly(self.doc, "mm")
        self.doc.saveAs(os.path.join(self.dir, "Asm.FCStd"))
        self.plate = assembly.place(self.doc, plate)
        self.block = assembly.place(self.doc, block)
        self.block.Placement = App.Placement(App.Vector(50, 40, 25), App.Rotation(10, 20, 30))
        self.doc.recompute()

    def tearDown(self):
        for name in list(App.listDocuments()):
            App.closeDocument(name)
        shutil.rmtree(self.dir, ignore_errors=True)

    def make(self, kind, **values):
        v = dict(kind.defaults(self.doc, None, None), **values)
        j = kind.create(self.doc, None, None, v)
        self.doc.recompute()
        return j

    def bb(self):
        return self.block.Shape.BoundBox

    def mate_bottom_on_top(self, **extra):
        return self.make(C.MATE, first=face(self.plate, z_is(10)), second=face(self.block, z_is(0)), **extra)

    def test_mate(self):
        j = self.mate_bottom_on_top()
        self.assertAlmostEqual(self.bb().ZMin, 10, places=4)
        self.assertAlmostEqual(self.bb().ZLength, 10, places=4)  # upright: faces opposed
        self.assertIs(kind_for(j), C.MATE)
        r = C.MATE.read(self.doc, j)
        self.assertEqual((r["first"], r["second"], r["offset"]),
                         (face(self.plate, z_is(10)), face(self.block, z_is(0)), "0 mm"))

    def test_offset_parameter_drives_the_mate(self):
        j = self.mate_bottom_on_top(offset="2 mm")
        self.assertAlmostEqual(self.bb().ZMin, 12, places=4)
        model.set_model_parameter(self.doc, model.bound_parameter(j, "Distance"), "5 mm")
        self.assertAlmostEqual(self.bb().ZMin, 15, places=4)

    def test_flush(self):
        self.make(C.FLUSH, first=face(self.plate, z_is(10)), second=face(self.block, z_is(10)))
        self.assertAlmostEqual(self.bb().ZMax, 10, places=4)
        self.assertAlmostEqual(self.bb().ZMin, 0, places=4)

    def test_rigid_keeps_the_relative_placement(self):
        self.make(C.RIGID, first=face(self.plate, z_is(10)), second=face(self.block, z_is(0)))
        self.assertAlmostEqual(self.bb().ZMin, 10, places=4)

    def test_a_constraint_value_is_named_after_it(self):
        """The user: the parameters should read Mate1, Flush1 — not d1, d2."""
        from incad.core import model
        j1 = self.mate_bottom_on_top(offset="2 mm")
        self.assertEqual(model.bound_parameter(j1, "Distance"), "Mate1")
        self.assertEqual(model.parameter_text(self.doc, "Mate1"), "2 mm")

    def test_editing_a_constraint_moves_the_part(self):
        """The user: edit a Mate's picks and offset in its dialog, not only its number in Parameters."""
        j = self.mate_bottom_on_top()
        values = dict(C.MATE.read(self.doc, j), offset="5 mm")
        C.MATE.update(self.doc, j, values)
        self.doc.recompute()
        self.assertAlmostEqual(self.bb().ZMin, 15, places=4)

    def test_two_ungrounded_components_still_solve(self):
        assembly.unground(self.plate)
        self.mate_bottom_on_top()
        gap = self.bb().ZMin - self.plate.Shape.BoundBox.ZMax
        self.assertAlmostEqual(gap, 0, places=4)

    def test_angle(self):
        self.mate_bottom_on_top()
        self.make(C.ANGLE, first=face(self.plate, x_is(40)), second=face(self.block, x_is(10)), angle="90 °")
        n1 = self.plate.Shape.Faces[[i for i, f in enumerate(self.plate.LinkedObject.Shape.Faces)
                                     if x_is(40)(f)][0]].normalAt(0, 0)
        n2 = self.block.Shape.Faces[[i for i, f in enumerate(self.block.LinkedObject.Shape.Faces)
                                     if x_is(10)(f)][0]].normalAt(0, 0)
        self.assertAlmostEqual(abs(n1.dot(n2)), 0, places=4)

    def test_conflict_is_refused_and_placement_kept(self):
        self.mate_bottom_on_top()
        before = App.Placement(self.block.Placement)
        with self.assertRaises(ValueError) as ctx:
            self.make(C.MATE, first=face(self.plate, z_is(10)), second=face(self.block, z_is(10)), offset="3 mm")
        self.assertIn("conflict", str(ctx.exception).lower())
        self.assertTrue(self.block.Placement.isSame(before, 1e-6))
        self.assertEqual(len([j for j in assembly.joints(self.doc) if C.claims(j)]), 1)

    def test_mate_and_flush_from_awkward_starts(self):
        for kind, pitch_roll, check in ((C.MATE, (0, -90, 0), lambda bb: abs(bb.ZMin - 10) < 1e-4),
                                        (C.FLUSH, (0, 90, 0), lambda bb: abs(bb.ZMax - 10) < 1e-4),
                                        (C.FLUSH, (0, 0, 90), lambda bb: abs(bb.ZMax - 10) < 1e-4)):
            for j in [j for j in assembly.joints(self.doc) if C.claims(j)]:
                self.doc.removeObject(j.Name)
            self.block.Placement = App.Placement(App.Vector(50, 40, 25), App.Rotation(*pitch_roll))
            self.doc.recompute()
            second = face(self.block, z_is(0)) if kind is C.MATE else face(self.block, z_is(10))
            self.make(kind, first=face(self.plate, z_is(10)), second=second)
            self.assertTrue(check(self.bb()), (kind.TITLE, pitch_roll, self.bb()))

    def _mate(self):
        return C.MATE.create(self.doc, None, None, dict(C.MATE.defaults(self.doc, None),
                                                        first=face(self.plate, z_is(10)), second=face(self.block, z_is(0))))

    def test_suppress_keeps_the_parts_and_unsuppress_solves_again(self):
        from incad.core import safe
        j = self._mate()
        at = App.Placement(self.block.Placement)
        r = safe.run_safely("Suppress", lambda: C.toggle_suppressed(j), self.doc)
        self.assertTrue(r.ok and r.value, r.error)
        self.assertTrue(j.Suppressed)
        self.assertTrue(self.block.Placement.isSame(at, 1e-9), "the parts stay where they are")
        self.assertEqual(self.doc.UndoNames[0], "Suppress")
        self.block.Placement = App.Placement(App.Vector(5, 5, 40), App.Rotation())  # moved while it was off
        self.doc.recompute()
        r = safe.run_safely("Suppress", lambda: C.toggle_suppressed(j), self.doc)
        self.assertTrue(r.ok and r.value is False, r.error)
        self.assertFalse(j.Suppressed)
        self.assertAlmostEqual(self.block.Shape.BoundBox.ZMin, 10, places=4)  # solved onto the plate again

    def test_unsuppress_that_cannot_be_met_is_refused_and_stays_suppressed(self):
        from incad.core import safe
        j = self._mate()
        safe.run_safely("Suppress", lambda: C.toggle_suppressed(j), self.doc)
        C.FLUSH.create(self.doc, None, None, dict(C.FLUSH.defaults(self.doc, None),  # block top flush with plate top
                                                  first=face(self.plate, z_is(10)), second=face(self.block, z_is(10))))
        at = App.Placement(self.block.Placement)
        r = safe.run_safely("Suppress", lambda: C.toggle_suppressed(j), self.doc)
        self.assertFalse(r.ok)
        self.assertIn("can't be met any more: it stays suppressed", r.error)
        self.assertTrue(j.Suppressed)
        self.assertTrue(self.block.Placement.isSame(at, 1e-6))

    def test_a_constraint_of_a_suppressed_part_is_not_unsuppressed_alone(self):
        j = self._mate()
        assembly.toggle_suppressed(self.block)  # the part's constraints go off with it
        self.assertTrue(j.Suppressed)
        with self.assertRaises(ValueError) as e:
            C.toggle_suppressed(j)
        self.assertIn("Block is suppressed", str(e.exception))

    def test_a_constraint_the_user_suppressed_stays_off_when_its_part_comes_back(self):
        j = self._mate()
        C.toggle_suppressed(j)  # the user's own
        assembly.toggle_suppressed(self.block)
        self.assertTrue(j.Suppressed)
        assembly.toggle_suppressed(self.block)
        self.assertFalse(assembly.is_suppressed(self.block))
        self.assertTrue(j.Suppressed, "the user suppressed it: it stays suppressed")

    def test_a_constraint_comes_back_only_with_both_its_parts(self):
        j = self._mate()
        assembly.toggle_suppressed(self.block)
        assembly.toggle_suppressed(self.plate)
        assembly.toggle_suppressed(self.block)
        self.assertTrue(j.Suppressed, "its other part is still suppressed")
        assembly.toggle_suppressed(self.plate)
        self.assertFalse(j.Suppressed, "both parts back: so is the constraint")

    def test_the_users_suppression_survives_both_parts_suppressed(self):
        j = self._mate()
        C.toggle_suppressed(j)
        assembly.toggle_suppressed(self.block)
        assembly.toggle_suppressed(self.plate)
        assembly.toggle_suppressed(self.block)
        assembly.toggle_suppressed(self.plate)
        self.assertTrue(j.Suppressed)

    def test_grounding_is_not_a_constraint_to_suppress(self):
        g = [x for x in assembly.joints(self.doc) if hasattr(x, "ObjectToGround")][0]
        self.assertIsNone(C.kind_of(g))
        with self.assertRaises(ValueError):
            C.toggle_suppressed(g)


def edge(link, x=None, y=None, z=None):
    """A straight edge of the part (own coordinates) whose middle has the given coordinates."""
    def ok(e):
        c = e.CenterOfMass
        return e.Curve.TypeId == "Part::GeomLine" and all(
            want is None or abs(got - want) < 1e-6 for got, want in ((c.x, x), (c.y, y), (c.z, z)))
    return "%s:Edge%d" % (link.Name, [i + 1 for i, e in enumerate(link.LinkedObject.Shape.Edges) if ok(e)][0])


def axis_of(doc, pick):
    """A pick's direction in the assembly: a flat face's normal, a straight edge's direction."""
    name, _, sub = pick.partition(":")
    el = doc.getObject(name).Shape.getElement(sub)
    if el.ShapeType == "Face":
        return App.Vector(el.normalAt(0, 0)).normalize()
    return App.Vector(el.Curve.Direction).normalize()


STARTS = (App.Rotation(10, 20, 30), App.Rotation(App.Vector(1, 1, 0.3), 134), App.Rotation(App.Vector(0, 1, 0), 20))


class DirectionConstraintsTest(unittest.TestCase):
    """Parallel, Perpendicular and Angle on flat faces and straight edges, in any mix: face + edge means what the user
    expects (Parallel: the edge lies along the face), not FreeCAD's raw normal-against-edge."""
    tearDown, make = ConstraintsTest.tearDown, ConstraintsTest.make

    def setUp(self):
        ConstraintsTest.setUp(self)
        self.plate_at = App.Placement(self.plate.Placement)

    def start(self, rot):
        for j in [j for j in assembly.joints(self.doc) if C.claims(j)]:
            self.doc.removeObject(j.Name)
        self.block.Placement = App.Placement(App.Vector(50, 40, 25), rot)
        self.doc.recompute()

    def degrees(self, p1, p2):
        """The angle between the two picks' axes, folded into 0..90 (edges have no side)."""
        d = abs(axis_of(self.doc, p1).dot(axis_of(self.doc, p2)))
        return math.degrees(math.acos(min(1.0, d)))

    def check(self, kind, p1, p2, want, **values):
        for rot in STARTS:
            self.start(rot)
            self.make(kind, first=p1, second=p2, **values)
            self.assertAlmostEqual(self.degrees(p1, p2), want, places=4, msg=(kind.TITLE, p1, p2, rot))
            self.assertTrue(self.plate.Placement.isSame(self.plate_at, 1e-9), "the grounded plate stays")

    # face + face
    def test_parallel_faces(self):
        self.check(C.PARALLEL, face(self.plate, z_is(10)), face(self.block, x_is(10)), 0)

    def test_perpendicular_faces(self):
        self.check(C.PERPENDICULAR, face(self.plate, z_is(10)), face(self.block, z_is(0)), 90)

    def test_angle_faces(self):
        self.check(C.ANGLE, face(self.plate, z_is(10)), face(self.block, z_is(0)), 30, angle="30 °")

    # edge + edge
    def test_parallel_edges(self):
        self.check(C.PARALLEL, edge(self.plate, y=0, z=10), edge(self.block, x=10, y=0), 0)

    def test_perpendicular_edges(self):
        self.check(C.PERPENDICULAR, edge(self.plate, y=0, z=10), edge(self.block, x=10, y=0), 90)

    def test_angle_edges(self):
        self.check(C.ANGLE, edge(self.plate, y=0, z=10), edge(self.block, x=10, y=0), 45, angle="45 °")

    # face + edge: the angle between the edge and the FACE (not its normal)
    def test_parallel_face_and_edge_lays_the_edge_along_the_face(self):
        self.check(C.PARALLEL, face(self.plate, z_is(10)), edge(self.block, x=10, y=0), 90)  # edge ⟂ normal

    def test_parallel_edge_and_face_in_that_order_too(self):
        self.check(C.PARALLEL, edge(self.block, x=10, y=0), face(self.plate, z_is(10)), 90)

    def test_perpendicular_face_and_edge_stands_the_edge_up(self):
        self.check(C.PERPENDICULAR, face(self.plate, z_is(10)), edge(self.block, x=10, y=0), 0)  # edge ∥ normal

    def test_angle_face_and_edge_is_the_angle_to_the_face(self):
        self.check(C.ANGLE, face(self.plate, z_is(10)), edge(self.block, x=10, y=0), 60, angle="30 °")  # 90 − 30

    def test_angle_90_on_face_and_edge_stands_the_edge_up(self):  # FreeCAD's Angle 0: normal along the edge
        self.check(C.ANGLE, face(self.plate, z_is(10)), edge(self.block, x=10, y=0), 0, angle="90 °")

    def test_angle_on_face_and_edge_reads_what_the_user_typed(self):
        j = self.make(C.ANGLE, first=face(self.plate, z_is(10)), second=edge(self.block, x=10, y=0), angle="30 °")
        self.assertEqual(C.ANGLE.read(self.doc, j)["angle"], "30°")
        self.assertAlmostEqual(j.Angle.Value, 60, places=6)  # FreeCAD's meaning: normal against edge
        name = C.ANGLE.param_names(j)["angle"]
        self.assertEqual(model.parameter_text(self.doc, name), "30°")
        model.set_model_parameter(self.doc, name, "20 °")  # the parameter still drives it
        self.doc.recompute()
        self.assertAlmostEqual(j.Angle.Value, 70, places=6)

    def test_editing_a_parallel_from_faces_to_face_and_edge_stays_parallel_for_the_user(self):
        j = self.make(C.PARALLEL, first=face(self.plate, z_is(10)), second=face(self.block, x_is(10)))
        self.assertEqual(j.JointType, "Parallel")
        values = dict(C.PARALLEL.read(self.doc, j), second=edge(self.block, x=10, y=0))
        C.PARALLEL.update(self.doc, j, values)
        self.doc.recompute()
        self.assertEqual(j.JointType, "Perpendicular")  # FreeCAD's normal-against-edge meaning
        self.assertAlmostEqual(self.degrees(values["first"], values["second"]), 90, places=4)
        C.PARALLEL.update(self.doc, j, dict(values, second=face(self.block, x_is(10))))  # and back
        self.assertEqual(j.JointType, "Parallel")

    def test_editing_an_angle_from_face_and_edge_to_faces_binds_the_value_plainly(self):
        j = self.make(C.ANGLE, first=face(self.plate, z_is(10)), second=edge(self.block, x=10, y=0), angle="30 °")
        C.ANGLE.update(self.doc, j, dict(C.ANGLE.read(self.doc, j), second=face(self.block, z_is(0))))
        self.doc.recompute()
        self.assertAlmostEqual(j.Angle.Value, 30, places=6)
        self.assertEqual(model.bound_parameter(j, "Angle"), C.ANGLE.param_names(j)["angle"])
        self.assertAlmostEqual(self.degrees(face(self.plate, z_is(10)), face(self.block, z_is(0))), 30, places=4)

    def test_parallel_after_perpendicular_on_the_same_faces_is_refused(self):
        self.make(C.PERPENDICULAR, first=face(self.plate, z_is(10)), second=face(self.block, z_is(0)))
        before = App.Placement(self.block.Placement)
        with self.assertRaises(ValueError) as ctx:
            self.make(C.PARALLEL, first=face(self.plate, z_is(10)), second=face(self.block, z_is(0)))
        self.assertIn("Parallel conflicts with the other constraints (it can't be met)", str(ctx.exception))
        self.assertTrue(self.block.Placement.isSame(before, 1e-6))
        self.assertEqual([C.kind_of(j) for j in assembly.joints(self.doc) if C.claims(j)], [C.PERPENDICULAR])

    def test_suppress_and_unsuppress_a_parallel(self):
        p1, p2 = face(self.plate, z_is(10)), face(self.block, x_is(10))
        j = self.make(C.PARALLEL, first=p1, second=p2)
        self.assertTrue(C.toggle_suppressed(j))
        self.block.Placement = App.Placement(App.Vector(50, 40, 25), App.Rotation(App.Vector(1, 1, 0.3), 70))
        self.doc.recompute()
        self.assertGreater(self.degrees(p1, p2), 1)
        self.assertFalse(C.toggle_suppressed(j))
        self.assertAlmostEqual(self.degrees(p1, p2), 0, places=4)

    def test_the_new_kinds_are_listed_after_angle(self):
        i = C.KINDS.index(C.ANGLE)
        self.assertEqual(C.KINDS[i + 1:i + 3], [C.PARALLEL, C.PERPENDICULAR])
        self.assertIs(kind_for(self.make(C.PARALLEL, first=face(self.plate, z_is(10)),
                                         second=face(self.block, x_is(10)))), C.PARALLEL)
        for k in (C.PARALLEL, C.PERPENDICULAR, C.ANGLE):
            self.assertEqual([f.pick for f in k.FIELDS if f.kind == "pick"], ["direction", "direction"])
        self.assertEqual([f.key for f in C.PARALLEL.FIELDS], ["first", "second"])  # no value


class RoundOneFixesTest(unittest.TestCase):
    """Review round 1: a stale or already-unmet constraint blocks nothing else; Angle 90° on a face and an edge is
    FreeCAD's Parallel; the joint's label stays what InCad named it when FreeCAD's type swaps."""
    tearDown, make = ConstraintsTest.tearDown, ConstraintsTest.make
    degrees, start = DirectionConstraintsTest.degrees, DirectionConstraintsTest.start

    def setUp(self):
        ConstraintsTest.setUp(self)
        _, bar = save_part(self.dir, "Bar", 20, 6, 4)
        self.bar = assembly.place(self.doc, bar)
        self.bar.Placement = App.Placement(App.Vector(-60, 10, 30), App.Rotation(App.Vector(1, 0.2, 0.5), 50))
        self.doc.recompute()

    def mate(self):
        return self.make(C.MATE, first=face(self.plate, z_is(10)), second=face(self.block, z_is(0)))

    def test_a_stale_reference_blocks_no_new_constraint_and_no_edit(self):
        m = self.mate()
        m.Reference2 = [self.block, ["Face99", "Face99"]]  # its face is gone (the part was changed)
        self.doc.recompute()
        p1, p2 = face(self.plate, z_is(10)), face(self.bar, z_is(4))
        j = self.make(C.PARALLEL, first=p1, second=p2)
        self.assertAlmostEqual(self.degrees(p1, p2), 0, places=4)
        p3 = edge(self.bar, y=0, z=4)
        C.PARALLEL.update(self.doc, j, dict(C.PARALLEL.read(self.doc, j), second=p3))
        self.assertAlmostEqual(self.degrees(p1, p3), 90, places=4)

    def test_unsuppress_next_to_an_already_unmet_angle(self):
        a = self.make(C.ANGLE, first=face(self.plate, z_is(10)), second=face(self.bar, z_is(4)), angle="30 °")
        # an old file: FreeCAD dropped this Angle without a word (here for a raw FreeCAD Parallel on the same faces)
        import JointObject
        raw = assembly.joint_group(self.doc).newObject("App::FeaturePython", "RawParallel")
        JointObject.Joint(raw, JointObject.JointTypes.index("Parallel"))
        (l1, e1), (l2, e2) = [(self.doc.getObject(n), el) for n, el in (r.split(":") for r in (
            C.ANGLE.read(self.doc, a)["first"], C.ANGLE.read(self.doc, a)["second"]))]
        raw.Proxy.setJointConnectors(raw, [[l1, [e1, e1]], [l2, [e2, e2]]])
        self.doc.recompute()
        self.assertFalse(C._met(self.doc, a, C.ANGLE, C.ANGLE.read(self.doc, a)))
        m = self.mate()
        self.assertTrue(C.toggle_suppressed(m))
        self.assertFalse(C.toggle_suppressed(m))  # not refused for the Angle's sake
        self.assertAlmostEqual(self.bb().ZMin, 10, places=4)

    def bb(self):
        return self.block.Shape.BoundBox

    def test_an_edit_that_breaks_another_constraint_is_refused(self):
        self.make(C.PERPENDICULAR, first=face(self.plate, z_is(10)), second=face(self.block, z_is(0)))
        j = self.make(C.PARALLEL, first=face(self.plate, z_is(10)), second=face(self.block, x_is(10)))
        before = App.Placement(self.block.Placement)
        with self.assertRaises(ValueError) as ctx:
            C.PARALLEL.update(self.doc, j, dict(C.PARALLEL.read(self.doc, j), second=face(self.block, z_is(0))))
        self.assertIn("Parallel conflicts with the other constraints", str(ctx.exception))
        self.assertTrue(self.block.Placement.isSame(before, 1e-6))

    def test_angle_90_on_a_face_and_an_edge_is_freecads_parallel(self):
        p1, p2 = face(self.plate, z_is(10)), edge(self.block, x=10, y=0)
        for rot in STARTS:
            self.start(rot)
            j = self.make(C.ANGLE, first=p1, second=p2, angle="90 °")
            self.assertEqual(j.JointType, "Parallel")  # not a degenerate Angle 0°
            self.assertAlmostEqual(self.degrees(p1, p2), 0, places=4, msg=rot)  # the edge stands up on the face
            self.assertEqual(C.ANGLE.read(self.doc, j)["angle"], "90°")
            self.assertEqual(j.Label, "Angle")
        C.ANGLE.update(self.doc, j, dict(C.ANGLE.read(self.doc, j), angle="30 °"))  # Edit: back to an Angle
        self.assertEqual((j.JointType, round(j.Angle.Value, 6)), ("Angle", 60))
        self.assertAlmostEqual(self.degrees(p1, p2), 60, places=4)
        name = C.ANGLE.param_names(j)["angle"]
        model.set_model_parameter(self.doc, name, "90 °")  # the Parameters window: the same switch
        self.assertEqual(j.JointType, "Parallel")
        self.assertAlmostEqual(self.degrees(p1, p2), 0, places=4)
        model.set_model_parameter(self.doc, name, "45 °")
        self.assertEqual(j.JointType, "Angle")
        self.assertAlmostEqual(self.degrees(p1, p2), 45, places=4)
        self.assertEqual((C.ANGLE.read(self.doc, j)["angle"], j.Label), ("45°", "Angle"))

    def test_the_label_stays_when_freecads_type_swaps(self):
        for kind in (C.PARALLEL, C.PERPENDICULAR):
            j = self.make(kind, first=face(self.plate, z_is(10)), second=edge(self.block, x=10, y=0))
            self.assertNotEqual(j.JointType, kind.joint)
            self.assertEqual(j.Label, kind.TITLE)
            self.doc.removeObject(j.Name)
        j = self.make(C.PARALLEL, first=face(self.plate, z_is(10)), second=face(self.block, x_is(10)))
        j.Label = "Lid Parallel"
        C.PARALLEL.update(self.doc, j, dict(C.PARALLEL.read(self.doc, j), second=edge(self.block, x=10, y=0)))
        self.assertEqual(j.Label, "Lid Parallel")


class DirectionPickTest(unittest.TestCase):
    def test_a_direction_is_a_flat_face_or_a_straight_edge(self):
        from incad.features.common import accepts
        doc = App.newDocument("Picks")
        try:
            box = doc.addObject("Part::Feature", "Box")
            box.Shape = Part.makeBox(10, 10, 10)
            cyl = doc.addObject("Part::Feature", "Cyl")
            cyl.Shape = Part.makeCylinder(3, 10)
            doc.recompute()
            self.assertTrue(accepts("direction", box, "Face1"))
            self.assertTrue(accepts("direction", box, "Edge1"))
            curved = [i + 1 for i, f in enumerate(cyl.Shape.Faces) if f.Surface.TypeId == "Part::GeomCylinder"][0]
            circle = [i + 1 for i, e in enumerate(cyl.Shape.Edges) if e.Curve.TypeId == "Part::GeomCircle"][0]
            self.assertFalse(accepts("direction", cyl, "Face%d" % curved))
            self.assertFalse(accepts("direction", cyl, "Edge%d" % circle))
            self.assertFalse(accepts("direction", box, "Vertex1"))
        finally:
            App.closeDocument(doc.Name)


def save_cylinder(folder, name, radius, height):
    """A part that is one cylinder (its axis the part's own Z)."""
    d = util.new_doc(name)
    body = document.make_part(d)
    cyl = body.newObject("PartDesign::AdditiveCylinder", name)
    cyl.Radius, cyl.Height = radius, height
    body.Tip = cyl
    d.recompute()
    path = os.path.join(folder, name + ".FCStd")
    d.saveAs(path)
    return path


def round_face(link):
    return "%s:Face%d" % (link.Name, [i + 1 for i, f in enumerate(link.LinkedObject.Shape.Faces)
                                      if f.Surface.TypeId == "Part::GeomCylinder"][0])


def normal_of(doc, pick):
    name, _, sub = pick.partition(":")
    f = doc.getObject(name).Shape.getElement(sub)
    return App.Vector(f.normalAt(*f.Surface.parameter(f.CenterOfMass))).normalize()


def cylinder_of(doc, pick):
    """(a point on the axis, the axis) of a round face in the assembly."""
    name, _, sub = pick.partition(":")
    s = doc.getObject(name).Shape.getElement(sub).Surface
    return App.Vector(s.Center), App.Vector(s.Axis).normalize()


class FlipTest(unittest.TestCase):
    """The user: 'For tangent match (mate, constraint) need the option to flip the side' — 'Yes, and Flip on Mate
    too'. Flip picks the constraint's other solution: Mate's faces face the same way, Flush's each other, Tangent's
    round face on the other side of the face (two round faces: inside), Insert's pin the other way, a joint's part
    turned over about the joint frame's X."""
    tearDown, make, bb = ConstraintsTest.tearDown, ConstraintsTest.make, ConstraintsTest.bb

    def setUp(self):
        ConstraintsTest.setUp(self)
        self.top, self.bottom = face(self.plate, z_is(10)), face(self.block, z_is(0))

    def update(self, kind, j, **values):
        kind.update(self.doc, j, dict(kind.read(self.doc, j), **values))
        self.doc.recompute()

    def test_flip_is_offered_where_there_is_another_solution(self):
        for k in (C.MATE, C.FLUSH, C.TANGENT, C.INSERT, C.ROTATIONAL, C.SLIDER, C.CYLINDRICAL):
            f = [f for f in k.FIELDS if f.key == "flip"]
            self.assertEqual([(x.label, x.kind, x.default) for x in f], [("Flip", "bool", False)], k.TITLE)
        for k in (C.ANGLE, C.PARALLEL, C.PERPENDICULAR, C.RIGID, C.BALL):
            self.assertNotIn("flip", [f.key for f in k.FIELDS], k.TITLE)

    def test_mate_flipped_faces_the_same_way_and_back(self):
        j = self.make(C.MATE, first=self.top, second=self.bottom, flip=True)
        self.assertAlmostEqual(normal_of(self.doc, self.top).dot(normal_of(self.doc, self.bottom)), 1, places=6)
        self.assertEqual((round(self.bb().ZMin, 4), round(self.bb().ZMax, 4)), (0, 10))  # bottom face on z 10, upside down
        self.assertEqual((j.Label, C.MATE.read(self.doc, j)["flip"]), ("Mate", True))
        self.update(C.MATE, j, flip=False)
        self.assertAlmostEqual(normal_of(self.doc, self.top).dot(normal_of(self.doc, self.bottom)), -1, places=6)
        self.assertEqual((round(self.bb().ZMin, 4), round(self.bb().ZMax, 4)), (10, 20))
        self.assertIs(C.MATE.read(self.doc, j)["flip"], False)

    def test_mate_flipped_keeps_its_offset(self):
        j = self.make(C.MATE, first=self.top, second=self.bottom, flip=True, offset="2 mm")
        self.assertAlmostEqual(normal_of(self.doc, self.top).dot(normal_of(self.doc, self.bottom)), 1, places=6)
        f = self.block.Shape.getElement(self.bottom.partition(":")[2])
        self.assertAlmostEqual(abs(f.CenterOfMass.z - 10), 2, places=4)
        self.assertEqual(C.MATE.read(self.doc, j)["offset"], "2 mm")

    def test_flush_flipped_faces_each_other(self):
        block_top = face(self.block, z_is(10))
        j = self.make(C.FLUSH, first=self.top, second=block_top, flip=True)
        self.assertAlmostEqual(normal_of(self.doc, self.top).dot(normal_of(self.doc, block_top)), -1, places=6)
        self.assertEqual((round(self.bb().ZMin, 4), round(self.bb().ZMax, 4)), (10, 20))
        self.assertEqual(j.Label, "Flush")
        self.update(C.FLUSH, j, flip=False)
        self.assertAlmostEqual(normal_of(self.doc, self.top).dot(normal_of(self.doc, block_top)), 1, places=6)
        self.assertAlmostEqual(self.bb().ZMax, 10, places=4)

    def rod(self, radius=3, name="Rod"):
        r = assembly.place(self.doc, save_cylinder(self.dir, name, radius, 20))
        r.Placement = App.Placement(App.Vector(10, 10, 30), App.Rotation(App.Vector(1, 0, 0), 80))
        self.doc.recompute()
        return r

    def side(self, rod_pick):
        """The rod axis' signed distance from the plate's top face (all along it: the axis lies parallel)."""
        c, a = cylinder_of(self.doc, rod_pick)
        self.assertAlmostEqual(a.z, 0, places=6)
        return c.z - 10

    def test_tangent_flipped_puts_the_round_face_on_the_other_side(self):
        for order in ("face first", "round face first"):
            rod = self.rod(name="Rod%d" % len(order))
            p = round_face(rod)
            picks = dict(first=self.top, second=p) if order == "face first" else dict(first=p, second=self.top)
            j = self.make(C.TANGENT, **picks)
            self.assertAlmostEqual(self.side(p), 3, places=4, msg=order)
            self.update(C.TANGENT, j, flip=True)
            self.assertAlmostEqual(self.side(p), -3, places=4, msg=order)
            self.assertIs(C.TANGENT.read(self.doc, j)["flip"], True)
            self.update(C.TANGENT, j, flip=False)
            self.assertAlmostEqual(self.side(p), 3, places=4, msg=order)
            self.doc.removeObject(j.Name)

    def test_tangent_flipped_from_the_start_and_with_an_offset(self):
        rod = self.rod()
        p = round_face(rod)
        j = self.make(C.TANGENT, first=self.top, second=p, flip=True, offset="1 mm")
        self.assertAlmostEqual(self.side(p), -4, places=4)  # the gap stays 1 mm, on the other side
        self.assertEqual(C.TANGENT.read(self.doc, j)["offset"], "1 mm")

    def test_tangent_sits_outside_by_default_on_every_flat_face(self):
        """The coordinator / Train_1: the default is the side the flat face's outward normal points to (outside the
        part), whichever way FreeCAD's plane frame points (it follows the surface, reversed on half a box's faces);
        Flip puts it inside."""
        flats = [i + 1 for i, f in enumerate(self.plate.LinkedObject.Shape.Faces) if f.Surface.TypeId == "Part::GeomPlane"]
        self.assertEqual(len(flats), 6)
        for k, n in enumerate(flats):
            rod = self.rod(name="Rod%d" % k)
            p, flat = round_face(rod), "%s:Face%d" % (self.plate.Name, n)
            for picks in (dict(first=flat, second=p), dict(first=p, second=flat)):
                rod.Placement = App.Placement(App.Vector(10, 10, 30), App.Rotation(App.Vector(1, 0, 0), 80))
                self.doc.recompute()
                j = self.make(C.TANGENT, **picks)
                self.assertAlmostEqual(self.signed(flat, p), 3, places=4, msg=(n, "default outside"))
                self.update(C.TANGENT, j, flip=True)
                self.assertAlmostEqual(self.signed(flat, p), -3, places=4, msg=(n, "flipped inside"))
                self.update(C.TANGENT, j, flip=False)
                self.assertAlmostEqual(self.signed(flat, p), 3, places=4, msg=(n, "back outside"))
                self.doc.removeObject(j.Name)
            self.doc.removeObject(rod.Name)

    def signed(self, flat, rod_pick):
        """The rod axis' signed distance from the flat face along its outward normal (the axis lies along it)."""
        name, _, sub = flat.partition(":")
        f = self.doc.getObject(name).Shape.getElement(sub)
        n = normal_of(self.doc, flat)
        c, a = cylinder_of(self.doc, rod_pick)
        self.assertAlmostEqual(a.dot(n), 0, places=6)
        return (c - f.CenterOfMass).dot(n)

    def big(self):
        b = assembly.place(self.doc, save_cylinder(self.dir, "Big", 8, 20))
        b.Placement = App.Placement(App.Vector(0, 0, 60), App.Rotation(App.Vector(1, 0, 0), 90))
        self.doc.recompute()
        assembly.ground(b)
        return b

    def axis_distance(self, p1, p2):
        (c1, a1), (c2, a2) = cylinder_of(self.doc, p1), cylinder_of(self.doc, p2)
        self.assertAlmostEqual(abs(a1.dot(a2)), 1, places=6)
        d = c2 - c1
        return (d - a1 * d.dot(a1)).Length

    def test_two_round_faces_flipped_touch_inside(self):
        b, rod = self.big(), self.rod()
        p1, p2 = round_face(b), round_face(rod)
        j = self.make(C.TANGENT, first=p1, second=p2)
        self.assertAlmostEqual(self.axis_distance(p1, p2), 11, places=4)  # outside: 8 + 3
        self.update(C.TANGENT, j, flip=True)
        self.assertAlmostEqual(self.axis_distance(p1, p2), 5, places=4)  # inside: 8 - 3
        r = C.TANGENT.read(self.doc, j)
        self.assertEqual((r["flip"], r["offset"]), (True, "0 mm"))
        self.assertEqual(C.TANGENT.param_names(j)["offset"], "Tangent1")
        self.update(C.TANGENT, j, offset="1 mm")  # the gap between the faces, inside too
        self.assertAlmostEqual(self.axis_distance(p1, p2), 4, places=4)
        self.assertEqual(model.parameter_text(self.doc, "Tangent1"), "1 mm")
        model.set_model_parameter(self.doc, "Tangent1", "2 mm")  # the parameter still drives it
        self.doc.recompute()
        self.assertAlmostEqual(self.axis_distance(p1, p2), 3, places=4)
        self.update(C.TANGENT, j, flip=False)
        self.assertAlmostEqual(self.axis_distance(p1, p2), 13, places=4)
        self.assertEqual(model.bound_parameter(j, "Distance"), "Tangent1")  # plain again

    def pin_in_hole(self):
        hd = App.getDocument("Plate")
        hb = document.primary_body(hd)
        hole = hb.newObject("PartDesign::SubtractiveCylinder", "HoleCyl")
        hole.Radius, hole.Height = 3, 10
        hole.Placement = App.Placement(App.Vector(20, 15, 0), App.Rotation())
        hb.Tip = hole
        hd.recompute()
        hd.save()
        self.doc.recompute()
        p = assembly.place(self.doc, save_cylinder(self.dir, "Pin", 3, 20))
        p.Placement = App.Placement(App.Vector(70, -30, 15), App.Rotation(App.Vector(1, 0.4, 0.2), 140))
        self.doc.recompute()
        mouth = [i + 1 for i, e in enumerate(self.plate.Shape.Edges) if e.Curve.TypeId == "Part::GeomCircle"
                 and abs(e.Curve.Radius - 3) < 1e-6 and abs(e.Curve.Center.z - 10) < 1e-6][0]
        end = [i + 1 for i, e in enumerate(p.LinkedObject.Shape.Edges) if e.Curve.TypeId == "Part::GeomCircle"
               and abs(e.Curve.Center.z) < 1e-6][0]
        return p, "%s:Edge%d" % (p.Name, end), "%s:Edge%d" % (self.plate.Name, mouth)

    def pin_axis(self, p):
        return p.Placement.Rotation.multVec(App.Vector(0, 0, 1))

    def on_hole_axis(self, p):
        c = p.Placement.Base  # the pin's end circle centre
        return App.Vector(c.x - 20, c.y - 15, 0).Length < 1e-4

    def test_insert_flipped_turns_the_pin_the_other_way(self):
        p, e1, e2 = self.pin_in_hole()
        plate_at = App.Placement(self.plate.Placement)
        j = self.make(C.INSERT, first=e1, second=e2)
        before = self.pin_axis(p)
        self.assertAlmostEqual(abs(before.z), 1, places=6)
        self.update(C.INSERT, j, flip=True)
        self.assertAlmostEqual(self.pin_axis(p).dot(before), -1, places=6)
        self.assertTrue(self.on_hole_axis(p))
        self.assertAlmostEqual(p.Placement.Base.z, 10, places=4)  # its end circle still on the hole's mouth
        self.assertTrue(self.plate.Placement.isSame(plate_at, 1e-7), "the grounded plate stays")
        self.update(C.INSERT, j, flip=False)
        self.assertAlmostEqual(self.pin_axis(p).dot(before), 1, places=6)
        self.assertTrue(self.on_hole_axis(p))

    def test_joints_flipped_turn_the_part_over(self):
        for kind in (C.ROTATIONAL, C.SLIDER, C.CYLINDRICAL):
            if not hasattr(self, "pin"):
                self.pin, self.e1, self.e2 = self.pin_in_hole()
            p = self.pin
            p.Placement = App.Placement(App.Vector(70, -30, 15), App.Rotation(App.Vector(1, 0.4, 0.2), 140))
            self.doc.recompute()
            j = self.make(kind, first=self.e1, second=self.e2)
            before = self.pin_axis(p)
            self.update(kind, j, flip=True)
            self.assertAlmostEqual(self.pin_axis(p).dot(before), -1, places=6, msg=kind.TITLE)
            self.assertTrue(self.on_hole_axis(p), kind.TITLE)
            self.assertIs(kind.read(self.doc, j)["flip"], True)
            self.update(kind, j, flip=False)
            self.assertAlmostEqual(self.pin_axis(p).dot(before), 1, places=6, msg=kind.TITLE)
            self.doc.removeObject(j.Name)

    def test_a_flipped_joint_from_the_start(self):
        p, e1, e2 = self.pin_in_hole()
        j0 = self.make(C.INSERT, first=e1, second=e2)
        natural = self.pin_axis(p)
        self.doc.removeObject(j0.Name)
        p.Placement = App.Placement(App.Vector(70, -30, 15), App.Rotation(App.Vector(1, 0.4, 0.2), 140))
        self.doc.recompute()
        self.make(C.INSERT, first=e1, second=e2, flip=True)
        self.assertAlmostEqual(self.pin_axis(p).dot(natural), -1, places=6)

    def test_reapplying_the_same_choice_flips_nothing(self):
        p, e1, e2 = self.pin_in_hole()
        j = self.make(C.INSERT, first=e1, second=e2, flip=True)
        at = App.Placement(p.Placement)
        for _ in range(2):  # a preview refresh, an Edit OK without a change
            self.update(C.INSERT, j)
            self.assertAlmostEqual(self.pin_axis(p).dot(at.Rotation.multVec(App.Vector(0, 0, 1))), 1, places=6)
        assembly.assembly_of(self.doc).solve()  # a re-solve
        self.doc.recompute()
        self.assertAlmostEqual(self.pin_axis(p).dot(at.Rotation.multVec(App.Vector(0, 0, 1))), 1, places=6)
        m = self.make(C.MATE, first=self.top, second=self.bottom, flip=True)
        at = App.Placement(self.block.Placement)
        self.update(C.MATE, m)
        self.update(C.MATE, m)
        self.assertTrue(self.block.Placement.isSame(at, 1e-6))

    def test_flip_survives_save_and_reopen(self):
        rod = self.rod()
        p = round_face(rod)
        t = self.make(C.TANGENT, first=self.top, second=p, flip=True)
        m = self.make(C.MATE, first=self.top, second=self.bottom, flip=True)
        names = (t.Name, m.Name)
        self.doc.save()
        path = self.doc.FileName
        App.closeDocument(self.doc.Name)
        self.doc = App.openDocument(path)
        self.doc.recompute()
        t, m = [self.doc.getObject(n) for n in names]
        self.assertIs(C.TANGENT.read(self.doc, t)["flip"], True)
        self.assertIs(C.MATE.read(self.doc, m)["flip"], True)
        assembly.assembly_of(self.doc).solve()
        self.doc.recompute()
        self.assertAlmostEqual(self.side(p), -3, places=4)
        self.assertTrue(C._met(self.doc, m, C.MATE, C.MATE.read(self.doc, m)))
        self.assertEqual(C._unmet(self.doc), set())

    def test_old_constraints_read_unflipped(self):
        j = self.make(C.MATE, first=self.top, second=self.bottom)
        if C._FLIP in j.PropertiesList:
            j.removeProperty(C._FLIP)  # a file from before Flip
        self.assertIs(C.MATE.read(self.doc, j)["flip"], False)
        self.update(C.MATE, j, flip=True)
        self.assertAlmostEqual(normal_of(self.doc, self.top).dot(normal_of(self.doc, self.bottom)), 1, places=6)

    def test_a_flip_that_cant_be_met_is_refused_and_the_parts_stay(self):
        m = self.make(C.MATE, first=self.top, second=self.bottom)
        self.make(C.FLUSH, first=face(self.plate, x_is(40)), second=face(self.block, x_is(10)))
        self.make(C.FLUSH, first=face(self.plate, lambda f: f.Surface.TypeId == "Part::GeomPlane"
                                       and abs(f.CenterOfMass.y - 30) < 1e-6),
                  second=face(self.block, lambda f: f.Surface.TypeId == "Part::GeomPlane"
                              and abs(f.CenterOfMass.y - 10) < 1e-6))
        at = App.Placement(self.block.Placement)
        with self.assertRaises(ValueError) as ctx:
            C.MATE.update(self.doc, m, dict(C.MATE.read(self.doc, m), flip=True))
        self.assertIn("Mate conflicts with the other constraints", str(ctx.exception))
        self.assertTrue(self.block.Placement.isSame(at, 1e-6))
        self.assertIs(C.MATE.read(self.doc, m)["flip"], False)
        with self.assertRaises(ValueError):  # a new one too: refused, nothing moved, nothing left
            self.make(C.FLUSH, first=self.top, second=face(self.block, z_is(10)), flip=True, offset="3 mm")
        self.assertTrue(self.block.Placement.isSame(at, 1e-6))
        self.assertEqual(len([j for j in assembly.joints(self.doc) if C.claims(j)]), 3)

    def test_a_flipped_mate_leaves_the_freedoms_as_they_are(self):
        from incad.core import dof
        j = self.make(C.MATE, first=self.top, second=self.bottom)
        n = dof.compute(self.doc)[self.block.Name].n
        self.update(C.MATE, j, flip=True)
        self.assertEqual(dof.compute(self.doc)[self.block.Name].n, n)
