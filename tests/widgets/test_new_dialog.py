import unittest

from widgets import qtapp
from incad.qt import QtWidgets
from incad.ui.new_dialog import NewDialog


class NewDialogTest(unittest.TestCase):
    def setUp(self):
        qtapp.app()

    def test_defaults(self):
        d = NewDialog()
        self.assertEqual(d.choice(), ("part", "mm", False))
        self.assertFalse(d.assembly.isEnabled())
        self.assertTrue(d.part.isChecked())

    def test_inch_and_remember(self):
        d = NewDialog(units="in", remember=True, theme="dark")
        self.assertEqual(d.choice(), ("part", "in", True))
        d.mm.click()
        self.assertEqual(d.choice(), ("part", "mm", True))
        self.assertFalse(d.inch.isChecked())

    def test_create_accepts(self):
        d = NewDialog()
        d.create_button.click()
        self.assertEqual(d.result(), QtWidgets.QDialog.Accepted)
