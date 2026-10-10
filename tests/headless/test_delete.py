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

    def test_delete_sweep_removes_its_wall(self):
        from incad.features import shapes
        from headless.test_shapes import sketch
        pad = util.add_pad(self.body, util.add_rect_sketch(self.body, name="BaseSk"), 5, name="Base")
        self.body.Tip = pad
        sketch(self.body, "YZ_Plane", "Prof", [Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 3)])
        sketch(self.body, "XY_Plane", "Path", [Part.LineSegment(App.Vector(0, 0, 0), App.Vector(30, 0, 0))])
        self.doc.recompute()
        f = shapes.SWEEP.create(self.doc, self.body, None, dict(shapes.SWEEP.defaults(self.doc, self.body, None),
                                                                 profile="Prof", path="Path", hollow=True))
        self.doc.recompute()
        self.assertIsNotNone(shapes.wall_of(f))
        delete.delete(f)
        self.doc.recompute()
        self.assertFalse(any(o.TypeId in ("PartDesign::Thickness", "PartDesign::AdditivePipe") for o in self.body.Group))
        self.assertIs(self.body.Tip, pad)

    def test_delete_refuses_origin_items(self):
        with self.assertRaises(ValueError):
            delete.delete(self.body.Origin.OriginFeatures[0])


class DeleteKeptFitTest(CombineTest):
    def test_delete_combine_with_a_worked_on_fit_copy(self):
        f = self.make(operation="cut", clearance="0.2 mm", apply_to="tool")
        fit = self.fit()[0]
        util.add_pad(fit, util.add_rect_sketch(fit, 2, 2, "UserSk"), 2, "UserPad")
        self.doc.recompute()
        res = safe.run_safely("Delete", lambda: delete.delete(f), self.doc)
        self.assertTrue(res.ok, res.error)
        self.assertIsNotNone(self.doc.getObject(fit.Name))
        self.assertTrue(self.doc.getObject(fit.Name).Shape.isValid())


class DeleteKeepsThePartOnScreenTest(unittest.TestCase):
    """Deleting a feature must leave the new End of Part shown: FreeCAD hides every feature but the newest, so the
    one before it was hidden and the view went blank."""

    def setUp(self):
        self.doc = util.new_doc("Dv")
        self.body = document.make_part(self.doc)
        sk = util.add_rect_sketch(self.body, name="SkA")
        self.pad = util.add_pad(self.body, sk, 10, name="PadA")
        self.pad2 = util.add_pad(self.body, util.add_rect_sketch(self.body, w=5, h=5, name="SkB"), 5, name="PadB")
        self.pad3 = util.add_pad(self.body, util.add_rect_sketch(self.body, w=3, h=3, name="SkC"), 2, name="PadC")
        self.body.Tip = self.pad3
        self.doc.recompute()
        for o in (self.pad, self.pad2):
            o.Visibility = False  # as FreeCAD leaves them
        self.pad3.Visibility = True

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def shown(self):
        return [o.Name for o in self.body.Group if o.isDerivedFrom("PartDesign::Feature") and o.Visibility]

    def test_deleting_the_last_feature_shows_the_one_before(self):
        delete.delete(self.pad3)
        self.doc.recompute()
        self.assertIs(self.body.Tip, self.pad2)
        self.assertEqual(self.shown(), ["PadB"])

    def test_deleting_a_middle_feature_keeps_the_tip_shown(self):
        delete.delete(self.pad2)
        self.doc.recompute()
        self.assertIs(self.body.Tip, self.pad3)
        self.assertEqual(self.shown(), ["PadC"])

    def test_deleting_a_sketch_keeps_the_tip_shown_and_only_it(self):
        delete.delete(self.doc.getObject("SkA")) if False else None  # a profile in use can't be deleted: use a free one
        free = self.body.newObject("Sketcher::SketchObject", "Free")
        free.Visibility = True
        self.doc.recompute()
        delete.delete(free)
        self.doc.recompute()
        self.assertEqual(self.shown(), ["PadC"])
