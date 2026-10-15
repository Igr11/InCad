"""Emboss geometry (incad.core.wrap): a profile wrapped onto a cylinder and raised or engraved along the radius,
reading the right way round from outside; a plane through the axis; a tilted sketch and letters off the face
refused; a straight emboss on a flat face."""
import math
import unittest

import FreeCAD as App
import Part
from incad.core import sketch_text as st
from incad.core import wrap

R, H = 10.0, 30.0


def text(words, corners, size=5.0):
    """Letter faces in a plane given by its frame: corners in (s, t) of that plane, mapped by `frame`."""
    return st.in_box(words, st.font_path("Arial", bold=True), size, corners)


def placed(faces, placement):
    out = []
    for f in faces:
        g = f.copy()
        g.Placement = placement.multiply(g.Placement)
        out.append(g)
    return out


BOX = [App.Vector(-14, 10, 0), App.Vector(14, 10, 0), App.Vector(14, 20, 0), App.Vector(-14, 20, 0)]
# a plane touching the cylinder at +X: the sketch's X runs along +Y, its Y along +Z, its normal +X
TANGENT = App.Placement(App.Vector(R, 0, 0), App.Rotation(App.Vector(0, 1, 0), App.Vector(0, 0, 1), App.Vector(1, 0, 0),
                                                          "ZXY"))


class WrapTest(unittest.TestCase):
    def setUp(self):
        self.cyl = Part.makeCylinder(R, H)
        self.side = next(f for f in self.cyl.Faces if wrap.is_round(f))

    def letters(self, words="HELLO", placement=TANGENT, corners=BOX):
        faces = placed(text(words, corners), placement)
        self.assertAlmostEqual(faces[0].normalAt(0, 0).x, 1.0, delta=1e-6, msg="the test's sketch faces +X")
        return faces

    def test_raised_on_the_cylinder_along_the_radius(self):
        out = wrap.apply(self.cyl, self.letters(), self.side, 1.0, engrave=False)
        self.assertTrue(out.isValid())
        self.assertEqual(len(out.Solids), 1)
        rmax = max(math.hypot(v.Point.x, v.Point.y) for v in out.Vertexes)
        self.assertAlmostEqual(rmax, R + 1.0, delta=1e-4)
        self.assertGreater(out.Volume, self.cyl.Volume + 10)

    def test_engraved_into_the_cylinder(self):
        out = wrap.apply(self.cyl, self.letters(), self.side, 0.6, engrave=True)
        self.assertTrue(out.isValid())
        self.assertLess(out.Volume, self.cyl.Volume - 5)
        self.assertGreater(min(math.hypot(v.Point.x, v.Point.y) for v in out.Vertexes), R - 0.6 - 1e-4)

    def test_reads_left_to_right_from_outside(self):
        letters = wrap.tools(self.letters("HL"), self.side, 1.0)
        h, l = letters[0].CenterOfMass, letters[1].CenterOfMass
        self.assertGreater(h.x, 0, "on the side facing the sketch")
        self.assertLess(h.y, l.y, "seen from +X (up = +Z) the text runs towards +Y: not mirrored")

    def test_the_letters_keep_their_width_round_the_axis(self):
        flat = self.letters("HHHHH")
        width = Part.makeCompound(flat).BoundBox.YLength
        wrapped = wrap.tools(flat, self.side, 0.01)
        angles = [math.atan2(v.Point.y, v.Point.x) for s in wrapped for v in s.Vertexes]
        arc = (max(angles) - min(angles)) * R
        self.assertAlmostEqual(arc, width, delta=0.05)

    def test_a_plane_through_the_axis(self):
        through = App.Placement(App.Vector(0, 0, 0), TANGENT.Rotation)
        out = wrap.apply(self.cyl, self.letters(placement=through), self.side, 1.0, engrave=False)
        self.assertTrue(out.isValid() and len(out.Solids) == 1)

    def test_a_tilted_sketch_is_refused(self):
        tilted = App.Placement(App.Vector(R, 0, 0), App.Rotation(App.Vector(0, 0, 1), 0).multiply(
            App.Rotation(App.Vector(0, 1, 0), 30)).multiply(TANGENT.Rotation))
        faces = placed(text("HI", BOX), tilted)
        with self.assertRaises(ValueError) as ctx:
            wrap.apply(self.cyl, faces, self.side, 1.0, engrave=False)
        self.assertIn("parallel", str(ctx.exception))

    def test_letters_past_the_end_are_refused(self):
        high = [App.Vector(-14, 26, 0), App.Vector(14, 26, 0), App.Vector(14, 36, 0), App.Vector(-14, 36, 0)]
        with self.assertRaises(ValueError):
            wrap.apply(self.cyl, self.letters(corners=high), self.side, 1.0, engrave=False)

    def test_straight_emboss_on_a_flat_face(self):
        box = Part.makeBox(40, 20, 10)
        top = next(f for f in box.Faces if abs(f.CenterOfMass.z - 10) < 1e-6)
        faces = placed(text("OK", [App.Vector(5, 5, 0), App.Vector(35, 5, 0), App.Vector(35, 15, 0),
                                   App.Vector(5, 15, 0)]), App.Placement(App.Vector(0, 0, 10), App.Rotation()))
        out = wrap.apply(box, faces, top, 1.5, engrave=False)
        self.assertTrue(out.isValid() and len(out.Solids) == 1)
        self.assertAlmostEqual(out.BoundBox.ZMax, 11.5, delta=1e-6)


