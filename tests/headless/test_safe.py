import unittest

import FreeCAD as App
from incad.core import log, safe
from headless import util


class SafeTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Safe")
        self.messages = []
        log.set_reporter(lambda level, msg: self.messages.append((level, msg)))

    def tearDown(self):
        log.set_reporter(None)
        App.closeDocument(self.doc.Name)

    def test_success_commits_one_undo_step(self):
        r = safe.run_safely("Add body", lambda: self.doc.addObject("PartDesign::Body", "Body"), self.doc)
        self.assertTrue(r.ok)
        self.assertIsNotNone(self.doc.getObject("Body"))
        self.assertIn("Add body", self.doc.UndoNames)

    def test_turns_undo_on(self):
        doc = App.newDocument("NoUndo")
        try:
            self.assertEqual(doc.UndoMode, 0)
            def boom():
                doc.addObject("PartDesign::Body", "Body")
                raise RuntimeError("boom")
            safe.run_safely("Boom", boom, doc)
            self.assertIsNone(doc.getObject("Body"))
        finally:
            App.closeDocument(doc.Name)

    def test_exception_rolls_back_and_reports(self):
        def boom():
            self.doc.addObject("PartDesign::Body", "Body")
            raise RuntimeError("boom")
        r = safe.run_safely("Boom", boom, self.doc)
        self.assertFalse(r.ok)
        self.assertIn("boom", r.error)
        self.assertIsNone(self.doc.getObject("Body"))
        self.assertEqual(self.messages[-1][0], "error")
        with open(log.log_path()) as f:
            self.assertIn("boom", f.read())

    def test_invalid_result_rolls_back(self):
        body, pad = util.padded_part(self.doc, length=10)
        volume = pad.Shape.Volume
        r = safe.run_safely("Zero pad", lambda: setattr(pad, "Length", 0), self.doc)
        self.assertFalse(r.ok)
        self.assertIn("Pad", r.error)
        self.assertAlmostEqual(pad.Length.Value, 10)
        self.assertAlmostEqual(pad.Shape.Volume, volume, places=6)
        self.assertNotIn("Invalid", pad.State)

    def test_nested_failure_rolls_back_outer(self):
        def inner():
            raise ValueError("inner")

        def outer():
            self.doc.addObject("PartDesign::Body", "Body")
            safe.run_safely("Inner", inner, self.doc)

        r = safe.run_safely("Outer", outer, self.doc)
        self.assertFalse(r.ok)
        self.assertIsNone(self.doc.getObject("Body"))

    def test_undo_works_after_a_rollback(self):
        safe.run_safely("Boom", lambda: 1 / 0, self.doc)
        self.assertFalse(self.doc.HasPendingTransaction)
        safe.run_safely("Add body", lambda: self.doc.addObject("PartDesign::Body", "Body"), self.doc)
        self.doc.undo()
        self.assertIsNone(self.doc.getObject("Body"))
        self.doc.redo()
        self.assertIsNotNone(self.doc.getObject("Body"))

    def test_existing_broken_object_does_not_block(self):
        body, pad = util.padded_part(self.doc, length=10)
        pad.Length = 0
        self.doc.recompute()
        r = safe.run_safely("Add body", lambda: self.doc.addObject("PartDesign::Body", "Body001"), self.doc)
        self.assertTrue(r.ok)

    def test_no_document_still_catches(self):
        for name in list(App.listDocuments()):
            App.closeDocument(name)
        try:
            r = safe.run_safely("No doc", lambda: 1 / 0)
            self.assertFalse(r.ok)
            self.assertIn("division", r.error)
        finally:
            self.doc = util.new_doc("Safe")
