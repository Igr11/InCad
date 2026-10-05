import unittest

import FreeCAD as App
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
        self.assertEqual([x[:3] for x in body_rows(self.doc)],
                         [(1, "feature", "Pad"), (2, "sketch", "Sketch"), (1, "end_of_part", "End of Part"),
                          (1, "sketch", "Loose")])
        self.assertEqual(body_rows(self.doc)[-1][3], "rolled_back")

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
