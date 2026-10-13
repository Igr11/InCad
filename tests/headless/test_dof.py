import os
import shutil
import tempfile
import unittest

import FreeCAD as App
from incad.core import assembly, document, dof
from incad.features import constraints as C
from headless import util
from headless.test_assembly import save_part


def fz(link, z):
    return "%s:Face%d" % (link.Name, [i + 1 for i, f in enumerate(link.LinkedObject.Shape.Faces)
                                      if f.Surface.TypeId == "Part::GeomPlane" and abs(f.CenterOfMass.z - z) < 1e-6][0])


def fx(link, x):
    return "%s:Face%d" % (link.Name, [i + 1 for i, f in enumerate(link.LinkedObject.Shape.Faces)
                                      if f.Surface.TypeId == "Part::GeomPlane" and abs(f.CenterOfMass.x - x) < 1e-6][0])


def fy(link, y):
    return "%s:Face%d" % (link.Name, [i + 1 for i, f in enumerate(link.LinkedObject.Shape.Faces)
                                      if f.Surface.TypeId == "Part::GeomPlane" and abs(f.CenterOfMass.y - y) < 1e-6][0])


def make(doc, kind, first, second):
    return kind.create(doc, None, None, dict(kind.defaults(doc, None), first=first, second=second))


class DofTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="incad_dof_")
        _, self.plate_path = save_part(self.dir, "Plate", 40, 30, 10)
        _, self.block_path = save_part(self.dir, "Block", 10, 10, 10)
        self.doc = App.newDocument("Asm")
        self.doc.UndoMode = 1
        assembly.make_assembly(self.doc, "mm")
        self.doc.saveAs(os.path.join(self.dir, "Asm.FCStd"))
        self.a = assembly.place(self.doc, self.plate_path)
        self.b = assembly.place(self.doc, self.block_path)
        dof._CACHE.clear()

    def tearDown(self):
        for name in list(App.listDocuments()):
            App.closeDocument(name)
        shutil.rmtree(self.dir, ignore_errors=True)

    def n(self, link):
        return dof.compute(self.doc)[link.Name].n

    def test_free_part_has_six(self):
        f = dof.compute(self.doc)[self.b.Name]
        self.assertEqual((f.n, len(f.slides), len(f.turns), f.error), (6, 3, 3, ""))

    def test_grounded_part_is_not_counted(self):
        self.assertNotIn(self.a.Name, dof.compute(self.doc))

    def test_mate_leaves_two_slides_in_the_face_and_one_turn_about_its_normal(self):
        make(self.doc, C.MATE, fz(self.a, 10), fz(self.b, 0))
        f = dof.compute(self.doc)[self.b.Name]
        self.assertEqual(f.n, 3)
        self.assertEqual(len(f.slides), 2)
        for d in f.slides:
            self.assertAlmostEqual(d.z, 0, places=3)  # in the plate's plane (block unturned: own frame = global)
        self.assertEqual(len(f.turns), 1)
        self.assertAlmostEqual(abs(f.turns[0][1].z), 1, places=3)

    def test_mate_and_flushes(self):
        make(self.doc, C.MATE, fz(self.a, 10), fz(self.b, 0))
        make(self.doc, C.FLUSH, fx(self.a, 0), fx(self.b, 0))
        self.assertEqual(self.n(self.b), 1)
        make(self.doc, C.FLUSH, fy(self.a, 0), fy(self.b, 0))
        self.assertEqual(self.n(self.b), 0)

    def test_insert_turns_about_the_pin_axis(self):
        d = util.new_doc("Pin")
        body = document.make_part(d)
        cyl = body.newObject("PartDesign::AdditiveCylinder", "Pin")
        cyl.Radius, cyl.Height = 3, 20
        body.Tip = cyl
        d.recompute()
        pin_path = os.path.join(self.dir, "Pin.FCStd")
        d.saveAs(pin_path)
        hd = App.getDocument("Plate")  # save_part leaves the part open (named after it)
        hb = document.primary_body(hd)
        hole = hb.newObject("PartDesign::SubtractiveCylinder", "HoleCyl")
        hole.Radius, hole.Height = 3, 10
        hole.Placement = App.Placement(App.Vector(20, 15, 0), App.Rotation())
        hb.Tip = hole
        hd.recompute()
        hd.save()
        self.doc.recompute()
        p = assembly.place(self.doc, pin_path)
        mouth = [i + 1 for i, e in enumerate(self.a.Shape.Edges) if e.Curve.TypeId == "Part::GeomCircle"
                 and abs(e.Curve.Radius - 3) < 1e-6 and abs(e.Curve.Center.z - 10) < 1e-6][0]
        end = [i + 1 for i, e in enumerate(p.LinkedObject.Shape.Edges) if e.Curve.TypeId == "Part::GeomCircle"
               and abs(e.Curve.Center.z) < 1e-6][0]
        make(self.doc, C.INSERT, "%s:Edge%d" % (p.Name, end), "%s:Edge%d" % (self.a.Name, mouth))
        f = dof.compute(self.doc)[p.Name]
        self.assertEqual((f.n, len(f.slides), len(f.turns)), (1, 0, 1))
        point, axis = f.turns[0]
        self.assertAlmostEqual(abs(axis.z), 1, places=3)  # the pin's own axis (its frame: z along the pin)
        self.assertLess(App.Vector(point.x, point.y, 0).Length, 1e-3)  # through the pin's centre line

    def test_count_is_relative_to_what_holds_it(self):
        _, mid_path = save_part(self.dir, "Mid", 20, 20, 10)
        m = assembly.place(self.doc, mid_path)  # free, no constraints
        make(self.doc, C.MATE, fz(m, 10), fz(self.b, 0))  # Block held only by the free Mid
        counts = dof.compute(self.doc)
        self.assertEqual(counts[self.b.Name].n, 3)
        self.assertEqual(counts[m.Name].n, 3)  # the same, the other way round: Mid slides on the held Block

    def test_nothing_grounded(self):
        assembly.unground(self.a)
        make(self.doc, C.MATE, fz(self.a, 10), fz(self.b, 0))
        counts = dof.compute(self.doc)
        self.assertEqual(counts[self.b.Name].n, 3)
        self.assertEqual(counts[self.a.Name].n, 3)
        single = App.newDocument("Solo")
        single.UndoMode = 1
        assembly.make_assembly(single, "mm")
        single.saveAs(os.path.join(self.dir, "Solo.FCStd"))
        only = assembly.place(single, self.block_path)
        assembly.unground(only)
        self.assertEqual(dof.compute(single)[only.Name].n, 6)

    def test_count_leaves_no_trace(self):
        make(self.doc, C.MATE, fz(self.a, 10), fz(self.b, 0))
        names = sorted(o.Name for o in self.doc.Objects)
        undo = list(self.doc.UndoNames)
        at = {c.Name: App.Placement(c.Placement) for c in assembly.components(self.doc)}
        dof.compute(self.doc)
        self.assertEqual(sorted(o.Name for o in self.doc.Objects), names)
        self.assertEqual(list(self.doc.UndoNames), undo)
        for c in assembly.components(self.doc):
            self.assertTrue(c.Placement.isSame(at[c.Name], 1e-9), c.Name)
        self.assertFalse(self.doc.HasPendingTransaction)

    def test_busy_while_a_step_is_open(self):
        self.doc.openTransaction("Mate")
        self.b.Label = "Block 2"  # a dialog's step has changes (FreeCAD reports HasPendingTransaction only then)
        with self.assertRaises(dof.Busy):
            dof.compute(self.doc)
        self.doc.abortTransaction()

    def test_cache_follows_constraints_not_placements(self):
        counts, computed = dof.ensure(self.doc)
        self.assertTrue(computed)
        self.assertEqual(counts[self.b.Name].n, 6)
        self.b.Placement = App.Placement(App.Vector(1, 2, 3), App.Rotation(10, 0, 0))
        self.assertEqual(dof.ensure(self.doc)[1], False, "a move does not recount")
        make(self.doc, C.MATE, fz(self.a, 10), fz(self.b, 0))
        self.assertIsNone(dof.cached(self.doc))
        self.assertEqual(dof.last(self.doc)[self.b.Name].n, 6, "the last numbers stay until the recount")
        counts, computed = dof.ensure(self.doc)
        self.assertTrue(computed)
        self.assertEqual(counts[self.b.Name].n, 3)

    def test_suppressed_part_is_not_counted(self):
        assembly.toggle_suppressed(self.b)
        self.assertNotIn(self.b.Name, dof.compute(self.doc))

    def test_sub_assembly_counts_as_one_part(self):
        sub = App.newDocument("Sub")
        sub.UndoMode = 1
        assembly.make_assembly(sub, "mm")
        sub_path = os.path.join(self.dir, "Sub.FCStd")
        sub.saveAs(sub_path)
        assembly.place(sub, self.block_path)
        sub.save()
        s = assembly.place(self.doc, sub_path)
        f = dof.compute(self.doc)[s.Name]
        self.assertEqual(f.n, 6, f.error)

    def test_part_without_a_solid_does_not_break_the_count(self):
        d = util.new_doc("Empty")
        document.make_part(d)
        d.recompute()
        path = os.path.join(self.dir, "Empty.FCStd")
        d.saveAs(path)
        e = assembly.place(self.doc, path)
        counts = dof.compute(self.doc)  # no exception
        self.assertIn(e.Name, counts)
        self.assertEqual(counts[self.b.Name].n, 6)


