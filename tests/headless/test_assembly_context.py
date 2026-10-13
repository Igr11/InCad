"""Edit a part from the assembly: the other parts around it (assembly.context_of)."""
import os
import shutil
import tempfile
import unittest

import FreeCAD as App
from incad.core import assembly
from headless.test_assembly import save_part


def moved(shape, placement):
    s = shape.copy()
    s.Placement = placement.multiply(s.Placement)
    return s


class AssemblyContextTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="incad_asm_ctx_")
        _, plate = save_part(self.dir, "Plate", 40, 30, 10)
        _, block = save_part(self.dir, "Block", 10, 10, 10)
        self.doc = App.newDocument("Asm")
        self.doc.UndoMode = 1
        assembly.make_assembly(self.doc, "mm")
        self.doc.saveAs(os.path.join(self.dir, "Asm.FCStd"))
        self.a = assembly.place(self.doc, plate)
        self.b = assembly.place(self.doc, block)
        self.b.Placement = App.Placement(App.Vector(50, 40, 25), App.Rotation(App.Vector(0, 0, 1), 90))
        self.doc.recompute()

    def tearDown(self):
        for name in list(App.listDocuments()):
            App.closeDocument(name)
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_the_other_part_lands_in_the_edited_parts_frame(self):
        ctx = assembly.context_of(self.doc, self.b)
        self.assertEqual([c[0] for c in ctx], [self.a.Name])
        _, shape, place = ctx[0]
        local = moved(shape, place)
        # the plate's corner (0,0,0) in the assembly, seen from the block turned 90° about Z and moved to (50,40,25)
        want = self.b.Placement.inverse().multVec(App.Vector(0, 0, 0))
        self.assertTrue(any(v.Point.isEqual(want, 1e-6) for v in local.Vertexes), (want, local.BoundBox))
        self.assertAlmostEqual(local.Volume, 40 * 30 * 10, 6)
        # the whole plate where the assembly has it, brought into the block's frame
        bb, ref = local.BoundBox, moved(self.a.Shape, self.b.Placement.inverse()).BoundBox
        for k in ("XMin", "YMin", "ZMin", "XMax", "YMax", "ZMax"):
            self.assertAlmostEqual(getattr(bb, k), getattr(ref, k), 6)

    def test_hidden_and_suppressed_parts_are_left_out(self):
        self.a.Visibility = False
        self.assertEqual(assembly.context_of(self.doc, self.b), [])
        self.a.Visibility = True
        assembly.toggle_suppressed(self.a)
        self.assertEqual(assembly.context_of(self.doc, self.b), [])

    def test_other_instances_of_the_same_part_are_context_too(self):
        b2 = assembly.place(self.doc, self.b.LinkedObject.Document.FileName)
        b2.Placement = App.Placement(App.Vector(-30, 0, 0), App.Rotation())
        self.doc.recompute()
        ctx = assembly.context_of(self.doc, self.b)
        self.assertEqual(sorted(c[0] for c in ctx), sorted([self.a.Name, b2.Name]))
        _, shape, place = next(c for c in ctx if c[0] == b2.Name)
        want = moved(b2.Shape, self.b.Placement.inverse()).BoundBox
        got = moved(shape, place).BoundBox
        self.assertTrue(got.isInside(want.Center) and abs(got.DiagonalLength - want.DiagonalLength) < 1e-6)


if __name__ == "__main__":
    unittest.main()
