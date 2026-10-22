"""End of Part before sketches, Texts and work features (the user: it jumped back below them — FreeCAD's Tip is only
ever a solid feature): they roll back below it, hidden while there and shown again when End of Part goes below them;
a sketch made meanwhile shows above it; a feature added after it ends the mark."""
import unittest

import FreeCAD as App

from incad.core import document, tree
from headless import util

V = App.Vector


def rows(doc):
    part = tree.build(doc)[0]
    return [(n.kind, n.label, n.state) for n in part.children if n.kind in ("feature", "sketch", "end_of_part")]


class EndOfPartMark(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Eop")
        self.body = document.make_part(self.doc)
        self.pad = util.add_pad(self.body, util.add_rect_sketch(self.body, 20, 10, "Base"), 10)
        self.body.Tip = self.pad
        cut = util.add_rect_sketch(self.body, 4, 4, "Hole")
        cut.AttachmentOffset = App.Placement(V(3, 3, 10), App.Rotation())
        self.pocket = self.body.newObject("PartDesign::Pocket", "Cut")
        self.pocket.Profile = cut
        self.pocket.Length = 3
        self.body.Tip = self.pocket
        self.plane = self.body.newObject("PartDesign::Plane", "WorkPlane")
        self.plane.AttachmentSupport = [(util.xy_plane(self.body), "")]
        self.plane.MapMode = "FlatFace"
        import Part
        self.sk = self.body.newObject("Sketcher::SketchObject", "Sketch3")  # an open line: shown while unused
        self.sk.AttachmentSupport = [(util.xy_plane(self.body), "")]
        self.sk.MapMode = "FlatFace"
        self.sk.addGeometry(Part.LineSegment(V(0, 0, 0), V(5, 5, 0)))
        self.doc.recompute()
        document.show_result(self.body)
        self.assertTrue(self.sk.Visibility)

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def labels(self):
        return [label for _, label, _ in rows(self.doc)]

    def test_default_work_in_progress_above_the_marker(self):
        self.assertEqual(self.labels()[-1], "End of Part")

    def test_before_the_work_plane_and_sketch_and_back(self):
        document.set_end_of_part_at(self.doc, self.pocket)
        r = rows(self.doc)
        names = [label for _, label, _ in r]
        self.assertEqual(names.index("End of Part"), names.index("Cut") + 1)
        states = {label: state for _, label, state in r}
        self.assertEqual(states["Sketch3"], "rolled_back")
        self.assertEqual(states["WorkPlane"], "rolled_back")
        self.assertFalse(self.sk.Visibility)
        self.assertIs(self.body.Tip, self.pocket)
        document.set_end_of_part_at(self.doc, self.sk)  # below everything again
        self.assertEqual(self.labels()[-1], "End of Part")
        self.assertTrue(self.sk.Visibility)
        self.assertIsNone(document.end_marker(self.doc))

    def test_between_the_work_plane_and_the_sketch(self):
        document.set_end_of_part_at(self.doc, self.plane)
        states = {label: state for _, label, state in rows(self.doc)}
        names = self.labels()
        self.assertEqual(names.index("End of Part"), names.index("WorkPlane") + 1)
        self.assertEqual(states["WorkPlane"], "")  # above it: applied, not greyed
        self.assertEqual(states["Sketch3"], "rolled_back")

    def test_before_everything(self):
        document.set_end_of_part_at(self.doc, None)
        self.assertEqual(self.labels()[0], "End of Part")
        self.assertIsNone(self.body.Tip)
        self.assertFalse(self.sk.Visibility)

    def test_a_sketch_made_meanwhile_is_above_the_marker(self):
        document.set_end_of_part_at(self.doc, self.pocket)
        new = util.add_rect_sketch(self.body, 2, 2, "Fresh")
        self.doc.recompute()
        names = self.labels()
        self.assertLess(names.index("Fresh"), names.index("End of Part"))
        self.assertGreater(names.index("Sketch3"), names.index("End of Part"))

    def test_a_feature_added_after_it_ends_the_mark(self):
        document.set_end_of_part_at(self.doc, self.pocket)
        pad2 = util.add_pad(self.body, util.add_rect_sketch(self.body, 2, 2, "More"), 3)
        self.body.Tip = pad2
        self.doc.recompute()
        self.assertTrue(document.settle_end_marker(self.doc))
        self.assertTrue(self.sk.Visibility)
        self.assertEqual(self.labels()[-1], "End of Part")
