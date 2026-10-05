import unittest

import FreeCAD as App
from incad.core import document, model, sketch
from headless import util


class ModelTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("M")
        self.body, self.pad = util.padded_part(self.doc, 10, incad=True)

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_feature_parameter_drives_the_feature(self):
        name = model.new_feature_parameter(self.doc, "25 mm")
        self.assertEqual(name, "d0")
        model.bind(self.pad, "Length", name)
        self.doc.recompute()
        self.assertAlmostEqual(self.pad.Length.Value, 25)
        self.assertEqual(model.bound_parameter(self.pad, "Length"), "d0")
        self.assertEqual(model.parameter_text(self.doc, "d0"), "25 mm")

    def test_plain_numbers_use_part_units_and_degrees(self):
        a = model.new_feature_parameter(self.doc, "12")
        b = model.new_feature_parameter(self.doc, "30", unit_kind="angle")
        self.assertEqual(model.parameter_text(self.doc, a), "12 mm")
        self.assertEqual(model.parameter_text(self.doc, b), "30°")

    def test_names_shared_with_dimensions_and_user_parameters(self):
        document.set_parameter(self.doc, "d2", "1 mm")
        self.assertEqual(model.new_feature_parameter(self.doc, "5 mm"), "d3")
        sk = self.doc.getObject("Sketch")
        import Sketcher
        sk.addConstraint(Sketcher.Constraint("DistanceX", 0, 1, 0, 2, 20))
        self.doc.recompute()
        self.assertEqual(sketch.name_new_dimensions(self.doc), ["d4"])
        self.assertEqual([n for n, _, _ in model.model_parameters(self.doc)], ["d4", "d3"])

    def test_formulas_and_rename(self):
        n = model.new_feature_parameter(self.doc, "20 mm")
        m = model.new_feature_parameter(self.doc, "1 mm")
        model.set_model_parameter(self.doc, m, "%s / 4" % n)
        self.assertEqual(model.parameter_text(self.doc, m), "%s / 4" % n)
        model.rename_model_parameter(self.doc, n, "Depth")
        self.assertEqual(model.parameter_text(self.doc, m), "Depth / 4")
        self.assertTrue(model.is_model_parameter(self.doc, "Depth"))
        self.assertFalse(model.is_model_parameter(self.doc, n))
        with self.assertRaises(ValueError):
            model.rename_model_parameter(self.doc, "Depth", "mm")
        with self.assertRaises(ValueError):
            model.set_model_parameter(self.doc, "Depth", "Nope * 2")

    def test_model_object_is_hidden_from_the_browser(self):
        model.new_feature_parameter(self.doc, "1 mm")
        from incad.core import nodes, tree
        self.assertNotIn("InCadModel", [n.label for _, n in nodes.flatten(tree.build(self.doc))])