class GlyphTest(unittest.TestCase):
    def test_slides_are_double_arrows_and_turns_are_arcs_on_their_axis(self):
        z = App.Vector(0, 0, 1)
        f = dof.Freedom(3, [App.Vector(1, 0, 0), App.Vector(0, 1, 0)], [(App.Vector(0, 0, 0), z)], "")
        plc = App.Placement(App.Vector(10, 0, 0), App.Rotation(z, 90))  # the part moved and turned since the count
        lines, heads = dof.glyph(f, plc, App.Vector(10, 0, 5), 4.0)
        self.assertEqual(len(lines), 3)
        self.assertEqual(len(heads), 5)
        a, b = lines[0]
        self.assertAlmostEqual((b - a).normalize().dot(App.Vector(0, 1, 0)), 1, places=6)  # own X turned to global Y
        arc = lines[2]
        self.assertEqual(len(arc), 25)
        for p in arc:
            self.assertAlmostEqual(p.z, 5, places=6)  # level with the centre
            self.assertAlmostEqual((p - App.Vector(10, 0, 5)).Length, 4.0 * 0.6, places=6)  # around the moved axis

    def test_no_freedom_no_glyph(self):
        self.assertEqual(dof.glyph(dof.Freedom(0, [], [], ""), App.Placement(), App.Vector(), 4.0), ([], []))
