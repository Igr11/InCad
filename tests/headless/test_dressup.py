import unittest

import FreeCAD as App
from incad.core import model
from incad.features import common, dressup, kind_for
from headless import util


class DressUpTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Du")
        self.body, self.pad = util.padded_part(self.doc, 10, incad=True)
        self.top_edges = ["Edge%d" % (i + 1) for i, e in enumerate(self.pad.Shape.Edges)
                          if abs(e.BoundBox.ZMin - 10) < 1e-6 and abs(e.BoundBox.ZMax - 10) < 1e-6]
        self.top_face = [i + 1 for i, f in enumerate(self.pad.Shape.Faces) if abs(f.CenterOfMass.z - 10) < 1e-6][0]

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def edges(self):
        return common.format_picks([(self.pad, e) for e in self.top_edges])

    def test_fillet(self):
        k = dressup.FILLET
        f = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None), edges=self.edges(),
                                                     radius="2 mm"))
        self.doc.recompute()
        self.assertAlmostEqual(f.Shape.Volume, 1951.56, places=1)
        self.assertIs(kind_for(f), k)
        self.assertEqual(k.read(self.doc, f)["radius"], "2 mm")
        model.set_model_parameter(self.doc, model.bound_parameter(f, "Radius"), "1 mm")
        self.assertGreater(f.Shape.Volume, 1951.56)

    def test_chamfer_types(self):
        k = dressup.CHAMFER
        for kind, volume in (("equal", 1971.33), ("two", 1945.33), ("angle", 1983.12)):
            f = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None), edges=self.edges(),
                                                         type=kind, size="1 mm", size2="2 mm", angle="30"))
            self.doc.recompute()
            self.assertAlmostEqual(f.Shape.Volume, volume, places=1, msg=kind)
            self.assertEqual(k.read(self.doc, f)["type"], kind)
            self.body.removeObject(f)
            self.doc.removeObject(f.Name)
            self.body.Tip = self.pad
            self.doc.recompute()

    def test_shell_inside_and_outside(self):
        k = dressup.SHELL
        face = "%s:Face%d" % (self.pad.Name, self.top_face)
        f = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None), faces=face,
                                                     thickness="1 mm", direction="inside"))
        self.doc.recompute()
        self.assertAlmostEqual(f.Shape.BoundBox.XLength, 20, places=3)
        f = k.update(self.doc, f, dict(k.read(self.doc, f), direction="outside"))
        self.doc.recompute()
        self.assertAlmostEqual(f.Shape.BoundBox.XLength, 22, places=3)

    def test_needs_edges(self):
        k = dressup.FILLET
        with self.assertRaises(ValueError):
            k.create(self.doc, self.body, None, k.defaults(self.doc, self.body, None))
