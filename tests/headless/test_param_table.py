"""The Parameters window's table (incad.core.param_table): every parameter with what uses it, and Delete Unused."""
import unittest

import FreeCAD as App
import Sketcher
from incad.core import document, model, param_table, safe, sketch
from headless import util


class ParamTableTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("PT")
        self.body, self.pad = util.padded_part(self.doc, 10, incad=True)
        self.sk = self.doc.getObject("Sketch")
        self.sk.addConstraint(Sketcher.Constraint("DistanceX", 0, 1, 0, 2, 20))
        self.doc.recompute()
        self.dim = sketch.name_new_dimensions(self.doc)[0]
        self.depth = model.new_feature_parameter(self.doc, "25 mm")
        model.bind(self.pad, "Length", self.depth)
        self.spare = model.new_feature_parameter(self.doc, "3 mm")  # a deleted feature's value
        document.set_parameter(self.doc, "Width", "40 mm")
        sketch.set_dimension(self.doc, self.dim, "Width")  # the dimension follows Width
        document.set_parameter(self.doc, "Base", "8 mm")
        document.set_parameter(self.doc, "Half", "Base/2")  # Half unused; Base only used by Half
        self.doc.recompute()

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def table(self):
        return {r[1]: r for r in param_table.rows(self.doc)}

    def test_every_kind_with_what_uses_it(self):
        t = self.table()
        self.assertEqual(t[self.dim][0], "dimension")
        self.assertEqual(t[self.dim][4][0], self.sk.Label)  # a dimension's first user is its sketch
        self.assertEqual(t[self.dim][2], "Width")
        self.assertEqual(t[self.depth][0], "feature")
        self.assertIn(self.pad.Label, t[self.depth][4])
        self.assertEqual(t[self.spare][4], [])
        self.assertEqual(t["Width"][0], "user")
        self.assertTrue(any(self.sk.Label in u for u in t["Width"][4]), t["Width"][4])  # its dimension's sketch
        self.assertEqual(t["Base"][4], ["Half"])
        self.assertEqual(t["Half"][4], [])
        self.assertEqual(t["Half"][3], "4 mm")
        self.assertEqual(sorted(param_table.unused(self.doc)), sorted([self.spare, "Half"]))

    def test_delete_unused_takes_what_is_freed_too(self):
        r = safe.run_safely("Delete Unused", lambda: param_table.delete_unused(self.doc), self.doc)
        self.assertTrue(r.ok, r.error)
        self.assertEqual(sorted(r.value), sorted([self.spare, "Half", "Base"]))
        t = self.table()
        self.assertEqual(sorted(t), sorted([self.dim, self.depth, "Width"]))
        self.assertAlmostEqual(self.pad.Length.Value, 25)
        self.doc.undo()
        self.doc.recompute()
        self.assertIn("Half", self.table())  # one undo step brings them all back

    def test_nothing_unused(self):
        safe.run_safely("Delete Unused", lambda: param_table.delete_unused(self.doc), self.doc)
        r = safe.run_safely("Delete Unused", lambda: param_table.delete_unused(self.doc), self.doc)
        self.assertTrue(r.ok, r.error)
        self.assertEqual(r.value, [])


if __name__ == "__main__":
    unittest.main()
