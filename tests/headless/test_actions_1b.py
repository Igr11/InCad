import unittest

import FreeCAD as App
from incad import actions
from incad.core import context, document, safe
from headless import util


class BrowserCommandsTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Cmd")
        self.body, self.pad = util.padded_part(self.doc, 10, incad=True)
        self.sketch = self.doc.getObject("Sketch")

    def tearDown(self):
        context.set_target(None)
        App.closeDocument(self.doc.Name)

    def test_owning_feature(self):
        self.assertIs(document.owning_feature(self.sketch), self.pad)
        self.assertIs(document.owning_feature(self.pad), self.pad)

    def test_suppress_toggles(self):
        context.set_target(self.pad.Name)
        self.assertTrue(safe.run_safely("S", actions.toggle_suppress, self.doc).ok)
        self.assertTrue(self.pad.Suppressed)
        actions.toggle_suppress()
        self.assertFalse(self.pad.Suppressed)

    def test_rename(self):
        context.set_target(self.pad.Name)
        actions.rename(ask=lambda current: "Base Plate")
        self.assertEqual(self.pad.Label, "Base Plate")
        actions.rename(ask=lambda current: "")
        self.assertEqual(self.pad.Label, "Base Plate")

    def test_move_end_of_part_on_a_sketch_uses_its_feature(self):
        document.set_end_of_part(self.body, None)
        context.set_target(self.sketch.Name)
        actions.move_end_of_part_here()
        self.assertIs(self.body.Tip, self.pad)

    def test_no_target(self):
        context.set_target(None)
        with self.assertRaises(ValueError):
            actions.toggle_suppress()
        context.set_target("Nope")
        with self.assertRaises(ValueError):
            actions.rename(ask=lambda c: "x")
