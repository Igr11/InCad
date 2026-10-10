import unittest

import FreeCAD as App
import Part
from incad.core import document, model
from incad.features import kind_for, shapes, thread
from headless import util


def plane(body, role):
    return [o for o in body.Origin.OriginFeatures if o.Role == role][0]


def sketch(body, role, name, geos, z=0.0):
    sk = body.newObject("Sketcher::SketchObject", name)
    sk.AttachmentSupport = [(plane(body, role), "")]
    sk.MapMode = "FlatFace"
    sk.AttachmentOffset = App.Placement(App.Vector(0, 0, z), App.Rotation())
    for g in geos:
        sk.addGeometry(g)
    return sk


class ShapesTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Sh")
        self.body = document.make_part(self.doc)

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def make(self, kind, **values):
        v = dict(kind.defaults(self.doc, self.body, None), **values)
        f = kind.create(self.doc, self.body, None, v)
        self.doc.recompute()
        return f

    def circle(self, r, z=0.0, role="XY_Plane", name="C", x=0.0):
        return sketch(self.body, role, name, [Part.Circle(App.Vector(x, 0, 0), App.Vector(0, 0, 1), r)], z)

    def test_sweep(self):
        prof = self.circle(2, name="Prof")
        path = sketch(self.body, "XZ_Plane", "Path", [Part.LineSegment(App.Vector(0, 0, 0), App.Vector(0, 20, 0))])
        self.doc.recompute()
        f = self.make(shapes.SWEEP, profile=prof.Name, path=path.Name)
        self.assertEqual(f.TypeId, "PartDesign::AdditivePipe")
        self.assertAlmostEqual(f.Shape.Volume, 3.14159265 * 4 * 20, places=1)
        self.assertIs(self.body.Tip, f)
        self.assertIs(kind_for(f), shapes.SWEEP)
        r = shapes.SWEEP.read(self.doc, f)
        self.assertEqual((r["profile"], r["path"], r["operation"]), (prof.Name, path.Name, "join"))

    def test_loft_and_its_checks(self):
        a, b = self.circle(2, name="A"), self.circle(5, z=10, name="B")
        self.doc.recompute()
        f = self.make(shapes.LOFT, sections="%s,%s" % (a.Name, b.Name))
        self.assertEqual(f.TypeId, "PartDesign::AdditiveLoft")
        self.assertNotIn("Invalid", f.State)
        self.assertGreater(f.Shape.Volume, 3.14159265 * 4 * 10)
        self.assertEqual(shapes.LOFT.read(self.doc, f)["sections"], "%s,%s" % (a.Name, b.Name))
        with self.assertRaises(ValueError) as ctx:
            shapes.LOFT.create(self.doc, self.body, None, dict(shapes.LOFT.defaults(self.doc, self.body, None),
                                                             sections=a.Name))
        self.assertIn("two", str(ctx.exception))

    def test_coil_with_parameters_and_threads_stay_threads(self):
        prof = sketch(self.body, "XZ_Plane", "CoilP", [Part.Circle(App.Vector(20, 0, 0), App.Vector(0, 0, 1), 1)])
        self.doc.recompute()
        f = self.make(shapes.COIL, profile=prof.Name, pitch="5 mm", height="20 mm")
        self.assertEqual(f.TypeId, "PartDesign::AdditiveHelix")
        self.assertTrue(f.Shape.isValid())
        self.assertIs(kind_for(f), shapes.COIL)
        model.set_model_parameter(self.doc, model.bound_parameter(f, "Height"), "10 mm")
        self.assertAlmostEqual(f.Height.Value, 10, places=6)
        self.assertFalse(shapes.COIL.claims(type("T", (), {"InCadThread": "{}"})()))
        self.assertIn(shapes.COIL, [k for k in [kind_for(f)]])

    def test_draft(self):
        body, pad = self.body, util.add_pad(self.body, util.add_rect_sketch(self.body), 10)
        body.Tip = pad
        self.doc.recompute()
        sides = ",".join("%s:Face%d" % (pad.Name, i + 1) for i, fc in enumerate(pad.Shape.Faces)
                         if abs(fc.normalAt(0, 0).z) < 1e-6)
        top = "%s:Face%d" % (pad.Name, [i + 1 for i, fc in enumerate(pad.Shape.Faces)
                                        if abs(fc.CenterOfMass.z - 10) < 1e-6][0])
        f = self.make(shapes.DRAFT, faces=sides, neutral=top, angle="5 °")
        self.assertEqual(f.TypeId, "PartDesign::Draft")
        self.assertNotIn("Invalid", f.State)
        self.assertNotAlmostEqual(f.Shape.Volume, pad.Shape.Volume, places=1)
        self.assertEqual(shapes.DRAFT.read(self.doc, f)["angle"], "5°")

    def test_loft_sections_out_of_order_are_refused(self):
        a, c, b = self.circle(2, name="A"), self.circle(3, z=20, name="C"), self.circle(5, z=10, name="B")
        self.doc.recompute()
        with self.assertRaises(ValueError) as ctx:
            self.make(shapes.LOFT, sections="%s,%s,%s" % (a.Name, c.Name, b.Name))
        self.assertIn("order", str(ctx.exception))

    def test_sweep_follows_a_changed_path(self):
        prof = self.circle(2, name="Prof")
        path = sketch(self.body, "XZ_Plane", "Path", [Part.LineSegment(App.Vector(0, 0, 0), App.Vector(0, 20, 0))])
        self.doc.recompute()
        f = self.make(shapes.SWEEP, profile=prof.Name, path=path.Name)
        v1 = f.Shape.Volume
        path.addGeometry(Part.LineSegment(App.Vector(0, 20, 0), App.Vector(10, 30, 0)))
        self.doc.recompute()
        self.assertGreater(f.Shape.Volume, v1 + 1)


