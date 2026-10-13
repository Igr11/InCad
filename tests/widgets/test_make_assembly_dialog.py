"""The Make Assembly names dialog: filled names, a refused name disables OK and says why, hover reports the row."""
import unittest

from widgets import qtapp
from incad.ui.make_assembly_dialog import MakeAssemblyDialog


class MakeAssemblyDialogTest(unittest.TestCase):
    def setUp(self):
        qtapp.app()
        self.d = MakeAssemblyDialog("Plate-Assembly", [("Plate-Solid1", "2000 mm³"), ("Plate-Solid2", "500 mm³")],
                                    lambda asm, names: "A name is used twice" if len(set(names)) < len(names) else "")

    def test_names_are_filled(self):
        self.assertEqual(self.d.names(), ("Plate-Assembly", ["Plate-Solid1", "Plate-Solid2"]))
        self.assertTrue(self.d.ok_button.isEnabled())

    def test_a_refused_name_disables_ok(self):
        self.d.name_field(1).setText("Plate-Solid1")
        self.assertFalse(self.d.ok_button.isEnabled())
        self.assertIn("twice", self.d.error_text())

    def test_existing_files_can_be_replaced(self):
        d = MakeAssemblyDialog("Plate-Assembly", [("Plate-Solid1", "2000 mm³")],
                               lambda asm, names, replace=False: "" if replace else "Plate-Assembly.FCStd exists",
                               existing=lambda asm, names: ["Plate-Assembly"])
        self.assertFalse(d.ok_button.isEnabled())
        self.assertFalse(d.replace_box.isHidden(), "the choice is offered when files exist")
        d.replace_box.setChecked(True)
        self.assertTrue(d.ok_button.isEnabled())
        self.assertTrue(d.replace())
        self.assertEqual(d.error_text(), "")

    def test_no_replace_choice_without_existing_files(self):
        self.assertTrue(self.d.replace_box.isHidden())
        self.assertFalse(self.d.replace())

    def test_hover_reports_the_row(self):
        seen = []
        self.d.hovered.connect(seen.append)
        self.d.hover_row(1)
        self.d.hover_row(-1)
        self.assertEqual(seen, [1, -1])
