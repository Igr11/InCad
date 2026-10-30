"""A chamfer wider than a face it runs onto stops at that face's far edge (incad.features.chamfer_fit)."""
import unittest

import FreeCAD as App
from incad.core import document, model
from incad.features import chamfer_fit, common, dressup
from headless import util


class ChamferFitTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Cf")
        self.body = document.make_part(self.doc)
        self.wall = util.add_pad(self.body, util.add_rect_sketch(self.body, w=20, h=2), 10)  # a 2 mm wall
        self.body.Tip = self.wall
        self.doc.recompute()

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def top_long(self, f):
        return ["Edge%d" % (i + 1) for i, e in enumerate(f.Shape.Edges)
                if abs(e.BoundBox.ZMin - 10) < 1e-6 and abs(e.BoundBox.ZMax - 10) < 1e-6 and e.Length > 10]

    def chamfer(self, size, edges=1):
        k = dressup.CHAMFER
        picks = common.format_picks([(self.wall, e) for e in self.top_long(self.wall)[:edges]])
        f = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None), edges=picks, size=size))
        self.doc.recompute()
        return f

    def shown(self):
        return self.body.Tip

    def test_a_chamfer_past_the_face_stops_at_its_far_edge(self):
        f = self.chamfer("2.5 mm")
        tip = self.shown()
        self.assertNotIn("Invalid", f.State, f.getStatusString())
        self.assertNotIn("Invalid", tip.State, tip.getStatusString())
        self.assertAlmostEqual(tip.Shape.Volume, 400 - 20 * 2 * 2 / 2, places=1)  # the top face taken whole
        self.assertTrue(tip.Shape.isValid())
        self.assertFalse([x for x in tip.Shape.Faces if x.Area < 0.01], "no hair-thin strip left")
        self.assertAlmostEqual(tip.Shape.BoundBox.ZMax, 10, places=3)
        self.assertEqual(dressup.CHAMFER.read(self.doc, f)["size"], "2.5 mm")  # the dialog keeps what was asked
        self.assertEqual(set(chamfer_fit.helpers(f)), {"fit", "trim"})

    def test_it_follows_the_value(self):
        f = self.chamfer("2.5 mm")
        name = model.bound_parameter(f, "Size")
        self.assertTrue(name)
        model.set_model_parameter(self.doc, name, "1 mm")
        self.doc.recompute()
        self.assertAlmostEqual(self.shown().Shape.Volume, 400 - 20 * 1 * 1 / 2, places=1)
        model.set_model_parameter(self.doc, name, "3 mm")
        self.doc.recompute()
        self.assertAlmostEqual(self.shown().Shape.Volume, 400 - 20 * 2 * 2 / 2, places=1)

    def test_two_chamfers_across_one_face_meet_halfway(self):
        self.chamfer("2 mm", edges=2)
        tip = self.shown()
        self.assertNotIn("Invalid", tip.State, tip.getStatusString())
        self.assertAlmostEqual(tip.Shape.Volume, 400 - 2 * (20 * 1 * 1 / 2), places=1)
        self.assertFalse([x for x in tip.Shape.Faces if x.Area < 0.01])

    def test_a_chamfer_that_fits_gets_no_steps(self):
        f = self.chamfer("0.5 mm")
        self.assertEqual(chamfer_fit.helpers(f), {})
        self.assertIs(self.shown(), f)
        self.assertAlmostEqual(f.Shape.Volume, 400 - 20 * 0.5 * 0.5 / 2, places=2)


if __name__ == "__main__":
    unittest.main()
