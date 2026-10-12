import os
import shutil
import tempfile
import unittest

import FreeCAD as App
from incad.core import assembly, document
from incad.features import common
from headless import util


def save_part(folder, name, w, h, length):
    doc = util.new_doc(name)
    body = document.make_part(doc)
    pad = util.add_pad(body, util.add_rect_sketch(body, w, h, "S"), length, "Pad")
    body.Tip = pad
    doc.recompute()
    path = os.path.join(folder, name + ".FCStd")
    doc.saveAs(path)
    return doc, path


class AssemblyTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="incad_asm_")
        self.plate_doc, self.plate = save_part(self.dir, "Plate", 40, 30, 10)
        self.block_doc, self.block = save_part(self.dir, "Block", 10, 10, 10)
        self.doc = App.newDocument("Asm")
        self.doc.UndoMode = 1
        assembly.make_assembly(self.doc, "mm")
        self.doc.saveAs(os.path.join(self.dir, "Asm.FCStd"))

    def tearDown(self):
        for name in list(App.listDocuments()):
            App.closeDocument(name)
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_marker_and_objects(self):
        self.assertTrue(assembly.is_assembly(self.doc))
        self.assertFalse(document.is_incad_part(self.doc))
        self.assertEqual(assembly.assembly_of(self.doc).TypeId, "Assembly::AssemblyObject")

    def test_place_grounds_the_first_and_puts_the_next_beside(self):
        a = assembly.place(self.doc, self.plate)
        b = assembly.place(self.doc, self.block)
        self.doc.recompute()
        self.assertEqual(assembly.components(self.doc), [a, b])
        self.assertTrue(assembly.is_grounded(a))
        self.assertFalse(assembly.is_grounded(b))
        self.assertFalse(a.Shape.BoundBox.intersect(b.Shape.BoundBox))
        c = assembly.place(self.doc, self.block)
        self.assertIs(c.LinkedObject, b.LinkedObject)
        self.assertEqual(len(assembly.components(self.doc)), 3)

    def test_ground_and_unground(self):
        a = assembly.place(self.doc, self.plate)
        assembly.unground(a)
        self.assertFalse(assembly.is_grounded(a))
        assembly.ground(a)
        assembly.ground(a)
        self.assertTrue(assembly.is_grounded(a))
        self.assertEqual(len([j for j in assembly.joints(self.doc) if hasattr(j, "ObjectToGround")]), 1)

    def test_create_part_next_to_the_assembly(self):
        link = assembly.create_part(self.doc, "Bracket")
        path = os.path.join(self.dir, "Bracket.FCStd")
        self.assertTrue(os.path.isfile(path))
        part_doc = link.LinkedObject.Document
        self.assertTrue(document.is_incad_part(part_doc))
        self.assertEqual(part_doc.FileName, path)
        self.assertIn(link, assembly.components(self.doc))

    def test_unsaved_assembly_is_refused_plainly(self):
        doc = App.newDocument("Unsaved")
        assembly.make_assembly(doc, "mm")
        with self.assertRaises(ValueError) as ctx:
            assembly.place(doc, self.plate)
        self.assertIn("Save the assembly first", str(ctx.exception))

    def test_picks_on_the_assembly_resolve_to_the_component(self):
        b = assembly.place(self.doc, self.block)
        asm = assembly.assembly_of(self.doc)
        self.assertEqual(common.resolve(asm, "%s.Body.Pad.Face5" % b.Name), (b, "Face5"))
        self.assertEqual(common.resolve(asm, "%s.Face5" % b.Name), (b, "Face5"))

    def test_browser_tree(self):
        from incad.core import tree
        from incad.features import constraints as C
        a = assembly.place(self.doc, self.plate)
        b = assembly.place(self.doc, self.block)
        self.doc.recompute()
        top = [i + 1 for i, f in enumerate(a.LinkedObject.Shape.Faces) if abs(f.CenterOfMass.z - 10) < 1e-6][0]
        bot = [i + 1 for i, f in enumerate(b.LinkedObject.Shape.Faces) if abs(f.CenterOfMass.z) < 1e-6][0]
        C.MATE.create(self.doc, None, None, dict(C.MATE.defaults(self.doc, None), first="%s:Face%d" % (a.Name, top),
                                                 second="%s:Face%d" % (b.Name, bot)))
        root = tree.build(self.doc)[0]
        self.assertEqual(root.kind, "assembly")
        comps = [n for n in root.children if n.kind == "component"]
        self.assertEqual([(n.label, n.detail) for n in comps], [("Plate", "grounded"), ("Block", "")])
        rel = [n for n in root.children if n.kind == "relationships"][0]
        self.assertEqual([n.label for n in rel.children], ["Mate"])
        # the user: no part's history in the assembly (Inventor shows each component's features under it)
        from incad.core.nodes import flatten
        rows = [n for _, n in flatten(comps[0].children)]
        self.assertTrue(any(n.kind == "feature" for n in rows), [(n.kind, n.label) for n in rows])
        self.assertEqual({n.name for n in rows}, {a.Name}, "every row stands for the component (double-click opens it)")
        self.assertFalse([n for n in rows if n.kind == "end_of_part"])

    def test_suppress_hide_and_remove_a_component(self):
        """The user: an assembly needs Hide / Show, Suppress, Edit and Remove on a part."""
        from incad.core import delete, tree
        from incad.features import constraints as C
        a = assembly.place(self.doc, self.plate)
        b = assembly.place(self.doc, self.block)
        self.doc.recompute()
        top = [i + 1 for i, f in enumerate(a.LinkedObject.Shape.Faces) if abs(f.CenterOfMass.z - 10) < 1e-6][0]
        bot = [i + 1 for i, f in enumerate(b.LinkedObject.Shape.Faces) if abs(f.CenterOfMass.z) < 1e-6][0]
        mate = C.MATE.create(self.doc, None, None, dict(C.MATE.defaults(self.doc, None),
                                                        first="%s:Face%d" % (a.Name, top),
                                                        second="%s:Face%d" % (b.Name, bot)))
        self.assertTrue(assembly.toggle_suppressed(b))
        self.assertFalse(b.Visibility)
        self.assertTrue(mate.Suppressed)
        comps = {n.name: n for n in tree.build(self.doc)[0].children if n.kind == "component"}
        self.assertEqual(comps[b.Name].state, "suppressed")
        self.assertFalse(assembly.toggle_suppressed(b))
        self.assertTrue(b.Visibility)
        self.assertFalse(mate.Suppressed)
        self.assertFalse(document.toggle_visibility([b]))  # Hide / Show on a component
        self.assertFalse(b.Visibility)
        name = b.Name
        delete.delete(b)  # Remove from Assembly: its constraint goes too, the part file stays
        self.assertIsNone(self.doc.getObject(name))
        self.assertEqual(len(assembly.components(self.doc)), 1)
        self.assertTrue(os.path.exists(self.block))

    def test_parts_changed_elsewhere_are_noticed_and_brought_in_on_request(self):
        """The user: after editing a part in its own tab the assembly should ask to update, never update by itself;
        declined, it shows that it needs an update until Refresh."""
        from incad.core import tree
        b = assembly.place(self.doc, self.block)
        self.doc.recompute()
        seen = assembly.parts_signature(self.doc)
        self.assertFalse(assembly.parts_changed(self.doc, seen))
        pad = self.block_doc.getObject("Pad")
        pad.Length = 25
        self.block_doc.recompute()
        self.assertTrue(assembly.parts_changed(self.doc, seen))
        assembly.mark_needs_update(self.doc)  # declined
        root = tree.build(self.doc)[0]
        self.assertIn("needs update", root.detail.lower())
        assembly.bring_parts_in(self.doc)  # Refresh (or Yes)
        self.assertAlmostEqual(b.Shape.BoundBox.ZLength, 25, places=6)
        self.assertFalse(assembly.needs_update(self.doc))
        self.assertNotIn("needs update", tree.build(self.doc)[0].detail.lower())

    def test_placing_the_assembly_into_itself_is_refused(self):
        with self.assertRaises(ValueError) as ctx:
            assembly.place(self.doc, self.doc.FileName)
        self.assertIn("itself", str(ctx.exception))

    def test_placing_an_assembly_that_contains_this_one_is_refused(self):
        outer = App.newDocument("Outer")
        assembly.make_assembly(outer, "mm")
        outer.saveAs(os.path.join(self.dir, "Outer.FCStd"))
        assembly.place(outer, self.doc.FileName)
        outer.save()
        with self.assertRaises(ValueError) as ctx:
            assembly.place(self.doc, outer.FileName)
        self.assertIn("contains", str(ctx.exception))


