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

    def test_grounding_is_not_a_constraint_to_suppress(self):
        g = [x for x in assembly.joints(self.doc) if hasattr(x, "ObjectToGround")][0]
        self.assertIsNone(C.kind_of(g))
        with self.assertRaises(ValueError):
            C.toggle_suppressed(g)