class EmbossFeatureTest(unittest.TestCase):
    """The Emboss step in a part: a Text on a sketch touching a cylinder raised round it, its depth and Engrave
    edited, and the cylinder made bigger afterwards (the emboss follows it)."""
    def setUp(self):
        from incad.core import document
        from headless import util
        self.doc = util.new_doc("Em")
        self.body = document.make_part(self.doc)
        self.cyl = self.body.newObject("PartDesign::AdditiveCylinder", "Drum")
        self.cyl.Radius, self.cyl.Height = R, H
        self.body.Tip = self.cyl
        self.sk = self.body.newObject("Sketcher::SketchObject", "Label")
        self.sk.MapMode = "Deactivated"
        self.sk.Placement = TANGENT
        self.doc.recompute()
        from incad.features import sketch_text as T
        T._pending_box = (App.Vector(-14, 10, 0), App.Vector(14, 20, 0))
        self.text = T.create(self.doc, self.body, self.sk, dict(T.defaults(self.doc, self.body, self.sk),
                                                                text="DRUM", size="5 mm"))
        self.side = "Face%d" % next(i + 1 for i, f in enumerate(self.cyl.Shape.Faces) if wrap.is_round(f))

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_raised_edited_engraved_and_following_the_cylinder(self):
        from incad.features import emboss, kind_for
        f = emboss.create(self.doc, self.body, self.text, dict(emboss.defaults(self.doc, self.body),
                                                                face="%s:%s" % (self.cyl.Name, self.side)))
        self.assertNotIn("Invalid", f.State, f.getStatusString())
        self.assertIs(kind_for(f), emboss)
        self.assertIs(self.body.Tip, f)
        rmax = lambda: max(math.hypot(v.Point.x, v.Point.y) for v in f.Shape.Vertexes)
        self.assertAlmostEqual(rmax(), R + 1.0, delta=1e-4)
        v = emboss.read(self.doc, f)
        self.assertEqual((v["operation"], v["depth"], v["face"]), ("raise", "1 mm", "%s:%s" % (self.cyl.Name, self.side)))
        emboss.update(self.doc, f, dict(v, depth="2 mm"))
        self.assertAlmostEqual(rmax(), R + 2.0, delta=1e-4)
        emboss.update(self.doc, f, dict(v, operation="engrave", depth="0.5 mm"))
        self.assertLess(f.Shape.Volume, self.cyl.Shape.Volume - 3)
        self.cyl.Radius = R + 2  # an earlier step edited: the emboss finds its (bigger) cylinder again
        self.doc.recompute()
        self.assertNotIn("Invalid", f.State, f.getStatusString())
        self.assertAlmostEqual(f.Shape.BoundBox.XMax, R + 2, delta=1e-4)


if __name__ == "__main__":
    unittest.main()
