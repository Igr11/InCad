import os
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


class OrphanProfileTest(unittest.TestCase):
    """An area profile whose feature is gone (deleted, or never made) must not hide the user's sketch: on
    2026-10-10 Sketch15 vanished from the tree this way and the user could not find it."""

    def setUp(self):
        self.doc = util.new_doc("Orph")
        self.body, self.pad = util.padded_part(self.doc, 10, incad=True)

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_sketch_whose_area_profile_lost_its_feature_is_listed(self):
        from incad.core import regions
        sk = util.add_rect_sketch(self.body, name="Cross")
        sk.addGeometry(Part.LineSegment(App.Vector(10, -5, 0), App.Vector(10, 15, 0)))
        self.doc.recompute()
        prof = regions.make_profile(self.doc, self.body, sk, regions.region_at(sk, App.Vector(5, 5, 0)))
        labels = [l for _, k, l, _ in rows(self.doc)]
        self.assertIn("Cross", labels, labels)
        self.assertNotIn(prof.Label, labels, labels)
        cut = self.body.newObject("PartDesign::Pocket", "Cut")
        cut.Profile = prof
        cut.Length = 3
        self.doc.recompute()
        flat = [(d, k, l) for d, k, l, _ in rows(self.doc)]
        self.assertNotIn((1, "sketch", "Cross"), flat, flat)  # used now: shown under its Cut only
        self.assertIn((2, "sketch", "Cross"), flat, flat)


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

    def test_consumed_sketch_is_not_marked_unless_the_user_hid_it(self):
        self.assertEqual(self._state("Sketch"), "")
        sk = self.doc.getObject("Sketch")
        document.set_visibility([sk], True)
        self.assertEqual(self._state("Sketch"), "")
        document.set_visibility([sk], False)
        self.assertEqual(self._state("Sketch"), "hidden", "hidden by choice: dimmed like any other")

    def test_hidden_work_plane_is_marked(self):
        wp = self.body.newObject("PartDesign::Plane", "WorkPlane")
        self.doc.recompute()
        self.assertIn(self._state("WorkPlane"), ("", "rolled_back"))  # after the tip: rolled back, not hidden
        wp.Visibility = False
        self.assertEqual(self._state("WorkPlane"), "hidden")


class SecondSolidTest(unittest.TestCase):
    """One End of Part for the part: a second Solid lists its features without a marker of its own."""

    def setUp(self):
        self.doc = util.new_doc("Ts2")
        self.body, self.pad = util.padded_part(self.doc, 10, incad=True)
        far = util.add_rect_sketch(self.body, name="Far")
        far.AttachmentOffset = App.Placement(App.Vector(50, 50, 0), App.Rotation())
        self.doc.recompute()
        from incad.features import extrude
        self.before = (self.body.Tip.Label if self.body.Tip else None, extrude._solids(self.body.Tip))
        self.box = extrude.create(self.doc, self.body, far, extrude.defaults(self.doc, self.body, far))
        self.doc.recompute()

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_one_history_for_the_part(self):
        """Inventor's browser: every Solid's features in the one list at the part level, in the order made, the
        other Solids' rows saying which Solid; the Solid Bodies folder lists names only; one End of Part."""
        from incad.features import extrude
        self.assertEqual(len(document.bodies(self.doc)), 2,
                         (self.before, self.box.State, extrude._solids(self.box), self.box.getParentGeoFeatureGroup().Label))
        flat = [(d, n.kind, n.label, n.detail) for d, n in nodes.flatten(tree.build(self.doc))]
        self.assertEqual([(d, k, l, t) for d, k, l, t in flat if k in ("solids", "body")],
                         [(1, "solids", "Solid Bodies (2)", ""), (2, "body", "Solid1", ""), (2, "body", "Solid2", "")])
        self.assertEqual([(l, t) for d, k, l, t in flat if d == 1 and k in ("feature", "sketch", "end_of_part")],
                         [("Pad", ""), ("Extrude", "Solid2"), ("End of Part", "")])
        top = util.add_rect_sketch(self.body, name="Top")
        top.AttachmentOffset = App.Placement(App.Vector(0, 0, 10), App.Rotation())
        pad2 = util.add_pad(self.body, top, 5, name="Pad2")
        self.body.Tip = pad2
        self.doc.recompute()
        flat = [(d, n.kind, n.label, n.detail, n.state) for d, n in nodes.flatten(tree.build(self.doc))]
        self.assertEqual([(l, t) for d, k, l, t, s in flat if d == 1 and k in ("feature", "end_of_part")],
                         [("Pad", ""), ("Extrude", "Solid2"), ("Pad2", ""), ("End of Part", "")])
        document.set_end_of_part_at(self.doc, self.pad)
        flat = [(d, n.kind, n.label, n.detail, n.state) for d, n in nodes.flatten(tree.build(self.doc))]
        self.assertEqual([(l, s) for d, k, l, t, s in flat if d == 1 and k in ("feature", "end_of_part")],
                         [("Pad", ""), ("End of Part", ""), ("Extrude", "rolled_back"), ("Pad2", "rolled_back")])

    def test_body_of(self):
        other = self.box.getParentGeoFeatureGroup()
        self.assertIs(document.body_of(self.box), other)
        self.assertIs(document.body_of(self.pad), self.body)
        self.assertIs(document.body_of([o for o in other.Origin.OriginFeatures if o.Role == "XY_Plane"][0]), other)
        self.assertIsNone(document.body_of(None))


