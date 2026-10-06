import os
import shutil
import tempfile
import unittest

import FreeCAD as App
from incad.core import asm_cut, assembly, document
from headless import util
from headless.test_assembly import save_part

PLATE = 40 * 30 * 10


class AsmCutTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="incad_cut_")
        self.plate_doc, plate = save_part(self.dir, "Plate", 40, 30, 10)
        self.block_doc, block = save_part(self.dir, "Block", 10, 10, 10)
        self.asm = self.new_asm("Asm")
        self.a = assembly.place(self.asm, plate)
        self.b = assembly.place(self.asm, block)
        self.b.Placement = App.Placement(App.Vector(15, 10, 5), App.Rotation())
        self.asm.recompute()

    def new_asm(self, name):
        doc = App.newDocument(name)
        doc.UndoMode = 1
        assembly.make_assembly(doc, "mm")
        doc.saveAs(os.path.join(self.dir, name + ".FCStd"))
        return doc

    def tearDown(self):
        for name in list(App.listDocuments()):
            App.closeDocument(name)
        shutil.rmtree(self.dir, ignore_errors=True)

    def plate(self):
        return document.primary_body(self.plate_doc)

    def cut(self, **values):
        v = dict(clearance="0.2 mm", apply_to="cavity")
        v.update(values)
        rec = asm_cut.create(self.asm, self.a, [self.b], v)
        self.plate_doc.recompute()
        return rec

    def test_cut_is_written_into_the_base_file(self):
        rec = self.cut()
        self.assertAlmostEqual(self.plate().Shape.Volume, PLATE - 10.4 * 10.4 * 5.2, places=1)
        self.assertEqual(asm_cut.records(self.asm), [rec])
        self.assertAlmostEqual(self.block_doc.getObject("Pad").Shape.Volume, 1000, places=3)  # tool untouched

    def test_moving_the_tool_moves_the_pocket(self):
        self.cut()
        self.assertFalse(self.plate().Shape.isInside(App.Vector(20, 15, 9), 1e-6, True))
        self.b.Placement = App.Placement(App.Vector(2, 2, 5), App.Rotation())
        self.asm.recompute()
        changed = asm_cut.sync(self.asm)
        self.assertEqual(changed, [self.plate_doc])
        self.assertTrue(self.plate().Shape.isInside(App.Vector(20, 15, 9), 1e-6, True))
        self.assertFalse(self.plate().Shape.isInside(App.Vector(7, 7, 9), 1e-6, True))
        self.assertEqual(asm_cut.sync(self.asm), [])  # nothing moved since

    def test_editing_the_tool_updates_the_pocket(self):
        self.cut()
        pad = self.block_doc.getObject("Pad")
        pad.Length = 3  # block now z 5..8 in the assembly
        self.block_doc.recompute()
        self.plate_doc.recompute()
        self.assertAlmostEqual(self.plate().Shape.Volume, PLATE - 10.4 * 10.4 * 3.4, places=1)

    def test_fit_copy_lives_in_the_base_file(self):
        self.cut(apply_to="tool")
        fits = [b for b in document.bodies(self.plate_doc) if b.Label.endswith(" fit")]
        self.assertEqual(len(fits), 1)
        self.assertAlmostEqual(self.plate().Shape.Volume, PLATE - 10 * 10 * 5, places=1)

    def test_two_assemblies_do_not_fight(self):
        self.cut()
        other = self.new_asm("Asm2")
        a2 = assembly.place(other, self.plate_doc.FileName)
        b2 = assembly.place(other, self.block_doc.FileName)
        b2.Placement = App.Placement(App.Vector(25, 5, 5), App.Rotation())
        other.recompute()
        asm_cut.create(other, a2, [b2], dict(clearance="0 mm", apply_to="cavity"))
        self.plate_doc.recompute()
        volume = self.plate().Shape.Volume
        self.assertEqual(asm_cut.sync(self.asm), [])
        self.assertEqual(asm_cut.sync(other), [])
        self.assertAlmostEqual(self.plate().Shape.Volume, volume, places=6)

    def test_plain_freecad_file_is_refused(self):
        plain = util.new_doc("Plain")
        body = plain.addObject("PartDesign::Body", "Body")
        body.Tip = util.add_pad(body, util.add_rect_sketch(body, 5, 5, "S"), 5, "Pad")
        plain.recompute()
        plain.saveAs(os.path.join(self.dir, "Plain.FCStd"))
        c = assembly.place(self.asm, plain.FileName)
        with self.assertRaises(ValueError) as ctx:
            asm_cut.create(self.asm, c, [self.b], dict(clearance="0 mm", apply_to="cavity"))
        self.assertIn("InCad part", str(ctx.exception))

    def test_remove_restores_the_part(self):
        rec = self.cut(apply_to="split")
        asm_cut.remove(rec)
        self.plate_doc.recompute()
        self.assertAlmostEqual(self.plate().Shape.Volume, PLATE, places=3)
        self.assertEqual(asm_cut.records(self.asm), [])
        self.assertEqual([o for o in self.plate_doc.Objects if o.TypeId == "App::Link"], [])
        self.assertEqual([b for b in document.bodies(self.plate_doc) if b.Label.endswith(" fit")], [])