class SweepWallTest(ShapesTest):
    """Sweep's Wall option: a helper Thickness under the Sweep, its removed faces the pipe's ends."""

    def hollow(self, **extra):
        prof = self.circle(5, role="YZ_Plane", name="Prof")
        path = sketch(self.body, "XY_Plane", "Path", [Part.LineSegment(App.Vector(0, 0, 0), App.Vector(40, 0, 0))])
        self.doc.recompute()
        v = dict(profile="Prof", path="Path", hollow=True, wall="1 mm", side="inside", ends="both_open")
        v.update(extra)
        return self.make(shapes.SWEEP, **v)

    def test_both_ends_open_is_a_tube(self):
        import math
        f = self.hollow()
        wall = shapes.wall_of(f)
        self.assertIsNotNone(wall)
        self.assertEqual(wall.TypeId, "PartDesign::Thickness")
        self.assertEqual(wall.InCadHelperOf, f.Name)
        self.assertIs(self.body.Tip, wall)
        self.assertNotIn("Invalid", wall.State, wall.getStatusString())
        expect = math.pi * (25 - 16) * 40
        self.assertAlmostEqual(wall.Shape.Volume, expect, delta=0.02 * expect)
        start, end = shapes._end_faces(f)
        self.assertNotEqual(start, end)

    def test_a_closed_end_keeps_its_cap(self):
        import math
        f = self.hollow(ends="start_closed")
        wall = shapes.wall_of(f)
        expect = math.pi * 25 * 40 - math.pi * 16 * 39  # a 1 mm cap at the start
        self.assertAlmostEqual(wall.Shape.Volume, expect, delta=0.02 * expect)
        self.assertEqual(shapes.SWEEP.read(self.doc, f)["ends"], "start_closed")
        f2 = shapes.SWEEP.update(self.doc, f, dict(shapes.SWEEP.read(self.doc, f), ends="end_closed"))
        self.doc.recompute()
        self.assertAlmostEqual(shapes.wall_of(f2).Shape.Volume, expect, delta=0.02 * expect)
        self.assertEqual(shapes.SWEEP.read(self.doc, f2)["ends"], "end_closed")
        self.assertEqual([v for v, _ in shapes._ENDS], ["both_open", "start_closed", "end_closed"])

    def test_read_round_trips_and_clearing_the_wall_removes_the_helper(self):
        f = self.hollow()
        v = shapes.SWEEP.read(self.doc, f)
        self.assertTrue(v["hollow"])
        self.assertEqual((v["wall"], v["side"], v["ends"]), ("1 mm", "inside", "both_open"))
        self.assertIs(kind_for(shapes.wall_of(f)), None, "a helper row opens no dialog of its own")
        shapes.SWEEP.update(self.doc, f, dict(v, hollow=False))
        self.doc.recompute()
        self.assertIsNone(shapes.wall_of(f))
        self.assertIs(self.body.Tip, f)
        self.assertFalse(any(o.TypeId == "PartDesign::Thickness" for o in self.body.Group))

    def test_solid_sweep_has_no_helper(self):
        f = self.hollow(hollow=False)
        self.assertIsNone(shapes.wall_of(f))
        self.assertIs(self.body.Tip, f)
