"""Make Assembly: a part's separate pieces become part files with their history, linked by an assembly."""
import os
import tempfile
import unittest

import FreeCAD as App
import Part

from incad.core import assembly, document, make_assembly as ma
from headless import util


def _close_all():
    for name in list(App.listDocuments()):
        App.closeDocument(name)


class MakeAssemblyTest(unittest.TestCase):
    def setUp(self):
        _close_all()
        self.dir = tempfile.mkdtemp()
        self.doc = util.new_doc("Mk")
        self.body, self.pad = util.padded_part(self.doc, 10, incad=True)  # 20 x 10 x 10 = 2000
        far = util.add_rect_sketch(self.body, w=10, h=10, name="FarSk")
        far.AttachmentOffset = App.Placement(App.Vector(50, 0, 0), App.Rotation())
        self.box = util.add_pad(self.body, far, 5, name="Box")  # 500, separate
        self.body.Tip = self.box
        self.doc.recompute()
        self.path = os.path.join(self.dir, "Plate.FCStd")
        self.doc.saveAs(self.path)

    def tearDown(self):
        _close_all()

    def test_pieces_largest_first(self):
        found = ma.pieces(self.doc)
        self.assertEqual([round(p.volume) for p in found], [2000, 500])

    def test_default_names(self):
        self.assertEqual(ma.default_names(self.doc, 2), ("Plate-Assembly", ["Plate-Solid1", "Plate-Solid2"]))

    def test_two_part_files_with_history_and_an_assembly(self):
        asm_path = ma.make(self.doc, "Plate-Assembly", ["Plate-Solid1", "Plate-Solid2"])
        self.assertEqual(asm_path, os.path.join(self.dir, "Plate-Assembly.FCStd"))
        self.assertEqual([d.Name for d in App.listDocuments().values()], [self.doc.Name],
                         "no copy or assembly is left open (hidden) after Make Assembly")
        _close_all()
        vols = []
        for name, has in (("Plate-Solid1", "Pad"), ("Plate-Solid2", "Box")):
            d = App.openDocument(os.path.join(self.dir, name + ".FCStd"))
            d.recompute()
            body = document.primary_body(d)
            self.assertIsNotNone(body, name)
            self.assertEqual(len(body.Shape.Solids), 1, name)
            self.assertFalse([o.Name for o in d.Objects if "Invalid" in o.State], name)
            self.assertIsNotNone(d.getObject(has), "history kept in %s" % name)
            vols.append(round(body.Shape.Volume))
            App.closeDocument(d.Name)
        self.assertEqual(vols, [2000, 500])
        a = App.openDocument(asm_path)
        a.recompute()
        comps = assembly.components(a)
        self.assertEqual(len(comps), 2)
        self.assertTrue(assembly.is_grounded(comps[0]))
        self.assertAlmostEqual(comps[1].Shape.BoundBox.XMin, 50, places=6)  # where it was

    def test_the_original_file_is_unchanged(self):
        before = os.path.getmtime(self.path)
        ma.make(self.doc, "Plate-Assembly", ["Plate-Solid1", "Plate-Solid2"])
        self.assertEqual(os.path.getmtime(self.path), before)
        self.assertEqual(len(self.body.Shape.Solids), 2)

    def test_each_copy_is_an_incad_part_with_its_piece_as_primary(self):
        ma.make(self.doc, "Plate-Assembly", ["Plate-Solid1", "Plate-Solid2"])
        _close_all()
        d = App.openDocument(os.path.join(self.dir, "Plate-Solid2.FCStd"))
        self.assertTrue(document.is_incad_part(d))
        self.assertEqual(len(document.bodies(d)), 1)
        self.assertIs(document.primary_body(d), document.bodies(d)[0])

    def test_an_existing_file_is_refused(self):
        open(os.path.join(self.dir, "Plate-Solid2.FCStd"), "w").close()
        self.assertIn("exists", ma.check_names(self.doc, "Plate-Assembly", ["Plate-Solid1", "Plate-Solid2"]))
        with self.assertRaises(ValueError):
            ma.make(self.doc, "Plate-Assembly", ["Plate-Solid1", "Plate-Solid2"])
        self.assertFalse(os.path.exists(os.path.join(self.dir, "Plate-Solid1.FCStd")))

    def test_duplicate_names_are_refused(self):
        self.assertIn("twice", ma.check_names(self.doc, "Plate-Assembly", ["Plate-Solid1", "Plate-Solid1"]))

    def test_a_one_piece_part_is_refused(self):
        d = util.new_doc("One")
        util.padded_part(d, 10, incad=True)
        d.recompute()
        d.saveAs(os.path.join(self.dir, "One.FCStd"))
        with self.assertRaises(ValueError) as ctx:
            ma.make(d, "One-Assembly", ["One-Solid1"])
        self.assertIn("one piece", str(ctx.exception))

    def test_an_unsaved_part_is_refused(self):
        d = util.new_doc("Unsaved")
        util.padded_part(d, 10, incad=True)
        with self.assertRaises(ValueError) as ctx:
            ma.pieces_or_refuse(d)
        self.assertIn("Save", str(ctx.exception))

    def test_a_failure_removes_the_files_made(self):
        original = ma._finish_copy
        def broken(*a, **kw):
            raise ValueError("boom")
        ma._finish_copy = broken
        try:
            with self.assertRaises(ValueError):
                ma.make(self.doc, "Plate-Assembly", ["Plate-Solid1", "Plate-Solid2"])
        finally:
            ma._finish_copy = original
        self.assertEqual(sorted(os.listdir(self.dir)), ["Plate.FCStd"])

    def test_a_split_box_gives_two_parts_each_keeping_one_piece(self):
        from incad.features import split
        d = util.new_doc("Sb")
        body, pad = util.padded_part(d, 10, incad=True)
        sk = body.newObject("Sketcher::SketchObject", "Knife")
        sk.AttachmentSupport = [(util.xy_plane(body), "")]
        sk.MapMode = "FlatFace"
        sk.addGeometry(Part.LineSegment(App.Vector(5, -5, 0), App.Vector(5, 15, 0)))
        d.recompute()
        split.create(d, body, None, dict(split.defaults(d, body, None), sketch=sk.Name))
        d.recompute()
        d.saveAs(os.path.join(self.dir, "Sb.FCStd"))
        ma.make(d, "Sb-Assembly", ["Sb-Solid1", "Sb-Solid2"])
        _close_all()
        vols = []
        for name in ("Sb-Solid1", "Sb-Solid2"):
            p = App.openDocument(os.path.join(self.dir, name + ".FCStd"))
            p.recompute()
            b = document.primary_body(p)
            self.assertEqual(len(b.Shape.Solids), 1)
            vols.append(round(b.Shape.Volume))
            App.closeDocument(p.Name)
        self.assertEqual(vols, [1500, 500])


if __name__ == "__main__":
    unittest.main()
