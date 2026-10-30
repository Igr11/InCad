"""Tools for printed parts: Boss, Lip / Groove, Snap Fit (incad.features.plastic) and Hole ▸ Insert."""
import unittest

import FreeCAD as App
import Part

from incad.core import document
from incad.features import hole, plastic
from incad.threads import inserts
from headless import util

V = App.Vector


def box(doc, w=40, d=30, h=20, wall=2):
    """An open box: a w × d × h block shelled from its top, walls `wall` thick."""
    body = document.make_part(doc)
    sk = util.add_rect_sketch(body, w, d)
    pad = util.add_pad(body, sk, h)
    body.Tip = pad
    doc.recompute()
    top = next(i for i, f in enumerate(pad.Shape.Faces, 1)
               if abs(f.normalAt(0, 0).z - 1) < 1e-9 and abs(f.CenterOfMass.z - h) < 1e-9)
    shell = body.newObject("PartDesign::Thickness", "Shell")
    shell.Base = (pad, ["Face%d" % top])
    shell.Value = wall
    shell.Reversed = True  # the walls go inwards: the outside stays w × d
    shell.Join = "Intersection"
    body.Tip = shell
    doc.recompute()
    return body, shell


def rim_face(feature, z):
    return next(i for i, f in enumerate(feature.Shape.Faces, 1)
                if f.Surface.TypeId == "Part::GeomPlane" and abs(f.normalAt(0, 0).z - 1) < 1e-9
                and abs(f.CenterOfMass.z - z) < 1e-6 and len(f.Wires) > 1)


def point_sketch(body, points, z=None, support=None, circles=()):
    sk = body.newObject("Sketcher::SketchObject", "Points")
    if support is not None:
        sk.AttachmentSupport = [support]
        sk.MapMode = "FlatFace"
    else:
        sk.AttachmentSupport = [(util.xy_plane(body), "")]
        sk.MapMode = "FlatFace"
        if z is not None:
            sk.AttachmentOffset = App.Placement(V(0, 0, z), App.Rotation())
    for x, y in points:
        sk.addGeometry(Part.Point(V(x, y, 0)))
    for (x, y), r in circles:
        sk.addGeometry(Part.Circle(V(x, y, 0), V(0, 0, 1), r))
    return sk


class PlasticTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Pl")
        self.body, self.shell = box(self.doc)

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def make(self, kind, **kw):
        values = kind.defaults(self.doc, self.body, None)
        values.update(kw)
        f = kind.create(self.doc, self.body, None, values)
        self.doc.recompute()
        self.assertNotIn("Invalid", f.State, f.getStatusString())
        self.assertTrue(f.Shape.isValid())
        self.assertEqual(len(f.Shape.Solids), 1, "joined to the part: one solid")
        return f

    def test_boss_with_insert_on_the_floor(self):
        sk = point_sketch(self.body, [(10, 10), (30, 20)], z=2, circles=[((20, 15), 3)])  # on the floor's top
        before = self.shell.Shape.Volume
        f = self.make(plastic.BOSS, sketch=sk.Name, height="8 mm", fillet="1 mm")
        ins = inserts.named("M3")
        r = float(plastic.BOSS.defaults(self.doc, self.body)["diameter"].split()[0]) / 2
        hole_v = 3.14159265 * (ins.hole / 2) ** 2 * inserts.depth(ins)
        one = 3.14159265 * r * r * 8 - hole_v
        self.assertGreater(f.Shape.Volume - before, 3 * one * 0.98, "three bosses (a circle's centre too)")
        # the insert's hole: a point down the axis inside the hole is air, just outside it is plastic
        self.assertFalse(f.Shape.isInside(V(10, 10, 2 + 8 - 1), 1e-6, True))
        self.assertTrue(f.Shape.isInside(V(10 + ins.hole / 2 + 0.5, 10, 2 + 8 - 1), 1e-6, True))
        self.assertIs(plastic.BOSS, next(k for k in [plastic.BOSS] if k.claims(f)))
        self.assertFalse(plastic.LIP.claims(f))
        values = plastic.BOSS.read(self.doc, f)
        self.assertEqual(values["hole"], "insert")
        self.assertEqual(values["insert"], "M3")
        plastic.BOSS.update(self.doc, f, dict(values, ribs="4", hole="plain", hole_d="2.5 mm"))
        self.assertTrue(f.Shape.isValid())
        self.assertTrue(f.Shape.isInside(V(10 + r + 1, 10, 2.5), 1e-6, True), "a rib beside the boss")

    def test_ribs_stop_at_the_wall(self):
        sk = point_sketch(self.body, [(5, 5)], z=2)  # 3 mm from the walls' inside: ribs would run out of the box
        f = self.make(plastic.BOSS, sketch=sk.Name, ribs="4", rib_length="6 mm")
        bb, box_bb = f.Shape.BoundBox, self.shell.Shape.BoundBox
        self.assertGreaterEqual(bb.XMin, box_bb.XMin - 1e-6)
        self.assertGreaterEqual(bb.YMin, box_bb.YMin - 1e-6)

    def test_ribs_turned_and_left_out(self):
        """The user: ribs set square (or turned), and one with no room for it left out."""
        sk = point_sketch(self.body, [(20, 15)], z=2)
        f = self.make(plastic.BOSS, sketch=sk.Name, height="8 mm", hole="none", diameter="8 mm", ribs="4",
                      rib_length="4 mm", fillet="0 mm")
        rib = lambda x, y: plastic.tool(f)[0].isInside(V(x, y, 2.5), 1e-6, True)
        self.assertTrue(rib(25, 15) and rib(20, 20) and rib(15, 15) and rib(20, 10), "rib 1 along x, then round")
        values = plastic.BOSS.read(self.doc, f)
        plastic.BOSS.update(self.doc, f, dict(values, rib_skip="1"))
        self.assertFalse(rib(25, 15), "rib 1 left out")
        self.assertTrue(rib(20, 20) and rib(15, 15) and rib(20, 10))
        values = plastic.BOSS.read(self.doc, f)
        self.assertEqual(values["rib_skip"], "1")
        plastic.BOSS.update(self.doc, f, dict(values, rib_skip="", rib_angle="45°"))
        self.assertTrue(rib(20 + 3.54, 15 + 3.54), "turned 45°")
        self.assertFalse(rib(25, 15))
        self.assertEqual(plastic.BOSS.unavailable(dict(values, ribs="4"))["rib_skip"], ["5", "6"])

    def test_boss_too_thin_for_the_insert(self):
        sk = point_sketch(self.body, [(10, 10)], z=2)
        values = dict(plastic.BOSS.defaults(self.doc, self.body), sketch=sk.Name, diameter="5 mm")
        with self.assertRaises(Exception):
            plastic.BOSS.create(self.doc, self.body, None, values)

    def test_flipped_boss_stays_on_its_point(self):
        """The user: "Flip direction is somehow inadequate" — a half turn about the sketch's x axis sent the boss to
        the mirror place across it too. Flipped, it stands on the same point and grows the other way."""
        sk = point_sketch(self.body, [(10, 8)], z=2)  # on the floor's top
        f = self.make(plastic.BOSS, sketch=sk.Name, height="6 mm", hole="none", ribs="0", fillet="0 mm", flip=True)
        self.assertTrue(f.Shape.isInside(V(10, 8, -3), 1e-6, True), "under the floor, on its point")
        self.assertFalse(f.Shape.isInside(V(10, 30 - 8, -3), 1e-6, True), "not at the mirror place")
        self.assertFalse(f.Shape.isInside(V(10, 8, 5), 1e-6, True), "not up into the box")

    def test_lip_and_groove_on_the_rim(self):
        before = self.shell.Shape.Volume
        face = rim_face(self.shell, 20)
        lip = self.make(plastic.LIP, face="%s:Face%d" % (self.shell.Name, face), width="1 mm", height="2 mm")
        added = lip.Shape.Volume - before
        ring = (38 * 28 - 36 * 26) * 2  # 1 mm of the rim along its inside edge (36 × 26), 2 mm high
        self.assertAlmostEqual(added, ring, delta=ring * 0.03)
        self.assertAlmostEqual(lip.Shape.BoundBox.ZMax, 22, places=6)
        # the lid's side: a groove along the inside edge, wider by the clearance and deeper
        lip.Visibility = False
        values = plastic.LIP.read(self.doc, lip)
        plastic.LIP.update(self.doc, lip, dict(values, type="groove", clearance="0.2 mm"))
        self.assertEqual(lip.Label, "Groove")
        self.assertLess(lip.Shape.Volume, before)
        self.assertAlmostEqual(lip.Shape.BoundBox.ZMax, 20, places=6)
        # the rim is found again after the part before it changes (its faces renumbered)
        self.shell.Value = 3
        self.doc.recompute()
        self.assertNotIn("Invalid", lip.State, lip.getStatusString())

    def hooks(self, *lines):
        sk = self.body.newObject("Sketcher::SketchObject", "Hooks")
        sk.AttachmentSupport = [(util.xy_plane(self.body), "")]
        sk.MapMode = "FlatFace"
        sk.AttachmentOffset = App.Placement(V(0, 0, 20), App.Rotation())  # on the rim's height
        for a, b in lines:
            sk.addGeometry(Part.LineSegment(V(*a), V(*b)))
        return sk

    def snap(self, line, **kw):
        sk = self.hooks(line)
        return self.make(plastic.SNAP_FIT, sketch=sk.Name, **kw)

    def test_snap_fit_grows_onto_the_inside_of_the_wall(self):
        """The user's pick: a strip on the wall's face from down the wall to over the rim, its lower edge chamfered
        45° over its thickness, the catch reaching back over the rim. The front wall is y 0..2, the rim at z 20."""
        before = self.shell.Shape.Volume
        f = self.snap(((15, 2, 0), (25, 2, 0)))  # along the rim's inner edge
        made = plastic.tool(f)[0]
        inside = lambda *p: made.isInside(V(*p), 1e-6, True)
        self.assertTrue(inside(20, 2.75, 15), "on the wall's inner face, down the wall")
        self.assertTrue(inside(20, 2.75, 25), "up over the rim")
        self.assertTrue(inside(20, 1.3, 27.7), "the catch reaches back over the rim")
        self.assertTrue(inside(20, 2.2, 11), "the chamfer under it")
        self.assertFalse(inside(20, 3.2, 11), "45°: thin near its lower end")
        self.assertFalse(inside(20, 2.75, 10), "nothing below the chamfer")
        self.assertAlmostEqual(made.BoundBox.ZMin, 20 - 8 - 1.5, places=4)
        self.assertAlmostEqual(made.BoundBox.ZMax, 30, places=4)
        strip = 1.5 * 10 * 18 + 0.5 * 1.5 * 1.5 * 10 + 0.5 * 1 * 2.5 * 10 + (1 - 3.14159265 / 4) * 0.25 * 10
        self.assertAlmostEqual(f.Shape.Volume - before, strip, delta=strip * 0.02)
        values = plastic.SNAP_FIT.read(self.doc, f)
        self.assertEqual((values["length"], values["overlap"], values["thick"]), ("10 mm", "8 mm", "1.5 mm"))
        plastic.SNAP_FIT.update(self.doc, f, dict(values, flip_side=True))
        made = plastic.tool(f)[0]
        self.assertTrue(made.isInside(V(20, 3.8, 27.7), 1e-6, True), "the other side: into the box")
        self.assertFalse(made.isInside(V(20, 1.3, 27.7), 1e-6, True))

    def test_snap_fit_goes_on_the_face_of_the_nearer_edge(self):
        """Drawn either way, or a little in from the edge: the same strip; on the outer edge: outside the wall."""
        def alone(line):  # each on the bare box, never on the one before
            f = self.snap(line)
            made = plastic.tool(f)[0].copy()
            sk = f.Sketch
            self.body.removeObject(f)
            self.doc.removeObject(f.Name)
            self.body.Tip = self.shell
            self.doc.removeObject(sk.Name)
            self.doc.recompute()
            return made
        ref = alone(((15, 2, 0), (25, 2, 0)))
        for line in (((25, 2, 0), (15, 2, 0)), ((15, 1.6, 0), (25, 1.6, 0))):
            made = alone(line)
            self.assertLess(made.cut(ref).Volume + ref.cut(made).Volume, 1e-3, line)
        out = alone(((25, 0, 0), (15, 0, 0)))
        self.assertTrue(out.isInside(V(20, -0.75, 15), 1e-6, True), "on the wall's outer face")
        self.assertTrue(out.isInside(V(20, 0.7, 27.7), 1e-6, True), "its catch back over the rim")

    def test_snap_fit_off_the_wall_and_too_far_down(self):
        sk = self.hooks(((15, 15, 0), (25, 15, 0)))  # over the middle of the box: no wall under it
        values = dict(plastic.SNAP_FIT.defaults(self.doc, self.body), sketch=sk.Name)
        with self.assertRaises(Exception):
            plastic.SNAP_FIT.create(self.doc, self.body, None, values)
        f = self.snap(((15, 2, 0), (25, 2, 0)), overlap="40 mm")
        self.assertGreaterEqual(plastic.tool(f)[0].BoundBox.ZMin, -1e-6, "kept inside the part: not under it")


class InsertHoleTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Ih")
        self.body, self.pad = util.padded_part(self.doc, 10, incad=True)

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_insert_hole_size_and_depth(self):
        sk = point_sketch(self.body, [(10, 5)], z=10)
        values = dict(hole.defaults(self.doc, self.body, None), sketch=sk.Name, hole_type="insert", insert_size="M4",
                      depth_type="distance")
        f = hole.create(self.doc, self.body, None, values)
        self.body.Tip = f
        self.doc.recompute()
        ins = inserts.named("M4")
        self.assertAlmostEqual(f.Diameter.Value, ins.hole)
        self.assertAlmostEqual(f.Depth.Value, ins.length + inserts.DEEPER)
        self.assertEqual(f.DrillPoint, "Flat")
        removed = self.pad.Shape.Volume - f.Shape.Volume
        want = 3.14159265 * (ins.hole / 2) ** 2 * inserts.depth(ins)
        self.assertAlmostEqual(removed, want, delta=want * 0.01)
        back = hole.read(self.doc, f)
        self.assertEqual((back["hole_type"], back["insert_size"]), ("insert", "M4"))
        hole.update(self.doc, f, dict(back, hole_type="simple", diameter="5 mm"))
        self.doc.recompute()
        self.assertAlmostEqual(f.Diameter.Value, 5.0)


if __name__ == "__main__":
    unittest.main()
