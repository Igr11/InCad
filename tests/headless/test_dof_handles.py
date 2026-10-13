"""DOF handles with a stand-in orthographic view: an arrow seen end-on is no handle and never slides (it would fling
the part); a failing clean-up still aborts the drag's step."""
import os
import shutil
import tempfile
import unittest

import FreeCAD as App
from incad.core import assembly, dof
from incad.features import constraints as C
from incad.ui import dof_handles as H
from headless.test_assembly import save_part
from headless.test_dof import fz


class Viewport:
    def devicePixelRatioF(self):
        return 1.0

    def height(self):
        return 600


class GraphicsView:
    def __init__(self, vp):
        self.vp = vp

    def viewport(self):
        return self.vp


class View:
    """Orthographic, 10 px/mm. front: looking along +Y (screen x = X, up = Z); top: looking down (x = X, up = Y)."""

    def __init__(self, kind):
        self.kind, self.vp = kind, Viewport()

    def getPointOnViewport(self, v):  # Coin: device px, bottom-left origin
        return (400 + 10 * v.x, 300 + 10 * (v.z if self.kind == "front" else v.y))

    def getObjectsInfo(self, pos):
        return []

    def graphicsView(self):
        return GraphicsView(self.vp)


class Shell:
    feature_session = status = asm_drag = None

    def schedule_refresh(self):
        pass

    def dof_display_changed(self):
        pass


class HandlesTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="incad_handles_")
        _, plate = save_part(self.dir, "Plate", 40, 30, 10)
        _, block = save_part(self.dir, "Block", 10, 10, 10)
        self.doc = App.newDocument("Asm")
        self.doc.UndoMode = 1
        assembly.make_assembly(self.doc, "mm")
        self.doc.saveAs(os.path.join(self.dir, "Asm.FCStd"))
        self.a = assembly.place(self.doc, plate)
        self.b = assembly.place(self.doc, block)
        C.MATE.create(self.doc, None, None, dict(C.MATE.defaults(self.doc, None), first=fz(self.a, 10),
                                                 second=fz(self.b, 0)))
        App.setActiveDocument(self.doc.Name)
        # on the plate: slides along X and Y, a turn about Z (as dof.compute finds them, axis-aligned for the test)
        self.f = dof.Freedom(3, [App.Vector(1, 0, 0), App.Vector(0, 1, 0)], [(App.Vector(5, 5, 5), App.Vector(0, 0, 1))], "")
        self.centre = self.b.Shape.BoundBox.Center
        self.hs = dof.handles(self.f, self.b.Placement, self.centre, 6.0)
        self.handles = H.Handles(Shell())

    def tearDown(self):
        for name in list(App.listDocuments()):
            App.closeDocument(name)
        shutil.rmtree(self.dir, ignore_errors=True)

    def grounds(self):
        return len([j for j in assembly.joints(self.doc) if hasattr(j, "ObjectToGround")])

    def test_an_arrow_seen_end_on_is_no_handle(self):
        view = View("front")  # Y points at the viewer: that arrow is a dot at the centre
        self.handles.set_drawn(self.doc.Name, self.b.Name, self.hs, 6.0, view)
        keys = [k for k, _ in self.handles._candidates(view, view.vp)]
        self.assertEqual(keys, [0, 2], "the X arrow and the arc, never the end-on Y arrow")
        x, y = H.screen(view, view.vp, self.centre)
        self.assertNotEqual(self.handles.hit(view, view.vp, x, y), 1)
        top = View("top")
        self.handles.set_drawn(self.doc.Name, self.b.Name, self.hs, 6.0, top)
        self.assertEqual([k for k, _ in self.handles._candidates(top, top.vp)], [0, 1, 2], "seen from above: both")

    def test_an_end_on_slide_is_refused_before_any_change(self):
        view = View("front")
        x, y = H.screen(view, view.vp, self.centre)
        drag = H.HandleDrag(self.handles, self.doc, self.b, self.hs, [(1, 0.0, (0.0, 0.0))], view, view.vp, x, y)
        start = App.Placement(self.b.Placement)
        n0 = len(self.doc.UndoNames)
        with self.assertRaises(RuntimeError):
            drag.move(x + 10, y)
        self.assertFalse(self.doc.HasPendingTransaction)
        self.assertTrue(self.b.Placement.isSame(start, 1e-9) and len(self.doc.UndoNames) == n0)
        self.assertEqual(self.grounds(), 1, "only the plate's")

    def test_a_turn_drag_is_one_step(self):
        view = View("top")
        x, y = H.screen(view, view.vp, self.hs[2].line[0])
        drag = H.HandleDrag(self.handles, self.doc, self.b, self.hs, [(2, 0.0, (0.0, 1.0))], view, view.vp, x, y)
        start = App.Placement(self.b.Placement)
        arc = self.hs[2]
        drag.move(*H.screen(view, view.vp, arc.point + arc.w * arc.radius))  # a quarter turn along the arc
        self.assertEqual(self.grounds(), 1)  # the plate's own; nothing else is free
        self.assertTrue(drag.finish())
        self.assertEqual(self.doc.UndoNames[0], "Move part")
        rel = self.b.Placement.multiply(start.inverse())
        self.assertAlmostEqual(abs(rel.Rotation.Angle), 3.14159265 / 2, places=3)

    def test_a_failing_clean_up_still_aborts_the_step(self):
        view = View("top")
        x, y = H.screen(view, view.vp, self.hs[0].line[1])
        drag = H.HandleDrag(self.handles, self.doc, self.b, self.hs, [(0, 0.0, (1.0, 0.0))], view, view.vp, x, y)
        start = App.Placement(self.b.Placement)
        n0 = len(self.doc.UndoNames)
        drag.move(x + 50, y)
        self.assertTrue(self.doc.HasPendingTransaction)
        self.assertFalse(self.b.Placement.isSame(start, 1e-9))
        real = assembly.unground

        def boom(link):
            raise RuntimeError("boom")
        drag._held = [self.a.Name]
        assembly.unground = boom
        try:
            with self.assertRaises(RuntimeError):
                drag.finish()
        finally:
            assembly.unground = real
        self.assertFalse(self.doc.HasPendingTransaction, "the step is aborted")
        self.assertTrue(self.b.Placement.isSame(start, 1e-9), "the part back where it was")
        self.assertEqual(len(self.doc.UndoNames), n0)


if __name__ == "__main__":
    unittest.main()
