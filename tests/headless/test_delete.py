import math
import unittest

import FreeCAD as App
import Part
from incad.core import delete, document, model, safe
from incad.features import combine, thread
from headless import util
from headless.test_combine import CombineTest
from headless.test_thread import shaft, cyl_face


class DeleteCombineTest(CombineTest):
    def test_delete_combine_removes_helpers_and_frees_the_parameter(self):
        f = self.make(operation="cut", clearance="0.2 mm", apply_to="split")
        name = combine.clearance_parameter(f)
        delete.delete(f)
        self.doc.recompute()
        self.assertEqual([o for o in self.doc.Objects if o.TypeId == "Part::Offset"], [])
        self.assertEqual(self.fit(), [])
        self.assertTrue(self.tool.Visibility)
        self.assertAlmostEqual(self.base.Shape.Volume, 40 * 30 * 10, places=3)
        model.remove_model_parameter(self.doc, name)  # nothing uses it any more


class DeleteTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Dl")
        self.body = document.make_part(self.doc)

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_delete_thread_removes_its_profile(self):
        pad = shaft(self.doc, self.body)
        t = thread.create(self.doc, self.body, None, dict(thread.defaults(self.doc, self.body, None),
                                                          face=cyl_face(pad, 5), size="M10"))
        self.doc.recompute()
        sk_name = t.Profile[0].Name
        delete.delete(t)
        self.doc.recompute()
        self.assertIsNone(self.doc.getObject(sk_name))
        self.assertIs(self.body.Tip, pad)

    def test_delete_in_the_middle_keeps_the_chain_and_undo_restores(self):
        a = util.add_pad(self.body, util.add_rect_sketch(self.body, 10, 10, "SA"), 5, "A")
        b = util.add_pad(self.body, util.add_rect_sketch(self.body, 4, 4, "SB"), 10, "B")
        self.body.Tip = b
        self.doc.recompute()
        res = safe.run_safely("Delete", lambda: delete.delete(a), self.doc)
        self.assertTrue(res.ok, res.error)
        self.assertIsNone(self.doc.getObject("A"))
        self.assertIs(self.body.Tip, b)
        self.assertAlmostEqual(b.Shape.Volume, 160, places=3)
        self.doc.undo()
        self.doc.recompute()
        self.assertIsNotNone(self.doc.getObject("A"))
        self.assertAlmostEqual(self.doc.getObject("B").Shape.Volume, 500 + 160 - 80, places=3)

    def test_delete_refuses_origin_items(self):
        with self.assertRaises(ValueError):
            delete.delete(self.body.Origin.OriginFeatures[0])
