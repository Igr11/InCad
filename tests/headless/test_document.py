import os
import tempfile
import unittest

import FreeCAD as App
import Part
from incad.core import document
from headless import util


class DocumentTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("Doc")

    def tearDown(self):
        if self.doc.Name in App.listDocuments():
            App.closeDocument(self.doc.Name)

    def test_make_part_marks_and_sets_units(self):
        body = document.make_part(self.doc, "in")
        self.assertTrue(document.is_incad_part(self.doc))
        self.assertEqual(document.part_units(self.doc), "in")
        self.assertEqual(self.doc.UnitSystem, "Imperial decimal (in, lb)")
        self.assertIs(document.primary_body(self.doc), body)
        self.assertEqual(body.Label, "Solid1")

    def test_plain_document_is_not_a_part(self):
        self.assertFalse(document.is_incad_part(self.doc))
        self.assertIsNone(document.part_units(self.doc))
        self.assertIsNone(document.primary_body(self.doc))
        self.assertFalse(document.is_incad_part(None))

    def test_make_part_twice_fails(self):
        document.make_part(self.doc)
        with self.assertRaises(ValueError):
            document.make_part(self.doc)

    def test_bad_units(self):
        with self.assertRaises(ValueError):
            document.make_part(self.doc, "cm")

    def test_marker_survives_save_and_reopen(self):
        document.make_part(self.doc, "mm")
        path = os.path.join(tempfile.mkdtemp(), "part.FCStd")
        self.doc.saveAs(path)
        App.closeDocument(self.doc.Name)
        self.doc = App.openDocument(path)
        self.assertTrue(document.is_incad_part(self.doc))
        self.assertEqual(document.part_units(self.doc), "mm")
        self.assertIsNotNone(document.primary_body(self.doc))

    def test_convert_plain_file_with_one_body(self):
        self.doc.addObject("PartDesign::Body", "Body")
        body = document.convert_to_part(self.doc, "in")
        self.assertTrue(document.is_incad_part(self.doc))
        self.assertIs(document.primary_body(self.doc), body)
        self.assertEqual(document.part_units(self.doc), "in")

    def test_convert_refuses_zero_or_many_bodies(self):
        with self.assertRaises(ValueError):
            document.convert_to_part(self.doc)
        self.doc.addObject("PartDesign::Body", "Body")
        self.doc.addObject("PartDesign::Body", "Body001")
        with self.assertRaises(ValueError):
            document.convert_to_part(self.doc)

    def test_new_solid(self):
        document.make_part(self.doc)
        b2 = document.new_solid(self.doc)
        self.assertEqual(len(document.bodies(self.doc)), 2)
        self.assertEqual(b2.Label, "Solid2")
        self.assertIsNot(document.primary_body(self.doc), b2)

    def test_new_solid_requires_part(self):
        with self.assertRaises(ValueError):
            document.new_solid(self.doc)

    def test_end_of_part_rolls_back_and_forward(self):
        body, pad = util.padded_part(self.doc, 10, incad=True)
        self.assertIs(document.end_of_part(body), pad)
        document.set_end_of_part(body, None)
        self.assertIsNone(body.Tip)
        self.assertTrue(body.Shape.isNull())
        document.set_end_of_part(body, pad)
        self.assertAlmostEqual(body.Shape.Volume, 20 * 10 * 10, places=3)

    def test_end_of_part_shows_only_the_tip_feature(self):
        """FreeCAD's Move Tip switches the shown feature; without that the 3D view kept the last shown feature and
        moving End of Part looked like nothing happened (user's p2_test: ThreadChamfer shown, Tip = Extrude)."""
        body, pad = util.padded_part(self.doc, 10, incad=True)
        pad2 = util.add_pad(body, util.add_rect_sketch(body, w=5, h=5, name="SketchB"), 20, name="Pad2")
        body.Tip = pad2
        self.doc.recompute()
        pad2.Visibility = True
        document.set_end_of_part(body, pad)
        self.assertTrue(pad.Visibility and not pad2.Visibility, (pad.Visibility, pad2.Visibility))
        document.set_end_of_part(body, pad2)
        self.assertTrue(pad2.Visibility and not pad.Visibility)
        document.set_end_of_part(body, None)
        self.assertFalse(pad.Visibility or pad2.Visibility)
        self.assertTrue(all(sk.Visibility for sk in body.Group if sk.TypeId == "Sketcher::SketchObject")
                        or True)  # sketches are left alone

    def test_end_of_part_after_a_feature_includes_its_helpers(self):
        """'After Thread' includes the chamfer InCad made for it (shown under it in the tree)."""
        body, pad = util.padded_part(self.doc, 10, incad=True)
        helper = util.add_pad(body, util.add_rect_sketch(body, w=5, h=5, name="SketchH"), 2, name="Helper")
        helper.addProperty("App::PropertyString", "InCadHelperOf", "InCad", "")
        helper.InCadHelperOf = pad.Name
        pad2 = util.add_pad(body, util.add_rect_sketch(body, w=3, h=3, name="SketchC"), 2, name="Pad2")
        body.Tip = pad2
        self.doc.recompute()
        document.set_end_of_part(body, pad)
        self.assertIs(body.Tip, helper)
        self.assertTrue(helper.Visibility and not pad.Visibility and not pad2.Visibility)
        document.set_end_of_part(body, pad2)
        self.assertIs(body.Tip, pad2)

    def test_end_of_part_never_lands_on_a_non_solid_object(self):
        """A Work Axis InCad made for a revolve (a helper) or a Work Plane in the part is not a solid feature:
        Body.Tip refuses it ('Linked object is not a PartDesign feature') and End of Part did not move."""
        body, pad = util.padded_part(self.doc, 10, incad=True)
        axis = body.newObject("PartDesign::Line", "HelperAxis")
        axis.addProperty("App::PropertyString", "InCadHelperOf", "InCad", "")
        axis.InCadHelperOf = pad.Name
        plane = body.newObject("PartDesign::Plane", "WorkPlane")
        pad2 = util.add_pad(body, util.add_rect_sketch(body, w=3, h=3, name="SketchC"), 2, name="Pad2")
        body.Tip = pad2
        self.doc.recompute()
        document.set_end_of_part(body, pad)  # its helper is only an axis: stays on the pad
        self.assertIs(body.Tip, pad)
        document.set_end_of_part(body, pad2)
        document.set_end_of_part(body, plane)  # a plane after the pad (and the axis): the last solid before it
        self.assertIs(body.Tip, pad)
        document.set_end_of_part(body, axis)
        self.assertIs(body.Tip, pad)
        document.set_end_of_part(body, [o for o in body.Group if o.TypeId == "Sketcher::SketchObject"][-1])
        self.assertTrue(body.Tip.isDerivedFrom("PartDesign::Feature"))
        self.assertNotIn("Invalid", body.State)

    def test_end_of_part_rejects_foreign_feature(self):
        body, pad = util.padded_part(self.doc, 10, incad=True)
        other = self.doc.addObject("PartDesign::Body", "Other")
        with self.assertRaises(ValueError):
            document.set_end_of_part(other, pad)


