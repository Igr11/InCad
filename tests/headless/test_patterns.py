import unittest

import FreeCAD as App
from incad.core import document, model
from incad.features import common, kind_for, patterns
from headless import util


class PatternsTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Pt")
        self.body, self.pad = util.padded_part(self.doc, 10, incad=True)
        self.pad_pick = common.format_picks([(self.pad, "")])

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_rectangular_two_directions(self):
        k = patterns.RECT
        v = dict(k.defaults(self.doc, self.body, None), features=self.pad_pick, count1="3", spacing1="30 mm",
                 two_directions=True,
                 count2="2", spacing2="20 mm")
        f = k.create(self.doc, self.body, None, v)
        self.doc.recompute()
        self.assertAlmostEqual(f.Shape.Volume, 6 * 2000, places=1)
        self.assertIs(kind_for(f), k)
        r = k.read(self.doc, f)
        self.assertEqual((r["count1"], r["spacing1"], r["count2"], r["two_directions"]), ("3", "30 mm", "2", True))

    def test_spacing_parameter_drives_the_pattern(self):
        k = patterns.RECT
        f = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None), features=self.pad_pick,
                                                     count1="2", spacing1="30 mm"))
        self.doc.recompute()
        name = model.bound_parameter(f, "Offset") or k.spacing_param(f, 1)
        model.set_model_parameter(self.doc, name, "10 mm")  # overlapping copies now
        self.assertLess(f.Shape.Volume, 2 * 2000 - 1)

    def test_a_count_must_be_a_whole_number_of_at_least_one(self):
        for k, key in ((patterns.RECT, "count1"), (patterns.CIRC, "count")):
            for bad in ("2.5", "0", "-3", "3 mm"):
                with self.assertRaises(ValueError, msg="%s %r" % (key, bad)) as cm:
                    k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None),
                                                             features=self.pad_pick, **{key: bad}))
                self.assertIn("whole number", str(cm.exception))
        k = patterns.CIRC  # a whole number is still fine
        f = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None), features=self.pad_pick,
                                                     count="5"))
        self.assertEqual(f.Occurrences, 5)

    def test_a_face_or_edge_clicked_in_3d_stands_for_the_feature_that_made_it(self):
        """Pattern's Features field takes a feature from the tree, or any face/edge of it clicked in the view: the
        feature that created that face (the Pad for its walls, the Pocket for the hole's wall)."""
        import Part
        top = [i + 1 for i, f in enumerate(self.pad.Shape.Faces) if abs(f.CenterOfMass.z - 10) < 1e-6][0]
        sk = self.body.newObject("Sketcher::SketchObject", "HoleSk")
        sk.AttachmentSupport = [(self.pad, "Face%d" % top)]
        sk.MapMode = "FlatFace"
        sk.addGeometry(Part.Circle(App.Vector(10, 5, 0), App.Vector(0, 0, 1), 2))
        self.doc.recompute()
        pocket = self.body.newObject("PartDesign::Pocket", "Pocket")
        pocket.Profile, pocket.Type = sk, 1
        self.body.Tip = pocket
        self.doc.recompute()
        wall = [i + 1 for i, f in enumerate(pocket.Shape.Faces) if f.Surface.TypeId == "Part::GeomCylinder"][0]
        side = [i + 1 for i, f in enumerate(pocket.Shape.Faces) if f.Surface.TypeId == "Part::GeomPlane"
                and abs(f.CenterOfMass.x) < 1e-6][0]
        self.assertIs(common.feature_of(pocket, "Face%d" % wall), pocket)
        self.assertIs(common.feature_of(pocket, "Face%d" % side), self.pad)
        self.assertIs(common.feature_of(self.pad, ""), self.pad)  # a tree row is the feature itself
        self.assertIs(common.feature_of(sk, ""), None)  # a sketch is not a feature to pattern
        self.assertTrue(common.accepts("feature", pocket, "Face%d" % wall))
        self.assertFalse(common.accepts("feature", sk, ""))
        # and the pattern really repeats the clicked feature
        k = patterns.RECT
        f = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None),
                                                     features=common.format_picks([(pocket, "")]),
                                                     count1="3", spacing1="4 mm"))
        self.doc.recompute()
        self.assertEqual([o.Name for o in f.Originals], ["Pocket"])
        self.assertNotIn("Invalid", f.State)

    def _boss_with_a_hole(self):
        """A second Pad (the boss) on the first, a Pocket (a hole in the boss) on the boss's top face, and an
        unrelated Pocket on the base."""
        import Part
        def top_of(feature, z):
            return [i + 1 for i, f in enumerate(feature.Shape.Faces)
                    if abs(f.CenterOfMass.z - z) < 1e-6 and f.Surface.TypeId == "Part::GeomPlane"][0]
        sk = self.body.newObject("Sketcher::SketchObject", "BossSk")
        sk.AttachmentSupport = [(self.pad, "Face%d" % top_of(self.pad, 10))]
        sk.MapMode = "FlatFace"
        sk.addGeometry(Part.Circle(App.Vector(10, 5, 0), App.Vector(0, 0, 1), 3))
        boss = util.add_pad(self.body, sk, 5, name="Boss")
        self.body.Tip = boss
        self.doc.recompute()
        hsk = self.body.newObject("Sketcher::SketchObject", "BossHoleSk")
        hsk.AttachmentSupport = [(boss, "Face%d" % top_of(boss, 15))]
        hsk.MapMode = "FlatFace"
        hsk.addGeometry(Part.Circle(App.Vector(10, 5, 0), App.Vector(0, 0, 1), 1))
        hole = self.body.newObject("PartDesign::Pocket", "BossHole")
        hole.Profile, hole.Type = hsk, 0
        hole.Length = 2
        self.body.Tip = hole
        self.doc.recompute()
        return boss, hole

    def test_the_pattern_can_take_the_features_built_on_the_picked_one(self):
        boss, hole = self._boss_with_a_hole()
        k = patterns.RECT
        base = dict(k.defaults(self.doc, self.body, None), features=common.format_picks([(boss, "")]),
                    count1="2", spacing1="30 mm")
        plain = k.create(self.doc, self.body, None, base)
        self.doc.recompute()
        self.assertEqual([o.Name for o in plain.Originals], ["Boss"])
        self.assertEqual(k.read(self.doc, plain)["children"], False)
        both = k.create(self.doc, self.body, None, dict(base, children=True))
        self.doc.recompute()
        self.assertEqual([o.Name for o in both.Originals], ["Boss", "BossHole"])
        self.assertNotIn("Invalid", both.State, both.getStatusString())
        back = k.read(self.doc, both)  # the dependents are not listed as picks: the toggle stands for them
        self.assertEqual((back["features"], back["children"]), ("Boss", True))
        k.update(self.doc, both, dict(back, children=False))
        self.assertEqual([o.Name for o in both.Originals], ["Boss"])
        # an unrelated feature is not taken; picking the hole alone with the toggle keeps just the hole
        only = k.create(self.doc, self.body, None, dict(base, features=common.format_picks([(hole, "")]),
                                                        children=True))
        self.assertEqual([o.Name for o in only.Originals], ["BossHole"])
        for kind in (patterns.CIRC, patterns.MIRROR):
            self.assertIn("children", [f.key for f in kind.FIELDS])

    def test_a_feature_on_a_face_merely_named_through_a_dependent_is_not_a_dependent(self):
        """A sketch is attached to a face through whatever feature was the Tip at the time. A pocket drawn on the
        block's top while the boss's hole was the Tip names the hole's feature, but stands on the block: it is not
        built on the boss and must not come along with 'Include dependent features' (it would widen the picked
        feature across the block and leave no room for an equal spacing)."""
        import Part
        boss, hole = self._boss_with_a_hole()
        top = [i + 1 for i, f in enumerate(hole.Shape.Faces)
               if abs(f.CenterOfMass.z - 10) < 1e-6 and f.Surface.TypeId == "Part::GeomPlane"][0]
        sk = self.body.newObject("Sketcher::SketchObject", "SideSk")
        sk.AttachmentSupport = [(hole, "Face%d" % top)]  # the block's top, named through the hole feature
        sk.MapMode = "FlatFace"
        sk.addGeometry(Part.Circle(App.Vector(3, 5, 0), App.Vector(0, 0, 1), 1))
        side = self.body.newObject("PartDesign::Pocket", "SidePocket")
        side.Profile, side.Type, side.Length = sk, 0, 2
        self.body.Tip = side
        self.doc.recompute()
        self.assertEqual([o.Name for o in common.support_features(side)], ["BossHole"])  # what the file says
        k = patterns.RECT
        both = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None),
                                                        features=common.format_picks([(boss, "")]),
                                                        children=True, count1="2", spacing1="30 mm"))
        self.doc.recompute()
        self.assertEqual([o.Name for o in both.Originals], ["Boss", "BossHole"])
        # the pocket's own dependents are judged the same way: it stands on the block, not on the hole
        self.assertEqual(k.read(self.doc, both)["children"], True)
        # a feature drawn on the boss's hole bottom IS a dependent of the boss, whichever feature named the face
        bottom = [i + 1 for i, f in enumerate(side.Shape.Faces)
                  if abs(f.CenterOfMass.z - 13) < 1e-6 and f.Surface.TypeId == "Part::GeomPlane"][0]
        dsk = self.body.newObject("Sketcher::SketchObject", "DeepSk")
        dsk.AttachmentSupport = [(side, "Face%d" % bottom)]  # the hole's bottom, named through the side pocket
        dsk.MapMode = "FlatFace"
        dsk.addGeometry(Part.Circle(App.Vector(10, 5, 0), App.Vector(0, 0, 1), 0.5))
        deep = self.body.newObject("PartDesign::Pocket", "DeepHole")
        deep.Profile, deep.Type, deep.Length = dsk, 0, 1
        self.body.Tip = deep
        self.doc.recompute()
        k.update(self.doc, both, dict(k.read(self.doc, both), children=True))
        self.assertEqual([o.Name for o in both.Originals], ["Boss", "BossHole", "DeepHole"])

    def test_a_face_named_through_a_thread_still_belongs_to_the_feature_that_made_it(self):
        """FreeCAD keeps no element names through a thread's helix, so the element history of any face named
        through the thread ends at the thread. The block's top is still the block's: a pocket drawn on it while
        the thread was the Tip is not a dependent of the threaded shaft, and the shaft (with its thread) can be
        spaced equally between the block's ends."""
        import Part
        from incad.features import thread
        from headless.test_thread import cyl_face
        top = [i + 1 for i, f in enumerate(self.pad.Shape.Faces) if abs(f.CenterOfMass.z - 10) < 1e-6][0]
        sk = self.body.newObject("Sketcher::SketchObject", "ShaftSk")
        sk.AttachmentSupport = [(self.pad, "Face%d" % top)]
        sk.MapMode = "FlatFace"
        sk.addGeometry(Part.Circle(App.Vector(17, 5, 0), App.Vector(0, 0, 1), 2.5))
        shaft = util.add_pad(self.body, sk, 8, name="Shaft")  # x 14.5..19.5, near the right face
        self.body.Tip = shaft
        self.doc.recompute()
        th = thread.create(self.doc, self.body, None, dict(thread.defaults(self.doc, self.body, None),
                                                           face=cyl_face(shaft, 2.5), standard="iso", size="M5",
                                                           clearance="0 mm"))
        self.doc.recompute()
        self.assertNotIn("Invalid", th.State, th.getStatusString())
        block_top = [i + 1 for i, f in enumerate(th.Shape.Faces)
                     if f.Surface.TypeId == "Part::GeomPlane" and abs(f.CenterOfMass.z - 10) < 0.5
                     and f.Area > 100][0]
        self.assertEqual(common.raw_feature_of(th, "Face%d" % block_top).Name, self.pad.Name)
        psk = self.body.newObject("Sketcher::SketchObject", "SideSk")
        psk.AttachmentSupport = [(th, "Face%d" % block_top)]  # the block's top, named through the thread
        psk.MapMode = "FlatFace"
        psk.addGeometry(Part.Circle(App.Vector(3, 5, 0), App.Vector(0, 0, 1), 1))
        side = self.body.newObject("PartDesign::Pocket", "SidePocket")
        side.Profile, side.Type, side.Length = psk, 0, 2
        self.body.Tip = side
        self.doc.recompute()
        self.assertEqual([o.Name for o in patterns._dependents(self.body, [shaft], None)], [th.Name])
        k = patterns.RECT
        f = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None),
                                                     features=common.format_picks([(shaft, "")]), children=True,
                                                     count1="3", fit1="faces", from1=self._face_at_x(self.pad, 20),
                                                     to1=self._face_at_x(self.pad, 0)))
        self.doc.recompute()
        self.assertEqual([o.Name for o in f.Originals], [shaft.Name, th.Name])
        self.assertNotIn("Invalid", f.State, f.getStatusString())
        self.assertAlmostEqual(f.Length.Value, 14.0, places=3)  # first to last copy: x 14.5, 7.5, 0.5 (0.5 mm margins)

    def _small_boss(self, x=3):
        """A 2 mm wide boss on the block's top (x-1..x+1; 2..4 by default), the block being x 0..20."""
        import Part
        top = [i + 1 for i, f in enumerate(self.pad.Shape.Faces) if abs(f.CenterOfMass.z - 10) < 1e-6][0]
        sk = self.body.newObject("Sketcher::SketchObject", "SmallSk")
        sk.AttachmentSupport = [(self.pad, "Face%d" % top)]
        sk.MapMode = "FlatFace"
        sk.addGeometry(Part.Circle(App.Vector(x, 5, 0), App.Vector(0, 0, 1), 1))
        boss = util.add_pad(self.body, sk, 2, name="SmallBoss")
        self.body.Tip = boss
        self.doc.recompute()
        return boss

    def _face_at_x(self, shape_obj, x):
        return "%s:Face%d" % (shape_obj.Name, [i + 1 for i, f in enumerate(shape_obj.Shape.Faces)
                                                if f.Surface.TypeId == "Part::GeomPlane"
                                                and abs(f.CenterOfMass.x - x) < 1e-6 and abs(f.Surface.Axis.x) > 0.99][0])

    def test_even_distribution_between_two_faces_leaves_equal_margins(self):
        """Count 4 between the block's two end faces: the first copy is as far from the left face as the last one is
        from the right face (2 mm here, the boss's own distance from the left face)."""
        boss = self._boss = self._small_boss()
        k = patterns.RECT
        f = k.create(self.doc, self.body, None, dict(
            k.defaults(self.doc, self.body, None), features=common.format_picks([(boss, "")]), count1="4",
            fit1="faces", from1=self._face_at_x(self.pad, 0), to1=self._face_at_x(self.pad, 20)))
        self.doc.recompute()
        self.assertNotIn("Invalid", f.State, f.getStatusString())
        self.assertAlmostEqual(f.Length.Value / 3.0, 14.0 / 3.0, places=3)  # (20 - 2 - 4) / 3
        bosses = f.Shape.cut(self.pad.Shape)
        self.assertAlmostEqual(bosses.BoundBox.XMin, 2.0, places=3)
        self.assertAlmostEqual(bosses.BoundBox.XMax, 18.0, places=3)  # 20 - 2: the same margin on both sides
        self.assertEqual(len(bosses.Solids), 4)
        back = k.read(self.doc, f)
        self.assertEqual(back["fit1"], "faces")
        self.assertEqual(back["to1"], self._face_at_x(self.pad, 20))

    def _edge_at_x(self, x):
        """A straight block edge lying in the plane x = const (a vertical one, on the left or right face)."""
        i = [i + 1 for i, e in enumerate(self.pad.Shape.Edges)
             if e.Curve.TypeId == "Part::GeomLine" and abs(e.BoundBox.XMin - x) < 1e-6 and abs(e.BoundBox.XMax - x) < 1e-6
             and e.BoundBox.ZLength > 1][0]
        return "%s:Edge%d" % (self.pad.Name, i)

    def test_equal_spacing_works_from_edge_to_edge_and_from_a_face_to_an_edge(self):
        boss = self._small_boss()
        k = patterns.RECT
        for frm, to in ((self._edge_at_x(0), self._edge_at_x(20)), (self._face_at_x(self.pad, 0), self._edge_at_x(20))):
            f = k.create(self.doc, self.body, None, dict(
                k.defaults(self.doc, self.body, None), features=common.format_picks([(boss, "")]), count1="4",
                fit1="faces", from1=frm, to1=to))
            self.doc.recompute()
            self.assertNotIn("Invalid", f.State, f.getStatusString())
            bosses = f.Shape.cut(self.pad.Shape)
            self.assertAlmostEqual(bosses.BoundBox.XMin, 2.0, places=3)
            self.assertAlmostEqual(bosses.BoundBox.XMax, 18.0, places=3)
            self.assertEqual(len(bosses.Solids), 4)
        self.assertTrue(common.accepts("limit", self.pad, self._edge_at_x(0).split(":")[1]))
        self.assertTrue(common.accepts("limit", self.pad, self._face_at_x(self.pad, 0).split(":")[1]))
        self.assertFalse(common.accepts("limit", self.pad, "Vertex1"))
        field_keys = {f.key: f for f in k.FIELDS}
        self.assertEqual(field_keys["fit1"].choices[1][1], "Equal spacing")
        self.assertEqual((field_keys["from1"].pick, field_keys["to1"].pick), ("limit", "limit"))

    def _face_at(self, axis, value):
        i = [i + 1 for i, f in enumerate(self.pad.Shape.Faces) if f.Surface.TypeId == "Part::GeomPlane"
             and abs(getattr(f.CenterOfMass, axis) - value) < 1e-6
             and abs(getattr(f.Surface.Axis, axis)) > 0.99][0]
        return "%s:Face%d" % (self.pad.Name, i)

    def _boss_at(self, x, y):
        import Part
        top = [i + 1 for i, f in enumerate(self.pad.Shape.Faces) if abs(f.CenterOfMass.z - 10) < 1e-6][0]
        sk = self.body.newObject("Sketcher::SketchObject", "BossSk%d" % len(self.body.Group))
        sk.AttachmentSupport = [(self.pad, "Face%d" % top)]
        sk.MapMode = "FlatFace"
        sk.addGeometry(Part.Circle(App.Vector(x, y, 0), App.Vector(0, 0, 1), 1))
        boss = util.add_pad(self.body, sk, 2, name="Boss%d" % len(self.body.Group))
        self.body.Tip = boss
        self.doc.recompute()
        return boss

    def _equal(self, boss, frm, to, count, **more):
        k = patterns.RECT
        f = k.create(self.doc, self.body, None, dict(
            k.defaults(self.doc, self.body, None), features=common.format_picks([(boss, "")]), count1=str(count),
            fit1="faces", from1=frm, to1=to, **more))
        self.doc.recompute()
        self.assertNotIn("Invalid", f.State, f.getStatusString())
        return f, f.Shape.cut(self.pad.Shape).BoundBox

    def test_equal_spacing_takes_its_direction_from_the_picked_faces(self):
        """Faces on Y: the pattern runs along Y whatever Direction 1 says (X by default)."""
        boss = self._boss_at(10, 2)  # y 1..3 on the 10 mm deep block
        f, box = self._equal(boss, self._face_at("y", 0), self._face_at("y", 10), 3)
        self.assertAlmostEqual(box.YMin, 1.0, places=3)
        self.assertAlmostEqual(box.YMax, 9.0, places=3)  # 10 - 1: equal margins along Y
        self.assertAlmostEqual(box.XMin, 9.0, places=3)
        self.assertAlmostEqual(box.XMax, 11.0, places=3)  # nothing moved in X

    def test_the_first_pick_is_the_start_and_the_copies_run_toward_the_second(self):
        """From is where the pattern starts, To where it runs toward — whichever end the original is nearer to."""
        boss = self._small_boss(17)  # x 16..18, close to the right face
        k = patterns.RECT
        # From the right face toward the left one: the original is at the start, the copies run left
        f, box = self._equal(boss, self._face_at_x(self.pad, 20), self._face_at_x(self.pad, 0), 3)
        self.assertTrue(f.Reversed)
        self.assertAlmostEqual(box.XMin, 2.0, places=3)
        self.assertAlmostEqual(box.XMax, 18.0, places=3)
        # From the left face toward the right one: the original is 16 mm from the start, so nothing fits - and it says
        # which side the start is (no silent turning round to the other end)
        with self.assertRaises(ValueError) as cm:
            k.create(self.doc, self.body, None, dict(
                k.defaults(self.doc, self.body, None), features=common.format_picks([(boss, "")]), count1="3",
                fit1="faces", from1=self._face_at_x(self.pad, 0), to1=self._face_at_x(self.pad, 20)))
        self.assertIn("from the start", str(cm.exception))
        self.assertIn("pick the other end as From", str(cm.exception))

    def test_flip_direction_puts_the_copies_on_the_other_side_of_the_original_in_both_modes(self):
        boss = self._small_boss(5)  # x 4..6
        k = patterns.RECT
        base = dict(k.defaults(self.doc, self.body, None), features=common.format_picks([(boss, "")]), count1="2",
                    spacing1="8 mm")
        fwd = k.create(self.doc, self.body, None, dict(base))
        self.doc.recompute()
        self.assertFalse(fwd.Reversed)
        self.assertAlmostEqual(fwd.Shape.cut(self.pad.Shape).BoundBox.XMax, 14.0, places=3)
        back = k.create(self.doc, self.body, None, dict(base, flip1=True))
        self.doc.recompute()
        self.assertTrue(back.Reversed)
        self.assertEqual(k.read(self.doc, back)["flip1"], True)
        self.assertAlmostEqual(back.Shape.cut(self.pad.Shape).BoundBox.XMin, -4.0, places=3)  # 8 mm to the left
        # equal spacing, 3 copies from the left face toward the right one: x 4..6, 9..11, 14..16 (4 mm margins)
        eq_args = dict(from1=self._face_at_x(self.pad, 0), to1=self._face_at_x(self.pad, 20), count1="3")
        f, box = self._equal(boss, eq_args["from1"], eq_args["to1"], 3)
        self.assertFalse(f.Reversed)
        self.assertAlmostEqual(box.XMax, 16.0, places=3)
        spacing = f.Length.Value / 2.0
        self.doc.removeObject(f.Name)  # the flipped one is built on the boss alone, not on the first pattern
        self.body.Tip = boss
        self.doc.recompute()
        # Flip: the same spacing, the copies on the other side of the original (x -6..-4 at the far end)
        g, gbox = self._equal(boss, eq_args["from1"], eq_args["to1"], 3, flip1=True)
        self.assertTrue(g.Reversed)
        self.assertAlmostEqual(g.Length.Value / 2.0, spacing, places=6)
        self.assertAlmostEqual(gbox.XMin, 4.0 - 2 * spacing, places=3)
        self.assertAlmostEqual(gbox.XMax, 6.0, places=3)

    def test_the_end_face_behind_the_start_face_runs_the_pattern_backwards(self):
        boss = self._small_boss(17)  # near the right face; the copies go left to the left face
        k = patterns.RECT
        f = k.create(self.doc, self.body, None, dict(
            k.defaults(self.doc, self.body, None), features=common.format_picks([(boss, "")]), count1="3",
            fit1="faces", from1=self._face_at_x(self.pad, 20), to1=self._face_at_x(self.pad, 0)))
        self.doc.recompute()
        self.assertNotIn("Invalid", f.State, f.getStatusString())
        self.assertTrue(f.Reversed)
        bosses = f.Shape.cut(self.pad.Shape)
        self.assertAlmostEqual(bosses.BoundBox.XMin, 2.0, places=3)   # 2 mm from the left face
        self.assertAlmostEqual(bosses.BoundBox.XMax, 18.0, places=3)  # and the original, 2 mm from the right one
        self.assertEqual(len(bosses.Solids), 3)

    def test_even_distribution_needs_an_end_face_and_room(self):
        boss = self._small_boss()
        k = patterns.RECT
        base = dict(k.defaults(self.doc, self.body, None), features=common.format_picks([(boss, "")]), count1="4",
                    fit1="faces")
        with self.assertRaises(ValueError) as cm:
            k.create(self.doc, self.body, None, dict(base))
        self.assertIn("To face", str(cm.exception))
        with self.assertRaises(ValueError) as cm:
            k.create(self.doc, self.body, None, dict(base, count1="30", from1=self._face_at_x(self.pad, 0),
                                                     to1=self._face_at_x(self.pad, 20)))
        self.assertIn("room", str(cm.exception))
        # the message gives the sizes: the feature's width, what the copies need and what the limits allow
        msg = str(cm.exception)
        self.assertIn("2.0 mm wide", msg)   # the boss
        self.assertIn("30 copies need", msg)
        self.assertIn("20.0 mm", msg)       # the space between the limits

    def test_circular(self):
        k = patterns.CIRC
        f = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None), features=self.pad_pick,
                                                     count="4"))
        self.doc.recompute()
        self.assertAlmostEqual(f.Shape.Volume, 8000, places=1)

    def test_mirror(self):
        k = patterns.MIRROR
        f = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None), features=self.pad_pick))
        self.doc.recompute()
        self.assertAlmostEqual(f.Shape.Volume, 4000, places=1)
        self.assertEqual(common.parse_picks(self.doc, k.read(self.doc, f)["features"]), [(self.pad, "")])

    def test_new_pattern_becomes_the_tip(self):
        for k in (patterns.RECT, patterns.CIRC, patterns.MIRROR):
            f = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None), features=self.pad_pick))
            self.doc.recompute()
            self.assertIs(self.body.Tip, f, k.TITLE)

    def test_defaults_name_the_origin_directions(self):
        names = {o.Role: o.Name for o in self.body.Origin.OriginFeatures}
        r = patterns.RECT.defaults(self.doc, self.body, None)
        self.assertEqual((r["dir1"], r["dir2"]), (names["X_Axis"], names["Y_Axis"]))
        self.assertEqual(patterns.CIRC.defaults(self.doc, self.body, None)["axis"], names["Z_Axis"])
        self.assertEqual(patterns.MIRROR.defaults(self.doc, self.body, None)["plane"], names["YZ_Plane"])

    def test_spacing_parameters_are_named_for_the_dialog(self):
        k = patterns.RECT
        f = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None), features=self.pad_pick, two_directions=True))
        self.doc.recompute()
        names = k.param_names(f)
        self.assertEqual(set(names), {"spacing1", "spacing2"})
        self.assertTrue(all(names.values()))

    def test_without_a_pick_a_new_pattern_asks_for_a_feature(self):
        """The Features field starts empty: no guess at the newest feature (on a real part that is whatever was
        made last, a groove at the other end). A feature selected before the command is seeded by the dialog."""
        for k in (patterns.RECT, patterns.CIRC, patterns.MIRROR):
            with self.assertRaises(ValueError, msg=k.TITLE) as cm:
                k.create(self.doc, self.body, None, k.defaults(self.doc, self.body, None))
            self.assertIn("Click a feature", str(cm.exception))
            self.assertIs(self.body.Tip, self.pad, k.TITLE)

    def test_the_picked_features_survive_an_edit_with_an_empty_field(self):
        for k in (patterns.RECT, patterns.CIRC, patterns.MIRROR):
            tip = self.body.Tip
            f = k.create(self.doc, self.body, None, dict(k.defaults(self.doc, self.body, None), features=self.pad_pick))
            self.doc.recompute()
            f = k.update(self.doc, f, k.defaults(self.doc, self.body, None))
            self.doc.recompute()
            self.assertEqual(list(f.Originals), [tip], k.TITLE)
            self.assertNotIn("Invalid", f.State, k.TITLE)
            self.body.removeObject(f)
            self.doc.removeObject(f.Name)
            self.body.Tip = tip
            self.doc.recompute()

