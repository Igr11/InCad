"""File ▸ Export: the visible Solids to STEP (re-imports with the same volume) and STL (a mesh file)."""
import os
import shutil
import tempfile
import unittest

import FreeCAD as App
import Part
from incad.core import document, export
from headless import util


class ExportTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Ex")
        self.body, self.pad = util.padded_part(self.doc, length=10, incad=True)
        hidden = document.new_solid(self.doc)
        util.add_pad(hidden, util.add_rect_sketch(hidden, 5, 5, "Small"), 3, "SmallPad")
        hidden.Tip = hidden.Group[-1]
        document.set_visibility([hidden], False)  # hidden by Hide / Show: not exported
        self.doc.recompute()
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        App.closeDocument(self.doc.Name)
        shutil.rmtree(self.dir)

    def test_step_has_the_visible_solid(self):
        path = os.path.join(self.dir, "part.step")
        export.export(self.doc, path)
        back = Part.read(path)
        self.assertAlmostEqual(back.Volume, 20 * 10 * 10, places=3)
        self.assertEqual(len(back.Solids), 1)

    def test_stl_mesh_normal_and_fine(self):
        import Mesh
        normal, fine = os.path.join(self.dir, "n.stl"), os.path.join(self.dir, "f.stl")
        self.assertGreater(export.export(self.doc, normal, "normal"), 0)
        export.export(self.doc, fine, "fine")
        self.assertAlmostEqual(Mesh.Mesh(normal).Volume, 2000, places=2)
        self.assertTrue(os.path.getsize(fine) > 0)

    def test_other_file_types_refused(self):
        with self.assertRaises(ValueError):
            export.export(self.doc, os.path.join(self.dir, "part.obj"))


if __name__ == "__main__":
    unittest.main()
