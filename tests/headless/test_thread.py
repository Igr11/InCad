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
