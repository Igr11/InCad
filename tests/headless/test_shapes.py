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
