"""A cut or join through a modeled thread goes before the thread (incad.core.thread_order). The user's part: a slot
drawn over a tapped Hole's rim, revolved around the sketch's vertical axis (gui/data/p2_test.FCStd)."""
import os
import shutil
import tempfile
import unittest

import FreeCAD as App
import Part
from incad.core import thread_order

DATA = os.path.join(os.path.dirname(__file__), "..", "gui", "data", "p2_test.FCStd")


class ThreadOrderUserPartTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        path = os.path.join(self.tmp, "p2_test.FCStd")
        shutil.copy(os.path.abspath(DATA), path)
        self.doc = App.openDocument(path)
        self.body = self.doc.Body
        self.sk = self.doc.Sketch004  # Sketch5: the slot, on ThreadChamfer's face, projecting its Edge13
        self.before = self.body.Tip.Shape.Volume

    def tearDown(self):
        App.closeDocument(self.doc.Name)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _revolve(self, kind):
        f = self.body.newObject(kind, "Revolve")
        f.Profile = self.sk
        f.ReferenceAxis = (self.sk, ["V_Axis"])
        f.Angle = 360
        self.doc.recompute()
        return f

    def _settled(self, f):
        self.assertIs(thread_order.crossed_thread(f), self.doc.Hole)
        self.assertTrue(thread_order.broken(f))  # the kernel: an invalid cut, a join that keeps only the ring
        self.assertEqual(thread_order.settle(f), "Hole")
        self.doc.recompute()
        group = list(self.body.Group)
        self.assertLess(group.index(self.sk), group.index(f))
        self.assertEqual(group.index(f) + 1, group.index(self.doc.Hole))
        self.assertIs(f.BaseFeature, self.doc.Extrude001)
        self.assertIs(self.body.Tip, self.doc.ThreadChamfer)
        self.assertIs(self.sk.AttachmentSupport[0][0], self.doc.Extrude001)  # the same face, as it is there
        self.assertEqual(list(self.sk.ExternalGeometry), [])  # the hole's rim only exists after the Hole
        self.assertFalse([o.Name for o in self.body.Group if "Invalid" in o.State])
        tip = self.body.Tip.Shape
        self.assertTrue(tip.isValid())
        self.assertGreater(sum(1 for face in tip.Faces if face.Surface.TypeId == "Part::GeomBSplineSurface"), 130)
        return tip

    def test_cut_through_a_tapped_hole_goes_before_it(self):
        tip = self._settled(self._revolve("PartDesign::Groove"))
        self.assertLess(tip.Volume, self.before - 100)

    def test_join_through_a_tapped_hole_goes_before_it(self):
        tip = self._settled(self._revolve("PartDesign::Revolution"))
        self.assertGreater(tip.Volume, self.before + 100)


class ThreadOrderPlainTest(unittest.TestCase):
    def test_a_part_without_threads_is_left_as_it_is(self):
        doc = App.newDocument("NoThread")
        try:
            body = doc.addObject("PartDesign::Body", "Body")
            xz = [f for f in body.Origin.OriginFeatures if f.Role == "XZ_Plane"][0]
            sk = body.newObject("Sketcher::SketchObject", "Sketch")
            sk.AttachmentSupport = [(xz, "")]
            sk.MapMode = "FlatFace"
            pts = [(2, 0), (6, 0), (6, 4), (2, 4)]
            for i in range(4):
                a, b = pts[i], pts[(i + 1) % 4]
                sk.addGeometry(Part.LineSegment(App.Vector(a[0], a[1], 0), App.Vector(b[0], b[1], 0)))
            f = body.newObject("PartDesign::Revolution", "Revolve")
            f.Profile = sk
            f.ReferenceAxis = (sk, ["V_Axis"])
            doc.recompute()
            self.assertIsNone(thread_order.crossed_thread(f))
            self.assertIsNone(thread_order.settle(f))
            self.assertIs(body.Tip, f)
        finally:
            App.closeDocument(doc.Name)


if __name__ == "__main__":
    unittest.main()
