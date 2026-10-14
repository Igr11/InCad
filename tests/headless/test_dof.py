import math
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

    def test_parallel_faces_leave_three_slides_and_one_turn(self):
        """Parallel limits rotation only: 2 turns away, the distance stays free."""
        make(self.doc, C.PARALLEL, fz(self.a, 10), fz(self.b, 0))
        f = dof.compute(self.doc)[self.b.Name]
        self.assertEqual((f.n, len(f.slides), len(f.turns)), (4, 3, 1))

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

    def test_tangent_on_a_turned_face_gives_two_slides_and_two_turns_on_the_part(self):
        """The user's Train_1: a round part tangent to a hex's face at 60°. The probe moves along world X/Y/Z, and the
        solver answers a slide or a turn with a little of the other: the glyph showed one arrow (the second slide
        was lost) and arcs far off the part (each turn's axis point came from a slide-and-turn motion)."""
        d = util.new_doc("Rod")
        body = document.make_part(d)
        cyl = body.newObject("PartDesign::AdditiveCylinder", "Rod")
        cyl.Radius, cyl.Height = 3, 20
        lug = body.newObject("PartDesign::AdditiveBox", "Lug")  # the D-shape: its centre off the round face's axis
        lug.Length, lug.Width, lug.Height = 8, 4, 20
        lug.Placement = App.Placement(App.Vector(0, -2, 0), App.Rotation())
        for o in (cyl, lug):  # drawn away from its own origin (Train_1's D-part sits at x 13..22 in its file): the
            o.Placement = App.Placement(App.Vector(20, 0, 0), App.Rotation()).multiply(o.Placement)  # solver turns
        body.Tip = lug  # the part about that origin, so every test move comes back as a slide-and-turn
        d.recompute()
        rod_path = os.path.join(self.dir, "Rod.FCStd")
        d.saveAs(rod_path)
        self.a.Placement = App.Placement(App.Vector(), App.Rotation(App.Vector(0, 0, 1), 60))  # the face at 60°
        self.doc.recompute()
        rod = assembly.place(self.doc, rod_path)
        side = [i + 1 for i, f in enumerate(self.a.Shape.Faces) if f.Surface.TypeId == "Part::GeomPlane"
                and abs(f.normalAt(*f.Surface.parameter(f.CenterOfMass)).z) < 1e-6][0]
        round_face = [i + 1 for i, f in enumerate(rod.LinkedObject.Shape.Faces) if f.Surface.TypeId == "Part::GeomCylinder"][0]
        make(self.doc, C.TANGENT, "%s:Face%d" % (rod.Name, round_face), "%s:Face%d" % (self.a.Name, side))
        f = dof.compute(self.doc)[rod.Name]
        self.assertEqual(f.n, 4)
        self.assertEqual((len(f.slides), len(f.turns)), (2, 2), (f.slides, f.turns))
        face = self.a.Shape.getElement("Face%d" % side)
        normal = face.normalAt(*face.Surface.parameter(face.CenterOfMass))
        rot = rod.Placement.Rotation
        for s in f.slides:  # both slides lie in the face's plane
            self.assertAlmostEqual(rot.multVec(s).dot(normal), 0, places=2)
        bb = rod.Shape.BoundBox
        axes = []
        for point, axis in f.turns:  # each arc's axis runs through (or right by) the part
            p, a = rod.Placement.multVec(point), rot.multVec(axis)
            off = (bb.Center - p) - a * (bb.Center - p).dot(a)
            self.assertLess(off.Length, bb.DiagonalLength, (p, a))
            axes.append(a)
        rod_axis = rot.multVec(App.Vector(0, 0, 1))
        self.assertEqual(sorted(round(max(abs(a.dot(rod_axis)), abs(a.dot(normal))), 2) for a in axes), [1.0, 1.0],
                         "one turn about the rod's axis, one about the face's normal")

    def test_slides_run_along_the_parts_own_axes_where_they_can(self):
        """The user's Train_3 (Tangent + Angle, DOF 2): the slides were two diagonals of the free plane, so no arrow
        moved the part straight up or sideways. Any pair spans the plane; the arrows take the part's own axes."""
        make(self.doc, C.MATE, fz(self.a, 10), fz(self.b, 0))
        f = dof.compute(self.doc)[self.b.Name]
        self.assertEqual(len(f.slides), 2)
        for s in f.slides:
            self.assertAlmostEqual(max(abs(s.x), abs(s.y), abs(s.z)), 1, places=3, msg=s)
        self.assertAlmostEqual(abs(f.turns[0][1].z), 1, places=3)
        self.b.Placement = App.Placement(self.b.Placement.Base, App.Rotation(App.Vector(0, 0, 1), 30))
        self.doc.recompute()
        dof._CACHE.clear()
        f = dof.compute(self.doc)[self.b.Name]
        for s in f.slides:  # in the part's own frame: its X and Y, turned with it
            self.assertAlmostEqual(max(abs(s.x), abs(s.y), abs(s.z)), 1, places=3, msg=s)

    def test_the_first_arrow_is_up_and_down_as_far_as_the_part_can(self):
        """The user: "In more cases I need up and down movement, not diagonal movement". On a face tilted 30° the
        block can only slide in that face's plane: its first arrow climbs the slope, the second runs level."""
        self.a.Placement = App.Placement(App.Vector(), App.Rotation(App.Vector(1, 0, 0), 30))
        self.doc.recompute()
        make(self.doc, C.MATE, fz(self.a, 10), fz(self.b, 0))
        f = dof.compute(self.doc)[self.b.Name]
        rot = self.b.Placement.Rotation
        up, level = (rot.multVec(s) for s in f.slides)
        self.assertAlmostEqual(abs(up.z), math.sin(math.radians(30)), places=3, msg=up)  # the steepest it can
        self.assertAlmostEqual(level.z, 0, places=3, msg=level)

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

    def test_count_keeps_the_redo_stack(self):
        self.doc.openTransaction("Mate")
        make(self.doc, C.MATE, fz(self.a, 10), fz(self.b, 0))
        self.doc.commitTransaction()
        self.doc.undo()
        redo = list(self.doc.RedoNames)
        self.assertTrue(redo)
        dof.compute(self.doc)
        self.assertEqual(list(self.doc.RedoNames), redo)  # a count opens no step: Redo still works
        self.doc.redo()
        self.assertEqual(list(self.doc.RedoNames), [])
        self.assertEqual(list(self.doc.UndoNames), redo)

    def test_busy_while_a_step_is_open(self):
        self.doc.openTransaction("Mate")
        self.b.Label = "Block 2"  # a dialog's step has changes (FreeCAD reports HasPendingTransaction only then)
        with self.assertRaises(dof.Busy):
            dof.compute(self.doc)
        self.doc.abortTransaction()

    def test_busy_while_any_document_is_loading(self):
        class Loading:
            Restoring = True
        real = App.listDocuments
        App.listDocuments = lambda: dict(real(), Other=Loading())  # another file still loading (its progress bar)
        try:
            with self.assertRaises(dof.Busy):
                dof.compute(self.doc)
        finally:
            App.listDocuments = real

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

    def test_handles_say_which_freedom_each_line_is(self):
        z = App.Vector(0, 0, 1)
        f = dof.Freedom(3, [App.Vector(1, 0, 0), App.Vector(0, 1, 0)], [(App.Vector(0, 0, 0), z)], "")
        plc = App.Placement(App.Vector(10, 0, 0), App.Rotation(z, 90))
        centre = App.Vector(10, 0, 5)
        hs = dof.handles(f, plc, centre, 4.0)
        self.assertEqual([(h.kind, h.index) for h in hs], [("slide", 0), ("slide", 1), ("turn", 0)])
        lines, heads = dof.glyph(f, plc, centre, 4.0)
        self.assertEqual([h.line for h in hs], lines, "the same lines as the glyph, in its order")
        self.assertEqual([hd for h in hs for hd in h.heads], heads)
        s0, _, t = hs
        self.assertAlmostEqual(s0.axis.dot(App.Vector(0, 1, 0)), 1, places=6)  # own X turned to global Y
        self.assertAlmostEqual((s0.point - centre).Length, 0, places=6)
        self.assertAlmostEqual(abs(t.axis.z), 1, places=6)
        self.assertAlmostEqual((t.point - centre).Length, 0, places=6)  # the turn axis is through the centre
        self.assertAlmostEqual(t.radius, 4.0 * 0.6, places=6)
        for k, p in enumerate((t.line[0], t.line[8])):  # the arc starts on u and runs towards w (positive turn)
            a = 1.5 * math.pi * (0, 8)[k] / 24
            want = t.point + (t.u * math.cos(a) + t.w * math.sin(a)) * t.radius
            self.assertAlmostEqual((p - want).Length, 0, places=6)
        self.assertAlmostEqual(t.u.cross(t.w).dot(t.axis), 1, places=6)

    def test_an_axis_far_from_the_part_has_its_arc_at_the_centre(self):
        z = App.Vector(0, 0, 1)
        f = dof.Freedom(1, [], [(App.Vector(100, 0, 0), z)], "")  # the part turns about a line 100 mm away
        centre = App.Vector(0, 0, 5)
        (t,) = dof.handles(f, App.Placement(), centre, 4.0)
        self.assertAlmostEqual((t.point - centre).Length, 0, places=6, msg="the arc is drawn on the part")
        for p in t.line:
            self.assertAlmostEqual((p - centre).Length, 4.0 * 0.6, places=6)
        self.assertAlmostEqual((t.pivot - App.Vector(100, 0, 5)).Length, 0, places=6, msg="it still turns there")
        near = dof.Freedom(1, [], [(App.Vector(3, 0, 0), z)], "")  # within 1.5 sizes: drawn on its own line
        (t,) = dof.handles(near, App.Placement(), centre, 4.0)
        self.assertAlmostEqual((t.point - App.Vector(3, 0, 5)).Length, 0, places=6)

    def test_each_turn_has_its_own_ring(self):
        """Arcs around one centre with one radius cross on screen: a press meant for one caught the other."""
        axes = [App.Vector(1, 0, 0), App.Vector(0, 1, 0), App.Vector(0, 0, 1)]
        f = dof.Freedom(3, [], [(App.Vector(), a) for a in axes], "")
        hs = dof.handles(f, App.Placement(), App.Vector(), 4.0)
        self.assertEqual([round(h.radius, 6) for h in hs], [2.4, 3.6, 4.8])
        for h in hs:
            for p in h.line:
                self.assertAlmostEqual(p.Length, h.radius, places=6)

    def test_no_freedom_no_glyph(self):
        self.assertEqual(dof.glyph(dof.Freedom(0, [], [], ""), App.Placement(), App.Vector(), 4.0), ([], []))


class GlyphSizeTest(unittest.TestCase):
    """The user (2026-10-14): the gizmo arrows a little smaller — 20 % — the grab zone stays as wide."""

    def test_twenty_percent_smaller_than_before(self):
        from incad.core import dof
        self.assertAlmostEqual(dof.glyph_size(100.0), 28.0)   # was 35
        self.assertAlmostEqual(dof.glyph_size(10.0), 4.0)     # the floor: was 5