class PickingWhatCannotBeRepeatedTest(unittest.TestCase):
    """A thread (or a fillet) can't be repeated by itself; picking one stands for the feature it modifies."""

    def setUp(self):
        from headless import test_thread
        from incad.features import thread
        self.doc = util.new_doc("Rp")
        self.body = document.make_part(self.doc)
        self.shaft = test_thread.shaft(self.doc, self.body)
        v = dict(thread.defaults(self.doc, self.body, None), face=test_thread.cyl_face(self.shaft, 5), size="M10",
                 clearance="0 mm")
        self.thread = thread.create(self.doc, self.body, None, v)
        self.doc.recompute()

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_a_thread_row_or_its_face_stands_for_the_shaft_it_cuts(self):
        self.assertIs(common.feature_of(self.thread, ""), self.shaft)
        wall = [i + 1 for i, f in enumerate(self.thread.Shape.Faces) if f.Surface.TypeId == "Part::GeomCylinder"
                or f.Surface.TypeId != "Part::GeomPlane"][0]
        self.assertIs(common.feature_of(self.thread, "Face%d" % wall), self.shaft)
        self.assertTrue(common.accepts("feature", self.thread, ""))
        self.assertTrue(common.is_stand_in(self.thread))
        self.assertFalse(common.is_stand_in(self.shaft))

    def test_the_shaft_pattern_with_dependents_carries_the_thread(self):
        k = patterns.RECT
        f = k.create(self.doc, self.body, None, dict(
            k.defaults(self.doc, self.body, None), features=common.format_picks([(self.thread, "")]), children=True,
            count1="2", spacing1="30 mm", dir1="Y_Axis"))
        self.doc.recompute()
        self.assertEqual([o.Name for o in f.Originals], [self.shaft.Name, self.thread.Name])
        self.assertNotIn("Invalid", f.State, f.getStatusString())
        self.assertGreater(f.Shape.BoundBox.YLength, 30)  # the second shaft stands 30 mm beside the first
