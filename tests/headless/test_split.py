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

    def pieces(self, f):
        """The Split's own piece and the Solids it made, as volumes (largest first)."""
        return sorted([round(s.Volume, 6) for s in f.Shape.Solids] +
                      [round(b.Shape.Volume, 6) for b in split.piece_bodies(f)], reverse=True)

    def test_keep_all_puts_every_other_piece_in_its_own_solid(self):
        """The user: with both pieces in one Solid, Hide / Show could not hide one of them (Inventor's Split Solid
        makes separate bodies)."""
        f = self.make(line_sketch(self.body, ((5, -5), (5, 15))))
        self.assertEqual(len(f.Shape.Solids), 1)
        self.assertAlmostEqual(f.Shape.Volume, 1500, places=6)  # the largest stays in this Solid
        others = split.piece_bodies(f)
        self.assertEqual(len(others), 1)
        self.assertIsNot(others[0], self.body)
        self.assertAlmostEqual(others[0].Shape.Volume, 500, places=6)
        self.assertIs(self.body.Tip, f)
        self.assertFalse([o.Name for o in self.doc.Objects if "Invalid" in o.State])

    def test_a_piece_solid_follows_the_sketch(self):
        sk = line_sketch(self.body, ((5, -5), (5, 15)))
        f = self.make(sk)
        sk.delGeometry(0)
        sk.addGeometry(Part.LineSegment(App.Vector(4, -5, 0), App.Vector(4, 15, 0)))
        self.doc.recompute()
        self.assertEqual(self.pieces(f), [1600.0, 400.0])

    def test_a_pad_on_a_piece_solid_stays_in_it(self):
        f = self.make(line_sketch(self.body, ((5, -5), (5, 15))))
        other = split.piece_bodies(f)[0]
        top = util.add_rect_sketch(other, w=2, h=2, name="Bump")
        top.AttachmentOffset = App.Placement(App.Vector(1, 1, 10), App.Rotation())
        bump = util.add_pad(other, top, 3, name="BumpPad")
        other.Tip = bump
        self.doc.recompute()
        self.assertAlmostEqual(other.Shape.Volume, 500 + 12, places=6)
        self.assertAlmostEqual(f.Shape.Volume, 1500, places=6)  # nothing fused back

    def test_keep_all_reads_no_picks(self):
        """GUI: the Split's own piece point came back as a Keep pick, so switching to Keep picked did not start
        picking."""
        f = self.make(line_sketch(self.body, ((5, -5), (5, 15))))
        self.assertEqual(split.read(self.doc, f)["keep"], "")

    def test_switching_to_keep_picked_removes_the_piece_solids(self):
        f = self.make(line_sketch(self.body, ((5, -5), (5, 15))))
        split.update(self.doc, f, dict(split.read(self.doc, f), mode="cut", keep="2 1 5"))
        self.doc.recompute()
        self.assertEqual(split.piece_bodies(f), [])
        self.assertEqual(len(document.bodies(self.doc)), 1)

    def test_an_arc_cuts_a_curved_face(self):
        import math
        f = self.make(line_sketch(self.body, ((0, 5), 8, -math.pi / 2, math.pi / 2)))
        self.assertEqual(len(self.pieces(f)), 2)
        self.assertTrue(any(face.Surface.TypeId == "Part::GeomCylinder" for face in f.Shape.Faces))
        self.assertAlmostEqual(sum(self.pieces(f)), 2000, places=6)

    def test_two_lines_give_three_pieces(self):
        f = self.make(line_sketch(self.body, ((5, -5), (5, 15)), ((15, -5), (15, 15))))
        self.assertEqual(self.pieces(f), [1000.0, 500.0, 500.0])
        self.assertEqual(len(split.piece_bodies(f)), 2)

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
        split.keep_piece(f, App.Vector(2, 5, 5))
        self.doc.recompute()
        self.assertEqual(f.Mode, "cut")
        self.assertAlmostEqual(f.Shape.Volume, 500, places=6)

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
        self.assertEqual(self.pieces(g), [1500.0, 500.0])  # the piece Solid's proxy is found too
        self.assertFalse([o.Name for o in self.doc.Objects if "Invalid" in o.State])
        self.assertTrue(split.claims(g))


    def test_the_knife_sketch_is_used_by_the_split(self):
        """Review: the knife counted as an unused sketch, so it was shown again after OK."""
        from incad.features import common
        sk = line_sketch(self.body, ((5, -5), (5, 15)))
        f = self.make(sk)
        self.assertIn(f, common.consumers(sk))

    def test_edit_reads_the_keep_picks_back(self):
        """Review: read() gave 'x y z' numbers, so the first click while editing replaced every kept piece."""
        f = self.make(line_sketch(self.body, ((5, -5), (5, 15))))
        big = max(f.Shape.Solids, key=lambda s: s.Volume)
        face = next(i + 1 for i, fc in enumerate(f.Shape.Faces) if big.isInside(fc.CenterOfMass, 1e-6, True))
        pick = "%s:Face%d" % (f.Name, face)
        split.update(self.doc, f, dict(split.read(self.doc, f), mode="cut", keep=pick))
        self.assertEqual(split.read(self.doc, f)["keep"], pick)


    def test_deleting_the_split_takes_its_empty_piece_solids_and_freezes_worked_ones(self):
        from incad.core import delete
        f = self.make(line_sketch(self.body, ((5, -5), (5, 15)), ((15, -5), (15, 15))))
        empty, worked = split.piece_bodies(f)
        top = util.add_rect_sketch(worked, w=2, h=2, name="Bump")
        top.AttachmentOffset = App.Placement(App.Vector(16, 1, 10), App.Rotation())
        worked.Tip = util.add_pad(worked, top, 3, name="BumpPad")
        self.doc.recompute()
        before = worked.Shape.Volume
        empty_name, worked_name = empty.Name, worked.Name
        delete.delete(f)
        self.doc.recompute()
        self.assertIsNone(self.doc.getObject(empty_name))
        self.assertIsNotNone(self.doc.getObject(worked_name))
        self.assertAlmostEqual(worked.Shape.Volume, before, places=6)  # its piece kept, frozen
        self.assertFalse([o.Name for o in self.doc.Objects if "Invalid" in o.State or o.TypeId == "Part::FeaturePython"])

    def test_deleting_a_piece_solid_takes_its_piece(self):
        from incad.core import delete
        f = self.make(line_sketch(self.body, ((5, -5), (5, 15))))
        other = split.piece_bodies(f)[0]
        delete.delete(other)
        self.doc.recompute()
        self.assertFalse([o.Name for o in self.doc.Objects if o.TypeId == "Part::FeaturePython"])
        self.assertFalse([o.Name for o in self.doc.Objects if "Invalid" in o.State])


    def test_an_old_split_gets_its_piece_solids(self):
        """A file from before Keep all made piece Solids: both pieces in the Split's Solid until it is upgraded."""
        f = self.make(line_sketch(self.body, ((5, -5), (5, 15))))
        for b in split.piece_bodies(f):  # back to the old state: no piece Solids, no kept point
            split._drop_piece_body(self.doc, b)
        f.Keep = []
        self.doc.recompute()
        self.assertEqual(len(f.Shape.Solids), 2)
        self.assertEqual(split.upgrade(self.doc), [f])
        self.assertEqual(len(f.Shape.Solids), 1)
        self.assertEqual(len(split.piece_bodies(f)), 1)
        self.assertEqual(split.upgrade(self.doc), [])


    def test_a_piece_solid_used_by_a_boolean_is_not_deleted(self):
        """The user's Thread_1: Solid2 was the tool of a Cut; deleting it broke the Cut ('No source shape linked')."""
        from incad.core import delete
        from incad.features import combine
        f = self.make(line_sketch(self.body, ((5, -5), (5, 15))))
        tool = split.piece_bodies(f)[0]
        cut = combine.create(self.doc, self.body, None, dict(combine.defaults(self.doc, self.body, None),
                                                             base=self.body.Name, tools=tool.Name, keep_tool=True))
        self.doc.recompute()
        with self.assertRaises(ValueError) as ctx:
            delete.delete(tool)
        self.assertIn(cut.Label, str(ctx.exception))
        self.assertIsNotNone(self.doc.getObject(tool.Name))
        self.assertFalse([o.Name for o in self.doc.Objects if "Invalid" in o.State])


if __name__ == "__main__":
    unittest.main()
