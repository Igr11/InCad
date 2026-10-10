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

    def test_thick_solid_failure_after_a_thread_gets_the_shell_hint(self):
        """The kernel can't hollow the user's real part once its helical thread is in ('Failed to make thick
        solid'): the user is told to shell before the thread (End of Part above it), not a bare kernel message."""
        import os
        from incad.core import document
        from incad.features import dressup
        path = os.path.join(os.path.dirname(__file__), "..", "gui", "data", "p2_test_reordered.FCStd")
        doc = App.openDocument(os.path.abspath(path))
        try:
            doc.UndoMode = 1
            doc.recompute()
            body = document.primary_body(doc)
            tip = body.Tip
            top = max((i for i, f in enumerate(tip.Shape.Faces) if abs(f.normalAt(0, 0).z - 1) < 1e-6),
                      key=lambda i: tip.Shape.Faces[i].Area)

            def build():
                dressup._shell_create(doc, body, None, {"faces": "%s:Face%d" % (tip.Name, top + 1),
                                                         "thickness": "1 mm", "direction": "inside"})
                doc.recompute()
            r = safe.run_safely("Shell", build, doc)
            self.assertFalse(r.ok)
            self.assertIn("End of Part above the thread", r.error)
            self.assertNotIn("Failed to make thick solid", r.error)
        finally:
            App.closeDocument(doc.Name)


class KernelFailureMessageTest(unittest.TestCase):
    """'command not done' from the kernel is explained for the feature that failed, not always as a Revolve."""

    def setUp(self):
        self.doc = util.new_doc("KF")
        self.body, self.pad = util.padded_part(self.doc, 10, incad=True)
        log.set_reporter(lambda level, msg: None)

    def tearDown(self):
        log.set_reporter(None)
        App.closeDocument(self.doc.Name)

    def dress(self, kind, **values):
        from incad.features import dressup
        k = {"chamfer": dressup.CHAMFER, "fillet": dressup.FILLET}[kind]
        edges = ["Edge%d" % (i + 1) for i, e in enumerate(self.pad.Shape.Edges)
                 if abs(e.BoundBox.ZMin - 10) < 1e-6 and abs(e.BoundBox.ZMax - 10) < 1e-6][:2]
        vals = dict(k.defaults(self.doc, self.body, None), edges=",".join("%s:%s" % (self.pad.Name, e) for e in edges),
                    **values)
        return safe.run_safely(k.TITLE, lambda: k.create(self.doc, self.body, None, vals), self.doc)

    def test_a_too_big_chamfer_is_explained_as_a_chamfer(self):
        r = self.dress("chamfer", size="500 mm")
        self.assertFalse(r.ok)
        self.assertIn("chamfer", r.error.lower())
        self.assertNotIn("revolve", r.error.lower())
        self.assertIn("smaller", r.error)

    def test_a_too_big_fillet_is_explained_as_a_fillet(self):
        r = self.dress("fillet", radius="500 mm")
        self.assertFalse(r.ok)
        self.assertIn("fillet", r.error.lower())
        self.assertNotIn("revolve", r.error.lower())

    def test_a_revolve_failure_keeps_the_revolve_text(self):
        from incad.core import model
        self.assertIn("revolve", model.friendly("BRep_API: command not done", "PartDesign::Revolution"))
        self.assertIn("revolve", model.friendly("BRep_API: command not done", "PartDesign::Groove"))


class EmptyPatternTest(unittest.TestCase):
    """A pattern whose result is empty (FreeCAD calls it Valid) is reported, not left as 'nothing happened'."""

    class _Shape:
        def __init__(self, null, solids=()):
            self._null, self.Solids = null, list(solids)
            self.Volume = 0.0

        def isNull(self):
            return self._null

        def isValid(self):
            return True

    class _Obj:
        def __init__(self, type_id, shape):
            self.TypeId, self.Shape, self.State, self.Label, self.BaseFeature = type_id, shape, [], "RectangularPattern", None

    def test_an_empty_pattern_says_what_to_do(self):
        for type_id in ("PartDesign::LinearPattern", "PartDesign::PolarPattern", "PartDesign::Mirrored"):
            msg = safe._broken(self._Obj(type_id, self._Shape(True)), True)
            self.assertIn("pattern produced nothing", msg, type_id)
            self.assertIn("another feature", msg)

    def test_a_working_pattern_is_fine(self):
        shape = self._Shape(False, solids=[object()])
        shape.Volume = 5.0
        self.assertEqual(safe._broken(self._Obj("PartDesign::LinearPattern", shape), True), "")


