"""Move Face as a feature: a step at the tip that finds its faces by geometry on every recompute."""
import os
import shutil
import tempfile
import unittest

import FreeCAD as App

from incad.core import document, model
from incad.features import kind_for, move_face
from headless import util


def top_name(feature):
    faces = feature.Shape.Faces
    i = max((k for k, f in enumerate(faces) if f.normalAt(0, 0).z > 0.999), key=lambda k: faces[k].CenterOfMass.z)
    return "%s:Face%d" % (feature.Name, i + 1)


class MoveFaceFeatureTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Mf")
        self.body, self.pad = util.padded_part(self.doc, 10, incad=True)  # 20 x 10 x 10
        self.doc.recompute()

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def make(self, **kw):
        values = dict(move_face.defaults(self.doc, self.body, None), faces=top_name(self.body.Tip))
        values.update(kw)
        f = move_face.create(self.doc, self.body, None, values)
        self.doc.recompute()
        return f

    def test_moves_the_top_and_is_the_tip(self):
        f = self.make(distance="5 mm")
        self.assertIs(self.body.Tip, f)
        self.assertIs(kind_for(f), move_face)
        self.assertAlmostEqual(f.Shape.Volume, 20 * 10 * 15, 6)
        self.assertNotIn("Invalid", f.State)

    def test_the_row_reads_move_face(self):
        f = self.make(distance="5 mm")
        self.assertEqual(f.Label, "Move Face")
        g = self.make(distance="1 mm", mode="step")  # (Inventor on Inventor's result: see the task-3 report)
        self.assertTrue(g.Label.startswith("Move Face0"), g.Label)

    def test_a_refused_create_leaves_nothing(self):
        side = next(k for k, g in enumerate(self.pad.Shape.Faces) if g.normalAt(0, 0).x > 0.999)
        with self.assertRaises(ValueError) as e:
            self.make(faces="%s,%s:Face%d" % (top_name(self.pad), self.pad.Name, side + 1))
        self.assertEqual(str(e.exception), move_face.mf.FACES_MSG)
        self.assertFalse([o.Name for o in self.doc.Objects if move_face.claims(o)])
        self.assertIs(self.body.Tip, self.pad)

    def test_step_and_together_on_a_chamfered_top(self):
        """A 2 mm chamfer on the top's right edge: Step pushes only the top (18 x 10) up, Together takes the chamfer
        along (the whole 20 x 10 grows); an edit switches the mode."""
        edge = next(k for k, e in enumerate(self.pad.Shape.Edges)
                    if abs(e.CenterOfMass.x - 20) < 1e-6 and abs(e.CenterOfMass.z - 10) < 1e-6)
        ch = self.body.newObject("PartDesign::Chamfer", "Chamfer")
        ch.Base = (self.pad, ["Edge%d" % (edge + 1)])
        ch.Size = 2
        self.body.Tip = ch
        self.doc.recompute()
        f = self.make(distance="5 mm", mode="step")
        before = 20 * 10 * 10 - 0.5 * 2 * 2 * 10
        self.assertAlmostEqual(f.Shape.Volume, before + 18 * 10 * 5, 6)
        move_face.update(self.doc, f, dict(move_face.read(self.doc, f), mode="together"))
        self.assertNotIn("Invalid", f.State)
        self.assertAlmostEqual(f.Shape.Volume, before + 20 * 10 * 5, 6)

    def test_to_with_faces_in_two_planes(self):
        """Two boss tops at 13 and 16 moved To one plane at 20: both end in it."""
        for name, x, h in (("Low", 2, 3), ("High", 12, 6)):
            box = self.body.newObject("PartDesign::AdditiveBox", name)
            box.Length, box.Width, box.Height = 4, 4, h
            box.Placement = App.Placement(App.Vector(x, 2, 10), App.Rotation())
            self.body.Tip = box
        self.doc.recompute()
        tip = self.body.Tip
        tops = ["%s:Face%d" % (tip.Name, k + 1) for k, g in enumerate(tip.Shape.Faces)
                if g.normalAt(0, 0).z > 0.999 and g.CenterOfMass.z > 10 + 1e-6]
        self.assertEqual(len(tops), 2)
        plane = self.body.newObject("PartDesign::Plane", "Target")
        plane.AttachmentSupport = [(util.xy_plane(self.body), "")]
        plane.MapMode = "FlatFace"
        plane.AttachmentOffset = App.Placement(App.Vector(0, 0, 20), App.Rotation())
        self.body.Tip = tip
        self.doc.recompute()
        f = self.make(faces=",".join(tops), extent="to", to=plane.Name)
        self.assertNotIn("Invalid", f.State)
        at_20 = [g for g in f.Shape.Faces if g.normalAt(0, 0).z > 0.999 and abs(g.CenterOfMass.z - 20) < 1e-6]
        self.assertAlmostEqual(sum(g.Area for g in at_20), 2 * 16, 6)
        self.assertAlmostEqual(f.Shape.Volume, 20 * 10 * 10 + 2 * 16 * 10, 6)

    def test_read_gives_the_values_back(self):
        f = self.make(distance="3 mm", mode="step")
        v = move_face.read(self.doc, f)
        self.assertEqual((v["distance"], v["mode"], v["extent"]), ("3 mm", "step", "distance"))
        self.assertTrue(v["faces"])

    def test_read_names_the_faces_where_they_are_now(self):
        """Edit reads the faces back by geometry: the pick names the face found now, not the name picked then."""
        from incad.features.common import parse_picks
        f = self.make(distance="5 mm")
        self.pad.Length = 12
        self.doc.recompute()
        picks = parse_picks(self.doc, move_face.read(self.doc, f)["faces"])
        self.assertEqual(len(picks), 1)
        obj, sub = picks[0]
        self.assertIs(obj, f.BaseFeature)
        face = obj.Shape.getElement(sub)
        self.assertAlmostEqual(face.CenterOfMass.z, 12, 6)
        self.assertGreater(face.normalAt(0, 0).z, 0.999)
        move_face.update(self.doc, f, move_face.read(self.doc, f))  # OK on an unchanged edit keeps the same face
        self.assertAlmostEqual(f.Shape.BoundBox.ZMax, 17, 6)

    def test_the_distance_parameter_drives_it(self):
        f = self.make(distance="2 mm")
        name = model.bound_parameter(f, "Distance")
        self.assertTrue(name)
        model.set_model_parameter(self.doc, name, "4 mm")
        self.doc.recompute()
        self.assertAlmostEqual(f.Shape.Volume, 20 * 10 * 14, 6)

    def test_an_earlier_feature_edited_keeps_the_face(self):
        f = self.make(distance="5 mm")
        self.pad.Length = 12
        self.doc.recompute()
        self.assertNotIn("Invalid", f.State)
        self.assertAlmostEqual(f.Shape.BoundBox.ZMax, 17, 6)

    def test_to_a_work_plane_follows_it(self):
        plane = self.body.newObject("PartDesign::Plane", "Target")
        plane.AttachmentSupport = [(util.xy_plane(self.body), "")]
        plane.MapMode = "FlatFace"
        plane.AttachmentOffset = App.Placement(App.Vector(0, 0, 16), App.Rotation())
        self.body.Tip = self.pad  # the plane is no solid step: the feature goes after the pad
        self.doc.recompute()
        f = self.make(extent="to", to=plane.Name)
        self.assertAlmostEqual(f.Shape.BoundBox.ZMax, 16, 6)
        plane.AttachmentOffset = App.Placement(App.Vector(0, 0, 18), App.Rotation())
        self.doc.recompute()
        self.assertAlmostEqual(f.Shape.BoundBox.ZMax, 18, 6)
        move_face.update(self.doc, f, dict(move_face.read(self.doc, f), extent="distance", distance="5 mm"))
        self.assertIsNone(f.Target)  # back to Distance: no link to the plane left
        self.assertNotIn(plane, f.OutList)
        self.assertAlmostEqual(f.Shape.BoundBox.ZMax, 15, 6)

    def test_to_a_face_of_a_moved_solid(self):
        """To takes what the To field accepts (an origin plane, a flat face); a face of another Solid placed 3 mm up."""
        from incad.features import common
        self.assertTrue(common.accepts("plane", util.xy_plane(self.body), ""))
        self.assertTrue(common.accepts("face", self.pad, top_name(self.pad).partition(":")[2]))
        other = document.new_solid(self.doc)
        box = other.newObject("PartDesign::AdditiveBox", "Away")
        box.Length, box.Width, box.Height = 6, 6, 4
        box.Placement = App.Placement(App.Vector(50, 0, 0), App.Rotation())
        other.Tip = box
        other.Placement = App.Placement(App.Vector(0, 0, 3), App.Rotation())  # its top at z 7 (global)
        self.doc.recompute()
        f = self.make(extent="to", to=top_name(box))
        self.assertAlmostEqual(f.Shape.BoundBox.ZMax, 7, 6)
        self.assertAlmostEqual(f.Shape.Volume, 20 * 10 * 7, 6)

    def test_save_and_reopen(self):
        f = self.make(distance="4 mm", mode="step")
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        path = os.path.join(tmp, "move_face.FCStd")
        self.doc.saveAs(path)
        name = f.Name
        App.closeDocument(self.doc.Name)
        self.doc = App.openDocument(path)
        g = self.doc.getObject(name)
        g.touch()
        self.doc.recompute()
        self.assertFalse([o.Name for o in self.doc.Objects if "Invalid" in o.State])
        self.assertIs(kind_for(g), move_face)
        self.assertAlmostEqual(g.Shape.Volume, 20 * 10 * 14, 6)
        self.assertEqual(move_face.read(self.doc, g)["mode"], "step")

    def test_a_face_gone_says_so(self):
        f = self.make(distance="5 mm")
        self.pad.Profile[0].AttachmentOffset = App.Placement(App.Vector(100, 0, 0), App.Rotation())  # part moved off
        self.doc.recompute()
        self.assertIn("Invalid", f.State)
        self.assertIn(move_face.mf.GONE_MSG, f.getStatusString())

    def test_suppress_gives_the_shape_before(self):
        f = self.make(distance="5 mm")
        from incad.core import suppress
        suppress.toggle(f)
        self.doc.recompute()
        self.assertAlmostEqual(self.body.Shape.Volume, 20 * 10 * 10, 6)

    def test_a_moved_body(self):
        self.body.Placement = App.Placement(App.Vector(100, 50, 7), App.Rotation(App.Vector(0, 0, 1), 30))
        self.doc.recompute()
        f = self.make(distance="5 mm")
        self.assertAlmostEqual(f.Shape.Volume, 20 * 10 * 15, 6)
        point, normal = move_face.arrow(f)
        self.assertAlmostEqual(normal.z, 1, 9)
        self.assertAlmostEqual(point.z, 7 + 15, 6)  # global: on the moved face
        import Part
        self.assertLess(self.body.Shape.distToShape(Part.Vertex(point))[0], 1e-6)  # x / y too: on the Solid as shown

    def test_face_on_a_second_solid(self):
        """A second Solid (as tests/headless/test_make_assembly.py makes one); Move Face on its top goes into it."""
        other = document.new_solid(self.doc)
        pin = other.newObject("PartDesign::AdditiveBox", "Away")
        pin.Length, pin.Width, pin.Height = 6, 6, 4
        pin.Placement = App.Placement(App.Vector(50, 0, 0), App.Rotation())
        other.Tip = pin
        self.doc.recompute()
        values = dict(move_face.defaults(self.doc, other, None), faces=top_name(other.Tip), distance="2 mm")
        f = move_face.create(self.doc, other, None, values)
        self.doc.recompute()
        self.assertIs(f.getParentGeoFeatureGroup(), other)
        self.assertAlmostEqual(f.Shape.BoundBox.ZMax, 6, 6)
        self.assertAlmostEqual(self.pad.Shape.BoundBox.ZMax, 10, 6)  # the first Solid untouched


if __name__ == "__main__":
    unittest.main()
