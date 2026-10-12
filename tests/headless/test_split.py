"""Split by sketch: sketch lines extruded into zero-thickness knives cut the part."""
import os
import tempfile
import unittest

import FreeCAD as App
import Part

from incad.core import document
from incad.features import split
from headless import util


def line_sketch(body, *segments, name="Knife"):
    """A sketch on XY with the given segments ((x1, y1), (x2, y2)); arcs as (centre, r, a0, a1)."""
    sk = body.newObject("Sketcher::SketchObject", name)
    sk.AttachmentSupport = [(util.xy_plane(body), "")]
    sk.MapMode = "FlatFace"
    for seg in segments:
        if len(seg) == 2:
            (x1, y1), (x2, y2) = seg
            sk.addGeometry(Part.LineSegment(App.Vector(x1, y1, 0), App.Vector(x2, y2, 0)))
        else:
            (cx, cy), r, a0, a1 = seg
            sk.addGeometry(Part.ArcOfCircle(Part.Circle(App.Vector(cx, cy, 0), App.Vector(0, 0, 1), r), a0, a1))
    return sk


class SplitTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Sp")
        self.body, self.pad = util.padded_part(self.doc, 10, incad=True)  # 20 x 10 x 10
        self.doc.recompute()

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def make(self, sk, **kw):
        values = dict(split.defaults(self.doc, self.body, None), sketch=sk.Name)
        values.update(kw)
        f = split.create(self.doc, self.body, None, values)
        self.doc.recompute()
        return f

    def test_a_line_through_the_box_gives_two_pieces(self):
        f = self.make(line_sketch(self.body, ((5, -5), (5, 15))))
        vols = sorted(round(s.Volume, 6) for s in f.Shape.Solids)
        self.assertEqual(vols, [500.0, 1500.0])
        self.assertIs(self.body.Tip, f)
        self.assertNotIn("Invalid", f.State)

    def test_an_arc_cuts_a_curved_face(self):
        import math
        f = self.make(line_sketch(self.body, ((0, 5), 8, -math.pi / 2, math.pi / 2)))
        self.assertEqual(len(f.Shape.Solids), 2)
        self.assertTrue(any(face.Surface.TypeId == "Part::GeomCylinder" for face in f.Shape.Faces))
        self.assertAlmostEqual(sum(s.Volume for s in f.Shape.Solids), 2000, places=6)

    def test_two_lines_give_three_pieces(self):
        f = self.make(line_sketch(self.body, ((5, -5), (5, 15)), ((15, -5), (15, 15))))
        self.assertEqual(len(f.Shape.Solids), 3)

    def test_cut_keeps_the_picked_piece(self):
        f = self.make(line_sketch(self.body, ((5, -5), (5, 15))), mode="cut", keep="2 1 5")
        self.assertEqual(len(f.Shape.Solids), 1)
        self.assertAlmostEqual(f.Shape.Volume, 500, places=6)

    def test_cut_follows_a_changed_sketch(self):
        sk = line_sketch(self.body, ((5, -5), (5, 15)))
        f = self.make(sk, mode="cut", keep="4.9 1 5")  # near the knife
        sk.delGeometry(0)  # the knife moves to x = 4: the kept spot (4.9) is now in the other piece's place
        sk.addGeometry(Part.LineSegment(App.Vector(4, -5, 0), App.Vector(4, 15, 0)))
        self.doc.recompute()
        self.assertEqual(len(f.Shape.Solids), 1)  # the piece holding the kept spot now, never nothing
        self.assertAlmostEqual(f.Shape.Volume, 1600, places=6)

    def test_a_sketch_missing_the_part_refuses(self):
        with self.assertRaises(ValueError) as ctx:
            self.make(line_sketch(self.body, ((50, -5), (50, 15))))
        self.assertIn("does not cut", str(ctx.exception))
        self.assertIs(self.body.Tip, self.pad)

    def test_a_line_ending_inside_refuses(self):
        with self.assertRaises(ValueError):
            self.make(line_sketch(self.body, ((5, -5), (5, 5))))  # stops in the middle

    def test_keep_piece_switches_to_cut(self):
        f = self.make(line_sketch(self.body, ((5, -5), (5, 15))))
        split.keep_piece(f, App.Vector(15, 5, 5))
        self.doc.recompute()
        self.assertEqual(f.Mode, "cut")
        self.assertAlmostEqual(f.Shape.Volume, 1500, places=6)

    def test_save_and_reopen(self):
        f = self.make(line_sketch(self.body, ((5, -5), (5, 15))))
        path = os.path.join(tempfile.mkdtemp(), "split.FCStd")
        self.doc.saveAs(path)
        name = f.Name
        App.closeDocument(self.doc.Name)
        self.doc = App.openDocument(path)
        g = self.doc.getObject(name)
        g.touch()
        self.doc.recompute()
        self.assertEqual(len(g.Shape.Solids), 2)
        self.assertTrue(split.claims(g))


if __name__ == "__main__":
    unittest.main()