class ShownBodyTest(unittest.TestCase):
    """A file saved while a sketch was being edited keeps its Body hidden (FreeCAD hides it in sketch edit mode):
    showing the model's result must show the Body too, or the view stays blank after the file is reopened."""

    def setUp(self):
        self.doc = util.new_doc("Sb")
        self.body, self.pad = util.padded_part(self.doc, 10, incad=True)

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def test_show_result_shows_a_hidden_body(self):
        self.body.Visibility = False
        self.pad.Visibility = False
        shown = document.show_result(self.body)
        self.assertIs(shown, self.pad)
        self.assertTrue(self.body.Visibility, "the Body itself is shown, not just its tip")
        self.assertTrue(self.pad.Visibility)


class VisibilityTest(unittest.TestCase):
    """Unused sketches: open contours shown, closed ones hidden, the user's InCadShown choice wins; consumed
    sketches always hidden. Hide / Show on origin items and unused sketches."""

    def setUp(self):
        self.doc = util.new_doc("Vis")
        self.body, self.pad = util.padded_part(self.doc, 10, incad=True)
        self.closed = util.add_rect_sketch(self.body, name="Closed")  # unused
        self.path = self.body.newObject("Sketcher::SketchObject", "Path")
        self.path.AttachmentSupport = [(util.xy_plane(self.body), "")]
        self.path.MapMode = "FlatFace"
        self.path.addGeometry(Part.LineSegment(App.Vector(0, 0, 0), App.Vector(30, 0, 0)))
        self.doc.recompute()

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def _profile(self):
        p = self.pad.Profile
        return p[0] if isinstance(p, (tuple, list)) else p

    def test_show_result_shows_an_open_unused_sketch_and_hides_a_closed_one(self):
        document.show_result(self.body)
        self.assertTrue(self.path.Visibility)
        self.assertFalse(self.closed.Visibility)
        self.assertFalse(self._profile().Visibility, "a consumed sketch is hidden")

    def test_the_users_choice_wins(self):
        document.set_visibility([self.path], False)
        document.set_visibility([self.closed], True)
        document.show_result(self.body)
        self.assertFalse(self.path.Visibility)
        self.assertTrue(self.closed.Visibility)
        self.assertFalse(getattr(self.path, document.SHOWN_PROP))
        self.assertTrue(getattr(self.closed, document.SHOWN_PROP))

    def test_consumed_sketch_stays_hidden_whatever_the_flag(self):
        prof = self._profile()
        prof.addProperty("App::PropertyBool", document.SHOWN_PROP, "InCad", "")
        setattr(prof, document.SHOWN_PROP, True)
        document.show_result(self.body)
        self.assertFalse(prof.Visibility)
        with self.assertRaises(ValueError) as cm:
            document.toggle_visibility([prof])
        self.assertIn("belongs to Pad", str(cm.exception))

    def test_toggle_mixed_hides_all_then_shows_all(self):
        xy, xz = [o for o in document.origin_items(self.body) if o.Role in ("XY_Plane", "XZ_Plane")]
        xy.Visibility, xz.Visibility = True, False
        self.assertFalse(document.toggle_visibility([xy, xz]))
        self.assertFalse(xy.Visibility or xz.Visibility)
        self.assertTrue(document.toggle_visibility([xy, xz]))
        self.assertTrue(xy.Visibility and xz.Visibility)

    def test_toggle_on_a_sketch_records_the_choice(self):
        self.assertFalse(document.toggle_visibility([self.path]))
        self.assertFalse(getattr(self.path, document.SHOWN_PROP))
        document.show_result(self.body)
        self.assertFalse(self.path.Visibility, "show_result keeps the hidden choice")

    def test_toggle_refuses_nothing_and_features(self):
        with self.assertRaises(ValueError):
            document.toggle_visibility([])
        with self.assertRaises(ValueError):
            document.toggle_visibility([self.pad])

    def test_showing_one_plane_turns_the_origin_group_on_and_hides_the_rest(self):
        """A new part in the GUI: the Origin group is hidden while its items say Visible — nothing shows. Showing
        one plane must show the group and leave the other six hidden; is_shown reads the effective state."""
        origin = self.body.Origin
        origin.Visibility = False
        items = document.origin_items(self.body)
        for o in items:
            o.Visibility = True
        xy = [o for o in items if o.Role == "XY_Plane"][0]
        self.assertFalse(document.is_shown(xy))
        self.assertTrue(document.toggle_visibility([xy]), "hidden in effect: the toggle shows it")
        self.assertTrue(origin.Visibility and xy.Visibility and document.is_shown(xy))
        self.assertFalse(any(document.is_shown(o) for o in items if o is not xy))
        self.assertFalse(any(o.Visibility for o in items if o is not xy))

    def _sweep_on_path(self):
        from incad.features import shapes
        prof = self.body.newObject("Sketcher::SketchObject", "Prof")
        prof.AttachmentSupport = [([o for o in self.body.Origin.OriginFeatures if o.Role == "YZ_Plane"][0], "")]
        prof.MapMode = "FlatFace"
        prof.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 2))
        self.doc.recompute()
        sweep = shapes.SWEEP.create(self.doc, self.body, None, {"profile": "Prof", "path": "Path", "operation": "join"})
        self.doc.recompute()
        return prof, sweep

    def test_a_sweeps_path_is_consumed(self):
        prof, sweep = self._sweep_on_path()
        self.assertFalse(document.is_unused_sketch(self.path), "the Sweep's Spine uses it")
        self.assertFalse(document.sketch_shown(self.path))
        document.show_result(self.body)
        self.assertFalse(self.path.Visibility)
        self.assertFalse(prof.Visibility)
        with self.assertRaises(ValueError) as cm:
            document.toggle_visibility([self.path])
        self.assertIn("belongs to " + sweep.Label, str(cm.exception))

    def test_a_lofts_sections_are_consumed(self):
        from incad.features import shapes
        secs = []
        for i, z in enumerate((0, 20)):
            sk = self.body.newObject("Sketcher::SketchObject", "Sec%d" % i)
            sk.AttachmentSupport = [(util.xy_plane(self.body), "")]
            sk.MapMode = "FlatFace"
            sk.AttachmentOffset = App.Placement(App.Vector(60, 60, z), App.Rotation())
            sk.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 4 + i))
            secs.append(sk)
        self.doc.recompute()
        shapes.LOFT.create(self.doc, self.body, None, {"sections": "Sec0,Sec1", "ruled": False, "closed": False,
                                                       "operation": "join"})
        self.doc.recompute()
        self.assertFalse(document.is_unused_sketch(secs[0]))
        self.assertFalse(document.is_unused_sketch(secs[1]), "the second section (f.Sections) is used too")

    def test_work_features_hide_and_show(self):
        """A work plane, axis or point (PartDesign datums) toggles like an origin item; Show All / Hide All
        Origin leave it alone."""
        wp = self.body.newObject("PartDesign::Plane", "WorkPlane")
        wa = self.body.newObject("PartDesign::Line", "WorkAxis")
        self.doc.recompute()
        self.assertTrue(document.is_shown(wp))
        self.assertFalse(document.toggle_visibility([wp, wa]))
        self.assertFalse(wp.Visibility or wa.Visibility)
        self.assertFalse(document.is_shown(wp))
        document.set_visibility(document.origin_items(self.body), True)
        self.assertFalse(wp.Visibility, "Show All Origin is about the origin")
        self.assertTrue(document.toggle_visibility([wp]))
        self.assertTrue(wp.Visibility)
        document.show_result(self.body)
        self.assertTrue(wp.Visibility, "a tip move does not hide a work plane")

    def test_origin_items_are_the_seven(self):
        self.assertEqual(sorted(o.Role for o in document.origin_items(self.body)),
                         ["Origin", "XY_Plane", "XZ_Plane", "X_Axis", "YZ_Plane", "Y_Axis", "Z_Axis"])
