import unittest

import FreeCAD as App
from incad.core import document, log, safe
from incad.features import thread
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
        with open(log.log_path(), encoding="utf-8") as f:
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

    def test_stray_pending_transaction_is_kept_apart(self):
        self.doc.openTransaction("User change")
        self.doc.addObject("PartDesign::Body", "Edited")

        def boom():
            self.doc.addObject("PartDesign::Body", "Body")
            raise RuntimeError("boom")

        r = safe.run_safely("Boom", boom, self.doc)
        self.assertFalse(r.ok)
        self.assertIsNone(self.doc.getObject("Body"))
        self.assertIsNotNone(self.doc.getObject("Edited"), "our rollback must not undo the user's change")
        self.assertIn("User change", self.doc.UndoNames)
        self.assertFalse(self.doc.HasPendingTransaction)

    def test_an_empty_part_is_not_broken(self):
        body, pad = util.padded_part(self.doc, length=10)
        r = safe.run_safely("Suppress", lambda: setattr(pad, "Suppressed", True), self.doc)
        self.assertTrue(r.ok, r.error)
        self.assertTrue(pad.Suppressed)

    def test_busy_refuses_new_changes(self):
        safe.set_busy("Extrude")
        try:
            r = safe.run_safely("Add", lambda: self.doc.addObject("PartDesign::Body", "Body"), self.doc)
            self.assertFalse(r.ok)
            self.assertIn("Extrude", r.error)
            self.assertIsNone(self.doc.getObject("Body"))
        finally:
            safe.set_busy(None)
        self.assertIsNone(safe.busy())

    def test_problems_reports_invalid_features(self):
        body, pad = util.padded_part(self.doc, length=10)
        before = safe.snapshot_broken(self.doc)
        pad.Length = 0
        self.doc.recompute()
        found = safe.problems(self.doc, before, {pad.Name})
        self.assertTrue(any("Pad" in p for p in found), found)

    def test_no_document_still_catches(self):
        for name in list(App.listDocuments()):
            App.closeDocument(name)
        try:
            r = safe.run_safely("No doc", lambda: 1 / 0)
            self.assertFalse(r.ok)
            self.assertIn("division", r.error)
        finally:
            self.doc = util.new_doc("Safe")

class ModeledThreadHintTest(unittest.TestCase):
    """An empty cut result is blamed on a modeled helix earlier in the part, not on 'cuts away the whole part'."""

    class _F:
        def __init__(self, name, type_id, base=None, model_thread=False):
            self.Name, self.TypeId, self.BaseFeature, self.ModelThread = name, type_id, base, model_thread

    def test_helix_or_modeled_hole_thread_in_the_base_chain_is_found(self):
        pad = self._F("Pad", "PartDesign::Pad")
        hole = self._F("Hole", "PartDesign::Hole", pad, model_thread=True)
        helix = self._F("Thread", "PartDesign::SubtractiveHelix", pad)
        self.assertTrue(safe._has_modeled_thread(self._F("Pocket", "PartDesign::Pocket", hole)))
        self.assertTrue(safe._has_modeled_thread(self._F("Chamfer", "PartDesign::Groove", helix)))

    def test_plain_or_cosmetic_chain_is_not_flagged(self):
        pad = self._F("Pad", "PartDesign::Pad")
        hole = self._F("Hole", "PartDesign::Hole", pad, model_thread=False)
        self.assertFalse(safe._has_modeled_thread(self._F("Pocket", "PartDesign::Pocket", hole)))
        self.assertFalse(safe._has_modeled_thread(None))


class ModeledThreadKernelTest(unittest.TestCase):
    """The real kernel path: a cut that removes everything is blamed on the thread only when a modeled one precedes it."""

    def setUp(self):
        from headless import test_thread
        self.doc = util.new_doc("SafeThread")
        self.body = document.make_part(self.doc)
        self.shaft = test_thread.shaft(self.doc, self.body)
        self.cyl_face = test_thread.cyl_face
        log.set_reporter(lambda level, msg: None)

    def tearDown(self):
        log.set_reporter(None)
        App.closeDocument(self.doc.Name)

    def cut_everything(self):
        import Part
        def build():
            sk = self.body.newObject("Sketcher::SketchObject", "BigSk")
            sk.AttachmentSupport = [(util.xy_plane(self.body), "")]
            sk.MapMode = "FlatFace"
            sk.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 50))
            pocket = self.body.newObject("PartDesign::Pocket", "Pocket")
            pocket.Profile, pocket.Type, pocket.SideType = sk, 1, "Symmetric"
            self.body.Tip = pocket
            self.doc.recompute()
            return pocket
        return safe.run_safely("Cut everything", build, self.doc)

    def test_plain_part_keeps_the_generic_message(self):
        r = self.cut_everything()
        self.assertFalse(r.ok)
        self.assertIn("cuts away the whole part", r.error)

    def test_modeled_thread_gets_the_thread_hint(self):
        v = dict(thread.defaults(self.doc, self.body, None), face=self.cyl_face(self.shaft, 5),
                 standard="iso", size="M10", clearance="0 mm")
        thread.create(self.doc, self.body, None, v)
        self.doc.recompute()
        r = self.cut_everything()
        self.assertFalse(r.ok)
        self.assertIn("modeled (helical) thread", r.error)
        self.assertNotIn("cuts away the whole part", r.error)
