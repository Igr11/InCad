"""Move Face on the user's own body (tests/gui/data/ellipse_band.FCStd, a copy of their file): its elliptic band —
the largest straight round wall of the part — offset ± in every mode, valid, the band at exactly d. The part is a
Shell with 1 mm walls: the move is 0.4 mm (more than the wall inward would cut through it — refused, as it should)."""
import os
import shutil
import tempfile
import unittest

import FreeCAD as App
import Part

from incad.core import document, round_wall as rw
from incad.features import move_face

DATA = os.path.join(os.environ["INCAD_REPO"], "tests", "gui", "data", "ellipse_band.FCStd")


class UserBody(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        path = os.path.join(self.tmp, "body.FCStd")
        shutil.copy(DATA, path)
        self.doc = App.openDocument(path)
        self.doc.recompute()
        self.body = document.primary_body(self.doc)
        self.tip = self.body.Tip

    def tearDown(self):
        App.closeDocument(self.doc.Name)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def band(self):
        """The outer elliptic band: the round wall the material lies inside of (the shell's inner walls face the other
        way), the largest of those."""
        shape = self.tip.Shape
        outer = []
        for i, f in enumerate(shape.Faces, 1):
            if not rw.is_round_wall(f):
                continue
            faces, a = rw.pieces(shape, f)
            try:
                wire = rw.section(faces, a, *rw.extent(faces, a))
            except ValueError:
                continue
            if rw.material_inside(faces, wire, a) and f.BoundBox.ZMax <= 8.0 + 1e-6:  # below the top fillet
                outer.append((i, f))
        return max(outer, key=lambda w: w[1].Area)

    def test_more_than_the_shell_wall_inward_is_refused(self):
        i, _ = self.band()
        values = dict(move_face.defaults(self.doc, self.body, None), faces="%s:Face%d" % (self.tip.Name, i),
                      distance="-1 mm", mode="step")
        with self.assertRaises(ValueError) as e:
            move_face.create(self.doc, self.body, None, values)
        self.assertEqual(str(e.exception), rw.mf.TOO_LARGE_MSG)

    def test_every_mode_both_ways(self):
        for mode in ("step", "together", "inventor"):
            for d in ("0.4 mm", "-0.4 mm"):
                i, wall = self.band()  # afresh: each recompute of the Shell may number its faces anew
                values = dict(move_face.defaults(self.doc, self.body, None), faces="%s:Face%d" % (self.tip.Name, i),
                              distance=d, mode=mode)
                try:
                    f = move_face.create(self.doc, self.body, None, values)
                except ValueError as e:  # blends next to the band: Inventor can't follow them; Together inward waits
                    expected = {("inventor", "0.4 mm"): rw.mf.ROUND_MSG, ("inventor", "-0.4 mm"): rw.mf.ROUND_MSG,
                                ("together", "-0.4 mm"): rw.INWARD_BLEND_MSG}
                    self.assertEqual(str(e), expected.get((mode, d)), (mode, d))
                    continue
                self.doc.recompute()
                self.assertNotIn("Invalid", f.State, (mode, d, f.getStatusString()))
                self.assertTrue(f.Shape.isValid(), (mode, d))
                # OCC may split the moved band into several faces: the nearest round wall to the old band is it (the
                # shell's inner wall is 1 mm in)
                walls = [g for g in f.Shape.Faces if rw.is_round_wall(g)]
                moved = Part.makeCompound(walls)
                for e in wall.Edges:
                    for p in e.discretize(6):
                        if abs(p.z - wall.CenterOfMass.z) < 0.25 * wall.BoundBox.ZLength:
                            self.assertAlmostEqual(moved.distToShape(Part.Vertex(p))[0], 0.4, 3, (mode, d))
                p = wall.CenterOfMass
                near = min(walls, key=lambda g: g.distToShape(Part.Vertex(p))[0])
                pieces, _ = rw.pieces(f.Shape, near)  # one click on the moved band takes all of it again
                self.assertAlmostEqual(sum(g.Area for g in pieces), sum(g.Area for g in walls
                                       if g.distToShape(near)[0] < 1e-6 and rw._same_surface(near, g, rw.direction(near))),
                                       6, (mode, d))
                self.body.removeObject(f)
                self.doc.removeObject(f.Name)
                self.body.Tip = self.tip
                self.doc.recompute()


if __name__ == "__main__":
    unittest.main()
