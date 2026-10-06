import math
import unittest

import FreeCAD as App
import Part
from incad.core import document, model
from incad.features import combine, common, kind_for
from headless import util

BLOCK = 40 * 30 * 10


class CombineTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Cb")
        self.base = document.make_part(self.doc)
        sk = util.add_rect_sketch(self.base, 40, 30, "BlockSk")
        self.block = util.add_pad(self.base, sk, 10, "Block")
        self.base.Tip = self.block
        self.tool = self.doc.addObject("PartDesign::Body", "Pin")
        sk2 = self.tool.newObject("Sketcher::SketchObject", "PinSk")
        sk2.AttachmentSupport = [(util.xy_plane(self.tool), "")]
        sk2.MapMode = "FlatFace"
        sk2.addGeometry(Part.Circle(App.Vector(20, 15, 0), App.Vector(0, 0, 1), 4))
        self.pin = util.add_pad(self.tool, sk2, 20, "PinPad")
        self.tool.Tip = self.pin
        self.doc.recompute()

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def make(self, **values):
        v = dict(combine.defaults(self.doc, self.base, None), base=self.base.Name, tools=self.tool.Name)
        v.update(values)
        f = combine.create(self.doc, self.base, None, v)
        self.doc.recompute()
        return f

    def fit(self):
        return [b for b in document.bodies(self.doc) if b.Label == "Pin fit"]

    def test_cut_with_clearance_on_the_cavity(self):
        f = self.make(operation="cut", clearance="0.2 mm", apply_to="cavity")
        self.assertEqual(f.TypeId, "PartDesign::Boolean")
        self.assertAlmostEqual(f.Shape.Volume, BLOCK - math.pi * 4.2 ** 2 * 10, places=1)
        self.assertAlmostEqual(self.tool.Shape.Volume, math.pi * 16 * 20, places=1)  # tool kept, unchanged
        self.assertFalse(self.tool.Visibility)
        self.assertIs(self.base.Tip, f)
        self.assertIs(kind_for(f), combine)
        self.assertEqual(self.fit(), [])

    def test_clearance_on_a_fit_copy_of_the_tool(self):
        f = self.make(operation="cut", clearance="0.2 mm", apply_to="tool")
        self.assertAlmostEqual(f.Shape.Volume, BLOCK - math.pi * 16 * 10, places=1)
        fit = self.fit()
        self.assertEqual(len(fit), 1)
        self.assertAlmostEqual(fit[0].Shape.Volume, math.pi * 3.8 ** 2 * 19.6, places=1)

    def test_split(self):
        f = self.make(operation="cut", clearance="0.2 mm", apply_to="split")
        self.assertAlmostEqual(f.Shape.Volume, BLOCK - math.pi * 4.1 ** 2 * 10, places=1)
        self.assertAlmostEqual(self.fit()[0].Shape.Volume, math.pi * 3.9 ** 2 * 19.8, places=1)

    def test_parameter_drives_cavity_and_fit(self):
        f = self.make(operation="cut", clearance="0.2 mm", apply_to="split")
        name = combine.clearance_parameter(f)
        model.set_model_parameter(self.doc, name, "0.4 mm")
        self.assertAlmostEqual(f.Shape.Volume, BLOCK - math.pi * 4.2 ** 2 * 10, places=1)
        self.assertAlmostEqual(self.fit()[0].Shape.Volume, math.pi * 3.8 ** 2 * 19.6, places=1)

    def test_join_and_intersect(self):
        f = self.make(operation="join")
        self.assertAlmostEqual(f.Shape.Volume, BLOCK + math.pi * 16 * 10, places=1)
        f = combine.update(self.doc, f, dict(combine.read(self.doc, f), operation="intersect"))
        self.doc.recompute()
        self.assertAlmostEqual(f.Shape.Volume, math.pi * 16 * 10, places=1)

    def test_edit_removes_unused_helpers(self):
        f = self.make(operation="cut", clearance="0.2 mm", apply_to="split")
        before = {o.Name for o in self.doc.Objects}
        f = combine.update(self.doc, f, dict(combine.read(self.doc, f), apply_to="cavity"))
        self.doc.recompute()
        self.assertEqual(self.fit(), [])
        self.assertTrue({o.Name for o in self.doc.Objects} < before)
        self.assertAlmostEqual(f.Shape.Volume, BLOCK - math.pi * 4.2 ** 2 * 10, places=1)
        r = combine.read(self.doc, f)
        self.assertEqual((r["operation"], r["apply_to"], r["clearance"], r["tools"]),
                         ("cut", "cavity", "0.2 mm", self.tool.Name))

    def test_base_cannot_be_a_tool(self):
        with self.assertRaises(ValueError) as ctx:
            self.make(tools=self.base.Name)
        self.assertIn("other solid", str(ctx.exception))

    def test_face_pick_means_its_body(self):
        top = [i + 1 for i, fc in enumerate(self.pin.Shape.Faces) if abs(fc.CenterOfMass.z - 20) < 1e-6][0]
        pair = (self.tool, "%s.Face%d" % (self.pin.Name, top))
        self.assertTrue(common.accepts("body", *common.resolve(*pair)))
        self.assertEqual(combine.body_of(*common.resolve(*pair)), self.tool)

    def test_tool_edit_updates_the_result(self):
        f = self.make(operation="cut", clearance="0 mm", apply_to="cavity")
        sk = self.pin.Profile[0]
        sk.delGeometry(0)
        sk.addGeometry(Part.Circle(App.Vector(20, 15, 0), App.Vector(0, 0, 1), 5))
        self.doc.recompute()
        self.assertAlmostEqual(f.Shape.Volume, BLOCK - math.pi * 25 * 10, places=1)
