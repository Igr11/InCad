import unittest

import FreeCAD as App
from incad.core import document, safe
from headless import util


def rows(doc):
    return {name: (expr, value) for name, expr, value in document.list_parameters(doc)}


class ParametersTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Params")
        document.make_part(self.doc)

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_empty_without_creating(self):
        self.assertEqual(document.list_parameters(self.doc), [])
        self.assertIsNone(document.parameters(self.doc, create=False))

    def test_quantity(self):
        document.set_parameter(self.doc, "Width", "80 mm")
        self.assertEqual(rows(self.doc)["Width"], ("", "80 mm"))
        self.assertEqual(document.parameters(self.doc).Label, "Parameters")

    def test_formula_follows_source(self):
        document.set_parameter(self.doc, "Width", "80 mm")
        document.set_parameter(self.doc, "HoleD", "Width/8")
        self.assertEqual(rows(self.doc)["HoleD"], ("Width / 8", "10 mm"))  # FreeCAD normalizes spacing
        document.set_parameter(self.doc, "Width", "160 mm")
        self.assertEqual(rows(self.doc)["HoleD"][1], "20 mm")

    def test_formula_replaced_by_value(self):
        document.set_parameter(self.doc, "Width", "80 mm")
        document.set_parameter(self.doc, "HoleD", "Width/8")
        document.set_parameter(self.doc, "HoleD", "5 mm")
        self.assertEqual(rows(self.doc)["HoleD"], ("", "5 mm"))

    def test_invalid_names(self):
        for bad in ("", "2x", "a b", "Width-1", "Label"):
            with self.assertRaises(ValueError, msg=bad):
                document.set_parameter(self.doc, bad, "1")

    def test_unit_symbol_names_rejected_without_leftovers(self):
        for bad in ("mm", "A", "deg"):
            with self.assertRaises(ValueError, msg=bad) as ctx:
                document.set_parameter(self.doc, bad, "1")
            self.assertIn("unit", str(ctx.exception))
            self.assertNotIn(bad, rows(self.doc))

    def test_empty_value(self):
        with self.assertRaises(ValueError):
            document.set_parameter(self.doc, "Gap", "  ")

    def test_unknown_name_in_formula_is_rolled_back(self):
        r = safe.run_safely("Set", lambda: document.set_parameter(self.doc, "Gap", "Nope*2"), self.doc)
        self.assertFalse(r.ok)
        self.assertNotIn("Gap", rows(self.doc))

    def test_cycle_is_rolled_back(self):
        document.set_parameter(self.doc, "Len", "1")
        document.set_parameter(self.doc, "Twice", "Len*2")
        r = safe.run_safely("Cycle", lambda: document.set_parameter(self.doc, "Len", "Twice*2"), self.doc)
        self.assertFalse(r.ok)
        self.assertEqual(rows(self.doc)["Len"], ("", "1"))

    def test_remove(self):
        document.set_parameter(self.doc, "Gap", "0.2 mm")
        document.remove_parameter(self.doc, "Gap")
        self.assertNotIn("Gap", rows(self.doc))
        with self.assertRaises(ValueError):
            document.remove_parameter(self.doc, "Gap")

    def test_undo_after_failed_formula(self):
        safe.run_safely("Bad", lambda: document.set_parameter(self.doc, "Gap", "Nope*2"), self.doc)
        safe.run_safely("Good", lambda: document.set_parameter(self.doc, "Gap", "0.2 mm"), self.doc)
        self.doc.undo()
        self.assertNotIn("Gap", rows(self.doc))
