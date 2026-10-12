"""Make Assembly: a part's separate pieces become part files with their history, linked by an assembly."""
import os
import tempfile
import unittest

import FreeCAD as App
import Part

from incad.core import assembly, document, make_assembly as ma
from headless import util


def _close_all():
    for name in list(App.listDocuments()):
        App.closeDocument(name)


class MakeAssemblyTest(unittest.TestCase):
    def setUp(self):
        _close_all()
        self.dir = tempfile.mkdtemp()
        self.doc = util.new_doc("Mk")
        self.body, self.pad = util.padded_part(self.doc, 10, incad=True)  # 20 x 10 x 10 = 2000
        far = util.add_rect_sketch(self.body, w=10, h=10, name="FarSk")
        far.AttachmentOffset = App.Placement(App.Vector(50, 0, 0), App.Rotation())
        self.box = util.add_pad(self.body, far, 5, name="Box")  # 500, separate
        self.body.Tip = self.box
        self.doc.recompute()
        self.path = os.path.join(self.dir, "Plate.FCStd")
        self.doc.saveAs(self.path)

    def tearDown(self):
        _close_all()

    def test_pieces_largest_first(self):
        found = ma.pieces(self.doc)
        self.assertEqual([round(p.volume) for p in found], [2000, 500])

    def test_default_names(self):
        self.assertEqual(ma.default_names(self.doc, 2), ("Plate-Assembly", ["Plate-Solid1", "Plate-Solid2"]))

    def test_two_part_files_with_history_and_an_assembly(self):
        asm_path = ma.make(self.doc, "Plate-Assembly", ["Plate-Solid1", "Plate-Solid2"])
        self.assertEqual(asm_path, os.path.join(self.dir, "Plate-Assembly.FCStd"))
        self.assertEqual([d.Name for d in App.listDocuments().values()], [self.doc.Name],
                         "no copy or assembly is left open (hidden) after Make Assembly")
        self.assertFalse([f for f in os.listdir(self.dir) if f.endswith(".FCBak")], "no backup files left behind")
        _close_all()
        vols = []
        for name, has in (("Plate-Solid1", "Pad"), ("Plate-Solid2", "Box")):
            d = App.openDocument(os.path.join(self.dir, name + ".FCStd"))
            d.recompute()
            body = document.primary_body(d)
            self.assertIsNotNone(body, name)
            self.assertEqual(len(body.Shape.Solids), 1, name)
            self.assertFalse([o.Name for o in d.Objects if "Invalid" in o.State], name)
            self.assertIsNotNone(d.getObject(has), "history kept in %s" % name)
            vols.append(round(body.Shape.Volume))
            App.closeDocument(d.Name)
        self.assertEqual(vols, [2000, 500])
        a = App.openDocument(asm_path)
        a.recompute()
        comps = assembly.components(a)
        self.assertEqual(len(comps), 2)
        self.assertTrue(assembly.is_grounded(comps[0]))
        self.assertAlmostEqual(comps[1].Shape.BoundBox.XMin, 50, places=6)  # where it was

    def test_the_original_file_is_unchanged(self):
        before = os.path.getmtime(self.path)
        ma.make(self.doc, "Plate-Assembly", ["Plate-Solid1", "Plate-Solid2"])
        self.assertEqual(os.path.getmtime(self.path), before)
        self.assertEqual(len(self.body.Shape.Solids), 2)

    def test_each_copy_is_an_incad_part_with_its_piece_as_primary(self):
        ma.make(self.doc, "Plate-Assembly", ["Plate-Solid1", "Plate-Solid2"])
        _close_all()
        d = App.openDocument(os.path.join(self.dir, "Plate-Solid2.FCStd"))
        self.assertTrue(document.is_incad_part(d))
        self.assertEqual(len(document.bodies(d)), 1)
        self.assertIs(document.primary_body(d), document.bodies(d)[0])

    def test_an_existing_file_is_refused(self):
        open(os.path.join(self.dir, "Plate-Solid2.FCStd"), "w").close()
        self.assertIn("exists", ma.check_names(self.doc, "Plate-Assembly", ["Plate-Solid1", "Plate-Solid2"]))
        with self.assertRaises(ValueError):
            ma.make(self.doc, "Plate-Assembly", ["Plate-Solid1", "Plate-Solid2"])
        self.assertFalse(os.path.exists(os.path.join(self.dir, "Plate-Solid1.FCStd")))

    def test_duplicate_names_are_refused(self):
        self.assertIn("twice", ma.check_names(self.doc, "Plate-Assembly", ["Plate-Solid1", "Plate-Solid1"]))

    def test_a_one_piece_part_is_refused(self):
        d = util.new_doc("One")
        util.padded_part(d, 10, incad=True)
        d.recompute()
        d.saveAs(os.path.join(self.dir, "One.FCStd"))
        with self.assertRaises(ValueError) as ctx:
            ma.make(d, "One-Assembly", ["One-Solid1"])
        self.assertIn("one piece", str(ctx.exception))

    def test_an_unsaved_part_is_refused(self):
        d = util.new_doc("Unsaved")
        util.padded_part(d, 10, incad=True)
        with self.assertRaises(ValueError) as ctx:
            ma.pieces_or_refuse(d)
        self.assertIn("Save", str(ctx.exception))

    def test_a_failure_removes_the_files_made(self):
        original = ma._finish_copy
        def broken(*a, **kw):
            raise ValueError("boom")
        ma._finish_copy = broken
        try:
            with self.assertRaises(ValueError):
                ma.make(self.doc, "Plate-Assembly", ["Plate-Solid1", "Plate-Solid2"])
        finally:
            ma._finish_copy = original
        self.assertEqual(sorted(os.listdir(self.dir)), ["Plate.FCStd"])

    def test_a_split_box_gives_two_parts_each_keeping_one_piece(self):
        from incad.features import split
        d = util.new_doc("Sb")
        body, pad = util.padded_part(d, 10, incad=True)
        sk = body.newObject("Sketcher::SketchObject", "Knife")
        sk.AttachmentSupport = [(util.xy_plane(body), "")]
        sk.MapMode = "FlatFace"
        sk.addGeometry(Part.LineSegment(App.Vector(5, -5, 0), App.Vector(5, 15, 0)))
        d.recompute()
        split.create(d, body, None, dict(split.defaults(d, body, None), sketch=sk.Name))
        d.recompute()
        d.saveAs(os.path.join(self.dir, "Sb.FCStd"))
        ma.make(d, "Sb-Assembly", ["Sb-Solid1", "Sb-Solid2"])
        _close_all()
        vols = []
        for name in ("Sb-Solid1", "Sb-Solid2"):
            p = App.openDocument(os.path.join(self.dir, name + ".FCStd"))
            p.recompute()
            b = document.primary_body(p)
            self.assertEqual(len(b.Shape.Solids), 1)
            vols.append(round(b.Shape.Volume))
            App.closeDocument(p.Name)
        self.assertEqual(vols, [1500, 500])


