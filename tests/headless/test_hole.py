import math
import unittest

import FreeCAD as App
import Part
from incad.core import document, model
from incad.features import hole, kind_for
from headless import util


class HoleTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Ho")
        self.body, self.pad = util.padded_part(self.doc, 10, incad=True)
        self.top = [i + 1 for i, f in enumerate(self.pad.Shape.Faces) if abs(f.CenterOfMass.z - 10) < 1e-6][0]

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def sketch_with_circle(self):
        sk = self.body.newObject("Sketcher::SketchObject", "Pts")
        sk.AttachmentSupport = [(self.pad, "Face%d" % self.top)]
        sk.MapMode = "FlatFace"
        sk.addGeometry(Part.Circle(App.Vector(10, 5, 0), App.Vector(0, 0, 1), 1))
        self.doc.recompute()
        return sk

    def test_from_sketch_through_all(self):
        sk = self.sketch_with_circle()
        v = dict(hole.defaults(self.doc, self.body, None), sketch=sk.Name, depth_type="through_all", diameter="4 mm")
        f = hole.create(self.doc, self.body, None, v)
        self.doc.recompute()
        self.assertEqual(f.TypeId, "PartDesign::Hole")
        self.assertIs(self.body.Tip, f)
        self.assertAlmostEqual(self.body.Shape.Volume, 2000 - math.pi * 4 * 10, places=2)
        self.assertIs(kind_for(f), hole)
        self.assertEqual(hole.read(self.doc, f)["diameter"], "4 mm")

    def test_counterbore(self):
        sk = self.sketch_with_circle()
        v = dict(hole.defaults(self.doc, self.body, None), sketch=sk.Name, type="counterbore", depth_type="through_all",
                 diameter="3 mm", cbore_diameter="6 mm", cbore_depth="2 mm")
        f = hole.create(self.doc, self.body, None, v)
        self.doc.recompute()
        self.assertEqual(f.HoleCutType, "Counterbore")
        self.assertAlmostEqual(2000 - self.body.Shape.Volume, math.pi * 1.5 ** 2 * 8 + math.pi * 9 * 2, places=1)

    def test_concentric_to_a_circular_edge(self):
        cyl_sk = self.body.newObject("Sketcher::SketchObject", "Boss")
        cyl_sk.AttachmentSupport = [(self.pad, "Face%d" % self.top)]
        cyl_sk.MapMode = "FlatFace"
        cyl_sk.addGeometry(Part.Circle(App.Vector(10, 5, 0), App.Vector(0, 0, 1), 3))
        boss = util.add_pad(self.body, cyl_sk, 5, name="BossPad")
        self.body.Tip = boss
        self.doc.recompute()
        top2 = [i + 1 for i, f in enumerate(boss.Shape.Faces) if abs(f.CenterOfMass.z - 15) < 1e-6][0]
        circle = [i + 1 for i, e in enumerate(boss.Shape.Edges)
                  if e.Curve.TypeId == "Part::GeomCircle" and abs(e.BoundBox.ZMax - 15) < 1e-6][0]
        v = dict(hole.defaults(self.doc, self.body, None), placement="concentric",
                 face="%s:Face%d" % (boss.Name, top2), edge="%s:Edge%d" % (boss.Name, circle),
                 diameter="2 mm", depth_type="distance", depth="4 mm")
        f = hole.create(self.doc, self.body, None, v)
        self.doc.recompute()
        self.assertEqual(f.State, ["Up-to-date"])
        c = f.Shape.BoundBox.Center
        self.assertLess(self.body.Shape.Volume, boss.Shape.Volume)
        self.assertAlmostEqual(hole.read(self.doc, f)["placement"], "concentric")

    def test_parameters(self):
        sk = self.sketch_with_circle()
        f = hole.create(self.doc, self.body, None, dict(hole.defaults(self.doc, self.body, None), sketch=sk.Name))
        self.doc.recompute()
        name = model.bound_parameter(f, "Diameter")
        model.set_model_parameter(self.doc, name, "5 mm")
        self.assertAlmostEqual(f.Diameter.Value, 5)

    def test_concentric_edit_moves_to_another_edge(self):
        boss_sk = self.body.newObject("Sketcher::SketchObject", "Bosses")
        boss_sk.AttachmentSupport = [(self.pad, "Face%d" % self.top)]
        boss_sk.MapMode = "FlatFace"
        boss_sk.addGeometry(Part.Circle(App.Vector(5, 5, 0), App.Vector(0, 0, 1), 2))
        boss_sk.addGeometry(Part.Circle(App.Vector(15, 5, 0), App.Vector(0, 0, 1), 2))
        boss = util.add_pad(self.body, boss_sk, 3, name="Bosses")
        self.body.Tip = boss
        self.doc.recompute()
        top2 = [i + 1 for i, f in enumerate(boss.Shape.Faces)
                if abs(f.CenterOfMass.z - 13) < 1e-6 and abs(f.CenterOfMass.x - 5) < 1e-6][0]
        top3 = [i + 1 for i, f in enumerate(boss.Shape.Faces)
                if abs(f.CenterOfMass.z - 13) < 1e-6 and abs(f.CenterOfMass.x - 15) < 1e-6][0]
        def circle(x):
            return [i + 1 for i, e in enumerate(boss.Shape.Edges) if e.Curve.TypeId == "Part::GeomCircle"
                    and abs(e.BoundBox.ZMax - 13) < 1e-6 and abs(e.Curve.Center.x - x) < 1e-6][0]
        v = dict(hole.defaults(self.doc, self.body, None), placement="concentric", diameter="1 mm",
                 face="%s:Face%d" % (boss.Name, top2), edge="%s:Edge%d" % (boss.Name, circle(5)),
                 depth_type="distance", depth="2 mm")
        f = hole.create(self.doc, self.body, None, v)
        self.doc.recompute()
        r = hole.read(self.doc, f)
        self.assertEqual((r["face"], r["edge"]), (v["face"], v["edge"]))
        f = hole.update(self.doc, f, dict(r, face="%s:Face%d" % (boss.Name, top3),
                                          edge="%s:Edge%d" % (boss.Name, circle(15))))
        self.doc.recompute()
        bores = [fc for fc in f.Shape.Faces if fc.Surface.TypeId == "Part::GeomCylinder"
                 and abs(fc.Surface.Radius - 0.5) < 1e-6]
        self.assertTrue(bores and all(abs(fc.Surface.Center.x - 15) < 1e-6 for fc in bores),
                        [fc.Surface.Center for fc in bores])

    def test_threaded_m8_with_clearance_and_back_to_plain(self):
        sk = self.sketch_with_circle()
        f = hole.create(self.doc, self.body, None, dict(hole.defaults(self.doc, self.body, None), sketch=sk.Name,
                                                        diameter="4 mm"))
        self.doc.recompute()
        plain_param = model.bound_parameter(f, "Diameter")
        v = dict(hole.read(self.doc, f), threaded=True, thread_standard="iso", thread_size="M8x1.25",
                 clearance="0.2 mm", depth_type="through_all")
        f = hole.update(self.doc, f, v)
        self.doc.recompute()
        self.assertTrue(f.Threaded and f.ModelThread)
        self.assertEqual(f.ThreadSize, "M8x1.25")
        self.assertTrue(f.UseCustomThreadClearance)
        self.assertAlmostEqual(f.CustomThreadClearance.Value, 0.2, places=6)
        self.assertNotIn("Invalid", f.State)
        r = hole.read(self.doc, f)
        self.assertEqual((r["threaded"], r["thread_standard"], r["thread_size"], r["clearance"]),
                         (True, "iso", "M8x1.25", "0.2 mm"))
        f = hole.update(self.doc, f, dict(r, threaded=False))
        self.doc.recompute()
        self.assertFalse(f.Threaded)
        self.assertEqual(model.bound_parameter(f, "Diameter"), plain_param)
        self.assertAlmostEqual(f.Diameter.Value, 4, places=6)

    def test_thread_size_options_follow_the_standard(self):
        sizes = [v for v, _ in hole.options("thread_size", {"thread_standard": "unc"})]
        self.assertIn("1/4", sizes)
        self.assertEqual(sizes[0], "")  # Auto
        self.assertIn("M8x1.25", [v for v, _ in hole.options("thread_size", {"thread_standard": "iso"})])