class AssemblyThreadsTest(unittest.TestCase):
    """The user: a part placed in an assembly with its threads off could not get them back from the assembly."""

    def setUp(self):
        import Part
        from incad.core import suppress
        from incad.features import thread
        from headless.test_thread import cyl_face, shaft
        self.dir = tempfile.mkdtemp(prefix="incad_asmt_")
        d = util.new_doc("Nut")
        body = document.make_part(d)
        shaft(d, body, radius=8.0, length=20.0, name="Block")
        sk = body.newObject("Sketcher::SketchObject", "BoreSk")
        sk.AttachmentSupport = [(util.xy_plane(body), "")]
        sk.MapMode = "FlatFace"
        sk.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 1.5))
        bore = body.newObject("PartDesign::Pocket", "Bore")
        bore.Profile = sk
        bore.Type = "ThroughAll"
        bore.Reversed = True
        body.Tip = bore
        d.recompute()
        thread.create(d, body, None, dict(thread.defaults(d, body, None), face=cyl_face(bore, 1.5), size="M3"))
        d.recompute()
        suppress.toggle_threads(d)  # made into an assembly with its threads off
        d.recompute()
        self.nut = os.path.join(self.dir, "Nut.FCStd")
        d.saveAs(self.nut)
        self.nut_doc = d
        _, self.block = save_part(self.dir, "Block", 10, 10, 10)
        self.doc = App.newDocument("AsmT")
        assembly.make_assembly(self.doc, "mm")
        self.doc.saveAs(os.path.join(self.dir, "AsmT.FCStd"))
        assembly.place(self.doc, self.nut)
        assembly.place(self.doc, self.block)

    def tearDown(self):
        for name in list(App.listDocuments()):
            App.closeDocument(name)
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_threads_come_back_from_the_assembly_and_go_off_again(self):
        from incad.core import suppress
        self.assertTrue(assembly.threads_off(self.doc))
        self.assertEqual(assembly.toggle_threads(self.doc), "on")
        self.assertFalse(suppress.threads_off(self.nut_doc))
        self.assertFalse(assembly.threads_off(self.doc))
        self.assertEqual(assembly.toggle_threads(self.doc), "off")
        self.assertTrue(suppress.threads_off(self.nut_doc))

    def test_an_assembly_without_threads_says_so(self):
        d = App.newDocument("AsmN")
        assembly.make_assembly(d, "mm")
        d.saveAs(os.path.join(self.dir, "AsmN.FCStd"))
        assembly.place(d, self.block)
        with self.assertRaises(ValueError) as ctx:
            assembly.toggle_threads(d)
        self.assertIn("has threads", str(ctx.exception))

