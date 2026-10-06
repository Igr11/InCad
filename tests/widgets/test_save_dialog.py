import unittest

from widgets import qtapp
from incad.ui.save_dialog import SaveDialog


class SaveDialogTest(unittest.TestCase):
    def setUp(self):
        qtapp.app()
        self.d = SaveDialog([("Part1", "Part1.FCStd"), ("Asm", "")], "dark")

    def test_every_file_is_listed_and_checked(self):
        self.assertEqual(self.d.rows(), [("Part1", True), ("Asm", True)])

    def test_choices(self):
        self.d.set_checked("Asm", False)
        self.d.save_button.click()
        self.assertEqual(self.d.result_choice(), ("save", ["Part1"]))

    def test_dont_save_and_cancel(self):
        self.d.dont_save_button.click()
        self.assertEqual(self.d.result_choice(), ("discard", []))
        d2 = SaveDialog([("A", "")], "light")
        d2.cancel_button.click()
        self.assertEqual(d2.result_choice(), ("cancel", []))