class NoOpPatternTest(unittest.TestCase):
    """A pattern that leaves the part exactly as it was (a hole's copies land outside the material) is reported."""

    def setUp(self):
        import Part
        self.doc = util.new_doc("NoOp")
        self.body, self.pad = util.padded_part(self.doc, 10, incad=True)
        top = [i + 1 for i, f in enumerate(self.pad.Shape.Faces) if abs(f.CenterOfMass.z - 10) < 1e-6][0]
        sk = self.body.newObject("Sketcher::SketchObject", "HoleSk")
        sk.AttachmentSupport = [(self.pad, "Face%d" % top)]
        sk.MapMode = "FlatFace"
        sk.addGeometry(Part.Circle(App.Vector(10, 5, 0), App.Vector(0, 0, 1), 2))
        self.pocket = self.body.newObject("PartDesign::Pocket", "Hole2")
        self.pocket.Profile, self.pocket.Type = sk, 0
        self.pocket.Length = 3
        self.body.Tip = self.pocket
        self.doc.recompute()
        log.set_reporter(lambda level, msg: None)

    def tearDown(self):
        log.set_reporter(None)
        App.closeDocument(self.doc.Name)

    def pattern(self, spacing):
        from incad.features import common, patterns
        k = patterns.RECT
        vals = dict(k.defaults(self.doc, self.body, None), features=common.format_picks([(self.pocket, "")]),
                    count1="2", spacing1=spacing)
        return safe.run_safely("Pattern", lambda: k.create(self.doc, self.body, None, vals), self.doc)

    def test_a_pattern_whose_copies_miss_the_part_says_so(self):
        r = self.pattern("100 mm")  # the copy of the hole lands 100 mm beside the block
        self.assertFalse(r.ok)
        self.assertIn("changes nothing", r.error)
        self.assertIn("Pick another feature", r.error)

    def test_a_pattern_whose_copies_land_on_the_part_is_fine(self):
        r = self.pattern("6 mm")
        self.assertTrue(r.ok, r.error)


class ShellOnTwoSolidsTest(unittest.TestCase):
    """A body holding two separate solids (a box drawn away from the part): the kernel's 'Null input shape' is
    explained — Shell works on one connected solid."""

    def setUp(self):
        self.doc = util.new_doc("S2")
        self.body = document.make_part(self.doc)
        pad = util.add_pad(self.body, util.add_rect_sketch(self.body, name="S1"), 10, name="Box1")
        sk2 = util.add_rect_sketch(self.body, name="S2")
        sk2.AttachmentOffset = App.Placement(App.Vector(50, 50, 0), App.Rotation())
        self.pad2 = util.add_pad(self.body, sk2, 10, name="Box2")
        self.body.Tip = self.pad2
        self.doc.recompute()
        log.set_reporter(lambda level, msg: None)

    def tearDown(self):
        log.set_reporter(None)
        App.closeDocument(self.doc.Name)

    def test_message_names_the_two_solids(self):
        from incad.features import dressup
        top = [i + 1 for i, f in enumerate(self.pad2.Shape.Faces) if abs(f.CenterOfMass.z - 10) < 1e-6
               and f.CenterOfMass.x > 40][0]

        def build():
            dressup._shell_create(self.doc, self.body, None, {"faces": "Box2:Face%d" % top, "thickness": "1 mm",
                                                               "direction": "inside"})
            self.doc.recompute()
        r = safe.run_safely("Shell", build, self.doc)
        self.assertFalse(r.ok)
        self.assertIn("2 separate solids", r.error)
        self.assertIn("one connected solid", r.error)
        self.assertNotIn("Null input shape", r.error)