class MakeAssemblyReviewTest(unittest.TestCase):
    """The whole-branch review of 2026-10-12: Booleans' tools, failures, features after a Split, lumps and Splits."""

    def setUp(self):
        _close_all()
        self.dir = tempfile.mkdtemp()

    def tearDown(self):
        _close_all()

    def _part(self, name):
        d = util.new_doc(name)
        body, pad = util.padded_part(d, 10, incad=True)  # 20 x 10 x 10
        d.recompute()
        return d, body, pad

    def _knife(self, body, x, y0=-5, y1=15):
        sk = body.newObject("Sketcher::SketchObject", "Knife")
        sk.AttachmentSupport = [(util.xy_plane(body), "")]
        sk.MapMode = "FlatFace"
        sk.addGeometry(Part.LineSegment(App.Vector(x, y0, 0), App.Vector(x, y1, 0)))
        return sk

    def _split(self, d, body, x=5, y0=-5, y1=15):
        from incad.features import split
        sk = self._knife(body, x, y0, y1)
        d.recompute()
        f = split.create(d, body, None, dict(split.defaults(d, body, None), sketch=sk.Name))
        d.recompute()
        return f

    def _open(self, name):
        p = App.openDocument(os.path.join(self.dir, name + ".FCStd"))
        p.recompute()
        return p

    def test_a_used_up_boolean_tool_is_no_piece(self):
        from incad.features import combine
        d, body, pad = self._part("Bo")
        pin_body = document.new_solid(d)
        pin = pin_body.newObject("PartDesign::AdditiveCylinder", "Pin")
        pin.Radius, pin.Height = 2, 10
        pin.Placement = App.Placement(App.Vector(10, 5, 0), App.Rotation())
        pin_body.Tip = pin
        d.recompute()
        combine.create(d, body, None, dict(combine.defaults(d, body, None), base=body.Name, tools=pin_body.Name))
        d.recompute()
        d.saveAs(os.path.join(self.dir, "Bo.FCStd"))
        with self.assertRaises(ValueError) as ctx:  # the pin is used up: the part is one piece
            ma.pieces_or_refuse(d)
        self.assertIn("one piece", str(ctx.exception))

    def test_a_kept_tool_is_a_piece_and_the_base_copy_still_cuts(self):
        from incad.features import combine
        d, body, pad = self._part("Kt")
        pin_body = document.new_solid(d)
        pin = pin_body.newObject("PartDesign::AdditiveCylinder", "Pin")
        pin.Radius, pin.Height = 2, 10
        pin.Placement = App.Placement(App.Vector(10, 5, 0), App.Rotation())
        pin_body.Tip = pin
        d.recompute()
        combine.create(d, body, None, dict(combine.defaults(d, body, None), base=body.Name, tools=pin_body.Name,
                                           keep_tool=True))
        d.recompute()
        d.saveAs(os.path.join(self.dir, "Kt.FCStd"))
        ma.make(d, "Kt-Assembly", ["Kt-Solid1", "Kt-Solid2"])
        _close_all()
        base = self._open("Kt-Solid1")
        b = document.primary_body(base)
        cut = next(o for o in b.Group if combine.claims(o))
        self.assertTrue(cut.Group, "the Boolean keeps its tool (hidden), so it still recomputes")
        cut.touch()
        base.recompute()
        self.assertFalse([o.Label for o in base.Objects if "Invalid" in o.State])
        self.assertLess(b.Shape.Volume, 2000 - 100)  # the hole is there

    def test_a_failure_leaves_no_file_and_no_backup(self):
        d, body, pad = self._part("Fb")
        self._split(d, body)
        d.saveAs(os.path.join(self.dir, "Fb.FCStd"))
        original, calls = ma._finish_copy, []
        def second_fails(path, point):
            calls.append(path)
            if len(calls) == 2:
                raise ValueError("boom")
            return original(path, point)
        ma._finish_copy = second_fails
        try:
            with self.assertRaises(ValueError):
                ma.make(d, "Fb-Assembly", ["Fb-Solid1", "Fb-Solid2"])
        finally:
            ma._finish_copy = original
        self.assertEqual(sorted(os.listdir(self.dir)), ["Fb.FCStd"])

    def test_a_fillet_on_one_split_piece_does_not_stop_the_other(self):
        d, body, pad = self._part("Fs")
        split_f = self._split(d, body)
        edge = next(i + 1 for i, e in enumerate(split_f.Shape.Edges)
                    if e.BoundBox.XMax < 4 and abs(e.BoundBox.ZMax - 10) < 1e-6 and e.BoundBox.YLength > 9)
        fil = body.newObject("PartDesign::Fillet", "Round")
        fil.Base = (split_f, ["Edge%d" % edge])
        fil.Radius = 1
        body.Tip = fil
        d.recompute()
        self.assertNotIn("Invalid", fil.State, fil.getStatusString())
        d.saveAs(os.path.join(self.dir, "Fs.FCStd"))
        ma.make(d, "Fs-Assembly", ["Fs-Solid1", "Fs-Solid2"])
        _close_all()
        for name in ("Fs-Solid1", "Fs-Solid2"):
            p = self._open(name)
            self.assertFalse([o.Label for o in p.Objects if "Invalid" in o.State], name)
            self.assertEqual(len(document.primary_body(p).Shape.Solids), 1, name)
            App.closeDocument(p.Name)

    def test_a_far_box_then_a_split_through_it(self):
        d, body, pad = self._part("Ls")
        far = util.add_rect_sketch(body, w=10, h=10, name="FarSk")
        far.AttachmentOffset = App.Placement(App.Vector(50, 0, 0), App.Rotation())
        box = util.add_pad(body, far, 5, name="Box")
        body.Tip = box
        d.recompute()
        self._split(d, body, x=55)
        d.saveAs(os.path.join(self.dir, "Ls.FCStd"))
        self.assertEqual(len(ma.pieces(d)), 3)
        ma.make(d, "Ls-Assembly", ["Ls-Solid1", "Ls-Solid2", "Ls-Solid3"])
        _close_all()
        vols = []
        for name in ("Ls-Solid1", "Ls-Solid2", "Ls-Solid3"):
            p = self._open(name)
            self.assertFalse([o.Label for o in p.Objects if "Invalid" in o.State], name)
            vols.append(round(document.primary_body(p).Shape.Volume))
            App.closeDocument(p.Name)
        self.assertEqual(vols, [2000, 250, 250])

    def test_inside_points_are_inside_their_pieces(self):
        d = util.new_doc("Ri")
        body = document.make_part(d)
        sk = body.newObject("Sketcher::SketchObject", "RingSk")
        sk.AttachmentSupport = [(util.xy_plane(body), "")]
        sk.MapMode = "FlatFace"
        for r in (10, 8):
            sk.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), r))
        ring = util.add_pad(body, sk, 4, name="Ring")
        body.Tip = ring
        d.recompute()
        d.saveAs(os.path.join(self.dir, "Ri.FCStd"))
        self._split(d, body, x=0, y0=-15, y1=15)  # two C halves: their centres of mass are in the hole
        for p in ma.pieces(d):
            solid = min(document.bodies(d)[0].Shape.Solids, key=lambda s: s.distToShape(Part.Vertex(p.point))[0])
            self.assertTrue(solid.isInside(p.point, 1e-7, False), p)

    def test_a_feature_that_joins_the_split_pieces_is_named(self):
        d, body, pad = self._part("Jn")
        self._split(d, body)
        top = util.add_rect_sketch(body, w=20, h=10, name="Lid")
        top.AttachmentOffset = App.Placement(App.Vector(0, 0, 10), App.Rotation())
        lid = util.add_pad(body, top, 2, name="Lid")
        body.Tip = lid
        d.recompute()
        d.saveAs(os.path.join(self.dir, "Jn.FCStd"))
        with self.assertRaises(ValueError) as ctx:
            ma.pieces_or_refuse(d)
        self.assertIn("Lid", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