class UsedUpToolTreeTest(unittest.TestCase):
    def setUp(self):
        from incad.features import combine
        self.doc = util.new_doc("Ut")
        self.part = document.make_part(self.doc)
        box = self.part.newObject("PartDesign::AdditiveBox", "Box")
        self.part.Tip = box
        self.tool = document.new_solid(self.doc)
        pin = self.tool.newObject("PartDesign::AdditiveCylinder", "Pin")
        pin.Radius, pin.Height = 2, 30
        self.tool.Tip = pin
        self.doc.recompute()
        self.f = combine.create(self.doc, self.part, None, dict(combine.defaults(self.doc, self.part),
                                                                tools=self.tool.Name, operation="cut",
                                                                clearance="0 mm"))
        self.doc.recompute()

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def rows(self):
        return tree.build(self.doc)[0].children

    def test_a_used_up_tool_sits_under_its_boolean(self):
        rows = self.rows()
        names = [n.name for n in rows]
        self.assertNotIn("Pin", names)  # not in the main history
        node = next(n for n in rows if n.name == self.f.Name)
        tool = next(c for c in node.children if c.kind == "body")
        self.assertEqual(tool.name, self.tool.Name)
        self.assertIn("Pin", [c.name for c in tool.children])
        solids = next((n for n in rows if n.kind == "solids"), None)
        self.assertIsNone(solids)  # one solid left that is not used up: no folder

    def test_keep_tool_on_puts_it_back_in_the_list(self):
        from incad.features import combine
        combine.update(self.doc, self.f, dict(combine.read(self.doc, self.f), keep_tool=True))
        self.doc.recompute()
        rows = self.rows()
        self.assertIn("Pin", [n.name for n in rows])
        solids = next(n for n in rows if n.kind == "solids")
        self.assertEqual(solids.label, "Solid Bodies (2)")


class NestedUsedUpToolTreeTest(unittest.TestCase):
    """Review: pin A cut into tool B (Keep tool off), B cut into the part: A vanished from the browser."""
    def test_a_tool_used_up_inside_a_used_up_tool_is_under_it(self):
        from incad.features import combine
        doc = util.new_doc("Nu")
        part = document.make_part(doc)
        part.Tip = part.newObject("PartDesign::AdditiveBox", "Box")
        b = document.new_solid(doc)
        b.Tip = b.newObject("PartDesign::AdditiveCylinder", "Plug")
        a = document.new_solid(doc)
        a.Tip = a.newObject("PartDesign::AdditiveCylinder", "PinA")
        doc.recompute()
        cut_b = combine.create(doc, b, None, dict(combine.defaults(doc, b), tools=a.Name, operation="cut",
                                                  clearance="0 mm"))
        doc.recompute()
        cut_part = combine.create(doc, part, None, dict(combine.defaults(doc, part), tools=b.Name, operation="cut",
                                                        clearance="0 mm"))
        doc.recompute()

        def names(nodes):
            out = []
            for n in nodes:
                out.append(n.name)
                out.extend(names(n.children))
            return out
        self.assertIn("PinA", names(tree.build(doc)))
        App.closeDocument(doc.Name)


class AssemblyRowsTest(unittest.TestCase):
    def setUp(self):
        import tempfile
        from headless.test_assembly import save_part
        from incad.core import assembly
        self.dir = tempfile.mkdtemp(prefix="incad_tree_asm_")
        _, plate = save_part(self.dir, "Plate", 40, 30, 10)
        _, block = save_part(self.dir, "Block", 10, 10, 10)
        self.doc = App.newDocument("Asm")
        self.doc.UndoMode = 1
        assembly.make_assembly(self.doc, "mm")
        self.doc.saveAs(os.path.join(self.dir, "Asm.FCStd"))
        self.a, self.b = assembly.place(self.doc, plate), assembly.place(self.doc, block)

    def tearDown(self):
        import shutil
        for name in list(App.listDocuments()):
            App.closeDocument(name)
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_a_suppressed_constraint_row_says_so(self):
        from incad.core import tree
        from incad.features import constraints as C
        top = [i + 1 for i, f in enumerate(self.a.LinkedObject.Shape.Faces) if abs(f.CenterOfMass.z - 10) < 1e-6][0]
        bot = [i + 1 for i, f in enumerate(self.b.LinkedObject.Shape.Faces) if abs(f.CenterOfMass.z) < 1e-6][0]
        j = C.MATE.create(self.doc, None, None, dict(C.MATE.defaults(self.doc, None), first="%s:Face%d" % (self.a.Name, top),
                                                     second="%s:Face%d" % (self.b.Name, bot)))
        C.toggle_suppressed(j)
        rel = [n for n in tree.build(self.doc)[0].children if n.kind == "relationships"][0]
        self.assertEqual([(n.name, n.state) for n in rel.children], [(j.Name, "suppressed")])

    def test_component_rows_show_the_last_count(self):
        from incad.core import dof, tree
        dof._CACHE.clear()
        detail = lambda: {n.name: n.detail for n in tree.build(self.doc)[0].children if n.kind == "component"}
        self.assertEqual(detail(), {self.a.Name: "grounded", self.b.Name: ""})  # not counted yet: nothing shown
        dof.ensure(self.doc)
        self.assertEqual(detail(), {self.a.Name: "grounded", self.b.Name: "DOF 6"})
        dof._CACHE[self.doc.Name] = (dof.signature(self.doc),
                                     {self.b.Name: dof.Freedom(None, [], [], "Could not count: the solver failed")})
        node = [n for n in tree.build(self.doc)[0].children if n.name == self.b.Name][0]
        self.assertEqual((node.detail, node.tooltip), ("DOF ?", "Could not count: the solver failed"))
