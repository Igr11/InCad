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
