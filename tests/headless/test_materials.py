import unittest

import FreeCAD as App
from incad.core import inspect, materials
from headless import util


class MaterialsTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Mt")
        self.body, self.pad = util.padded_part(self.doc, 10, incad=True)

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_default_is_pla(self):
        self.assertEqual(materials.material(self.doc), "PLA")
        self.assertIn("PETG", materials.names())

    def test_set_and_mass_follows(self):
        materials.set_material(self.doc, "Steel")
        self.assertEqual(materials.material(self.doc), "Steel")
        rows = dict(inspect.mass_properties(self.body, materials.density(self.doc)))
        self.assertEqual(rows["Mass"], "15.7 g")

    def test_unknown_material_is_refused(self):
        with self.assertRaises(ValueError):
            materials.set_material(self.doc, "Unobtainium")

    def test_material_change_is_undoable(self):
        from incad.core import safe
        res = safe.run_safely("Material", lambda: materials.set_material(self.doc, "Steel"), self.doc)
        self.assertTrue(res.ok, res.error)
        self.assertEqual(self.doc.UndoNames[0], "Material")
        self.doc.undo()
        self.assertEqual(materials.material(self.doc), "PLA")
