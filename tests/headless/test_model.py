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

    def test_new_parameter_with_unknown_name_is_refused_plainly(self):
        before = model.feature_parameters(self.doc)
        with self.assertRaises(ValueError) as ctx:
            model.new_feature_parameter(self.doc, "Nope * 2")
        self.assertIn("Unknown name 'Nope'", str(ctx.exception))
        self.assertNotIn("property binding", str(ctx.exception))
        self.assertEqual(model.feature_parameters(self.doc), before)

    def test_unused_feature_parameter_can_be_removed(self):
        used = model.new_feature_parameter(self.doc, "25 mm")
        model.bind(self.pad, "Length", used)
        spare = model.new_feature_parameter(self.doc, "3 mm")
        self.doc.recompute()
        model.remove_model_parameter(self.doc, spare)
        self.assertNotIn(spare, [p[0] for p in model.feature_parameters(self.doc)])
        with self.assertRaises(ValueError) as ctx:
            model.remove_model_parameter(self.doc, used)
        self.assertIn(self.pad.Label, str(ctx.exception))


class RelinkAfterUndoTest(unittest.TestCase):
    """FreeCAD quirk (probed): an object restored by undo/abort loses its formula dependency links."""

    def setUp(self):
        from incad.features import extrude
        self.extrude = extrude
        self.doc = util.new_doc("RL")
        self.body = document.make_part(self.doc)
        sk = util.add_rect_sketch(self.body)
        self.doc.recompute()
        self.doc.openTransaction("create")
        self.f = extrude.create(self.doc, self.body, sk, extrude.defaults(self.doc, self.body, sk))
        self.doc.recompute()
        self.doc.commitTransaction()

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_relink_restores_live_formulas(self):
        self.doc.openTransaction("edit")
        self.extrude.update(self.doc, self.f, dict(self.extrude.read(self.doc, self.f), operation="cut"))
        self.doc.recompute()
        self.doc.abortTransaction()
        self.doc.recompute()
        self.assertEqual(model.relink(self.doc), ["Extrude"])
        model.set_model_parameter(self.doc, "d0", "4 mm")
        self.assertAlmostEqual(self.body.Tip.Length.Value, 4)

    def test_rollback_relinks_by_itself(self):
        from incad.core import safe

        def replace_then_fail():
            self.extrude.update(self.doc, self.f, dict(self.extrude.read(self.doc, self.f), operation="cut"))
            raise RuntimeError("boom")

        self.assertFalse(safe.run_safely("Bad", replace_then_fail, self.doc).ok)
        model.set_model_parameter(self.doc, "d0", "6 mm")
        self.assertAlmostEqual(self.body.Tip.Length.Value, 6)


class UserParameterNamesTest(unittest.TestCase):
    def test_user_parameter_cannot_take_a_feature_parameter_name(self):
        doc = util.new_doc("UP")
        try:
            document.make_part(doc)
            name = model.new_feature_parameter(doc, "5 mm")
            with self.assertRaises(ValueError):
                document.set_parameter(doc, name, "1 mm")
        finally:
            App.closeDocument(doc.Name)


class FriendlyErrorTest(unittest.TestCase):
    def test_unknown_name_is_said_plainly(self):
        doc = util.new_doc("FE")
        try:
            document.make_part(doc)
            name = model.new_feature_parameter(doc, "5 mm")
            with self.assertRaises(ValueError) as ctx:
                model.set_model_parameter(doc, name, "Nope * 2")
            self.assertIn("Unknown name 'Nope'", str(ctx.exception))
            self.assertNotIn("property binding", str(ctx.exception))
        finally:
            App.closeDocument(doc.Name)


class FriendlyEverywhereTest(unittest.TestCase):
    def test_dimensions_and_user_parameters_say_it_plainly(self):
        import Sketcher
        doc = util.new_doc("FE2")
        try:
            body = document.make_part(doc)
            sk = util.add_rect_sketch(body)
            sk.addConstraint(Sketcher.Constraint("DistanceX", 0, 1, 0, 2, 20))
            doc.recompute()
            name = sketch.name_new_dimensions(doc)[0]
            for fn in (lambda: sketch.set_dimension(doc, name, "Nope * 2"),
                       lambda: document.set_parameter(doc, "Gap", "Nope * 2")):
                with self.assertRaises(ValueError) as ctx:
                    fn()
                self.assertIn("Unknown name 'Nope'", str(ctx.exception))
        finally:
            App.closeDocument(doc.Name)
