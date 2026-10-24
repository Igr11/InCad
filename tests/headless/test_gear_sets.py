"""Spur Gears and Worm Gear (the user: one dialog makes the pair, as Inventor's Design Accelerator): both gears made,
the second meshing with the first in a Solid of its own, either one opening the set, One gear / Pair switching,
the second going with the first, and a worm with its wheel."""
import math
import unittest

import FreeCAD as App
from incad.core import delete, document, gears
from incad.features import gear, kind_for
from headless import util


class GearSetTest(unittest.TestCase):
    def setUp(self):
        self.doc = util.new_doc("GS")
        self.body = document.make_part(self.doc)
        self.doc.recompute()

    def tearDown(self):
        App.closeDocument(self.doc.Name)

    def make(self, kind=gear.SPUR_GEARS, **over):
        values = kind.defaults(self.doc, self.body)
        values.update(over)
        f = kind.create(self.doc, self.body, None, values)
        self.doc.recompute()
        return f

    def test_one_dialog_makes_the_pair(self):
        lead = self.make(teeth="20", size2="ratio", ratio="1.5", helix="15 °")
        second = gear.second_of(lead)
        self.assertIsNotNone(second)
        self.assertIsNot(second.getParentGeoFeatureGroup(), lead.getParentGeoFeatureGroup())
        self.assertEqual(gear.effective(second)["teeth"], 30)
        self.assertEqual(gear.effective(second)["hand"], "left")
        self.assertLess(lead.Shape.common(second.Shape).Volume, 1e-3 * second.Shape.Volume / 30)
        self.assertIs(kind_for(second), gear.SPUR_GEARS, "either one opens the set")
        self.assertEqual(gear.SPUR_GEARS.read(self.doc, second), gear.SPUR_GEARS.read(self.doc, lead))
        self.assertIn("ratio 30:20 = 1.5", gear.SPUR_GEARS.info(gear.SPUR_GEARS.read(self.doc, lead)))

    def test_editing_through_the_second_changes_both(self):
        lead = self.make(teeth="20", size2="teeth", teeth2="25")
        second = gear.second_of(lead)
        v = gear.SPUR_GEARS.read(self.doc, second)
        v.update(module="1.5 mm", teeth2="40")
        gear.SPUR_GEARS.update(self.doc, second, v)
        self.assertEqual(gear.effective(lead)["module"], 1.5)
        self.assertEqual(gear.effective(second)["teeth"], 40)
        self.assertLess(lead.Shape.common(second.Shape).Volume, 1e-3 * second.Shape.Volume / 40)

    def test_one_gear_and_back_to_a_pair(self):
        lead = self.make()
        bodies = len(document.bodies(self.doc))
        v = gear.SPUR_GEARS.read(self.doc, lead)
        gear.SPUR_GEARS.update(self.doc, lead, dict(v, make="one"))
        self.assertIsNone(gear.second_of(lead))
        self.assertEqual(len(document.bodies(self.doc)), bodies - 1, "its Solid went with it")
        gear.SPUR_GEARS.update(self.doc, lead, dict(v, make="pair"))
        self.assertIsNotNone(gear.second_of(lead))

    def test_deleting_the_first_takes_the_second(self):
        lead = self.make()
        name = gear.second_of(lead).Name
        delete.delete(lead)
        self.assertIsNone(self.doc.getObject(name))
        self.assertEqual([o for o in self.doc.Objects if gear.is_gear(o)], [])

    def test_a_worm_gear_set(self):
        worm = self.make(gear.WORM_GEAR, starts="2", size2="ratio", ratio="20")
        wheel = gear.second_of(worm)
        self.assertTrue(gear.is_gear(worm, "worm") and gear.is_gear(wheel, "gear"))
        self.assertEqual(gear.effective(wheel)["teeth"], 40)
        self.assertAlmostEqual(gear.effective(wheel)["helix"], gears.lead_angle(2, 2, 20))
        self.assertLess(worm.Shape.common(wheel.Shape).Volume, 0.02 * wheel.Shape.Volume / 40)
        self.assertIs(kind_for(wheel), gear.WORM_GEAR)
        self.assertIn("ratio 40:2 = 20", gear.WORM_GEAR.info(gear.WORM_GEAR.read(self.doc, worm)))

    def test_bored_through_by_default(self):
        """The user: a worm without a bore gave no axis to pick and go on working with."""
        import Part
        for kind in (gear.SPUR_GEARS, gear.WORM_GEAR):
            lead = self.make(kind)
            for g in (lead, gear.second_of(lead)):
                axis = gear.frame(g)
                mid = axis.multVec(App.Vector(0, 0, (g.Length.Value if gear.is_gear(g, "worm") else g.Width.Value) / 2))
                if gear.is_gear(gear.mate_of(g), "worm"):
                    mid = axis.Base
                self.assertFalse(g.Shape.isInside(mid, 1e-6, True), "a hole along %s's axis" % g.Label)
                self.assertTrue(any(f.Surface.TypeId == "Part::GeomCylinder" and f.Surface.Radius < 6
                                    for f in g.Shape.Faces), "its round face gives the axis")

    def in_mesh(self, a, b):
        tiny = 1e-3 * min(a.Shape.Volume, b.Shape.Volume) / 20
        self.assertLess(a.Shape.common(b.Shape).Volume, tiny, "%s and %s run into each other" % (a.Label, b.Label))
        self.assertLess(a.Shape.distToShape(b.Shape)[0], 0.05, "%s and %s touch" % (a.Label, b.Label))

    def apart(self, a, b):
        self.assertGreater(a.Shape.distToShape(b.Shape)[0], 0.5, "%s and %s apart" % (a.Label, b.Label))

    def test_a_third_gear_meshes_with_one_already_there(self):
        """The user: a third gear landed inside the pair, and its dialog had nothing to put it in mesh. Mesh with
        puts gear 1 of the new set at a gear already there, Around turns it round that gear; module, pressure and
        helix angle come from that gear."""
        lead = self.make(teeth="20", size2="ratio", ratio="1.5")
        second = gear.second_of(lead)
        for around in ("90 °", "30 °", "-60 °"):
            third = self.make(mesh=second.Name, around=around, make="one", teeth="17", module="5 mm")
            self.assertEqual(gear.effective(third)["module"], 2.0, "the mate's module")
            centre = gear.frame(third).Base - gear.frame(second).Base
            self.assertAlmostEqual(math.degrees(math.atan2(centre.y, centre.x)) % 360, float(around.split()[0]) % 360,
                                   6)
            self.in_mesh(third, second)
            self.apart(third, lead)
            v = gear.SPUR_GEARS.read(self.doc, third)
            self.assertEqual((v["mesh"], v["around"].replace(" ", "")), (second.Name, around.replace(" ", "")))
            delete.delete(third)

    def test_a_meshing_set_and_its_second_round_it(self):
        lead = self.make(teeth="20", size2="ratio", ratio="1.5")
        second = gear.second_of(lead)
        g3 = self.make(mesh=second.Name, around="90 °", teeth="16", size2="teeth", teeth2="24", around2="45 °")
        g4 = gear.second_of(g3)
        self.in_mesh(g3, second)
        self.in_mesh(g4, g3)
        for a, b in ((g4, second), (g4, lead), (g3, lead)):
            self.apart(a, b)
        self.assertEqual(gear.SPUR_GEARS.read(self.doc, g4)["around2"].replace(" ", ""), "45°")

    def test_a_worm_on_a_gear_already_there(self):
        lead = self.make(teeth="30", make="one")
        worm = self.make(gear.WORM_GEAR, mesh=lead.Name, around="120 °", make="one")
        self.assertEqual(gear.effective(worm)["module"], 2.0)
        self.assertLess(worm.Shape.common(lead.Shape).Volume, 0.02 * lead.Shape.Volume / 30)
        self.assertLess(worm.Shape.distToShape(lead.Shape)[0], 0.05)
        c = gear.frame(lead).Base
        mid = gear.frame(worm).multVec(App.Vector(0, 0, worm.Length.Value / 2)) - c
        self.assertAlmostEqual(math.degrees(math.atan2(mid.y, mid.x)), 120, 6)

    def test_a_new_set_stands_beside_the_gears_there(self):
        first = self.make()
        values = gear.SPUR_GEARS.defaults(self.doc, self.body)
        self.assertNotEqual(values["offset_x"], "0 mm")
        lead = self.make()
        for a in (first, gear.second_of(first)):
            for b in (lead, gear.second_of(lead)):
                self.apart(a, b)

    def test_the_gizmo_is_the_firsts(self):
        lead = self.make(offset_x="10 mm")
        self.assertIsNotNone(gear.gizmo_frame(gear.second_of(lead)))
        self.assertAlmostEqual(gear.gizmo_frame(gear.second_of(lead)).Base.x, 10, 6)


if __name__ == "__main__":
    unittest.main()
