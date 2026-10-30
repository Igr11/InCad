"""Solids of STL triangles are kept out of Booleans (the user's ProstoCAD stood 30 minutes on an AI's cut of one):
the check itself and the Boolean feature."""
import unittest

import FreeCAD as App
import Mesh
import Part

from incad.core import faceted
from headless import util


def faceted_solid():
    m = Mesh.createSphere(10.0, 60)
    sh = Part.Shape()
    sh.makeShapeFromMesh(m.Topology, 0.05)
    return Part.makeSolid(sh)


class FacetedTest(unittest.TestCase):
    def test_triangles_are_told_from_ordinary_parts(self):
        tri = faceted_solid()
        self.assertGreater(len(tri.Faces), faceted.LEAST)
        self.assertTrue(faceted.is_faceted(tri))
        self.assertFalse(faceted.is_faceted(Part.makeBox(10, 10, 10)))
        many = Part.makeBox(10, 10, 10)
        for k in range(40):  # an ordinary part with many faces: holes, not triangles
            many = many.cut(Part.makeCylinder(0.1, 10, App.Vector(0.2 + 0.24 * k, 5, 0)))
        self.assertFalse(faceted.is_faceted(many, least=50))


class BooleanFeatureTest(unittest.TestCase):
    def test_a_boolean_with_a_solid_of_triangles_is_refused(self):
        from incad.core import document
        from incad.features import combine
        doc = util.new_doc("Fb")
        try:
            a = document.make_part(doc)
            sk = util.add_rect_sketch(a, 30, 30)
            a.Tip = util.add_pad(a, sk, 5)
            b = doc.addObject("PartDesign::Body", "Tri")
            base = doc.addObject("Part::Feature", "TriShape"); base.Shape = faceted_solid()
            b.BaseFeature = base
            doc.recompute()
            values = dict(combine.defaults(doc, a, None), base="%s:" % a.Name, tools="%s:" % b.Name, operation="cut",
                          clearance="0 mm")
            with self.assertRaises(ValueError) as hit:
                combine.create(doc, a, None, values)
            self.assertIn("STL's triangles", str(hit.exception))
        finally:
            App.closeDocument(doc.Name)


if __name__ == "__main__":
    unittest.main()
