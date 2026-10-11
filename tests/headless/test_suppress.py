"""Suppress / Unsuppress: a feature together with the pieces InCad made for it, and every thread at once (the user
works with threads off — a faster redraw — and turns them on at the end)."""
import unittest

import FreeCAD as App
import Part
from incad.core import document, suppress
from incad.features import thread
from headless import util
from headless.test_thread import cyl_face, shaft


class SuppressTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Sp")
        self.body = document.make_part(self.doc)
        shaft(self.doc, self.body, radius=8.0, length=20.0, name="Block")
        sk = self.body.newObject("Sketcher::SketchObject", "BoreSk")
        sk.AttachmentSupport = [(util.xy_plane(self.body), "")]
        sk.MapMode = "FlatFace"
        sk.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 1.5))
        self.bore = self.body.newObject("PartDesign::Pocket", "Bore")
        self.bore.Profile = sk
        self.bore.Type = "ThroughAll"
        self.bore.Reversed = True
        self.body.Tip = self.bore
        self.doc.recompute()
        self.plain = self.bore.Shape.Volume

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def make(self, **values):
        f = thread.create(self.doc, self.body, None, dict(thread.defaults(self.doc, self.body, None),
                                                          face=cyl_face(self.bore, 1.5), **values))
        self.doc.recompute()
        return f

    def test_a_thread_goes_off_with_its_fill_and_chamfer(self):
        f = self.make(size="M3", chamfer="both", chamfer_size="0.3 mm")
        self.assertEqual(len(thread.helpers_of(f)), 2)
        threaded = self.body.Shape.Volume
        self.assertIs(suppress.toggle(f), f)
        self.doc.recompute()
        self.assertTrue(all(o.Suppressed for o in [f] + thread.helpers_of(f)))
        self.assertAlmostEqual(self.body.Shape.Volume, self.plain, places=3)  # the part as before the thread
        suppress.toggle(f)
        self.doc.recompute()
        self.assertFalse(any(o.Suppressed for o in [f] + thread.helpers_of(f)))
        self.assertAlmostEqual(self.body.Shape.Volume, threaded, places=3)

    def test_the_profile_sketch_or_a_helper_means_the_thread(self):
        """User log: 'ThreadProfile cannot be suppressed' (the row picked was the thread's profile)."""
        f = self.make(size="M3", chamfer="start", chamfer_size="0.3 mm")
        self.assertIs(suppress.toggle(f.Profile[0]), f)
        self.assertTrue(f.Suppressed)
        self.assertIs(suppress.toggle(thread.helpers_of(f)[0]), f)
        self.assertFalse(f.Suppressed)
        self.assertIs(suppress.toggle(self.bore.Profile[0]), self.bore)  # any feature's own sketch: that feature

    def test_all_threads_off_and_on_keeps_one_suppressed_by_hand(self):
        a = self.make(size="M3", length_mode="distance", length="5 mm")
        b = self.make(size="M3", length_mode="distance", length="5 mm", flip=True)
        c = self.make(size="M3.5", length_mode="distance", length="4 mm", offset="8 mm")
        suppress.toggle(c)  # off by hand
        self.assertFalse(suppress.threads_off(self.doc))
        self.assertEqual(suppress.toggle_threads(self.doc), "off")
        self.doc.recompute()
        self.assertTrue(suppress.threads_off(self.doc))
        self.assertTrue(all(o.Suppressed for t in (a, b) for o in [t] + thread.helpers_of(t)))
        self.assertAlmostEqual(self.body.Shape.Volume, self.plain, places=3)
        self.assertEqual(suppress.toggle_threads(self.doc), "on")
        self.doc.recompute()
        self.assertFalse(suppress.threads_off(self.doc))
        self.assertFalse(any(o.Suppressed for t in (a, b) for o in [t] + thread.helpers_of(t)))
        self.assertTrue(c.Suppressed)  # it was off before: it stays off

    def test_no_threads_is_said(self):
        with self.assertRaises(ValueError) as ctx:
            suppress.toggle_threads(self.doc)
        self.assertIn("thread", str(ctx.exception).lower())

    def test_a_sketch_cannot_be_suppressed(self):
        sk = self.body.newObject("Sketcher::SketchObject", "Loose")
        with self.assertRaises(ValueError):
            suppress.toggle(sk)


if __name__ == "__main__":
    unittest.main()
