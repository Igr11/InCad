import unittest

import FreeCAD as App
import Part
from incad.core import document, nodes, tree
from headless import util


def rows(doc):
    return [(d, n.kind, n.label, n.state) for d, n in nodes.flatten(tree.build(doc))]


def body_rows(doc):
    return [r for r in rows(doc) if r[1] not in ("part", "origin", "origin_item")]


class TreeTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Tree")

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_none(self):
        self.assertEqual(tree.build(None), [])

    def test_part_tree(self):
        body, pad = util.padded_part(self.doc, 10, incad=True)
        util.add_rect_sketch(body, name="Loose")
        body.Tip = pad
        self.doc.recompute()
        r = rows(self.doc)
        self.assertEqual(r[0], (0, "part", self.doc.Label, ""))
        self.assertEqual(r[1][:3], (1, "origin", "Origin"))
        self.assertIn("XY Plane", [x[2] for x in r])
        # a sketch no feature uses yet, right after the Tip, is work in progress: shown above End of Part (Inventor)
        self.assertEqual([x[:3] for x in body_rows(self.doc)],
                         [(1, "feature", "Pad"), (2, "sketch", "Sketch"), (1, "sketch", "Loose"),
                          (1, "end_of_part", "End of Part")])
        self.assertEqual(body_rows(self.doc)[2][3], "")

    def test_end_of_part_at_top(self):
        body, pad = util.padded_part(self.doc, 10, incad=True)
        document.set_end_of_part(body, None)
        b = body_rows(self.doc)
        self.assertEqual(b[0][1], "end_of_part")
        self.assertEqual(b[1][:3] + (b[1][3],), (1, "feature", "Pad", "rolled_back"))

    def test_error_state_and_reason(self):
        body, pad = util.padded_part(self.doc, 10, incad=True)
        pad.Length = 0
        self.doc.recompute()
        pad_node = [n for d, n in nodes.flatten(tree.build(self.doc)) if n.label == "Pad"][0]
        self.assertEqual(pad_node.state, "error")
        self.assertIn("zero", pad_node.tooltip.lower())

    def test_suppressed(self):
        body, pad = util.padded_part(self.doc, 10, incad=True)
        pad.Suppressed = True
        self.doc.recompute()
        pad_node = [n for d, n in nodes.flatten(tree.build(self.doc)) if n.label == "Pad"][0]
        self.assertEqual(pad_node.state, "suppressed")

    def test_parameters_hidden(self):
        document.make_part(self.doc)
        document.set_parameter(self.doc, "Width", "80 mm")
        self.assertNotIn("Parameters", [x[2] for x in rows(self.doc)])

    def test_multi_body(self):
        document.make_part(self.doc)
        document.new_solid(self.doc)
        r = rows(self.doc)
        self.assertIn((1, "solids", "Solid Bodies (2)", ""), r)
        self.assertIn((2, "body", "Solid2", ""), r)

    def test_plain_file_with_one_body(self):
        self.doc.addObject("PartDesign::Body", "Body")
        self.assertEqual([(n.kind, n.label, n.name) for n in tree.build(self.doc)],
                         [("message", "Not an InCad part", ""), ("action", "Convert to InCad Part", "convert"),
                          ("action", "Open in FreeCAD", "freecad")])

    def test_plain_empty_file(self):
        self.assertEqual([n.kind for n in tree.build(self.doc)], ["message", "action"])

    def test_sketch_detail(self):
        body, pad = util.padded_part(self.doc, 10, incad=True)
        sk = self.doc.getObject("Sketch")
        node = [n for d, n in nodes.flatten(tree.build(self.doc)) if n.label == "Sketch"][0]
        self.assertEqual(node.detail, "✓" if sk.FullyConstrained else "%d DOF" % sk.DoF)

    def test_new_sketch_in_an_empty_part_is_above_end_of_part(self):
        body = document.make_part(self.doc)
        util.add_rect_sketch(body, name="First")
        self.doc.recompute()
        self.assertEqual([x[:4] for x in body_rows(self.doc)],
                         [(1, "sketch", "First", ""), (1, "end_of_part", "End of Part", "")])


class HiddenRowsTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Th")
        self.body, self.pad = util.padded_part(self.doc, 10, incad=True)
        self.path = self.body.newObject("Sketcher::SketchObject", "Path")
        self.path.AttachmentSupport = [(util.xy_plane(self.body), "")]
        self.path.MapMode = "FlatFace"
        self.path.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(30, 0, 0)))
        self.doc.recompute()
        document.show_result(self.body)
        for o in document.origin_items(self.body):
            o.Visibility = False  # as FreeCAD's GUI leaves them in a new part (headless defaults them visible)

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def _state(self, label):
        return next(n.state for _, n in nodes.flatten(tree.build(self.doc)) if n.label == label)

    def test_hidden_origin_items_and_unused_sketches_are_marked(self):
        self.assertEqual(self._state("XY Plane"), "hidden")
        xy = [o for o in document.origin_items(self.body) if o.Role == "XY_Plane"][0]
        xy.Visibility = True
        self.assertEqual(self._state("XY Plane"), "")
        self.assertEqual(self._state("Path"), "", "an open contour is shown")
        document.set_visibility([self.path], False)
        self.assertEqual(self._state("Path"), "hidden")

    def test_consumed_sketch_is_not_marked(self):
        self.assertEqual(self._state("Sketch"), "")
