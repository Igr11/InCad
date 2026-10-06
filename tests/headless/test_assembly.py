import os
import shutil
import tempfile
import unittest

import FreeCAD as App
from incad.core import assembly, document
from incad.features import common
from headless import util


def save_part(folder, name, w, h, length):
    doc = util.new_doc(name)
    body = document.make_part(doc)
    pad = util.add_pad(body, util.add_rect_sketch(body, w, h, "S"), length, "Pad")
    body.Tip = pad
    doc.recompute()
    path = os.path.join(folder, name + ".FCStd")
    doc.saveAs(path)
    return doc, path


class AssemblyTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="incad_asm_")
        self.plate_doc, self.plate = save_part(self.dir, "Plate", 40, 30, 10)
        self.block_doc, self.block = save_part(self.dir, "Block", 10, 10, 10)
        self.doc = App.newDocument("Asm")
        self.doc.UndoMode = 1
        assembly.make_assembly(self.doc, "mm")
        self.doc.saveAs(os.path.join(self.dir, "Asm.FCStd"))

    def tearDown(self):
        for name in list(App.listDocuments()):
            App.closeDocument(name)
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_marker_and_objects(self):
        self.assertTrue(assembly.is_assembly(self.doc))
        self.assertFalse(document.is_incad_part(self.doc))
        self.assertEqual(assembly.assembly_of(self.doc).TypeId, "Assembly::AssemblyObject")

    def test_place_grounds_the_first_and_puts_the_next_beside(self):
        a = assembly.place(self.doc, self.plate)
        b = assembly.place(self.doc, self.block)
        self.doc.recompute()
        self.assertEqual(assembly.components(self.doc), [a, b])
        self.assertTrue(assembly.is_grounded(a))
        self.assertFalse(assembly.is_grounded(b))
        self.assertFalse(a.Shape.BoundBox.intersect(b.Shape.BoundBox))
        c = assembly.place(self.doc, self.block)
        self.assertIs(c.LinkedObject, b.LinkedObject)
        self.assertEqual(len(assembly.components(self.doc)), 3)

    def test_ground_and_unground(self):
        a = assembly.place(self.doc, self.plate)
        assembly.unground(a)
        self.assertFalse(assembly.is_grounded(a))
        assembly.ground(a)
        assembly.ground(a)
        self.assertTrue(assembly.is_grounded(a))
        self.assertEqual(len([j for j in assembly.joints(self.doc) if hasattr(j, "ObjectToGround")]), 1)

    def test_create_part_next_to_the_assembly(self):
        link = assembly.create_part(self.doc, "Bracket")
        path = os.path.join(self.dir, "Bracket.FCStd")
        self.assertTrue(os.path.isfile(path))
        part_doc = link.LinkedObject.Document
        self.assertTrue(document.is_incad_part(part_doc))
        self.assertEqual(part_doc.FileName, path)
        self.assertIn(link, assembly.components(self.doc))

    def test_unsaved_assembly_is_refused_plainly(self):
        doc = App.newDocument("Unsaved")
        assembly.make_assembly(doc, "mm")
        with self.assertRaises(ValueError) as ctx:
            assembly.place(doc, self.plate)
        self.assertIn("Save the assembly first", str(ctx.exception))

    def test_picks_on_the_assembly_resolve_to_the_component(self):
        b = assembly.place(self.doc, self.block)
        asm = assembly.assembly_of(self.doc)
        self.assertEqual(common.resolve(asm, "%s.Body.Pad.Face5" % b.Name), (b, "Face5"))
        self.assertEqual(common.resolve(asm, "%s.Face5" % b.Name), (b, "Face5"))

    def test_browser_tree(self):
        from incad.core import tree
        from incad.features import constraints as C
        a = assembly.place(self.doc, self.plate)
        b = assembly.place(self.doc, self.block)
        self.doc.recompute()
        top = [i + 1 for i, f in enumerate(a.LinkedObject.Shape.Faces) if abs(f.CenterOfMass.z - 10) < 1e-6][0]
        bot = [i + 1 for i, f in enumerate(b.LinkedObject.Shape.Faces) if abs(f.CenterOfMass.z) < 1e-6][0]
        C.MATE.create(self.doc, None, None, dict(C.MATE.defaults(self.doc, None), first="%s:Face%d" % (a.Name, top),
                                                 second="%s:Face%d" % (b.Name, bot)))
        root = tree.build(self.doc)[0]
        self.assertEqual(root.kind, "assembly")
        comps = [n for n in root.children if n.kind == "component"]
        self.assertEqual([(n.label, n.detail) for n in comps], [("Plate", "grounded"), ("Block", "")])
        rel = [n for n in root.children if n.kind == "relationships"][0]
        self.assertEqual([n.label for n in rel.children], ["Mate"])

    def test_placing_the_assembly_into_itself_is_refused(self):
        with self.assertRaises(ValueError) as ctx:
            assembly.place(self.doc, self.doc.FileName)
        self.assertIn("itself", str(ctx.exception))

    def test_placing_an_assembly_that_contains_this_one_is_refused(self):
        outer = App.newDocument("Outer")
        assembly.make_assembly(outer, "mm")
        outer.saveAs(os.path.join(self.dir, "Outer.FCStd"))
        assembly.place(outer, self.doc.FileName)
        outer.save()
        with self.assertRaises(ValueError) as ctx:
            assembly.place(self.doc, outer.FileName)
        self.assertIn("contains", str(ctx.exception))
