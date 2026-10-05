import os
import tempfile
import unittest

import FreeCAD as App
from incad.core import document
from headless import util


class DocumentTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Doc")

    def tearDown(self):
        if self.doc.Name in App.listDocuments():
            App.closeDocument(self.doc.Name)

    def test_make_part_marks_and_sets_units(self):
        body = document.make_part(self.doc, "in")
        self.assertTrue(document.is_incad_part(self.doc))
        self.assertEqual(document.part_units(self.doc), "in")
        self.assertEqual(self.doc.UnitSystem, "Imperial decimal (in, lb)")
        self.assertIs(document.primary_body(self.doc), body)
        self.assertEqual(body.Label, "Solid1")

    def test_plain_document_is_not_a_part(self):
        self.assertFalse(document.is_incad_part(self.doc))
        self.assertIsNone(document.part_units(self.doc))
        self.assertIsNone(document.primary_body(self.doc))
        self.assertFalse(document.is_incad_part(None))

    def test_make_part_twice_fails(self):
        document.make_part(self.doc)
        with self.assertRaises(ValueError):
            document.make_part(self.doc)

    def test_bad_units(self):
        with self.assertRaises(ValueError):
            document.make_part(self.doc, "cm")

    def test_marker_survives_save_and_reopen(self):
        document.make_part(self.doc, "mm")
        path = os.path.join(tempfile.mkdtemp(), "part.FCStd")
        self.doc.saveAs(path)
        App.closeDocument(self.doc.Name)
        self.doc = App.openDocument(path)
        self.assertTrue(document.is_incad_part(self.doc))
        self.assertEqual(document.part_units(self.doc), "mm")
        self.assertIsNotNone(document.primary_body(self.doc))

    def test_convert_plain_file_with_one_body(self):
        self.doc.addObject("PartDesign::Body", "Body")
        body = document.convert_to_part(self.doc, "in")
        self.assertTrue(document.is_incad_part(self.doc))
        self.assertIs(document.primary_body(self.doc), body)
        self.assertEqual(document.part_units(self.doc), "in")

    def test_convert_refuses_zero_or_many_bodies(self):
        with self.assertRaises(ValueError):
            document.convert_to_part(self.doc)
        self.doc.addObject("PartDesign::Body", "Body")
        self.doc.addObject("PartDesign::Body", "Body001")
        with self.assertRaises(ValueError):
            document.convert_to_part(self.doc)

    def test_new_solid(self):
        document.make_part(self.doc)
        b2 = document.new_solid(self.doc)
        self.assertEqual(len(document.bodies(self.doc)), 2)
        self.assertEqual(b2.Label, "Solid2")
        self.assertIsNot(document.primary_body(self.doc), b2)

    def test_new_solid_requires_part(self):
        with self.assertRaises(ValueError):
            document.new_solid(self.doc)

    def test_end_of_part_rolls_back_and_forward(self):
        body, pad = util.padded_part(self.doc, 10, incad=True)
        self.assertIs(document.end_of_part(body), pad)
        document.set_end_of_part(body, None)
        self.assertIsNone(body.Tip)
        self.assertTrue(body.Shape.isNull())
        document.set_end_of_part(body, pad)
        self.assertAlmostEqual(body.Shape.Volume, 20 * 10 * 10, places=3)

    def test_end_of_part_rejects_foreign_feature(self):
        body, pad = util.padded_part(self.doc, 10, incad=True)
        other = self.doc.addObject("PartDesign::Body", "Other")
        with self.assertRaises(ValueError):
            document.set_end_of_part(other, pad)
