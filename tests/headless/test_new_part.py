import unittest

import FreeCAD as App
from incad import actions
from incad.core import document, prefs


class NewPartTest(unittest.TestCase):
    def setUp(self):
        prefs.use_memory_backend()

    def tearDown(self):
        for name in list(App.listDocuments()):
            App.closeDocument(name)

    def test_asks_then_remembers(self):
        doc = actions.new_part(ask=lambda: ("part", "in", True))
        self.assertTrue(document.is_incad_part(doc))
        self.assertEqual(document.part_units(doc), "in")
        self.assertEqual((prefs.default_units(), prefs.remember_new_choice()), ("in", True))
        doc2 = actions.new_part(ask=lambda: self.fail("must not ask when remembered"))
        self.assertEqual(document.part_units(doc2), "in")

    def test_cancel_creates_nothing(self):
        self.assertIsNone(actions.new_part(ask=lambda: None))
        self.assertEqual(App.listDocuments(), {})

    def test_creation_is_not_an_undo_step(self):
        doc = actions.new_part(ask=lambda: ("part", "mm", False))
        self.assertEqual(doc.UndoNames, [])
        self.assertEqual(doc.UndoMode, 1)
