import unittest

import FreeCAD as App
import Part
from incad.core import document, feature_faces
from headless import util


class FeatureFacesTest(unittest.TestCase):
    """Inventor's browser link both ways: a feature row lights its faces on the shown solid, and a face clicked
    on the solid names the feature that made it."""

    def setUp(self):
        self.doc = util.new_doc("FF")
        self.body, self.pad = util.padded_part(self.doc, 10, incad=True)  # 20 x 10 x 10
        hole = self.body.newObject("Sketcher::SketchObject", "HoleSk")
        hole.AttachmentSupport = [(util.xy_plane(self.body), "")]
        hole.MapMode = "FlatFace"
        hole.AttachmentOffset = App.Placement(App.Vector(0, 0, 10), App.Rotation())
        hole.addGeometry(Part.Circle(App.Vector(5, 5, 0), App.Vector(0, 0, 1), 2))
        self.pocket = self.body.newObject("PartDesign::Pocket", "Pocket")
        self.pocket.Profile = hole
        self.pocket.Length = 4
        self.doc.recompute()
        self.fillet = self.body.newObject("PartDesign::Fillet", "Fillet")
        edge = [i + 1 for i, e in enumerate(self.pocket.Shape.Edges)
                if abs(e.CenterOfMass.x - 20) < 1e-6 and abs(e.CenterOfMass.y) < 1e-6][0]
        self.fillet.Base = (self.pocket, ["Edge%d" % edge])
        self.fillet.Radius = 1
        self.body.Tip = self.fillet
        self.doc.recompute()
        self.tip = self.fillet

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def faces(self, names):
        return [self.tip.Shape.getElement(n) for n in names]

    def test_a_pocket_row_lights_its_hole_faces(self):
        names = feature_faces.on_tip(self.pocket)
        self.assertTrue(names)
        for f in self.faces(names):
            c = f.CenterOfMass
            self.assertLess((App.Vector(c.x, c.y, 0) - App.Vector(5, 5, 0)).Length, 2.01, (names, c))

    def test_the_fillet_row_lights_the_round(self):
        names = feature_faces.on_tip(self.fillet)
        self.assertEqual(len(names), 1, names)
        self.assertEqual(self.faces(names)[0].Surface.TypeId, "Part::GeomCylinder")

    def test_a_clicked_face_names_its_feature(self):
        for feature in (self.pocket, self.fillet):
            for n in feature_faces.on_tip(feature):
                self.assertIs(feature_faces.creator(self.tip, n), feature, n)
        bottom = [i + 1 for i, f in enumerate(self.tip.Shape.Faces) if abs(f.CenterOfMass.z) < 1e-6][0]
        self.assertIs(feature_faces.creator(self.tip, "Face%d" % bottom), self.pad)

    def test_a_clicked_edge_names_its_feature(self):
        rim = [i + 1 for i, e in enumerate(self.tip.Shape.Edges) if e.Curve.TypeId == "Part::GeomCircle"
               and abs(e.CenterOfMass.z - 6) < 1e-6]
        self.assertTrue(rim)
        self.assertIs(feature_faces.creator(self.tip, "Edge%d" % rim[0]), self.pocket)

    def test_rolled_back_features_light_nothing(self):
        self.body.Tip = self.pocket
        self.doc.recompute()
        self.assertEqual(feature_faces.on_tip(self.fillet), [])
