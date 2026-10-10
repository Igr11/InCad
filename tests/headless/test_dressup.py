import unittest

import FreeCAD as App
from incad.core import model
from incad.features import common, dressup, kind_for
from headless import util


class DressUpTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Du")
        self.body, self.pad = util.padded_part(self.doc, 10, incad=True)
        self.top_edges = ["Edge%d" % (i + 1) for i, e in enumerate(self.pad.Shape.Edges)
                          if abs(e.BoundBox.ZMin - 10) < 1e-6 and abs(e.BoundBox.ZMax - 10) < 1e-6]
        self.top_face = [i + 1 for i, f in enumerate(self.pad.Shape.Faces) if abs(f.CenterOfMass.z - 10) < 1e-6][0]

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def edges(self):
        return common.format_picks([(self.pad, e) for e in self.top_edges])

    def test_fillet(self):
        k = dressup.FILLET
        f = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None), edges=self.edges(),
                                                     radius="2 mm"))
        self.doc.recompute()
        self.assertAlmostEqual(f.Shape.Volume, 1951.56, places=1)
        self.assertIs(kind_for(f), k)
        self.assertEqual(k.read(self.doc, f)["radius"], "2 mm")
        model.set_model_parameter(self.doc, model.bound_parameter(f, "Radius"), "1 mm")
        self.assertGreater(f.Shape.Volume, 1951.56)

    def test_chamfer_types(self):
        k = dressup.CHAMFER
        for kind, volume in (("equal", 1971.33), ("two", 1945.33), ("angle", 1983.12)):
            f = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None), edges=self.edges(),
                                                         type=kind, size="1 mm", size2="2 mm", angle="30"))
            self.doc.recompute()
            self.assertAlmostEqual(f.Shape.Volume, volume, places=1, msg=kind)
            self.assertEqual(k.read(self.doc, f)["type"], kind)
            self.body.removeObject(f)
            self.doc.removeObject(f.Name)
            self.body.Tip = self.pad
            self.doc.recompute()

    def test_shell_inside_and_outside(self):
        k = dressup.SHELL
        face = "%s:Face%d" % (self.pad.Name, self.top_face)
        f = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None), faces=face,
                                                     thickness="1 mm", direction="inside"))
        self.doc.recompute()
        self.assertAlmostEqual(f.Shape.BoundBox.XLength, 20, places=3)
        f = k.update(self.doc, f, dict(k.read(self.doc, f), direction="outside"))
        self.doc.recompute()
        self.assertAlmostEqual(f.Shape.BoundBox.XLength, 22, places=3)

    def test_needs_edges(self):
        k = dressup.FILLET
        with self.assertRaises(ValueError):
            k.create(self.doc, self.body, None, k.defaults(self.doc, self.body, None))

    def test_edges_must_be_on_the_current_shape(self):
        import Part
        sk = self.body.newObject("Sketcher::SketchObject", "Cut")
        sk.AttachmentSupport = [(self.pad, "Face%d" % self.top_face)]
        sk.MapMode = "FlatFace"
        sk.addGeometry(Part.Circle(App.Vector(10, 5, 0), App.Vector(0, 0, 1), 2))
        pocket = self.body.newObject("PartDesign::Pocket", "Pocket")
        pocket.Profile = sk
        pocket.Length = 3
        self.body.Tip = pocket
        self.doc.recompute()
        k = dressup.FILLET
        with self.assertRaises(ValueError) as ctx:
            k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None), edges=self.edges()))
        self.assertIn("current shape", str(ctx.exception))


