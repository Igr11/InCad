"""Text on a gear (the user: Emboss and Extrude Cut did nothing with a text written on a gear): the gear stands in a
Solid of its own; Cut, Auto and Emboss's Engrave on its face change that gear, never another Solid, and the Text's
Solid is found through the sketch it is written in."""
import unittest

import FreeCAD as App
from incad.core import document, sketch
from incad.features import emboss, extrude, gear
from incad.features import sketch_text as T
from headless import util


class TextOnGearTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Tg")
        body = document.make_part(self.doc)
        self.doc.recompute()
        k = gear.SPUR_GEARS
        lead = k.create(self.doc, body, None, dict(k.defaults(self.doc, body), teeth="30"))
        self.doc.recompute()
        self.g = gear.second_of(lead)  # in a Solid of its own
        self.body = self.g.getParentGeoFeatureGroup()
        top = [i + 1 for i, f in enumerate(self.g.Shape.Faces) if f.Surface.TypeId == "Part::GeomPlane"
               and abs(f.CenterOfMass.z - 10) < 1e-6][0]
        self.face = "%s:Face%d" % (self.g.Name, top)
        sk = sketch.make_sketch(self.body, self.g, "Face%d" % top)
        c = self.g.Shape.BoundBox.Center
        T._pending_box = (App.Vector(c.x + 12, c.y - 5, 0), App.Vector(c.x + 32, c.y + 5, 0))
        self.text = T.create(self.doc, self.body, sk, dict(T.defaults(self.doc, self.body, sk), text="AB",
                                                            size="4 mm"))
        self.doc.recompute()
        self.before = self.body.Shape.Volume
        self.bodies = len(document.bodies(self.doc))

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_the_text_goes_by_its_sketch(self):
        self.assertIs(document.target_body(self.text), self.body)

    def test_cut_and_auto(self):
        for op, more in (("cut", False), ("auto", True)):
            f = extrude.create(self.doc, document.target_body(self.text), self.text,
                               dict(extrude.defaults(self.doc, self.body, self.text), operation=op, distance="1 mm"))
            self.doc.recompute()
            self.assertIs(f.getParentGeoFeatureGroup(), self.body, op)
            self.assertNotIn("Invalid", f.State, f.getStatusString())
            vol = self.body.Shape.Volume
            self.assertTrue(vol > self.before + 1 if more else vol < self.before - 1, (op, self.before, vol))
            self.assertEqual(len(document.bodies(self.doc)), self.bodies, "no Solid of its own")
            self.body.Tip = self.g
            self.doc.removeObject(f.Name)
            self.doc.recompute()

    def test_engrave(self):
        e = emboss.create(self.doc, self.body, self.text, dict(emboss.defaults(self.doc, self.body, self.text),
                                                                 operation="engrave", face=self.face))
        self.doc.recompute()
        self.assertNotIn("Invalid", e.State, e.getStatusString())
        self.assertLess(self.body.Shape.Volume, self.before - 1)


if __name__ == "__main__":
    unittest.main()
