import math
import unittest

import FreeCAD as App
import Part
from incad.core import document, model
from incad.features import common, kind_for, thread
from incad.threads import profile, standards as st
from headless import util


def shaft(doc, body, radius=5.0, length=20.0, name="Shaft"):
    sk = body.newObject("Sketcher::SketchObject", name + "Sk")
    sk.AttachmentSupport = [(util.xy_plane(body), "")]
    sk.MapMode = "FlatFace"
    sk.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), radius))
    pad = util.add_pad(body, sk, length, name=name)
    body.Tip = pad
    doc.recompute()
    return pad


def cyl_face(feature, radius):
    return "%s:Face%d" % (feature.Name, [i + 1 for i, f in enumerate(feature.Shape.Faces)
                                         if f.Surface.TypeId == "Part::GeomCylinder"
                                         and abs(f.Surface.Radius - radius) < 1e-6][0])


def estimate(spec, internal, clearance, length):
    """Groove area inside the material × mean circumference × turns."""
    g = profile.groove(spec, internal, clearance)
    R = spec.major / 2.0
    inside = [(r, z) for r, z in g]
    lo, hi = (min(r for r, _ in g), R) if not internal else (R - spec.depth_int, max(r for r, _ in g))
    n = 40
    area = sum(profile.width_at(inside, lo + (hi - lo) * (i + 0.5) / n) * (hi - lo) / n for i in range(n))
    rc = (lo + hi) / 2.0
    return area * 2 * math.pi * rc * length / spec.pitch


class ThreadTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Th")
        self.body = document.make_part(self.doc)

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def make(self, **values):
        v = dict(thread.defaults(self.doc, self.body, None), **values)
        f = thread.create(self.doc, self.body, None, v)
        self.doc.recompute()
        return f

    def test_external_m10(self):
        pad = shaft(self.doc, self.body)
        f = self.make(face=cyl_face(pad, 5), standard="iso", size="M10", clearance="0 mm")
        self.assertEqual(f.State, ["Up-to-date"], f.getStatusString())
        self.assertTrue(f.Shape.isValid())
        removed = pad.Shape.Volume - f.Shape.Volume
        want = estimate(st.spec("iso", "M10"), False, 0.0, 20.0)
        self.assertAlmostEqual(removed / want, 1.0, delta=0.15)
        self.assertIs(self.body.Tip, f)
        self.assertIs(kind_for(f), thread)

    def test_size_is_suggested_from_the_face(self):
        pad = shaft(self.doc, self.body, radius=4.0)
        f = self.make(face=cyl_face(pad, 4), standard="iso", size="")
        self.assertEqual(thread.read(self.doc, f)["size"], "M8")

    def test_internal_m10_in_a_bore(self):
        block = shaft(self.doc, self.body, radius=10.0, name="Block")
        s = st.spec("iso", "M10")
        bore_r = st.bore_diameter(s, 0.2) / 2
        sk = self.body.newObject("Sketcher::SketchObject", "BoreSk")
        sk.AttachmentSupport = [(util.xy_plane(self.body), "")]
        sk.MapMode = "FlatFace"
        sk.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), bore_r))
        bore = self.body.newObject("PartDesign::Pocket", "Bore")
        bore.Profile = sk
        bore.Type = "ThroughAll"
        bore.Reversed = True
        self.body.Tip = bore
        self.doc.recompute()
        self.assertLess(bore.Shape.Volume, block.Shape.Volume)
        f = self.make(face=cyl_face(bore, bore_r), standard="iso", size="M10", clearance="0.2 mm")
        self.assertEqual(f.State, ["Up-to-date"], f.getStatusString())
        self.assertTrue(thread.read(self.doc, f)["internal"])
        removed = bore.Shape.Volume - f.Shape.Volume
        self.assertGreater(removed, 0.5 * estimate(s, True, 0.2, 20.0))

    def test_left_hand_and_taper(self):
        pad = shaft(self.doc, self.body, radius=6.6)
        f = self.make(face=cyl_face(pad, 6.6), standard="npt", size="1/4", hand="left")
        self.assertTrue(f.LeftHanded)
        self.assertAlmostEqual(abs(f.Angle.Value), st.spec("npt", "1/4").taper, places=4)
        self.assertNotIn("Invalid", f.State)

    def test_length_parameter_drives_the_helix(self):
        pad = shaft(self.doc, self.body)
        f = self.make(face=cyl_face(pad, 5), size="M10", length_mode="distance", length="8 mm")
        name = model.bound_parameter(f, "Height")
        self.assertIsNotNone(name)
        model.set_model_parameter(self.doc, name, "12 mm")
        self.assertAlmostEqual(f.Height.Value, 12, places=6)

    def test_edit_size_keeps_the_feature(self):
        pad = shaft(self.doc, self.body)
        f = self.make(face=cyl_face(pad, 5), size="M10")
        v1 = f.Shape.Volume
        g = thread.update(self.doc, f, dict(thread.read(self.doc, f), standard="iso_fine", size="M10x1.25"))
        self.doc.recompute()
        self.assertIs(g, f)
        self.assertAlmostEqual(f.Pitch.Value, 1.25, places=6)
        self.assertNotAlmostEqual(f.Shape.Volume, v1, places=1)
        self.assertEqual(thread.read(self.doc, f)["size"], "M10x1.25")

    def test_flat_face_is_refused(self):
        pad = shaft(self.doc, self.body)
        top = [i + 1 for i, fc in enumerate(pad.Shape.Faces) if fc.Surface.TypeId == "Part::GeomPlane"][0]
        with self.assertRaises(ValueError) as ctx:
            self.make(face="%s:Face%d" % (pad.Name, top), size="M10")
        self.assertIn("cylindrical", str(ctx.exception))

    def test_big_clearance_on_a_fine_pitch_is_still_valid(self):
        pad = shaft(self.doc, self.body, radius=1.5, length=6)
        f = self.make(face=cyl_face(pad, 1.5), size="M3", clearance="0.6 mm")
        self.assertEqual(f.State, ["Up-to-date"], f.getStatusString())
        self.assertTrue(f.Shape.isValid())

    def test_cylinder_pick_kind(self):
        pad = shaft(self.doc, self.body)
        obj, sub = common.parse_picks(self.doc, cyl_face(pad, 5))[0]
        self.assertTrue(common.accepts("cylinder", obj, sub))
        self.assertFalse(common.accepts("cylinder", obj, "Face1" if sub != "Face1" else "Face2"))


class ThreadReviewTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Tr")
        self.body = document.make_part(self.doc)

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def make(self, **values):
        v = dict(thread.defaults(self.doc, self.body, None), **values)
        f = thread.create(self.doc, self.body, None, v)
        self.doc.recompute()
        return f

    def add_cyl(self, radius, z0, length, name):
        sk = self.body.newObject("Sketcher::SketchObject", name + "Sk")
        sk.AttachmentSupport = [(util.xy_plane(self.body), "")]
        sk.MapMode = "FlatFace"
        sk.AttachmentOffset = App.Placement(App.Vector(0, 0, z0), App.Rotation())
        sk.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), radius))
        pad = util.add_pad(self.body, sk, length, name=name)
        self.body.Tip = pad
        self.doc.recompute()
        return pad

    def test_starts_at_the_free_end_of_a_shaft_on_a_shoulder(self):
        self.add_cyl(8, -5, 5, "Shoulder")           # z -5..0, Ø16
        shaft_ = self.add_cyl(5, 0, 20, "Shaft")     # z 0..20, Ø10
        before = shaft_.Shape.Volume
        f = self.make(face=cyl_face(shaft_, 5), size="M10", length_mode="distance", length="6 mm", clearance="0 mm")
        cut = shaft_.Shape.cut(f.Shape)
        self.assertGreater(cut.BoundBox.ZMin, 12, cut.BoundBox)  # the 6 mm thread is at the free (top) end
        self.assertLess(before - f.Shape.Volume, before)

    def test_full_thread_does_not_cut_the_shoulder(self):
        shoulder = self.add_cyl(8, -5, 5, "Shoulder")
        shaft_ = self.add_cyl(5, 0, 20, "Shaft")
        f = self.make(face=cyl_face(shaft_, 5), size="M10", clearance="0 mm")
        below = Part.makeCylinder(8, 5, App.Vector(0, 0, -5))
        self.assertAlmostEqual(below.common(f.Shape).Volume, below.common(shaft_.Shape).Volume, places=3)

    def test_npt_external_is_small_at_the_free_end(self):
        self.add_cyl(9, -5, 5, "Shoulder")
        shaft_ = self.add_cyl(6.6, 0, 15, "Pipe")
        f = self.make(face=cyl_face(shaft_, 6.6), standard="npt", size="1/4", clearance="0 mm")
        def root(z):
            sl = f.Shape.slice(App.Vector(0, 0, 1), z)
            return min(min(abs(v.Point.x) for v in w.Vertexes) for w in sl if w.Vertexes) if sl else None
        lows = [min(e.distToShape(Part.Vertex(App.Vector(0, 0, z)))[0] for e in f.Shape.slice(App.Vector(0, 0, 1), z))
                for z in (2.0, 13.0)]
        self.assertGreater(lows[0], lows[1])  # thread root larger near the shoulder, smaller at the free end

    def test_mismatched_size_is_refused_or_cuts_through(self):
        shaft_ = self.add_cyl(5, 0, 10, "Shaft")
        with self.assertRaises(ValueError) as ctx:
            self.make(face=cyl_face(shaft_, 5), size="M20")
        self.assertIn("size", str(ctx.exception).lower())
        with self.assertRaises(ValueError) as ctx:
            self.make(face=cyl_face(shaft_, 5), size="M6")  # would only make a buried helical tunnel
        self.assertIn("size", str(ctx.exception).lower())
        wide = self.add_cyl(5.2, 10, 10, "Wide")  # Ø10.4 with an M10: the groove still opens at the surface
        f = self.make(face=cyl_face(wide, 5.2), size="M10", clearance="0 mm")
        ring = Part.makeCylinder(5.2, 10, App.Vector(0, 0, 10)).cut(Part.makeCylinder(4.9, 10, App.Vector(0, 0, 10)))
        self.assertLess(ring.common(f.Shape).Volume, ring.Volume * 0.7)

    def test_partial_cylinder_is_refused(self):
        pad = self.add_cyl(5, 0, 10, "Shaft")
        from incad.features import dressup
        edges = [(pad, "Edge%d" % (i + 1)) for i, e in enumerate(pad.Shape.Edges)
                 if e.Curve.TypeId == "Part::GeomCircle" and e.BoundBox.ZMax > 9]
        fil = dressup.FILLET.create(self.doc, self.body, None, {"edges": common.format_picks(edges),
                                                                "radius": "2 mm"})
        self.doc.recompute()
        torus_or_cyl = [i + 1 for i, fc in enumerate(fil.Shape.Faces) if fc.Surface.TypeId == "Part::GeomCylinder"]
        sub = "Face%d" % torus_or_cyl[0]
        self.assertTrue(common.accepts("cylinder", fil, sub))  # the full shaft face is still fine
        box = self.doc.addObject("Part::Box", "Box")
        self.doc.recompute()
        cube = Part.makeBox(10, 10, 10)
        f2 = cube.makeFillet(2, [cube.Edges[0]])
        part = self.doc.addObject("Part::Feature", "Rounded")
        part.Shape = f2
        quarter = [i + 1 for i, fc in enumerate(f2.Faces) if fc.Surface.TypeId == "Part::GeomCylinder"][0]
        self.assertFalse(common.accepts("cylinder", part, "Face%d" % quarter))

    def test_clearance_limits(self):
        shaft_ = self.add_cyl(1.5, 0, 6, "Shaft")
        for bad in ("-0.1 mm", "3 mm"):
            with self.assertRaises(ValueError) as ctx:
                self.make(face=cyl_face(shaft_, 1.5), size="M3", clearance=bad)
            self.assertIn("clearance", str(ctx.exception).lower())

    def test_print_friendly_matches_iso_pitch_diameter(self):
        for size in ("M6", "M10", "M24"):
            iso, pr = st.spec("iso", size), st.spec("print", size)
            d2 = iso.major - 0.6495 * iso.pitch
            for spec in (iso, pr):
                g = profile.groove(spec, internal=False, clearance=0.0)
                self.assertAlmostEqual(profile.width_at(g, d2 / 2), spec.pitch / 2, places=2, msg=(size, spec.std))
                gi = profile.groove(spec, internal=True, clearance=0.0)
                self.assertAlmostEqual(profile.width_at(gi, d2 / 2), spec.pitch / 2, places=2, msg=(size, spec.std))


class ThreadRunOutTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Ro")
        self.body = document.make_part(self.doc)

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_full_thread_runs_out_past_both_free_ends(self):
        pad = shaft(self.doc, self.body)  # Ø10 × 20, both ends free
        f = thread.create(self.doc, self.body, None, dict(thread.defaults(self.doc, self.body, None),
                                                          face=cyl_face(pad, 5), size="M10", clearance="0 mm"))
        self.doc.recompute()

        def ring_cut(z0):  # material removed in a 1.5 mm (one pitch) slab
            slab = Part.makeCylinder(5, 1.5, App.Vector(0, 0, z0))
            return slab.Volume - slab.common(f.Shape).Volume
        middle = ring_cut(9.25)
        self.assertAlmostEqual(ring_cut(0.0) / middle, 1.0, delta=0.1)   # full thread right to the end
        self.assertAlmostEqual(ring_cut(18.5) / middle, 1.0, delta=0.1)