class ShellBeforeThreadTest(unittest.TestCase):
    """The user's real part: the kernel can't shell it once the thread is in. shell_before_thread puts End of
    Part above the thread, shells there (the picked top face mapped onto the earlier feature), and moves End of
    Part back, as one undo step; the chain after it recomputes."""

    def setUp(self):
        import os
        path = os.path.join(os.path.dirname(__file__), "..", "gui", "data", "p2_test_reordered.FCStd")
        self.doc = App.openDocument(os.path.abspath(path))
        self.doc.UndoMode = 1
        self.doc.recompute()

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def _values(self, body, thickness):
        tip = body.Tip
        top = max((i for i, f in enumerate(tip.Shape.Faces) if abs(f.normalAt(0, 0).z - 1) < 1e-6),
                  key=lambda i: tip.Shape.Faces[i].Area) + 1
        return {"faces": "%s:Face%d" % (tip.Name, top), "thickness": thickness, "direction": "inside"}

    def test_the_real_part_rolls_back_when_the_thread_fails_on_the_hollowed_shaft(self):
        """On this part the Shell before the thread computes, but the thread then cuts a 1.5 mm tube and the
        kernel returns invalid solids: without the search the step rolls back and says which feature fails."""
        from incad.core import document, safe
        body = document.primary_body(self.doc)
        tip = body.Tip
        n0 = self.doc.UndoCount
        r = safe.run_safely("Shell", lambda: dressup.shell_before_thread(self.doc, body, self._values(body, "1.5 mm"),
                                                                         search=False), self.doc)
        self.assertFalse(r.ok)
        self.assertIn("Thread then fails on the hollowed part", r.error)
        self.assertEqual(self.doc.UndoCount, n0, "rolled back: no step")
        self.assertFalse(any(o.TypeId == "PartDesign::Thickness" for o in body.Group))
        self.assertIs(body.Tip, tip)
        self.assertTrue(tip.Shape.isValid())

    def test_the_search_reports_that_no_wall_works_here(self):
        """This part refuses every wall (the thread on the hollowed shaft): the search tries half and a quarter,
        then says so and rolls back."""
        from incad.core import document, safe
        body = document.primary_body(self.doc)
        tip = body.Tip
        n0 = self.doc.UndoCount
        r = safe.run_safely("Shell", lambda: dressup.shell_before_thread(self.doc, body, self._values(body, "1.5 mm")),
                            self.doc)
        self.assertFalse(r.ok)
        self.assertIn("and so do walls of 0.75 mm and 0.375 mm", r.error)
        self.assertEqual(self.doc.UndoCount, n0)
        self.assertFalse(any(o.TypeId == "PartDesign::Thickness" for o in body.Group))
        self.assertIs(body.Tip, tip)


class ShellBeforeThreadShaftTest(unittest.TestCase):
    """A plain shaft with a thread: the Shell goes before the thread and the thread still cuts the tube."""

    def setUp(self):
        from headless import test_thread
        self.doc = util.new_doc("SbT")
        from incad.core import document
        self.body = document.make_part(self.doc)
        self.shaft = test_thread.shaft(self.doc, self.body)
        self.cyl_face = test_thread.cyl_face

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_shell_lands_before_the_thread(self):
        from incad.core import document, safe
        from incad.features import thread
        v = dict(thread.defaults(self.doc, self.body, None), face=self.cyl_face(self.shaft, 5),
                 standard="iso", size="M10", clearance="0 mm")
        thread.create(self.doc, self.body, None, v)
        self.doc.recompute()
        tip = self.body.Tip
        top = max((i for i, f in enumerate(tip.Shape.Faces) if abs(f.normalAt(0, 0).z - 1) < 1e-6),
                  key=lambda i: tip.Shape.Faces[i].Area) + 1
        values = {"faces": "%s:Face%d" % (tip.Name, top), "thickness": "1 mm", "direction": "inside"}
        r = safe.run_safely("Shell", lambda: dressup.shell_before_thread(self.doc, self.body, values), self.doc)
        self.assertTrue(r.ok, r.error)
        group = list(self.body.Group)
        f = r.value
        self.assertLess(group.index(f), group.index(next(o for o in group if o.TypeId.endswith("Helix"))))
        self.assertIs(self.body.Tip, tip)
        self.assertTrue(tip.Shape.isValid() and tip.Shape.Volume > 0)
