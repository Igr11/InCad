"""Fillet ▸ Full (the user: Full beside the radius arrows in the ordinary Fillet window): two edges and Full make a
full round between them (a Full Round step), the dialog reads it back with Full on, and Full switched off makes it an
ordinary fillet again — the Fillet dialog edits both."""
import unittest

import FreeCAD as App

from incad.features import dressup, full_round, kind_for
from headless import util

V = App.Vector


class FilletFull(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("FF")
        self.body, self.pad = util.padded_part(self.doc, 10, incad=True)  # 20 x 10, 10 high

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def top_long_edges(self):
        """The two long edges of the top (along x, 10 apart)."""
        shape = self.pad.Shape
        top = shape.BoundBox.ZMax
        out = []
        for i, e in enumerate(shape.Edges):
            a, b = e.Vertexes[0].Point, e.Vertexes[-1].Point
            if abs(a.z - top) < 1e-6 and abs(b.z - top) < 1e-6 and abs(a.y - b.y) < 1e-6:
                out.append("%s:Edge%d" % (self.pad.Name, i + 1))
        self.assertEqual(len(out), 2)
        return ",".join(out)

    def cylinders(self, f):
        return [x.Surface.Radius for x in f.Shape.Faces if x.Surface.TypeId == "Part::GeomCylinder"]

    def test_full_then_back_to_a_radius(self):
        k = dressup.FILLET
        values = dict(k.defaults(self.doc, self.body, None), edges=self.top_long_edges(), full=True)
        f = k.create(self.doc, self.body, None, values)
        self.doc.recompute()
        self.assertTrue(full_round.claims(f), f.TypeId)
        self.assertNotIn("Invalid", f.State, f.getStatusString())
        self.assertEqual([round(r, 6) for r in self.cylinders(f)], [5])  # half of the 10 mm width
        self.assertIs(kind_for(f), k)  # edited in the Fillet window
        back = k.read(self.doc, f)
        self.assertTrue(back["full"])
        self.assertEqual(sorted(back["edges"].split(",")), sorted(values["edges"].split(",")))
        g = k.update(self.doc, f, dict(back, full=False, radius="2 mm"))
        self.doc.recompute()
        self.assertEqual(g.TypeId, "PartDesign::Fillet")
        self.assertIs(self.body.Tip, g)
        self.assertNotIn("Invalid", g.State, g.getStatusString())
        self.assertEqual(sorted(round(r, 6) for r in self.cylinders(g)), [2, 2])
        self.assertFalse(k.read(self.doc, g)["full"])
        h = k.update(self.doc, g, dict(k.read(self.doc, g), full=True))
        self.doc.recompute()
        self.assertTrue(full_round.claims(h))
        self.assertEqual([round(r, 6) for r in self.cylinders(h)], [5])

    def test_full_waits_for_two_edges(self):
        self.assertTrue(dressup.FILLET.pending({"edges": "", "full": True}))
        self.assertFalse(dressup.FILLET.pending({"edges": "", "full": False}))
